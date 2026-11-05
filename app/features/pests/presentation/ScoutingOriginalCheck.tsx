'use client';
import { useLayoutEffect, useState } from 'react';
import { localeForLanguage, type Language } from '@/app/lib/i18n';
import { originalScope, ScoutingOriginalReader, type OriginalState } from './scouting-original-reader';

const copy = {
  ko: ['원본 단건 조회', '원본을 불러오는 중입니다.', '이 농장·구역에서 원본을 찾을 수 없습니다.', '현재 원본을 볼 권한이 없습니다.', '원본을 불러오지 못했습니다. 다시 조회해 주세요.', '시각 미상', '종류 미확인', '원본 기록 · 정정 적용 전'],
  vi: ['Xem bản gốc', 'Đang tải bản gốc.', 'Không tìm thấy bản gốc trong khu vực này.', 'Hiện không có quyền xem bản gốc.', 'Không tải được. Hãy thử lại.', 'Chưa rõ thời gian', 'Chưa rõ loại', 'Bản gốc · trước sửa đổi'],
  th: ['ดูต้นฉบับ', 'กำลังโหลดต้นฉบับ', 'ไม่พบต้นฉบับในพื้นที่นี้', 'ไม่มีสิทธิ์ดูต้นฉบับในขณะนี้', 'โหลดไม่ได้ กรุณาลองใหม่', 'ไม่ทราบเวลา', 'ไม่ทราบชนิด', 'ต้นฉบับ · ก่อนแก้ไข'],
  'zh-CN': ['查询原始记录', '正在加载原始记录。', '此农场区域内未找到原始记录。', '当前无权查看原始记录。', '无法加载，请重试。', '时间未知', '类型未知', '原始记录 · 更正前'],
};

export function ScoutingOriginalCheck({ farmId, locationId, checkId, language, labelForCode }: {
  farmId: string; locationId: string; checkId: string; language: Language; labelForCode: (code: string) => string | null;
}) {
  const [reader] = useState(() => new ScoutingOriginalReader());
  const scope = originalScope(farmId, locationId, checkId);
  const [state, setState] = useState<OriginalState>({ scope, status: 'idle', entry: null });
  useLayoutEffect(() => { reader.invalidate(); return () => reader.invalidate(); }, [reader, scope]);
  const current = state.scope === scope ? state : { scope, status: 'idle', entry: null };
  const text = copy[language];
  return <span className="scouting-original-check">
    <button type="button" disabled={current.status === 'loading'} onClick={() => { void reader.load(farmId, locationId, checkId, setState); }}>{text[0]}</button>
    {current.status === 'loading' && <span role="status">{text[1]}</span>}
    {['missing', 'denied', 'error'].includes(current.status) && <span role="alert">{text[current.status === 'missing' ? 2 : current.status === 'denied' ? 3 : 4]}</span>}
    {current.entry && <span role="status">{text[7]} · {labelForCode(current.entry.code) ?? text[6]} · <time dateTime={current.entry.at ?? undefined}>{current.entry.at ? new Intl.DateTimeFormat(localeForLanguage(language), { dateStyle: 'short', timeStyle: 'short' }).format(new Date(current.entry.at)) : text[5]}</time></span>}
  </span>;
}
