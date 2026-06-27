import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService, TicketType, TicketKind } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, Ticket, Plus, Trash2, Check, X } from 'lucide-angular';

@Component({
  selector: 'app-ticket-types',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">

        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">Dashboard</a>
          <span>/</span>
          @if (eventId) {
            <a [routerLink]="['/organizer/events', eventId, 'attendees']" class="hover:text-foreground transition-colors truncate max-w-[180px]">{{ event?.title || 'Event' }}</a>
          }
          <span>/</span>
          <span class="text-foreground font-medium">Ticket types</span>
        </nav>

        <div class="flex items-center justify-between mb-2">
          <h1 class="text-2xl font-bold text-foreground flex items-center gap-2">
            <lucide-icon [img]="icons.Ticket" class="w-6 h-6 text-primary"></lucide-icon>
            Ticket types
          </h1>
          <button (click)="showForm = !showForm" class="btn btn-primary btn-sm flex items-center gap-1.5">
            <lucide-icon [img]="icons.Plus" class="w-4 h-4"></lucide-icon> New tier
          </button>
        </div>
        <p class="text-sm text-muted-foreground mb-6">
          Offer multiple tiers for {{ event?.title }} — General, VIP, Early Bird, or a donation.
          When you add tiers, they replace the single price at checkout.
        </p>

        @if (showForm) {
          <div class="card p-5 mb-6 animate-slide-up">
            <h2 class="font-semibold text-foreground mb-4">New ticket tier</h2>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="sm:col-span-2">
                <label class="block text-sm font-medium text-foreground mb-1.5">Name</label>
                <input [(ngModel)]="form.name" placeholder="e.g. VIP, Early Bird, General Admission" class="input w-full" />
              </div>
              <div class="sm:col-span-2">
                <label class="block text-sm font-medium text-foreground mb-1.5">Description <span class="text-muted-foreground font-normal">(optional)</span></label>
                <input [(ngModel)]="form.description" placeholder="What's included with this tier?" class="input w-full" />
              </div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Type</label>
                <select [(ngModel)]="form.kind" class="input w-full">
                  <option value="paid">Paid</option>
                  <option value="free">Free</option>
                  <option value="donation">Donation (pay what you want)</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">
                  {{ form.kind === 'donation' ? 'Minimum ($)' : 'Price ($)' }}
                </label>
                <input type="number" [(ngModel)]="form.price" min="0" step="0.01" [disabled]="form.kind === 'free'" class="input w-full" />
              </div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Quantity <span class="text-muted-foreground font-normal">(blank = ∞)</span></label>
                <input type="number" [(ngModel)]="form.quantity" min="1" placeholder="Unlimited" class="input w-full" />
              </div>
              <div></div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Sales start <span class="text-muted-foreground font-normal">(optional)</span></label>
                <input type="datetime-local" [(ngModel)]="form.sale_start" class="input w-full" />
              </div>
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Sales end <span class="text-muted-foreground font-normal">(optional)</span></label>
                <input type="datetime-local" [(ngModel)]="form.sale_end" class="input w-full" />
              </div>
            </div>
            <div class="flex gap-2 mt-4">
              <button (click)="showForm = false" class="btn btn-secondary flex-1">Cancel</button>
              <button (click)="create()" [disabled]="!form.name.trim() || saving" class="btn btn-primary flex-1">
                {{ saving ? 'Creating…' : 'Create tier' }}
              </button>
            </div>
          </div>
        }

        @if (loading) {
          <div class="flex justify-center py-16"><span class="spinner spinner-lg"></span></div>
        } @else if (tiers.length === 0) {
          <div class="flex flex-col items-center justify-center py-16 text-center">
            <div class="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.Ticket" class="w-7 h-7 text-muted-foreground/50"></lucide-icon>
            </div>
            <h3 class="font-semibold text-foreground mb-1">No ticket tiers</h3>
            <p class="text-sm text-muted-foreground">This event uses its single price. Add tiers for VIP/Early Bird pricing.</p>
          </div>
        } @else {
          <div class="space-y-3">
            @for (t of tiers; track t.id) {
              <div class="card p-4 flex items-center gap-4" [class.opacity-60]="!t.is_active">
                <div class="w-14 h-14 rounded-xl flex flex-col items-center justify-center flex-shrink-0 font-bold"
                     [class]="t.kind === 'donation' ? 'bg-ember/10 text-ember' : t.kind === 'free' ? 'bg-[color:var(--pine-50)] text-[color:var(--pine-600)]' : 'bg-primary/10 text-primary'">
                  @if (t.kind === 'free') { <span class="text-sm">Free</span> }
                  @else { <span class="text-base">{{ '$' + t.price }}</span> }
                  @if (t.kind === 'donation') { <span class="text-[9px] uppercase">min</span> }
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-semibold text-foreground">{{ t.name }}</span>
                    <span class="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded {{ saleStateClass(t.sale_state) }}">{{ saleStateLabel(t.sale_state) }}</span>
                  </div>
                  @if (t.description) { <p class="text-xs text-muted-foreground mt-0.5">{{ t.description }}</p> }
                  <p class="text-xs text-muted-foreground mt-0.5">
                    Sold {{ t.sold }}{{ t.quantity ? ' / ' + t.quantity : '' }}
                    @if (t.sale_end) { · ends {{ t.sale_end | date:'MMM d, HH:mm' }} }
                  </p>
                </div>
                <button (click)="toggleActive(t)" class="btn btn-ghost btn-sm" [title]="t.is_active ? 'Disable' : 'Enable'">
                  <lucide-icon [img]="t.is_active ? icons.X : icons.Check" class="w-4 h-4"></lucide-icon>
                </button>
                <button (click)="remove(t)" class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]">
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
export class TicketTypesComponent implements OnInit {
  eventId = 0;
  event: EventModel | null = null;
  tiers: TicketType[] = [];
  loading = true;
  showForm = false;
  saving = false;

  form: any = { name: '', description: '', kind: 'paid' as TicketKind, price: null, quantity: null, sale_start: '', sale_end: '' };

  readonly icons = { Ticket, Plus, Trash2, Check, X };

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
    this.eventService.getTicketTypes(this.eventId).subscribe({
      next: t => { this.tiers = t; this.loading = false; },
      error: () => { this.loading = false; this.toast.error('Failed to load ticket types.'); },
    });
  }

  create(): void {
    if (!this.form.name.trim()) return;
    this.saving = true;
    const payload: any = {
      name: this.form.name.trim(),
      description: this.form.description.trim(),
      kind: this.form.kind,
      price: this.form.kind === 'free' ? 0 : (this.form.price || 0),
      order: this.tiers.length,
    };
    if (this.form.quantity) payload.quantity = this.form.quantity;
    if (this.form.sale_start) payload.sale_start = new Date(this.form.sale_start).toISOString();
    if (this.form.sale_end) payload.sale_end = new Date(this.form.sale_end).toISOString();

    this.eventService.createTicketType(this.eventId, payload).subscribe({
      next: () => {
        this.toast.success('Ticket tier created.');
        this.saving = false;
        this.showForm = false;
        this.form = { name: '', description: '', kind: 'paid', price: null, quantity: null, sale_start: '', sale_end: '' };
        this.load();
      },
      error: err => {
        this.saving = false;
        this.toast.error(err.error?.price?.[0] || err.error?.detail || 'Could not create tier.');
      },
    });
  }

  toggleActive(t: TicketType): void {
    this.eventService.updateTicketType(t.id, { is_active: !t.is_active }).subscribe({
      next: u => { Object.assign(t, u); },
      error: () => this.toast.error('Update failed.'),
    });
  }

  remove(t: TicketType): void {
    this.eventService.deleteTicketType(t.id).subscribe({
      next: () => { this.tiers = this.tiers.filter(x => x.id !== t.id); this.toast.success('Deleted.'); },
      error: () => this.toast.error('Delete failed.'),
    });
  }

  saleStateLabel(s: string): string {
    return { on_sale: 'On sale', sold_out: 'Sold out', scheduled: 'Scheduled', ended: 'Ended', inactive: 'Off' }[s] ?? s;
  }
  saleStateClass(s: string): string {
    return {
      on_sale: 'text-[color:var(--pine-600)] bg-[color:var(--pine-50)]',
      sold_out: 'text-ember bg-[color:var(--destructive-50)]',
      scheduled: 'text-[color:var(--pine-600)] bg-[color:var(--pine-50)]',
      ended: 'text-muted-foreground bg-muted',
      inactive: 'text-muted-foreground bg-muted',
    }[s] ?? 'text-muted-foreground bg-muted';
  }
}
