import { ar } from './ar'
import { en } from './en'
import { hi } from './hi'
import type { Locale, Translations } from './types'
import { zh } from './zh'

export const TRANSLATIONS: Record<Locale, Translations> = {
  ar,
  en,
  hi,
  zh
}
