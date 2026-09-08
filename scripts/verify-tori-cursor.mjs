import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const source = JSON.parse(await readFile(new URL('vendor/tori-ui/source.json', root), 'utf8'));
for (const file of source.files) {
  const bytes = await readFile(new URL(`vendor/tori-ui/${file.path}`, root));
  const hash = createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
  assert.equal(hash, file.gitBlobSha, `${file.path}: restore the shared source instead of changing it per product`);
}

const theme = (await readFile(new URL('app/ui/tori/cursor-theme.css', root), 'utf8')).replace(/\/\*[\s\S]*?\*\//g, '');
assert.ok(!theme.includes('@'), 'Product cursor theme must not replace shared media queries or animation');
const allowed = new Set(['fill', 'stroke', 'color', 'background', 'background-color', 'border-color']);
for (const match of theme.matchAll(/\{([^{}]*)\}/g)) {
  for (const declaration of match[1].split(';').filter((value) => value.trim())) {
    const [property, ...rest] = declaration.split(':');
    assert.ok(allowed.has(property.trim()), `Non-color cursor override: ${property.trim()}`);
    assert.match(rest.join(':').trim(), /^var\(--tori-[a-z-]+\)$/, 'Use the Nongtori theme palette only');
  }
}
console.log('TORI cursor: 2 upstream files verified; Nongtori overrides colors only.');
