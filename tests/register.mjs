import { registerHooks } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import ts from 'typescript';
const root = path.resolve(import.meta.dirname, '..');
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === 'cloudflare:workers') return { url: 'test:cloudflare', shortCircuit: true };
    if (specifier === 'next/server') specifier = 'next/server.js';
    if (specifier.startsWith('@/') || specifier.startsWith('.')) {
      const base = specifier.startsWith('@/') ? path.join(root, specifier.slice(2)) : path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier);
      for (const suffix of ['', '.ts', '.tsx', '/index.ts']) {
        if (existsSync(base + suffix) && /\.(ts|tsx|mjs)$/.test(base + suffix)) return { url: pathToFileURL(base + suffix).href, shortCircuit: true };
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url === 'test:cloudflare') return { format: 'module', source: 'export const env = globalThis.nongtoriTestEnv;', shortCircuit: true };
    if (/\.(ts|tsx)$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText };
    return nextLoad(url, context);
  },
});
