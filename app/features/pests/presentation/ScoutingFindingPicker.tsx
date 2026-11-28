'use client';

import { useState } from 'react';
import type { Language } from '@/app/lib/i18n';
import type { FieldEvidenceCode } from '../domain/scouting-policy';

export const findingGroups = {
  NONE: ['NO_VISIBLE_EVIDENCE'],
  PEST_DISEASE: ['WEBBING_OR_MITE_TRACE_SUSPECTED', 'DIRECT_MITE_OR_EGG_CONFIRMED', 'OTHER_PEST_LIKE_EVIDENCE', 'DISEASE_LIKE_EVIDENCE'],
  OTHER: ['LEAF_DAMAGE_OBSERVED', 'PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY'],
  UNCERTAIN: ['INCONCLUSIVE'],
} as const satisfies Record<string, readonly FieldEvidenceCode[]>;
type FindingGroup = keyof typeof findingGroups;
const groupIds = Object.keys(findingGroups) as FindingGroup[];
const copy = {
  ko: { title: '관찰한 내용 선택', help: '먼저 관찰한 내용을 고른 뒤, 아래 결과 버튼을 눌러 기록하세요. 선택만으로 저장되지 않습니다.', result: '관찰 결과 기록', groups: ['뚜렷한 이상 못 찾음', '병해충 흔적 발견', '기타 이상 발견', '판단 어려움'] },
  vi: { title: 'Chọn nội dung quan sát', help: 'Chọn nhóm rồi nhấn kết quả bên dưới để ghi nhận. Chọn nhóm chưa lưu dữ liệu.', result: 'Ghi kết quả quan sát', groups: ['Không thấy bất thường rõ ràng', 'Thấy dấu hiệu sâu bệnh', 'Thấy bất thường khác', 'Khó xác định'] },
  th: { title: 'เลือกสิ่งที่สังเกต', help: 'เลือกกลุ่ม แล้วกดผลด้านล่างเพื่อบันทึก การเลือกกลุ่มยังไม่บันทึกข้อมูล', result: 'บันทึกผลการสังเกต', groups: ['ไม่พบความผิดปกติชัดเจน', 'พบร่องรอยโรคหรือศัตรูพืช', 'พบความผิดปกติอื่น', 'ยังตัดสินไม่ได้'] },
  'zh-CN': { title: '选择观察内容', help: '先选择类别，再点击下方结果按钮记录。仅选择类别不会保存。', result: '记录观察结果', groups: ['未发现明显异常', '发现病虫害迹象', '发现其他异常', '难以判断'] },
};

export function ScoutingFindingPicker({ scope, language, options, disabled, onSelect }: {
  scope: string; language: Language; options: readonly { code: string; label: string }[];
  disabled: boolean; onSelect: (code: string) => void;
}) {
  const [selection, setSelection] = useState<{ scope: string; group: FindingGroup } | null>(null);
  const group = selection?.scope === scope ? selection.group : null;
  const text = copy[language];
  const allowed: readonly string[] = group ? findingGroups[group] : [];
  return <div>
    <p>{text.help}</p>
    <div className="scouting-choice-grid" role="group" aria-label={text.title}>
      {groupIds.map((id, index) => <button type="button" key={id} disabled={disabled} aria-pressed={group === id}
        onClick={() => { if (!disabled) setSelection({ scope, group: id }); }}>{text.groups[index]}</button>)}
    </div>
    {group && <div className="scouting-choice-grid" role="group" aria-label={text.result}>
      {options.filter(option => allowed.includes(option.code)).map(option => <button type="button" key={option.code} disabled={disabled}
        onClick={() => { if (!disabled) onSelect(option.code); }}>{option.label}</button>)}
    </div>}
  </div>;
}
