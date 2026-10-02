import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember, hasFarmAccess, hasFarmPermission } from '@/app/lib/farm-auth';
import {
  appendManualMeasuredWeight,
  loadResolvedWeight,
  publicWeightObservation,
} from '@/app/features/weight/application/weight-service';
import { WeightObservationRepository } from '@/app/features/weight/infrastructure/weight-observation-repository';

export const runtime = 'edge';

function requiredParam(url: URL, name: string) {
  return url.searchParams.get(name)?.trim() ?? '';
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const farmId = requiredParam(url, 'farmId');
    const assessmentId = requiredParam(url, 'assessmentId');
    if (!farmId || !assessmentId) {
      return NextResponse.json(
        { error: 'farmId와 assessmentId가 필요합니다.' },
        { status: 422 },
      );
    }

    await ensureSchema();
    if (!await hasFarmAccess(request, farmId)) {
      return NextResponse.json({ error: '이 농장의 기록을 볼 권한이 없습니다.' }, { status: 403 });
    }

    const repository = new WeightObservationRepository(env.DB);
    const result = await loadResolvedWeight(repository, farmId, assessmentId);
    if (!result) {
      return NextResponse.json({ error: '과실 판독 기록을 찾을 수 없습니다.' }, { status: 404 });
    }

    return NextResponse.json({
      assessmentId,
      resolved: result.resolved,
      observations: result.observations.map(publicWeightObservation),
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '무게 기록 조회에 실패했습니다.' },
      { status: 400 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    const farmId = String(body.farmId ?? '').trim();
    const assessmentId = String(body.assessmentId ?? '').trim();
    const weightG = Number(body.weightG);
    const measuredAt = body.measuredAt == null ? null : String(body.measuredAt).trim();

    if (!farmId || !assessmentId) {
      return NextResponse.json(
        { error: 'farmId와 assessmentId가 필요합니다.' },
        { status: 422 },
      );
    }
    if ('source' in body || 'modelName' in body || 'modelVersion' in body || 'confidence' in body) {
      return NextResponse.json(
        { error: '무게 출처와 모델 정보는 서버가 관리합니다.' },
        { status: 422 },
      );
    }
    if (!Number.isFinite(weightG) || weightG <= 0) {
      return NextResponse.json({ error: '0보다 큰 무게(g)를 입력해 주세요.' }, { status: 422 });
    }
    if (measuredAt && Number.isNaN(Date.parse(measuredAt))) {
      return NextResponse.json({ error: 'measuredAt은 유효한 날짜/시간이어야 합니다.' }, { status: 422 });
    }

    await ensureSchema();
    if (!await hasFarmPermission(request, farmId, 'uploadMedia')) {
      return NextResponse.json({ error: '이 농장의 측정값을 기록할 권한이 없습니다.' }, { status: 403 });
    }

    const member = await getFarmMember(request, farmId);
    const repository = new WeightObservationRepository(env.DB);
    const result = await appendManualMeasuredWeight(repository, {
      farmId,
      fruitAssessmentId: assessmentId,
      weightG,
      measuredAt,
      createdByMemberId: member?.id ?? null,
    });
    if (!result) {
      return NextResponse.json({ error: '과실 판독 기록을 찾을 수 없습니다.' }, { status: 404 });
    }

    return NextResponse.json(
      {
        observationId: result.id,
        assessmentId,
        resolved: result.resolved,
        observations: result.observations.map(publicWeightObservation),
      },
      { status: 201 },
    );
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '무게 기록 저장에 실패했습니다.' },
      { status: 400 },
    );
  }
}
