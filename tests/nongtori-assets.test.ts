import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { NongtoriPortrait } from '../app/ui/tori/NongtoriPortrait';

const root = path.resolve(import.meta.dirname, '..');
const approvedAssets = {
  'nongtori-character-open-eyes.png': 'a0497cb496e9ddcecdc56933ad5b5006f0840b9a8fa2224ef09739cc93e4d2e7',
  'nongtori-character-wink.png': '3c17d51755e799853642193317e811452014313009d16e29f90376cd5ad73f96',
  'nongtori-face-open-eyes.png': '8f5e93e6c04dec157fc453e7f82b77d06bd22155f5e64d43923bc13a18bfe529',
  'nongtori-face-wink.png': 'f75e3cf505abeff99e06ddc740141b02355ac0cc4cac276a3c2d7ed9acc3bb01',
} as const;

function sha256(file: string) {
  return createHash('sha256').update(readFileSync(file)).digest('hex');
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(target);
    return /\.(?:css|ts|tsx)$/.test(entry.name) ? [target] : [];
  });
}

test('approved character and face assets keep their canonical hashes in assets and public', () => {
  for (const [name, expectedHash] of Object.entries(approvedAssets)) {
    for (const directory of ['assets', 'public']) {
      assert.equal(sha256(path.join(root, directory, name)), expectedHash, `${directory}/${name} must match the approved source`);
    }
  }
});

test('portrait variants map default and welcome to different approved full-body images', () => {
  const defaultMarkup = renderToStaticMarkup(NongtoriPortrait({ alt: 'default Nongtori' }));
  const winkMarkup = renderToStaticMarkup(NongtoriPortrait({ alt: 'welcome Nongtori', variant: 'wink' }));
  assert.match(defaultMarkup, /src="\/nongtori-character-open-eyes\.png"/);
  assert.match(winkMarkup, /src="\/nongtori-character-wink\.png"/);
  assert.notEqual(defaultMarkup, winkMarkup);

  const auth = readFileSync(path.join(root, 'app/components/AuthGateway.tsx'), 'utf8');
  const dashboard = readFileSync(path.join(root, 'app/components/FarmerDashboard.tsx'), 'utf8');
  assert.match(auth, /<NongtoriPortrait[^>]+variant="wink"/);
  assert.match(dashboard, /<NongtoriPortrait alt=\{translate\(language, 'scout\.alt'\)\} \/>/);

  const winkUsages = sourceFiles(path.join(root, 'app'))
    .flatMap((file) => (readFileSync(file, 'utf8').match(/variant="wink"/g) ?? []).map(() => path.relative(root, file).replaceAll(path.sep, '/')));
  assert.deepEqual(winkUsages, ['app/components/AuthGateway.tsx']);
});

test('runtime source no longer references the obsolete focus JPEG', () => {
  const references = sourceFiles(path.join(root, 'app'))
    .filter((file) => readFileSync(file, 'utf8').includes('nongtori-focus-v1.jpg'));
  assert.deepEqual(references, []);
});
