'use client';

import { useState } from 'react';
import type { Language } from '@/app/lib/i18n';
import { readLegacyFieldEvidence, type LegacyFindingFamily } from '../domain/legacy-field-evidence-view';

const copy = {
  ko: { toggle: '기록 해석 출처', source: '원문 코드', derived: '기존 기록에서 해석됨', warning: '코드 해석이며 새 진단이나 확정 음성 판정이 아닙니다.', unknown: '해석 규칙에 없는 코드입니다. 원문을 유지합니다.', empty: '(빈 코드)', category: '관찰 범주', target: '원문 코드의 대상 표기', mite: '응애', version: '해석 규칙', families: ['해충 관련 관찰', '병해 관련 관찰', '환경·생리 관련 관찰', '범주 미확인', '당시 뚜렷한 이상 못 찾음'] },
  vi: { toggle: 'Nguồn diễn giải bản ghi', source: 'Mã gốc', derived: 'Diễn giải từ bản ghi hiện có', warning: 'Đây là diễn giải mã, không phải chẩn đoán mới hay kết luận âm tính.', unknown: 'Chưa có quy tắc cho mã này. Giữ nguyên mã gốc.', empty: '(mã trống)', category: 'Nhóm quan sát', target: 'Đối tượng ghi trong mã gốc', mite: 'Nhện đỏ', version: 'Quy tắc diễn giải', families: ['Quan sát liên quan sâu hại', 'Quan sát liên quan bệnh cây', 'Quan sát môi trường/sinh lý', 'Chưa rõ nhóm', 'Lúc đó không thấy bất thường rõ ràng'] },
  th: { toggle: 'ที่มาของการแปลบันทึก', source: 'รหัสต้นฉบับ', derived: 'แปลจากบันทึกเดิม', warning: 'เป็นการแปลรหัส ไม่ใช่การวินิจฉัยใหม่หรือยืนยันผลลบ', unknown: 'ยังไม่มีกฎสำหรับรหัสนี้ คงรหัสต้นฉบับไว้', empty: '(รหัสว่าง)', category: 'กลุ่มการสังเกต', target: 'สิ่งที่ระบุในรหัสต้นฉบับ', mite: 'ไรแดง', version: 'กฎการแปล', families: ['การสังเกตเกี่ยวกับศัตรูพืช', 'การสังเกตเกี่ยวกับโรคพืช', 'การสังเกตสภาพแวดล้อม/สรีรวิทยา', 'ยังไม่ทราบกลุ่ม', 'ขณะนั้นไม่พบความผิดปกติชัดเจน'] },
  'zh-CN': { toggle: '记录解读来源', source: '原始代码', derived: '根据已有记录解读', warning: '仅为代码解读，不是新诊断或确定的阴性结论。', unknown: '此代码尚无解读规则，保留原始代码。', empty: '（空代码）', category: '观察类别', target: '原始代码注明的对象', mite: '叶螨', version: '解读规则', families: ['虫害相关观察', '病害相关观察', '环境/生理相关观察', '类别未确认', '当时未发现明显异常'] },
};
const families: LegacyFindingFamily[] = ['PEST', 'DISEASE', 'PHYSIOLOGICAL_ENVIRONMENTAL', 'UNKNOWN', 'NONE_VISIBLE'];

// Consumes a projected code only. Opening this view cannot fetch or mutate data.
export function LegacyEvidenceReading({ code, language }: { code: string; language: Language }) {
  const [opened, setOpened] = useState(false);
  const text = copy[language];
  const view = readLegacyFieldEvidence({ primaryEvidenceCode: code });
  const finding = view.derived.findings[0];
  return <span className="scouting-legacy-reading">
    <button type="button" aria-expanded={opened} onClick={() => setOpened(value => !value)}>{text.toggle}</button>
    {opened && <span className="scouting-legacy-reading-content">
      <span>{text.source}: <code dir="ltr">{view.source.code || text.empty}</code></span>
      <strong>{text.derived}</strong>
      <span>{text.warning}</span>
      {view.derived.status !== 'RECOGNIZED' ? <span>{text.unknown}</span> : finding && <>
        <span>{text.category}: {text.families[families.indexOf(finding.family)]}</span>
        {finding.issueCode === 'SPIDER_MITE' && <span>{text.target}: {text.mite} (<code dir="ltr">{finding.issueCode}</code>)</span>}
      </>}
      <span>{text.version}: <code dir="ltr">{view.derived.mapperVersion}</code></span>
    </span>}
  </span>;
}
