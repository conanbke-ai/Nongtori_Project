'use client';

import { useEffect, useRef, useState } from 'react';

const stages = [
  { title: '영상 수신', detail: '로봇 카메라 또는 저장 영상을 불러옵니다.' },
  { title: '프레임 추출', detail: '촬영 시각을 기준으로 분석할 화면을 자동 분리합니다.' },
  { title: '품질 선별', detail: '흔들림·가림·중복 프레임을 먼저 제외합니다.' },
  { title: '과실·잎 판별', detail: '등급·후숙도와 응애 재확인 후보를 분석합니다.' },
  { title: '구역별 정리', detail: '연속 프레임을 한 사건으로 묶어 농민에게 보여줍니다.' },
];

export function RobotMonitor() {
  const [running, setRunning] = useState(false);
  const [active, setActive] = useState(-1);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearInterval(timer.current);
  }, []);

  function startDemo() {
    if (timer.current) clearInterval(timer.current);
    setRunning(true);
    setActive(0);
    let step = 0;
    timer.current = setInterval(() => {
      step += 1;
      if (step >= stages.length) {
        if (timer.current) clearInterval(timer.current);
        timer.current = null;
        setRunning(false);
        setActive(stages.length);
        return;
      }
      setActive(step);
    }, 720);
  }

  return (
    <section className="analysis-panel" id="video-analysis">
      <div className="section-heading inverse">
        <div><p className="kicker">자동 영상 분석</p><h2>영상 한 번, 결과는 구역별로.</h2></div>
        <p>영상 세션과 프레임 번호는 서버가 자동 생성합니다. 농민이 잎 번호나 페어링 번호를 입력할 일은 없습니다.</p>
      </div>

      <div className="analysis-layout">
        <div className="pipeline" aria-label="영상 분석 처리 단계">
          {stages.map((stage, index) => {
            const state = active > index ? 'done' : active === index ? 'active' : '';
            return (
              <div className={`pipeline-step ${state}`} key={stage.title}>
                <span aria-hidden="true">{state === 'done' ? '✓' : index + 1}</span>
                <div><strong>{stage.title}</strong><p>{stage.detail}</p></div>
              </div>
            );
          })}
        </div>

        <aside className="analysis-result" aria-live="polite">
          <span className="demo-chip">기능 흐름 시연</span>
          <h3>{active < 0 ? '아직 시작하지 않았습니다.' : active >= stages.length ? '구역 요약 준비 완료' : stages[active].title}</h3>
          <p>{active < 0
            ? '버튼을 누르면 영상이 들어온 뒤 결과가 정리되는 과정을 확인할 수 있습니다.'
            : active >= stages.length
              ? '실제 운영에서는 농장·하우스·베드·구역 정보와 자동으로 연결됩니다.'
              : stages[active].detail}</p>
          <div className="result-rule">
            <strong>화면 표시 원칙</strong>
            <p>프레임 수백 장을 그대로 보여주지 않고, 같은 대상의 연속 판정을 한 건으로 묶습니다.</p>
          </div>
          <button disabled={running} onClick={startDemo} type="button">
            {running ? '분석 흐름 확인 중…' : '영상 분석 흐름 보기'}
          </button>
          <small>실제 카메라 영상이나 AI 판정값이 아닌 서비스 흐름 시연입니다.</small>
        </aside>
      </div>
    </section>
  );
}
