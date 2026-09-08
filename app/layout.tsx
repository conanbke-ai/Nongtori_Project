import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://seolhyang-mite-scout.conanbke.chatgpt.site'),
  title: '농토리 운영센터',
  description: '농장별 작물·품종의 영상 판독, 응애 예찰, 수확 이력과 예상 수익을 관리하는 현장 앱',
  icons: { icon: '/nongtori-app-icon-512.png', apple: '/nongtori-app-icon-512.png' },
  appleWebApp: { capable: true, statusBarStyle: 'default', title: '농토리 운영센터' },
  openGraph: {
    title: '농토리 운영센터',
    description: '영상 판독 · 응애 예찰 · 수확 이력',
    images: [{ url: '/nongtori-social-card-v1.jpg', width: 1200, height: 627, alt: '농토리 운영센터' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: '농토리 운영센터',
    description: '영상 판독 · 응애 예찰 · 수확 이력',
    images: ['/nongtori-social-card-v1.jpg'],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
