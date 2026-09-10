'use client';

import { useEffect, useState } from 'react';
import { translate, type Language } from '@/app/lib/i18n';

type Farm = {
  id: string;
  name: string;
  cultivars: { code: string; name: string }[];
  houses: {
    id: string;
    name: string;
    beds: { id: string; name: string; zones: { id: string; name: string }[] }[];
  }[];
  cameras: { id: string; name: string; camera_type: string; source_type: string; status: string }[];
};

type FarmItemSummary = { id: string; crop_name: string; cultivar_name: string | null; display_name: string };

export function FarmStatus({ farmId, items, language }: { farmId: string; items: FarmItemSummary[]; language: Language }) {
  const [farms, setFarms] = useState<Farm[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    fetch('/api/farm-structure')
      .then((response) => response.ok ? response.json() : Promise.reject(new Error('load failed')))
      .then((data: unknown) => {
        const payload = data as { farms?: unknown };
        setFarms(Array.isArray(payload.farms) ? payload.farms as Farm[] : []);
      })
      .catch(() => {
        setFarms([]);
        setLoadFailed(true);
      })
      .finally(() => setLoading(false));
  }, [retryCount]);

  const farm = farms.find((item) => item.id === farmId) ?? null;
  const beds = farm?.houses.reduce((count, house) => count + house.beds.length, 0) ?? 0;
  const zones = farm?.houses.reduce(
    (count, house) => count + house.beds.reduce((bedCount, bed) => bedCount + bed.zones.length, 0),
    0,
  ) ?? 0;

  if (loading) return <p className="status-loading">{translate(language, 'management.loadingStructure')}</p>;
  if (loadFailed) return <div className="farm-status-error" role="alert"><strong>{translate(language, 'management.loadFailed')}</strong><p>{translate(language, 'management.loadFailedHelp')}</p><button onClick={() => { setLoading(true); setLoadFailed(false); setRetryCount((count) => count + 1); }} type="button">{translate(language, 'common.retry')}</button></div>;
  if (!farm) {
    return (
      <div className="setup-empty">
        <span>{translate(language, 'management.setupWaiting')}</span>
        <strong>{translate(language, 'management.setupNeeded')}</strong>
        <p>{translate(language, 'management.setupHelp')}</p>
      </div>
    );
  }

  return (
    <section className="farm-status-panel">
      <header className="management-section-heading">
        <div><span>{translate(language, 'management.farmOverview')}</span><h2>{farm.name}</h2></div>
        <b>{translate(language, 'data.readOnly')}</b>
      </header>
      <div className="farm-live-status">
        <div><span>{translate(language, 'management.currentFarm')}</span><strong>{farm.name}</strong></div>
        <div><span>{translate(language, 'management.registeredItems')}</span><strong>{translate(language, 'management.itemCount', { count: items.length })}</strong></div>
        <div><span>{translate(language, 'management.operationStructure')}</span><strong>{translate(language, 'management.structureCount', { houses: farm.houses.length, beds, zones })}</strong></div>
        <div><span>{translate(language, 'management.registeredDevices')}</span><strong>{translate(language, 'management.cameraCount', { count: farm.cameras.length })}</strong></div>
      </div>
      <div className="farm-item-list">
        <strong>{translate(language, 'management.registeredItems')}</strong>
        <div>{items.length === 0 ? <span>{translate(language, 'management.noItems')}</span> : items.map((item) => <span key={item.id}><b>{item.crop_name}</b><small>{item.cultivar_name ?? item.display_name}</small></span>)}</div>
      </div>
      <div className="farm-structure-list">
        {farm.houses.length === 0 ? <p>{translate(language, 'management.noStructure')}</p> : farm.houses.map((house) => {
          const houseZones = house.beds.reduce((count, bed) => count + bed.zones.length, 0);
          return <article key={house.id}>
            <header><h3>{house.name}</h3><span>{translate(language, 'management.houseCount', { beds: house.beds.length, zones: houseZones })}</span></header>
            <div>{house.beds.map((bed) => <span key={bed.id}><b>{bed.name}</b><small>{translate(language, 'management.zoneCount', { count: bed.zones.length })}</small></span>)}</div>
          </article>;
        })}
      </div>
      <div className="farm-device-list">
        <strong>{translate(language, 'management.registeredDevices')}</strong>
        <div>{farm.cameras.length === 0 ? <span>{translate(language, 'management.noDevices')}</span> : farm.cameras.map((camera) => <span key={camera.id}><b>{camera.name}</b><small>{camera.source_type === 'ROBOT' ? translate(language, 'management.robotCamera') : translate(language, 'management.savedMediaCamera')}</small></span>)}</div>
      </div>
      <p className="data-scope-note"><strong>{translate(language, 'management.vendorManaged')}</strong> {translate(language, 'management.vendorManagedHelp')}</p>
    </section>
  );
}
