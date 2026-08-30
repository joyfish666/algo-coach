// Clipboard write with a fallback for non-secure contexts: localhost is a
// secure context so navigator.clipboard is normally present, but a file://
// launch or an odd proxy would silently lose the share code without the
// hidden-textarea fallback.
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.setAttribute('readonly', '')
      area.style.opacity = '0'
      area.style.position = 'fixed'
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand('copy')
      area.remove()
      return ok
    } catch {
      return false
    }
  }
}
