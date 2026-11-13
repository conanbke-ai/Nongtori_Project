// 기존 접수 API의 합계 제한. 형식/내용의 최종 판단은 서버가 수행한다.
export const MAX_CAPTURE_TOTAL_BYTES = 40 * 1024 * 1024;

export type CaptureFileIssue = 'fileRequired' | 'fileImage' | 'fileSize';
type FileMetadata = Pick<File, 'size' | 'type'>;

// 브라우저가 이미 아는 오류만 사전 안내한다. 빈 MIME/확장자는 거부 근거가 아니다.
export function captureFileIssue(rgb: FileMetadata | null, thermal: FileMetadata | null): CaptureFileIssue | null {
  if (!rgb || rgb.size === 0) return 'fileRequired';
  const files = [rgb, ...(thermal && thermal.size > 0 ? [thermal] : [])];
  if (files.some(file => file.type !== '' && !file.type.startsWith('image/'))) return 'fileImage';
  if (files.reduce((sum, file) => sum + file.size, 0) > MAX_CAPTURE_TOTAL_BYTES) return 'fileSize';
  return null;
}
