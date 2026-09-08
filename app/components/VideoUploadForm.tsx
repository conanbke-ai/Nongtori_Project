'use client';

import { FormEvent, useEffect, useState } from 'react';
import { translate, type Language } from '@/app/lib/i18n';

type LocationOption = { id: string; label: string };
type FarmStructure = {
  id: string;
  houses: Array<{
    name: string;
    beds: Array<{ name: string; zones: Array<{ id: string; name: string }> }>;
  }>;
};

export function VideoUploadForm({
  farmId,
  itemId,
  language,
  onUploaded,
}: {
  farmId: string;
  itemId: string;
  language: Language;
  onUploaded: () => void;
}) {
  const [state, setState] = useState<{ kind: 'idle' | 'sending' | 'success' | 'error'; message: string }>({ kind: 'idle', message: '' });
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [zoneId, setZoneId] = useState('');
  const [locationsLoading, setLocationsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setLocationsLoading(true);
      setLocations([]);
      setZoneId('');
    });
    fetch('/api/farm-structure', { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error('FARM_STRUCTURE_UNAVAILABLE');
        return await response.json() as { farms?: FarmStructure[] };
      })
      .then((result) => {
        if (!active) return;
        const farm = (result.farms ?? []).find((candidate) => candidate.id === farmId);
        const nextLocations = (farm?.houses ?? []).flatMap((house) => house.beds.flatMap((bed) => (
          bed.zones.map((zone) => ({ id: zone.id, label: `${house.name} · ${bed.name} · ${zone.name}` }))
        )));
        setLocations(nextLocations);
        setZoneId(nextLocations.length === 1 ? nextLocations[0].id : '');
      })
      .catch(() => active && setLocations([]))
      .finally(() => active && setLocationsLoading(false));
    return () => { active = false; };
  }, [farmId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setState({ kind: 'sending', message: translate(language, 'upload.videoSending') });
    try {
      const body = new FormData(form);
      body.set('farmId', farmId);
      body.set('itemId', itemId);
      body.set('zoneId', zoneId);
      const response = await fetch('/api/video-upload', { method: 'POST', body });
      await response.json();
      if (!response.ok) throw new Error(translate(language, 'upload.videoError'));
      form.reset();
      setZoneId(locations.length === 1 ? locations[0].id : '');
      setState({ kind: 'success', message: translate(language, 'upload.videoSuccess') });
      onUploaded();
    } catch (error) {
      setState({ kind: 'error', message: error instanceof Error ? error.message : translate(language, 'upload.videoError') });
    }
  }

  return (
    <form className="video-upload-form" onSubmit={submit}>
      <label><span>{translate(language, 'upload.location')} <b>{translate(language, 'upload.required')}</b></span><select disabled={locationsLoading || locations.length === 0} name="zoneId" onChange={(event) => setZoneId(event.target.value)} required value={zoneId}><option value="">{translate(language, locationsLoading ? 'upload.locationLoading' : locations.length ? 'upload.locationSelect' : 'upload.locationUnavailable')}</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.label}</option>)}</select></label>
      <p className="video-location-help">{translate(language, 'upload.locationHelp')}</p>
      <label><span>{translate(language, 'upload.rgb')} <b>{translate(language, 'upload.required')}</b></span><input accept="video/*" name="rgbVideo" required type="file" /></label>
      <label><span>{translate(language, 'upload.thermal')} <small>{translate(language, 'common.optional')}</small></span><input accept="video/*" name="thermalVideo" type="file" /></label>
      <p>{translate(language, 'upload.videoHelp')}</p>
      <button disabled={!farmId || !zoneId || state.kind === 'sending'} type="submit">{state.kind === 'sending' ? translate(language, 'common.loading') : translate(language, 'upload.submit')}</button>
      {state.kind !== 'idle' && <div className={`upload-status ${state.kind}`} role="status">{state.message}</div>}
    </form>
  );
}
