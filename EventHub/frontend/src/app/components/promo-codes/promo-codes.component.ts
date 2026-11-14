import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import {
  EventService,
  PromoCode,
  type DiscountType,
  type PromoCodeInput,
} from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event as EventModel } from '../../models/models';
import {
  LucideAngularModule,
  Tag,
  Plus,
  Trash2,
  Check,
  X,
  Percent,
  DollarSign,
} from 'lucide-angular';
import { MoneyPipe } from '../../pipes/money.pipe';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

/** The "new code" form; numeric inputs are null while empty. */
interface PromoForm {
  code: string;
  discount_type: DiscountType;
  discount_value: number | null;
  max_uses: number | null;
  expires_at: string;
}

const emptyPromoForm = (): PromoForm => ({
  code: '',
  discount_type: 'percent',
  discount_value: null,
  max_uses: null,
  expires_at: '',
});

@Component({
  selector: 'app-promo-codes',
  standalone: true,
  imports: [
    MoneyPipe,
    CommonModule,
    FormsModule,
    RouterModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">
        <!-- Breadcrumb -->
        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">{{
            'nav.dashboard' | transloco
          }}</a>
          <span>/</span>
          @if (eventId) {
            <a
              [routerLink]="['/organizer/events', eventId, 'attendees']"
              class="hover:text-foreground transition-colors truncate max-w-[180px]"
              >{{ event?.title || ('nav.event' | transloco) }}</a
            >
          }
          <span>/</span>
          <span class="text-foreground font-medium">{{ 'promo.promoCodes' | transloco }}</span>
        </nav>

        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground flex items-center gap-2">
              <lucide-icon [img]="icons.Tag" class="w-6 h-6 text-primary" />
              {{ 'promo.promoCodes' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground mt-1">{{ event?.title }}</p>
          </div>
          <button
            (click)="showForm = !showForm"
            class="btn btn-primary btn-sm flex items-center gap-1.5"
          >
            <lucide-icon [img]="icons.Plus" class="w-4 h-4" />
            {{ 'promo.newCode' | transloco }}
          </button>
        </div>

        <!-- Create form -->
        @if (showForm) {
          <div class="card p-5 mb-6 animate-slide-up">
            <h2 class="font-semibold text-foreground mb-4">
              {{ 'promo.createAPromoCode' | transloco }}
            </h2>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label
                  for="promo-codes-code"
                  class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'promo.code' | transloco }}</label
                >
                <input
                  id="promo-codes-code"
                  [(ngModel)]="form.code"
                  [placeholder]="'promo.save' | transloco"
                  class="input w-full uppercase"
                />
              </div>
              <div>
                <p id="promo-type-caption" class="block text-sm font-medium text-foreground mb-1.5">
                  {{ 'promo.type' | transloco }}
                </p>
                <div class="flex gap-2" role="group" aria-labelledby="promo-type-caption">
                  <button
                    type="button"
                    (click)="form.discount_type = 'percent'"
                    [attr.aria-pressed]="form.discount_type === 'percent'"
                    class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border text-sm font-medium transition-colors"
                    [class]="
                      form.discount_type === 'percent'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground'
                    "
                  >
                    <lucide-icon [img]="icons.Percent" class="w-4 h-4" />
                    {{ 'promo.percent' | transloco }}
                  </button>
                  <button
                    type="button"
                    (click)="form.discount_type = 'fixed'"
                    [attr.aria-pressed]="form.discount_type === 'fixed'"
                    class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border text-sm font-medium transition-colors"
                    [class]="
                      form.discount_type === 'fixed'
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground'
                    "
                  >
                    <lucide-icon [img]="icons.DollarSign" class="w-4 h-4" />
                    {{ 'promo.fixed' | transloco }}
                  </button>
                </div>
              </div>
              <div>
                <label
                  for="promo-codes-discount-value"
                  class="block text-sm font-medium text-foreground mb-1.5"
                >
                  {{
                    (form.discount_type === 'percent' ? 'promo.discount' : 'promo.discount2')
                      | transloco
                  }}
                </label>
                <input
                  id="promo-codes-discount-value"
                  type="number"
                  [(ngModel)]="form.discount_value"
                  min="0"
                  step="0.01"
                  class="input w-full"
                />
              </div>
              <div>
                <label
                  for="promo-codes-max-uses"
                  class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'promo.maxUses' | transloco }}
                  <span class="text-muted-foreground font-normal">{{
                    'promo.blank' | transloco
                  }}</span></label
                >
                <input
                  id="promo-codes-max-uses"
                  type="number"
                  [(ngModel)]="form.max_uses"
                  min="1"
                  [placeholder]="'promo.unlimited' | transloco"
                  class="input w-full"
                />
              </div>
              <div class="sm:col-span-2">
                <label
                  for="promo-codes-expires-at"
                  class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'promo.expires' | transloco }}
                  <span class="text-muted-foreground font-normal">{{
                    'checkout.optional' | transloco
                  }}</span></label
                >
                <input
                  id="promo-codes-expires-at"
                  type="datetime-local"
                  [(ngModel)]="form.expires_at"
                  class="input w-full"
                />
              </div>
            </div>
            <div class="flex gap-2 mt-4">
              <button (click)="showForm = false" class="btn btn-secondary flex-1">
                {{ 'common.cancel' | transloco }}
              </button>
              <button
                (click)="create()"
                [disabled]="!canSubmit() || saving"
                class="btn btn-primary flex-1"
              >
                {{ (saving ? 'checkin.creating' : 'promo.createCode') | transloco }}
              </button>
            </div>
          </div>
        }

        <!-- List -->
        @if (loading) {
          <div class="flex justify-center py-16"><span class="spinner spinner-lg"></span></div>
        } @else if (codes.length === 0) {
          <div class="flex flex-col items-center justify-center py-16 text-center">
            <div class="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.Tag" class="w-7 h-7 text-muted-foreground/50" />
            </div>
            <h3 class="font-semibold text-foreground mb-1">
              {{ 'promo.noPromoCodesYet' | transloco }}
            </h3>
            <p class="text-sm text-muted-foreground">
              {{ 'promo.createACodeTo' | transloco }}
            </p>
          </div>
        } @else {
          <div class="space-y-3">
            @for (c of codes; track c.id) {
              <div class="card p-4 flex items-center gap-4" [class.opacity-60]="!c.is_valid">
                <div
                  class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 font-bold text-lg"
                  [class]="
                    c.discount_type === 'percent'
                      ? 'bg-ember/10 text-ember'
                      : 'bg-[color:var(--pine-50)] text-[color:var(--pine-600)]'
                  "
                >
                  @if (c.discount_type === 'percent') {
                    {{ c.discount_value }}%
                  } @else {
                    {{ c.discount_value | money: event?.currency }}
                  }
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-mono font-bold text-foreground tracking-wide">{{
                      c.code
                    }}</span>
                    @if (c.is_valid) {
                      <span
                        class="text-[10px] font-bold uppercase text-[color:var(--pine-600)] bg-[color:var(--pine-50)] px-1.5 py-0.5 rounded"
                        >{{ 'common.active' | transloco }}</span
                      >
                    } @else if (c.is_expired) {
                      <span
                        class="text-[10px] font-bold uppercase text-ember bg-[color:var(--destructive-50)] px-1.5 py-0.5 rounded"
                        >{{ 'promo.expired' | transloco }}</span
                      >
                    } @else if (c.is_exhausted) {
                      <span
                        class="text-[10px] font-bold uppercase text-warning bg-[color:var(--warning-50)] px-1.5 py-0.5 rounded"
                        >{{ 'promo.usedUp' | transloco }}</span
                      >
                    } @else {
                      <span
                        class="text-[10px] font-bold uppercase text-muted-foreground bg-muted px-1.5 py-0.5 rounded"
                        >{{ 'promo.disabled' | transloco }}</span
                      >
                    }
                  </div>
                  <p class="text-xs text-muted-foreground mt-0.5">
                    {{
                      (c.max_uses ? 'promo.usedOf' : 'promo.used')
                        | transloco: { used: c.times_used, max: c.max_uses }
                    }}
                    @if (c.expires_at) {
                      {{
                        'promo.expiresExpiresat'
                          | transloco: { expiresAt: (c.expires_at | localDate: 'MMM d, y') }
                      }}
                    }
                  </p>
                </div>
                <button
                  (click)="toggleActive(c)"
                  class="btn btn-ghost btn-sm text-xs"
                  [title]="
                    (c.is_active ? 'eventSettings.disable' : 'eventSettings.enable') | transloco
                  "
                >
                  <lucide-icon [img]="c.is_active ? icons.X : icons.Check" class="w-4 h-4" />
                </button>
                <button
                  (click)="remove(c)"
                  class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]"
                >
                  <lucide-icon [img]="icons.Trash2" class="w-4 h-4" />
                </button>
              </div>
            }
          </div>
        }
      </div>
    </div>
  `,
})
export class PromoCodesComponent implements OnInit {
  private i18n = inject(LanguageService);
  private route = inject(ActivatedRoute);
  private eventService = inject(EventService);
  private toast = inject(ToastService);

  eventId = 0;
  event: EventModel | null = null;
  codes: PromoCode[] = [];
  loading = true;
  showForm = false;
  saving = false;

  form: PromoForm = emptyPromoForm();

  readonly icons = { Tag, Plus, Trash2, Check, X, Percent, DollarSign };

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.eventService.getEvent(this.eventId).subscribe((e) => (this.event = e));
    this.load();
  }

  load(): void {
    this.loading = true;
    this.eventService.getPromoCodes(this.eventId).subscribe({
      next: (c) => {
        this.codes = c;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.toast.error(this.i18n.t('promo.failedToLoadPromo'));
      },
    });
  }

  canSubmit(): boolean {
    return !!this.form.code.trim() && (this.form.discount_value ?? 0) > 0;
  }

  create(): void {
    if (!this.canSubmit()) return;
    this.saving = true;
    const payload: PromoCodeInput = {
      code: this.form.code.trim().toUpperCase(),
      discount_type: this.form.discount_type,
      discount_value: this.form.discount_value ?? 0,
    };
    if (this.form.max_uses) payload.max_uses = this.form.max_uses;
    if (this.form.expires_at) payload.expires_at = new Date(this.form.expires_at).toISOString();

    this.eventService.createPromoCode(this.eventId, payload).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('promo.promoCodeCreated'));
        this.saving = false;
        this.showForm = false;
        this.form = emptyPromoForm();
        this.load();
      },
      error: (err) => {
        this.saving = false;
        this.toast.error(
          apiErrorMessage(err, this.i18n.t('promo.couldNotCreateCode'), 'code', 'detail'),
        );
      },
    });
  }

  toggleActive(c: PromoCode): void {
    this.eventService.updatePromoCode(c.id, { is_active: !c.is_active }).subscribe({
      next: (updated) => {
        Object.assign(c, updated);
      },
      error: () => this.toast.error(this.i18n.t('eventSettings.updateFailed')),
    });
  }

  remove(c: PromoCode): void {
    this.eventService.deletePromoCode(c.id).subscribe({
      next: () => {
        this.codes = this.codes.filter((x) => x.id !== c.id);
        this.toast.success(this.i18n.t('eventSettings.deleted'));
      },
      error: () => this.toast.error(this.i18n.t('eventSettings.deleteFailed')),
    });
  }
}
