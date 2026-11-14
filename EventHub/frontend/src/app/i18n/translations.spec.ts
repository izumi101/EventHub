import en from '../../assets/i18n/en.json';
import kk from '../../assets/i18n/kk.json';
import ru from '../../assets/i18n/ru.json';

interface Tree {
  [key: string]: string | Tree;
}

function flatten(tree: Tree, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') out[path] = value;
    else Object.assign(out, flatten(value, path));
  }
  return out;
}

const params = (text: string) => [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();

const source = flatten(en);

/** Keeps every language file in step with English (the source of truth). */
describe.each([
  ['ru', flatten(ru)],
  ['kk', flatten(kk)],
])('translations (%s)', (_name, other) => {
  it('has exactly the keys of en.json', () => {
    const missing = Object.keys(source).filter((k) => !(k in other));
    const extra = Object.keys(other).filter((k) => !(k in source));
    expect({ missing, extra }).toEqual({ missing: [], extra: [] });
  });

  it('has no empty strings', () => {
    expect(
      Object.entries(other)
        .filter(([, v]) => !v.trim())
        .map(([k]) => k),
    ).toEqual([]);
  });

  it('uses the same {{ params }} as English', () => {
    const mismatched = Object.keys(source).filter(
      (k) => k in other && params(source[k]).join() !== params(other[k]).join(),
    );
    expect(mismatched).toEqual([]);
  });
});
