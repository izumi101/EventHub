import { Component, inject } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from './language.service';
import { LANG_META, Lang, SUPPORTED_LANGS } from './languages';

/** `ҚАЗ / РУС / ENG` segmented control. Works in the topbar and the mobile drawer. */
@Component({
  selector: 'app-language-switcher',
  standalone: true,
  imports: [TranslocoPipe],
  template: `
    <div
      class="inline-flex items-center rounded-md border border-border p-0.5 text-[11px] font-semibold"
      role="group"
      [attr.aria-label]="'common.language' | transloco"
    >
      @for (code of langs; track code) {
        <button
          type="button"
          class="px-2 py-1 rounded transition-colors focus-ring"
          [class]="
            language.lang() === code
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground'
          "
          [attr.aria-pressed]="language.lang() === code"
          [attr.lang]="code"
          [attr.aria-label]="meta[code].name"
          [attr.data-lang]="code"
          (click)="select(code)"
        >
          {{ meta[code].short }}
        </button>
      }
    </div>
  `,
})
export class LanguageSwitcherComponent {
  readonly language = inject(LanguageService);
  readonly langs = SUPPORTED_LANGS;
  readonly meta = LANG_META;

  select(code: Lang): void {
    void this.language.setLang(code);
  }
}
