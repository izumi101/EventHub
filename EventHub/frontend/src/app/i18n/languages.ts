/** Languages the UI is translated into. English is the source and the fallback. */
export const SUPPORTED_LANGS = ['kk', 'ru', 'en'] as const;
export type Lang = (typeof SUPPORTED_LANGS)[number];

export const DEFAULT_LANG: Lang = 'en';
export const LANG_STORAGE_KEY = 'eventhub.lang';

/** Short labels shown in the switcher and the full names used as accessible names. */
export const LANG_META: Record<Lang, { short: string; name: string; locale: string }> = {
  kk: { short: 'ҚАЗ', name: 'Қазақша', locale: 'kk' },
  ru: { short: 'РУС', name: 'Русский', locale: 'ru' },
  en: { short: 'ENG', name: 'English', locale: 'en' },
};

export function isLang(value: unknown): value is Lang {
  return typeof value === 'string' && (SUPPORTED_LANGS as readonly string[]).includes(value);
}

/** Maps a BCP 47 tag such as `ru-KZ` to a supported language, or null. */
export function matchLang(tag: string | null | undefined): Lang | null {
  const primary = tag?.toLowerCase().split('-')[0];
  return isLang(primary) ? primary : null;
}
