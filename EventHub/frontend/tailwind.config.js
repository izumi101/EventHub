/**
 * A design token as a Tailwind colour that also takes an opacity modifier.
 *
 * The tokens in styles.css are plain hex values behind CSS variables, so Tailwind
 * cannot split them into channels: a bare 'var(--x)' string makes every
 * `bg-primary/10`, `border-primary/30`, `text-muted-foreground/40`… generate NO
 * rule at all (the class silently does nothing). As a function, Tailwind hands us
 * the opacity and we mix the token with transparent instead. Without a modifier
 * the plain variable is returned, so nothing else changes.
 */
const token =
  (cssVar) =>
  ({ opacityValue }) => {
    if (opacityValue === undefined || String(opacityValue).startsWith('var(')) {
      return `var(${cssVar})`;
    }
    return `color-mix(in srgb, var(${cssVar}) calc(${opacityValue} * 100%), transparent)`;
  };

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      /* CSS-vars bridge — every colour comes from the tokens in styles.css */
      colors: Object.fromEntries(
        Object.entries({
          background: '--background',
          foreground: '--foreground',
          surface: '--surface',
          'surface-sunken': '--surface-sunken',
          'surface-elevated': '--surface-elevated',
          card: '--card',
          'card-foreground': '--card-foreground',
          popover: '--popover',
          'popover-foreground': '--popover-foreground',
          primary: '--primary',
          'primary-hover': '--primary-hover',
          'primary-foreground': '--primary-foreground',
          secondary: '--secondary',
          'secondary-foreground': '--secondary-foreground',
          'secondary-text': '--text-secondary',
          muted: '--muted',
          'muted-foreground': '--muted-foreground',
          accent: '--accent',
          'accent-foreground': '--accent-foreground',
          'accent-text': '--accent-text',
          destructive: '--destructive',
          'destructive-foreground': '--destructive-foreground',
          success: '--success',
          'success-foreground': '--success-foreground',
          warning: '--warning',
          'warning-foreground': '--warning-foreground',
          ember: '--ember-500',
          pine: '--pine-500',
          border: '--border',
          'border-strong': '--border-strong',
          input: '--input',
          ring: '--ring',
        }).map(([name, cssVar]) => [name, token(cssVar)]),
      ),

      /* Ember as TEXT must pass AA: #E8643A on paper is only 3.1:1, so text-primary /
         text-ember / text-accent use the darker (light) or lighter (dark) accent-text.
         Fills (bg-primary, border-ember, ring-ember…) keep the brand orange. */
      textColor: {
        primary: token('--accent-text'),
        ember: token('--accent-text'),
        accent: token('--accent-text'),
      },

      fontFamily: {
        sans: ['Onest', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        display: ['Onest', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },

      borderRadius: {
        DEFAULT: 'var(--radius)',
        sm: 'var(--radius-sm)' /* 8px  */,
        md: '10px',
        lg: 'var(--radius)' /* 14px */,
        xl: 'var(--radius-lg)' /* 20px */,
        '2xl': '1.5rem',
        '3xl': '2rem',
        full: '9999px',
      },

      boxShadow: {
        xs: 'var(--shadow-xs)',
        sm: 'var(--shadow-sm)',
        card: 'var(--shadow-card)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        pop: 'var(--shadow-pop)',
      },

      /* Тонкая типографическая шкала */
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
    },
  },
  plugins: [],
};
