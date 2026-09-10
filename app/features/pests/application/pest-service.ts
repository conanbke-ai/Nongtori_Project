import { findPestTarget, pestTargets, reviewVerdict } from '../domain/catalog';
import type { PestRepository } from '../infrastructure/pest-repository';

export async function loadPestDashboard(repository: PestRepository, farmId: string, code: string, status: 'OPEN' | 'DONE', requestedPage: number, limit = 20) {
  if (code && !findPestTarget(code)) throw new Error('지원하는 병해충 종류를 선택해 주세요.');
  const counts = await repository.counts(farmId);
  const count = (target: string, state: string) => counts.filter((row) => (!target || row.pest_code === target) && row.review_status === state).reduce((sum, row) => sum + Number(row.count), 0);
  const total = count(code, status);
  const page = Math.min(requestedPage, Math.max(1, Math.ceil(total / limit)));
  return {
    rows: await repository.list(farmId, code, status, limit, (page - 1) * limit),
    totalOpen: count('', 'OPEN'),
    breakdown: pestTargets.map((target) => ({ code: target.code, label: target.labels.ko, capability: target.capability, openCount: count(target.code, 'OPEN') })),
    pagination: { status, page, limit, total, pageCount: Math.ceil(total / limit), openCount: count(code, 'OPEN'), doneCount: count(code, 'DONE') },
  };
}

export async function savePestReview(repository: PestRepository, input: Parameters<PestRepository['addReview']>[0]) {
  const target = await repository.target(input.farmId, input.predictionId);
  if (!target) return null;
  const verdict = reviewVerdict(target.pest_code, input.verdict);
  if (target.pest_code !== 'MITE' && input.quickNote === 'WEBBING_SEEN') throw new Error('선택한 병해충에 맞는 확인 항목을 선택해 주세요.');
  await repository.addReview({ ...input, verdict });
  return { verdict, pestCode: target.pest_code };
}
