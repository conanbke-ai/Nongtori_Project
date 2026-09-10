'use client';

import { findPestTarget, pestLabel, type PestLanguage } from '../domain/catalog';
import { pestText } from './text';

export type PestCount = { code: string; openCount: number };
export type OverviewState = 'ready' | 'loading' | 'unlinked' | 'error';

export function activePestSummary(targets: readonly PestCount[], language: PestLanguage) {
  const labels = targets.filter((target) => target.openCount > 0).map((target) => pestLabel(target.code, language));
  return labels.length ? labels.join(' · ') : pestText(language, 'all');
}

function PestKindIcon({ kind }: { kind: string }) {
  return (
    <svg viewBox="0 0 32 32" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {kind === 'DISEASE' ? <><path d="M26 5C11 4 4 10 6 20c2 10 21 10 20-15Z" /><path d="m7 25 15-15M12 20l-1-6m6 1 6 1" /></>
        : kind === 'PEST' ? <><rect x="10" y="11" width="12" height="16" rx="6" /><path d="M12 11V9a4 4 0 0 1 8 0v2M16 12v14M10 16l-5-3m5 7H4m6 3-5 4m17-11 5-3m-5 7h6m-6 3 5 4M13 6l-2-3m8 3 2-3" /></>
          : <><circle cx="16" cy="16" r="11" /><path d="M13 12a3 3 0 1 1 5 2c-2 1-2 2-2 4m0 4h.01" /></>}
    </svg>
  );
}

export function PestOverviewCard({ targets, total, language, state, onSelect }: {
  targets: readonly PestCount[];
  total: number;
  language: PestLanguage;
  state: OverviewState;
  onSelect: (code?: string) => void;
}) {
  const ready = state === 'ready';
  return (
    <article className={`pest-overview-card ${ready && total > 0 ? 'has-alerts' : ''}`} aria-busy={state === 'loading'}>
      <header className="pest-overview-heading">
        <div><span className="overview-eyebrow">{pestText(language, 'fieldScout')}</span><h2>{pestText(language, 'managementTitle')}</h2></div>
        <span className="overview-section-icon"><PestKindIcon kind="DISEASE" /></span>
      </header>
      <p className="pest-overview-intro">{pestText(language, 'overviewIntro')}</p>
      <div className="pest-overview-grid" role="group" aria-label={pestText(language, 'target')}>
        {targets.map((target) => {
          const kind = findPestTarget(target.code)?.kind ?? 'UNIDENTIFIED';
          return (
            <button key={target.code} className={`pest-overview-target ${kind.toLowerCase()} ${ready && target.openCount > 0 ? 'needs-review' : ''}`} disabled={!ready} onClick={() => onSelect(target.code)} type="button">
              <span className="pest-kind-symbol"><PestKindIcon kind={kind} /></span>
              <span className="pest-target-name"><small>{pestText(language, kind === 'PEST' ? 'pestKind' : kind === 'DISEASE' ? 'diseaseKind' : 'unknownKind')}</small><strong>{pestLabel(target.code, language)}</strong></span>
              <span className="pest-target-count"><b>{ready ? target.openCount : '—'}</b><small>{pestText(language, 'cases')}</small></span>
            </button>
          );
        })}
      </div>
      <p className="pest-overview-note" role={state === 'error' ? 'alert' : 'status'}>{pestText(language, ready ? 'countBasis' : state === 'unlinked' ? 'farmRequired' : state === 'error' ? 'loadFailed' : 'loading')}</p>
      <footer className="pest-overview-footer">
        <div><span>{pestText(language, 'reviewNeeded')}</span><strong>{ready ? total : '—'}<small>{pestText(language, 'cases')}</small></strong></div>
        <button disabled={!ready} onClick={() => onSelect()} type="button">{pestText(language, 'allRecords')} <span aria-hidden="true">→</span></button>
      </footer>
    </article>
  );
}
