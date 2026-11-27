import { Component, computed, inject, input } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { LucideAngularModule, Star } from 'lucide-angular';
import { LanguageService } from '../../i18n/language.service';

/**
 * Five stars filled up to `rating` (a whole review rating, or an average such
 * as 4.42: the fifth star is then filled 42%). One image for assistive
 * technology: "4.4 out of 5".
 */
@Component({
  selector: 'app-dashboard-stars',
  standalone: true,
  imports: [LucideAngularModule, TranslocoPipe],
  template: `
    <span
      class="relative inline-flex align-middle"
      role="img"
      [attr.aria-label]="'dashboard.reviews.outOf' | transloco: { rating: formatted() }"
    >
      <span class="flex text-border-strong" aria-hidden="true">
        @for (n of positions; track n) {
          <lucide-icon [img]="icons.Star" [class]="starClass()" />
        }
      </span>
      <span
        class="absolute inset-y-0 left-0 overflow-hidden text-warning"
        [style.width.%]="percent()"
        aria-hidden="true"
        data-testid="stars-fill"
      >
        <span class="flex w-max">
          @for (n of positions; track n) {
            <lucide-icon [img]="icons.Star" [class]="starClass() + ' fill-current'" />
          }
        </span>
      </span>
    </span>
  `,
})
export class DashboardStarsComponent {
  private readonly language = inject(LanguageService);

  /** 0 to 5. */
  readonly rating = input.required<number>();
  /** Decimals of the spoken rating: 1 for an average, 0 for one review. */
  readonly decimals = input<0 | 1>(0);
  readonly size = input<'sm' | 'md'>('sm');

  readonly icons = { Star };
  readonly positions = [1, 2, 3, 4, 5];

  readonly percent = computed(() => Math.min(100, Math.max(0, (this.rating() / 5) * 100)));
  readonly starClass = computed(() => (this.size() === 'md' ? 'w-5 h-5' : 'w-3.5 h-3.5'));
  readonly formatted = computed(() =>
    new Intl.NumberFormat(this.language.locale(), {
      minimumFractionDigits: this.decimals(),
      maximumFractionDigits: this.decimals(),
    }).format(this.rating()),
  );
}
