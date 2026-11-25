import type { PestCaptureAsset, PestCapturePhoto, PestCaptureStoragePort } from '../application/pest-capture-service';

export class R2PestCaptureStorage implements PestCaptureStoragePort {
  constructor(private readonly bucket: R2Bucket) {}

  keyFor({ farmId, pestCode, sessionId, photo }: { farmId: string; pestCode: string; sessionId: string; photo: PestCapturePhoto }) {
    const extension = photo.file.name.toLowerCase().match(/\.([a-z0-9]{1,8})$/)?.[1] ?? 'jpg';
    return `direct/${farmId}/pest/${pestCode}/${sessionId}/${photo.modality}-${crypto.randomUUID()}.${extension}`;
  }

  async put(sessionId: string, asset: PestCaptureAsset) {
    await this.bucket.put(asset.key, asset.file.stream(), {
      httpMetadata: { contentType: asset.file.type },
      customMetadata: { captureSessionId: sessionId, modality: asset.modality, originalName: asset.file.name },
    });
  }

  async remove(key: string) {
    await this.bucket.delete(key);
  }
}
