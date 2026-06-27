import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService, PromoCode } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, Tag, Plus, Trash2, Check, X, Percent, DollarSign } from 'lucide-angular';

@Component({
  selector: 'app-promo-codes',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">

        <!-- Breadcrumb -->
        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">Dashboard</a>
          <span>/</span>
          @if (eventId) {
            <a [routerLink]="['/organizer/events', eventId, 'attendees']" class="hover:text-foreground transition-colors truncate max-w-[180px]">{{ event?.title || 'Event' }}</a>
          }
          <span>/</span>
          <span class="text-foreground font-medium">Promo codes</span>
        </nav>

        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground flex items-center gap-2">
              <lucide-icon [img]="icons.Tag" class="w-6 h-6 text-primary"></lucide-icon>
              Promo codes
            </h1>
            <p class="text-sm text-muted-foreground mt-1">{{ event?.title }}</p>
          </div>
          <button (click)="showForm = !showForm" class="btn btn-primary btn-sm flex items-center gap-1.5">
            <lucide-icon [img]="icons.Plus" class="w-4 h-4"></lucide-icon>
            New code
          </button>
        </div>

        <!-- Create form -->
        @if (showForm) {
          <div class="card p-5 mb-6 animate-slide-up">
            <h2 class="font-semibold text-foreground mb-4">Create a promo code</h2>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Code</label>
                <input [(ngModel)]="form.code" placeholder="SAVE20" class="input w-full uppercase" />
              </div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Type</label>
                <div class="flex gap-2">
                  <button type="button" (click)="form.discount_type = 'percent'"
                    class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border text-sm font-medium transition-colors"
                    [class]="form.discount_type === 'percent' ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground'">
                    <lucide-icon [img]="icons.Percent" class="w-4 h-4"></lucide-icon> Percent
                  </button>
                  <button type="button" (click)="form.discount_type = 'fixed'"
                    class="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg border text-sm font-medium transition-colors"
                    [class]="form.discount_type === 'fixed' ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground'">
                    <lucide-icon [img]="icons.DollarSign" class="w-4 h-4"></lucide-icon> Fixed
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">
                  {{ form.discount_type === 'percent' ? 'Discount (%)' : 'Discount ($)' }}
                </label>
                <input type="number" [(ngModel)]="form.discount_value" min="0" step="0.01" class="input w-full" />
              </div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Max uses <span class="text-muted-foreground font-normal">(blank = ∞)</span></label>
                <input type="number" [(ngModel)]="form.max_uses" min="1" placeholder="Unlimited" class="input w-full" />
              </div>
              <div class="sm:col-span-2">
                <label class="block text-sm font-medium text-foreground mb-1.5">Expires <span class="text-muted-foreground font-normal">(optional)</span></label>
                <input type="datetime-local" [(ngModel)]="form.expires_at" class="input w-full" />
              </div>
            </div>
            <div class="flex gap-2 mt-4">
              <button (click)="showForm = false" class="btn btn-secondary flex-1">Cancel</button>
              <button (click)="create()" [disabled]="!canSubmit() || saving" class="btn btn-primary flex-1">
                {{ saving ? 'Creating…' : 'Create code' }}
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
              <lucide-icon [img]="icons.Tag" class="w-7 h-7 text-muted-foreground/50"></lucide-icon>
            </div>
            <h3 class="font-semibold text-foreground mb-1">No promo codes yet</h3>
            <p class="text-sm text-muted-foreground">Create a code to offer discounts at checkout.</p>
          </div>
        } @else {
          <div class="space-y-3">
            @for (c of codes; track c.id) {
              <div class="card p-4 flex items-center gap-4" [class.opacity-60]="!c.is_valid">
                <div class="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 font-bold text-lg"
                     [class]="c.discount_type === 'percent' ? 'bg-ember/10 text-ember' : 'bg-[color:var(--pine-50)] text-[color:var(--pine-600)]'">
                  @if (c.discount_type === 'percent') { {{ c.discount_value }}% }
                  @else { {{ '$' + c.discount_value }} }
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-mono font-bold text-foreground tracking-wide">{{ c.code }}</span>
                    @if (c.is_valid) {
                      <span class="text-[10px] font-bold uppercase text-[color:var(--pine-600)] bg-[color:var(--pine-50)] px-1.5 py-0.5 rounded">Active</span>
                    } @else if (c.is_expired) {
                      <span class="text-[10px] font-bold uppercase text-ember bg-[color:var(--destructive-50)] px-1.5 py-0.5 rounded">Expired</span>
                    } @else if (c.is_exhausted) {
                      <span class="text-[10px] font-bold uppercase text-warning bg-[color:var(--warning-50)] px-1.5 py-0.5 rounded">Used up</span>
                    } @else {
                      <span class="text-[10px] font-bold uppercase text-muted-foreground bg-muted px-1.5 py-0.5 rounded">Disabled</span>
                    }
                  </div>
                  <p class="text-xs text-muted-foreground mt-0.5">
                    Used {{ c.times_used }}{{ c.max_uses ? ' / ' + c.max_uses : '' }} times
                    @if (c.expires_at) { · expires {{ c.expires_at | date:'MMM d, y' }} }
                  </p>
                </div>
                <button (click)="toggleActive(c)" class="btn btn-ghost btn-sm text-xs" [title]="c.is_active ? 'Disable' : 'Enable'">
                  <lucide-icon [img]="c.is_active ? icons.X : icons.Check" class="w-4 h-4"></lucide-icon>
                </button>
                <button (click)="remove(c)" class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]">
                  <lucide-icon [img]="icons.Trash2" class="w-4 h-4"></lucide-icon>
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
  eventId = 0;
  event: EventModel | null = null;
  codes: PromoCode[] = [];
  loading = true;
  showForm = false;
  saving = false;

  form: any = { code: '', discount_type: 'percent', discount_value: null, max_uses: null, expires_at: '' };

  readonly icons = { Tag, Plus, Trash2, Check, X, Percent, DollarSign };

  constructor(
    private route: ActivatedRoute,
    private eventService: EventService,
    private toast: ToastService,
  ) {}

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.eventService.getEvent(this.eventId).subscribe(e => this.event = e);
    this.load();
  }

  load(): void {
    this.loading = true;
    this.eventService.getPromoCodes(this.eventId).subscribe({
      next: c => { this.codes = c; this.loading = false; },
      error: () => { this.loading = false; this.toast.error('Failed to load promo codes.'); },
    });
  }

  canSubmit(): boolean {
    return !!this.form.code?.trim() && this.form.discount_value > 0;
  }

  create(): void {
    if (!this.canSubmit()) return;
    this.saving = true;
    const payload: any = {
      code: this.form.code.trim().toUpperCase(),
      discount_type: this.form.discount_type,
      discount_value: this.form.discount_value,
    };
    if (this.form.max_uses) payload.max_uses = this.form.max_uses;
    if (this.form.expires_at) payload.expires_at = new Date(this.form.expires_at).toISOString();

    this.eventService.createPromoCode(this.eventId, payload).subscribe({
      next: () => {
        this.toast.success('Promo code created.');
        this.saving = false;
        this.showForm = false;
        this.form = { code: '', discount_type: 'percent', discount_value: null, max_uses: null, expires_at: '' };
        this.load();
      },
      error: err => {
        this.saving = false;
        const e = err.error;
        this.toast.error(e?.code?.[0] || e?.detail || 'Could not create code (is it a duplicate?).');
      },
    });
  }

  toggleActive(c: PromoCode): void {
    this.eventService.updatePromoCode(c.id, { is_active: !c.is_active }).subscribe({
      next: updated => { Object.assign(c, updated); },
      error: () => this.toast.error('Update failed.'),
    });
  }

  remove(c: PromoCode): void {
    this.eventService.deletePromoCode(c.id).subscribe({
      next: () => { this.codes = this.codes.filter(x => x.id !== c.id); this.toast.success('Deleted.'); },
      error: () => this.toast.error('Delete failed.'),
    });
  }
}
