import { atom } from 'nanostores'

import { persistString, storedString } from '@/lib/storage'

// Chat text size. A desktop-only display preference: a multiplier applied to the
// chat area's base font size via the `--chat-font-scale` CSS variable (see
// styles.css `--conversation-text-font-size`). Persisted in localStorage and
// applied to <html> at module load so the saved size is in effect on launch.

const STORAGE_KEY = 'hermes.desktop.chatFontScale'

export const MIN_FONT_SCALE = 0.8
export const MAX_FONT_SCALE = 1.6
export const FONT_SCALE_STEP = 0.05
export const DEFAULT_FONT_SCALE = 1

const clampScale = (n: number) => Math.min(MAX_FONT_SCALE, Math.max(MIN_FONT_SCALE, n))

function initialScale(): number {
  const raw = storedString(STORAGE_KEY)
  const parsed = raw ? Number.parseFloat(raw) : Number.NaN

  return Number.isFinite(parsed) ? clampScale(parsed) : DEFAULT_FONT_SCALE
}

export const $chatFontScale = atom<number>(initialScale())

function applyScale(scale: number) {
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--chat-font-scale', String(scale))
  }
}

// Subscribe fires immediately with the current value, so this both applies the
// saved scale on launch and keeps <html> + localStorage in sync on every change.
$chatFontScale.subscribe(scale => {
  applyScale(scale)
  persistString(STORAGE_KEY, String(scale))
})

export function setChatFontScale(next: number) {
  $chatFontScale.set(clampScale(Number.isFinite(next) ? next : DEFAULT_FONT_SCALE))
}

export function resetChatFontScale() {
  $chatFontScale.set(DEFAULT_FONT_SCALE)
}
