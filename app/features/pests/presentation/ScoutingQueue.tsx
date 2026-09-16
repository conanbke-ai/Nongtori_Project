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

type EvidenceOption = { code: string; ko: string; vi: string; th: string; 'zh-CN': string };
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
  { code: 'TREATMENT_APPLIED', ko: '방제했어요', vi: 'Đã xử lý phòng trừ', th: 'ดำเนินการป้องกันกำจัดแล้ว', 'zh-CN': '已进行防治' },
  { code: 'LEAF_REMOVED', ko: '피해잎을 제거했어요', vi: 'Đã loại bỏ lá bị hại', th: 'นำใบที่เสียหายออกแล้ว', 'zh-CN': '已移除受害叶片' },
  { code: 'BIOCONTROL_APPLIED', ko: '천적 처리를 했어요', vi: 'Đã dùng thiên địch', th: 'ใช้ศัตรูธรรมชาติแล้ว', 'zh-CN': '已使用天敌' },
  { code: 'OBSERVE_ONLY', ko: '조금 더 지켜볼게요', vi: 'Tiếp tục theo dõi', th: 'เฝ้าดูต่อ', 'zh-CN': '继续观察' },
  { code: 'OTHER_ACTION', ko: '기타 조치', vi: 'Xử lý khác', th: 'การดำเนินการอื่น', 'zh-CN': '其他处理' },
];

const stateLabels: Record<string, EvidenceOption> = {
  FIELD_CHECK_REQUIRED: { code: '', ko: '현장 확인 필요', vi: 'Cần kiểm tra hiện trường', th: 'ต้องตรวจหน้างาน', 'zh-CN': '需要现场检查' },
  SUSPECTED: { code: '', ko: '이상 흔적 확인', vi: 'Đã thấy dấu hiệu bất thường', th: 'พบร่องรอยผิดปกติ', 'zh-CN': '已发现异常迹象' },
  CONFIRMED: { code: '', ko: '응애 확인', vi: 'Đã xác nhận nhện', th: 'ยืนยันพบไร', 'zh-CN': '已确认螨害' },
  POST_TREATMENT: { code: '', ko: '방제 후 관찰', vi: 'Theo dõi sau xử lý', th: 'ติดตามหลังการกำจัด', 'zh-CN': '防治后观察' },
  MONITORING: { code: '', ko: '추적 관찰', vi: 'Đang theo dõi', th: 'กำลังติดตาม', 'zh-CN': '持续观察' },
  WATCH: { code: '', ko: '관찰 중', vi: 'Đang quan sát', th: 'อยู่ระหว่างเฝ้าดู', 'zh-CN': '观察中' },
};

const reasonLabels: Record<string, string> = {
  NEW_ANOMALY: '새로운 이상 패턴',
  NEW_FIELD_EVIDENCE: '새로운 현장 증거',
  WORSENING_TREND: '이전보다 악화된 변화',
  SPATIAL_SPREAD: '이상 범위 확대',
  STALE_PREVIOUS_CHECK: '이전 점검 후 시간이 지남',
  STALE_OR_CHANGED_PATTERN: '이전과 다른 패턴',
  POST_TREATMENT_REBOUND: '방제 후 이상 신호 재상승',
};

function localized(option: EvidenceOption, language: Language) {
  return option[language] ?? option.ko;
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

  const load = useCallback(async () => {
    if (!farmId) { setRows([]); return; }
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/scouting-locations?farmId=${encodeURIComponent(farmId)}&attention=1&limit=20`, { cache: 'no-store' });
      const result = await response.json() as QueueResponse;
      if (!response.ok) throw new Error(result.error ?? '예찰 구역을 불러오지 못했습니다.');
      setRows(result.rows);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '예찰 구역을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [farmId]);

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
      if (!response.ok) throw new Error(result.error ?? '기록을 저장하지 못했습니다.');
      setMessage(result.message ?? '기록했습니다.');
      await load();
      onChanged?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '기록을 저장하지 못했습니다.');
    } finally {
      setSending('');
    }
  }

  return (
    <section className="scouting-queue" aria-busy={loading}>
      <header className="scouting-queue-heading">
        <div><span>구역 상태 기반 예찰</span><h2>오늘 확인할 곳</h2><p>같은 상태가 반복되면 다시 알리지 않고, 이전 점검 이후 의미 있는 변화가 생긴 구역을 우선 보여줍니다.</p></div>
        <button disabled={loading || !farmId} onClick={() => void load()} type="button">새로고침</button>
      </header>
      {message && <div className="review-feedback success" role="status">{message}</div>}
      {error && <div className="review-feedback error" role="alert">{error}</div>}
      {loading ? <div className="screen-empty compact"><strong>예찰 구역을 불러오는 중입니다.</strong></div>
        : rows.length === 0 ? <div className="scouting-all-clear"><strong>지금 바로 확인할 구역이 없습니다.</strong><p>관측 기록은 계속 쌓이고, 새롭거나 악화된 변화가 생기면 여기에 표시됩니다.</p></div>
          : <div className="scouting-location-list">{rows.map((row) => {
            const state = stateLabels[row.current_state] ?? stateLabels.WATCH;
            const reason = row.last_alert_reason ? (reasonLabels[row.last_alert_reason] ?? row.last_alert_reason) : '최근 상태 변화 확인';
            return <article className={`scouting-location-card state-${row.current_state.toLowerCase()}`} key={row.id}>
              <div className="scouting-location-main">
                <span className="scouting-state-badge">{localized(state, language)}</span>
                <div><h3>{row.house_code}동 · {row.bed_code}번 베드 · {row.zone_code}구역</h3><p>{reason}</p></div>
                <time>{formatTime(row.last_alert_at ?? row.last_observed_at, language)}</time>
              </div>
              <div className="scouting-location-meta">
                {row.last_field_check_at && <span>최근 현장 확인 <b>{formatTime(row.last_field_check_at, language)}</b></span>}
                {row.last_action_at && <span>최근 조치 <b>{formatTime(row.last_action_at, language)}</b></span>}
              </div>
              {canReview && <div className="scouting-actions-row">
                <details><summary>현장 점검 결과</summary><div className="scouting-choice-grid">{evidenceOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void submit('/api/scouting-field-checks', row, option.code)} type="button">{localized(option, language)}</button>)}</div></details>
                <details><summary>조치 기록</summary><div className="scouting-choice-grid compact">{actionOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void submit('/api/scouting-actions', row, option.code)} type="button">{localized(option, language)}</button>)}</div></details>
              </div>}
            </article>;
          })}</div>}
      <p className="scouting-evidence-note"><strong>참고</strong> “특별한 이상을 못 찾음”은 응애가 없다는 확정 판정이 아닙니다. 당시 현장에서 눈에 띄는 증거를 찾지 못했다는 관찰 사실로 저장됩니다.</p>
    </section>
  );
}
