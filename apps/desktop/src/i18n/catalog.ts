import { ar } from './ar'
import { de } from './de'
import { en } from './en'
import { es } from './es'
import { fr } from './fr'
import { hi } from './hi'
import { it } from './it'
import { ja } from './ja'
import { nl } from './nl'
import { pt } from './pt'
import type { Locale, Translations } from './types'
import { zh } from './zh'

export const TRANSLATIONS: Record<Locale, Translations> = {
  ar,
  de,
  en,
  es,
  fr,
  hi,
  it,
  ja,
  nl,
  pt,
  zh
}
