/**
 * Authentic artisan product image fallback mapping.
 * Ensures verified handcrafted imagery is always rendered across all views.
 */
export const PRODUCT_IMAGE_FALLBACKS: Record<string, string> = {
  // Suriya Craft Studio (South Indian artisan crafts)
  "terracotta filter coffee cup set": "/products/suriya-terracotta-cups.jpg",
  "thanjavur hammered brass lamp": "/products/suriya-brass-lamp.jpg",
  "kolam block print dupatta": "/products/suriya-kolam-dupatta.jpg",
  "chettinad stone mortar and pestle": "/products/suriya-stone-mortar.jpg",
  "kanchipuram silk table runner": "/products/suriya-silk-runner.jpg",

  // Meera's Jaipur Studio (Rajasthan traditional textiles)
  "indigo block print scarf": "/products/meera-indigo-scarf.jpg",
  "terracotta pendant": "/products/meera-terracotta-pendant.jpg",
  "woven table runner": "/products/meera-woven-runner.jpg",
  "botanical art print": "/products/meera-botanical-print.jpg",
  "painted keepsake box": "/products/meera-keepsake-box.jpg",
  "rose patterned scarf": "/products/meera-rose-scarf.jpg",
};

export function resolveProductImage(
  title?: string,
  imageUrl?: string | null,
): string | null {
  if (imageUrl) return imageUrl;
  if (!title) return null;
  return PRODUCT_IMAGE_FALLBACKS[title.trim().toLowerCase()] || null;
}
