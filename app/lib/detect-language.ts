export type SupportedLanguage = 'ko' | 'vi' | 'th' | 'zh-CN';

export type LanguageDetection = {
  language: SupportedLanguage;
  method: 'SCRIPT' | 'VIETNAMESE_MARKS' | 'HINT' | 'PROFILE' | 'DEFAULT';
  confidence: 'HIGH' | 'MEDIUM' | 'FALLBACK';
};

const supported = new Set<SupportedLanguage>(['ko', 'vi', 'th', 'zh-CN']);

export function normalizeSupportedLanguage(value: unknown): SupportedLanguage | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLowerCase();
  if (normalized === 'zh' || normalized === 'zh-cn') return 'zh-CN';
  if (supported.has(normalized as SupportedLanguage)) return normalized as SupportedLanguage;
  return null;
}

function count(value: string, expression: RegExp) {
  return value.match(expression)?.length ?? 0;
}

export function detectSupportedLanguage(
  content: string,
  hint?: unknown,
  preferredLanguage?: unknown,
): LanguageDetection {
  const normalized = content.normalize('NFC');
  const korean = count(normalized, /[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]/gu);
  const thai = count(normalized, /[\u0e00-\u0e7f]/gu);
  const chinese = count(normalized, /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/gu);
  const vietnameseMarks = count(normalized, /[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/giu);
  const vietnamese = vietnameseMarks > 0 ? count(normalized, /[a-zăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/giu) : 0;
  const candidates: Array<{ language: SupportedLanguage; score: number; method: LanguageDetection['method'] }> = [
    { language: 'ko', score: korean, method: 'SCRIPT' },
    { language: 'th', score: thai, method: 'SCRIPT' },
    { language: 'zh-CN', score: chinese, method: 'SCRIPT' },
    { language: 'vi', score: vietnamese, method: 'VIETNAMESE_MARKS' },
  ];
  const total = candidates.reduce((sum, candidate) => sum + candidate.score, 0);
  const strongest = [...candidates].sort((left, right) => right.score - left.score)[0];
  if (strongest.score >= 2 && strongest.score / Math.max(1, total) >= 0.7) {
    return { language: strongest.language, method: strongest.method, confidence: 'HIGH' };
  }

  const hinted = normalizeSupportedLanguage(hint);
  if (hinted) return { language: hinted, method: 'HINT', confidence: 'FALLBACK' };
  const preferred = normalizeSupportedLanguage(preferredLanguage);
  if (preferred) return { language: preferred, method: 'PROFILE', confidence: 'FALLBACK' };
  return { language: 'ko', method: 'DEFAULT', confidence: 'FALLBACK' };
}
