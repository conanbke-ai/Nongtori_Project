export type PestCapturePhoto = { file: File; modality: 'LEAF_RGB' | 'LEAF_THERMAL' };
export type PestCaptureAsset = PestCapturePhoto & { id: string; key: string };
export type PestCaptureSession = {
  sessionId: string;
  farmId: string;
  itemId: string | null;
  pestCode: string;
  createdAt: string;
  assets: PestCaptureAsset[];
};

export interface PestCaptureRepositoryPort {
  hasActiveFarm(farmId: string): Promise<boolean>;
  hasActiveItem(farmId: string, itemId: string): Promise<boolean>;
  save(session: PestCaptureSession): Promise<void>;
}

export interface PestCaptureStoragePort {
  keyFor(input: { farmId: string; pestCode: string; sessionId: string; photo: PestCapturePhoto }): string;
  put(sessionId: string, asset: PestCaptureAsset): Promise<void>;
  remove(key: string): Promise<void>;
}

type PestCaptureResult =
  | { kind: 'FARM_NOT_FOUND' | 'UPLOAD_FORBIDDEN' | 'ITEM_NOT_FOUND' }
  | { kind: 'RECEIVED'; sessionId: string; photoCount: number };

export async function recordPestCapture(
  { farmId, itemId, pestCode, photos }: { farmId: string; itemId: string | null; pestCode: string; photos: PestCapturePhoto[] },
  { repository, storage, canUpload }: {
    repository: PestCaptureRepositoryPort;
    storage: PestCaptureStoragePort;
    canUpload: (farmId: string) => Promise<boolean>;
  },
): Promise<PestCaptureResult> {
  if (!await repository.hasActiveFarm(farmId)) return { kind: 'FARM_NOT_FOUND' };
  if (!await canUpload(farmId)) return { kind: 'UPLOAD_FORBIDDEN' };
  if (itemId && !await repository.hasActiveItem(farmId, itemId)) return { kind: 'ITEM_NOT_FOUND' };

  const sessionId = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  const assets = photos.map(photo => ({
    ...photo,
    id: crypto.randomUUID(),
    key: storage.keyFor({ farmId, pestCode, sessionId, photo }),
  }));
  try {
    // Wait for every put before attempting cleanup. A rejected put can still
    // have stored an object if its acknowledgement was lost.
    const uploads = await Promise.allSettled(assets.map(async asset => storage.put(sessionId, asset)));
    const failure = uploads.find(upload => upload.status === 'rejected');
    if (failure) throw failure.reason;
    await repository.save({ sessionId, farmId, itemId, pestCode, createdAt, assets });
    return { kind: 'RECEIVED', sessionId, photoCount: assets.length };
  } catch (error) {
    // The D1 batch and R2 puts have separate commit boundaries.
    await Promise.allSettled(assets.map(async asset => storage.remove(asset.key)));
    throw error;
  }
}
