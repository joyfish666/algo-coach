/**
 * Single extraction point for user-visible error text.
 *
 * api.js handle() already localizes server message_key payloads into
 * err.message (and maps timeout/refused connections to localized copy), so
 * views must not re-parse err.payload with their own precedence - that used
 * to drift per view (payload.error.message here, payload.detail there).
 */
export function userFacingError(err) {
  return (err && err.message) || String(err)
}
