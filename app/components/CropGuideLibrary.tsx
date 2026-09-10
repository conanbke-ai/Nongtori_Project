'use client';

import { useMemo, useState } from 'react';

export type CropGuideRecord = {
  id: string;
  crop_code: string;
  crop_name: string;
  cultivar_code: string | null;
  guide_type: string;
  title: string;
  symptom_summary: string;
  risk_summary: string;
  prevention_summary: string;
  response_summary: string;
  source_title: string;
  source_url: string;
  reviewed_at: string;
  stage_codes: string | null;
};

const stageOrder = ['SEEDLING', 'TRANSPLANT', 'VEGETATIVE', 'FLOWERING', 'FRUITING', 'HARVEST'];
const stageLabels: Record<string, string> = {
  SEEDLING: '육묘',
  TRANSPLANT: '정식·활착',
  VEGETATIVE: '잎·줄기 생육',
  FLOWERING: '개화',
  FRUITING: '착과·비대',
  HARVEST: '수확',
};

function typeLabel(type: string) {
  if (type === 'PEST') return '해충';
  if (type === 'FUNGAL') return '곰팡이성 병해';
  return '기타 병해';
}

export function CropGuideLibrary({ guides, itemName }: { guides: CropGuideRecord[]; itemName: string }) {
  const [query, setQuery] = useState('');
  const [cropCode, setCropCode] = useState('');
  const [stage, setStage] = useState('');
  const [guideType, setGuideType] = useState('');

  const availableStages = useMemo(() => {
    const values = new Set(guides.flatMap((guide) => (guide.stage_codes ?? '').split(',').filter(Boolean)));
    return stageOrder.filter((code) => values.has(code));
  }, [guides]);

  const availableCrops = useMemo(() => Array.from(new Map(guides.map((guide) => [guide.crop_code, guide.crop_name])).entries()), [guides]);
  const effectiveCropCode = availableCrops.some(([code]) => code === cropCode) ? cropCode : '';

  const availableTypes = useMemo(() => Array.from(new Set(guides.map((guide) => guide.guide_type))), [guides]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLocaleLowerCase('ko-KR');
    return guides.filter((guide) => {
      const stages = (guide.stage_codes ?? '').split(',');
      if (effectiveCropCode && guide.crop_code !== effectiveCropCode) return false;
      if (stage && !stages.includes(stage)) return false;
      if (guideType && guide.guide_type !== guideType) return false;
      if (!keyword) return true;
      return [guide.title, guide.symptom_summary, guide.risk_summary, guide.prevention_summary, guide.response_summary]
        .some((value) => value.toLocaleLowerCase('ko-KR').includes(keyword));
    });
  }, [effectiveCropCode, guides, guideType, query, stage]);

  return (
    <div className="guide-library">
      <div className="guide-search-panel">
        <label className="guide-search"><span>병해충 이름이나 증상 찾기</span><input onChange={(event) => setQuery(event.target.value)} placeholder="예: 잎에 흰 가루, 응애, 과실 곰팡이" type="search" value={query} /></label>
        <label><span>작물</span><select onChange={(event) => setCropCode(event.target.value)} value={effectiveCropCode}><option value="">모든 작물</option>{availableCrops.map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label>
        <label><span>재배 시기</span><select onChange={(event) => setStage(event.target.value)} value={stage}><option value="">모든 시기</option>{availableStages.map((code) => <option key={code} value={code}>{stageLabels[code]}</option>)}</select></label>
        <label><span>종류</span><select onChange={(event) => setGuideType(event.target.value)} value={guideType}><option value="">모든 종류</option>{availableTypes.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</select></label>
      </div>

      <div className="guide-result-heading"><strong>{effectiveCropCode ? availableCrops.find(([code]) => code === effectiveCropCode)?.[1] : itemName} 관리 정보 {filtered.length}건</strong><span>증상만으로 단정하지 말고 현장에서 다시 확인해 주세요.</span></div>
      {filtered.length === 0 ? <div className="screen-empty"><span>⌕</span><strong>검색 결과가 없습니다.</strong><p>검색어를 짧게 쓰거나 재배 시기를 ‘모든 시기’로 바꿔 보세요.</p></div> : <div className="guide-grid">{filtered.map((guide) => {
        const stages = (guide.stage_codes ?? '').split(',').filter(Boolean)
          .sort((left, right) => stageOrder.indexOf(left) - stageOrder.indexOf(right));
        return <article className="guide-card" key={guide.id}><header><span>{typeLabel(guide.guide_type)}</span><b>정보 확인 {guide.reviewed_at}</b></header><h2>{guide.title}</h2><div className="guide-stage-tags" aria-label="주의할 재배 시기">{stages.map((code) => <span key={code}>{stageLabels[code] ?? code}</span>)}</div><dl><div><dt>처음 보이는 모습</dt><dd>{guide.symptom_summary}</dd></div><div><dt>잘 생기는 때</dt><dd>{guide.risk_summary}</dd></div><div><dt>평소 관리</dt><dd>{guide.prevention_summary}</dd></div><div><dt>발견했을 때</dt><dd>{guide.response_summary}</dd></div></dl><a href={guide.source_url} rel="noreferrer" target="_blank">{guide.source_title}에서 자세히 보기</a></article>;
      })}</div>}
      <div className="guide-official-link"><div><strong>방제 제품을 사용하기 전에</strong><span>딸기와 해당 병해충에 지금 등록된 제품인지, 사용 시기와 수확 전 안전기간을 확인해 주세요.</span></div><a href="https://psis.rda.go.kr/psis/index.ps" rel="noreferrer" target="_blank">농촌진흥청 농약안전정보에서 확인</a></div>
    </div>
  );
}
