import { env } from 'cloudflare:workers';
import { drizzle } from 'drizzle-orm/d1';
import * as schema from './schema';

let schemaReady: Promise<void> | undefined;

const notificationTrigger = `CREATE TRIGGER IF NOT EXISTS trg_mite_alert_notification_outbox_v3
  AFTER INSERT ON frame_predictions
  WHEN NEW.decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED')
    AND (upper(NEW.class_label) LIKE '%MITE%' OR NEW.class_label LIKE '%응애%'
      OR EXISTS (
        SELECT 1 FROM inference_runs ir
        WHERE ir.id = NEW.inference_run_id AND upper(ir.task) LIKE '%MITE%'
      ))
  BEGIN
    INSERT INTO notification_outbox(
      id, farm_id, frame_prediction_id, recipient_member_id, recipient_phone,
      notification_type, payload_json, status, attempts, last_error, created_at, sent_at
    )
    SELECT lower(hex(randomblob(16))), cs.farm_id, NEW.id, fm.id, fm.phone,
      'MITE_ALERT', json_object('classLabel', NEW.class_label, 'confidence', NEW.confidence),
      'PENDING', 0, NULL, NEW.created_at, NULL
    FROM frames fr
    JOIN capture_sessions cs ON cs.id = fr.capture_session_id
    JOIN farm_members fm ON fm.farm_id = cs.farm_id
    WHERE fr.id = NEW.frame_id AND fm.status = 'ACTIVE'
      AND fm.phone IS NOT NULL AND fm.phone_verified_at IS NOT NULL
      AND fm.notifications_enabled = 1
      AND NOT EXISTS (
        SELECT 1 FROM notification_outbox existing
        JOIN frame_predictions existing_fp ON existing_fp.id = existing.frame_prediction_id
        WHERE existing.recipient_member_id = fm.id
          AND existing.notification_type = 'MITE_ALERT'
          AND existing.status IN ('PENDING', 'SENDING', 'SENT')
          AND existing_fp.inference_run_id = NEW.inference_run_id
      );
  END`;

const protectLastOwnerRoleTrigger = `CREATE TRIGGER IF NOT EXISTS trg_farm_members_keep_last_owner_update
  BEFORE UPDATE OF role, status ON farm_members
  WHEN OLD.role = 'OWNER' AND OLD.status = 'ACTIVE'
    AND (NEW.role <> 'OWNER' OR NEW.status <> 'ACTIVE')
    AND (SELECT COUNT(*) FROM farm_members
      WHERE farm_id = OLD.farm_id AND role = 'OWNER' AND status = 'ACTIVE') <= 1
  BEGIN
    SELECT RAISE(ABORT, 'LAST_OWNER_REQUIRED');
  END`;

const protectLastOwnerDeleteTrigger = `CREATE TRIGGER IF NOT EXISTS trg_farm_members_keep_last_owner_delete
  BEFORE DELETE ON farm_members
  WHEN OLD.role = 'OWNER' AND OLD.status = 'ACTIVE'
    AND (SELECT COUNT(*) FROM farm_members
      WHERE farm_id = OLD.farm_id AND role = 'OWNER' AND status = 'ACTIVE') <= 1
  BEGIN
    SELECT RAISE(ABORT, 'LAST_OWNER_REQUIRED');
  END`;

export function getDb() {
  if (!env.DB) throw new Error('Cloudflare D1 binding `DB` is unavailable.');
  return drizzle(env.DB, { schema });
}

async function applyColumnAdditions(statements: D1PreparedStatement[]) {
  for (const statement of statements) {
    try {
      await statement.run();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (!/duplicate column name/i.test(message)) throw error;
    }
  }
}

const definitions = [
  `CREATE TABLE IF NOT EXISTS cultivars (
    code TEXT PRIMARY KEY NOT NULL, display_name_ko TEXT NOT NULL, operational_status TEXT NOT NULL,
    supports_quality INTEGER NOT NULL, supports_ripeness INTEGER NOT NULL,
    supports_mite_warning INTEGER NOT NULL, created_at TEXT NOT NULL
  )`,
  `INSERT OR IGNORE INTO cultivars(
    code, display_name_ko, operational_status, supports_quality,
    supports_ripeness, supports_mite_warning, created_at
  ) VALUES ('SEOLHYANG', '설향', 'ACTIVE', 1, 1, 1, '2026-08-27T00:00:00.000Z')`,
  `CREATE TABLE IF NOT EXISTS crop_types (
    code TEXT PRIMARY KEY NOT NULL, display_name_ko TEXT NOT NULL, created_at TEXT NOT NULL
  )`,
  `INSERT OR IGNORE INTO crop_types(code, display_name_ko, created_at)
    VALUES ('STRAWBERRY', '딸기', '2026-08-27T00:00:00.000Z')`,
  `CREATE TABLE IF NOT EXISTS crop_profiles (
    crop_code TEXT PRIMARY KEY NOT NULL, image_uri TEXT, description_ko TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
    FOREIGN KEY (crop_code) REFERENCES crop_types(code) ON DELETE CASCADE
  )`,
  `INSERT OR IGNORE INTO crop_profiles(crop_code, image_uri, description_ko, updated_at)
    VALUES ('STRAWBERRY', '/crops/strawberry-cover-v1.png', '수확 과실 품질 판독과 병해충 조기예찰을 함께 관리합니다.', '2026-08-27T00:00:00.000Z')`,
  `CREATE TABLE IF NOT EXISTS crop_guides (
    id TEXT PRIMARY KEY NOT NULL, crop_code TEXT NOT NULL, cultivar_code TEXT,
    guide_type TEXT NOT NULL, title TEXT NOT NULL, symptom_summary TEXT NOT NULL,
    risk_summary TEXT NOT NULL, prevention_summary TEXT NOT NULL, response_summary TEXT NOT NULL,
    source_title TEXT NOT NULL, source_url TEXT NOT NULL, reviewed_at TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (crop_code) REFERENCES crop_types(code) ON DELETE CASCADE,
    FOREIGN KEY (cultivar_code) REFERENCES cultivars(code) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_crop_guides_crop_cultivar
    ON crop_guides(crop_code, cultivar_code, status, display_order)`,
  `INSERT OR IGNORE INTO crop_guides(
    id, crop_code, cultivar_code, guide_type, title, symptom_summary, risk_summary,
    prevention_summary, response_summary, source_title, source_url, reviewed_at,
    display_order, status, created_at, updated_at
  ) VALUES (
    'guide-strawberry-mite', 'STRAWBERRY', NULL, 'PEST', '점박이응애',
    '잎 뒷면에서 흡즙하며 초기에는 잎 표면에 작은 황백색 반점이 나타나고 밀도가 높아지면 잎이 마르거나 거미줄이 보일 수 있습니다.',
    '고온·건조 조건에서 세대가 빨라질 수 있어 하우스 가장자리와 잎 뒷면을 먼저 확인하는 것이 중요합니다.',
    '새 묘와 반입 자재를 점검하고 구역별로 잎 뒷면을 정기 관찰하며 잡초와 심한 피해 잎을 관리합니다.',
    '의심 구역을 표시하고 잎 뒷면을 확대 관찰해 재확인합니다. 방제 시 등록 약제와 안전사용기준을 확인하고 저항성 관리를 고려합니다.',
    '국가농작물병해충관리시스템',
    'https://ncpms.rda.go.kr/npms/HlsctIstguInfoDtlR.np?hlsctIstguNo=H00000527&totalSearchYn=Y',
    '2026-08-27', 10, 'ACTIVE', '2026-08-27T00:00:00.000Z', '2026-08-27T00:00:00.000Z'
  )`,
  `INSERT OR IGNORE INTO crop_guides(
    id, crop_code, cultivar_code, guide_type, title, symptom_summary, risk_summary,
    prevention_summary, response_summary, source_title, source_url, reviewed_at,
    display_order, status, created_at, updated_at
  ) VALUES (
    'guide-strawberry-powdery', 'STRAWBERRY', NULL, 'DISEASE', '흰가루병',
    '잎 뒷면에 흰색 균총이 나타나며 과실에는 흰가루를 뿌린 듯한 증상이 생길 수 있습니다. 어린 과실은 비대가 억제될 수 있습니다.',
    '주로 봄과 가을의 시설재배에서 발생하며 병든 식물체 잔재가 전염원이 될 수 있습니다.',
    '건전한 묘를 사용하고 통풍·환기·관수를 관리하며 발생 잎이나 발병 과실은 바로 제거합니다.',
    '증상 부위를 격리·제거하고 확산 범위를 확인합니다. 등록 약제를 사용할 때는 딸기 적용 여부와 수확 전 안전사용기준을 확인합니다.',
    '국가농작물병해충관리시스템',
    'https://ncpms.rda.go.kr/npms/SicknsInfoDtlR.np?sicknsListNo=D00000459&totalSearchYn=Y',
    '2026-08-27', 20, 'ACTIVE', '2026-08-27T00:00:00.000Z', '2026-08-27T00:00:00.000Z'
  )`,
  `INSERT OR IGNORE INTO crop_guides(
    id, crop_code, cultivar_code, guide_type, title, symptom_summary, risk_summary,
    prevention_summary, response_summary, source_title, source_url, reviewed_at,
    display_order, status, created_at, updated_at
  ) VALUES (
    'guide-strawberry-gray-mold', 'STRAWBERRY', NULL, 'DISEASE', '잿빛곰팡이병',
    '과실·꽃받침·과경·잎·엽병 등 지상부에 발생하며 특히 과실에 큰 피해를 줄 수 있습니다.',
    '저온·다습하고 밤낮 온도차가 큰 시설 환경에서 발생 위험이 높아집니다.',
    '시설 내 과습을 줄이고 환기와 보온을 함께 관리하며 병든 과실과 잔여물은 즉시 제거합니다.',
    '발병 과실과 주변 잔재를 분리하고 인접 주를 점검합니다. 등록 약제와 안전사용기준은 공식 시스템에서 최종 확인합니다.',
    '농촌진흥청 농사로',
    'https://www.nongsaro.go.kr/portal/ps/psb/psby/vodPlay.ps?menuId=PS00069&mvpClipNo=3&mvpNo=743',
    '2026-08-27', 30, 'ACTIVE', '2026-08-27T00:00:00.000Z', '2026-08-27T00:00:00.000Z'
  )`,
  `INSERT OR IGNORE INTO crop_guides(
    id, crop_code, cultivar_code, guide_type, title, symptom_summary, risk_summary,
    prevention_summary, response_summary, source_title, source_url, reviewed_at,
    display_order, status, created_at, updated_at
  ) VALUES
  (
    'guide-strawberry-anthracnose', 'STRAWBERRY', NULL, 'FUNGAL', '탄저병',
    '어미묘의 잎자루 안쪽이 붉어지거나 런너와 잎자루가 물을 먹은 듯 검게 변할 수 있습니다. 심해지면 뿌리와 줄기가 만나는 부분이 갈색으로 변하고 빠르게 시듭니다.',
    '고온다습한 날씨, 장마, 잎에 물기가 오래 남는 환경에서 퍼지기 쉽습니다. 특히 육묘기와 정식 직후에 주의합니다.',
    '건강한 모주를 사용하고 비가림과 점적관수로 잎이 젖는 시간을 줄입니다. 병든 조직과 잡초를 제거하고 가위와 작업도구를 깨끗이 관리합니다.',
    '의심되는 포기는 뿌리째 분리해 봉투에 담아 재배 구역 밖으로 옮기고 주변 포기도 함께 살펴봅니다. 방제 전에는 딸기 등록 여부와 안전사용기준을 확인합니다.',
    '농촌진흥청',
    'https://www.rda.go.kr/board/board.do?boardId=farmlcltinfo&currPage=1&dataNo=100000810791&mode=updateCnt&prgId=day_farmlcltinfoEntry&searchEDate=&searchKey=&searchSDate=&searchVal=',
    '2026-08-28', 40, 'ACTIVE', '2026-08-28T00:00:00.000Z', '2026-08-28T00:00:00.000Z'
  ),
  (
    'guide-strawberry-fusarium-wilt', 'STRAWBERRY', NULL, 'FUNGAL', '시들음병',
    '한쪽 잎이 작아 보이거나 잎자루 일부가 갈색으로 변하고 생육이 늦어질 수 있습니다. 줄기 안쪽의 물길이 갈색으로 변하고 뿌리가 썩기도 합니다.',
    '더운 육묘기와 정식 뒤 고온기에 잘 나타나며 배지의 염류가 높거나 산도가 너무 낮을 때 위험이 커질 수 있습니다.',
    '병 없는 모주와 자묘를 쓰고 깨끗한 상토와 포트를 사용합니다. 과한 비료와 물고임을 피하고 작업도구를 깨끗이 관리합니다.',
    '의심 포기와 연결된 자묘를 분리하고 뿌리와 줄기 밑부분을 확인합니다. 물과 작업도구를 통한 번짐을 막고 필요한 방제는 현재 등록 여부를 확인합니다.',
    '농촌진흥청 농사로',
    'https://www.rda.go.kr/middlePopOpenPopNongsaroDBView.do?no=1779',
    '2026-08-28', 50, 'ACTIVE', '2026-08-28T00:00:00.000Z', '2026-08-28T00:00:00.000Z'
  ),
  (
    'guide-strawberry-phytophthora', 'STRAWBERRY', NULL, 'DISEASE', '역병',
    '잎이 데친 것처럼 보이면서 시들 수 있습니다. 줄기 밑부분을 잘랐을 때 안쪽이 갈색으로 변하거나 가운데가 비어 보일 수 있고 이후 포기 전체가 말라 죽기도 합니다.',
    '연작지와 물이 잘 빠지지 않는 과습한 곳에서 위험이 큽니다. 오염된 물을 따라 번질 수 있어 육묘기와 정식 뒤를 주의합니다.',
    '병 없는 묘와 깨끗한 상토를 사용하고 배수가 잘되게 관리합니다. 재사용 자재와 작업도구, 관수 물의 오염을 줄입니다.',
    '병든 포기는 바로 분리하고 같은 물길을 쓰는 주변 포기도 확인합니다. 재배 구역과 도구를 깨끗이 하고 방제 전 현재 등록 여부와 안전사용기준을 확인합니다.',
    '농촌진흥청 농사로',
    'https://www.rda.go.kr/middlePopOpenPopNongsaroDBView.do?no=1779',
    '2026-08-28', 60, 'ACTIVE', '2026-08-28T00:00:00.000Z', '2026-08-28T00:00:00.000Z'
  ),
  (
    'guide-strawberry-thrips', 'STRAWBERRY', NULL, 'PEST', '총채벌레류',
    '꽃과 꽃봉오리 안에 아주 작은 벌레가 보이거나 꽃잎 색이 빠지고 오그라들 수 있습니다. 과실 표면과 꽃받침 둘레가 갈색으로 변해 상품성이 떨어질 수 있습니다.',
    '꽃이 피는 시기에 시설 안에서 빠르게 늘 수 있고 시설 주변 잡초가 들어오는 길이 될 수 있습니다.',
    '꽃과 꽃봉오리를 확대해 자주 보고 흰색이나 노란색 끈끈이판으로 발생 여부를 살핍니다. 시설 안팎의 잡초도 관리합니다.',
    '꽃과 과실에 피해가 보이기 전에 발생 위치를 표시하고 끈끈이판과 꽃 조사를 함께해 번진 범위를 확인합니다. 수정벌 영향과 딸기 등록 여부를 반드시 확인합니다.',
    '국가농작물병해충관리시스템',
    'https://ncpms.rda.go.kr/npms/HlsctIstguInfoDtlR.np?hlsctIstguNo=H00000262&totalSearchYn=Y',
    '2026-08-28', 70, 'ACTIVE', '2026-08-28T00:00:00.000Z', '2026-08-28T00:00:00.000Z'
  ),
  (
    'guide-strawberry-fungus-gnat', 'STRAWBERRY', NULL, 'PEST', '작은뿌리파리',
    '어린뿌리가 상하고 갈색으로 변하면서 포기의 생육이 느려지거나 시들 수 있습니다. 배지 위에 감자 조각을 놓아 유충이 있는지 살펴볼 수 있습니다.',
    '온실 배지가 계속 축축할 때 늘기 쉽고 육묘기와 정식 뒤에 피해가 두드러질 수 있습니다.',
    '배지에 물이 고이지 않게 하고 노란색 끈끈이판으로 성충을 살핍니다. 들여오는 상토와 묘가 깨끗한지도 확인합니다.',
    '끈끈이판과 감자 조각으로 성충과 유충이 퍼진 범위를 확인하고 먼저 과습 원인을 고칩니다. 방제 시 수정벌 영향과 등록·안전사용기준을 확인합니다.',
    '농촌진흥청 농사로',
    'https://www.rda.go.kr/middlePopOpenPopNongsaroDBView.do?no=1779',
    '2026-08-28', 80, 'ACTIVE', '2026-08-28T00:00:00.000Z', '2026-08-28T00:00:00.000Z'
  )`,
  `UPDATE crop_guides SET guide_type = 'FUNGAL'
    WHERE id IN ('guide-strawberry-powdery', 'guide-strawberry-gray-mold')`,
  `UPDATE crop_guides SET
    symptom_summary = '어린 과실에 물을 먹은 듯한 작은 갈색 반점이 생기고 꽃받침·과경·잎자루가 갈색으로 변할 수 있습니다. 심해지면 과실이 물러 썩고 잿빛 곰팡이가 보입니다.',
    risk_summary = '기온이 낮고 습도가 높거나 흐린 날이 이어질 때, 포기가 너무 빽빽하고 바람이 잘 통하지 않을 때 위험이 커집니다. 설향은 냉해를 입은 뒤 더 주의합니다.',
    prevention_summary = '환기와 보온으로 물방울과 과습을 줄이고 죽은 잎·늙은 잎·붙어 있는 꽃잎과 병든 과실을 바로 치웁니다. 질소 비료를 지나치게 주지 않습니다.',
    response_summary = '병든 잎·꽃·과실을 즉시 제거해 재배 구역 밖으로 옮기고 옆 과실을 다시 살펴봅니다. 수정벌 영향과 딸기 등록 여부·안전사용기준을 확인합니다.',
    source_title = '농촌진흥청 ASTIS',
    source_url = 'https://astis.rda.go.kr/api/field/consltCont.ps?cntntsNo=251183',
    reviewed_at = '2026-08-28', updated_at = '2026-08-28T00:00:00.000Z'
    WHERE id = 'guide-strawberry-gray-mold'`,
  `UPDATE crop_guides SET
    symptom_summary = '응애가 잎 뒷면에서 즙을 빨아먹어 잎 앞면에 작은 흰 반점이 무더기로 생깁니다. 심해지면 잎이 노랗거나 갈색으로 변하고 가는 거미줄이 보일 수 있습니다.',
    risk_summary = '덥고 건조할 때 빠르게 늘어납니다. 시설에서는 계절과 관계없이 생길 수 있어 하우스 가장자리와 잎 뒷면을 자주 봅니다.',
    prevention_summary = '새로 들여오는 묘를 확인하고 구역별로 잎 뒷면을 정기적으로 살핍니다. 잡초와 늙은 잎을 관리하고 처음 적게 보일 때 천적 활용 가능성도 확인합니다.',
    response_summary = '발생 위치를 표시하고 옆 포기까지 잎 뒷면을 확대해 봅니다. 같은 성분의 제품만 반복하지 말고 딸기 등록 여부·안전사용기준과 천적에 미치는 영향을 확인합니다.',
    reviewed_at = '2026-08-28', updated_at = '2026-08-28T00:00:00.000Z'
    WHERE id = 'guide-strawberry-mite'`,
  `UPDATE crop_guides SET
    symptom_summary = '잎 뒷면에 흰 곰팡이가 보이고 과실이나 과실 꼭지에도 흰 가루를 뿌린 듯한 모습이 생길 수 있습니다. 어린 과실은 잘 자라지 않고 단단해질 수 있습니다.',
    risk_summary = '봄과 가을 시설재배에서 잘 생기며 병든 잎과 과실이 남아 있거나 바람이 잘 통하지 않을 때 위험이 커질 수 있습니다.',
    prevention_summary = '병 없는 묘를 쓰고 환기와 물주기를 알맞게 관리합니다. 정식할 때 늙은 아랫잎을 정리하고 병든 잎과 과실은 일찍 제거합니다.',
    response_summary = '병든 부분을 바로 제거해 따로 처리하고 주변 잎 뒷면과 어린 과실을 자세히 살핍니다. 사용할 제품은 딸기 등록 여부와 수확 전 안전사용기간을 확인합니다.',
    reviewed_at = '2026-08-28', updated_at = '2026-08-28T00:00:00.000Z'
    WHERE id = 'guide-strawberry-powdery'`,
  `CREATE TABLE IF NOT EXISTS crop_stages (
    code TEXT PRIMARY KEY NOT NULL, display_name_ko TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0
  )`,
  `INSERT OR IGNORE INTO crop_stages(code, display_name_ko, display_order) VALUES
    ('SEEDLING', '육묘', 10),
    ('TRANSPLANT', '정식·활착', 20),
    ('VEGETATIVE', '잎·줄기 생육', 30),
    ('FLOWERING', '개화', 40),
    ('FRUITING', '착과·비대', 50),
    ('HARVEST', '수확', 60)`,
  `CREATE TABLE IF NOT EXISTS crop_guide_stages (
    id TEXT PRIMARY KEY NOT NULL, guide_id TEXT NOT NULL, stage_code TEXT NOT NULL,
    FOREIGN KEY (guide_id) REFERENCES crop_guides(id) ON DELETE CASCADE,
    FOREIGN KEY (stage_code) REFERENCES crop_stages(code) ON DELETE CASCADE,
    UNIQUE(guide_id, stage_code)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_crop_guide_stages_stage
    ON crop_guide_stages(stage_code, guide_id)`,
  `INSERT OR IGNORE INTO crop_guide_stages(id, guide_id, stage_code) VALUES
    ('stage-mite-seedling', 'guide-strawberry-mite', 'SEEDLING'),
    ('stage-mite-transplant', 'guide-strawberry-mite', 'TRANSPLANT'),
    ('stage-mite-vegetative', 'guide-strawberry-mite', 'VEGETATIVE'),
    ('stage-mite-flowering', 'guide-strawberry-mite', 'FLOWERING'),
    ('stage-mite-fruiting', 'guide-strawberry-mite', 'FRUITING'),
    ('stage-mite-harvest', 'guide-strawberry-mite', 'HARVEST'),
    ('stage-powdery-vegetative', 'guide-strawberry-powdery', 'VEGETATIVE'),
    ('stage-powdery-flowering', 'guide-strawberry-powdery', 'FLOWERING'),
    ('stage-powdery-fruiting', 'guide-strawberry-powdery', 'FRUITING'),
    ('stage-powdery-harvest', 'guide-strawberry-powdery', 'HARVEST'),
    ('stage-gray-flowering', 'guide-strawberry-gray-mold', 'FLOWERING'),
    ('stage-gray-fruiting', 'guide-strawberry-gray-mold', 'FRUITING'),
    ('stage-gray-harvest', 'guide-strawberry-gray-mold', 'HARVEST'),
    ('stage-anthracnose-seedling', 'guide-strawberry-anthracnose', 'SEEDLING'),
    ('stage-anthracnose-transplant', 'guide-strawberry-anthracnose', 'TRANSPLANT'),
    ('stage-anthracnose-vegetative', 'guide-strawberry-anthracnose', 'VEGETATIVE'),
    ('stage-wilt-seedling', 'guide-strawberry-fusarium-wilt', 'SEEDLING'),
    ('stage-wilt-transplant', 'guide-strawberry-fusarium-wilt', 'TRANSPLANT'),
    ('stage-wilt-vegetative', 'guide-strawberry-fusarium-wilt', 'VEGETATIVE'),
    ('stage-phytophthora-seedling', 'guide-strawberry-phytophthora', 'SEEDLING'),
    ('stage-phytophthora-transplant', 'guide-strawberry-phytophthora', 'TRANSPLANT'),
    ('stage-phytophthora-vegetative', 'guide-strawberry-phytophthora', 'VEGETATIVE'),
    ('stage-thrips-flowering', 'guide-strawberry-thrips', 'FLOWERING'),
    ('stage-thrips-fruiting', 'guide-strawberry-thrips', 'FRUITING'),
    ('stage-thrips-harvest', 'guide-strawberry-thrips', 'HARVEST'),
    ('stage-fungus-gnat-seedling', 'guide-strawberry-fungus-gnat', 'SEEDLING'),
    ('stage-fungus-gnat-transplant', 'guide-strawberry-fungus-gnat', 'TRANSPLANT'),
    ('stage-fungus-gnat-vegetative', 'guide-strawberry-fungus-gnat', 'VEGETATIVE')`,
  `CREATE TABLE IF NOT EXISTS farms (
    id TEXT PRIMARY KEY NOT NULL, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Seoul', status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farms_status ON farms(status, name)`,
  `CREATE TABLE IF NOT EXISTS farm_cultivars (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, cultivar_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (cultivar_code) REFERENCES cultivars(code), UNIQUE(farm_id, cultivar_code)
  )`,
  `CREATE TABLE IF NOT EXISTS farm_items (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, crop_code TEXT NOT NULL, cultivar_code TEXT,
    display_name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (crop_code) REFERENCES crop_types(code),
    FOREIGN KEY (cultivar_code) REFERENCES cultivars(code), UNIQUE(farm_id, crop_code, cultivar_code)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_items_farm_status ON farm_items(farm_id, status)`,
  `CREATE TABLE IF NOT EXISTS app_users (
    id TEXT PRIMARY KEY NOT NULL, display_name TEXT NOT NULL, phone_e164 TEXT,
    phone_verified_at TEXT, preferred_language TEXT NOT NULL DEFAULT 'ko',
    status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_app_users_status ON app_users(status, updated_at)`,
  `CREATE UNIQUE INDEX IF NOT EXISTS uq_app_users_verified_phone ON app_users(phone_e164)
    WHERE phone_e164 IS NOT NULL`,
  `CREATE TABLE IF NOT EXISTS auth_identities (
    id TEXT PRIMARY KEY NOT NULL, user_id TEXT NOT NULL, provider TEXT NOT NULL,
    provider_subject TEXT NOT NULL, email TEXT, email_verified_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE,
    UNIQUE(provider, provider_subject)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_auth_identities_user ON auth_identities(user_id, provider)`,
  `CREATE TABLE IF NOT EXISTS password_credentials (
    user_id TEXT PRIMARY KEY NOT NULL, login_id TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL, password_algorithm TEXT NOT NULL DEFAULT 'ARGON2ID',
    failed_attempts INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
    password_changed_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_password_credentials_locked ON password_credentials(locked_until)`,
  `CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY NOT NULL, user_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_expiry ON auth_sessions(user_id, expires_at)`,
  `CREATE TABLE IF NOT EXISTS farm_members (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, user_id TEXT, login_id TEXT NOT NULL UNIQUE,
    identity_provider TEXT NOT NULL, identity_subject TEXT, email TEXT,
    display_name TEXT, phone TEXT, phone_verified_at TEXT, notifications_enabled INTEGER NOT NULL DEFAULT 0,
    preferred_language TEXT NOT NULL DEFAULT 'ko',
    invited_by_member_id TEXT, approved_at TEXT, joined_at TEXT, role TEXT NOT NULL DEFAULT 'WORKER',
    status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE SET NULL,
    UNIQUE(identity_provider, identity_subject)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_members_farm_status ON farm_members(farm_id, status)`,
  `CREATE TABLE IF NOT EXISTS farm_member_events (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, target_member_id TEXT, actor_member_id TEXT,
    target_name_snapshot TEXT NOT NULL, actor_name_snapshot TEXT NOT NULL,
    event_type TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (target_member_id) REFERENCES farm_members(id) ON DELETE SET NULL,
    FOREIGN KEY (actor_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_member_events_farm_created ON farm_member_events(farm_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_farm_member_events_target_created ON farm_member_events(target_member_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS farm_invitations (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'WORKER',
    token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, max_uses INTEGER NOT NULL DEFAULT 1,
    used_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_by_member_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_invitations_farm_status
    ON farm_invitations(farm_id, status, expires_at)`,
  `CREATE TABLE IF NOT EXISTS farm_join_requests (
    id TEXT PRIMARY KEY NOT NULL, invitation_id TEXT NOT NULL, farm_id TEXT NOT NULL,
    user_id TEXT NOT NULL, requested_role TEXT NOT NULL DEFAULT 'WORKER',
    preferred_language TEXT NOT NULL DEFAULT 'ko', status TEXT NOT NULL DEFAULT 'PENDING',
    reviewed_by_member_id TEXT, reviewed_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (invitation_id) REFERENCES farm_invitations(id) ON DELETE RESTRICT,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE RESTRICT,
    FOREIGN KEY (reviewed_by_member_id) REFERENCES farm_members(id) ON DELETE SET NULL,
    UNIQUE(invitation_id, user_id)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_join_requests_farm_status
    ON farm_join_requests(farm_id, status, created_at)`,
  `CREATE TABLE IF NOT EXISTS farm_notes (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, item_id TEXT, author_member_id TEXT,
    author_name_snapshot TEXT NOT NULL, author_role_snapshot TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'ko', category TEXT NOT NULL, title TEXT NOT NULL,
    content TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES farm_items(id) ON DELETE SET NULL,
    FOREIGN KEY (author_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_notes_farm_status_updated ON farm_notes(farm_id, status, updated_at)`,
  `CREATE INDEX IF NOT EXISTS idx_farm_notes_item_updated ON farm_notes(item_id, updated_at)`,
  `CREATE TABLE IF NOT EXISTS farm_chat_messages (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, author_member_id TEXT,
    author_name_snapshot TEXT NOT NULL, author_role_snapshot TEXT NOT NULL,
    author_account_snapshot TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'ko',
    content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (author_member_id) REFERENCES farm_members(id) ON DELETE SET NULL,
    CHECK(language IN ('ko', 'vi', 'th', 'zh-CN')),
    CHECK(status IN ('ACTIVE', 'DELETED')),
    CHECK(length(content) BETWEEN 1 AND 500)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_chat_messages_farm_status_created
    ON farm_chat_messages(farm_id, status, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_farm_chat_messages_author_created
    ON farm_chat_messages(author_member_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS community_chat_messages (
    id TEXT PRIMARY KEY NOT NULL, author_member_id TEXT,
    author_name_snapshot TEXT NOT NULL, author_role_snapshot TEXT NOT NULL,
    author_account_snapshot TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'ko',
    content TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (author_member_id) REFERENCES farm_members(id) ON DELETE SET NULL,
    CHECK(language IN ('ko', 'vi', 'th', 'zh-CN')),
    CHECK(status IN ('ACTIVE', 'DELETED')),
    CHECK(length(content) BETWEEN 1 AND 300)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_community_chat_messages_status_created
    ON community_chat_messages(status, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_community_chat_messages_author_created
    ON community_chat_messages(author_member_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS houses (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE, UNIQUE(farm_id, code)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_houses_farm_order ON houses(farm_id, display_order)`,
  `CREATE TABLE IF NOT EXISTS beds (
    id TEXT PRIMARY KEY NOT NULL, house_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE, UNIQUE(house_id, code)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_beds_house_order ON beds(house_id, display_order)`,
  `CREATE TABLE IF NOT EXISTS zones (
    id TEXT PRIMARY KEY NOT NULL, bed_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (bed_id) REFERENCES beds(id) ON DELETE CASCADE, UNIQUE(bed_id, code)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_zones_bed_order ON zones(bed_id, display_order)`,
  `CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, house_id TEXT, bed_id TEXT, zone_id TEXT,
    code TEXT NOT NULL, name TEXT NOT NULL, camera_type TEXT NOT NULL, source_type TEXT NOT NULL,
    external_ref TEXT, stream_url TEXT, connection_status TEXT NOT NULL DEFAULT 'DISCONNECTED', last_seen_at TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE SET NULL,
    FOREIGN KEY (bed_id) REFERENCES beds(id) ON DELETE SET NULL,
    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL, UNIQUE(farm_id, code)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_cameras_zone ON cameras(zone_id, status)`,
  `CREATE TABLE IF NOT EXISTS capture_sessions (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, camera_id TEXT, item_id TEXT, house_id TEXT, bed_id TEXT, zone_id TEXT,
    capture_mode TEXT NOT NULL, source_type TEXT NOT NULL, processing_status TEXT NOT NULL,
    started_at TEXT NOT NULL, ended_at TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL,
    FOREIGN KEY (item_id) REFERENCES farm_items(id) ON DELETE SET NULL,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE SET NULL,
    FOREIGN KEY (bed_id) REFERENCES beds(id) ON DELETE SET NULL,
    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_capture_sessions_farm_started ON capture_sessions(farm_id, started_at)`,
  `CREATE INDEX IF NOT EXISTS idx_capture_sessions_farm_item_started ON capture_sessions(farm_id, item_id, started_at)`,
  `CREATE INDEX IF NOT EXISTS idx_capture_sessions_processing ON capture_sessions(processing_status, created_at)`,
  `CREATE TABLE IF NOT EXISTS harvest_runs (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, item_id TEXT NOT NULL, camera_id TEXT,
    status TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
    started_by_member_id TEXT, started_by_name_snapshot TEXT,
    completed_by_member_id TEXT, completed_by_name_snapshot TEXT, note TEXT NOT NULL DEFAULT '',
    harvested_count INTEGER NOT NULL DEFAULT 0, total_weight_g REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES farm_items(id) ON DELETE RESTRICT,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL,
    FOREIGN KEY (started_by_member_id) REFERENCES farm_members(id) ON DELETE SET NULL,
    FOREIGN KEY (completed_by_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_harvest_runs_farm_completed ON harvest_runs(farm_id, completed_at)`,
  `CREATE INDEX IF NOT EXISTS idx_harvest_runs_item_status_completed ON harvest_runs(item_id, status, completed_at)`,
  `CREATE TABLE IF NOT EXISTS harvest_grade_summaries (
    id TEXT PRIMARY KEY NOT NULL, harvest_run_id TEXT NOT NULL, grade_code TEXT NOT NULL,
    fruit_count INTEGER NOT NULL, total_weight_g REAL NOT NULL, average_confidence REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (harvest_run_id) REFERENCES harvest_runs(id) ON DELETE CASCADE,
    UNIQUE(harvest_run_id, grade_code)
  )`,
  `CREATE TABLE IF NOT EXISTS price_forecasts (
    id TEXT PRIMARY KEY NOT NULL, crop_code TEXT NOT NULL, cultivar_code TEXT, grade_code TEXT NOT NULL,
    target_date TEXT NOT NULL, horizon_days INTEGER NOT NULL, model_name TEXT NOT NULL, model_version TEXT NOT NULL,
    price_p10_per_kg REAL NOT NULL, price_p50_per_kg REAL NOT NULL, price_p90_per_kg REAL NOT NULL,
    feature_snapshot_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL, generated_at TEXT NOT NULL,
    FOREIGN KEY (crop_code) REFERENCES crop_types(code) ON DELETE CASCADE,
    FOREIGN KEY (cultivar_code) REFERENCES cultivars(code) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_price_forecasts_series_target ON price_forecasts(crop_code, cultivar_code, grade_code, target_date)`,
  `CREATE TABLE IF NOT EXISTS revenue_forecasts (
    id TEXT PRIMARY KEY NOT NULL, harvest_run_id TEXT NOT NULL UNIQUE, grade_breakdown_json TEXT NOT NULL,
    estimated_gross_won REAL NOT NULL, estimated_cost_won REAL NOT NULL DEFAULT 0,
    estimated_net_won REAL NOT NULL, revenue_p10_won REAL, revenue_p90_won REAL,
    price_basis_date TEXT NOT NULL, price_model_name TEXT NOT NULL, price_model_version TEXT NOT NULL,
    status TEXT NOT NULL, generated_at TEXT NOT NULL,
    FOREIGN KEY (harvest_run_id) REFERENCES harvest_runs(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_revenue_forecasts_status_generated ON revenue_forecasts(status, generated_at)`,
  `CREATE TABLE IF NOT EXISTS forecast_jobs (
    id TEXT PRIMARY KEY NOT NULL, harvest_run_id TEXT NOT NULL, job_type TEXT NOT NULL,
    status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (harvest_run_id) REFERENCES harvest_runs(id) ON DELETE CASCADE,
    UNIQUE(harvest_run_id, job_type)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_forecast_jobs_status_created ON forecast_jobs(status, created_at)`,
  `CREATE TABLE IF NOT EXISTS forecast_model_registry (
    id TEXT PRIMARY KEY NOT NULL, model_name TEXT NOT NULL, model_version TEXT NOT NULL,
    algorithm TEXT NOT NULL, status TEXT NOT NULL, training_started_at TEXT, training_ended_at TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}', artifact_uri TEXT, deployed_at TEXT, created_at TEXT NOT NULL,
    UNIQUE(model_name, model_version)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_forecast_model_status ON forecast_model_registry(status, deployed_at)`,
  `CREATE TABLE IF NOT EXISTS farm_revenue_settings (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, item_id TEXT NOT NULL,
    commission_rate REAL NOT NULL DEFAULT 0, packaging_won_per_kg REAL NOT NULL DEFAULT 0,
    labor_won_per_kg REAL NOT NULL DEFAULT 0, shipping_won_per_kg REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE', updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES farm_items(id) ON DELETE CASCADE,
    UNIQUE(farm_id, item_id)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_farm_revenue_settings_status ON farm_revenue_settings(farm_id, status)`,
  `CREATE TABLE IF NOT EXISTS capture_assets (
    id TEXT PRIMARY KEY NOT NULL, capture_session_id TEXT NOT NULL, modality TEXT NOT NULL,
    object_key TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL, content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_capture_assets_session ON capture_assets(capture_session_id, modality)`,
  `CREATE TABLE IF NOT EXISTS video_assets (
    id TEXT PRIMARY KEY NOT NULL, capture_session_id TEXT NOT NULL, camera_id TEXT, modality TEXT NOT NULL,
    object_key TEXT UNIQUE, original_name TEXT, source_uri TEXT, duration_ms INTEGER, frame_rate REAL,
    frame_count INTEGER, processing_status TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_video_assets_session ON video_assets(capture_session_id, modality)`,
  `CREATE TABLE IF NOT EXISTS frames (
    id TEXT PRIMARY KEY NOT NULL, video_asset_id TEXT NOT NULL, capture_session_id TEXT NOT NULL,
    frame_index INTEGER NOT NULL, timestamp_ms INTEGER NOT NULL, object_key TEXT UNIQUE,
    quality_score REAL, processing_status TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY (video_asset_id) REFERENCES video_assets(id) ON DELETE CASCADE,
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE,
    UNIQUE(video_asset_id, frame_index)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_frames_session_time ON frames(capture_session_id, timestamp_ms)`,
  `CREATE TABLE IF NOT EXISTS frame_location_assignments (
    frame_id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL,
    house_id TEXT, bed_id TEXT, zone_id TEXT,
    source TEXT NOT NULL DEFAULT 'MANUAL_CORRECTION'
      CHECK(source IN ('ROBOT_TELEMETRY', 'MANUAL_CORRECTION', 'MODEL_ESTIMATE')),
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE SET NULL,
    FOREIGN KEY (bed_id) REFERENCES beds(id) ON DELETE SET NULL,
    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_frame_location_assignments_farm
    ON frame_location_assignments(farm_id, frame_id)`,
  `CREATE TABLE IF NOT EXISTS inference_runs (
    id TEXT PRIMARY KEY NOT NULL, capture_session_id TEXT NOT NULL, task TEXT NOT NULL,
    model_version TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
    finished_at TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_inference_runs_session_task ON inference_runs(capture_session_id, task)`,
  `CREATE TABLE IF NOT EXISTS frame_predictions (
    id TEXT PRIMARY KEY NOT NULL, inference_run_id TEXT NOT NULL, frame_id TEXT NOT NULL, track_id TEXT,
    class_label TEXT NOT NULL, confidence REAL, decision_status TEXT NOT NULL,
    result_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
    FOREIGN KEY (inference_run_id) REFERENCES inference_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_frame_predictions_run ON frame_predictions(inference_run_id, frame_id)`,
  `CREATE INDEX IF NOT EXISTS idx_frame_predictions_frame_created ON frame_predictions(frame_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_frame_predictions_track ON frame_predictions(track_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS prediction_review_events (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, frame_prediction_id TEXT NOT NULL,
    reviewer_member_id TEXT, reviewer_name_snapshot TEXT NOT NULL,
    reviewer_role_snapshot TEXT NOT NULL, verdict TEXT NOT NULL, quick_note_code TEXT,
    note TEXT NOT NULL DEFAULT '', note_language TEXT NOT NULL DEFAULT 'ko',
    created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (frame_prediction_id) REFERENCES frame_predictions(id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_prediction_reviews_prediction_created ON prediction_review_events(frame_prediction_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_prediction_reviews_farm_created ON prediction_review_events(farm_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS mite_record_notes (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, capture_session_id TEXT NOT NULL,
    track_key TEXT NOT NULL, target_frame_id TEXT, evidence_frame_prediction_id TEXT, parent_note_id TEXT,
    author_member_id TEXT, author_name_snapshot TEXT NOT NULL, author_role_snapshot TEXT NOT NULL,
    author_account_snapshot TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'ko', content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (target_frame_id) REFERENCES frames(id) ON DELETE SET NULL,
    FOREIGN KEY (evidence_frame_prediction_id) REFERENCES frame_predictions(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_note_id) REFERENCES mite_record_notes(id) ON DELETE SET NULL,
    FOREIGN KEY (author_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_mite_record_notes_case_status_created
    ON mite_record_notes(capture_session_id, track_key, status, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_mite_record_notes_farm_status_created
    ON mite_record_notes(farm_id, status, created_at)`,
  `CREATE TABLE IF NOT EXISTS mite_record_note_translations (
    id TEXT PRIMARY KEY NOT NULL, note_id TEXT NOT NULL,
    source_language TEXT NOT NULL, detected_source_language TEXT, target_language TEXT NOT NULL,
    source_updated_at TEXT NOT NULL, translated_content TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'GOOGLE_TRANSLATE_V2', model_version TEXT NOT NULL DEFAULT 'nmt',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (note_id) REFERENCES mite_record_notes(id) ON DELETE CASCADE,
    UNIQUE(note_id, target_language),
    CHECK(target_language IN ('ko', 'vi', 'th', 'zh-CN'))
  )`,
  `CREATE INDEX IF NOT EXISTS idx_mite_record_note_translations_note_source
    ON mite_record_note_translations(note_id, source_updated_at)`,
  `CREATE TABLE IF NOT EXISTS phone_verification_challenges (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, member_id TEXT,
    phone TEXT NOT NULL, code_hash TEXT NOT NULL, expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, consumed_at TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (member_id) REFERENCES farm_members(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_phone_challenges_member_created ON phone_verification_challenges(member_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_phone_challenges_expires ON phone_verification_challenges(expires_at)`,
  `CREATE TABLE IF NOT EXISTS notification_outbox (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, frame_prediction_id TEXT,
    recipient_member_id TEXT, recipient_phone TEXT NOT NULL, notification_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT, claimed_at TEXT, created_at TEXT NOT NULL, sent_at TEXT,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE,
    FOREIGN KEY (frame_prediction_id) REFERENCES frame_predictions(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_member_id) REFERENCES farm_members(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_notification_outbox_status_created ON notification_outbox(status, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_notification_outbox_farm_created ON notification_outbox(farm_id, created_at)`,
  `CREATE TABLE IF NOT EXISTS config_sources (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT, source_type TEXT NOT NULL, spreadsheet_id TEXT,
    sheet_gid TEXT, access_mode TEXT NOT NULL DEFAULT 'READ_ONLY', mapping_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL, last_imported_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_config_sources_farm ON config_sources(farm_id, status)`,
  `CREATE TABLE IF NOT EXISTS config_import_runs (
    id TEXT PRIMARY KEY NOT NULL, source_id TEXT NOT NULL, status TEXT NOT NULL,
    rows_read INTEGER NOT NULL DEFAULT 0, rows_created INTEGER NOT NULL DEFAULT 0,
    rows_updated INTEGER NOT NULL DEFAULT 0, rows_rejected INTEGER NOT NULL DEFAULT 0,
    checksum TEXT, error_summary TEXT, started_at TEXT NOT NULL, finished_at TEXT,
    FOREIGN KEY (source_id) REFERENCES config_sources(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_config_import_runs_source ON config_import_runs(source_id, started_at)`,
  `CREATE TABLE IF NOT EXISTS fruit_assessments (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT, capture_session_id TEXT, cultivar TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'PERSONAL_CAPTURE', capture_at TEXT, object_key TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL, grade_prediction TEXT, ripeness_prediction TEXT, confidence REAL,
    decision_status TEXT NOT NULL, processing_status TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE SET NULL,
    FOREIGN KEY (capture_session_id) REFERENCES capture_sessions(id) ON DELETE SET NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_fruit_assessments_created ON fruit_assessments(created_at)`,
  `CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY NOT NULL, farm_id TEXT NOT NULL, house_id TEXT NOT NULL, bed_id TEXT NOT NULL,
    zone_id TEXT NOT NULL, plant_id TEXT, leaf_id TEXT, cultivar TEXT NOT NULL, pest_species TEXT NOT NULL,
    capture_at TEXT NOT NULL, visual_symptom_status TEXT NOT NULL, active_pest_status TEXT NOT NULL,
    decision_status TEXT NOT NULL, environment_status TEXT NOT NULL, processing_status TEXT NOT NULL,
    capture_method TEXT NOT NULL DEFAULT 'PAIRED_STILL', pairing_id TEXT NOT NULL DEFAULT 'LEGACY',
    source_video_id TEXT, rgb_frame_index INTEGER, thermal_frame_index INTEGER, created_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS idx_observations_zone_capture ON observations(farm_id, house_id, bed_id, zone_id, capture_at)`,
  `CREATE INDEX IF NOT EXISTS idx_observations_processing ON observations(processing_status, created_at)`,
  `CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY NOT NULL, observation_id TEXT NOT NULL, modality TEXT NOT NULL,
    object_key TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL, content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY (observation_id) REFERENCES observations(id) ON DELETE CASCADE
  )`,
  `CREATE INDEX IF NOT EXISTS idx_assets_observation ON assets(observation_id)`,
];

export function ensureSchema() {
  if (!env.DB) throw new Error('Cloudflare D1 binding `DB` is unavailable.');
  const pending = schemaReady ??= (async () => {
    await env.DB.batch(definitions.map((sql) => env.DB.prepare(sql)));

    const tableInfo = await env.DB.prepare('PRAGMA table_info(observations)').all<{ name: string }>();
    const columns = new Set(tableInfo.results.map((column) => column.name));
    const additions: D1PreparedStatement[] = [];
    if (!columns.has('capture_method')) additions.push(env.DB.prepare("ALTER TABLE observations ADD COLUMN capture_method TEXT NOT NULL DEFAULT 'PAIRED_STILL'"));
    if (!columns.has('pairing_id')) additions.push(env.DB.prepare("ALTER TABLE observations ADD COLUMN pairing_id TEXT NOT NULL DEFAULT 'LEGACY'"));
    if (!columns.has('source_video_id')) additions.push(env.DB.prepare('ALTER TABLE observations ADD COLUMN source_video_id TEXT'));
    if (!columns.has('rgb_frame_index')) additions.push(env.DB.prepare('ALTER TABLE observations ADD COLUMN rgb_frame_index INTEGER'));
    if (!columns.has('thermal_frame_index')) additions.push(env.DB.prepare('ALTER TABLE observations ADD COLUMN thermal_frame_index INTEGER'));
    await applyColumnAdditions(additions);

    const cameraInfo = await env.DB.prepare('PRAGMA table_info(cameras)').all<{ name: string }>();
    const cameraColumns = new Set(cameraInfo.results.map((column) => column.name));
    const cameraAdditions: D1PreparedStatement[] = [];
    if (!cameraColumns.has('stream_url')) cameraAdditions.push(env.DB.prepare('ALTER TABLE cameras ADD COLUMN stream_url TEXT'));
    if (!cameraColumns.has('connection_status')) cameraAdditions.push(env.DB.prepare("ALTER TABLE cameras ADD COLUMN connection_status TEXT NOT NULL DEFAULT 'DISCONNECTED'"));
    if (!cameraColumns.has('last_seen_at')) cameraAdditions.push(env.DB.prepare('ALTER TABLE cameras ADD COLUMN last_seen_at TEXT'));
    await applyColumnAdditions(cameraAdditions);

    const sessionInfo = await env.DB.prepare('PRAGMA table_info(capture_sessions)').all<{ name: string }>();
    const sessionColumns = new Set(sessionInfo.results.map((column) => column.name));
    if (!sessionColumns.has('item_id')) {
      await applyColumnAdditions([env.DB.prepare('ALTER TABLE capture_sessions ADD COLUMN item_id TEXT')]);
    }

    const memberInfo = await env.DB.prepare('PRAGMA table_info(farm_members)').all<{ name: string }>();
    const memberColumns = new Set(memberInfo.results.map((column) => column.name));
    const memberAdditions: D1PreparedStatement[] = [];
    if (!memberColumns.has('user_id')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN user_id TEXT REFERENCES app_users(id) ON DELETE SET NULL'));
    if (!memberColumns.has('display_name')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN display_name TEXT'));
    if (!memberColumns.has('phone')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN phone TEXT'));
    if (!memberColumns.has('phone_verified_at')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN phone_verified_at TEXT'));
    if (!memberColumns.has('notifications_enabled')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN notifications_enabled INTEGER NOT NULL DEFAULT 0'));
    if (!memberColumns.has('preferred_language')) memberAdditions.push(env.DB.prepare("ALTER TABLE farm_members ADD COLUMN preferred_language TEXT NOT NULL DEFAULT 'ko'"));
    if (!memberColumns.has('invited_by_member_id')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN invited_by_member_id TEXT'));
    if (!memberColumns.has('approved_at')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN approved_at TEXT'));
    if (!memberColumns.has('joined_at')) memberAdditions.push(env.DB.prepare('ALTER TABLE farm_members ADD COLUMN joined_at TEXT'));
    await applyColumnAdditions(memberAdditions);
    await env.DB.prepare(`CREATE UNIQUE INDEX IF NOT EXISTS uq_farm_members_farm_user
      ON farm_members(farm_id, user_id) WHERE user_id IS NOT NULL`).run();
    await env.DB.prepare(`CREATE UNIQUE INDEX IF NOT EXISTS idx_farm_members_verified_phone
      ON farm_members(farm_id, phone)
      WHERE phone IS NOT NULL AND phone_verified_at IS NOT NULL AND status = 'ACTIVE'`).run();
    await env.DB.batch([
      env.DB.prepare('DROP TRIGGER IF EXISTS trg_mite_alert_notification_outbox'),
      env.DB.prepare('DROP TRIGGER IF EXISTS trg_mite_alert_notification_outbox_v2'),
      env.DB.prepare(notificationTrigger),
      env.DB.prepare(protectLastOwnerRoleTrigger),
      env.DB.prepare(protectLastOwnerDeleteTrigger),
      env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS trg_farm_members_app_user_insert
        BEFORE INSERT ON farm_members
        WHEN NEW.user_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app_users WHERE id = NEW.user_id)
        BEGIN SELECT RAISE(ABORT, 'APP_USER_REQUIRED'); END`),
      env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS trg_farm_members_app_user_update
        BEFORE UPDATE OF user_id ON farm_members
        WHEN NEW.user_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM app_users WHERE id = NEW.user_id)
        BEGIN SELECT RAISE(ABORT, 'APP_USER_REQUIRED'); END`),
      env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS trg_app_users_memberships_null_on_delete
        AFTER DELETE ON app_users
        BEGIN UPDATE farm_members SET user_id = NULL WHERE user_id = OLD.id; END`),
    ]);

    const harvestInfo = await env.DB.prepare('PRAGMA table_info(harvest_runs)').all<{ name: string }>();
    const harvestColumns = new Set(harvestInfo.results.map((column) => column.name));
    const harvestAdditions: D1PreparedStatement[] = [];
    if (!harvestColumns.has('started_by_member_id')) harvestAdditions.push(env.DB.prepare('ALTER TABLE harvest_runs ADD COLUMN started_by_member_id TEXT'));
    if (!harvestColumns.has('started_by_name_snapshot')) harvestAdditions.push(env.DB.prepare('ALTER TABLE harvest_runs ADD COLUMN started_by_name_snapshot TEXT'));
    if (!harvestColumns.has('completed_by_member_id')) harvestAdditions.push(env.DB.prepare('ALTER TABLE harvest_runs ADD COLUMN completed_by_member_id TEXT'));
    if (!harvestColumns.has('completed_by_name_snapshot')) harvestAdditions.push(env.DB.prepare('ALTER TABLE harvest_runs ADD COLUMN completed_by_name_snapshot TEXT'));
    if (!harvestColumns.has('note')) harvestAdditions.push(env.DB.prepare("ALTER TABLE harvest_runs ADD COLUMN note TEXT NOT NULL DEFAULT ''"));
    await applyColumnAdditions(harvestAdditions);

    const reviewInfo = await env.DB.prepare('PRAGMA table_info(prediction_review_events)').all<{ name: string }>();
    const reviewColumns = new Set(reviewInfo.results.map((column) => column.name));
    const reviewAdditions: D1PreparedStatement[] = [];
    if (!reviewColumns.has('quick_note_code')) reviewAdditions.push(env.DB.prepare('ALTER TABLE prediction_review_events ADD COLUMN quick_note_code TEXT'));
    if (!reviewColumns.has('note_language')) reviewAdditions.push(env.DB.prepare("ALTER TABLE prediction_review_events ADD COLUMN note_language TEXT NOT NULL DEFAULT 'ko'"));
    await applyColumnAdditions(reviewAdditions);

    const recordNoteInfo = await env.DB.prepare('PRAGMA table_info(mite_record_notes)').all<{ name: string }>();
    const recordNoteColumns = new Set(recordNoteInfo.results.map((column) => column.name));
    const recordNoteAdditions: D1PreparedStatement[] = [];
    if (!recordNoteColumns.has('target_frame_id')) recordNoteAdditions.push(env.DB.prepare('ALTER TABLE mite_record_notes ADD COLUMN target_frame_id TEXT REFERENCES frames(id) ON DELETE SET NULL'));
    if (!recordNoteColumns.has('parent_note_id')) recordNoteAdditions.push(env.DB.prepare('ALTER TABLE mite_record_notes ADD COLUMN parent_note_id TEXT REFERENCES mite_record_notes(id) ON DELETE SET NULL'));
    if (!recordNoteColumns.has('author_account_snapshot')) recordNoteAdditions.push(env.DB.prepare("ALTER TABLE mite_record_notes ADD COLUMN author_account_snapshot TEXT NOT NULL DEFAULT ''"));
    await applyColumnAdditions(recordNoteAdditions);
    await env.DB.batch([
      env.DB.prepare(`UPDATE mite_record_notes SET target_frame_id = (
          SELECT fp.frame_id FROM frame_predictions fp WHERE fp.id = mite_record_notes.evidence_frame_prediction_id
        ) WHERE target_frame_id IS NULL AND evidence_frame_prediction_id IS NOT NULL`),
      env.DB.prepare(`UPDATE mite_record_notes SET author_account_snapshot =
          substr(author_role_snapshot, 1, 1) || '-' ||
          CASE WHEN author_member_id IS NULL THEN 'OLD' ELSE upper(substr(replace(author_member_id, '-', ''), -4)) END
        WHERE author_account_snapshot = ''`),
      env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_mite_record_notes_frame_status_created
        ON mite_record_notes(capture_session_id, target_frame_id, status, created_at)`),
      env.DB.prepare(`CREATE INDEX IF NOT EXISTS idx_mite_record_notes_parent_status_created
        ON mite_record_notes(parent_note_id, status, created_at)`),
      env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS trg_mite_record_note_parent_scope
        BEFORE INSERT ON mite_record_notes
        WHEN NEW.parent_note_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM mite_record_notes parent
          WHERE parent.id = NEW.parent_note_id AND parent.farm_id = NEW.farm_id
            AND parent.capture_session_id = NEW.capture_session_id AND parent.status = 'ACTIVE'
            AND (
              parent.target_frame_id = NEW.target_frame_id
              OR (parent.target_frame_id IS NULL AND NEW.target_frame_id IS NULL AND parent.track_key = NEW.track_key)
            )
        )
        BEGIN SELECT RAISE(ABORT, 'NOTE_PARENT_SCOPE_MISMATCH'); END`),
      env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS trg_mite_record_note_frame_session
        BEFORE INSERT ON mite_record_notes
        WHEN NEW.target_frame_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM frames frame
          WHERE frame.id = NEW.target_frame_id AND frame.capture_session_id = NEW.capture_session_id
        )
        BEGIN SELECT RAISE(ABORT, 'NOTE_FRAME_SESSION_MISMATCH'); END`),
      env.DB.prepare('DROP TRIGGER IF EXISTS trg_frame_location_assignment_scope_insert'),
      env.DB.prepare('DROP TRIGGER IF EXISTS trg_frame_location_assignment_scope_update'),
      env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS trg_frame_location_assignment_scope_insert
        BEFORE INSERT ON frame_location_assignments
        WHEN NOT EXISTS (
          SELECT 1 FROM frames frame JOIN capture_sessions session ON session.id = frame.capture_session_id
          WHERE frame.id = NEW.frame_id AND session.farm_id = NEW.farm_id
        ) OR (NEW.bed_id IS NOT NULL AND NEW.house_id IS NULL
        ) OR (NEW.zone_id IS NOT NULL AND (NEW.house_id IS NULL OR NEW.bed_id IS NULL)
        ) OR (NEW.house_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM houses house WHERE house.id = NEW.house_id AND house.farm_id = NEW.farm_id
        )) OR (NEW.bed_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM beds bed JOIN houses house ON house.id = bed.house_id
          WHERE bed.id = NEW.bed_id AND house.farm_id = NEW.farm_id
            AND (NEW.house_id IS NULL OR bed.house_id = NEW.house_id)
        )) OR (NEW.zone_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM zones zone JOIN beds bed ON bed.id = zone.bed_id
          JOIN houses house ON house.id = bed.house_id
          WHERE zone.id = NEW.zone_id AND house.farm_id = NEW.farm_id
            AND (NEW.house_id IS NULL OR house.id = NEW.house_id)
            AND (NEW.bed_id IS NULL OR bed.id = NEW.bed_id)
        ))
        BEGIN SELECT RAISE(ABORT, 'FRAME_LOCATION_SCOPE_MISMATCH'); END`),
      env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS trg_frame_location_assignment_scope_update
        BEFORE UPDATE OF frame_id, farm_id, house_id, bed_id, zone_id ON frame_location_assignments
        WHEN NOT EXISTS (
          SELECT 1 FROM frames frame JOIN capture_sessions session ON session.id = frame.capture_session_id
          WHERE frame.id = NEW.frame_id AND session.farm_id = NEW.farm_id
        ) OR (NEW.bed_id IS NOT NULL AND NEW.house_id IS NULL
        ) OR (NEW.zone_id IS NOT NULL AND (NEW.house_id IS NULL OR NEW.bed_id IS NULL)
        ) OR (NEW.house_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM houses house WHERE house.id = NEW.house_id AND house.farm_id = NEW.farm_id
        )) OR (NEW.bed_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM beds bed JOIN houses house ON house.id = bed.house_id
          WHERE bed.id = NEW.bed_id AND house.farm_id = NEW.farm_id
            AND (NEW.house_id IS NULL OR bed.house_id = NEW.house_id)
        )) OR (NEW.zone_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM zones zone JOIN beds bed ON bed.id = zone.bed_id
          JOIN houses house ON house.id = bed.house_id
          WHERE zone.id = NEW.zone_id AND house.farm_id = NEW.farm_id
            AND (NEW.house_id IS NULL OR house.id = NEW.house_id)
            AND (NEW.bed_id IS NULL OR bed.id = NEW.bed_id)
        ))
        BEGIN SELECT RAISE(ABORT, 'FRAME_LOCATION_SCOPE_MISMATCH'); END`),
    ]);

    const outboxInfo = await env.DB.prepare('PRAGMA table_info(notification_outbox)').all<{ name: string }>();
    const outboxColumns = new Set(outboxInfo.results.map((column) => column.name));
    if (!outboxColumns.has('claimed_at')) {
      await applyColumnAdditions([env.DB.prepare('ALTER TABLE notification_outbox ADD COLUMN claimed_at TEXT')]);
    }

    const fruitInfo = await env.DB.prepare('PRAGMA table_info(fruit_assessments)').all<{ name: string }>();
    const fruitColumns = new Set(fruitInfo.results.map((column) => column.name));
    const fruitAdditions: D1PreparedStatement[] = [];
    if (!fruitColumns.has('farm_id')) fruitAdditions.push(env.DB.prepare('ALTER TABLE fruit_assessments ADD COLUMN farm_id TEXT'));
    if (!fruitColumns.has('capture_session_id')) fruitAdditions.push(env.DB.prepare('ALTER TABLE fruit_assessments ADD COLUMN capture_session_id TEXT'));
    if (!fruitColumns.has('source_type')) fruitAdditions.push(env.DB.prepare("ALTER TABLE fruit_assessments ADD COLUMN source_type TEXT NOT NULL DEFAULT 'PERSONAL_CAPTURE'"));
    if (!fruitColumns.has('capture_at')) fruitAdditions.push(env.DB.prepare('ALTER TABLE fruit_assessments ADD COLUMN capture_at TEXT'));
    await applyColumnAdditions(fruitAdditions);
    await env.DB.prepare('CREATE INDEX IF NOT EXISTS idx_fruit_assessments_farm_capture ON fruit_assessments(farm_id, capture_at)').run();
    await env.DB.prepare('PRAGMA optimize').run();
  })();
  return pending.catch((error) => {
    if (schemaReady === pending) schemaReady = undefined;
    throw error;
  });
}
