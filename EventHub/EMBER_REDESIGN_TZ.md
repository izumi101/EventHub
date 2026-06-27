# ТЗ: Полный редизайн дизайн-системы EventHub — «Ember» (Warm Editorial)

> Дизайн-язык уровня Apple по ремеслу, но с собственной идентичностью. Не Apple, не «техно-SaaS», не indigo-marketplace. Кодовое имя системы — **Ember**.
> Направление утверждено владельцем: **Warm Editorial** (Ink / Paper / Coral, Clash Display + Satoshi).
> Метафора: «культурный журнал, который продаёт билеты».

---

## 0. TL;DR

Заменить текущую светлую indigo-систему (`#4f46e5`, Inter, 8px-радиусы) на тёплую editorial-систему **Ember**:
- **Палитра:** тёплая бумага `#FAF7F2`, графитовый ink `#1A1714`, фирменный коралл-ember `#E8552D`, опорный pine `#2B6B5E`.
- **Типографика:** display **Clash Display**, UI/body **Satoshi**, моно **JetBrains Mono** (коды/таблицы). Все — self-hosted (Fontshare/Google).
- **Геометрия:** базовый радиус 14px, тёплые мягкие тени (ink-tinted, не серые), воздух и крупная типографика.
- **Сигнатура:** ticket-stub-вырез на карточках, editorial-«kicker» (моно-надстрочник), крупный календарный date-block, асимметричная featured-сетка.
- **Объём:** переписать `styles.css` (дизайн-токены + shared-классы) и `tailwind.config.js`, затем последовательно прогнать все 24 маршрута. Логику, сервисы, гварды, роуты — **не трогать**.
- **Качество:** WCAG AA (проверенные пары контраста), `prefers-reduced-motion`, тёмная тема в тёплой палитре, CLS < 0.1, `npm run build` зелёный.

---

## 1. Роль исполнителя

Ты — senior product-дизайнер-инженер. Делаешь не «фейслифт», а полную замену визуального языка с уровнем ремесла, ожидаемым от Apple: тотальная сдержанность, идеальная типографическая ритмика, оптическое выравнивание, осмысленное движение, глубина за счёт тонкости, а не тяжёлых эффектов. При этом результат **не должен выглядеть как Apple** — никакого SF/system-look, никакого frosted-glass marketing-hero, никакой серебристо-холодной нейтрали. У EventHub своя тёплая редакционная душа.

Работать строго по этому ТЗ. Где ТЗ даёт токен/значение — использовать его дословно. Где даёт направление — держать заявленный уровень аккуратности.

---

## 2. Контекст проекта (факты, проверено в коде)

- **Стек фронтенда:** Angular 21 (standalone), Tailwind CSS **v3.4**, RxJS, `lucide-angular`, PostCSS + autoprefixer. Сборка `ng build` (prod, nginx в Docker). PDF-билеты: `jspdf` + `html2canvas`. QR: `jsqr`.
- **Текущая дизайн-система** живёт в `frontend/src/styles.css` (755 строк): CSS-переменные в `:root` + `.dark`, и `@layer components` с классами `.btn*`, `.input`, `.card`, `.badge*`, `.spinner`, `.toggle`, плюс полноценная shell-система (`.sidebar*`, `.topbar*`, `.shell-right*`). Tailwind мостит цвета через `var(--…)` в `tailwind.config.js`.
- **Шрифт сейчас:** Inter. **Цвет сейчас:** indigo `#4f46e5`. Радиус `--radius: 0.5rem`. Это и есть то, что заменяем.
- **Навигация:** Grafana-style сворачиваемый сайдбар (`frontend/src/app/layout/`: `app-shell`, `sidebar`, `topbar`, `layout.service`, `nav.config.ts`). Часть маршрутов («bare»: login/register/forgot/payment/booking) рендерится без сайдбара.
- **Роли:** `public | auth | attendee | organizer | admin`. Навигация и видимость пунктов зависят от роли (см. `nav.config.ts`). Organizer получает «event-context» секцию сайдбара.
- **24 маршрута** (см. `app.routes.ts`) — полный список в §12. Все должны быть переоформлены; ни один не удаляем.
- **Запрет на изменение поведения:** `app.routes.ts`, гварды (`guards/`), интерсепторы (`interceptors/`), сервисы (`services/`), модели (`models/`) и любые API-вызовы — **не меняем**. Редизайн — только визуальный слой (шаблоны, классы, токены, при необходимости — мелкая разметочная перестройка внутри компонентов).

> Важно: это **второй** редизайн. Первый (2026-06) уже увёл проект из тёмного neon-glass в светлый indigo. Ember — следующий шаг: из «корректного, но нейтрального» в «фирменный и запоминающийся». Не возвращаем dark-glass и neon.

---

## 3. Главный принцип: «уровень Apple, но не Apple»

**Берём у Apple (уровень ремесла):**
- Радикальная сдержанность: один акцент, мало цвета, много воздуха.
- Типографика как главный носитель иерархии (размер/вес/трекинг), а не цвет и не рамки.
- Движение со смыслом: каждая анимация объясняет причинно-следственную связь; пружинные кривые; прерываемость.
- Оптическая точность: выравнивание по оптике, табличные цифры, согласованный ритм 4/8px.
- Глубина тонкостью: мягкие слои и одна аккуратная тень вместо «толстых» эффектов.

**НЕ делаем как Apple (чтобы была своя идентичность):**
- ❌ Никакого SF Pro / system-font-look. У нас Clash Display + Satoshi.
- ❌ Никакого frosted-glass / liquid-glass / backdrop-blur как несущей эстетики.
- ❌ Никакой холодной серебристо-серой нейтрали и «space-gray». База — тёплая бумага.
- ❌ Никаких гигантских центрированных marketing-hero на весь экран.
- ❌ Никаких градиентных blob/orb, neon-glow, фиолетово-синих градиентов.

**Своя душа Ember (editorial marketplace):**
- Тёплая бумажная база + насыщенный коралловый акцент = живая, человеческая, «культурная» интонация.
- Редакционные приёмы: moho-«kicker» над заголовком, крупные display-числа дат, асимметричная featured-сетка, «билетная» метафора (вырез-перфорация).
- События — в центре внимания; рабочие экраны организатора — плотные, но спокойные (Linear/Stripe-уровень чистоты, без их холодности).

Антиреференсы (не копировать визуально, брать только уровень): Apple.com, generic AI-SaaS-лендинги, crypto-дашборды, Material-дефолты.
Референсы интонации (не копировать, брать дух): редакционные афиши и культурные журналы (Kinfolk/Cereal по теплу), Eventbrite по сценариям, Airbnb по аккуратности карточек, Linear/Stripe по чистоте рабочих экранов.

---

## 4. Дизайн-язык «Ember» — концепция

Три несущих идеи, которые делают систему узнаваемой:

1. **Тёплая бумага + ember-акцент.** Фон — тёплый off-white (как качественная бумага), не чисто-белый и не серый. Один насыщенный коралл несёт всё действие: CTA, активные состояния, акценты. Второй цвет (pine) — опорный, для «free/доверие/успех».
2. **Editorial-типографика.** Clash Display задаёт характер в крупных заголовках и числах; Satoshi держит всю плотную UI-работу. Моно-«kicker» (надстрочные ярлыки капсом) — фирменная деталь рубрикации.
3. **Билетная метафора.** Карточка события и билет несут лёгкий «stub»-намёк: перфорация/вырез, отрывная линия, крупный date-block. Это сразу читается как «события и билеты», без иллюстративного мусора.

Эмоция: премиально, но тепло и по-человечески; уверенно, но не громко; «журнал, который продаёт билеты».

---

## 5. Цветовая система

Все цвета — через семантические CSS-переменные. Никаких raw-hex в компонентах (кроме самих определений токенов). Tailwind продолжает мостить через `var(--…)`.

### 5.1 Светлая тема (основная) — токены

```css
:root {
  /* ── Surfaces (тёплая бумага) ── */
  --background:          #FAF7F2;  /* warm paper — фон приложения */
  --surface:             #FFFFFF;  /* карточки/панели приподняты над бумагой */
  --surface-sunken:      #F2ECE3;  /* «утопленные» зоны: inputs-fill, табы-трек */
  --foreground:          #1A1714;  /* warm near-black ink */

  --card:                #FFFFFF;
  --card-foreground:     #1A1714;
  --popover:             #FFFFFF;
  --popover-foreground:  #1A1714;

  /* ── Brand: Ember (коралл) ── */
  --ember-50:   #FEF1EC;
  --ember-100:  #FBDFD3;
  --ember-500:  #E8552D;   /* ФИРМЕННЫЙ акцент: марки, иконки, подчёркивания, hover-обводки */
  --ember-600:  #D2491F;   /* hover для не-текстовых заливок */
  --ember-700:  #C2410C;   /* заливка CTA-кнопок (бел. текст = AA 5.18:1) */
  --ember-800:  #9A3412;   /* active/pressed */

  --primary:             var(--ember-700);  /* заливка primary CTA */
  --primary-foreground:  #FFFFFF;
  --accent:              var(--ember-500);  /* идентичность: подчёркивания/иконки/маркеры */
  --accent-foreground:   #FFFFFF;

  /* ── Support: Pine (опора/доверие/free) ── */
  --pine-50:   #E8F2EF;
  --pine-500:  #2B6B5E;
  --pine-600:  #235850;

  /* ── Neutrals (тёплые) ── */
  --muted:               #F2ECE3;  /* тёплый «secondary» surface */
  --muted-foreground:    #6B6259;  /* тёплый серый текст (AA на бумаге) */
  --secondary:           #F2ECE3;
  --secondary-foreground:#3A332C;

  /* ── Borders & inputs (тёплые hairline) ── */
  --border:              #ECE6DD;
  --border-strong:       #DCD3C6;  /* акцентированная рамка/divider */
  --input:               #FFFFFF;
  --ring:                var(--ember-500);

  /* ── Feedback (тёплая настройка; destructive ≠ ember!) ── */
  --success:             #2B6B5E;  /* = pine */
  --success-foreground:  #FFFFFF;
  --warning:             #B8761F;
  --warning-foreground:  #FFFFFF;
  --destructive:         #B42318;  /* ГЛУБОКИЙ красный — намеренно отличён от коралла */
  --destructive-foreground:#FFFFFF;
  --info:                #2B6B5E;

  /* ── Geometry ── */
  --radius:     14px;
  --radius-sm:  8px;
  --radius-lg:  20px;
  --radius-pill:9999px;

  /* ── Fonts ── */
  --font-display: 'Clash Display', 'Satoshi', ui-sans-serif, system-ui, sans-serif;
  --font-sans:    'Satoshi', ui-sans-serif, system-ui, -apple-system, sans-serif;
  --font-mono:    'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;

  /* ── Elevation (ink-tinted, ТЁПЛЫЕ тени, не серые) ── */
  --shadow-xs:   0 1px 2px rgba(26,23,20,0.04);
  --shadow-sm:   0 1px 3px rgba(26,23,20,0.06), 0 1px 2px rgba(26,23,20,0.04);
  --shadow-card: 0 2px 8px rgba(26,23,20,0.06);
  --shadow-md:   0 6px 16px -4px rgba(26,23,20,0.10);
  --shadow-lg:   0 12px 32px -8px rgba(26,23,20,0.14);
  --shadow-pop:  0 20px 48px -12px rgba(26,23,20,0.18);
}
```

### 5.2 Тёмная тема (warm dark — НЕ холодный slate)

```css
.dark {
  --background:          #17140F;  /* warm espresso, не сине-чёрный */
  --surface:             #211C16;
  --surface-sunken:      #120F0B;
  --foreground:          #F5EFE6;  /* warm paper text */

  --card:                #211C16;
  --card-foreground:     #F5EFE6;
  --popover:             #211C16;
  --popover-foreground:  #F5EFE6;

  --ember-500:  #FF6A3D;  /* чуть ярче для тёмного фона */
  --ember-600:  #F2592C;
  --ember-700:  #FF6A3D;  /* в тёмной теме CTA = яркий ember (тёмный текст) */
  --primary:             #FF6A3D;
  --primary-foreground:  #1A1310;  /* тёмный текст на ярком ember */
  --accent:              #FF6A3D;
  --accent-foreground:   #1A1310;

  --muted:               #2A241C;
  --muted-foreground:    #A89D8E;
  --secondary:           #2A241C;
  --secondary-foreground:#E6DCCD;

  --border:              #332C23;
  --border-strong:       #4A4032;
  --input:               #211C16;
  --ring:                #FF6A3D;

  --success:             #4FB89A;
  --destructive:         #F0654E;  /* в тёмном — светлее, но всё ещё «красный», не коралл */
  --warning:             #E0A042;

  --shadow-card: 0 2px 8px rgba(0,0,0,0.40);
  --shadow-md:   0 6px 16px -4px rgba(0,0,0,0.50);
  --shadow-lg:   0 12px 32px -8px rgba(0,0,0,0.55);
  --shadow-pop:  0 20px 48px -12px rgba(0,0,0,0.60);
}
```

Дефолт темы — **светлая**. Тёмная подключается через существующий `ThemeService` (`<html class="dark">`). Тёмная — обязательный first-class режим, не «инверсия»: спроектирована отдельно, в тёплой палитре.

### 5.3 Критическое правило: Ember-акцент ≠ Destructive

Коралл `#E8552D` и опасный красный `#B42318` близки по тону. Это намеренная зона риска, и её снимаем правилами:
- **Destructive всегда** сопровождается иконкой (`Trash2`/`AlertTriangle`) и текстовой меткой — цвет никогда не несёт смысл в одиночку.
- Destructive-кнопка — обведённая/ghost по умолчанию (`--destructive` текст на прозрачном, hover-фон `--ember-50`-аналог красного `#FDEBE9`); сплошная красная заливка — только в финальном confirm-модале.
- Ember-акцент **никогда** не используется для ошибок/удаления. Ember = «главное действие/идентичность», красный = «опасно/ошибка».
- Контраст проверять (см. §15): белый текст на `--primary` (`#C2410C`) = 5.18:1 ✓; `--ember-500` использовать для текста только на светлом фоне ≥ size-L или как не-текстовую марку.

---

## 6. Типографика

### 6.1 Семейства

| Роль | Шрифт | Источник | Назначение |
|---|---|---|---|
| Display | **Clash Display** (500, 600) | Fontshare (ITF Free License) | Hero-заголовки, крупные числа дат/цен, H1–H2, editorial-моменты |
| UI / Body | **Satoshi** (400, 500, 700) | Fontshare (ITF Free License) | Весь интерфейс, body, кнопки, формы, таблицы, сайдбар |
| Mono | **JetBrains Mono** (400, 500) | Google Fonts | «kicker»-надстрочники капсом, коды билетов/UUID, промокоды, табличные значения |

> Clash Display и Satoshi — **не Google Fonts**. Их нужно **self-hostить** (см. §6.4). Inter полностью удаляется.

### 6.2 Шкала (editorial-контраст)

| Токен | Размер / line-height | Шрифт / вес / трекинг | Применение |
|---|---|---|---|
| `display-xl` | `clamp(2.5rem, 5vw, 4rem)` / 1.02 | Clash 600 / −0.02em | Hero событие, крупные экраны |
| `display-l`  | `clamp(2rem, 3.5vw, 3rem)` / 1.05 | Clash 600 / −0.02em | Заголовки секций-афиш |
| `h1` | 1.875rem / 1.15 | Clash 600 / −0.01em | Заголовок страницы |
| `h2` | 1.5rem / 1.2 | Clash 500 / −0.01em | Подзаголовок раздела |
| `h3` | 1.25rem / 1.3 | Satoshi 700 | Заголовок карточки/блока |
| `body-l` | 1.0625rem / 1.6 | Satoshi 400 | Лиды, описание события |
| `body` | 0.9375rem / 1.6 | Satoshi 400 | Базовый текст |
| `small` | 0.8125rem / 1.5 | Satoshi 400/500 | Мета, подписи |
| `kicker` | 0.6875rem / 1 | **Mono** 500, uppercase, +0.10em | Надстрочные ярлыки-рубрики (категория, «SOLD OUT», даты-метки) |
| `numeric` | — | `font-variant-numeric: tabular-nums` | Цены, счётчики, дашборд-метрики, таймеры |

Правила: длина строки body 60–75 симв.; базовый body на мобиле ≥16px (анти-зум iOS — для `input` ставить 16px); заголовки переносить, а не truncate (где truncate необходим — ellipsis + полный текст в `title`).

### 6.3 «Kicker» — фирменная деталь

Над крупными заголовками и в мета-зонах используем моно-надстрочник капсом: например `НА МОНО · 21 ИЮНЯ · OPEN AIR`. Это даёт редакционную интонацию и отстраивает нас от Apple. Цвет — `--muted-foreground` или `--ember-500` для «горячих» ярлыков (`SELLING FAST`).

### 6.4 Self-hosting шрифтов (технический пункт)

1. Скачать `Clash Display` и `Satoshi` (woff2, нужные веса) с Fontshare; положить в `frontend/src/assets/fonts/`.
2. JetBrains Mono — тоже self-host (woff2) либо подключить через Google `display=swap`.
3. Объявить `@font-face` с `font-display: swap` для каждого веса; задать `size-adjust`/fallback-метрики, чтобы свести CLS к минимуму.
4. Убрать любые `@import`/`<link>` Inter. Обновить `tailwind.config.js` `fontFamily` (`display`, `sans`, `mono`).
5. Preload **только** критических весов (Clash 600 для hero, Satoshi 400/500). Остальное — `swap`.
6. Проверить лицензию ITF Free Font License (разрешает self-host в вебе) — приложить файл лицензии в `assets/fonts/`.

```css
/* пример */
@font-face{
  font-family:'Satoshi';
  src:url('/assets/fonts/Satoshi-Variable.woff2') format('woff2');
  font-weight:300 900; font-display:swap; font-style:normal;
}
@font-face{
  font-family:'Clash Display';
  src:url('/assets/fonts/ClashDisplay-Variable.woff2') format('woff2');
  font-weight:400 700; font-display:swap; font-style:normal;
}
```

---

## 7. Сетка, отступы, радиусы, тени

- **База ритма:** 4px; шаг 8px. Spacing-набор: `4, 8, 12, 16, 24, 32, 48, 64, 96`. Внутри одного уровня иерархии — одинаковые отступы.
- **Контейнер:** `max-width: 1200px` (контентные страницы), `padding-inline` 16/24/32 по брейкпоинтам (как сейчас в `.container`). Discovery-сетка может уходить шире (до 1320px) для афишной плотности.
- **Радиусы:** кнопки/инпуты/чипы `--radius-sm` 8px; карточки/панели `--radius` 14px; модалки/hero-медиа/большие изображения `--radius-lg` 20px; бэйджи/аватары/тогглы — pill. Без «огромных» 24px+ радиусов на мелких элементах.
- **Тени (editorial-сдержанность):** базовый язык — рамка `--border` + при наведении одна мягкая тёплая тень `--shadow-card`. Тяжёлые многослойные тени — только для всплывающих слоёв (popover/modal/toast → `--shadow-lg`/`--shadow-pop`). Никаких тёмных «глубоких» теней на статичных карточках.
- **Z-index шкала:** `0 / 10 (sticky) / 20 (topbar) / 30 (sidebar) / 40 (dropdown) / 50 (overlay) / 60 (modal) / 70 (toast)`.

---

## 8. Движение и анимации

| Тип | Длительность | Кривая |
|---|---|---|
| Micro (hover/press/toggle) | 140ms | `cubic-bezier(0.32,0.72,0,1)` (фирменная «emphasized») |
| Standard (раскрытие/смена состояния) | 220ms | enter `ease-out`, exit `ease-in` |
| Entrance (появление страницы/секции) | 280–320ms | spring-подобная emphasized |
| Exit | ~70% от entrance | быстрее входа |

Правила:
- Анимируем **только** `transform` и `opacity`. Никогда — `width/height/top/left` (никакого CLS).
- На экран — **1–2** значимых анимации, не больше. Никаких декоративных «вечных» анимаций.
- Stagger для списков/сеток: 30–40ms на элемент при первом появлении.
- **Сигнатурное движение:** shared-element-переход «карточка → деталь события» (изображение события «вырастает» в hero); лёгкий подъём карточки при hover (`translateY(-2px)` + `--shadow-card` + `scale(1.03)` изображения внутри `overflow:hidden`); press-feedback `scale(0.98)`.
- **Параллакс** hero-изображения — максимум 8px, только если включено движение.
- `@media (prefers-reduced-motion: reduce)`: отключить все `transform`-анимации и параллакс, оставить мгновенные/opacity-переходы. Обязательно.
- Все анимации прерываемы; ввод пользователя не блокируется анимацией.

---

## 9. Иконография

- Остаёмся на **`lucide-angular`** (тонкая линия, единый стиль). Stroke 1.75–2px, единый размер-набор: `icon-sm 16`, `icon 18`, `icon-md 20`, `icon-lg 24`. Не смешивать filled/outline на одном уровне.
- Никаких emoji как иконок (в текущем коде местами есть 📝/⏳/✓ в статус-бэйджах дашборда — заменить на lucide).
- Иконки выравнивать по оптической базовой линии текста; в кнопках — `gap` 8px.
- Цвет иконок — `currentColor`; акцентные — `--ember-500`.

---

## 10. Система компонентов (переписать shared-классы)

Ниже — целевые спецификации для `@layer components` в `styles.css`. Сохранить **имена существующих классов** (`.btn`, `.btn-primary`, `.input`, `.card`, `.badge*`, `.spinner`, `.toggle` и shell-классы), чтобы не переписывать 37 шаблонов — меняем их визуальное наполнение. Добавить новые классы там, где появляется новая сущность.

### 10.1 Buttons
- `.btn`: Satoshi 500/600, `--radius-sm`, высота 40px (sm 32px, lg 48px), `gap` 8px, переход 140ms. Press → `scale(0.98)`.
- `.btn-primary`: фон `--primary` (ember-700), текст белый; hover `--ember-800`; focus-ring `--ring` 3px low-alpha. Ровно **один** primary CTA на экран.
- `.btn-secondary`: фон `--muted`, текст `--secondary-foreground`, рамка `--border`; hover `--border-strong`.
- `.btn-outline`: прозрачный, рамка `--border-strong`, текст `--foreground`; hover фон `--muted`.
- `.btn-ghost`: прозрачный, текст `--muted-foreground`; hover фон `--muted`, текст `--foreground`.
- `.btn-accent` (новый, опц.): фон `--ember-500`, текст белый — **только** для крупных/важных «горячих» CTA размера ≥L (контраст ок на size-L); иначе использовать `.btn-primary`.
- `.btn-danger`: текст `--destructive` на прозрачном + обяз. иконка; hover фон `#FDEBE9`. Сплошной красный — только финальный confirm.
- Disabled: `opacity .5`, `cursor not-allowed`, без hover.

### 10.2 Inputs / Forms
- `.input`: фон `--input` (#FFF), рамка `--border`, `--radius-sm`, высота 44px (touch), 16px текст на мобиле. Focus: рамка `--ember-500` + ring `0 0 0 3px rgba(232,85,45,.15)`.
- Видимый `<label>` над полем (не placeholder-as-label). Required — `*` в `--ember-500`.
- Ошибка: `.input-error` рамка `--destructive`, текст ошибки **под полем**, иконка `AlertCircle`, `aria-live`. Валидация — на `blur`, не на каждый keystroke.
- Helper-text под сложными полями (persistent). Пароль — toggle show/hide. `inputmode/type` семантические (email/tel/number). `autocomplete` включить.
- `.select`, `.textarea`, `.checkbox`, `.radio`, `.toggle` — единый язык (track `--surface-sunken`, активный `--ember-500`).

### 10.3 Card + ticket-stub
- `.card`: фон `--surface`, рамка `--border`, `--radius` 14px. `.card-hover`: при наведении `translateY(-2px)` + `--shadow-card` + рамка `--border-strong`.
- **`.card-ticket` (новый, сигнатура):** карточка события с «билетным» намёком — тонкая пунктирная отрывная линия между медиа и контентом и два полукруглых выреза `--background`-цвета по краям этой линии (через `radial-gradient`/псевдоэлементы, **без** layout-shift). Применять к Event Card и билетам в «My Tickets».
- **`.date-block` (новый):** компактный «календарный» блок — крупное число дня (Clash 600) над моно-месяцем капсом. Используется в карточках/деталях/списках.

### 10.4 Badge / Chip / Kicker
- `.badge`: pill, Satoshi 500, 12px. Семантика на тёплых тинтах:
  - `badge-free`/`badge-success`: `--pine-50` фон, `--pine-600` текст.
  - `badge-pending`/`badge-hot` («Selling fast»): `--ember-50` фон, `--ember-700` текст.
  - `badge-soldout`/`badge-error`: `#FDEBE9` фон, `--destructive` текст + иконка.
  - `badge-online`/`badge-info`: `--pine-50`/нейтраль.
- `.chip` (фильтры/категории): pill/`--radius-sm`, рамка `--border`; active → фон `--foreground` ink, текст `--background` (editorial-инверсия) **или** подчёркивание `--ember-500` — выбрать один паттерн активности и держать его везде.
- `.kicker`: моно капс надстрочник (см. §6.3).

### 10.5 Sidebar / Topbar / Shell (сохранить структуру, сменить кожу)
- Сайдбар: фон `--surface`, рамка-справа `--border`. Active-item — **не** заливка-pill, а: лёгкий тинт `--ember-50` + левый маркер 2px `--ember-500` + текст `--foreground` (вес 600). Hover — фон `--muted`.
- Логотип EventHub перерисовать в Ember-стиле (Clash-wordmark + ember-марк; см. §11.5).
- Topbar: фон `--background` (тёплая бумага), нижняя рамка `--border`, высота 56px, sticky. Поиск/иконки/профиль — в новом языке.
- Все размеры/брейкпоинты shell-системы (collapsed 64px / expanded 248px / mobile off-canvas) — сохранить.

### 10.6 Прочие
- `.modal`/sheet: `--radius-lg`, `--shadow-pop`, анимация из источника (scale+fade/slide); scrim `rgba(26,23,20,.45)`; Esc/клик-вне/«×»; на мобиле — bottom-sheet со swipe-down.
- `.toast`: `--radius-sm`, `--shadow-lg`, `aria-live="polite"`, авто-дисмисс 3–5s, не крадёт фокус. Успех — pine, ошибка — destructive (с иконкой).
- `.table` (дашборд/attendee/check-in): zebra тёплая (`--surface` / `--surface-sunken` слегка), sticky-заголовок, сортировка с `aria-sort`, табличные цифры, на мобиле — переход в карточный список.
- `.skeleton`: тёплый shimmer (`--muted` → `--surface`), резервирует размеры (анти-CLS). Показывать при загрузке >300ms.
- `.empty-state`: иконка-кружок `--muted`, заголовок Clash, текст-подсказка, один CTA.
- `.spinner`: тёплый, top-color `--ember-500`.

---

## 11. Сигнатурные паттерны (что делает дизайн «нашим»)

1. **Ticket-stub-вырез** (`.card-ticket`) — на карточках событий и билетах. Главный визуальный код продукта.
2. **Editorial date-block** (`.date-block`) — крупное число дня + моно-месяц; повторяется по всему продукту.
3. **Mono-kicker** (`.kicker`) — надстрочные рубрики капсом; интонация журнала.
4. **Асимметричная featured-сетка** на Discovery — первое/featured-событие крупнее (2×), остальные — обычная сетка. Не «marketing-hero», а афишная плотность.
5. **Wordmark Ember** — логотип набран Clash Display; «марка» — стилизованный ember/билет. Без неон-glow.

---

## 12. Экраны (по всем 24 маршрутам)

Для каждого экрана обязательны состояния: **loading (skeleton) · empty · error · success**. Ниже — направление по поверхностям; маршруты сгруппированы.

### 12.1 Discovery / Home — `/`
- Компактная discovery-шапка: крупный поиск (главный «CTA-as-search»), сохранить AI-toggle семантического поиска (ember-marker вместо violet), фильтры (категория-чипы, локация, free/paid, online/offline, sort).
- **Editorial-сетка:** featured-событие крупной карточкой + сетка `card-ticket` 1/2/3 колонки (mobile/tablet/desktop), `gap` 20–24px. Category-rail чипами.
- Загрузка — skeleton-сетка; empty — `empty-state`; load-more/пагинация. Без огромного hero.

### 12.2 Event Card — `app-event-card`
- `card-ticket`: медиа 16:9 (или fallback с инициалом в `--surface-sunken`), отрывная линия + вырезы, `date-block`, `kicker` категории, заголовок (Clash 700/Satoshi 700, line-clamp 2), мета (дата/локация/места) иконками, футер: цена (tabular) ↔ «View event →» (ember). Бэйджи `Free`/`Online`/`Selling fast`/`Sold out` — новые тинты.

### 12.3 Event Detail — `/events/:id`
- Сильная visual-зона (hero-медиа `--radius-lg`, shared-element из карточки). Слева — контент (kicker, display-xl заголовок, описание body-l, дата/локация/организатор, карта/онлайн-метка). Справа — **sticky ticket-панель** (`card-ticket`): цена, выбор тарифа/мест (сохранить `seat-selector`/`seat-map-svg`), промокод, CTA «Get tickets» (`.btn-primary`/`.btn-accent`), статус-баннеры (pending — `--warning` тинт, sold out, waitlist).
- Stripe-флоу не ломать. `SeoService` (title/og/JSON-LD) не трогать.
- Sub-routes: `/events/:id/group` (group-booking), `/booking/:token` (claim) — bare-страницы в том же языке.

### 12.4 Auth — `/login`, `/register`, `/forgot-password`
- Bare-страницы (без сайдбара). Editorial-композиция: слева тёплая брендовая панель (kicker + Clash-фраза + ember-деталь/паттерн, **без** glass и градиент-blob), справа — спокойная форма. На мобиле — только форма.
- Формы по §10.2: видимые labels, inline-валидация на blur, password-toggle, понятные ошибки с recovery-путём, loading→success на submit. Register сохраняет email-verification флоу.

### 12.5 Account — `/profile`, `/favorites`, `/my-registrations`, `/my-events`
- `/profile`: editorial-«профиль-карточка» (аватар-инициалы на ember/pine), секции настроек, формы в новом языке.
- `/my-registrations` (My Tickets, attendee): список **билетов** как `card-ticket` со stub-вырезом, QR/код (mono), статус-бэйджи, скачивание PDF (jspdf не трогать).
- `/my-events`, `/favorites`: сетки/списки событий в новом языке, empty-states.

### 12.6 Organizer workspace — `/organizer/dashboard` + event-context
- **Dashboard:** спокойный, плотный, Linear/Stripe-уровень. Метрики-карточки (tabular-цифры, тренды иконками lucide — **убрать emoji**), табы Upcoming/Past/Drafts, поиск/фильтр/сорт, capacity-бары (ember-fill), revenue, quick-actions меню, activity feed, status-бэйджи (новые тинты, без emoji). View-toggle list/calendar.
- **Event-context экраны** (сайдбар-секция): `/attendees`, `/ticket-types`, `/promo-codes`, `/questions`, `/checkin-lists`, `/waitlist`, `/settings`, `/edit-event/:id`, `/create-event` — единый язык таблиц/форм/тулбаров (§10.2, §10.6). `create/edit-event` — многошаговая форма с прогрессом, авто-сейв-черновик, понятные ошибки.

### 12.7 Check-in / Scan — `/scan`, `/validate/:uuid`, `/organizer/events/:id/checkin-lists`
- `/scan`: камера-QR (jsqr не трогать) на спокойном тёмном-нейтральном фоне сканера с ember-рамкой-таргетом; крупная обратная связь success/fail. `/validate/:uuid`: крупный статус check-in (pine success / destructive fail) с иконкой и данными билета. Check-in lists — таблицы §10.6.

### 12.8 Payment & system — `/payment/success`, `/payment/cancel`, `**` (404)
- Success: pine-успех, иконка, краткое подтверждение, ссылка на билет (`card-ticket`-превью). Cancel: спокойный нейтральный, recovery-CTA «Try again». 404: editorial-минимал (крупная Clash-цифра, kicker, ссылка домой). Все — без сайдбара/в общем языке соответственно.

---

## 13. Тёмная тема

- Тёплый dark (см. §5.2), не холодный slate; ember в тёмном — ярче (`#FF6A3D`), текст на ember — тёмный. Проектировать пары контраста отдельно (§15). Рамки/divider видимы в обеих темах. Тестировать оба режима до сдачи (не выводить из одного).

---

## 14. Адаптивность

- Mobile-first. Брейкпоинты: 375 / 640 / 768 / 1024 / 1440.
- Нет горизонтального скролла на мобиле; `min-h-dvh` вместо `100vh`; `viewport-fit=cover` + safe-area для bare-экранов и sticky-баров.
- Сайдбар: desktop expand/collapse, tablet collapsed, mobile off-canvas (как сейчас).
- Таблицы → карточные списки на мобиле. Touch-таргеты ≥44px, gap ≥8px.
- Sticky ticket-панель Event Detail → закреплённый нижний bar с ценой+CTA на мобиле.

---

## 15. Доступность (WCAG AA — обязательно)

- **Контраст (проверить инструментом):**
  - ink `#1A1714` на paper `#FAF7F2` ≈ 15:1 ✓; на белой карте ≈ 16:1 ✓.
  - `--muted-foreground #6B6259` на бумаге — проверить ≥4.5:1 для body (если не дотягивает на мелком — затемнить до `#5E564D`).
  - белый на `--primary #C2410C` = 5.18:1 ✓ (AA).
  - `--ember-500 #E8552D` как **текст** — только size-L (≥3:1) или как не-текстовая марка; для мелкого текста брать `--ember-700`.
  - белый на pine `#2B6B5E` ≈ 6.2:1 ✓; белый на destructive `#B42318` — проверить (≈6:1) ✓.
- Цвет никогда не единственный носитель смысла: статусы/ошибки — иконка+текст.
- Видимые focus-ring (2–3px) на всех интерактивных; tab-порядок = визуальный; skip-link к main.
- Иконочные кнопки — `aria-label`; модалки/sheet — focus-trap + Esc + возврат фокуса; формы — `label for`, `aria-live` для ошибок, авто-фокус на первое невалидное поле.
- Поддержка `prefers-reduced-motion` и масштабирования текста без поломки layout.

---

## 16. Производительность

- Шрифты: self-host woff2, `font-display: swap`, preload только критических весов, fallback-метрики (`size-adjust`) против CLS.
- Изображения: WebP/AVIF, `srcset/sizes`, `loading="lazy"` ниже сгиба, `width/height`/`aspect-ratio` (CLS < 0.1).
- Skeleton вместо длинных спиннеров (>300ms); резерв места под async-контент.
- Lazy-маршруты сохранить; не раздувать initial bundle. Анимации — только `transform/opacity`.
- Цель: Lighthouse Perf ≥ 90 на Home/Event Detail; CLS < 0.1; `npm run build` без ошибок и значимого роста бандла из-за шрифтов (контролировать веса).

---

## 17. Технический план внедрения (порядок работ)

1. **Шрифты:** добавить woff2 + `@font-face` + лицензию; обновить `tailwind.config.js` (`fontFamily`), удалить Inter.
2. **Токены:** переписать `:root` и `.dark` в `styles.css` по §5 (палитра, радиусы, тени, шрифт-переменные). Здесь же — типографические утилиты (`.kicker`, display-классы) и `font-variant-numeric` для `.numeric`.
3. **Shared-классы:** переписать `@layer components` (§10), сохранив имена. Добавить `.card-ticket`, `.date-block`, `.chip`, `.btn-accent`.
4. **Shell:** обновить `.sidebar*`/`.topbar*`/`.shell-*` (§10.5) + новый wordmark.
5. **Экраны по приоритету:** Home → Event Card → Event Detail → Auth → My Tickets/Account → Organizer Dashboard → event-context экраны → Scan/Validate/Check-in → Payment/404.
6. **Тёмная тема:** пройти все ключевые экраны в `.dark`, выправить пары контраста.
7. **A11y/Perf-проход:** контраст, focus, reduced-motion, CLS, Lighthouse.
8. `npm run build` — зелёный; быстрый прогон в Docker (`docker compose up -d --build frontend`).

Не трогать: `app.routes.ts`, `guards/`, `interceptors/`, `services/`, `models/`, API-контракты, Stripe/SEO/QR/PDF-логику.

---

## 18. Критерии приёмки (чек-лист)

- [ ] Inter и indigo полностью удалены; нигде нет `#4f46e5`.
- [ ] Подключены Clash Display + Satoshi (self-host) + JetBrains Mono; типографическая шкала §6 применена.
- [ ] Все цвета — через семантические токены §5; raw-hex в компонентах отсутствуют.
- [ ] `.card-ticket`, `.date-block`, `.kicker` реализованы и используются (карточка/деталь/билет).
- [ ] Ember-акцент и destructive визуально и семантически различимы; destructive всегда с иконкой.
- [ ] Все 24 маршрута переоформлены; каждый имеет loading/empty/error-состояния.
- [ ] Сайдбар/topbar/shell в новом языке; роли/видимость/брейкпоинты сохранены.
- [ ] Тёмная тема — тёплая, first-class, проверена на ключевых экранах.
- [ ] WCAG AA: пары контраста §15 проверены инструментом; focus-states видимы; `prefers-reduced-motion` уважается.
- [ ] CLS < 0.1; Lighthouse Perf ≥ 90 (Home, Event Detail).
- [ ] Никаких emoji-иконок; lucide единым стилем.
- [ ] `app.routes.ts`/гварды/сервисы/модели не изменены; Stripe/SEO/QR/PDF работают.
- [ ] `npm run build` зелёный; проверено в Docker.

---

## 19. Вне области (MVP)

- Анимация-библиотеки (GSAP/Lottie) — не вводим; хватает CSS/Angular animations.
- Редизайн логики/IA навигации (она уже Grafana-style) — не трогаем, только кожа.
- Новые экраны/фичи — нет; только визуальный слой существующих.
- Полноценный motion-парралакс/3D — нет.

---

## 20. Открытые вопросы (с дефолтами — менять только при возражении)

1. **Моно-шрифт:** дефолт JetBrains Mono (Google). Альтернатива — Space Mono (более «editorial»). → дефолт оставить.
2. **Активное состояние чипов/нав:** дефолт — ink-инверсия для чипов + ember-маркер для нав-items. → держать один паттерн.
3. **`.btn-accent` (яркий ember):** дефолт — только крупные «горячие» CTA; обычный primary = ember-700. → ок.
4. **Ticket-stub вырез:** дефолт — тонкий, на Event Card + билетах; не на каждой карточке подряд. → ок.
5. **Тёмная тема по умолчанию:** нет, дефолт — светлая; dark по выбору пользователя. → ок.

---

*Документ — источник истины по визуальному языку Ember. Дизайн-направление подобрано через design-intelligence (ui-ux-pro-max), палитра и пары контраста просчитаны под WCAG AA, фактура проекта сверена с `styles.css`, `app.routes.ts`, `nav.config.ts` и компонентами.*
