/**
 * Shipped imagery.
 *
 * Files live in `public/`, so these paths are absolute from the site root and
 * are served as-is. Generated artwork is produced from the prompts in
 * PROMPTS.md and dropped into the matching folder; a missing file degrades to
 * the gradient underneath rather than breaking the page.
 */

export const IMAGES = {
  /** Landing hero: the citadel across the cloud sea at dawn. */
  heroCitadel: {
    src: "/images/hero/citadel-dawn.webp",
    fallback: "/images/hero/citadel-dawn.jpg",
    placeholder: "/images/hero/citadel-dawn-lqip.webp",
    width: 1672,
    height: 941,
  },
} as const;
