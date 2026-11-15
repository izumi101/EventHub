# Design tokens

## Agent Entry

- Purpose: how colour, type and elevation are defined in the SPA, and the rules that keep both themes readable.
- Read when: adding a colour, a status badge, a new page, or touching `styles.css` / `tailwind.config.js`.
- Skip when: backend-only work.
- Canonical: Yes for tokens; the values themselves live in `EventHub/frontend/src/styles.css`.
- Read next: `REDESIGN_PLAN.md` (why the redesign looks the way it does), `I18N.md`.

## Where they live

| File | Holds |
|---|---|
| `frontend/src/styles.css` `:root` | light theme tokens (CSS custom properties) |
| `frontend/src/styles.css` `.dark` | dark theme: the same names, other values (`<html class="dark">`, set by `ThemeService`) |
| `frontend/tailwind.config.js` | maps Tailwind names to the tokens (`bg-card`, `text-muted-foreground`, `border-border`, …); `text-primary`, `text-ember` and `text-accent` resolve to `--accent-text` |
| `frontend/src/app/design-tokens.spec.ts` | guard: every colour token exists in both themes; text tokens pass WCAG AA (4.5:1) on `--background`, `--card` and `--muted`; filled buttons pass AA |

## Tokens

| Group | Tokens | Use |
|---|---|---|
| Surfaces | `--background`, `--card`, `--popover`, `--muted`, `--secondary`, `--surface*` | page, cards, menus, quiet fills |
| Text | `--foreground`, `--text-secondary`, `--muted-foreground` | body, secondary, captions |
| Brand (Ember) | `--ember-50…800`, `--primary`, `--primary-hover`, `--accent`, `--accent-text` | `--ember-500` (#E8643A) for fills, marks and rings; `--accent-text` for orange **text** (darker in light, lighter in dark) |
| Support (Pine) | `--pine-50`, `--pine-500`, `--pine-600` | free, confirmed, live, success |
| Feedback | `--success*`, `--warning`, `--warning-50`, `--warning-text`, `--warning-foreground`, `--destructive`, `--destructive-50`, `--destructive-foreground`, `--info` | statuses, alerts, toasts |
| Seat zones | `--zone-vip`, `--zone-vip-50`, `--zone-premium`, `--zone-premium-50` (standard uses Pine) | seat maps, zone badges, legends |
| Lines | `--border`, `--border-strong`, `--input`, `--ring` | borders, taken seats, focus |
| Elevation | `--shadow-xs…pop` | warm-tinted shadows (neutral black in dark) |
| Shape / type | `--radius*`, `--font-display`, `--font-sans` (Onest), `--font-mono` | theme-independent, `:root` only |

## Rules

1. **No hard-coded colours in components.** No hex values and no Tailwind palette classes (`bg-red-400`, `text-blue-700`, `dark:…`). Use the Tailwind token names or an arbitrary value with a token: `bg-[color:var(--warning-50)] text-[color:var(--warning-text)]`. The check:
   ```bash
   grep -rnE '#[0-9a-fA-F]{3,8}\b|\b(bg|text|border|ring|from|to|via|fill|stroke)-(red|orange|amber|yellow|green|emerald|teal|blue|indigo|purple|pink|rose|gray|slate)-[0-9]{2,3}' EventHub/frontend/src/app --include='*.ts' | grep -v '\.spec\.ts'
   ```
   Allowed exceptions: the default colour of a new check-in list (`#E8643A`, stored as data) and the scanner's spinner over the camera feed.
2. **Orange fills take dark text.** White on `--ember-500` is about 3.3:1; use `--primary-foreground` / `--accent-foreground` (`#1A120D`).
3. **Orange text uses `--accent-text`**, never `--ember-500`.
4. **Artwork is fixed, not themed.** Photos, category covers (`components/home/category-cover.ts`), the Discover hero and pills over photos use white text on a dark fade or `bg-black/45…60`; they look the same in both themes. QR codes keep a white background so scanners read them.
5. **A new token goes into both blocks** (`:root` and `.dark`); a new text token also goes into the contrast list in `design-tokens.spec.ts`.
6. **SVG colours go through `style`**, not presentation attributes: `[style.fill]="'var(--pine-50)'"` (see `seat-map-svg.component.ts`).
7. **Custom CSS lives in `@layer components`**, otherwise it overrides Tailwind utilities such as `hidden` and `md:*`.

## Typography

Onest (OFL, `assets/fonts/onest-*.woff2`, Cyrillic and Kazakh subsets loaded by `unicode-range`) for headings and body; JetBrains Mono for codes and ticket numbers. Outfit exists only inside the logo artwork (it has no Cyrillic). Headings use `.font-display` (tight tracking), numbers use `.num` (tabular figures), small uppercase labels use `.kicker`.

## Status colours at a glance

| State | Badge / pill |
|---|---|
| confirmed, published, free | Pine (`badge-confirmed`, `badge-success`) |
| pending, waiting, offered | Ember tint (`badge-pending`) or Warning tint |
| rejected, cancelled, expired | Destructive tint (`badge-rejected`, `badge-cancelled`) |
| completed, info | Sunken surface (`badge-completed`, `badge-info`) |
