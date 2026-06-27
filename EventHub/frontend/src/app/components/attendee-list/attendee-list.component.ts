import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event as EventModel, EventStatsResponse, Registration } from '../../models/models';
import { LucideAngularModule, Search, Users, CheckCircle, ScanLine, Download, RotateCcw, DollarSign, Mail } from 'lucide-angular';

@Component({
  selector: 'app-attendee-list',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-4xl py-8">

        <!-- Breadcrumb -->
        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6" aria-label="Breadcrumb">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">Dashboard</a>
          <span>/</span>
          <span class="text-foreground font-medium truncate max-w-xs">
            {{ event?.title || 'Event' }}
          </span>
          <span>/</span>
          <span class="text-muted-foreground">Attendees</span>
        </nav>

        <!-- Header -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground">Attendees</h1>
            @if (event) {
              <p class="text-sm text-muted-foreground mt-1">
                {{ event.title }} · {{ event.date | date:'MMM d, y' }}
              </p>
            }
          </div>

          <div class="flex items-center gap-2 flex-wrap">
            <button (click)="showMessage = true" class="btn btn-secondary btn-sm flex items-center gap-1.5">
              <lucide-icon [img]="icons.Mail" class="w-4 h-4" aria-hidden="true"></lucide-icon>
              Message
            </button>
            <button (click)="exportCsv()" [disabled]="exporting" class="btn btn-secondary btn-sm flex items-center gap-1.5">
              <lucide-icon [img]="icons.Download" class="w-4 h-4" aria-hidden="true"></lucide-icon>
              {{ exporting ? 'Exporting…' : 'Export Excel' }}
            </button>
            <a routerLink="/scan" class="btn btn-primary btn-sm flex items-center gap-1.5">
              <lucide-icon [img]="icons.ScanLine" class="w-4 h-4" aria-hidden="true"></lucide-icon>
              Scan tickets
            </a>

          <!-- Stats -->
          @if (stats) {
            <div class="flex items-center gap-4 text-sm">
              <div class="text-center">
                <p class="font-bold text-foreground text-lg">{{ stats.total_registrations }}</p>
                <p class="text-xs text-muted-foreground">Registered</p>
              </div>
              <div class="w-px h-8 bg-border"></div>
              <div class="text-center">
                <p class="font-bold text-foreground text-lg">{{ stats.checked_in }}</p>
                <p class="text-xs text-muted-foreground">Checked in</p>
              </div>
              <div class="w-px h-8 bg-border"></div>
              <div class="text-center">
                <p class="font-bold text-primary text-lg">{{ stats.check_in_rate }}%</p>
                <p class="text-xs text-muted-foreground">Rate</p>
              </div>
            </div>
          }
          </div>
        </div>

        <!-- Search -->
        <label class="flex items-center gap-2 mb-4 max-w-xs border border-border rounded-md px-3 h-9 bg-background focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-shadow cursor-text">
          <lucide-icon [img]="icons.Search" class="w-4 h-4 text-muted-foreground flex-shrink-0" aria-hidden="true"></lucide-icon>
          <input
            type="search"
            [(ngModel)]="searchQuery"
            (input)="onSearch()"
            placeholder="Search attendees..."
            class="flex-1 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
            aria-label="Search attendees"
          />
        </label>

        <!-- Table / list -->
        @if (loading) {
          <div class="flex items-center justify-center py-16 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">Loading attendees...</span>
          </div>

        } @else if (filtered.length === 0) {
          <div class="flex flex-col items-center justify-center py-16 text-center">
            <lucide-icon [img]="icons.Users" class="w-8 h-8 text-muted-foreground/40 mb-3" aria-hidden="true"></lucide-icon>
            <p class="text-sm text-muted-foreground">
              {{ searchQuery ? 'No attendees match your search.' : 'No attendees yet.' }}
            </p>
          </div>

        } @else {
          <!-- Desktop table -->
          <div class="card overflow-hidden hidden sm:block">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border bg-muted/40">
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Attendee</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Status</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Payment</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Check-in</th>
                  <th class="text-right px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border">
                @for (reg of filtered; track reg.id) {
                  <tr class="hover:bg-muted/30 transition-colors" [class.bg-[color:var(--pine-50)]]="reg.is_checked_in">
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-2.5">
                        <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary flex-shrink-0">
                          {{ reg.full_name?.charAt(0)?.toUpperCase() || reg.username.charAt(0).toUpperCase() }}
                        </div>
                        <div class="min-w-0">
                          <p class="font-medium text-foreground truncate">{{ reg.full_name || reg.username }}</p>
                          <p class="text-xs text-muted-foreground truncate">{{ reg.email || '@' + reg.username }}</p>
                          @if (reg.answers?.length) {
                            <div class="flex flex-wrap gap-1 mt-1">
                              @for (a of reg.answers; track a.label) {
                                <span class="text-[10px] bg-muted text-muted-foreground px-1.5 py-0.5 rounded" [title]="a.label">
                                  {{ a.label }}: <span class="text-foreground font-medium">{{ a.answer || '—' }}</span>
                                </span>
                              }
                            </div>
                          }
                        </div>
                      </div>
                    </td>
                    <td class="px-4 py-3">
                      <span class="badge {{ statusBadgeClass(reg.status) }}">{{ statusLabel(reg.status) }}</span>
                      @if (reg.promo) {
                        <span class="ml-1 text-[10px] font-bold uppercase text-primary bg-primary/10 px-1.5 py-0.5 rounded">{{ reg.promo.code }}</span>
                      }
                    </td>
                    <td class="px-4 py-3">
                      @if (reg.payment) {
                        @if (reg.payment.status === 'refunded') {
                          <span class="text-xs text-[color:var(--destructive)] font-medium">Refunded {{ '$' + reg.payment.refunded_amount }}</span>
                        } @else if (+reg.payment.refunded_amount > 0) {
                          <span class="text-xs text-foreground">{{ '$' + reg.payment.net_amount }}</span>
                          <span class="text-[10px] text-ember ml-1">(−{{ '$' + reg.payment.refunded_amount }})</span>
                        } @else {
                          <span class="text-xs text-foreground font-medium">{{ '$' + reg.payment.amount }}</span>
                          <span class="text-[10px] text-muted-foreground ml-1">{{ reg.payment.method === 'offline' ? 'cash' : 'card' }}</span>
                        }
                      } @else {
                        <span class="text-xs text-muted-foreground">—</span>
                      }
                    </td>
                    <td class="px-4 py-3">
                      @if (reg.is_checked_in) {
                        <span class="flex items-center gap-1 text-xs text-[color:var(--pine-600)] font-medium">
                          <lucide-icon [img]="icons.CheckCircle" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
                          {{ reg.checked_in_at | date:'HH:mm' }}
                        </span>
                      } @else if (reg.status === 'confirmed') {
                        <span class="text-xs text-muted-foreground">Awaiting scan</span>
                      } @else {
                        <span class="text-xs text-muted-foreground">—</span>
                      }
                    </td>
                    <td class="px-4 py-3 text-right whitespace-nowrap">
                      @if (reg.status === 'pending') {
                        <button (click)="markPaid(reg)" [disabled]="actingId === reg.id"
                          class="text-xs font-medium text-[color:var(--pine-600)] hover:text-[color:var(--pine-600)] inline-flex items-center gap-1">
                          <lucide-icon [img]="icons.DollarSign" class="w-3.5 h-3.5"></lucide-icon>
                          Mark paid
                        </button>
                      } @else if (reg.payment?.is_refundable) {
                        <button (click)="openRefund(reg)"
                          class="text-xs font-medium text-[color:var(--destructive)] hover:text-[color:var(--destructive)] inline-flex items-center gap-1">
                          <lucide-icon [img]="icons.RotateCcw" class="w-3.5 h-3.5"></lucide-icon>
                          Refund
                        </button>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Mobile cards -->
          <div class="sm:hidden space-y-3">
            @for (reg of filtered; track reg.id) {
              <div class="card p-4" [class.border-l-4]="true" [class.border-l-emerald-400]="reg.is_checked_in">
                <div class="flex items-center gap-3 mb-3">
                  <div class="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary">
                    {{ reg.full_name?.charAt(0)?.toUpperCase() || reg.username.charAt(0).toUpperCase() }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <p class="text-sm font-semibold text-foreground truncate">{{ reg.full_name || reg.username }}</p>
                    <p class="text-xs text-muted-foreground truncate">{{ reg.email || '@' + reg.username }}</p>
                  </div>
                  <span class="badge {{ statusBadgeClass(reg.status) }}">{{ statusLabel(reg.status) }}</span>
                </div>

                <div class="flex items-center justify-between text-xs">
                  @if (reg.payment) {
                    <span class="text-foreground font-medium">
                      @if (reg.payment.status === 'refunded') { Refunded {{ '$' + reg.payment.refunded_amount }} }
                      @else { {{ '$' + reg.payment.net_amount }} }
                    </span>
                  } @else {
                    <span class="text-muted-foreground">No payment</span>
                  }

                  @if (reg.status === 'pending') {
                    <button (click)="markPaid(reg)" [disabled]="actingId === reg.id" class="text-[color:var(--pine-600)] font-medium">Mark paid</button>
                  } @else if (reg.payment?.is_refundable) {
                    <button (click)="openRefund(reg)" class="text-[color:var(--destructive)] font-medium">Refund</button>
                  }
                </div>
              </div>
            }
          </div>
        }
      </div>
    </div>

    <!-- Refund modal -->
    @if (refundReg) {
      <div class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 animate-fade-in" (click)="refundReg = null">
        <div class="card w-full max-w-sm p-6 animate-slide-up" (click)="$event.stopPropagation()">
          <h3 class="text-lg font-bold text-foreground mb-1">Refund ticket</h3>
          <p class="text-sm text-muted-foreground mb-4">
            {{ refundReg.full_name || refundReg.username }} · paid {{ '$' + refundReg.payment?.net_amount }}
          </p>

          <label class="block text-sm font-medium text-foreground mb-1.5">Amount to refund</label>
          <div class="flex items-center gap-2 mb-2">
            <span class="text-muted-foreground">$</span>
            <input type="number" [(ngModel)]="refundAmount" [max]="refundReg.payment?.net_amount" min="0" step="0.01" class="input flex-1" />
            <button (click)="refundAmount = refundReg.payment?.net_amount || ''" class="btn btn-ghost btn-sm text-xs">Full</button>
          </div>

          <label class="block text-sm font-medium text-foreground mb-1.5 mt-3">Reason (optional)</label>
          <input [(ngModel)]="refundReason" placeholder="e.g. Event cancelled" class="input w-full mb-4" />

          <div class="flex gap-2">
            <button (click)="refundReg = null" class="btn btn-secondary flex-1">Cancel</button>
            <button (click)="confirmRefund()" [disabled]="refunding || !refundAmount" class="btn btn-danger flex-1">
              {{ refunding ? 'Refunding…' : 'Refund $' + (refundAmount || '0') }}
            </button>
          </div>
        </div>
      </div>
    }

    <!-- Message attendees modal -->
    @if (showMessage) {
      <div class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 animate-fade-in" (click)="showMessage = false">
        <div class="card w-full max-w-md p-6 animate-slide-up" (click)="$event.stopPropagation()">
          <h3 class="text-lg font-bold text-foreground mb-1 flex items-center gap-2">
            <lucide-icon [img]="icons.Mail" class="w-5 h-5 text-primary"></lucide-icon>
            Message attendees
          </h3>
          <p class="text-sm text-muted-foreground mb-4">Sends an in-app notification (and email if configured).</p>

          <label class="block text-sm font-medium text-foreground mb-1.5">Send to</label>
          <select [(ngModel)]="msgAudience" class="input w-full mb-3">
            <option value="all">Everyone</option>
            <option value="confirmed">Confirmed only</option>
            <option value="pending">Pending payment</option>
            <option value="checked_in">Checked in</option>
          </select>

          <label class="block text-sm font-medium text-foreground mb-1.5">Subject</label>
          <input [(ngModel)]="msgSubject" placeholder="e.g. Schedule update" class="input w-full mb-3" />

          <label class="block text-sm font-medium text-foreground mb-1.5">Message</label>
          <textarea [(ngModel)]="msgBody" rows="4" placeholder="Write your message to attendees…" class="input resize-none w-full mb-4"></textarea>

          <div class="flex gap-2">
            <button (click)="showMessage = false" class="btn btn-secondary flex-1">Cancel</button>
            <button (click)="sendMessage()" [disabled]="sending || !msgSubject.trim() || !msgBody.trim()" class="btn btn-primary flex-1">
              {{ sending ? 'Sending…' : 'Send message' }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class AttendeeListComponent implements OnInit {
  eventId: number | null = null;
  event: EventModel | null = null;
  registrations: Registration[] = [];
  filtered: Registration[] = [];
  stats: EventStatsResponse | null = null;
  loading = true;
  searchQuery = '';
  exporting = false;
  actingId: number | null = null;

  // Refund modal
  refundReg: Registration | null = null;
  refundAmount: string | number = '';
  refundReason = '';
  refunding = false;

  // Message modal
  showMessage = false;
  msgAudience = 'all';
  msgSubject = '';
  msgBody = '';
  sending = false;

  readonly icons = { Search, Users, CheckCircle, ScanLine, Download, RotateCcw, DollarSign, Mail };

  constructor(
    private route: ActivatedRoute,
    private eventService: EventService,
    private toastService: ToastService,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.eventId = +id;
      this.loadData();
    }
  }

  loadData(): void {
    if (!this.eventId) return;
    this.loading = true;
    this.eventService.getEvent(this.eventId).subscribe(e => { this.event = e; });
    this.eventService.getEventStats(this.eventId).subscribe(s => { this.stats = s; });
    this.eventService.getEventRegistrations(this.eventId).subscribe({
      next: regs => {
        this.registrations = regs.filter(r => r.status !== 'cancelled');
        this.filtered = [...this.registrations];
        this.loading = false;
      },
      error: () => { this.loading = false; },
    });
  }

  onSearch(): void {
    const q = this.searchQuery.toLowerCase().trim();
    this.filtered = q
      ? this.registrations.filter(r => r.username.toLowerCase().includes(q))
      : [...this.registrations];
  }

  statusBadgeClass(status: string): string {
    const map: Record<string, string> = {
      confirmed: 'badge-confirmed', pending: 'badge-pending',
      rejected: 'badge-rejected', cancelled: 'badge-rejected',
    };
    return map[status] ?? 'badge-pending';
  }

  statusLabel(status: string): string {
    const map: Record<string, string> = {
      confirmed: 'Confirmed',
      pending: 'Pending payment',
      rejected: 'Cancelled',
      cancelled: 'Cancelled',
    };
    return map[status] ?? status;
  }

  exportCsv(): void {
    if (!this.eventId) return;
    this.exporting = true;
    this.eventService.exportAttendees(this.eventId).subscribe({
      next: blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(this.event?.title || 'event').replace(/\s+/g, '-')}-attendees.xlsx`;
        a.click();
        window.URL.revokeObjectURL(url);
        this.exporting = false;
      },
      error: () => { this.exporting = false; this.toastService.error('Export failed.'); },
    });
  }

  markPaid(reg: Registration): void {
    this.actingId = reg.id;
    this.eventService.markOfflinePaid(reg.id).subscribe({
      next: () => { this.toastService.success('Marked as paid.'); this.actingId = null; this.loadData(); },
      error: () => { this.actingId = null; this.toastService.error('Could not mark as paid.'); },
    });
  }

  openRefund(reg: Registration): void {
    this.refundReg = reg;
    this.refundAmount = reg.payment?.net_amount || '';
    this.refundReason = '';
  }

  confirmRefund(): void {
    if (!this.refundReg) return;
    this.refunding = true;
    this.eventService.refundRegistration(this.refundReg.id, {
      amount: String(this.refundAmount),
      reason: this.refundReason,
    }).subscribe({
      next: () => {
        this.toastService.success('Refund issued.');
        this.refunding = false;
        this.refundReg = null;
        this.loadData();
      },
      error: err => {
        this.refunding = false;
        this.toastService.error(err.error?.error || 'Refund failed.');
      },
    });
  }

  sendMessage(): void {
    if (!this.eventId || !this.msgSubject.trim() || !this.msgBody.trim()) return;
    this.sending = true;
    this.eventService.broadcast(this.eventId, {
      subject: this.msgSubject.trim(),
      body: this.msgBody.trim(),
      audience: this.msgAudience,
    }).subscribe({
      next: res => {
        this.sending = false;
        this.showMessage = false;
        this.msgSubject = ''; this.msgBody = '';
        const emailNote = res.email_enabled ? ` (${res.emailed} emailed)` : '';
        this.toastService.success(`Sent to ${res.recipients} attendee(s)${emailNote}.`);
      },
      error: err => {
        this.sending = false;
        this.toastService.error(err.error?.error || 'Could not send message.');
      },
    });
  }
}
