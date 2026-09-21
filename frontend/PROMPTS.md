# Heimdall — Image Generation Prompts

Every generated visual asset the frontend needs, with the prompt to produce it.

Paired with `DESIGN.md` (which fixes the palette these prompts must obey) and
`AGENTS.md` (which says where each asset is used).

---

## 1. The style contract

Prepend or honour this in **every** prompt. It is what makes twenty separately
generated images look like one product.

> Cinematic matte painting, photoreal concept art. Nordic-mythic architecture —
> a golden citadel of impossibly tall slender spires on a cliff above an ocean of
> cloud, arched stone bridges, long thin waterfalls falling into mist, snow
> mountains on the horizon. Deep blue-black night-to-dawn palette, near-black
> `#070D11` in shadow, cool desaturated blue-grey mid-tones, a single warm gold
> light source low on the horizon. Volumetric god rays, heavy atmospheric haze,
> fine film grain, subtle anamorphic bloom. Painterly realism, restrained and
> austere — grand but never gaudy. High dynamic range with genuinely deep blacks.

### 1.1 Universal negative prompt

> text, letters, words, typography, watermark, signature, logo, UI elements,
> charts, graphs, arrows, currency symbols, coins, gold bars, stock tickers,
> bulls, bears, rockets, neon, cyberpunk, lens flare streaks, oversaturation,
> HDR clipping, purple-orange teal grade, cluttered composition, busy foreground,
> people's faces in close-up, modern clothing, cars, contemporary cityscape,
> cartoon, anime, low contrast grey mush, blown highlights

### 1.2 Hard rules

1. **No text inside images, ever.** All type is live HTML. An image with baked-in
   words cannot be translated, cannot be read by a screen reader, and will not
   match the font.
2. **Every hero image needs a dark, quiet region for the headline.** Each prompt
   below names where. Check the result at every breakpoint: a hero that passes on
   desktop and fails on mobile is a fail.
3. **No horn outside Gjallarhorn.** `CLAUDE.md` forbids a horn in the primary
   identity. The watchman may hold a spear, raise a hand, or simply stand
   watching. The horn appears **only** in §7 — the Early Warning System.
4. **No imagery that implies prediction or gain.** No rising arrows, no sunrise
   framed as a promise, no treasure. The mood is _vigilance_, not _fortune_.
5. **Generate at 2× the largest display size**, then downsample. Ship AVIF with
   WebP fallback, plus a `<20KB` LQIP blur placeholder for every hero.
6. Faces are distant, silhouetted or turned away. No recognisable person, no
   real-world brand, no existing film's production design.

### 1.3 File plan

```text
public/images/
  splash/        gate plate            portrait, 1440×2560 + 828×1792 mobile
  hero/          landing hero          2560×1440 + 1440×1080 mobile crop
  auth/          sign-in backdrop      1600×2400
  sections/      in-page backdrops     2400×1200
  states/        empty and error       1200×900
  social/        OG card               1200×630
public/textures/ grain, starfield, dot matrix, spectral gradient
public/brand/    star glyph, wordmark, Gjallarhorn mark
```

---

## 2. Landing hero — `hero/citadel-dawn`

**2560×1440 (16:9) and a 1440×1080 mobile crop.** The most-seen image in the
product. Replaces `resources/images/bg.png`, which at 1672×941 is too small to
run full-bleed.

> Wide cinematic vista from a high clifftop at the blue hour before dawn. A vast
> golden citadel of impossibly tall slender spires stands on a plateau across a
> sea of cloud, catching the first warm light from a low sun at the right edge of
> frame. Long arched stone bridges span the void toward it; thin waterfalls pour
> from the plateau edge and dissolve into mist far below. Dark evergreen forest
> and wet black rock in the near foreground. Snow-capped mountains recede in
> layers of cool blue haze. In the left third, on a rocky outcrop in deep
> silhouette, a lone armoured watchman stands facing the citadel, a tall spear
> planted beside him and a long cloak falling still — small in frame, unlit,
> reading as a dark shape against the cloud. Deep blue-black shadows, cool
> desaturated blue-grey cloud, a single warm gold light source. Volumetric god
> rays through broken cloud, heavy atmospheric depth, fine grain, gentle bloom.
> --ar 16:9

**Composition constraints:** the **left 45%** must stay dark and low-detail — the
headline, sub-line and buttons sit there. Keep the top 90px quiet for the
transparent header. The watchman must not rise into the headline band; place him
low-left. Horizon on the lower third line.

**Mobile crop:** re-generate at `--ar 4:3` rather than cropping — the desktop
composition loses the citadel when squeezed.

---

## 3. Splash gate — `splash/watchman-gate`

**1440×2560 portrait, plus 828×1792.** The full-viewport plate behind the runic
wordmark on first entry.

> Vertical cinematic composition. A lone armoured watchman in a long weathered
> cloak stands in three-quarter silhouette on a jagged clifftop in the lower-left
> third, facing out across an immense sea of cloud. He holds a tall spear upright;
> one hand rests on it. Bronze and dark iron armour catching only a thin rim of
> warm gold light along its edge. Far below and beyond, a golden spired citadel
> floats on a cloud plateau, small and distant, lit by a low sun breaking through
> heavy cumulus. Upper half of the frame is open sky — dramatic layered cloud,
> deep blue-black at the top edge, warming to pale gold near the horizon.
> Mountains in cool blue haze. Wet black rock, sparse dark pines. Volumetric
> light, deep atmospheric perspective, fine film grain.
> --ar 9:16

**Composition constraints:** the **upper 40%** stays open and dark — the star,
the runic wordmark and the tagline stack there. The lower 15% must be dark enough
for the `SLIDE UP TO ENTER` control. The watchman never crosses the vertical
centre line. **No horn** — he holds a spear.

---

## 4. Auth backdrop — `auth/threshold-hall`

**1600×2400 portrait.** Behind the glass sign-in and registration cards.

> Interior of a vast open colonnade at dawn, looking outward between two rows of
> tall pale stone columns with slender pointed arches. Beyond the arches, a
> golden spired citadel on a cloud plateau, mountains and a low warm sun. Polished
> stone floor with a faint mirror sheen catching the light. Shafts of warm gold
> light fall between the columns across the floor. Thin mist drifts at ankle
> height. Deep blue-grey shadow in the foreground columns, warm light beyond.
> Utterly still and quiet. Symmetrical, single-point perspective, centred vanishing
> point. Volumetric light, fine grain, subtle bloom.
> --ar 2:3

**Composition constraints:** the **centre 55%** must be uniform enough to sit a
glass card on — the card blurs it anyway, but a busy centre fights the form.
Keep the brightest light source out of the middle band. Verify the card's text
clears 4.5:1 over the _brightest_ pixel it covers.

---

## 5. Section backdrops

Low-contrast, heavily atmospheric, used at 10–20% opacity behind content. These
must almost disappear.

### 5.1 Methodology — `sections/roots-and-well`

> An immense ancient tree seen from below in a green mountain valley, its canopy
> lost in mist, long pale waterfalls falling in vertical threads from its high
> branches into a still dark pool at its roots. Terraced stone steps descend to the
> water. Cool green and blue-grey, soft diffused overcast light, no direct sun.
> Deep atmospheric haze, layered depth, painterly and calm.
> --ar 2:1

### 5.2 Stress testing — `sections/weather-on-the-horizon`

> A wide view from a high stone rampart across an ocean of cloud toward a distant
> weather front — dense dark storm cloud building far away on the right, with
> clear cold blue sky still holding on the left. The foreground rampart and its
> arched stone parapet are calm, dry and lit. The storm is remote, observed, not
> arriving. Deep blue-black, cool grey, a thin band of pale gold along the horizon.
> Restrained and analytical, not apocalyptic. Heavy atmospheric perspective.
> --ar 2:1

Deliberately **not** threatening. This page shows what a scenario _would_ do, not
what _will_ happen.

### 5.3 Reports — `sections/archive-hall`

> A long hall of pale stone with tall arched windows down one side, warm low light
> falling in wide bands across a polished floor. Deep shadow between the windows.
> Empty, still, austere. No furniture, no objects. Cool blue-grey shadow, warm gold
> light. Single-point perspective down the length of the hall.
> --ar 2:1

---

## 6. Empty and error states

Quiet, small-scale, never comic. **1200×900**, used at ~420px wide.

### 6.1 No portfolios — `states/unlit-watchtower`

> A single slender unlit stone watchtower alone on a small rocky island in a calm
> sea of cloud at twilight. No light in its windows. Empty sky, one faint star.
> Vast negative space around it. Deep blue-black and cool grey, almost monochrome,
> one small point of pale warm light on the horizon. Minimal, still, patient.
> --ar 4:3

### 6.2 No holdings — `states/empty-plinth`

> An empty pale stone plinth on a wide flat terrace overlooking cloud at dawn.
> Nothing on it. Long soft shadow. Cool grey stone, warm low light from one side.
> Extremely minimal, enormous negative space.
> --ar 4:3

### 6.3 No signals — `states/clear-horizon`

> A wide calm horizon of unbroken cloud under a clear pale sky at first light. No
> structures, no figures, no weather. Utterly quiet. Soft gradient from deep blue
> at the top to pale warm gold at the horizon. Almost abstract.
> --ar 4:3

This is a **good** state — the watch is running and nothing is wrong. It must
feel reassuring, not empty.

### 6.4 404 — `states/broken-bridge`

> An arched stone bridge over an ocean of cloud, with a span missing near the far
> end — the path simply stops. The far side is lost in mist. Cool blue-grey stone,
> soft overcast light, no drama, no debris, no danger. Quiet and matter-of-fact.
> --ar 4:3

### 6.5 Server error — `states/shuttered-gate`

> A tall closed gate of dark iron and pale stone set in a cliff face, shut. Mist at
> its base. One small warm light still burning in a recess above the lintel. Cool
> blue-grey, one point of warm gold. Calm, temporary, not ruined.
> --ar 4:3

The light is deliberate: something is still running, this is temporary.

---

## 7. Gjallarhorn — the Early Warning System

**The only place a horn may appear.** See `DESIGN.md` §4.1.

### 7.1 Section backdrop — `sections/gjallarhorn-watch`

> A lone armoured watchman standing on a high clifftop at dawn, seen from behind
> and below in silhouette, raising a long curved horn. He is not blowing it — it is
> held ready, lifted. Vast cloud ocean and a distant golden citadel below. Low warm
> sun behind him producing a strong rim light along the horn's curve and the edge
> of his cloak. Deep blue-black foreground, pale gold sky. Still, poised, watchful —
> a moment of attention, not alarm.
> --ar 2:1

The distinction matters. A signal is an _observation_, not an emergency. The horn
is raised and quiet.

### 7.2 Section glyph — `brand/gjallarhorn-mark`

The supplied `resources/logos/HEIMDALL_*.svg` is exactly this mark — a curved
horn fused with an eye. It is currently a raster bitmap inside an SVG wrapper. If
it is redrawn rather than traced:

> Minimal geometric line mark: a curved drinking horn whose body forms the outline
> of an open eye, the horn's mouth becoming the outer corner. Single uniform stroke
> weight, no fill, no gradient, no shading. Flat vector, pure white on transparent.
> Balanced within a square, generous optical margin. Clean, austere, heraldic.
> --ar 1:1

**Vector output required**, single stroke weight, `currentColor`.

---

## 8. Brand marks

### 8.1 The star — `brand/star`

> Minimal four-pointed star with a long vertical axis and short horizontal axis,
> sharp tapered points, perfectly symmetrical. Solid flat white on transparent, no
> gradient, no glow, no outline. Centred with generous margin.
> --ar 1:1

Used as loading indicator, list bullet, favicon and the lockup mark above the
wordmark. **Hand-draw this as SVG** — a four-pointed star is a dozen path
commands and generation will only approximate it.

### 8.2 Favicon

The star alone in `--hm-gold` on `--hm-abyss`. Ship 16, 32, 180 (Apple touch) and
512 (maskable) px, plus a monochrome SVG for pinned tabs. **Not** the horn mark.

### 8.3 Social card — `social/og-card`

**1200×630.** A crop of the landing hero with the **right 55% left dark and
empty** for the wordmark and tagline, which are composited as live text at build
time — never baked into the generated image.

---

## 9. Textures

Small, tileable, shipped as PNG.

| File                     | Prompt / method                                                                                                                      | Use                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- |
| `textures/grain.png`     | Generate procedurally: 256×256 monochrome film grain, fine, even, no clumping, mean 50% grey                                         | `DESIGN.md` §5.7, 4.5% opacity overlay |
| `textures/starfield.png` | 1024×1024 sparse white points of varying size on pure black, irregular natural distribution, no constellations, no nebula, no colour | Splash upper sky, 25% opacity          |
| `textures/dots.png`      | 64×64 tileable regular dot matrix grid, single small circle per cell, flat white on transparent                                      | Loading state only                     |
| `textures/spectral.png`  | 2048×64 horizontal gradient: cold blue `#8FB4D9` → violet `#C9B7E8` → warm `#F0C9A8`, smooth, no banding                             | Bifröst transition sweep               |

Generate the gradient and the grain in code, not with an image model — both need
exact values and clean banding, and both are a few lines of canvas.

---

## 10. Feature icons

Four marks for the landing capability row: **Unified Portfolio View**,
**Advanced Analytics**, **Stress Testing & Scenario Analysis**, **Institutional
Grade Reports**.

> Minimal line icon, single uniform 1.5px stroke, 24×24 grid, rounded caps and
> joins, no fill, no perspective, no shading, geometric and austere. Flat vector,
> `currentColor`.

Concepts, holding the metaphor without becoming literal: an open eye within a
circle (unified view); three ascending measured bars behind a vertical axis
(analytics); a shield with a fracture line that does not break it (stress
testing); a document with a seal (reports).

Draw as SVG by hand. Generated icons will not share a stroke weight, and mixed
stroke weights in an icon row are immediately visible.

---

## 11. Report cover — `sections/report-cover`

Portrait plate for the PDF's first page, behind the live-rendered title.

> A wide still horizon of cloud at dawn seen from a high stone terrace, the terrace
> edge a single clean horizontal line across the lower third. No structures, no
> figures. Deep blue-black above, pale warm gold at the horizon. Extremely
> restrained, almost abstract, printable — no detail that would muddy at 300dpi in
> greyscale.
> --ar 3:4

Must survive black-and-white printing. Check a greyscale conversion before
shipping: reports get printed, and the cover cannot become a grey slab.

---

## 12. Delivery checklist

For every generated asset:

- [ ] No text, letters or symbols anywhere in the image
- [ ] No horn, except §7
- [ ] Palette matches `DESIGN.md` §2 — blue-black ground, single warm gold
- [ ] The named text region is dark and quiet, verified at every breakpoint
- [ ] Overlaid text clears 4.5:1 against the brightest pixel it covers
- [ ] AVIF + WebP + LQIP placeholder generated
- [ ] Explicit `width`/`height` so nothing shifts on load
- [ ] Mobile crop generated separately, not squeezed from desktop
- [ ] Greyscale check for anything that reaches a printed report
- [ ] Meaningful `alt` text written; purely decorative assets `alt=""` and
      `aria-hidden="true"`
- [ ] Nothing implies prediction, gain, urgency or advice

---

> Heimdall is an educational portfolio-analysis tool. Its calculations are
> estimates based on historical data and model assumptions and do not constitute
> financial advice or guarantee future results.
