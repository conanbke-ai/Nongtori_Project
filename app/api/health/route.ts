import { NextResponse } from 'next/server';

export const runtime = 'edge';

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    service: 'strawberry-farm-operations',
    supportedCultivars: ['SEOLHYANG'],
    cultivarPolicy: 'FARM_SCOPED_EXTENSIBLE_CATALOG',
    inputPolicy: 'DEVICE_AND_SERVER_GENERATED_IDENTIFIERS',
    diagnosisPolicy: 'HUMAN_REVIEW_REQUIRED',
  });
}
