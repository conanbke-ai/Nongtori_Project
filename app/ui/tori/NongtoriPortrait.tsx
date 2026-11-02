import Image from 'next/image';
import './portrait.css';

const portraitSources = {
  default: '/nongtori-character-open-eyes.png',
  wink: '/nongtori-character-wink.png',
} as const;

type NongtoriPortraitVariant = keyof typeof portraitSources;

/** Full-size approved artwork; identity thumbnails and face crops are separate assets. */
export function NongtoriPortrait({ alt, variant = 'default' }: { alt: string; variant?: NongtoriPortraitVariant }) {
  return <Image alt={alt} className="nongtori-portrait" width={1254} height={1254} priority unoptimized src={portraitSources[variant]} />;
}
