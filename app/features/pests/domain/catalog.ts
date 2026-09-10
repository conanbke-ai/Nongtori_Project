export type PestLanguage = 'ko' | 'vi' | 'th' | 'zh-CN';
export type PestTarget = {
  code: string;
  kind: 'PEST' | 'DISEASE' | 'UNIDENTIFIED';
  labels: Record<PestLanguage, string>;
  aliases: readonly string[];
  // No validated inference worker is connected in this application baseline.
  capability: 'RECORD_ONLY';
};

// Extend this registry when adding a target; routing, forms, filters and summaries
// consume it. A catalog entry does not claim that an AI model can diagnose it.
export const pestTargets: readonly PestTarget[] = [
  { code: 'MITE', kind: 'PEST', labels: { ko: '응애', vi: 'Nhện đỏ', th: 'ไรแดง', 'zh-CN': '叶螨' }, aliases: ['MITE', 'MITES', 'SPIDER_MITE', 'SPIDER_MITES', '응애'], capability: 'RECORD_ONLY' },
  { code: 'POWDERY_MILDEW', kind: 'DISEASE', labels: { ko: '흰가루병', vi: 'Bệnh phấn trắng', th: 'โรคราแป้ง', 'zh-CN': '白粉病' }, aliases: ['POWDERY_MILDEW', '흰가루병'], capability: 'RECORD_ONLY' },
  { code: 'GRAY_MOLD', kind: 'DISEASE', labels: { ko: '잿빛곰팡이병', vi: 'Bệnh mốc xám', th: 'โรคราสีเทา', 'zh-CN': '灰霉病' }, aliases: ['GRAY_MOLD', 'GREY_MOLD', 'BOTRYTIS', '잿빛곰팡이병'], capability: 'RECORD_ONLY' },
  { code: 'APHID', kind: 'PEST', labels: { ko: '진딧물', vi: 'Rệp', th: 'เพลี้ยอ่อน', 'zh-CN': '蚜虫' }, aliases: ['APHID', 'APHIDS', '진딧물'], capability: 'RECORD_ONLY' },
  { code: 'THRIPS', kind: 'PEST', labels: { ko: '총채벌레', vi: 'Bọ trĩ', th: 'เพลี้ยไฟ', 'zh-CN': '蓟马' }, aliases: ['THRIPS', '총채벌레'], capability: 'RECORD_ONLY' },
  { code: 'OTHER', kind: 'UNIDENTIFIED', labels: { ko: '기타·미확인', vi: 'Khác / chưa xác định', th: 'อื่น ๆ / ยังไม่ทราบ', 'zh-CN': '其他／未确认' }, aliases: [], capability: 'RECORD_ONLY' },
];

export function findPestTarget(code: string) {
  return pestTargets.find((target) => target.code === code);
}

export function pestLabel(code: string, language: PestLanguage) {
  return findPestTarget(code)?.labels[language] ?? code;
}

export function reviewVerdict(code: string, verdict: string) {
  if (verdict === 'RECHECK' || verdict === 'TARGET_CONFIRMED' || verdict === 'NOT_TARGET') return verdict;
  if (code === 'MITE' && (verdict === 'MITE_CONFIRMED' || verdict === 'NOT_MITE')) return verdict;
  throw new Error('선택한 병해충에 맞는 현장 확인 결과를 선택해 주세요.');
}
