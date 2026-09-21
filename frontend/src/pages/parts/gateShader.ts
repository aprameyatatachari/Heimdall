/**
 * The gate dissolve.
 *
 * A single full-screen quad holding the splash photograph. As scroll progress
 * rises, a noise front climbs the frame and eats the image, so the plate does
 * not slide away — it is taken by its own weather. Where the front is passing,
 * the mist catches the light of the citadel and goes briefly gold.
 *
 * One authored moment for the whole surface. Nothing else on the page animates
 * on scroll.
 */

export const VERTEX = /* glsl */ `
  attribute vec2 uv;
  attribute vec2 position;
  varying vec2 vUv;

  void main() {
    vUv = uv;
    gl_Position = vec4(position, 0.0, 1.0);
  }
`;

export const FRAGMENT = /* glsl */ `
  precision highp float;

  varying vec2 vUv;

  uniform sampler2D uTexture;
  uniform vec2 uResolution;   // canvas size in device pixels
  uniform vec2 uImageSize;    // intrinsic texture size
  uniform float uProgress;    // 0 at rest, 1 fully dissolved
  uniform float uTime;        // seconds, for the drift
  uniform float uFocusX;      // horizontal framing, 0 left .. 1 right
  uniform vec3 uGlow;         // colour the dissolving edge takes

  // --- Value noise ---------------------------------------------------------
  // Cheap, smooth, and tileable enough at this scale. A gradient-noise
  // implementation costs more instructions than this effect can justify for
  // what would be an invisible difference behind a photograph.
  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i + vec2(0.0, 0.0)), hash(i + vec2(1.0, 0.0)), u.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
      u.y
    );
  }

  float fbm(vec2 p) {
    float total = 0.0;
    float amplitude = 0.5;
    for (int octave = 0; octave < 5; octave++) {
      total += noise(p) * amplitude;
      p *= 2.02;
      amplitude *= 0.5;
    }
    return total;
  }

  // Cover-fit, the shader equivalent of object-fit: cover, with the framing
  // bias the component passes in so the citadel survives a portrait viewport.
  vec2 coverUv(vec2 uv) {
    float canvasRatio = uResolution.x / uResolution.y;
    float imageRatio = uImageSize.x / uImageSize.y;
    vec2 scale = canvasRatio > imageRatio
      ? vec2(1.0, imageRatio / canvasRatio)
      : vec2(canvasRatio / imageRatio, 1.0);
    vec2 focus = vec2(uFocusX, 0.5);
    return (uv - focus) * scale + focus;
  }

  void main() {
    vec2 uv = coverUv(vUv);

    // The image settles a little as the gate opens, so the frame is never
    // perfectly still while it is being taken apart.
    uv += vec2(0.0, uProgress * 0.03);
    uv = clamp(uv, 0.0005, 0.9995);

    vec3 colour = texture2D(uTexture, uv).rgb;

    // Every pixel carries a resistance: how far the reveal must travel before
    // the mist takes it. Noise supplies most of it, so the edge is cloud rather
    // than a line; a gentle vertical bias makes the whole thing rise, because
    // the cloud sea this frame sits in is at its foot.
    float aspect = uResolution.x / max(uResolution.y, 1.0);
    float drift = uTime * 0.015;
    float cloud = fbm(vec2(vUv.x * 2.0 * aspect, vUv.y * 1.7 - drift));

    // Five octaves of value noise cluster tightly around the middle, which made
    // the whole frame cross the front at once and the reveal finish in the
    // first half of the runway. Stretching the distribution about its centre is
    // what buys the dissolve its full travel.
    cloud = clamp((cloud - 0.5) * 1.9 + 0.5, 0.0, 1.0);

    // The sky carries the least resistance and goes first; the horizon band
    // holds longest, so the citadel and the watchman on his cliff are the last
    // things the mist takes. Weighted evenly against the noise so the lower
    // third genuinely survives rather than being eaten by a low noise patch.
    float field = clamp(cloud * 0.5 + (1.0 - vUv.y) * 0.5, 0.0, 1.0);

    // Overshot at both ends so the plate is genuinely solid at rest and
    // genuinely gone at the finish, rather than asymptotic at either.
    float front = uProgress * 1.34 - 0.17;

    float alpha = smoothstep(front - 0.17, front + 0.17, field);

    // Light in the mist: the band currently dissolving picks up the citadel's
    // warmth, which is what stops the effect reading as an eraser.
    float edge = 1.0 - clamp(abs(field - front) / 0.24, 0.0, 1.0);
    edge *= smoothstep(0.0, 0.1, uProgress) * smoothstep(1.0, 0.8, uProgress);
    colour += uGlow * edge * 0.6;

    // A last breath of brightness as the plate goes, so the hand-off to the
    // page beneath is a lift rather than a cut.
    colour = mix(colour, colour * 1.22, smoothstep(0.55, 1.0, uProgress) * 0.6);

    gl_FragColor = vec4(colour, alpha);
  }
`;
