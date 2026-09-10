import { ImageResponse } from 'next/og';

export const size = { width: 512, height: 512 };
export const contentType = 'image/png';

export default function Icon() {
  return new ImageResponse(
    <div style={{
      width: '100%',
      height: '100%',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#1f3f7a',
      color: '#ffffff',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 24, height: 210 }}>
        <div style={{ width: 72, height: 120, borderRadius: 22, background: '#ffffff' }} />
        <div style={{ width: 72, height: 210, borderRadius: 22, background: '#ffffff' }} />
        <div style={{ width: 72, height: 165, borderRadius: 22, background: '#9fb8ff' }} />
      </div>
    </div>,
    size,
  );
}
