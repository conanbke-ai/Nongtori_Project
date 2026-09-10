import Image from 'next/image';
import './portrait.css';

/** Full-size standard artwork; the 192px identity thumbnail is not a hero image. */
export function NongtoriPortrait({ alt }: { alt: string }) {
  return <Image alt={alt} className="nongtori-portrait" width={720} height={1080} priority unoptimized src="/nongtori-focus-v1.jpg" />;
}
