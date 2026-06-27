import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService, EventStaff, Affiliate, Webhook, WebhookTrigger, RefundRequest } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { ModalService } from '../../services/modal.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, Users, Share2, Webhook as WebhookIcon, Plus, Trash2, Copy, Check, Link2, RotateCcw, Armchair, AlertTriangle } from 'lucide-angular';

@Component({
  selector: 'app-event-settings',
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
          <span class="text-foreground font-medium">Settings</span>
        </nav>

        <h1 class="text-2xl font-bold text-foreground mb-1">Event settings</h1>
        <p class="text-sm text-muted-foreground mb-6">{{ event?.title }}</p>

        <!-- Tabs -->
        <div class="flex border-b border-border mb-6 gap-1">
          <button (click)="tab='team'" class="px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
            [class]="tab==='team' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'">
            <lucide-icon [img]="icons.Users" class="w-4 h-4"></lucide-icon> Team
          </button>
          <button (click)="tab='affiliates'" class="px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
            [class]="tab==='affiliates' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'">
            <lucide-icon [img]="icons.Share2" class="w-4 h-4"></lucide-icon> Affiliates
          </button>
          <button (click)="tab='webhooks'" class="px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
            [class]="tab==='webhooks' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'">
            <lucide-icon [img]="icons.WebhookIcon" class="w-4 h-4"></lucide-icon> Webhooks
          </button>
          <button (click)="tab='refunds'" class="px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
            [class]="tab==='refunds' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'">
            <lucide-icon [img]="icons.RotateCcw" class="w-4 h-4"></lucide-icon> Refunds
            @if (pendingRefunds > 0) {
              <span class="bg-[color:var(--destructive)] text-white text-[10px] font-bold rounded-full px-1.5 min-w-[18px] text-center">{{ pendingRefunds }}</span>
            }
          </button>
          <button (click)="tab='seatmap'" class="px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
            [class]="tab==='seatmap' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'">
            <lucide-icon [img]="icons.Armchair" class="w-4 h-4"></lucide-icon> Seat map
          </button>
          <button (click)="tab='danger'" class="px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5"
            [class]="tab==='danger' ? 'border-[color:var(--destructive)] text-[color:var(--destructive)]' : 'border-transparent text-muted-foreground hover:text-foreground'">
            <lucide-icon [img]="icons.AlertTriangle" class="w-4 h-4"></lucide-icon> Danger
          </button>
        </div>

        <!-- ───────── TEAM ───────── -->
        @if (tab === 'team') {
          <div class="card p-5 mb-5">
            <h2 class="font-semibold text-foreground mb-3">Invite a team member</h2>
            <div class="flex flex-col sm:flex-row gap-2">
              <input [(ngModel)]="staffUsername" placeholder="Username" class="input flex-1" />
              <select [(ngModel)]="staffRole" class="input sm:w-56">
                <option value="co_organizer">Co-organizer (full access)</option>
                <option value="check_in">Check-in staff (scan only)</option>
              </select>
              <button (click)="addStaff()" [disabled]="!staffUsername.trim() || savingStaff" class="btn btn-primary">
                {{ savingStaff ? '…' : 'Invite' }}
              </button>
            </div>
          </div>

          @if (staff.length === 0) {
            <p class="text-sm text-muted-foreground text-center py-8">No team members yet. You have full access as the organizer.</p>
          } @else {
            <div class="space-y-2">
              @for (s of staff; track s.id) {
                <div class="card p-4 flex items-center gap-3">
                  <div class="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary">
                    {{ s.username.charAt(0).toUpperCase() }}
                  </div>
                  <div class="flex-1 min-w-0">
                    <p class="font-medium text-foreground">{{ s.username }}</p>
                    <p class="text-xs text-muted-foreground">{{ s.email }}</p>
                  </div>
                  <span class="text-[11px] font-bold uppercase px-2 py-1 rounded-full"
                    [class]="s.role === 'co_organizer' ? 'text-primary bg-primary/10' : 'text-warning bg-[color:var(--warning-50)]'">
                    {{ s.role === 'co_organizer' ? 'Co-organizer' : 'Check-in' }}
                  </span>
                  <button (click)="removeStaff(s)" class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]">
                    <lucide-icon [img]="icons.Trash2" class="w-4 h-4"></lucide-icon>
                  </button>
                </div>
              }
            </div>
          }
        }

        <!-- ───────── AFFILIATES ───────── -->
        @if (tab === 'affiliates') {
          <div class="card p-5 mb-5">
            <h2 class="font-semibold text-foreground mb-3">New promoter link</h2>
            <div class="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-2">
              <input [(ngModel)]="affName" placeholder="Promoter name (e.g. Instagram)" class="input" />
              <input [(ngModel)]="affCode" placeholder="CODE" class="input uppercase sm:w-32" />
              <button (click)="addAffiliate()" [disabled]="!affName.trim() || !affCode.trim() || savingAff" class="btn btn-primary">
                {{ savingAff ? '…' : 'Create' }}
              </button>
            </div>
          </div>

          @if (affiliates.length === 0) {
            <p class="text-sm text-muted-foreground text-center py-8">No promoters yet. Create a tracked link to attribute sales.</p>
          } @else {
            <div class="space-y-3">
              @for (a of affiliates; track a.id) {
                <div class="card p-4">
                  <div class="flex items-center gap-3 mb-3">
                    <div class="flex-1 min-w-0">
                      <p class="font-semibold text-foreground">{{ a.name }}</p>
                      <p class="text-xs text-muted-foreground font-mono">{{ a.code }}</p>
                    </div>
                    <div class="text-center px-3">
                      <p class="font-bold text-foreground">{{ a.clicks }}</p>
                      <p class="text-[10px] uppercase text-muted-foreground">clicks</p>
                    </div>
                    <div class="text-center px-3">
                      <p class="font-bold text-foreground">{{ a.sales }}</p>
                      <p class="text-[10px] uppercase text-muted-foreground">sales</p>
                    </div>
                    <div class="text-center px-3">
                      <p class="font-bold text-[color:var(--pine-600)]">{{ '$' + a.revenue }}</p>
                      <p class="text-[10px] uppercase text-muted-foreground">revenue</p>
                    </div>
                    <button (click)="removeAffiliate(a)" class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]">
                      <lucide-icon [img]="icons.Trash2" class="w-4 h-4"></lucide-icon>
                    </button>
                  </div>
                  <div class="flex items-center gap-2 bg-muted rounded-lg px-3 py-2">
                    <lucide-icon [img]="icons.Link2" class="w-4 h-4 text-muted-foreground flex-shrink-0"></lucide-icon>
                    <span class="text-xs text-muted-foreground truncate flex-1 font-mono">{{ affLink(a) }}</span>
                    <button (click)="copy(affLink(a), a.id)" class="btn btn-ghost btn-sm">
                      <lucide-icon [img]="copiedId === a.id ? icons.Check : icons.Copy" class="w-4 h-4"></lucide-icon>
                    </button>
                  </div>
                </div>
              }
            </div>
          }
        }

        <!-- ───────── WEBHOOKS ───────── -->
        @if (tab === 'webhooks') {
          <div class="card p-5 mb-5">
            <h2 class="font-semibold text-foreground mb-3">New webhook</h2>
            <label class="block text-sm font-medium text-foreground mb-1.5">Endpoint URL</label>
            <input [(ngModel)]="hookUrl" placeholder="https://your-server.com/webhook" class="input w-full mb-3" />
            <label class="block text-sm font-medium text-foreground mb-1.5">Secret <span class="text-muted-foreground font-normal">(optional, signs payloads)</span></label>
            <input [(ngModel)]="hookSecret" placeholder="A shared secret" class="input w-full mb-3" />
            <label class="block text-sm font-medium text-foreground mb-2">Trigger on</label>
            <div class="grid grid-cols-2 gap-2 mb-4">
              @for (t of allTriggers; track t.key) {
                <label class="flex items-center gap-2 text-sm text-foreground cursor-pointer p-2 rounded-lg border border-border">
                  <input type="checkbox" [checked]="hookTriggers.includes(t.key)" (change)="toggleTrigger(t.key)" class="w-4 h-4 rounded" />
                  {{ t.label }}
                </label>
              }
            </div>
            <button (click)="addWebhook()" [disabled]="!hookUrl.trim() || hookTriggers.length===0 || savingHook" class="btn btn-primary btn-full">
              {{ savingHook ? 'Creating…' : 'Create webhook' }}
            </button>
          </div>

          @if (webhooks.length === 0) {
            <p class="text-sm text-muted-foreground text-center py-8">No webhooks. Add one to push events to Zapier, Make, or your own server.</p>
          } @else {
            <div class="space-y-2">
              @for (w of webhooks; track w.id) {
                <div class="card p-4">
                  <div class="flex items-start gap-3">
                    <div class="flex-1 min-w-0">
                      <p class="font-mono text-sm text-foreground truncate">{{ w.url }}</p>
                      <div class="flex flex-wrap gap-1 mt-1.5">
                        @for (t of w.triggers; track t) {
                          <span class="text-[10px] font-medium text-primary bg-primary/10 px-1.5 py-0.5 rounded">{{ t }}</span>
                        }
                      </div>
                      <p class="text-xs text-muted-foreground mt-1.5">
                        {{ w.deliveries_count }} deliveries
                        @if (w.last_status) { · last status {{ w.last_status }} }
                      </p>
                    </div>
                    <button (click)="toggleWebhook(w)" class="btn btn-ghost btn-sm text-xs" [title]="w.is_active ? 'Disable' : 'Enable'">
                      <span [class]="w.is_active ? 'text-[color:var(--pine-600)]' : 'text-muted-foreground'">{{ w.is_active ? 'Active' : 'Off' }}</span>
                    </button>
                    <button (click)="removeWebhook(w)" class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]">
                      <lucide-icon [img]="icons.Trash2" class="w-4 h-4"></lucide-icon>
                    </button>
                  </div>
                </div>
              }
            </div>
          }
        }

        <!-- ───────── SEAT MAP ───────── -->
        @if (tab === 'seatmap') {
          @if (loadingSeatMap) {
            <div class="flex justify-center py-12"><span class="spinner"></span></div>
          } @else if (seatMapInfo) {
            <div class="card p-5">
              <h2 class="font-semibold text-foreground mb-2">Seat map exists</h2>
              <p class="text-sm text-muted-foreground">
                {{ seatMapInfo.rows }} rows × {{ seatMapInfo.cols }} columns — {{ seatMapInfo.seats.length || (seatMapInfo.rows * seatMapInfo.cols) }} seats total.
                Attendees pick a seat at checkout; zone prices multiply the base price
                (VIP ×2, Premium ×3 by default).
              </p>
            </div>
          } @else {
            <div class="card p-5">
              <h2 class="font-semibold text-foreground mb-1">Create a seat map</h2>
              <p class="text-sm text-muted-foreground mb-4">
                Without a seat map this event sells general-admission tickets.
                Generate assigned seating below — front rows can be Premium/VIP priced.
              </p>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                <div>
                  <label class="block text-sm font-medium text-foreground mb-1.5">Rows</label>
                  <input type="number" [(ngModel)]="smRows" min="1" max="26" class="input" />
                </div>
                <div>
                  <label class="block text-sm font-medium text-foreground mb-1.5">Seats per row</label>
                  <input type="number" [(ngModel)]="smCols" min="1" max="30" class="input" />
                </div>
                <div>
                  <label class="block text-sm font-medium text-foreground mb-1.5">Premium rows</label>
                  <input type="number" [(ngModel)]="smPremium" min="0" class="input" />
                </div>
                <div>
                  <label class="block text-sm font-medium text-foreground mb-1.5">VIP rows</label>
                  <input type="number" [(ngModel)]="smVip" min="0" class="input" />
                </div>
              </div>
              <label class="flex items-center gap-2 text-sm text-foreground cursor-pointer mb-4">
                <input type="checkbox" [(ngModel)]="smSyncCapacity" class="w-4 h-4 rounded" />
                Set event capacity to {{ smRows * smCols }} (rows × seats)
              </label>
              <button (click)="createSeatMap()" [disabled]="creatingSeatMap || smRows < 1 || smCols < 1" class="btn btn-primary">
                {{ creatingSeatMap ? 'Generating…' : 'Generate ' + (smRows * smCols) + ' seats' }}
              </button>
            </div>
          }
        }

        <!-- ───────── DANGER ───────── -->
        @if (tab === 'danger') {
          <div class="card p-5 border-[color:var(--destructive-50)]">
            <h2 class="font-semibold text-[color:var(--destructive)] mb-1">Cancel this event</h2>
            <p class="text-sm text-muted-foreground mb-4">
              The event is taken off sale, every attendee gets an in-app notification,
              and all paid tickets are automatically refunded. This cannot be undone.
            </p>
            @if (event?.status === 'cancelled') {
              <p class="text-sm font-medium text-[color:var(--destructive)]">This event is already cancelled.</p>
            } @else {
              <button (click)="cancelEvent()" [disabled]="cancellingEvent" class="btn btn-danger">
                {{ cancellingEvent ? 'Cancelling…' : 'Cancel event & refund attendees' }}
              </button>
            }
          </div>
        }

        <!-- ───────── REFUNDS ───────── -->
        @if (tab === 'refunds') {
          @if (refunds.length === 0) {
            <p class="text-sm text-muted-foreground text-center py-12">No refund requests for this event.</p>
          } @else {
            <div class="space-y-3">
              @for (r of refunds; track r.id) {
                <div class="card p-4">
                  <div class="flex items-start justify-between gap-3 mb-2">
                    <div class="min-w-0">
                      <p class="font-semibold text-foreground">{{ r.full_name }}
                        <span class="text-xs font-normal text-muted-foreground">· {{ '$' + r.amount }}@if (r.ticket_type) { · {{ r.ticket_type }} }</span>
                      </p>
                      <p class="text-xs text-muted-foreground">Requested {{ r.created_at | date:'MMM d, HH:mm' }}</p>
                    </div>
                    <span class="text-[11px] font-bold uppercase px-2 py-1 rounded-full {{ refundStatusClass(r.status) }}">{{ r.status }}</span>
                  </div>
                  @if (r.reason) {
                    <p class="text-sm text-foreground/80 bg-muted rounded-lg px-3 py-2 mb-3">"{{ r.reason }}"</p>
                  }
                  @if (r.status === 'pending') {
                    <div class="flex gap-2">
                      <button (click)="resolveRefund(r, false)" [disabled]="resolvingId === r.id" class="btn btn-secondary flex-1 text-sm">Decline</button>
                      <button (click)="resolveRefund(r, true)" [disabled]="resolvingId === r.id" class="btn btn-primary flex-1 text-sm">
                        {{ resolvingId === r.id ? '…' : 'Approve & refund $' + r.amount }}
                      </button>
                    </div>
                  } @else if (r.organizer_note) {
                    <p class="text-xs text-muted-foreground">Note: {{ r.organizer_note }}</p>
                  }
                </div>
              }
            </div>
          }
        }
      </div>
    </div>
  `,
})
export class EventSettingsComponent implements OnInit {
  eventId = 0;
  event: EventModel | null = null;
  tab: 'team' | 'affiliates' | 'webhooks' | 'refunds' | 'seatmap' | 'danger' = 'team';

  // Seat map
  seatMapInfo: any = null;
  loadingSeatMap = false;
  smRows = 6;
  smCols = 8;
  smVip = 2;
  smPremium = 0;
  smSyncCapacity = true;
  creatingSeatMap = false;

  // Danger zone
  cancellingEvent = false;

  // Refunds
  refunds: RefundRequest[] = [];
  resolvingId: number | null = null;
  get pendingRefunds(): number { return this.refunds.filter(r => r.status === 'pending').length; }

  // Team
  staff: EventStaff[] = [];
  staffUsername = '';
  staffRole = 'check_in';
  savingStaff = false;

  // Affiliates
  affiliates: Affiliate[] = [];
  affName = '';
  affCode = '';
  savingAff = false;
  copiedId: number | null = null;

  // Webhooks
  webhooks: Webhook[] = [];
  hookUrl = '';
  hookSecret = '';
  hookTriggers: WebhookTrigger[] = [];
  savingHook = false;
  allTriggers: { key: WebhookTrigger; label: string }[] = [
    { key: 'ticket_sold', label: 'Ticket sold' },
    { key: 'registration_created', label: 'Registration' },
    { key: 'refund_issued', label: 'Refund issued' },
    { key: 'attendee_checked_in', label: 'Checked in' },
  ];

  readonly icons = { Users, Share2, WebhookIcon, Plus, Trash2, Copy, Check, Link2, RotateCcw, Armchair, AlertTriangle };

  constructor(
    private route: ActivatedRoute,
    private eventService: EventService,
    private toast: ToastService,
    private modal: ModalService,
  ) {}

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.eventService.getEvent(this.eventId).subscribe(e => this.event = e);
    this.loadStaff();
    this.loadAffiliates();
    this.loadWebhooks();
    this.loadRefunds();
    this.loadSeatMap();
  }

  // Seat map
  loadSeatMap(): void {
    this.loadingSeatMap = true;
    this.eventService.getSeatMap(this.eventId).subscribe({
      next: sm => { this.seatMapInfo = sm; this.loadingSeatMap = false; },
      error: () => { this.seatMapInfo = null; this.loadingSeatMap = false; },
    });
  }

  createSeatMap(): void {
    this.creatingSeatMap = true;
    this.eventService.createSeatMap(this.eventId, {
      rows: this.smRows,
      cols: this.smCols,
      vip_rows: this.smVip,
      premium_rows: this.smPremium,
      sync_capacity: this.smSyncCapacity,
    }).subscribe({
      next: sm => {
        this.creatingSeatMap = false;
        this.seatMapInfo = sm;
        this.toast.success(`Seat map created — ${this.smRows * this.smCols} seats.`);
      },
      error: err => {
        this.creatingSeatMap = false;
        this.toast.error(err.error?.error || 'Could not create the seat map.');
      },
    });
  }

  // Danger zone
  async cancelEvent(): Promise<void> {
    if (!this.event) return;
    const confirmed = await this.modal.open({
      title: 'Cancel Event',
      message: `Cancel "${this.event.title}"? Every attendee will be notified and paid tickets will be refunded. This cannot be undone.`,
      confirmText: 'Cancel event',
      cancelText: 'Keep event',
      isDestructive: true,
    });
    if (!confirmed) return;
    this.cancellingEvent = true;
    this.eventService.cancelEvent(this.eventId).subscribe({
      next: res => {
        this.cancellingEvent = false;
        if (this.event) this.event.status = 'cancelled';
        this.toast.success(`Event cancelled — ${res.notified ?? 0} attendees notified, ${res.refunded ?? 0} refunds issued.`);
      },
      error: err => {
        this.cancellingEvent = false;
        this.toast.error(err.error?.error || 'Could not cancel the event.');
      },
    });
  }

  loadRefunds() { this.eventService.getRefundRequests(this.eventId).subscribe(r => this.refunds = r); }
  resolveRefund(r: RefundRequest, approve: boolean) {
    this.resolvingId = r.id;
    this.eventService.resolveRefundRequest(r.id, approve).subscribe({
      next: () => {
        this.resolvingId = null;
        this.toast.success(approve ? 'Refund approved & processed.' : 'Refund declined.');
        this.loadRefunds();
      },
      error: err => { this.resolvingId = null; this.toast.error(err.error?.error || 'Could not resolve.'); },
    });
  }
  refundStatusClass(s: string): string {
    return { pending: 'text-warning bg-[color:var(--warning-50)]', approved: 'text-[color:var(--pine-600)] bg-[color:var(--pine-50)]', rejected: 'text-ember bg-[color:var(--destructive-50)]' }[s] ?? 'text-muted-foreground bg-muted';
  }

  // Team
  loadStaff() { this.eventService.getStaff(this.eventId).subscribe(s => this.staff = s); }
  addStaff() {
    this.savingStaff = true;
    this.eventService.addStaff(this.eventId, this.staffUsername.trim(), this.staffRole).subscribe({
      next: () => { this.toast.success('Team member added.'); this.staffUsername = ''; this.savingStaff = false; this.loadStaff(); },
      error: err => { this.savingStaff = false; this.toast.error(err.error?.invite_username?.[0] || err.error?.detail || 'Could not add member.'); },
    });
  }
  removeStaff(s: EventStaff) {
    this.eventService.removeStaff(s.id).subscribe({
      next: () => { this.staff = this.staff.filter(x => x.id !== s.id); this.toast.success('Removed.'); },
      error: () => this.toast.error('Remove failed.'),
    });
  }

  // Affiliates
  loadAffiliates() { this.eventService.getAffiliates(this.eventId).subscribe(a => this.affiliates = a); }
  addAffiliate() {
    this.savingAff = true;
    this.eventService.createAffiliate(this.eventId, { name: this.affName.trim(), code: this.affCode.trim().toUpperCase() }).subscribe({
      next: () => { this.toast.success('Promoter created.'); this.affName = ''; this.affCode = ''; this.savingAff = false; this.loadAffiliates(); },
      error: err => { this.savingAff = false; this.toast.error(err.error?.code?.[0] || 'Could not create (duplicate code?).'); },
    });
  }
  removeAffiliate(a: Affiliate) {
    this.eventService.deleteAffiliate(a.id).subscribe({
      next: () => { this.affiliates = this.affiliates.filter(x => x.id !== a.id); this.toast.success('Deleted.'); },
      error: () => this.toast.error('Delete failed.'),
    });
  }
  affLink(a: Affiliate): string {
    return `${window.location.origin}/events/${this.eventId}?ref=${a.code}`;
  }
  copy(text: string, id: number) {
    navigator.clipboard.writeText(text).then(() => {
      this.copiedId = id;
      setTimeout(() => this.copiedId = null, 2000);
    });
  }

  // Webhooks
  loadWebhooks() { this.eventService.getWebhooks(this.eventId).subscribe(w => this.webhooks = w); }
  toggleTrigger(key: WebhookTrigger) {
    const i = this.hookTriggers.indexOf(key);
    if (i >= 0) this.hookTriggers.splice(i, 1); else this.hookTriggers.push(key);
  }
  addWebhook() {
    this.savingHook = true;
    this.eventService.createWebhook(this.eventId, {
      url: this.hookUrl.trim(), secret: this.hookSecret.trim(), triggers: this.hookTriggers, is_active: true,
    }).subscribe({
      next: () => {
        this.toast.success('Webhook created.');
        this.hookUrl = ''; this.hookSecret = ''; this.hookTriggers = []; this.savingHook = false;
        this.loadWebhooks();
      },
      error: err => { this.savingHook = false; this.toast.error(err.error?.url?.[0] || 'Could not create webhook.'); },
    });
  }
  toggleWebhook(w: Webhook) {
    this.eventService.updateWebhook(w.id, { is_active: !w.is_active }).subscribe({
      next: u => Object.assign(w, u),
      error: () => this.toast.error('Update failed.'),
    });
  }
  removeWebhook(w: Webhook) {
    this.eventService.deleteWebhook(w.id).subscribe({
      next: () => { this.webhooks = this.webhooks.filter(x => x.id !== w.id); this.toast.success('Deleted.'); },
      error: () => this.toast.error('Delete failed.'),
    });
  }
}
