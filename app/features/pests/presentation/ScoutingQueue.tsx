'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { localeForLanguage, type Language } from '@/app/lib/i18n';

export type ScoutingLocation = {
  id: string;
  location_key: string;
  display_location: string | null;
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
  latest_humidity: number | null;
  latest_leaf_temp: number | null;
  latest_ambient_temp: number | null;
  latest_reference_temp: number | null;
  latest_risk_signal: number | null;
  observation_count: number;
};

type QueueResponse = { rows: ScoutingLocation[]; counts: Record<string, number>; error?: string };
type LocalizedText = { ko: string; vi: string; th: string; 'zh-CN': string };
type Choice = LocalizedText & { code: string };

const evidenceOptions: Choice[] = [
  { code: 'NO_VISIBLE_EVIDENCE', ko: '특별한 이상 못 찾음', vi: 'Không thấy bất thường rõ ràng', th: 'ไม่พบความผิดปกติชัดเจน', 'zh-CN': '未发现明显异常' },
  { code: 'LEAF_DAMAGE_OBSERVED', ko: '잎 피해 흔적', vi: 'Có dấu vết hư hại trên lá', th: 'พบร่องรอยความเสียหายที่ใบ', 'zh-CN': '发现叶片受害痕迹' },
  { code: 'WEBBING_OR_MITE_TRACE_SUSPECTED', ko: '거미줄·응애 흔적 의심', vi: 'Nghi có tơ hoặc dấu vết nhện', th: 'สงสัยใยหรือร่องรอยไร', 'zh-CN': '疑似有蛛网或螨迹' },
  { code: 'DIRECT_MITE_OR_EGG_CONFIRMED', ko: '응애·알 직접 확인', vi: 'Đã thấy nhện hoặc trứng', th: 'พบไรหรือไข่โดยตรง', 'zh-CN': '直接发现螨或卵' },
  { code: 'OTHER_PEST_LIKE_EVIDENCE', ko: '다른 해충 발견', vi: 'Phát hiện sâu hại khác', th: 'พบศัตรูพืชชนิดอื่น', 'zh-CN': '发现其他害虫' },
  { code: 'DISEASE_LIKE_EVIDENCE', ko: '병해 의심', vi: 'Nghi bệnh cây', th: 'สงสัยโรคพืช', 'zh-CN': '疑似病害' },
  { code: 'PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY', ko: '환경·생리 이상', vi: 'Bất thường môi trường/sinh lý', th: 'ความผิดปกติจากสภาพแวดล้อม/สรีรวิทยา', 'zh-CN': '环境/生理异常' },
  { code: 'INCONCLUSIVE', ko: '판단 어려움', vi: 'Khó xác định', th: 'ยังตัดสินไม่ได้', 'zh-CN': '难以判断' },
];

const actionOptions: Choice[] = [
  { code: 'TREATMENT_APPLIED', ko: '방제', vi: 'Phòng trừ', th: 'ป้องกันกำจัด', 'zh-CN': '防治' },
  { code: 'LEAF_REMOVED', ko: '피해잎 제거', vi: 'Loại bỏ lá bị hại', th: 'นำใบที่เสียหายออก', 'zh-CN': '移除受害叶片' },
  { code: 'BIOCONTROL_APPLIED', ko: '천적 처리', vi: 'Dùng thiên địch', th: 'ใช้ศัตรูธรรมชาติ', 'zh-CN': '天敌处理' },
  { code: 'OBSERVE_ONLY', ko: '추적 관찰', vi: 'Theo dõi tiếp', th: 'ติดตามต่อ', 'zh-CN': '持续观察' },
  { code: 'OTHER_ACTION', ko: '기타 조치', vi: 'Xử lý khác', th: 'การดำเนินการอื่น', 'zh-CN': '其他处理' },
];

const resolveOptions: Choice[] = [
  { code: 'NO_FURTHER_ABNORMALITY', ko: '추가 이상 없음', vi: 'Không còn bất thường', th: 'ไม่พบความผิดปกติเพิ่ม', 'zh-CN': '未再发现异常' },
  { code: 'TREATMENT_COMPLETED', ko: '방제·조치 완료', vi: 'Đã hoàn tất xử lý', th: 'จัดการเสร็จแล้ว', 'zh-CN': '防治/处理完成' },
  { code: 'FALSE_ALARM_CLOSED', ko: '오경보로 종료', vi: 'Đóng do cảnh báo nhầm', th: 'ปิดเพราะแจ้งเตือนผิด', 'zh-CN': '按误报结束' },
  { code: 'OTHER', ko: '기타 종료', vi: 'Lý do khác', th: 'เหตุผลอื่น', 'zh-CN': '其他结束原因' },
];

const stateLabels: Record<string, LocalizedText> = {
  BASELINE: { ko: '평상', vi: 'Bình thường', th: 'ปกติ', 'zh-CN': '平稳' },
  WATCH: { ko: '관찰', vi: 'Theo dõi', th: 'เฝ้าดู', 'zh-CN': '观察' },
  FIELD_CHECK_REQUIRED: { ko: '확인 필요', vi: 'Cần kiểm tra', th: 'ต้องตรวจ', 'zh-CN': '需要确认' },
  SUSPECTED: { ko: '이상 확인', vi: 'Đã thấy dấu hiệu', th: 'พบความผิดปกติ', 'zh-CN': '已发现异常' },
  CONFIRMED: { ko: '현장 확인 완료', vi: 'Đã xác nhận tại hiện trường', th: 'ยืนยันหน้างานแล้ว', 'zh-CN': '现场已确认' },
  POST_TREATMENT: { ko: '조치 후 관찰', vi: 'Theo dõi sau xử lý', th: 'ติดตามหลังจัดการ', 'zh-CN': '处理后观察' },
  MONITORING: { ko: '추적 관찰', vi: 'Đang theo dõi', th: 'กำลังติดตาม', 'zh-CN': '跟踪观察' },
  RESOLVED: { ko: '종료', vi: 'Đã kết thúc', th: 'สิ้นสุด', 'zh-CN': '已结束' },
};

const reasonLabels: Record<string, LocalizedText> = {
  NEW_ANOMALY: { ko: '새로운 변화', vi: 'Thay đổi mới', th: 'การเปลี่ยนแปลงใหม่', 'zh-CN': '出现新变化' },
  NEW_FIELD_EVIDENCE: { ko: '새로운 현장 정보', vi: 'Thông tin hiện trường mới', th: 'ข้อมูลหน้างานใหม่', 'zh-CN': '新的现场信息' },
  WORSENING_TREND: { ko: '이상 신호 증가', vi: 'Tín hiệu bất thường tăng', th: 'สัญญาณผิดปกติเพิ่ม', 'zh-CN': '异常信号增加' },
  SPATIAL_SPREAD: { ko: '이상 범위 확대', vi: 'Vùng bất thường mở rộng', th: 'ขอบเขตผิดปกติขยาย', 'zh-CN': '异常范围扩大' },
  STALE_PREVIOUS_CHECK: { ko: '재확인 시점', vi: 'Đến lúc kiểm tra lại', th: 'ถึงเวลาตรวจซ้ำ', 'zh-CN': '需要复查' },
  STALE_OR_CHANGED_PATTERN: { ko: '이전과 다른 변화', vi: 'Thay đổi khác trước', th: 'เปลี่ยนแปลงจากเดิม', 'zh-CN': '与之前不同' },
  POST_TREATMENT_REBOUND: { ko: '조치 후 다시 감지', vi: 'Phát hiện lại sau xử lý', th: 'ตรวจพบอีกหลังจัดการ', 'zh-CN': '处理后再次检测' },
};

const issueLabels: Record<string, LocalizedText> = {
  SPIDER_MITE: { ko: '응애', vi: 'Nhện đỏ', th: 'ไรแดง', 'zh-CN': '叶螨' },
  APHID: { ko: '진딧물', vi: 'Rệp', th: 'เพลี้ยอ่อน', 'zh-CN': '蚜虫' },
  THRIPS: { ko: '총채벌레', vi: 'Bọ trĩ', th: 'เพลี้ยไฟ', 'zh-CN': '蓟马' },
  POWDERY_MILDEW: { ko: '흰가루병', vi: 'Bệnh phấn trắng', th: 'โรคราแป้ง', 'zh-CN': '白粉病' },
  GRAY_MOLD: { ko: '잿빛곰팡이병', vi: 'Bệnh mốc xám', th: 'โรคราสีเทา', 'zh-CN': '灰霉病' },
  UNKNOWN_PEST: { ko: '해충', vi: 'Sâu hại', th: 'ศัตรูพืช', 'zh-CN': '害虫' },
  UNKNOWN_DISEASE: { ko: '병해', vi: 'Bệnh cây', th: 'โรคพืช', 'zh-CN': '病害' },
  ENVIRONMENTAL_STRESS: { ko: '환경·생리 이상', vi: 'Bất thường môi trường/sinh lý', th: 'ความผิดปกติจากสภาพแวดล้อม/สรีรวิทยา', 'zh-CN': '环境/生理异常' },
  UNKNOWN: { ko: '원인 미확인', vi: 'Chưa rõ nguyên nhân', th: 'ยังไม่ทราบสาเหตุ', 'zh-CN': '原因未确认' },
};

const copy: Record<Language, {
  eyebrow: string; title: string; description: string; refresh: string; loading: string; emptyTitle: string; emptyHelp: string;
  candidate: string; recentDetection: string; recentCheck: string; recentAction: string; details: string; closeDetails: string;
  fieldCheck: string; action: string; resolve: string; correctionTitle: string; correctionHelp: string; voidInput: string;
  noteLabel: string; noteText: string; loadError: string; saveError: string; saved: string;
}> = {
  ko: { eyebrow: '병해충 예찰', title: '오늘 확인할 구역', description: '반복 알림은 묶고, 확인 가치가 높은 구역만 우선 보여줍니다.', refresh: '새로고침', loading: '예찰 구역을 불러오는 중입니다.', emptyTitle: '지금 바로 확인할 구역이 없습니다.', emptyHelp: '관측은 계속되고 새로운 변화가 생기면 목록에 표시됩니다.', candidate: '탐지 후보', recentDetection: '최근 감지', recentCheck: '최근 현장 확인', recentAction: '최근 조치', details: '상세보기', closeDetails: '상세 닫기', fieldCheck: '현장 확인 결과 기록', action: '조치 기록', resolve: '예찰 건 종료', correctionTitle: '방금 입력 수정', correctionHelp: '잘못 눌렀다면 원본을 지우지 않고 수정 이력으로 남깁니다.', voidInput: '입력 무효화', noteLabel: '기록 원칙', noteText: '“특별한 이상 못 찾음”은 확정 정상 판정이 아니라 당시 관찰 결과로 저장됩니다.', loadError: '예찰 구역을 불러오지 못했습니다.', saveError: '기록을 저장하지 못했습니다.', saved: '기록했습니다.' },
  vi: { eyebrow: 'Theo dõi sâu bệnh', title: 'Khu vực cần kiểm tra hôm nay', description: 'Gộp cảnh báo lặp lại và ưu tiên khu vực cần kiểm tra.', refresh: 'Làm mới', loading: 'Đang tải khu vực theo dõi.', emptyTitle: 'Hiện không có khu vực cần kiểm tra ngay.', emptyHelp: 'Hệ thống vẫn tiếp tục quan sát và sẽ hiển thị khi có thay đổi mới.', candidate: 'Đối tượng nghi ngờ', recentDetection: 'Phát hiện gần nhất', recentCheck: 'Kiểm tra gần nhất', recentAction: 'Xử lý gần nhất', details: 'Chi tiết', closeDetails: 'Đóng chi tiết', fieldCheck: 'Ghi kết quả kiểm tra', action: 'Ghi nhận xử lý', resolve: 'Kết thúc vụ việc', correctionTitle: 'Sửa dữ liệu vừa nhập', correctionHelp: 'Bản gốc được giữ lại và thay đổi được lưu thành lịch sử sửa.', voidInput: 'Hủy hiệu lực nhập', noteLabel: 'Nguyên tắc ghi nhận', noteText: '“Không thấy bất thường rõ ràng” được lưu như một quan sát, không phải xác nhận hoàn toàn bình thường.', loadError: 'Không tải được khu vực theo dõi.', saveError: 'Không lưu được bản ghi.', saved: 'Đã ghi nhận.' },
  th: { eyebrow: 'เฝ้าระวังโรคและศัตรูพืช', title: 'พื้นที่ที่ต้องตรวจวันนี้', description: 'รวมการแจ้งเตือนซ้ำและแสดงพื้นที่ที่ควรตรวจเป็นอันดับแรก', refresh: 'รีเฟรช', loading: 'กำลังโหลดพื้นที่เฝ้าระวัง', emptyTitle: 'ขณะนี้ไม่มีพื้นที่ที่ต้องตรวจทันที', emptyHelp: 'ระบบยังคงสังเกตและจะแสดงเมื่อมีการเปลี่ยนแปลงใหม่', candidate: 'สิ่งที่สงสัย', recentDetection: 'ตรวจพบล่าสุด', recentCheck: 'ตรวจหน้างานล่าสุด', recentAction: 'การจัดการล่าสุด', details: 'รายละเอียด', closeDetails: 'ปิดรายละเอียด', fieldCheck: 'บันทึกผลตรวจหน้างาน', action: 'บันทึกการจัดการ', resolve: 'ปิดกรณีเฝ้าระวัง', correctionTitle: 'แก้ไขข้อมูลที่เพิ่งบันทึก', correctionHelp: 'ข้อมูลเดิมจะยังคงอยู่และบันทึกการแก้ไขเป็นประวัติ', voidInput: 'ยกเลิกรายการ', noteLabel: 'หลักการบันทึก', noteText: '“ไม่พบความผิดปกติชัดเจน” เป็นเพียงผลการสังเกต ไม่ใช่การยืนยันว่าปกติทั้งหมด', loadError: 'ไม่สามารถโหลดพื้นที่เฝ้าระวังได้', saveError: 'ไม่สามารถบันทึกได้', saved: 'บันทึกแล้ว' },
  'zh-CN': { eyebrow: '病虫害巡检', title: '今天需要确认的区域', description: '合并重复提醒，仅优先显示值得检查的区域。', refresh: '刷新', loading: '正在加载巡检区域。', emptyTitle: '目前没有需要立即确认的区域。', emptyHelp: '系统会持续观测，出现新的变化时会显示在列表中。', candidate: '检测候选', recentDetection: '最近检测', recentCheck: '最近现场检查', recentAction: '最近处理', details: '查看详情', closeDetails: '关闭详情', fieldCheck: '记录现场确认结果', action: '记录处理', resolve: '结束本次巡检事件', correctionTitle: '修改刚才的输入', correctionHelp: '不会删除原记录，而是追加修正历史。', voidInput: '作废本次输入', noteLabel: '记录原则', noteText: '“未发现明显异常”只作为当时的观察结果保存，并不等于确认完全正常。', loadError: '无法加载巡检区域。', saveError: '无法保存记录。', saved: '已记录。' },
};

function localized(value: LocalizedText, language: Language) { return value[language] ?? value.ko; }
function formatTime(value: string | null, language: Language) {
  if (!value) return '-';
  return new Intl.DateTimeFormat(localeForLanguage(language), { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}
function locationLabel(row: ScoutingLocation) {
  return row.display_location?.trim() || row.location_key?.trim() || [row.house_code, row.bed_code, row.zone_code].filter(Boolean).join(' · ');
}
function issueLabel(row: ScoutingLocation, language: Language) {
  if (row.primary_issue_code && issueLabels[row.primary_issue_code]) return localized(issueLabels[row.primary_issue_code], language);
  if (row.issue_family === 'PEST') return language === 'ko' ? '해충' : 'PEST';
  if (row.issue_family === 'DISEASE') return language === 'ko' ? '병해' : 'DISEASE';
  return language === 'ko' ? '원인 확인 중' : 'Unknown';
}
function thermalDelta(row: ScoutingLocation) {
  const base = row.latest_reference_temp ?? row.latest_ambient_temp;
  if (row.latest_leaf_temp === null || base === null) return null;
  return row.latest_leaf_temp - base;
}
function metricSummary(row: ScoutingLocation, language: Language) {
  const parts: string[] = [];
  if (row.latest_humidity !== null) parts.push(language === 'ko' ? `습도 ${Math.round(row.latest_humidity)}%` : `RH ${Math.round(row.latest_humidity)}%`);
  const delta = thermalDelta(row);
  if (delta !== null) parts.push(language === 'ko' ? `잎 온도 ${delta >= 0 ? '+' : ''}${delta.toFixed(1)}℃` : `Leaf ΔT ${delta >= 0 ? '+' : ''}${delta.toFixed(1)}℃`);
  if (row.observation_count > 1) parts.push(language === 'ko' ? `관측 ${row.observation_count}회` : `${row.observation_count} observations`);
  return parts;
}
function focusedLocationId() {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('scoutingLocation')?.trim() ?? '';
}

type RecentFieldCheck = { fieldCheckId: string; label: string };

export function ScoutingQueue({ farmId, canReview, language, onChanged }: {
  farmId: string; canReview: boolean; language: Language; onChanged?: () => void;
}) {
  const [rows, setRows] = useState<ScoutingLocation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState('');
  const [recentFieldCheck, setRecentFieldCheck] = useState<RecentFieldCheck | null>(null);
  const text = copy[language];
  const selected = useMemo(() => rows.find((row) => row.id === selectedId) ?? null, [rows, selectedId]);

  const load = useCallback(async () => {
    if (!farmId) { setRows([]); setSelectedId(null); return; }
    setLoading(true); setError('');
    try {
      const focus = focusedLocationId();
      const params = new URLSearchParams({ farmId, attention: '1', limit: '20' });
      if (focus) params.set('locationStateId', focus);
      const response = await fetch(`/api/scouting-locations?${params}`, { cache: 'no-store' });
      const result = await response.json() as QueueResponse;
      if (!response.ok) throw new Error(result.error ?? text.loadError);
      setRows(result.rows);
      setSelectedId((current) => {
        if (focus && result.rows.some((row) => row.id === focus)) return focus;
        return current && result.rows.some((row) => row.id === current) ? current : null;
      });
    } catch (caught) { setError(caught instanceof Error ? caught.message : text.loadError); }
    finally { setLoading(false); }
  }, [farmId, text.loadError]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(async () => { if (!cancelled) await load(); });
    return () => { cancelled = true; };
  }, [load]);

  async function post(path: string, body: Record<string, unknown>) {
    const response = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const result = await response.json() as { error?: string; message?: string; fieldCheckId?: string };
    if (!response.ok) throw new Error(result.error ?? text.saveError);
    return result;
  }

  async function submitFieldCheck(row: ScoutingLocation, code: string) {
    setSending(`${row.id}:${code}`); setMessage(''); setError('');
    try {
      const result = await post('/api/scouting-field-checks', { farmId, locationStateId: row.id, evidenceCode: code });
      if (result.fieldCheckId) setRecentFieldCheck({ fieldCheckId: result.fieldCheckId, label: locationLabel(row) });
      setMessage(result.message ?? text.saved); await load(); onChanged?.();
    } catch (caught) { setError(caught instanceof Error ? caught.message : text.saveError); }
    finally { setSending(''); }
  }

  async function submitAction(row: ScoutingLocation, code: string) {
    setSending(`${row.id}:${code}`); setMessage(''); setError('');
    try { const result = await post('/api/scouting-actions', { farmId, locationStateId: row.id, actionCode: code }); setMessage(result.message ?? text.saved); await load(); onChanged?.(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : text.saveError); }
    finally { setSending(''); }
  }

  async function correctRecent(code: string | null) {
    if (!recentFieldCheck) return;
    setSending(`correction:${recentFieldCheck.fieldCheckId}`); setMessage(''); setError('');
    try {
      const result = await post('/api/scouting-field-check-corrections', {
        farmId, fieldCheckId: recentFieldCheck.fieldCheckId,
        correctionKind: code ? 'REPLACE' : 'VOID', replacementEvidenceCode: code, reasonCode: 'MISCLICK',
      });
      setMessage(result.message ?? text.saved); setRecentFieldCheck(null); await load(); onChanged?.();
    } catch (caught) { setError(caught instanceof Error ? caught.message : text.saveError); }
    finally { setSending(''); }
  }

  async function resolve(row: ScoutingLocation, reasonCode: string) {
    setSending(`resolve:${row.id}`); setMessage(''); setError('');
    try { const result = await post('/api/scouting-resolve', { farmId, locationStateId: row.id, reasonCode }); setMessage(result.message ?? text.saved); closeDetail(); await load(); onChanged?.(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : text.saveError); }
    finally { setSending(''); }
  }

  function closeDetail() {
    setSelectedId(null);
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href);
      url.searchParams.delete('scoutingLocation');
      window.history.replaceState(null, '', url);
    }
  }

  return <section className="scouting-queue" aria-busy={loading}>
    <header className="scouting-queue-heading"><div><span>{text.eyebrow}</span><h2>{text.title}</h2><p>{text.description}</p></div><button disabled={loading || !farmId} onClick={() => void load()} type="button">{text.refresh}</button></header>
    {message && <div className="review-feedback success" role="status">{message}</div>}
    {error && <div className="review-feedback error" role="alert">{error}</div>}
    {loading ? <div className="screen-empty compact"><strong>{text.loading}</strong></div>
      : rows.length === 0 ? <div className="scouting-all-clear"><strong>{text.emptyTitle}</strong><p>{text.emptyHelp}</p></div>
        : <div className="scouting-workspace">
          <div className="scouting-location-list" role="list">{rows.map((row) => {
            const state = stateLabels[row.current_state] ?? stateLabels.WATCH;
            const metrics = metricSummary(row, language);
            const reason = row.last_alert_reason && reasonLabels[row.last_alert_reason] ? localized(reasonLabels[row.last_alert_reason], language) : null;
            return <button aria-pressed={selectedId === row.id} className={`scouting-location-row state-${row.current_state.toLowerCase()} ${selectedId === row.id ? 'selected' : ''}`} key={row.id} onClick={() => setSelectedId(row.id)} role="listitem" type="button">
              <span className="scouting-state-badge">{localized(state, language)}</span>
              <span className="scouting-location-identity"><strong>{locationLabel(row)}</strong><small>{text.candidate}: {issueLabel(row, language)}</small></span>
              <span className="scouting-location-signals">{metrics.length ? metrics.join(' · ') : reason ?? '-'}</span>
              <time>{formatTime(row.last_alert_at ?? row.last_observed_at, language)}</time>
              <span className="scouting-row-chevron" aria-hidden="true">›</span>
            </button>;
          })}</div>

          {selected && <aside className="scouting-detail-panel" aria-label={`${locationLabel(selected)} ${text.details}`}>
            <div className="scouting-detail-heading">
              <div><span className="scouting-state-badge">{localized(stateLabels[selected.current_state] ?? stateLabels.WATCH, language)}</span><h3>{locationLabel(selected)}</h3><p>{text.candidate}: <strong>{issueLabel(selected, language)}</strong></p></div>
              <button className="scouting-detail-close" onClick={closeDetail} type="button">{text.closeDetails}</button>
            </div>

            <div className="scouting-signal-grid">
              {selected.latest_humidity !== null && <div><span>{language === 'ko' ? '습도' : 'RH'}</span><strong>{Math.round(selected.latest_humidity)}%</strong></div>}
              {thermalDelta(selected) !== null && <div><span>{language === 'ko' ? '잎 온도 차' : 'Leaf ΔT'}</span><strong>{thermalDelta(selected)! >= 0 ? '+' : ''}{thermalDelta(selected)!.toFixed(1)}℃</strong></div>}
              <div><span>{language === 'ko' ? '관측 횟수' : 'Observations'}</span><strong>{selected.observation_count}</strong></div>
              {selected.last_alert_reason && <div><span>{language === 'ko' ? '최근 변화' : 'Latest change'}</span><strong>{reasonLabels[selected.last_alert_reason] ? localized(reasonLabels[selected.last_alert_reason], language) : selected.last_alert_reason}</strong></div>}
            </div>

            <div className="scouting-detail-meta">
              <span>{text.recentDetection} <b>{formatTime(selected.last_alert_at ?? selected.last_observed_at, language)}</b></span>
              <span>{text.recentCheck} <b>{formatTime(selected.last_field_check_at, language)}</b></span>
              <span>{text.recentAction} <b>{formatTime(selected.last_action_at, language)}</b></span>
            </div>

            {recentFieldCheck && canReview && <aside className="scouting-correction-panel"><div><strong>{text.correctionTitle}</strong><span>{recentFieldCheck.label}</span><p>{text.correctionHelp}</p></div><div className="scouting-choice-grid">{evidenceOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void correctRecent(option.code)} type="button">{localized(option, language)}</button>)}<button disabled={Boolean(sending)} onClick={() => void correctRecent(null)} type="button">{text.voidInput}</button></div></aside>}

            {canReview && <div className="scouting-detail-actions">
              <details><summary>{text.fieldCheck}</summary><div className="scouting-choice-grid">{evidenceOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void submitFieldCheck(selected, option.code)} type="button">{localized(option, language)}</button>)}</div></details>
              <details><summary>{text.action}</summary><div className="scouting-choice-grid compact">{actionOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void submitAction(selected, option.code)} type="button">{localized(option, language)}</button>)}</div></details>
              <details className="secondary"><summary>{text.resolve}</summary><div className="scouting-choice-grid compact">{resolveOptions.map((option) => <button disabled={Boolean(sending)} key={option.code} onClick={() => void resolve(selected, option.code)} type="button">{localized(option, language)}</button>)}</div></details>
            </div>}
            <p className="scouting-evidence-note"><strong>{text.noteLabel}</strong> {text.noteText}</p>
          </aside>}
        </div>}
  </section>;
}
