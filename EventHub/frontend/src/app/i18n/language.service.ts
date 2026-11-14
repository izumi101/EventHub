import { DOCUMENT } from '@angular/common';
import { Injectable, computed, inject, signal } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';
import { firstValueFrom } from 'rxjs';
import { DEFAULT_LANG, LANG_META, LANG_STORAGE_KEY, Lang, isLang, matchLang } from './languages';

/**
 * Owns the active UI language: persistence, `<html lang>`, the Angular locale
 * used by date/number pipes, and the Transloco active language.
 * `lang` is a signal, so anything that reads it re-renders on a switch.
 */
@Injectable({ providedIn: 'root' })
export class LanguageService {
  private readonly transloco = inject(TranslocoService);
  private readonly document = inject(DOCUMENT);

  private readonly _lang = signal<Lang>(DEFAULT_LANG);
  readonly lang = this._lang.asReadonly();
  /** Locale id for Intl and Angular's `formatDate`. */
  readonly locale = computed(() => LANG_META[this._lang()].locale);

  /** Resolves the initial language and loads its translations. Call once at boot. */
  async init(): Promise<void> {
    await this.apply(this.detect());
  }

  /** Switches the language at runtime (no reload) and persists the choice. */
  async setLang(lang: Lang): Promise<void> {
    await this.apply(lang);
    this.store(lang);
  }

  /** Translates a key in code (toasts, modals); templates use the `transloco` pipe. */
  t(key: string, params?: Record<string, unknown>): string {
    return this.transloco.translate(key, params);
  }

  /** Like `t`, but returns `fallback` (not the key) when the key has no translation. */
  tOr(key: string, fallback: string): string {
    const text = this.transloco.translate(key);
    return text === key ? fallback : text;
  }

  /**
   * Picks `<key>_one|few|many|other` for the count using the active language's
   * plural rules, falling back to `<key>_other`. `count` is always available
   * to the string as `{{ count }}`.
   */
  plural(key: string, count: number, params: Record<string, unknown> = {}): string {
    const category = new Intl.PluralRules(this.locale()).select(count);
    const all = { ...params, count };
    const specific = `${key}_${category}`;
    const text = this.transloco.translate(specific, all);
    return text === specific ? this.transloco.translate(`${key}_other`, all) : text;
  }

  private async apply(lang: Lang): Promise<void> {
    await firstValueFrom(this.transloco.load(lang));
    this.transloco.setActiveLang(lang);
    this._lang.set(lang);
    this.document.documentElement.lang = lang;
  }

  private detect(): Lang {
    const stored = this.read();
    if (stored) return stored;
    const nav = this.document.defaultView?.navigator;
    const tags = nav?.languages.length ? nav.languages : nav?.language ? [nav.language] : [];
    for (const tag of tags) {
      const match = matchLang(tag);
      if (match) return match;
    }
    return DEFAULT_LANG;
  }

  private read(): Lang | null {
    try {
      const value = localStorage.getItem(LANG_STORAGE_KEY);
      return isLang(value) ? value : null;
    } catch {
      return null;
    }
  }

  private store(lang: Lang): void {
    try {
      localStorage.setItem(LANG_STORAGE_KEY, lang);
    } catch {
      // Storage can be blocked (private mode); the choice then lasts for the session only.
    }
  }
}
