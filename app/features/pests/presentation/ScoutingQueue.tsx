'use client';

import { useCallback, useEffect, useState } from 'react';
import { localeForLanguage, type Language } from '@/app/lib/i18n';

export type ScoutingLocation = {
  id: string;
  location_key: string;
  house_code: string;
  bed_code: string;
  zone_code: string;
  current_state: string;
  active_case_id: string | null;
  last_observed_at: string | null;
  last_field_check_at: string | null;
  last_action_at: string | null;
  last_alert_at: string | null;
  last_alert_reason: string | null;
  primary_issue_code: string | null;
  issue_family: string | null;
  case_status: string | null;
};

type QueueResponse = { rows: ScoutingLocation[]; counts: Record<string, number>; error?: string };
type LocalizedText = { ko: string; vi: string; th: string; 'zh-CN': string };
type EvidenceOption = LocalizedText & { code: string };
type ActionOption = EvidenceOption;

const evidenceOptions: EvidenceOption[] = [
  { code: 'NO_VISIBLE_EVIDENCE', ko: '특별한 이상을 못 찾음', vi: 'Không thấy bất thường rõ ràng', th: 'ไม่พบความผิดปกติชัดเจน', 'zh-CN': '未发现明显异常' },
  { code: 'LEAF_DAMAGE_OBSERVED', ko: '잎 피해 흔적이 보임', vi: 'Thấy dấu vết hư hại trên lá', th: 'พบร่องรอยความเสียหายที่ใบ', 'zh-CN': '发现叶片受害痕迹' },
  { code: 'WEBBING_OR_MITE_TRACE_SUSPECTED', ko: '거미줄·응애 흔적이 의심됨', vi: 'Nghi có tơ hoặc dấu vết nhện', th: 'สงสัยใยหรือร่องรอยไร', 'zh-CN': '疑似有蛛网或螨迹' },
  { code: 'DIRECT_MITE_OR_EGG_CONFIRMED', ko: '응애·알을 직접 확인함', vi: 'Đã nhìn thấy nhện hoặc trứng', th: 'พบไรหรือไข่โดยตรง', 'zh-CN': '直接发现螨或卵' },
  { code: 'OTHER_PEST_LIKE_EVIDENCE', ko: '다른 벌레 같음', vi: 'Có vẻ là sâu hại khác', th: 'ดูเหมือนแมลงศัตรูชนิดอื่น', 'zh-CN': '像其他害虫' },
  { code: 'DISEASE_LIKE_EVIDENCE', ko: '병해 같음', vi: 'Có vẻ là bệnh cây', th: 'ดูเหมือนโรคพืช', 'zh-CN': '像病害' },
  { code: 'PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY', ko: '환경·생리 이상 같음', vi: 'Có vẻ do môi trường hoặc sinh lý', th: 'ดูเหมือนความผิดปกติจากสภาพแวดล้อม/สรีรวิทยา', 'zh-CN': '像环境或生理异常' },
  { code: 'INCONCLUSIVE', ko: '판단하기 어려움', vi: 'Khó xác định', th: 'ยังตัดสินไม่ได้', 'zh-CN': '难以判断' },
];

const actionOptions: ActionOption[] = [
  { code: 'TREATMENT_APPLIED', ko: '방제', vi: 'Phòng trừ', th: 'ป้องกันกำจัด', 'zh-CN': '防治' },
  { code: 'LEAF_REMOVED', ko: '피해잎 제거', vi: 'Loại bỏ lá bị hại', th: 'นำใบที่เสียหายออก', 'zh-CN': '移除受害叶片' },
  { code: 'BIOCONTROL_APPLIED', ko: '천적 처리', vi: 'Dùng thiên địch', th: 'ใช้ศัตรูธรรมชาติ', 'zh-CN': '天敌处理' },
  { code: 'OBSERVE_ONLY', ko: '추적 관찰', vi: 'Theo dõi tiếp', th: 'ติดตามต่อ', 'zh-CN': '持续观察' },
  { code: 'OTHER_ACTION', ko: '기타 조치', vi: 'Xử lý khác', th: 'การดำเนินการอื่น', 'zh-CN': '其他处理' },
];

const stateLabels: Record<string, LocalizedText> = {
  FIELD_CHECK_REQUIRED: { ko: '현장 확인 필요', vi: 'Cần kiểm tra hiện trường', th: 'ต้องตรวจหน้างาน', 'zh-CN': '需要现场检查' },
  SUSPECTED: { ko: '이상 흔적 확인', vi: 'Đã thấy dấu hiệu bất thường', th: 'พบร่องรอยผิดปกติ', 'zh-CN': '已发现异常迹象' },
  CONFIRMED: { ko: '응애 확인', vi: 'Đã xác nhận nhện', th: 'ยืนยันพบไร', 'zh-CN': '已确认螨害' },
  POST_TREATMENT: { ko: '방제 후 관찰', vi: 'Theo dõi sau xử lý', th: 'ติดตามหลังการกำจัด', 'zh-CN': '防治后观察' },
  MONITORING: { ko: '추적 관찰', vi: 'Đang theo dõi', th: 'กำลังติดตาม', 'zh-CN': '持续观察' },
  WATCH: { ko: '관찰 중', vi: 'Đang quan sát', th: 'อยู่ระหว่างเฝ้าดู', 'zh-CN': '观察中' },
};

const reasonLabels: Record<string, LocalizedText> = {
  NEW_ANOMALY: { ko: '새로운 이상 패턴', vi: 'Mẫu bất thường mới', th: 'รูปแบบความผิดปกติใหม่', 'zh-CN': '新的异常模式' },
  NEW_FIELD_EVIDENCE: { ko: '새로운 현장 증거', vi: 'Bằng chứng hiện trường mới', th: 'หลักฐานภาคสนามใหม่', 'zh-CN': '新的现场证据' },
  WORSENING_TREND: { ko: '이전보다 악화된 변화', vi: 'Xu hướng xấu đi', th: 'แนวโน้มแย่ลง', 'zh-CN': '较之前恶化' },
  SPATIAL_SPREAD: { ko: '이상 범위 확대', vi: 'Phạm vi bất thường lan rộng', th: 'ขอบเขตความผิดปกติขยายตัว', 'zh-CN': '异常范围扩大' },
  STALE_PREVIOUS_CHECK: { ko: '이전 점검 후 시간이 지남', vi: 'Đã lâu từ lần kiểm tra trước', th: 'ผ่านมานานจากการตรวจครั้งก่อน', 'zh-CN': '距上次检查已过一段时间' },
  STALE_OR_CHANGED_PATTERN: { ko: '이전과 다른 패턴', vi: 'Mẫu khác lần trước', th: 'รูปแบบต่างจากครั้งก่อน', 'zh-CN': '与之前不同的模式' },
  POST_TREATMENT_REBOUND: { ko: '방제 후 이상 신호 재상승', vi: 'Tín hiệu tăng lại sau xử lý', th: 'สัญญาณผิดปกติเพิ่มขึ้นอีกหลังการจัดการ', 'zh-CN': '防治后异常信号再次上升' },
};

const copy: Record<Language, {
  eyebrow: string; title: string; description: string; refresh: string; loading: string;
  emptyTitle: string; emptyHelp: string; fallbackReason: string; recentCheck: string; recentAction: string;
  fieldCheck: string; action: string; noteLabel: string; noteText: string; loadError: string; saveError: string; saved: string;
}> = {
  ko: {
    eyebrow: '구역 상태 기반 예찰', title: '오늘 확인할 곳',
    description: '같은 상태가 반복되면 다시 알리지 않고, 이전 점검 이후 의미 있는 변화가 생긴 구역을 우선 보여줍니다.',
    refresh: '새로고침', loading: '예찰 구역을 불러오는 중입니다.', emptyTitle: '지금 바로 확인할 구역이 없습니다.',
    emptyHelp: '관측 기록은 계속 쌓이고, 새롭거나 악화된 변화가 생기면 여기에 표시됩니다.',
    fallbackReason: '최근 상태 변화 확인', recentCheck: '최근 현장 확인', recentAction: '최근 조치',
    fieldCheck: '현장 점검 결과', action: '조치 기록', noteLabel: '참고',
    noteText: '“특별한 이상을 못 찾음”은 응애가 없다는 확정 판정이 아닙니다. 당시 현장에서 눈에 띄는 증거를 찾지 못했다는 관찰 사실로 저장됩니다.',
    loadError: '예찰 구역을 불러오지 못했습니다.', saveError: '기록을 저장하지 못했습니다.', saved: '기록했습니다.',
  },
  vi: {
    eyebrow: 'Theo dõi theo trạng thái khu vực', title: 'Khu vực cần kiểm tra hôm nay',
    description: 'Không lặp lại cảnh báo cho cùng một trạng thái; ưu tiên khu vực có thay đổi đáng kể sau lần kiểm tra trước.',
    refresh: 'Làm mới', loading: 'Đang tải khu vực theo dõi.', emptyTitle: 'Hiện không có khu vực cần kiểm tra ngay.',
    emptyHelp: 'Dữ liệu vẫn tiếp tục được ghi; khu vực sẽ xuất hiện khi có thay đổi mới hoặc xấu đi.',
    fallbackReason: 'Kiểm tra thay đổi trạng thái gần đây', recentCheck: 'Kiểm tra hiện trường gần nhất', recentAction: 'Xử lý gần nhất',
    fieldCheck: 'Kết quả kiểm tra hiện trường', action: 'Ghi nhận xử lý', noteLabel: 'Lưu ý',
    noteText: '“Không thấy bất thường rõ ràng” không có nghĩa là xác nhận không có nhện. Đây chỉ là ghi nhận rằng tại thời điểm kiểm tra không thấy bằng chứng rõ ràng.',
    loadError: 'Không tải được khu vực theo dõi.', saveError: 'Không lưu được bản ghi.', saved: 'Đã ghi nhận.',
  },
  th: {
    eyebrow: 'เฝ้าระวังตามสถานะพื้นที่', title: 'จุดที่ต้องตรวจวันนี้',
    description: 'ไม่แจ้งซ้ำเมื่อสถานะเดิมเกิดซ้ำ และจะแสดงพื้นที่ที่มีการเปลี่ยนแปลงสำคัญหลังการตรวจครั้งก่อนก่อน',
    refresh: 'รีเฟรช', loading: 'กำลังโหลดพื้นที่เฝ้าระวัง', emptyTitle: 'ขณะนี้ไม่มีพื้นที่ที่ต้องตรวจทันที',
    emptyHelp: 'ระบบยังคงบันทึกข้อมูล และจะแสดงที่นี่เมื่อมีการเปลี่ยนแปลงใหม่หรือแย่ลง',
    fallbackReason: 'ตรวจสอบการเปลี่ยนแปลงล่าสุด', recentCheck: 'ตรวจหน้างานครั้งล่าสุด', recentAction: 'การจัดการล่าสุด',
    fieldCheck: 'ผลการตรวจหน้างาน', action: 'บันทึกการจัดการ', noteLabel: 'หมายเหตุ',
    noteText: '“ไม่พบความผิดปกติชัดเจน” ไม่ได้แปลว่ายืนยันว่าไม่มีไร แต่หมายถึงขณะตรวจยังไม่พบหลักฐานที่เห็นได้ชัด',
    loadError: 'ไม่สามารถโหลดพื้นที่เฝ้าระวังได้', saveError: 'ไม่สามารถบันทึกได้', saved: 'บันทึกแล้ว',
  },
  'zh-CN': {
    eyebrow: '按区域状态巡检', title: '今天需要确认的区域',
    description: '相同状态重复时不重复提醒，优先显示上次检查后出现明显变化的区域。',
    refresh: '刷新', loading: '正在加载巡检区域。', emptyTitle: '目前没有需要立即确认的区域。',
    emptyHelp: '观测记录仍会持续保存；出现新的或恶化的变化时会显示在这里。',
    fallbackReason: '确认最近状态变化', recentCheck: '最近现场检查', recentAction: '最近处理',
    fieldCheck: '现场检查结果', action: '处理记录', noteLabel: '说明',
    noteText: '“未发现明显异常”并不等于确认没有螨虫，只表示当时现场未发现明显证据。',
    loadError: '无法加载巡检区域。', saveError: '无法保存记录。', saved: '已记录。',
  },
};

function localized(value: LocalizedText, language: Language) {
  return value[language] ?? value.ko;
}

function formatTime(value: string | null, language: Language) {
  if (!value) return '';
  return new Intl.DateTimeFormat(localeForLanguage(language), { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}

export function ScoutingQueue({ farmId, canReview, language, onChanged }: {
  farmId: string;
  canReview: boolean;
  language: Language;
  onChanged?: () => void;
}) {
  const [rows, setRows] = useState<ScoutingLocation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState('');
  const text = copy[language];

  const load = useCallback(async () => {
    if (!farmId) { setRows([]); return; }
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/scouting-locations?farmId=${encodeURIComponent(farmId)}&attention=1&limit=20`, { cache: 'no-store' });
      const result = await response.json() as QueueResponse;
      if (!response.ok) throw new Error(result.error ?? text.loadError);
      setRows(result.rows);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : text.loadError);
    } finally {
      setLoading(false);
    }
  }, [farmId, text.loadError]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(async () => {
      if (!cancelled) await load();
    });
    return () => { cancelled = true; };
  }, [load]);

  async function submit(path: '/api/scouting-field-checks' | '/api/scouting-actions', row: ScoutingLocation, code: string) {
    setSending(`${row.id}:${code}`);
    setMessage('');
    setError('');
    try {
      const body = path.endsWith('field-checks')
        ? { farmId, locationStateId: row.id, evidenceCode: code }
        : { farmId, locationStateId: row.id, actionCode: code };
      const response = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
      const result = await response.json() as { error?: string; message?: string };
      if (!response.ok) throw new Error(result.error ?? text.saveError);
      setMessage(result.message ?? text.saved);
      await load();
      onChanged?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : text.saveError);
    } finally {
      setSending('');
    }
  }

  return (
    <section className="scouting-queue" aria-busy={loading}>
      <header className="scouting-queue-heading">
        <div><span>{text.eyebrow}</span><h2>{text.title}</h2><p>{text.description}</p></div>
        <button disabled={loading || !farmId} onClick={() => void load()} type="button">{text.refresh}</button>
      </header>
      {message && <div className="review-feedback success" role="status">{message}</div>}
      {error && <div className="review-feedback error" role="alert">{error}</div>}
      {loading ? <div className="screen-empty compact"><strong>{text.loading}</strong></div>
        : rows.length === 0 ? <div className="scouting-all-clear"><strong>{text.emptyTitle}</strong><p>{text.emptyHelp}</p></div>
          : <div className="scouting-location-list">{rows.map((row) => {
            const state = stateLabels[row.current_state] ?? stateLabels.WATCH;
            const reason = row.last_alert_reason && reasonLabels[row.last_alert_reason]
              ? localized(reasonLabels[row.last_alert_reason], language)
              : text.fallbackReason;
            return <article className={`scouting-location-card state-${row.current_state.toLowerCase()}`} key={row.id}>
              <div className="scouting-location-main">
                <span className="scouting-state-badge">{localized(state, language)}</span>
                <div><h3>{row.house_code} · {row.bed_code} · {row.zone_code}</h3><p>{reason}</p></div>
                <time>{formatTime(row.last_alert_at ?? row.last_observed_at, language)}</time>
              </div>
              <div className="scouting-location-meta">
                {row.last_field_check_at && <span>{text.recentCheck} <b>{formatTime(row.last_field_check_at, language)}</b></span>}
                {row.last_action_at && <span>{text.recentAction} <b>{formatTime(row.last_action_at, language)}</b></span>}
              </div>
              {canReview && <div className="scouting-actions-row">
                <details><summary>{text.fieldCheck}</summary><div className="scouting-choice-grid">{evidenceOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void submit('/api/scouting-field-checks', row, option.code)} type="button">{localized(option, language)}</button>)}</div></details>
                <details><summary>{text.action}</summary><div className="scouting-choice-grid compact">{actionOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void submit('/api/scouting-actions', row, option.code)} type="button">{localized(option, language)}</button>)}</div></details>
              </div>}
            </article>;
          })}</div>}
      <p className="scouting-evidence-note"><strong>{text.noteLabel}</strong> {text.noteText}</p>
    </section>
  );
}
