import { cx } from "@/lib/cx";

/**
 * The Heimdall logo.
 *
 * Three supplied variants: the mark alone, the runic wordmark alone, and the
 * lockup of both. Artwork rather than type, which also means the Elder Futhark
 * face never has to be shipped as a webfont — the wordmark is the same on every
 * machine whatever fonts a visitor has.
 *
 * The runes spell HEIMDALLR. They are artwork, so the accessible name is the
 * Latin word: assistive technology, search engines and a copied link all get
 * "Heimdall" rather than glyphs. DESIGN.md section 3.2.
 */

type Variant = "mark" | "wordmark" | "full";
type Tone = "light" | "dark";

interface Asset {
  width: number;
  height: number;
}

const ASSETS: Record<Variant, Asset> = {
  mark: { width: 256, height: 117 },
  wordmark: { width: 768, height: 171 },
  full: { width: 900, height: 538 },
};

export interface LogoProps {
  variant?: Variant;
  /** "light" is the white artwork for dark surfaces, which is the default here. */
  tone?: Tone;
  /**
   * Set when adjacent text already names the product, so the logo is not
   * announced twice.
   */
  decorative?: boolean;
  className?: string;
}

export function Logo({
  variant = "wordmark",
  tone = "light",
  decorative = false,
  className,
}: LogoProps) {
  const asset = ASSETS[variant];
  const base = `/brand/${variant}-${tone === "light" ? "white" : "black"}`;

  return (
    <img
      src={`${base}.webp`}
      onError={(event) => {
        // One retry as PNG, for browsers without WebP.
        const element = event.currentTarget;
        if (!element.src.endsWith(".png")) element.src = `${base}.png`;
      }}
      alt={decorative ? "" : "Heimdall"}
      aria-hidden={decorative || undefined}
      width={asset.width}
      height={asset.height}
      // The height comes from the class; width follows the intrinsic ratio, so
      // nothing shifts while the image loads.
      className={cx("w-auto select-none", className)}
      draggable={false}
    />
  );
}
