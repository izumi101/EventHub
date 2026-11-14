import { Injectable, effect, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';
import { LanguageService } from './language.service';

const SITE_NAME = 'EventHub';

/**
 * Route `title`s are translation keys (`routeTitles.*`). The document title is
 * translated on navigation and again whenever the language changes.
 */
@Injectable({ providedIn: 'root' })
export class TranslatedTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private readonly language = inject(LanguageService);
  private snapshot: RouterStateSnapshot | null = null;

  constructor() {
    super();
    effect(() => {
      this.language.lang();
      if (this.snapshot) this.apply(this.snapshot);
    });
  }

  override updateTitle(snapshot: RouterStateSnapshot): void {
    this.snapshot = snapshot;
    this.apply(snapshot);
  }

  private apply(snapshot: RouterStateSnapshot): void {
    const key = this.buildTitle(snapshot);
    if (key) this.title.setTitle(`${SITE_NAME} — ${this.language.t(key)}`);
  }
}
