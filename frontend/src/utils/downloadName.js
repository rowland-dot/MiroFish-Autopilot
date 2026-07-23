// Parse a download filename out of a Content-Disposition header.
// Prefers RFC5987 `filename*` (UTF-8 — carries Chinese), falls back to plain
// `filename=`, then to the caller-provided fallback.

/**
 * @param {string|null} disposition - the Content-Disposition header value
 * @param {string} fallback - name to use when the header is missing/unparseable
 * @returns {string}
 */
export function filenameFromDisposition(disposition, fallback) {
  const cd = String(disposition || '')

  const star = cd.match(/filename\*=UTF-8''([^;]+)/i)
  if (star) {
    try {
      return decodeURIComponent(star[1].trim())
    } catch {
      // fall through to plain filename
    }
  }

  const plain = cd.match(/filename="?([^";]+)"?/i)
  if (plain) return plain[1].trim()

  return fallback
}
