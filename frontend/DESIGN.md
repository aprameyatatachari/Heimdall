# Heimdall — Design Language

The authoritative visual and motion specification for the Heimdall frontend.
Where this file and `prompt.md` disagree on appearance, **this file wins**.
Where this file and `CLAUDE.md` disagree on product rules, **`CLAUDE.md` wins**.

Derived from the mockups in `resources/mockups/`, the supplied inspiration
imagery, and the motion references
[era-residence.com](https://www.era-residence.com) and
[lamalama.com](https://lamalama.com).

---

## 1. The idea

Heimdall is the watchman on the bridge. He sees further than anyone else and he
says only what he actually sees. The interface has to feel like that: a high
vantage point, a wide horizon, and calm, exact reporting.

The product is an **educational risk-analysis tool**. It never tells anyone what
to buy. So the design is allowed to be cinematic about _vision and vigilance_,
and is never allowed to be cinematic about _gains_. No rocket arrows, no bull or
bear imagery, no triumphant green, no urgency theatre.

> "A clearer tomorrow, through a wider horizon."

### 1.1 Two realms

The mockups contain two distinct visual registers. Keeping them separate is the
single most important structural decision in this system.

|         | **Outer Realm**                                      | **Inner Realm**                                                                    |
| ------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Screens | Splash, landing, marketing, auth, methodology, legal | Everything behind the login: portfolios, analytics, stress tests, signals, reports |
| Feel    | Cinematic, full-bleed, spacious, slow                | Quiet, dense, precise, fast                                                        |
| Imagery | Hero photography fills the frame                     | Imagery reduced to near-invisible texture                                          |
| Type    | Display serif at heroic sizes                        | UI sans, tabular figures                                                           |
| Motion  | Scroll-driven, orchestrated, generous                | Functional only: 120–200ms state changes                                           |
| Density | One idea per viewport                                | Information-dense panels                                                           |

A user crossing from the Outer Realm to the Inner Realm should feel they have
**arrived somewhere and started working**. That crossing is the Bifröst
transition (§7.4).

---

## 2. Colour

Sampled from `resources/mockups/`. The palette is a near-black blue-tinted
ground with a single warm gold accent. There is no second accent hue.

### 2.1 Tokens

```css
:root {
  /* --- Ground: near-black, cool, faintly blue ------------------------- */
  --hm-void: #04090c; /* deepest — page behind everything        */
  --hm-abyss: #070d11; /* app background (sampled from mockups)   */
  --hm-surface: #0b131a; /* panels, cards                           */
  --hm-surface-2: #101a22; /* raised: inputs, hovered rows, popovers   */
  --hm-surface-3: #16222c; /* highest: menus, modals, tooltips        */

  /* --- Edges ---------------------------------------------------------- */
  --hm-line: #1b2831; /* default hairline                        */
  --hm-line-soft: #141f27; /* internal dividers inside a panel        */
  --hm-line-strong: #2a3a46; /* emphasised edge, table header rule      */

  /* --- Ink ------------------------------------------------------------ */
  --hm-ink: #f2f5f7; /* primary text                            */
  --hm-ink-muted: #b6bcc1; /* secondary text (sampled)                */
  --hm-ink-dim: #7c868e; /* tertiary: captions, units, axis labels  */
  --hm-ink-faint: #4c565e; /* disabled, placeholder, unavailable mark */

  /* --- Gold: the single accent (sampled #FDD89D) ---------------------- */
  --hm-gold: #fdd89d; /* primary actions, focus, active state    */
  --hm-gold-bright: #fce8b3; /* hover / highlight                       */
  --hm-gold-deep: #c9a46b; /* pressed, borders on gold surfaces       */
  --hm-gold-wash: rgba(253, 216, 157, 0.1); /* tinted fills           */
  --hm-on-gold: #100c05; /* text on a gold fill                     */

  /* --- Horizon: the Bifröst light, used sparingly --------------------- */
  --hm-horizon-1: #8fb4d9; /* cold sky blue                           */
  --hm-horizon-2: #c9b7e8; /* violet                                  */
  --hm-horizon-3: #f0c9a8; /* warm dawn                               */

  /* --- Semantics: dusty, never neon ----------------------------------- */
  --hm-positive: #7fa88a; /* gain                                    */
  --hm-positive-dim: #2a3a31;
  --hm-negative: #c08078; /* loss (sampled family #96605D)           */
  --hm-negative-dim: #3a2b29;
  --hm-caution: #d6b06a; /* attention, not alarm                    */
  --hm-neutral: #8a9299; /* flat / no change / not applicable       */

  /* --- Severity (Gjallarhorn). Never the only signal. ----------------- */
  --hm-sev-info: #8fa6b8;
  --hm-sev-elevated: #d6b06a;
  --hm-sev-high: #d08f63;
  --hm-sev-critical: #c4675c;
}
```

### 2.2 Rules

1. **One accent.** Gold means _"this is the action"_ or _"this is where you
   are."_ If gold appears twice in a viewport for two different reasons, one of
   them is wrong.
2. **Gold is never a data colour.** Charts do not plot in gold, except the
   single "your portfolio" series, which is the subject of the chart.
3. **Green is never celebratory.** `--hm-positive` is a dusty sage. A gain is a
   fact, not good news. Losses and gains get equal visual weight.
4. **Colour never carries meaning alone.** Every positive/negative value also
   carries an explicit `+` or `−` sign. Every severity also carries an icon and
   a word. This is a hard requirement from `CLAUDE.md`, not a preference.
5. **Contrast floor.** Body text ≥ 4.5:1, large display text and non-text UI
   ≥ 3:1 against its actual backdrop — _including over photography_. If a hero
   image is too bright behind text, the scrim (§5.6) is too weak.

### 2.3 Chart series palette

Ordered, colour-blind-safe, all ≥ 3:1 on `--hm-surface`. Series 1 is always the
user's portfolio.

```css
--hm-series-1: #fdd89d; /* portfolio (gold — the subject)  */
--hm-series-2: #8fb4d9; /* benchmark                       */
--hm-series-3: #a9c4a0;
--hm-series-4: #c9b7e8;
--hm-series-5: #d9a38b;
--hm-series-6: #7fa5a8;
--hm-series-7: #b9a7c4;
--hm-series-8: #9aa3ab;
```

Beyond eight categories, group the tail into "Other" rather than inventing
colours. Series must also differ by dash pattern or marker so the chart survives
greyscale printing — reports are printed.

---

## 3. Typography

### 3.1 The four faces

| Role          | Face               | Source                | Used for                                       |
| ------------- | ------------------ | --------------------- | ---------------------------------------------- |
| **Wordmark**  | Elder Futhark      | Self-hosted, see §3.2 | The word "HEIMDALL" only                       |
| **Display**   | Cormorant Garamond | Google Fonts          | Outer Realm headlines, pull quotes             |
| **Ritual**    | Skranji            | Google Fonts          | Eyebrows, section numerals, Gjallarhorn titles |
| **UI / Data** | Inter              | Google Fonts          | Everything else, all numbers                   |

```css
--hm-font-rune: "Elder Futhark", var(--hm-font-display);
--hm-font-display: "Cormorant Garamond", "EB Garamond", Georgia, serif;
--hm-font-ritual: "Skranji", var(--hm-font-display);
--hm-font-ui: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
--hm-font-mono: "IBM Plex Mono", ui-monospace, "Cascadia Code", monospace;
```

**Skranji is deliberately bounded.** It has two weights, tight spacing and heavy
texture. It is excellent as a small, letterspaced, uppercase label and poor as a
headline or body face. Permitted: eyebrow labels, section numerals, Gjallarhorn
signal titles, the `SEE FURTHER` lockup line. Forbidden: body copy, table
content, form labels, anything below 11px, anything above 28px.

**Inter carries every number.** Enable tabular figures globally on numeric
content so columns of currency align and digits do not jitter when a value
updates:

```css
.hm-numeric {
  font-feature-settings:
    "tnum" 1,
    "zero" 1;
  font-variant-numeric: tabular-nums slashed-zero;
}
```

### 3.2 The wordmark is artwork

The runic wordmark ships as an image, not as type, so Elder Futhark never has to
be licensed or self-hosted and the mark is identical on every machine. See §4.1
for the accessibility contract that comes with that.

### 3.3 Scale

A modular scale, ratio 1.25, fluid between 360px and 1440px viewports.

```css
--hm-text-2xs: 0.6875rem; /* 11px — eyebrows, units, axis labels        */
--hm-text-xs: 0.75rem; /* 12px — captions, table meta, disclaimers   */
--hm-text-sm: 0.875rem; /* 14px — dense table content, form helpers   */
--hm-text-base: 1rem; /* 16px — body, inputs. Never smaller for body */
--hm-text-lg: 1.125rem; /* 18px — lead paragraphs                     */
--hm-text-xl: 1.5rem; /* 24px — card titles, metric values          */
--hm-text-2xl: 2rem; /* 32px — page titles                         */
--hm-text-3xl: clamp(2.5rem, 1.6rem + 4vw, 4rem);
--hm-text-4xl: clamp(3.25rem, 1.8rem + 6.4vw, 6rem); /* hero headline */
--hm-text-5xl: clamp(4rem, 1.5rem + 11vw, 9rem); /* splash mark   */
```

Line height: `1.1` for display, `1.35` for UI, `1.6` for prose. Measure caps at
**68 characters** for prose and **46 characters** for display.

### 3.4 Eyebrow style

The recurring `MARKETS | RISK | CLARITY` and `DISCIPLINE / INTELLIGENCE /
A WIDER HORIZON` marks in the mockups:

```css
.hm-eyebrow {
  font-family: var(--hm-font-ritual);
  font-size: var(--hm-text-2xs);
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: var(--hm-ink-dim);
}
```

---

## 4. Brand assets

### 4.1 The logo

The supplied artwork is a **horn fused with an open eye**. It ships as the mark
alone and as a flattened lockup with the runic wordmark, each light and dark.

**The wordmark is type, not artwork.** It reads `HEIMDALL` in Latin letters, and
hovering it turns the whole word into runes — one letter after the next, left to
right, each arriving out of a blur — and letting go sweeps it back to Latin the
same way, left to right again. The runic layer reads `HEIMDALR`, the Old Norse form.

The effect is pure CSS `:hover`. The cascade is eight transition delays derived
from each letter's index: 45ms apart on the turn and 30ms on the return, both
running left to right, so the word always reads in one direction whichever
alphabet it is heading for. No pointer listener to throttle, no animation frame
to cancel, nothing to leak.

Eight equal columns rather than tracked text, because the rune advances run
about twelve per cent narrower than the Latin ones; matched tracking drifts the
two alphabets apart letter by letter, and the runes would no longer sit under
the letters they replace.

**On the splash the mark joins in.** The lockup is one hover target: gold washes
across the mark from left to right while the letters turn beneath it, so the two
read as a single movement rather than two effects that fired together. Hovering
the mark turns the letters, and hovering the letters washes the mark.

The mark is drawn by masking its own artwork rather than by tinting the image —
the supplied file is white on transparent, so its alpha is the shape, and
masking a coloured box with it gives a colour that can actually animate. No
filter chain over a bitmap reaches that colour cleanly.

Gold arrives as a wipe and leaves as a fade. A wipe running back right to left
would fight the letters, which settle to Latin left to right; the clip resets
only once the fade has finished, so the gold never vanishes early.

| Variant  | Use                                                                                                  |
| -------- | ---------------------------------------------------------------------------------------------------- |
| Wordmark | The default identity. Header, footer, auth, and the splash lockup.                                   |
| `mark`   | Where type will not do: favicon, above the auth card, empty and error states, the Gjallarhorn glyph. |
| `full`   | The flattened lockup. Report cover and social card, where there is no cursor to reveal anything.     |

**Spelling follows the alphabet.** In runes it is HEIMDALLR, the Old Norse form,
which is what the flattened artwork spells; the live wordmark carries its
eight-letter form, `HEIMDALR`. In Latin letters it is **Heimdall** — page
titles, prose, reports, documentation, and the wordmark's accessible name, which
is Latin text standing in for the mark. Never write "Heimdallr" in Latin letters.

The runic layer is hidden from assistive technology and excluded from selection,
so the name is announced once and a copy of the wordmark yields `HEIMDALL`
rather than the two alphabets interleaved letter by letter.

The rune face is **Elder Futhark by Curtis Clark (1996)**, subset to eight
letters and self-hosted. It is licensed _free for personal use_; see `README.md`
before deploying commercially. It maps rune shapes onto Latin letter positions
rather than onto the Unicode runic block, which is why both layers are real
text.

The mark's source files place the artwork inside a 2752×1536 canvas that is
mostly empty. They are trimmed to their alpha bounding box and exported to
`public/brand/` as WebP with a PNG fallback; the raw files stay in `resources/`
as the source of truth.

### 4.2 Asset inventory

```text
resources/                       sources, never served
  logos/HEIMDALL_full_{white,black}.png       lockup
  logos/HEIMDALL_onlylogo_white.png           mark
  logos/HEIMDALL_onlyLogo_black.png
  logos/HEIMDALL_onlyText_{white,black}.png   wordmark
  images/bg.png                 1672×941 hero vista, in use; a ≥2560px wide
                                regeneration is still wanted (PROMPTS.md §2)
  mockups/                      reference only

public/brand/                    served, generated from the above
  {mark,wordmark,full}-{white,black}.{webp,png}
public/favicon*.png, favicon.ico the mark in gold on the app background
```

Regenerate the served files from the sources rather than editing them by hand.

## 5. Surfaces, space and form

### 5.1 Spacing

A 4px base. Use the token, never a raw pixel value.

```css
--hm-space-1: 4px;
--hm-space-2: 8px;
--hm-space-3: 12px;
--hm-space-4: 16px;
--hm-space-5: 24px;
--hm-space-6: 32px;
--hm-space-7: 48px;
--hm-space-8: 64px;
--hm-space-9: 96px;
--hm-space-10: 128px;
--hm-space-11: 192px;
```

Outer Realm sections breathe at `--hm-space-9` to `--hm-space-11`. Inner Realm
panels sit at `--hm-space-4` to `--hm-space-6`. Page gutter: 16px mobile, 32px
tablet, 64px desktop. Max content width 1440px; prose column 680px.

### 5.2 Radii

```css
--hm-radius-sm: 4px; /* chips, badges, tags        */
--hm-radius-md: 8px; /* inputs, buttons            */
--hm-radius-lg: 12px; /* cards, panels              */
--hm-radius-xl: 20px; /* auth card, modal           */
--hm-radius-full: 999px;
```

### 5.3 The panel

The defining Inner Realm surface. A dark glass plate with a single hairline and
a barely-there top highlight, as though catching light from above.

```css
.hm-panel {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.028) 0%, rgba(255, 255, 255, 0) 40%),
    var(--hm-surface);
  border: 1px solid var(--hm-line);
  border-radius: var(--hm-radius-lg);
  box-shadow:
    0 1px 0 0 rgba(255, 255, 255, 0.03) inset,
    0 12px 32px -18px rgba(0, 0, 0, 0.9);
}
```

### 5.4 The glass card (Outer Realm only)

The auth cards in the mockups float over photography:

```css
.hm-glass {
  background: rgba(8, 13, 18, 0.72);
  backdrop-filter: blur(24px) saturate(120%);
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: var(--hm-radius-xl);
  box-shadow: 0 32px 80px -32px rgba(0, 0, 0, 0.85);
}
```

Always ship an opaque fallback — `backdrop-filter` fails on some browsers and
the card must stay legible when it does.

### 5.5 Elevation

Four levels only: flat (`--hm-abyss`), panel, raised (popover, dropdown), modal.
Depth comes from the hairline and the inset highlight, not from heavy drop
shadows. There is no level five.

### 5.6 Scrims

Any text over photography sits on a scrim. Two standard forms:

```css
--hm-scrim-bottom: linear-gradient(
  to top,
  rgba(4, 9, 12, 0.94) 0%,
  rgba(4, 9, 12, 0.72) 28%,
  rgba(4, 9, 12, 0) 62%
);
--hm-scrim-left: linear-gradient(
  to right,
  rgba(4, 9, 12, 0.92) 0%,
  rgba(4, 9, 12, 0.78) 45%,
  rgba(4, 9, 12, 0) 70%
);
```

Verify the contrast against the **brightest pixel** the text can overlap, at
every breakpoint. A hero that passes on desktop and fails on mobile is a fail.

These stop positions are measured against the shipping hero, not chosen by eye.
An earlier ramp that looked fine left the headline at **3.34:1** over a patch of
sunlit cloud; the values above hold the worst pixel under the headline at
**8.53:1**. Re-measure whenever the hero image changes — the numbers belong to
the photograph, not to the gradient.

### 5.7 Texture

A fine film grain over full-bleed imagery stops gradient banding in the dark
sky and gives the Outer Realm its photographic feel.

```css
.hm-grain::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: url("/textures/grain.png");
  opacity: 0.045;
  mix-blend-mode: overlay;
}
```

Lama Lama's dot-matrix idea is adopted only for the loading state (§7.2), never
behind data.

---

## 6. Components

### 6.1 Buttons

| Variant   | Fill        | Text             | Border             | Use                            |
| --------- | ----------- | ---------------- | ------------------ | ------------------------------ |
| Primary   | `--hm-gold` | `--hm-on-gold`   | none               | One per view. The main action. |
| Secondary | transparent | `--hm-ink`       | `--hm-line-strong` | Alternative action             |
| Ghost     | transparent | `--hm-ink-muted` | none               | Tertiary, toolbar              |
| Danger    | transparent | `--hm-negative`  | `--hm-negative`    | Delete, dismiss                |

Heights: 32 / 40 / 48px. Hover lifts to `--hm-gold-bright` over 140ms; press
drops to `--hm-gold-deep` with no vertical translation. Minimum touch target
44×44px including padding.

The era-residence label-swap is the signature hover for Outer Realm buttons: two
stacked copies of the label, the first sliding up and out while the second
slides up and in, 320ms, `--hm-ease-out`. Disabled under reduced motion — the
label simply changes colour.

### 6.2 Inputs

40px tall, `--hm-surface-2` fill, `--hm-line` border, 8px radius, leading icon
in `--hm-ink-dim` (as in the auth mockups). Focus is a 2px `--hm-gold` ring at
2px offset — **never** `outline: none` without a replacement. Errors put a
`--hm-negative` border _and_ a message below with a warning icon; the message is
tied to the field with `aria-describedby` and the field gets
`aria-invalid="true"`.

### 6.3 The metric tile

The most important component in the product. Every number the backend produces
arrives with a unit, a period and caveats, and the tile shows all of it.

```
┌─────────────────────────────────────────┐
│ VOLATILITY (ANNUALIZED)          (i)    │  eyebrow + definition affordance
│ 21.88%                                  │  value, tabular figures
│ annualized · 2019-01-02 → 2023-12-29    │  what it means and over what
│ 1,257 observations                      │  provenance
└─────────────────────────────────────────┘
```

Hard rules:

- The unit is **always** visible, never only in a tooltip.
- "Annualized" and "daily" are never both rendered the same way. Annualized
  values carry the word; daily values carry the word. Neither is ever bare.
- A value that could not be computed renders `—` with the backend's reason,
  never `0`, never an empty cell, never a dash with no explanation:

  ```
  INFORMATION RATIO
  —  unavailable
  Tracking error is zero, so the ratio is undefined.
  ```

- Value-at-Risk tiles always carry "estimate at 95% confidence — not a maximum
  possible loss" in the caption. This is non-negotiable.

### 6.4 Severity indicator

Colour, icon and word, always all three:

| Severity      | Icon       | Colour              | Shape cue |
| ------------- | ---------- | ------------------- | --------- |
| Informational | circle-i   | `--hm-sev-info`     | circle    |
| Elevated      | flag       | `--hm-sev-elevated` | pennant   |
| High          | triangle-! | `--hm-sev-high`     | triangle  |
| Critical      | octagon-!  | `--hm-sev-critical` | octagon   |

The backend already names these icons in `SEVERITY_ICONS`; map to that, do not
invent a parallel scheme. Severity never blinks, pulses or animates. Nothing in
this product makes a sound.

### 6.5 Tables

Header row in `--hm-text-2xs` uppercase `--hm-ink-dim` over `--hm-line-strong`.
Rows 48px, hover `--hm-surface-2`. Numbers right-aligned and tabular; text
left-aligned. Sticky header on scroll. On mobile, tables become stacked
definition cards — never a horizontal scroll that hides the symbol column.

### 6.6 Charts

Grid lines `--hm-line-soft` at 12% opacity, horizontal only. Axis labels
`--hm-text-2xs` in `--hm-ink-dim`. Every chart has a visible title, labelled
axes with units, and a legend when more than one series is plotted.

Every chart ships with a **"View as table"** toggle exposing the same numbers as
a real `<table>`. That is the accessible alternative required by the acceptance
criteria, and it is also how a user checks a figure.

Gaps in data are **gaps** — the line breaks. Never interpolate across missing
observations, and never drop a missing point to zero.

### 6.7 Disclaimer surfaces

The standard disclaimer appears in the footer of every page, on every generated
report, and adjacent to every stress-test result and signal list:

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.

Styled as `--hm-text-xs` in `--hm-ink-dim` on `--hm-surface`. Present and
readable — never a collapsed accordion, never 4px grey-on-grey.

---

## 7. Motion

The references are built on **Lenis** (smooth scroll), **GSAP** with
**ScrollTrigger**, **SplitText** and **CustomEase**, and **Barba**-style page
transitions. Adopt that stack. Verify current GSAP plugin licensing before
shipping SplitText.

### 7.1 Principles

1. **Motion explains, it never decorates data.** The Outer Realm may be
   choreographed. The Inner Realm gets 120–200ms functional transitions and
   nothing more.
2. **Numbers do not animate on update.** A count-up is permitted once, on first
   mount, in the Outer Realm only. A figure that changes because data refreshed
   changes instantly — animating it invites misreading a transient value.
3. **Nothing flashes.** No strobe, no pulse on alerts, no attention-seeking
   loops. Explicitly forbidden by the product rules.
4. **`prefers-reduced-motion: reduce` is a full stop.** Disable Lenis, kill
   every ScrollTrigger timeline, replace reveals with instant visibility, and
   reduce transitions to opacity at ≤100ms. The site must be completely usable
   and lose no information.

### 7.2 Easing and duration

```css
--hm-ease-out: cubic-bezier(0.16, 1, 0.3, 1); /* entrances    */
--hm-ease-in-out: cubic-bezier(0.76, 0, 0.24, 1); /* transitions  */
--hm-ease-soft: cubic-bezier(0.33, 1, 0.68, 1); /* UI states    */

--hm-dur-instant: 100ms;
--hm-dur-fast: 160ms;
--hm-dur-base: 240ms;
--hm-dur-slow: 480ms;
--hm-dur-cinematic: 900ms;
```

### 7.3 The scroll reveal

The house reveal, applied to headlines and section content:

- Split the headline to **lines** (not characters — character stagger on a
  serif at hero size looks nervous).
- Each line starts `y: 110%` inside an `overflow: hidden` mask, `opacity: 0`.
- Stagger 80ms, duration 900ms, `--hm-ease-out`.
- Fires at `start: "top 80%"`, `once: true`. Content **never** animates out on
  scroll-up — a user scrolling back must not watch text leave.

Images rise 40px and fade over 700ms. Panels and metric tiles in the Inner Realm
fade only, 200ms, no translation.

### 7.4 Signature transitions

**The Gate (splash → landing).** The single authored moment of the whole site,
and the only place a shader is allowed.

The landing page is behind the plate the whole time, already at the top of the
document and completely still. The plate dissolves off it in place: a WebGL
shader gives each pixel a resistance made mostly of drifting noise, with a
vertical bias so the sky goes first and the horizon band holds longest — the
citadel and the watchman on his cliff are the last things the mist takes. The
dissolving edge picks up `--hm-gold`, so it reads as light in cloud rather than
as an eraser. Underneath, the landing hero's own photograph of the same world
comes through, and the two cross-dissolve.

Mechanics that matter:

- **The page does not move.** An earlier build gave the gate a scroll runway and
  let the landing page arrive in normal flow beneath it, which meant the page
  slid up into view as the mist cleared instead of being revealed by it. Holding
  it still is the whole point of the effect.
- **That costs one deliberate trade:** while the gate is open the document does
  not scroll, and the gesture drives the reveal. Bounded to one screen, once per
  session, finished by scroll, swipe, arrow, space, Escape or the control, and
  released for good afterwards. This is the only place in the product allowed to
  take the scroll.
- **Progress is one number on `<html>`,** written as `--gate-progress`. The
  plate, its type and the page header are pure functions of it, so the browser
  composites the reveal without React re-rendering.
- **Every part of the effect is optional.** No WebGL, a lost context, a texture
  that will not decode, or a reduced-motion preference each drop to the still
  photograph fading on the same progress. The gate opens either way.
- Never in front of a direct deep link.

**The Bifröst (Outer → Inner).** Crossing into the app after sign-in: a soft
spectral sweep using `--hm-horizon-1/2/3` passes once across the viewport over
600ms as the shell fades in. Once per session, on sign-in only. Not on every
navigation.

**Route changes inside the app.** 160ms opacity crossfade. Nothing else. The
data is the point.

**The Horn (Gjallarhorn only).** When the signals panel first mounts with at
least one open signal, the horn-and-eye glyph draws its stroke once over 800ms.
It does not repeat, does not loop, and does not fire on refresh. A signal is an
observation, not an event to dramatise.

### 7.5 Hover

Cards lift 2px and brighten their border to `--hm-line-strong` over 160ms. Table
rows tint only. Lama Lama's cursor-following image cluster is adopted **only**
on the marketing "Insights" list, never in the app.

---

## 8. Layout

### 8.1 Outer Realm

Transparent header over the hero that gains `--hm-surface` with a hairline after
80px of scroll. Wordmark left, nav centre, `Sign In` (secondary) and
`Get Started` (primary) right — exactly as the landing mockup. Sections are full
viewport-height where they carry an image, auto-height where they carry prose.

### 8.2 Inner Realm

Fixed 64px top bar: wordmark left, primary nav centre (Portfolios, Analytics,
Stress Test, Signals, Reports), account avatar right. Content max-width 1440px,
64px gutters. A 12-column grid at ≥1024px, 8 at ≥768px, 4 below.

Standard dashboard rhythm, from the mockups: page title and portfolio selector →
metric tile row → primary chart → two-column supporting panels → disclaimer.

### 8.3 Breakpoints

```
sm 640   md 768   lg 1024   xl 1280   2xl 1536
```

Design at 1440. Verify at 360. The Inner Realm must be genuinely usable on a
phone — that means stacked cards and a table-alternative view, not a pinch-zoom
of the desktop layout.

---

## 9. Accessibility

Not a phase-12 checklist. These are build-time requirements.

- **Contrast**: 4.5:1 body, 3:1 large text and UI boundaries, measured over the
  real backdrop including images.
- **Focus**: visible on every interactive element, 2px `--hm-gold` at 2px
  offset. Never removed.
- **Keyboard**: every flow completable without a mouse. Modals trap focus and
  restore it on close. A skip-to-content link is the first tabbable element.
- **Motion**: §7.1 rule 4.
- **Colour independence**: §2.2 rule 4.
- **Runes**: §3.2 rule 3.
- **Charts**: §6.6 table alternative.
- **Live regions**: `aria-live="polite"` for async results. Never `assertive` —
  nothing here is an emergency.
- **Language**: `lang="en"` on `<html>`.
- **Targets**: 44×44px minimum.

---

## 10. Voice

Calm, precise, transparent about uncertainty.

| Write                                | Not             |
| ------------------------------------ | --------------- |
| Estimated portfolio loss             | Predicted loss  |
| Based on the selected period         | Guaranteed      |
| Historical simulation                | AI forecast     |
| Observed condition                   | Warning / alarm |
| Consider reviewing the concentration | You should sell |
| This metric is unavailable because…  | 0.00            |

Gjallarhorn signal copy describes what was measured and what threshold it
crossed, and stops there:

> **Gjallarhorn Signal — High position concentration**
> AAPL represents 34.2% of this portfolio, exceeding your 30% high-severity
> threshold. Observed 2026-09-18 over a 500-day window.

A signal never says what will happen, and never says what to trade. Signals are
understandable to a reader who has never heard of Norse mythology — the branded
term always sits beside the plain one.

---

## 11. Reality checks

Things the mockups show that the backend does not provide. Resolve each before
building the screen; do not invent an endpoint.

| Mockup shows                                       | Backend reality                                       | Resolution                                                |
| -------------------------------------------------- | ----------------------------------------------------- | --------------------------------------------------------- |
| "Continue with Google / Microsoft"                 | Email + password only; no OAuth                       | Remove the buttons, or scope OAuth as new backend work    |
| Full name, or first and last name, at registration | `RegisterRequest` accepts `email` and `password` only | Collect neither, or add a profile field to the backend    |
| `₹` amounts                                        | Each portfolio carries its own `base_currency`        | Format from the portfolio's actual currency               |
| Sortino ratio, bare "Alpha"                        | Neither exists; there is `benchmark_alpha_annualized` | Drop Sortino; label alpha correctly and annualized        |
| Nifty 50 benchmark                                 | Benchmark is per-portfolio, fixtures ship SPY         | Use the portfolio's configured benchmark                  |
| Mutual Funds, Bonds, Cash, Gold, REITs             | `AssetType` is `equity`, `etf`, `unknown`             | Show the three that exist; `unknown` is honest, not a bug |
| "Direct broker integration"                        | CSV import only                                       | Remove the claim                                          |
| Excel report format                                | `ReportFormat` is PDF only                            | PDF only                                                  |
| "Scheduled Reports" tab                            | No scheduling endpoint                                | Remove, or scope as new work                              |
| "Transactions" tab                                 | No transaction model; positions only                  | Remove                                                    |
| "Watch Demo"                                       | No demo video exists                                  | Supply one or remove the button                           |

---

## 12. Reference

|               |                                                                        |
| ------------- | ---------------------------------------------------------------------- |
| Mockups       | `resources/mockups/` — the binding visual reference                    |
| Imagery       | `PROMPTS.md`                                                           |
| Behaviour     | `AGENTS.md`                                                            |
| Motion feel   | era-residence.com (scroll orchestration, label swap, page transitions) |
| Structure     | lamalama.com (dark canvas, list hover reveals, loader)                 |
| Product rules | `../CLAUDE.md` — wins over this file on product matters                |

---

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
