import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { processScoutingObservation } from '@/app/features/pests/application/scouting-service';
import { ScoutingRepository } from '@/app/features/pests/infrastructure/scouting-repository';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

function text(value: unknown, max = 120) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (result.length > max) throw new Error(`입력값은 ${max}자 이내여야 합니다.`);
  return result;
}
function finite(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
function flag(value: unknown) { return value === true; }

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = text(body.farmId);
    const houseId = text(body.houseId);
    const bedId = text(body.bedId);
    const zoneId = text(body.zoneId);
    if (!farmId || !houseId || !bedId || !zoneId) {
      return NextResponse.json({ error: '농장·동·베드·구역을 모두 선택해 주세요.' }, { status: 422 });
    }
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.reviewAlerts) {
      return NextResponse.json({ error: '이 농장의 예찰 기록을 등록할 권한이 없습니다.' }, { status: 403 });
    }

    const sourceType = text(body.sourceType, 30) || 'FUSION';
    if (!['THERMAL', 'RGB_REFERENCE', 'SENSOR', 'MANUAL', 'FUSION'].includes(sourceType)) {
      return NextResponse.json({ error: '지원하지 않는 관측 유형입니다.' }, { status: 422 });
    }
    const issueFamily = text(body.issueFamily, 40) || 'UNKNOWN';
    if (!['PEST', 'DISEASE', 'PHYSIOLOGICAL_ENVIRONMENTAL', 'UNKNOWN'].includes(issueFamily)) {
      return NextResponse.json({ error: '지원하지 않는 이상 유형입니다.' }, { status: 422 });
    }
    const signals = (body.signals && typeof body.signals === 'object' ? body.signals : {}) as Record<string, unknown>;
    const now = text(body.observedAt, 40) || new Date().toISOString();
    const result = await processScoutingObservation(new ScoutingRepository(env.DB), {
      farmId, houseId, bedId, zoneId, observedAt: now,
      sourceType: sourceType as 'THERMAL' | 'RGB_REFERENCE' | 'SENSOR' | 'MANUAL' | 'FUSION',
      issueFamily: issueFamily as 'PEST' | 'DISEASE' | 'PHYSIOLOGICAL_ENVIRONMENTAL' | 'UNKNOWN',
      issueCode: text(body.issueCode, 60) || null,
      signals: {
        hasMeaningfulAnomaly: flag(signals.hasMeaningfulAnomaly),
        matchesRecentKnownPattern: flag(signals.matchesRecentKnownPattern),
        hasMeaningfulNewEvidence: flag(signals.hasMeaningfulNewEvidence),
        worseningTrend: flag(signals.worseningTrend),
        spatialSpread: flag(signals.spatialSpread),
        previousFieldCheckFresh: flag(signals.previousFieldCheckFresh),
        postTreatmentRebound: flag(signals.postTreatmentRebound),
      },
      captureSessionId: text(body.captureSessionId) || null,
      frameId: text(body.frameId) || null,
      sourceAssetId: text(body.sourceAssetId) || null,
      leafTemp: finite(body.leafTemp), ambientTemp: finite(body.ambientTemp),
      referenceTemp: finite(body.referenceTemp), humidity: finite(body.humidity), lightLevel: finite(body.lightLevel),
      thermalFeatures: body.thermalFeatures, rgbReference: body.rgbReference,
      modelName: text(body.modelName) || null, modelVersion: text(body.modelVersion) || null,
      riskSignal: finite(body.riskSignal), noveltySignal: finite(body.noveltySignal),
      trendSignal: finite(body.trendSignal), spatialSignal: finite(body.spatialSignal),
      patternFingerprint: text(body.patternFingerprint, 200) || null,
    });
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '예찰 관측을 저장하지 못했습니다.' }, { status: 400 });
  }
}
