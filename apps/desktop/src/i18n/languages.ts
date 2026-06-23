import type { Locale } from './types'

export const DEFAULT_LOCALE: Locale = 'en'

export const LOCALE_OPTIONS = [
  {
    id: 'en',
    name: 'English',
    configValue: 'en'
  },
  {
    id: 'zh',
    name: '简体中文',
    configValue: 'zh'
  },
  {
    id: 'ar',
    name: 'العربية',
    configValue: 'ar'
  },
  {
    id: 'hi',
    name: 'हिन्दी',
    configValue: 'hi'
  }
] as const satisfies readonly { configValue: string; id: Locale; name: string }[]

// Endonyms (native names) for the language picker so users recognize their
// language regardless of the current UI language. No country flags:
// languages are not countries.
export const LOCALE_META: Record<Locale, { name: string }> = Object.fromEntries(
  LOCALE_OPTIONS.map(locale => [locale.id, { name: locale.name }])
) as Record<Locale, { name: string }>

const LOCALE_ALIASES: Record<string, Locale> = {
  en: 'en',
  'en-us': 'en',
  en_us: 'en',
  zh: 'zh',
  'zh-cn': 'zh',
  zh_cn: 'zh',
  'zh-hans': 'zh',
  zh_hans: 'zh',
  'zh-hans-cn': 'zh',
  zh_hans_cn: 'zh',
  ar: 'ar',
  'ar-sa': 'ar',
  ar_sa: 'ar',
  'ar-ae': 'ar',
  ar_ae: 'ar',
  hi: 'hi',
  'hi-in': 'hi',
  hi_in: 'hi'
}

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && LOCALE_OPTIONS.some(locale => locale.id === value)
}

export function normalizeLocale(value: unknown): Locale {
  if (typeof value !== 'string') {
    return DEFAULT_LOCALE
  }

  return LOCALE_ALIASES[value.trim().toLowerCase()] ?? DEFAULT_LOCALE
}

export function isSupportedLocaleValue(value: unknown): boolean {
  return typeof value === 'string' && LOCALE_ALIASES[value.trim().toLowerCase()] != null
}

export function localeConfigValue(locale: Locale): string {
  return LOCALE_OPTIONS.find(item => item.id === locale)?.configValue ?? DEFAULT_LOCALE
}

// Right-to-left locales. Arabic renders RTL; the app root's `dir` is flipped to
// 'rtl' for these so layout, text alignment, and logical CSS properties mirror.
const RTL_LOCALES: ReadonlySet<Locale> = new Set<Locale>(['ar'])

export function isRtlLocale(locale: Locale): boolean {
  return RTL_LOCALES.has(locale)
}

export function localeDirection(locale: Locale): 'ltr' | 'rtl' {
  return isRtlLocale(locale) ? 'rtl' : 'ltr'
}
