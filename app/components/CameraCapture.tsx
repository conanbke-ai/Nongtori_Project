'use client';

import Image from 'next/image';
import { ChangeEvent, useEffect, useRef, useState } from 'react';

export function CameraCapture({
  farmId,
  cultivarCode,
  cultivarName,
  enabled,
  onUploaded,
}: {
  farmId: string;
  cultivarCode: string;
  cultivarName: string;
  enabled: boolean;
  onUploaded: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [preview, setPreview] = useState('');
  const [state, setState] = useState<{ kind: 'idle' | 'sending' | 'success' | 'error'; message: string }>({ kind: 'idle', message: '' });

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function setPhotoBlob(blob: Blob) {
    if (preview) URL.revokeObjectURL(preview);
    setPhoto(blob);
    setPreview(URL.createObjectURL(blob));
  }

  async function openCamera() {
    if (!enabled) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = stream;
      setCameraOpen(true);
      requestAnimationFrame(() => {
        if (videoRef.current) videoRef.current.srcObject = stream;
      });
      setState({ kind: 'idle', message: '' });
    } catch {
      setState({ kind: 'error', message: '카메라 권한을 허용하거나 사진 파일을 선택해 주세요.' });
    }
  }

  function closeCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraOpen(false);
  }

  function capture() {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) return;
      setPhotoBlob(blob);
      closeCamera();
    }, 'image/jpeg', .92);
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) setPhotoBlob(file);
  }

  function retake() {
    if (preview) URL.revokeObjectURL(preview);
    setPhoto(null);
    setPreview('');
    setState({ kind: 'idle', message: '' });
  }

  async function upload() {
    if (!photo) return;
    setState({ kind: 'sending', message: '사진을 접수하고 있습니다…' });
    const body = new FormData();
    body.set('cultivar', cultivarCode);
    body.set('farmId', farmId);
    body.set('image', new File([photo], `capture-${Date.now()}.jpg`, { type: photo.type || 'image/jpeg' }));
    try {
      const response = await fetch('/api/fruit-assessments', { method: 'POST', body });
      const result = await response.json() as { error?: string; message?: string };
      if (!response.ok) throw new Error(result.error ?? '사진 접수에 실패했습니다.');
      setState({ kind: 'success', message: result.message ?? '사진을 접수했습니다.' });
      onUploaded();
    } catch (error) {
      setState({ kind: 'error', message: error instanceof Error ? error.message : '사진 접수에 실패했습니다.' });
    }
  }

  return (
    <div className={`camera-capture ${!enabled ? 'disabled' : ''}`}>
      {!enabled && <div className="unsupported-item"><strong>이 품종은 아직 사진 판독을 할 수 없습니다.</strong><p>충분한 사진과 판독 기준이 준비되면 촬영 버튼을 사용할 수 있습니다.</p></div>}
      {enabled && !cameraOpen && !preview && (
        <div className="camera-start">
          <span aria-hidden="true">◎</span><strong>{cultivarName} 후숙도·등급 판독</strong><p>수확한 과실 하나가 화면에 크게 보이도록 촬영해 주세요.</p>
          <button onClick={openCamera} type="button">카메라 열기</button>
          <label>앨범에서 선택<input accept="image/*" capture="environment" onChange={chooseFile} type="file" /></label>
        </div>
      )}
      {enabled && cameraOpen && (
        <div className="camera-live">
          <video autoPlay muted playsInline ref={videoRef} />
          <div><button className="cancel-camera" onClick={closeCamera} type="button">취소</button><button className="shutter" aria-label="사진 촬영" onClick={capture} type="button" /></div>
        </div>
      )}
      {enabled && preview && (
        <div className="capture-preview">
          <Image alt="촬영한 과실" height={720} src={preview} unoptimized width={960} />
          <div><button onClick={retake} type="button">다시 촬영</button><button disabled={state.kind === 'sending' || state.kind === 'success'} onClick={upload} type="button">{state.kind === 'sending' ? '접수 중…' : '이 사진 접수'}</button></div>
        </div>
      )}
      {state.kind !== 'idle' && <div className={`upload-status ${state.kind}`} role="status">{state.message}</div>}
    </div>
  );
}
