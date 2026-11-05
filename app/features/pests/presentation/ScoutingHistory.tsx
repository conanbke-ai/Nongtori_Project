'use client';

import { useLayoutEffect, useState } from 'react';
import { localeForLanguage, type Language } from '@/app/lib/i18n';
import { historyScope, ScoutingHistoryReader, type HistoryLoadState } from './scouting-history-reader';
import './scouting-history.css';
import { ScoutingOriginalCheck } from './ScoutingOriginalCheck';

const copy = {
  ko: { title: '예찰 이력 보기', close: '이력 접기', refresh: '이력 새로고침', loading: '예찰 이력을 불러오는 중입니다.', error: '이력을 불러오지 못했습니다. 다시 조회해 주세요.', empty: '조회 범위에 저장된 이력이 없습니다. 병해충이 없다는 뜻은 아닙니다.', stale: '갱신하지 못해 이전 조회 결과를 표시합니다.', idle: '이력을 조회해 주세요.', limit: '종류별 최근 50건 · 더 이전 기록이 있을 수 있습니다. 새로고침으로 갱신합니다.', time: '시각 미상', unknown: '종류 미확인', original: '원본 확인 기록', outside: '원본 확인 기록은 조회 범위 밖에 있습니다.', replacement: '대체 관찰', types: ['관측', '현장 확인', '정정', '조치', '알림', 'CASE 이력'], codes: ['입력 대체', '입력 무효', '열화상 관측', '일반 사진 관측', '센서 관측', '수기 관측', 'CASE 시작', 'CASE 종료', '재발 CASE 시작', '현장 입력 정정', '알림 발행', '반복 알림 억제', '재확인 요청', '위험 변화 알림'] },
  vi: { title: 'Xem lịch sử theo dõi', close: 'Thu gọn lịch sử', refresh: 'Làm mới lịch sử', loading: 'Đang tải lịch sử.', error: 'Không tải được lịch sử. Hãy thử lại.', empty: 'Không có bản ghi trong phạm vi truy vấn; không có nghĩa là không có sâu bệnh.', stale: 'Không làm mới được; đang hiển thị lần tra cứu trước.', idle: 'Hãy tải lịch sử.', limit: '50 bản ghi gần nhất mỗi loại; có thể còn bản ghi cũ hơn. Làm mới để cập nhật.', time: 'Chưa rõ thời gian', unknown: 'Chưa rõ loại', original: 'Bản kiểm tra gốc', outside: 'Bản gốc nằm ngoài phạm vi truy vấn.', replacement: 'Quan sát thay thế', types: ['Quan sát', 'Kiểm tra', 'Sửa đổi', 'Xử lý', 'Cảnh báo', 'Lịch sử CASE'], codes: ['Thay thế đầu vào', 'Vô hiệu đầu vào', 'Ảnh nhiệt', 'Ảnh thường', 'Cảm biến', 'Thủ công', 'Mở CASE', 'Đóng CASE', 'CASE tái phát', 'Sửa kiểm tra', 'Phát cảnh báo', 'Hạn chế cảnh báo lặp', 'Yêu cầu kiểm tra lại', 'Cảnh báo thay đổi'] },
  th: { title: 'ดูประวัติการตรวจแปลง', close: 'ย่อประวัติ', refresh: 'รีเฟรชประวัติ', loading: 'กำลังโหลดประวัติ', error: 'โหลดประวัติไม่ได้ กรุณาลองใหม่', empty: 'ไม่มีบันทึกในช่วงที่ค้นหา ไม่ได้หมายความว่าไม่มีศัตรูพืช', stale: 'รีเฟรชไม่สำเร็จ กำลังแสดงผลจากครั้งก่อน', idle: 'กรุณาเรียกดูประวัติ', limit: 'ล่าสุดชนิดละ 50 บันทึก อาจมีบันทึกเก่ากว่านี้ รีเฟรชเพื่ออัปเดต', time: 'ไม่ทราบเวลา', unknown: 'ไม่ทราบชนิด', original: 'บันทึกตรวจต้นฉบับ', outside: 'บันทึกต้นฉบับอยู่นอกช่วงที่ค้นหา', replacement: 'ข้อสังเกตที่ใช้แทน', types: ['สังเกต', 'ตรวจในพื้นที่', 'แก้ไข', 'ดำเนินการ', 'แจ้งเตือน', 'ประวัติ CASE'], codes: ['แทนข้อมูล', 'ยกเลิกข้อมูล', 'ภาพความร้อน', 'ภาพทั่วไป', 'เซ็นเซอร์', 'บันทึกด้วยมือ', 'เปิด CASE', 'ปิด CASE', 'CASE เกิดซ้ำ', 'แก้ไขการตรวจ', 'ออกแจ้งเตือน', 'ระงับแจ้งเตือนซ้ำ', 'ขอตรวจซ้ำ', 'แจ้งการเปลี่ยนแปลง'] },
  'zh-CN': { title: '查看巡查历史', close: '收起历史', refresh: '刷新历史', loading: '正在加载历史。', error: '无法加载历史，请重试。', empty: '查询范围内没有已保存记录，不代表不存在病虫害。', stale: '刷新失败，正在显示上次查询结果。', idle: '请查询历史。', limit: '每类最近50条，可能还有更早记录。刷新以更新。', time: '时间未知', unknown: '类型未知', original: '原始检查记录', outside: '原始检查记录不在本次查询范围内。', replacement: '替代观察', types: ['观察', '现场检查', '更正', '措施', '警报', 'CASE历史'], codes: ['替换输入', '作废输入', '热成像观察', '普通照片观察', '传感器观察', '人工观察', 'CASE开始', 'CASE结束', '复发CASE开始', '更正现场输入', '发布警报', '抑制重复警报', '请求复查', '风险变化警报'] },
};
const kinds = ['observations', 'fieldChecks', 'corrections', 'actions', 'alerts', 'caseEvents'];
const codes = ['REPLACE', 'VOID', 'THERMAL', 'RGB_REFERENCE', 'SENSOR', 'MANUAL', 'OPENED', 'RESOLVED', 'RECURRENCE_OPENED', 'FIELD_CHECK_CORRECTED', 'ISSUED', 'SUPPRESSED', 'RECHECK_REQUESTED', 'ESCALATED'];
const fusion = { ko: '융합 관측', vi: 'Quan sát kết hợp', th: 'การสังเกตแบบผสาน', 'zh-CN': '融合观察' };
type Label = (code: string) => string | null;

// Pure view exported for deterministic markup tests, not browser acceptance.
export function ScoutingHistoryPanel({ state, language, labelForCode = () => null, onRetry, farmId, locationId }: {
  state: HistoryLoadState; language: Language; labelForCode?: Label; onRetry: () => void;
  farmId?: string; locationId?: string;
}) {
  const text = copy[language];
  const label = (code: string) => labelForCode(code) ?? (code === 'FUSION' ? fusion[language] : text.codes[codes.indexOf(code)]) ?? text.unknown;
  const checks = new Set(state.entries.filter(row => row.kind === 'fieldChecks').map(row => row.id));
  const checkAnchor = (id: string) => `scouting-history-check-${encodeURIComponent(id)}`;
  return <div className="scouting-history-panel" aria-busy={state.status === 'loading'}>
    {state.status === 'loading' && <p role="status">{text.loading}</p>}
    {state.status === 'idle' && <p role="status">{text.idle}</p>}
    {(state.status === 'error' || state.status === 'stale') && <p role="alert">{state.status === 'stale' ? text.stale : text.error}</p>}
    {state.status === 'ready' && state.entries.length === 0 && <p role="status">{text.empty}</p>}
    <p className="scouting-history-limit">{text.limit}</p>
    <button type="button" disabled={state.status === 'loading'} onClick={onRetry}>{text.refresh}</button>
    {state.entries.length > 0 && <ol tabIndex={0} aria-label={text.title}>{state.entries.map(entry => <li key={`${entry.kind}:${entry.id}`} id={entry.kind === 'fieldChecks' ? checkAnchor(entry.id) : undefined}>
      <div><strong>{text.types[kinds.indexOf(entry.kind)]} · {label(entry.code)}</strong>
        <time dateTime={entry.at ?? undefined}>{entry.at ? new Intl.DateTimeFormat(localeForLanguage(language), { dateStyle: 'short', timeStyle: 'short' }).format(new Date(entry.at)) : text.time}</time></div>
      {entry.kind === 'corrections' && <p>{entry.originalCheckId && checks.has(entry.originalCheckId)
        ? <a href={`#${checkAnchor(entry.originalCheckId)}`}>{text.original}</a> : <>{text.outside}
          {entry.originalCheckId && farmId && locationId && state.status === 'ready' && <ScoutingOriginalCheck
            key={JSON.stringify([farmId, locationId, entry.originalCheckId])} farmId={farmId} locationId={locationId}
            checkId={entry.originalCheckId} language={language} labelForCode={label} />}</>}
        {entry.code === 'REPLACE' && entry.replacementCode && <> · {text.replacement}: {label(entry.replacementCode)}</>}</p>}
    </li>)}</ol>}
  </div>;
}

export function ScoutingHistory({ farmId, locationId, language, labelForCode }: {
  farmId: string; locationId: string; language: Language; labelForCode?: Label;
}) {
  const [reader] = useState(() => new ScoutingHistoryReader());
  const [opened, setOpened] = useState(false);
  const scope = historyScope(farmId, locationId);
  const [state, setState] = useState<HistoryLoadState>({ scope, status: 'idle', entries: [] });
  useLayoutEffect(() => { reader.invalidate(); return () => reader.invalidate(); }, [reader, farmId, locationId]);
  const current: HistoryLoadState = state.scope === scope ? state : { scope, status: 'idle', entries: [] };
  const load = () => { void reader.load(farmId, locationId, setState); };
  return <section className="scouting-history" aria-label={copy[language].title}>
    <button type="button" aria-expanded={opened} disabled={!farmId || !locationId} onClick={() => {
      if (opened) { reader.invalidate(); setOpened(false); }
      else { setOpened(true); load(); }
    }}>{opened ? copy[language].close : copy[language].title}</button>
    {opened && <ScoutingHistoryPanel state={current} language={language} labelForCode={labelForCode} onRetry={load} farmId={farmId} locationId={locationId} />}
  </section>;
}
