import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

// WCAG sRGB relative luminance. Read the shipped tokens, not a duplicate palette.
const css = readFileSync(new URL('../src/app/globals.css', import.meta.url), 'utf8');
const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[\da-f]{6});/gi)].map(([, name, value]) => [name, value]));
function luminance(hex) {
  const [r, g, b] = hex.slice(1).match(/../g).map(value => parseInt(value, 16) / 255)
    .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return .2126 * r + .7152 * g + .0722 * b;
}
function ratio(a, b) {
  const x = luminance(a), y = luminance(b);
  return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
const surfaces = ['bg', 'surface-raised', 'bg-subtle', 'surface-sunken', 'bg-muted', 'accent-soft', 'success-soft', 'warning-soft', 'danger-soft'];
const rows = [];
for (const token of ['ink', 'ink-2', 'ink-3', 'accent', 'success-ink', 'warning-ink', 'danger', 'focus-ring', 'control-line', 'danger-line']) {
  const minimum = ['focus-ring', 'control-line', 'danger-line'].includes(token) ? 3 : 4.5;
  const row = { token, hex: tokens[token] };
  for (const surface of surfaces) {
    const value = ratio(tokens[token], tokens[surface]);
    assert(value >= minimum, `${token} on ${surface}: ${value.toFixed(2)} < ${minimum}`);
    row[surface] = Number(value.toFixed(2));
  }
  rows.push(row);
}
for (const background of ['ink', 'ink-hover', 'accent', 'danger']) {
  const value = ratio(tokens['on-ink'], tokens[background]);
  assert(value >= 4.5, `on-ink on ${background}: ${value.toFixed(2)}`);
  rows.push({ token: `on-ink / ${background}`, ratio: Number(value.toFixed(2)) });
}
if (process.argv.includes('--json')) console.log(JSON.stringify(rows, null, 2));
else console.table(rows);
