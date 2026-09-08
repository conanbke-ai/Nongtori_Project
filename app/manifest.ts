import type { MetadataRoute } from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: '농토리 운영센터',
    short_name: '농토리',
    description: '작물·품종별 영상 판독, 응애 예찰, 수확 이력과 예상 수익을 관리하는 현장 앱',
    start_url: '/',
    display: 'standalone',
    orientation: 'portrait-primary',
    scope: '/',
    background_color: '#f5f6f1',
    theme_color: '#315f3d',
    lang: 'ko',
    categories: ['business', 'productivity', 'utilities'],
    icons: [
      { src: '/nongtori-app-icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
    ],
    shortcuts: [
      { name: '영상 판독', short_name: '판독', url: '/?screen=capture', icons: [{ src: '/nongtori-app-icon-512.png', sizes: '512x512', type: 'image/png' }] },
      { name: '응애 예찰', short_name: '예찰', url: '/?screen=alerts', icons: [{ src: '/nongtori-app-icon-512.png', sizes: '512x512', type: 'image/png' }] },
    ],
  };
}
