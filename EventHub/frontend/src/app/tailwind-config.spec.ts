// The Tailwind config is CommonJS; Vite hands it over as the default export.
import config from '../../tailwind.config.js';

type ColorFn = (args: { opacityValue?: string }) => string;
interface TailwindColors {
  theme: { extend: { colors: Record<string, ColorFn>; textColor: Record<string, ColorFn> } };
}

const { colors, textColor } = (config as TailwindColors).theme.extend;

/**
 * Every token colour must accept an opacity modifier (`bg-primary/10`). With a
 * bare 'var(--x)' string Tailwind silently drops the whole class, which left
 * 79 classes in 31 templates without any effect (e.g. invisible chart bars).
 */
describe('tailwind token colours', () => {
  it('turn an opacity modifier into color-mix', () => {
    for (const [name, fn] of Object.entries(colors)) {
      expect(typeof fn, name).toBe('function');
      const mixed = fn({ opacityValue: '0.1' });
      expect(mixed, name).toMatch(
        /^color-mix\(in srgb, var\(--[\w-]+\) calc\(0\.1 \* 100%\), transparent\)$/,
      );
    }
  });

  it('stay the plain variable without a modifier', () => {
    expect(colors['primary']({})).toBe('var(--primary)');
    expect(colors['ember']({ opacityValue: 'var(--tw-bg-opacity)' })).toBe('var(--ember-500)');
  });

  it('keep the accessible text colour for primary, ember and accent text', () => {
    for (const name of ['primary', 'ember', 'accent']) {
      expect(textColor[name]({})).toBe('var(--accent-text)');
    }
  });
});
