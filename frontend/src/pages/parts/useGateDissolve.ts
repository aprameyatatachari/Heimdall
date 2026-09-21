import { useEffect, useRef, useState } from "react";

import type * as OGL from "ogl";

import { FRAGMENT, VERTEX } from "./gateShader";

const IMAGE_WIDTH = 1672;
const IMAGE_HEIGHT = 941;

/** The citadel sits right of centre; bias the crop so it survives a narrow viewport. */
const FOCUS_X = 0.58;

/** The colour the dissolving edge takes — the gold from the design tokens. */
const GLOW: [number, number, number] = [253 / 255, 216 / 255, 157 / 255];

export interface GateDissolve {
  canvasRef: React.MutableRefObject<HTMLCanvasElement | null>;
  /** False when WebGL is unavailable, so the caller renders the plain plate. */
  supported: boolean;
}

/**
 * Drives the gate's dissolve shader.
 *
 * Progress is read from a ref rather than passed as state: it changes on every
 * scroll frame, and re-rendering React sixty times a second to move one uniform
 * would cost more than the effect.
 *
 * Everything here is optional. If WebGL is missing, the context is lost, or the
 * texture cannot decode, `supported` goes false and the caller falls back to an
 * ordinary image. The gate must open either way.
 */
export function useGateDissolve(
  progressRef: React.RefObject<number>,
  {
    enabled,
    imageSrc,
    containerRef,
  }: {
    enabled: boolean;
    imageSrc: string;
    /** Measured for sizing. The canvas cannot measure itself — see `resize`. */
    containerRef: React.RefObject<HTMLElement | null>;
  },
): GateDissolve {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [supported, setSupported] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setSupported(false);
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;

    let disposed = false;
    let frame = 0;
    let cleanup: (() => void) | undefined;

    void (async () => {
      let ogl: typeof OGL;
      try {
        // Loaded on demand: the bundle for everyone who never sees the gate
        // should not carry a WebGL library.
        ogl = await import("ogl");
      } catch {
        if (!disposed) setSupported(false);
        return;
      }
      if (disposed) return;

      const { Renderer, Program, Mesh, Triangle, Texture } = ogl;

      let renderer: InstanceType<typeof Renderer>;
      try {
        renderer = new Renderer({
          canvas,
          alpha: true,
          antialias: false,
          // The dissolve is a smooth gradient over a photograph; a device pixel
          // ratio above 2 costs fill rate and shows nothing.
          dpr: Math.min(window.devicePixelRatio || 1, 2),
        });
      } catch {
        if (!disposed) setSupported(false);
        return;
      }

      const gl = renderer.gl;
      gl.clearColor(0, 0, 0, 0);

      const texture = new Texture(gl, { generateMipmaps: false });
      const image = new Image();
      image.decoding = "async";
      image.src = imageSrc;

      const program = new Program(gl, {
        vertex: VERTEX,
        fragment: FRAGMENT,
        transparent: true,
        depthTest: false,
        uniforms: {
          uTexture: { value: texture },
          uResolution: { value: [canvas.clientWidth, canvas.clientHeight] },
          uImageSize: { value: [IMAGE_WIDTH, IMAGE_HEIGHT] },
          uProgress: { value: 0 },
          uTime: { value: 0 },
          uFocusX: { value: FOCUS_X },
          uGlow: { value: GLOW },
        },
      });

      const mesh = new Mesh(gl, { geometry: new Triangle(gl), program });

      // Measured from the plate, never from the canvas. OGL's constructor
      // writes an inline 300x150 onto the canvas, which beats the stylesheet;
      // asking the canvas its own size returns that default forever.
      const resize = () => {
        const host = containerRef.current;
        if (!host) return;
        const width = host.clientWidth;
        const height = host.clientHeight;
        if (width === 0 || height === 0) return;

        renderer.setSize(width, height);
        // setSize writes inline pixel dimensions too. Handing layout back to
        // the stylesheet keeps the canvas tracking the plate on every resize.
        canvas.style.width = "100%";
        canvas.style.height = "100%";
        program.uniforms.uResolution!.value = [width * renderer.dpr, height * renderer.dpr];
      };

      const observer = new ResizeObserver(resize);
      const host = containerRef.current;
      if (host) observer.observe(host);
      resize();

      image.onload = () => {
        texture.image = image;
      };
      image.onerror = () => {
        if (!disposed) setSupported(false);
      };

      const onContextLost = (event: Event) => {
        // A lost context on a decorative surface is not worth recovering; drop
        // to the still image rather than leaving an empty canvas.
        event.preventDefault();
        if (!disposed) setSupported(false);
      };
      canvas.addEventListener("webglcontextlost", onContextLost);

      const start = performance.now();
      const render = () => {
        frame = requestAnimationFrame(render);
        program.uniforms.uTime!.value = (performance.now() - start) / 1000;
        program.uniforms.uProgress!.value = progressRef.current ?? 0;
        renderer.render({ scene: mesh });
      };
      frame = requestAnimationFrame(render);

      cleanup = () => {
        cancelAnimationFrame(frame);
        observer.disconnect();
        canvas.removeEventListener("webglcontextlost", onContextLost);
        image.onload = null;
        image.onerror = null;
        gl.getExtension("WEBGL_lose_context")?.loseContext();
      };
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      cleanup?.();
    };
  }, [enabled, imageSrc, progressRef, containerRef]);

  return { canvasRef, supported };
}
