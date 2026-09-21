import { useState } from "react";

import { cx } from "@/lib/cx";

export interface BackdropImage {
  src: string;
  fallback: string;
  placeholder: string;
  width: number;
  height: number;
}

/**
 * A full-bleed photographic backdrop with its scrims.
 *
 * Decorative in every use so far: the page's meaning is carried by its text, so
 * the image is hidden from assistive technology rather than given invented
 * alternative text.
 *
 * The scrims are not styling — text sits on top of this, and the gradient is
 * what keeps that text above its contrast floor. See DESIGN.md section 5.6.
 */
export function Backdrop({
  image,
  scrim = "left",
  position = "object-center",
  className,
}: {
  image: BackdropImage;
  scrim?: "left" | "bottom" | "both" | "flat";
  position?: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  return (
    <div aria-hidden="true" className={cx("absolute inset-0 overflow-hidden", className)}>
      {/* Gradient floor. Visible before the image loads, and the whole backdrop
          when no artwork has been generated yet. Positioned, like everything
          else in this stack: a statically positioned sibling would paint
          underneath it and disappear. */}
      <div className="from-void via-abyss to-surface absolute inset-0 bg-gradient-to-br" />

      {!failed && (
        <img
          src={image.src}
          onError={(event) => {
            // One retry at the fallback format, then give up and keep the
            // gradient rather than showing a broken-image frame.
            const element = event.currentTarget;
            if (element.src.endsWith(image.fallback)) setFailed(true);
            else element.src = image.fallback;
          }}
          alt=""
          width={image.width}
          height={image.height}
          loading="eager"
          fetchPriority="high"
          decoding="async"
          className={cx("absolute inset-0 size-full object-cover", position)}
          style={{
            backgroundImage: `url(${image.placeholder})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
          }}
        />
      )}

      {(scrim === "left" || scrim === "both") && (
        <div className="hm-scrim-left absolute inset-0" />
      )}
      {(scrim === "bottom" || scrim === "both") && (
        <div className="hm-scrim-bottom absolute inset-0" />
      )}
      {/* 84%, not less: at 72% the small print over this image measured
          2.49:1. See DESIGN.md section 5.6. */}
      {scrim === "flat" && <div className="bg-void/84 absolute inset-0" />}
    </div>
  );
}
