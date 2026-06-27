/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,ts}",
  ],
  theme: {
    extend: {
      /* CSS-vars bridge — все цвета берутся из :root */
      colors: {
        background:           "var(--background)",
        foreground:           "var(--foreground)",
        surface:              "var(--surface)",
        "surface-sunken":     "var(--surface-sunken)",
        card:                 "var(--card)",
        "card-foreground":    "var(--card-foreground)",
        popover:              "var(--popover)",
        "popover-foreground": "var(--popover-foreground)",
        primary:              "var(--primary)",
        "primary-foreground": "var(--primary-foreground)",
        secondary:            "var(--secondary)",
        "secondary-foreground":"var(--secondary-foreground)",
        muted:                "var(--muted)",
        "muted-foreground":   "var(--muted-foreground)",
        accent:               "var(--accent)",
        "accent-foreground":  "var(--accent-foreground)",
        destructive:          "var(--destructive)",
        "destructive-foreground":"var(--destructive-foreground)",
        success:              "var(--success)",
        "success-foreground": "var(--success-foreground)",
        warning:              "var(--warning)",
        "warning-foreground": "var(--warning-foreground)",
        ember:                "var(--ember-500)",
        pine:                 "var(--pine-500)",
        border:               "var(--border)",
        "border-strong":      "var(--border-strong)",
        input:                "var(--input)",
        ring:                 "var(--ring)",
      },

      fontFamily: {
        sans:    ['Satoshi', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Clash Display', 'Satoshi', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono:    ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },

      borderRadius: {
        DEFAULT: "var(--radius)",
        sm:  "var(--radius-sm)",   /* 8px  */
        md:  "10px",
        lg:  "var(--radius)",      /* 14px */
        xl:  "var(--radius-lg)",   /* 20px */
        "2xl": "1.5rem",
        "3xl": "2rem",
        full: "9999px",
      },

      boxShadow: {
        xs:   "var(--shadow-xs)",
        sm:   "var(--shadow-sm)",
        card: "var(--shadow-card)",
        md:   "var(--shadow-md)",
        lg:   "var(--shadow-lg)",
        pop:  "var(--shadow-pop)",
      },

      /* Тонкая типографическая шкала */
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
    },
  },
  plugins: [],
};
