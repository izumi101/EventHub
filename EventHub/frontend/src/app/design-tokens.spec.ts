import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Guards the design tokens in styles.css: both themes define the same colour
 * tokens, and the text/background pairs the UI relies on pass WCAG AA (4.5:1).
 */
const css = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8');

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`No ${selector} block in styles.css`);
  const body = css.slice(start, css.indexOf('\n}', start));
  const tokens: Record<string, string> = {};
  for (const m of body.matchAll(/(--[\w-]+):\s*([^;]+);/g)) tokens[m[1]] = m[2].trim();
  return tokens;
}

const light = block(':root');
const dark = block('.dark');

/** Tokens that are theme-independent and live only in :root. */
const SHARED = /^--(radius|font-)/;

function resolveColor(theme: Record<string, string>, name: string): string {
  let value = theme[name] ?? light[name];
  for (let i = 0; i < 5 && value.startsWith('var('); i++) {
    const ref = value.slice(4, -1);
    value = theme[ref] ?? light[ref];
  }
  return value;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe('design tokens', () => {
  it('defines every colour token in both themes', () => {
    const lightColours = Object.keys(light).filter((k) => !SHARED.test(k));
    expect(lightColours.length).toBeGreaterThan(30);
    expect(lightColours.filter((k) => !(k in dark))).toEqual([]);
    expect(Object.keys(dark).filter((k) => !(k in light))).toEqual([]);
  });

  const textOnSurfaces = [
    '--foreground',
    '--text-secondary',
    '--muted-foreground',
    '--accent-text',
    '--destructive',
    '--pine-600',
    '--zone-vip',
    '--zone-premium',
  ];
  const surfaces = ['--background', '--card', '--muted'];
  const filled: [string, string][] = [
    ['--primary-foreground', '--primary'],
    ['--primary-foreground', '--primary-hover'],
    ['--success-foreground', '--success'],
    ['--warning-foreground', '--warning'],
    ['--destructive-foreground', '--destructive'],
  ];

  describe.each([
    ['light', light],
    ['dark', dark],
  ])('%s theme contrast', (_name, theme) => {
    it('keeps text on every surface at AA (4.5:1)', () => {
      const failing: string[] = [];
      for (const fg of textOnSurfaces) {
        for (const bg of surfaces) {
          const ratio = contrast(resolveColor(theme, fg), resolveColor(theme, bg));
          if (ratio < 4.5) failing.push(`${fg} on ${bg}: ${ratio.toFixed(2)}`);
        }
      }
      expect(failing).toEqual([]);
    });

    it('keeps filled buttons and pills at AA (4.5:1)', () => {
      const failing = filled
        .map(
          ([fg, bg]) =>
            [fg, bg, contrast(resolveColor(theme, fg), resolveColor(theme, bg))] as const,
        )
        .filter(([, , ratio]) => ratio < 4.5)
        .map(([fg, bg, ratio]) => `${fg} on ${bg}: ${ratio.toFixed(2)}`);
      expect(failing).toEqual([]);
    });
  });
});
