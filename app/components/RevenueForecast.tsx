export type RevenueForecastRecord = {
  id: string;
  harvest_run_id: string;
  item_id: string;
  completed_at: string;
  harvested_count: number;
  total_weight_g: number;
  grade_breakdown_json: string;
  estimated_gross_won: number;
  estimated_cost_won: number;
  estimated_net_won: number;
  revenue_p10_won: number | null;
  revenue_p90_won: number | null;
  price_basis_date: string;
  price_model_name: string;
  price_model_version: string;
  status: string;
  generated_at: string;
};

export type ForecastJobRecord = {
  id: string;
  harvest_run_id: string;
  item_id: string;
  status: string;
  created_at: string;
};

function won(value: number | null) {
  if (value === null) return '—';
  return `${new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(Math.round(value))}원`;
}

function dateTime(value: string) {
  return new Intl.DateTimeFormat('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}

export function RevenueForecast({ itemName, forecasts, jobs }: { itemName: string; forecasts: RevenueForecastRecord[]; jobs: ForecastJobRecord[] }) {
  const latest = forecasts[0] ?? null;
  const pending = jobs.find((job) => ['PENDING', 'PROCESSING'].includes(job.status)) ?? null;

  if (!latest) {
    return (
      <div className="automatic-forecast-empty">
        <div className="automation-status"><i className={pending ? 'processing' : ''} /><div><span>예상 수익 자동 계산</span><strong>{pending ? '영상 판독 결과로 예상 수익을 계산하고 있습니다.' : '수확 영상 판독이 끝나기를 기다리고 있습니다.'}</strong><p>수량이나 가격을 직접 입력할 필요가 없습니다.</p></div></div>
        <ol className="forecast-pipeline"><li><b>1</b><span>수확 영상 판독</span></li><li><b>2</b><span>같은 딸기는 한 개로 세기</span></li><li><b>3</b><span>등급별 예상 시세 확인</span></li><li><b>4</b><span>예상 수익 계산</span></li></ol>
        <p className="forecast-note">{itemName} 영상에서 등급별 딸기 수를 확인한 뒤 예상 시세와 합쳐 이 화면에 자동으로 보여드립니다.</p>
      </div>
    );
  }

  let grades: Array<{ grade: string; count: number; weight_g: number; predicted_price_per_kg: number }> = [];
  try { grades = JSON.parse(latest.grade_breakdown_json) as typeof grades; } catch { grades = []; }

  return (
    <div className="revenue-forecast-result">
      <header><div><span>최근 자동 산출</span><h3>{dateTime(latest.completed_at)} 수확 작업</h3><p>{latest.price_model_name} {latest.price_model_version} · 가격 기준 {latest.price_basis_date}</p></div><b>{latest.status === 'COMPLETED' ? '산출 완료' : latest.status === 'PRICE_ONLY' ? '비용 설정 필요' : '검토 필요'}</b></header>
      <div className="forecast-summary"><article><span>수확량</span><strong>{latest.harvested_count}개</strong><small>{(latest.total_weight_g / 1000).toFixed(1)}kg</small></article><article><span>예상 매출</span><strong>{won(latest.estimated_gross_won)}</strong><small>등급별 P50 단가 기준</small></article><article><span>예상 비용</span><strong>{won(latest.estimated_cost_won)}</strong><small>농가 계약 설정 기준</small></article><article className="net"><span>예상 수익</span><strong>{won(latest.estimated_net_won)}</strong><small>{won(latest.revenue_p10_won)} ~ {won(latest.revenue_p90_won)}</small></article></div>
      <div className="forecast-grade-list"><div><span>등급</span><span>판정 수량</span><span>중량</span><span>예측 단가</span></div>{grades.map((grade) => <article key={grade.grade}><strong>{grade.grade}</strong><span>{grade.count}개</span><span>{(grade.weight_g / 1000).toFixed(1)}kg</span><b>{won(grade.predicted_price_per_kg)}/kg</b></article>)}</div>
      <p className="forecast-note">예측 구간과 실제 정산액은 출하 시장·포장 단위·수수료와 당일 거래 조건에 따라 달라질 수 있습니다.</p>
    </div>
  );
}
