# Arkenstone Defense — Design System

> **Tagline:** _Equipping the next generation of primes._

A portable reference for applying the Arkenstone brand to any codebase (web, slides, product UI). Derived from `arkenstonedefense.com` + the official Arkenstone PowerPoint template + brand kit.

The brand is **disciplined, understated, structural, and military-adjacent**. The visual system is quiet so the substance reads loud.

---

## Table of contents
1. [Brand voice & content rules](#brand-voice--content-rules)
2. [Color palette](#color-palette)
3. [Typography](#typography)
4. [Spacing & layout](#spacing--layout)
5. [Borders, radii, shadows](#borders-radii-shadows)
6. [Motion](#motion)
7. [Iconography & logos](#iconography--logos)
8. [Component patterns](#component-patterns)
9. [Page patterns](#page-patterns)
10. [Drop-in CSS tokens](#drop-in-css-tokens)
11. [Tailwind config](#tailwind-config)
12. [Do / Don't](#do--dont)

---

## Brand voice & content rules

**Audience model.** Write as if a senior operator is briefing a peer. The reader is a serious counterparty, not a prospect being sold to.

**Voice**
- Third-person, company-as-subject: *"Arkenstone builds operating environments."*
- Use "we" sparingly, only when speaking as the team. Never "you" to the reader.
- Active voice. Present tense. Claims are stated, not hedged.
- No adjective stacks, superlatives, or startup idioms ("synergy", "seamless", "game-changing", "revolutionary"). Remove "innovative" on sight.

**Casing**
- Display / marketing headlines: **ALL CAPS** (e.g. "YOUR MISSION. OUR INFRASTRUCTURE").
- In-product / long-form headings and body: **sentence case**. Only proper nouns capitalized.
- Eyebrows, metadata, labels, chrome (e.g. `FOR INTERNAL USE ONLY`, `V1`, slide numbers): **ALL CAPS**, DM Mono, tracked +0.12em.
- Compliance standards exactly as the government writes them: **CMMC Level II**, **NIST 800-171**, **DFARS 7012** (no hyphens inserted, no abbreviations softened).

**Tone — good vs bad**
- ✅ "Standards such as CMMC Level II, NIST 800-171, and DFARS 7012 are treated as baseline operating conditions."
- ✅ "We build systems that hold up under scrutiny."
- ✅ "Equipping the next generation of primes."
- ❌ "We're on a mission to transform defense innovation!"
- ❌ "Supercharge your path to compliance 🚀"

**Emoji.** None. Ever. Not even in internal decks. If an icon is needed, use a vector glyph (see [Iconography](#iconography--logos)).
**Exclamation points.** None.
**Numerals.** Spell out one through nine in prose; digits for 10+. Exceptions: compliance numbers (`800-171`), data in figures.
**Symbols.** No ® or ™ unless legally required.

---

## Color palette

Anchored on near-black + warm cream. Two disciplined families of accent: **military olive** (backbone of dark surfaces) and **orange** (primary action / highlight). No gradients except in the marketing hero (olive → black), no bright accents, no purples, no glassmorphism.

### Core brand
| Token | Hex | Usage |
|---|---|---|
| `--brand-black` | `#161616` | Primary ink on light; base dark bg |
| `--brand-white` | `#FFFFFF` | Pure white — used rarely |
| `--brand-bone` | `#E8E4D4` | Warm cream — primary ink on dark; light-surface fill |

### Olive / drab (dark-surface backbone)
| Token | Hex | Usage |
|---|---|---|
| `--olive-900` | `#1F2414` | Darkest — bottom of hero gradient |
| `--olive-800` | `#2A3120` | Primary dark surface |
| `--olive-700` | `#414C32` | Deep olive — section dividers, chart fills |
| `--olive-600` | `#5D6946` | Mid olive — hover / pressed surface |
| `--olive-500` | `#798760` | **Signature olive** — tagline slides, PPTX accent |
| `--olive-200` | `#B8BFA0` | Soft olive — disabled / muted |

### Orange (primary action / signal)
| Token | Hex | Usage |
|---|---|---|
| `--orange-600` | `#C94A1E` | Pressed |
| `--orange-500` | `#E85D2C` | **Primary action, signals, "Approved" stamp** |
| `--orange-400` | `#F47148` | Hover |

### Earth (warm neutrals)
| Token | Hex | Usage |
|---|---|---|
| `--earth-500` | `#8C8271` | Warm neutral |
| `--earth-200` | `#D3CFC3` | Tan / parchment (use sparingly on light) |
| `--earth-900` | `#33322E` | Near-black warm |

### Semantic aliases
| Token | Value |
|---|---|
| `--bg` | `var(--olive-800)` — default dark surface |
| `--bg-deep` | `var(--olive-900)` — deepest dark |
| `--bg-inverse` | `var(--brand-bone)` — light surface |
| `--bg-muted` | `#3A4228` — subtle dark tint |
| `--fg` | `var(--brand-bone)` — cream ink on dark |
| `--fg-inverse` | `var(--brand-black)` — ink on light |
| `--fg-muted` | `#A8A392` — dim cream |
| `--fg-subtle` | `#6E6A5E` — tertiary on dark |
| `--fg-on-orange` | `var(--brand-white)` |
| `--border` | `rgba(232,228,212,0.18)` — hairline on dark |
| `--border-strong` | `rgba(232,228,212,0.35)` |
| `--border-subtle` | `rgba(232,228,212,0.08)` |
| `--border-on-light` | `var(--brand-black)` |
| `--link` | `#2A6EBB` |
| `--link-visited` | `#593E9C` |

**Palette rules**
- Default surface mode is **dark** (olive-800 → black). Light mode is an inversion using bone + black.
- Orange (`--orange-500`) is reserved for primary action, positive signal dots, "Approved" marks, pull-quote marks, and section eyebrow text. Do not use it as a generic decoration color.
- Olive-500 is the signature brand green — used for taglines, the logomark fill when on dark, and single-hero callouts. It is _not_ the primary action color.
- Backgrounds are flat. The only approved gradient is the hero: `linear-gradient(180deg, #3A4225 0%, #2A3120 30%, #161616 100%)`.
- No photography overlays, no patterned fills, no glassmorphism, no backdrop-filter. Exception: a black scrim at `rgba(22,22,22,0.6)` is permitted over full-bleed photography if text must sit on top.

---

## Typography

Three families, each with a clear job.

| Family | Role | Weights in use |
|---|---|---|
| **DM Sans** | Workhorse — headings, body, UI | 400 Regular, 500 Medium, 600 SemiBold, 700 Bold |
| **DM Mono** | "Operational" voice — chrome, metadata, eyebrows, code | 400 Regular, 300 LightItalic |
| **DM Serif Text** | Long-form essay, pull quotes, quote marks | 400 Regular |

DM Mono is **always** tracked `+0.12em` and usually uppercased at small sizes.
DM Serif Text is used **sparingly** — never for UI, never for product headings.

### Type scale (web)
| Token | Size | Weight | Usage |
|---|---|---|---|
| `--fs-display` | `64px` (clamp `56px → 120px` for marketing hero) | 700 | Hero / tagline — ALL CAPS, condensed feel |
| `--fs-h1` | `48px` | 500 Medium | Page titles |
| `--fs-h2` | `36px` | 500 Medium | Section titles |
| `--fs-h3` | `24px` | 600 SemiBold | Block titles |
| `--fs-h4` | `18px` | 600 SemiBold | Card titles |
| `--fs-body` | `16px` | 400 | Body |
| `--fs-small` | `14px` | 400 | Secondary, footnotes |
| `--fs-meta` | `11px` | 400 DM Mono | UPPERCASE chrome (slide #, V1, eyebrows) |

### Heading rules
- Marketing-site **hero + section titles**: DM Sans 700, ALL CAPS, letter-spacing `-0.015em to -0.02em`, line-height `0.95–1.1`.
- In-product **headings**: DM Sans 500 Medium, sentence case, letter-spacing `-0.015em` for h1 and `-0.01em` for h2; h3/h4 use 600 SemiBold with default tracking.
- Display line height: `1.0`. Body line height: `1.5–1.55`. `text-wrap: pretty;` on body paragraphs.

### Eyebrow / meta pattern
```css
font-family: "DM Mono", monospace;
font-size: 11px;
letter-spacing: 0.12em;
text-transform: uppercase;
```
Use for section labels ("01 / PILLAR"), chip content, slide chrome (`FOR INTERNAL USE ONLY`, `V1`, slide numbers), table column headers, form field labels in dark UIs.

### Links
```css
color: var(--link); /* #2A6EBB */
text-decoration: underline;
text-underline-offset: 2px;
text-decoration-thickness: 1px;
```
`:hover` → thickness `2px`. Do not restyle with color changes.

---

## Spacing & layout

**4pt base scale.**
| Token | px |
|---|---|
| `--space-1` | 4 |
| `--space-2` | 8 |
| `--space-3` | 12 |
| `--space-4` | 16 |
| `--space-5` | 24 |
| `--space-6` | 32 |
| `--space-7` | 48 |
| `--space-8` | 64 |
| `--space-9` | 96 |
| `--space-10` | 128 |

**Layout grid.** 12-column at 1440px, 80px outer gutters, 32px column gutters. Container max-width `1200px` with `40px` horizontal padding is the practical default. Content blocks align to column edges, not to optical centers.

**Slide dimensions.** 1920 × 1080. ~96px outer padding. Chrome strip (mono text top/bottom) sits ~24px from the slide edge and is present on _every_ layout.

**Hairline cross markers.** A signature device: a 14 × 14 "+" at section corners, 1px `rgba(232,228,212,0.35)`. Use to frame marketing sections (Statement, CTA).

```css
.plus { position:absolute; width:14px; height:14px; color:rgba(232,228,212,0.35); pointer-events:none; }
.plus::before, .plus::after { content:""; position:absolute; background:currentColor; }
.plus::before { left:50%; top:0; bottom:0; width:1px; transform:translateX(-50%); }
.plus::after  { top:50%; left:0; right:0; height:1px; transform:translateY(-50%); }
```

---

## Borders, radii, shadows

**Radii — restrained. The brand reads as structural.**
| Token | px | Usage |
|---|---|---|
| `--radius-0` | `0` | **Default** — everything (cards, sections, photos) |
| `--radius-sm` | `2` | Small chips, hero compliance chips |
| `--radius-md` | `4` | Product form inputs (ceiling for data-dense UI) |
| `--radius-lg` | `8` | Menus, modals only |
| (pill) | `999px` | **Primary CTA buttons, avatars** — the only approved pill shape |

**Borders.** Prefer hairlines over shadows.
- On light: `1px solid #161616` (hard). Subtle divider: `#D4D4D4`.
- On dark: `1px solid rgba(232,228,212,0.18)`. Strong: `rgba(232,228,212,0.35)`. Subtle: `rgba(232,228,212,0.08)`.

**Shadows.** Rare.
```css
--shadow-0: none;
--shadow-1: 0 1px 2px rgba(22,22,22,0.06), 0 1px 0 rgba(22,22,22,0.04);
--shadow-2: 0 8px 24px -8px rgba(22,22,22,0.18), 0 2px 4px rgba(22,22,22,0.06);
```
No inner shadows. No colored shadows.

---

## Motion

Minimal. Fades and short translations only.

```css
--ease-standard: cubic-bezier(.2, 0, 0, 1);
--dur-fast: 120ms;
--dur-base: 200ms;
```

- Durations: 120–200ms.
- No bounce, no spring overshoot, no parallax, no scale transforms.
- Hover states:
  - Text links → underline thickens to 2px.
  - Filled olive surfaces darken `olive-500` → `olive-600`.
  - Dark (black) buttons lift to `#2A2A2A`.
  - Orange CTA: `#E85D2C` → `#F47148`.
- Press states: hairline-border buttons invert (black bg + white fg). Filled buttons step one shade darker.

---

## Iconography & logos

### Approach
Arkenstone does not ship an icon font or use emoji. Icons are used **sparingly** — prefer text labels and hairline rules over iconographic decoration.

### Logo assets
Four mark types, each in Pure (transparent) and Brand (filled block) variants, each with black and white versions — so 16 files total. All available in `assets/`:

- `logomark-{black,white}.svg` — hexagonal brand mark. Primary brand signal.
- `wordmark-{pureblack,purewhite,brandblack,brandwhite}.svg` — "ARKENSTONE" type only.
- `logo-horizontal-{pureblack,purewhite,brandblack,brandwhite}.svg` — hex + wordmark lockup.

**Pure vs Brand**
- **Pure** — transparent background, ink-colored glyph. Use on clean surfaces.
- **Brand** — logo sits in a rectangular fill (black or white). Use where the logo must sit in its own protected block over photography or busy surfaces.

**Lockup rules**
- **Logomark alone** is sufficient in contexts ≤ 64px tall, or when brand context is otherwise clear.
- **Horizontal lockup** is preferred for page headers/footers.
- **Wordmark alone** is used when the logomark would appear adjacent to another visual of comparable size (co-branding).
- Clear space: at least the height of the wordmark's lowercase "n" on all sides.
- Nav height on the web: 72px; lockup height inside = 22px.

### Functional icons
- **Library:** Lucide (`https://unpkg.com/lucide@latest`), 1.5px stroke — closest CDN match to DM Sans.
- **Sizes:** 16, 20, 24, 32 px.
- **Color:** `currentColor` so icons inherit the adjacent text color.
- **Status note:** Arkenstone has not formally endorsed an icon library; Lucide is the system default until superseded.
- **Emoji / unicode symbols:** not used. Ever. This includes ✓ → ★ etc.

---

## Component patterns

### Buttons
Three core treatments. All buttons use DM Sans 500, 13px, `letter-spacing: 0.04em`, line-height 1, pill shape (`border-radius: 999px`), `1px` transparent border.

```css
.btn { font-family:"DM Sans"; font-weight:500; font-size:13px; padding:14px 26px;
       border-radius:999px; border:1px solid transparent; cursor:pointer;
       line-height:1; letter-spacing:.04em; }
.btn-primary   { background:#E85D2C; color:#fff; border-color:#E85D2C; }        /* orange */
.btn-primary:hover { background:#F47148; border-color:#F47148; }
.btn-secondary { background:transparent; color:#E8E4D4; border-color:rgba(232,228,212,0.35); }
.btn-olive     { background:#798760; color:#fff; border-color:#798760; }         /* rare */
.btn-ghost {                                                                     /* "Read memo →" */
  background:transparent; color:#E85D2C; border:0;
  border-bottom:1px solid #E85D2C; border-radius:0;
  font-family:"DM Mono"; font-size:11px; letter-spacing:.18em; text-transform:uppercase;
  padding: 0 0 4px;
}
.btn-sm { font-size:11px; padding:10px 20px; }
.btn-lg { font-size:15px; padding:18px 34px; }
```

**When to use which**
- **Primary (orange)**: single most important action on a page — "Start Now", "Get in touch", form submit.
- **Secondary (hairline)**: exploratory link-out — "Explore", "About".
- **Olive filled**: rarely; only on light surfaces where you need a brand pop without competing with orange.
- **Ghost / "read more"**: inline mono link with bottom-border, ALL CAPS, ends with `→`.

### Cards
Square, hairline, no shadow. Interior padding `24px` (space-5). On dark, use `rgba(232,228,212,0.02)` fill with `rgba(232,228,212,0.14)` border. Product UI cards may use `radius-md (4px)` — data/content cards stay at 0.

```css
.card {
  background: rgba(232,228,212,0.02);
  border: 1px solid rgba(232,228,212,0.14);
  padding: 24px 20px;
  display: flex; flex-direction: column; gap: 12px;
  border-radius: 0;
}
.card .kicker {
  font-family:"DM Mono"; font-size:10px; letter-spacing:.22em;
  text-transform:uppercase; color:#E85D2C;
}
.card .name {                               /* card title */
  font-family:"DM Sans"; font-weight:500; font-size:26px;
  line-height:1; letter-spacing:-0.01em;
  text-transform:uppercase; color:#E8E4D4; margin:0;
}
.card .desc { font-size:13px; line-height:1.5; color:#A8A392; margin:0; }
.card .tag {                                /* olive pill with status dot */
  font-family:"DM Mono"; font-size:9px; letter-spacing:.16em;
  text-transform:uppercase; color:#B8BFA0;
  padding:4px 8px; border:1px solid rgba(184,191,160,0.3);
  display:inline-flex; align-items:center; gap:6px;
}
.card .tag::before {
  content:""; width:6px; height:6px; border-radius:50%; background:#798760;
}
```

### Inputs
Borderless on the sides, hairline bottom only. No background fill in marketing contexts; subtle fill in product forms.

```css
label {
  display:flex; flex-direction:column; gap:6px;
  font-family:"DM Mono"; font-size:11px; letter-spacing:.18em;
  text-transform:uppercase; color:#A8A392;
}
input, select, textarea {
  font-family:"DM Sans"; font-size:15px;
  padding:12px 0 14px;
  background:transparent; color:#E8E4D4;
  border:0; border-bottom:1px solid rgba(232,228,212,0.25);
  border-radius:0; outline:none;
}
input:focus, select:focus, textarea:focus { border-bottom-color:#E85D2C; }
input::placeholder { color:#6E6A5E; }
```

**Marketing CTA variant** (fuller box): add background `rgba(232,228,212,0.04)`, full border `1px solid rgba(232,228,212,0.12)`, 14px padding on all sides.

### Tables
Monospace uppercase headers, hairline dividers, colored status dots.

```css
table { width:100%; border-collapse:collapse; font-size:13px; }
th {
  font-family:"DM Mono"; font-size:10px; letter-spacing:.18em;
  text-transform:uppercase; text-align:left; padding:10px;
  border-bottom:1px solid rgba(232,228,212,0.25);
  color:#A8A392; font-weight:400;
}
td { padding:12px 10px; border-bottom:1px solid rgba(232,228,212,0.08); color:#E8E4D4; }
.status-ok, .status-pend {
  font-family:"DM Mono"; font-size:10px; letter-spacing:.14em; text-transform:uppercase;
}
.status-ok   { color:#B8BFA0; }
.status-ok::before   { content:"●"; margin-right:6px; color:#798760; }
.status-pend { color:#E85D2C; }
.status-pend::before { content:"●"; margin-right:6px; color:#E85D2C; }
```

### Navigation bar
```css
.nav {
  position: sticky; top: 0; z-index: 40;
  background: rgba(47,55,35,0.72);
  backdrop-filter: saturate(1.1) blur(8px);
  height: 72px;
}
.nav-cta { /* outline pill — becomes filled on hover */
  padding: 10px 22px;
  background: transparent; color: #E85D2C;
  border: 1px solid #E85D2C; border-radius: 999px;
  font-size: 13px; font-weight: 500;
}
.nav-cta:hover { background:#E85D2C; color:#fff; }
```
Nav links: DM Sans 400, 14px, `letter-spacing: 0.02em`, `opacity: 0.88` default → `1.0` on hover, color shifts to orange.
Typical items: **About / Foundation / Cohort / Start Now** (Start Now is the CTA pill).

### Testimonial / pull-quote card
Single olive-olive card on black, with a clipped corner. Orange `"` quote mark in DM Serif Text. Do not render as a 2×2 grid.

```css
.memo-card {
  background:#2F3823; color:#E8E4D4;
  padding:40px 44px; display:flex; gap:28px;
  max-width:760px; margin:0 auto;
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - 24px), calc(100% - 24px) 100%, 0 100%);
}
.memo-quote-mark { font-family:"DM Serif Text"; color:#E85D2C; font-size:32px; line-height:1; }
```

### Compliance chips (hero)
Small monospace badges floating over the topographic hero, with a green signal dot:
```css
.hero-chip {
  background: rgba(22,22,22,0.85);
  border: 1px solid rgba(232,228,212,0.18);
  color: #E8E4D4;
  font-family:"DM Mono"; font-size:11px; letter-spacing:.08em;
  padding:6px 12px; border-radius:4px;
  display:inline-flex; align-items:center; gap:8px;
}
.hero-chip::before {
  content:""; width:8px; height:8px; border-radius:50%;
  background:#4CAF50; box-shadow:0 0 6px rgba(76,175,80,0.6);
}
```
Canonical chips: `DCAA`, `Secure HRIS`, `CMMC L2`, `ATO`, `CUI Enclave`, `FedRAMP`.

---

## Page patterns

### Marketing hero (dark)
- Background: olive-to-black gradient, `linear-gradient(180deg, #3A4225 0%, #2A3120 30%, #161616 100%)`.
- Topographic grid floor: repeating lines at 60px, masked with a radial ellipse, tilted with `perspective(900px) rotateX(62deg) scale(2.6)`, `opacity: 0.55`.
- Center geopin (olive hex) with an orange signal dot + glow beneath it.
- Floating `hero-chip`s scattered around the topo floor.
- Title: ALL CAPS DM Sans 700, clamp(56px, 8vw, 120px), `line-height: 0.95`, centered.
- Subhead: DM Sans 400, 16px, 440px max-width, centered.
- Single orange pill CTA.

### Statement section
Big ALL CAPS thesis sentence on black, flanked by hairline cross markers at all four corners. Max-width ~980px, centered.

### Pillar grid
2×2 grid (alternating dark + olive-tinted cells), each cell 80×64 padding with a 180×180 isometric illustration tile on one side.
- Pillar cells alternate: `dark | olive | olive | dark`.
- Pillar name: DM Sans 700, 26px, ALL CAPS, `letter-spacing: 0.02em`.
- Pillar desc: 14px, `#A8A392`, 380px max-width.
- Illustration: line-art isometric (Shield, Dossier, Approved Folder) in olive + orange strokes on the dark background.

### Segment strip (B&W photography)
Asymmetric four-column grid (`grid-template-columns: 2.4fr 1fr 1fr 1fr`, 4px gap). Each cell:
- Full-bleed B&W photo (`filter: grayscale(1) contrast(1.05) brightness(0.55)`).
- Orange 1.5px outline inset 12px with an irregular `clip-path` polygon (the "signature" orange outline).
- Segment name in orange, DM Sans 700, 15px, ALL CAPS.
- Only the main (first, 2.4fr) cell shows a description.

Canonical segments: **Defense Industrial Base / Dual-Use Companies / Defense Tech / Prime-Level Operators**.

### CTA section (contact)
2-column layout, 72px gap, 1040px max-width:
- Left: ALL CAPS headline + secondary gray copy.
- Right: grid form (first/last/company/email in 2 cols; message textarea spanning 2; orange pill submit spanning 2).
- Flanked by `.plus` cross markers.

### Footer
Dark olive (`#2A3120`), 32px/40px padding.
- Left: "Bonded ESAC Accredited" badge (bone fill, black ink, 3-line DM Mono) + `© 2026 Arkenstone`.
- Right: "Follow Us" / LinkedIn `in` square / "Made in the USA".
- All text is DM Mono 10px, `letter-spacing: 0.18em`, ALL CAPS.

---

## Drop-in CSS tokens

Save as `arkenstone-tokens.css` and `@import` it at the top of your stylesheet.

```css
/* ============================================================
   Arkenstone Defense — Tokens
   ============================================================ */
:root {
  /* Core ----------------------------------------------------- */
  --brand-black:        #161616;
  --brand-white:        #FFFFFF;
  --brand-bone:         #E8E4D4;
  --brand-ink-on-dark:  #E8E4D4;

  /* Olive ---------------------------------------------------- */
  --olive-900: #1F2414;
  --olive-800: #2A3120;
  --olive-700: #414C32;
  --olive-600: #5D6946;
  --olive-500: #798760;
  --olive-200: #B8BFA0;

  /* Orange --------------------------------------------------- */
  --orange-600: #C94A1E;
  --orange-500: #E85D2C;
  --orange-400: #F47148;

  /* Earth ---------------------------------------------------- */
  --earth-500: #8C8271;
  --earth-200: #D3CFC3;
  --earth-900: #33322E;

  /* Links ---------------------------------------------------- */
  --link:         #2A6EBB;
  --link-visited: #593E9C;

  /* Semantic ------------------------------------------------- */
  --bg:            var(--olive-800);
  --bg-deep:       var(--olive-900);
  --bg-inverse:    var(--brand-bone);
  --bg-muted:      #3A4228;
  --fg:            var(--brand-bone);
  --fg-inverse:    var(--brand-black);
  --fg-muted:      #A8A392;
  --fg-subtle:     #6E6A5E;
  --fg-on-orange:  var(--brand-white);
  --border:        rgba(232,228,212,0.18);
  --border-strong: rgba(232,228,212,0.35);
  --border-subtle: rgba(232,228,212,0.08);

  /* Type ----------------------------------------------------- */
  --font-sans:  "DM Sans", "Helvetica Neue", Arial, sans-serif;
  --font-mono:  "DM Mono", ui-monospace, "SF Mono", Menlo, monospace;
  --font-serif: "DM Serif Text", Georgia, serif;

  --fs-display: 64px;
  --fs-h1:      48px;
  --fs-h2:      36px;
  --fs-h3:      24px;
  --fs-h4:      18px;
  --fs-body:    16px;
  --fs-small:   14px;
  --fs-meta:    11px;

  /* Spacing (4pt) -------------------------------------------- */
  --space-1:   4px;
  --space-2:   8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-5:  24px;
  --space-6:  32px;
  --space-7:  48px;
  --space-8:  64px;
  --space-9:  96px;
  --space-10:128px;

  /* Radii ---------------------------------------------------- */
  --radius-0:   0;
  --radius-sm:  2px;
  --radius-md:  4px;
  --radius-lg:  8px;
  --radius-pill: 999px;

  /* Borders -------------------------------------------------- */
  --hairline:        1px solid var(--border);
  --hairline-subtle: 1px solid var(--border-subtle);
  --hairline-strong: 1px solid var(--border-strong);

  /* Shadows -------------------------------------------------- */
  --shadow-0: none;
  --shadow-1: 0 1px 2px rgba(22,22,22,0.06), 0 1px 0 rgba(22,22,22,0.04);
  --shadow-2: 0 8px 24px -8px rgba(22,22,22,0.18), 0 2px 4px rgba(22,22,22,0.06);

  /* Motion --------------------------------------------------- */
  --ease-standard: cubic-bezier(.2, 0, 0, 1);
  --dur-fast: 120ms;
  --dur-base: 200ms;
}

/* Base ----------------------------------------------------- */
html, body {
  margin: 0;
  font-family: var(--font-sans);
  color: var(--fg);
  background: var(--bg);
  font-size: var(--fs-body);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

h1, .h1 { font-weight:500; font-size:var(--fs-h1); line-height:1.05; letter-spacing:-0.015em; margin:0 0 var(--space-4); }
h2, .h2 { font-weight:500; font-size:var(--fs-h2); line-height:1.1;  letter-spacing:-0.01em;  margin:0 0 var(--space-3); }
h3, .h3 { font-weight:600; font-size:var(--fs-h3); line-height:1.2;  margin:0 0 var(--space-3); }
h4, .h4 { font-weight:600; font-size:var(--fs-h4); line-height:1.3;  margin:0 0 var(--space-2); }

.display {
  font-family: var(--font-sans);
  font-weight: 700;
  font-size: clamp(56px, 8vw, 120px);
  line-height: 0.95;
  letter-spacing: -0.02em;
  text-transform: uppercase;
}

p, .body { font-weight:400; font-size:var(--fs-body); line-height:1.55; text-wrap:pretty; }
small, .small { font-size:var(--fs-small); color:var(--fg-muted); }

.eyebrow, .meta, .chrome-meta {
  font-family: var(--font-mono);
  font-size: var(--fs-meta);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--fg);
}

code, pre, kbd, samp { font-family:var(--font-mono); font-size:0.92em; }
code { background:var(--bg-muted); padding:1px 6px; border-radius:var(--radius-sm); }

.serif { font-family:var(--font-serif); font-weight:400; }

a { color:var(--link); text-decoration:underline; text-underline-offset:2px; text-decoration-thickness:1px; }
a:visited { color:var(--link-visited); }
a:hover   { text-decoration-thickness:2px; }

hr { border:0; border-top:var(--hairline); margin:var(--space-6) 0; }

.surface-olive { background:var(--olive-500); color:var(--fg-on-orange); }
.surface-dark  { background:var(--brand-black); color:var(--brand-bone); }
.surface-bone  { background:var(--brand-bone); color:var(--brand-black); }
```

### Font loading

Use Google Fonts if you can't ship the TTFs:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,100..1000;1,100..1000&family=DM+Mono:ital,wght@0,300..500;1,300..500&family=DM+Serif+Text:ital@0;1&display=swap">
```

---

## Tailwind config

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        brand: { black: "#161616", white: "#FFFFFF", bone: "#E8E4D4" },
        olive: {
          900:"#1F2414", 800:"#2A3120", 700:"#414C32",
          600:"#5D6946", 500:"#798760", 200:"#B8BFA0",
        },
        orange: { 600:"#C94A1E", 500:"#E85D2C", 400:"#F47148" },
        earth: { 900:"#33322E", 500:"#8C8271", 200:"#D3CFC3" },
        ink: { DEFAULT:"#E8E4D4", muted:"#A8A392", subtle:"#6E6A5E" },
      },
      fontFamily: {
        sans:  ['"DM Sans"', "Helvetica Neue", "Arial", "sans-serif"],
        mono:  ['"DM Mono"', "ui-monospace", "Menlo", "monospace"],
        serif: ['"DM Serif Text"', "Georgia", "serif"],
      },
      fontSize: {
        meta:    ["11px", { letterSpacing: "0.12em", lineHeight: "1.3" }],
        display: ["clamp(56px, 8vw, 120px)", { lineHeight: "0.95", letterSpacing: "-0.02em" }],
      },
      borderRadius: { pill: "999px" },
      boxShadow: {
        1: "0 1px 2px rgba(22,22,22,0.06), 0 1px 0 rgba(22,22,22,0.04)",
        2: "0 8px 24px -8px rgba(22,22,22,0.18), 0 2px 4px rgba(22,22,22,0.06)",
      },
      transitionTimingFunction: { standard: "cubic-bezier(.2,0,0,1)" },
      transitionDuration: { fast: "120ms", base: "200ms" },
    },
  },
};
```

---

## Do / Don't

**Do**
- Default to the dark surface (olive-800) for marketing; bone + ink for in-product.
- Use ALL CAPS + `letter-spacing` on chrome, eyebrows, display titles, and segment names.
- Use square corners everywhere except CTA buttons (pill) and overlay surfaces (8px).
- Use the "+" cross-marker at section corners for marketing framing.
- Lead with text; add an icon only if it materially clarifies.
- Spell compliance standards exactly: CMMC Level II, NIST 800-171, DFARS 7012.
- Keep animations under 200ms with the standard ease.

**Don't**
- No emoji. No ✓ → ★.
- No gradients other than the hero olive-to-black.
- No glassmorphism, no backdrop-filter blur (except the nav bar).
- No colored shadows, no inner shadows, no drop-shadow flourishes.
- No rounded corners on cards, photos, or data tables.
- No bright accent colors. Orange and olive are the only accents.
- No exclamation points. No superlatives. Don't address the reader as "you".
- Don't use DM Serif Text in UI or product headings.

---

## Source files

This document was distilled from the Arkenstone design bundle:
- `colors_and_type.css` — the canonical token file.
- `ui_kits/website/` — real website recreation (`site.css`, JSX components for Nav/Hero/Statement/Pillars/Segments/Memoranda/CTA/Footer).
- `slides/` — PPTX-faithful slide layouts (Intro, Title, Section Header, Title+Content, Two Content, Tagline, Contact).
- `preview/` — component specimens (buttons, cards, inputs, tables, spacing, colors, type).
- `assets/` — logomark, wordmark, horizontal-lockup SVGs (Pure / Brand × black / white).
- `fonts/` — DM Sans (full family), DM Mono (Regular + LightItalic), DM Serif Text (Regular).
