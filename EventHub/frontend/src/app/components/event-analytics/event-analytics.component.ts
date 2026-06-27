import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService, EventAnalytics } from '../../services/event.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, TrendingUp, Ticket, UserCheck, Wallet, BarChart3 } from 'lucide-angular';

@Component({
  selector: 'app-event-analytics',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-4xl py-8">

        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">Dashboard</a>
          <span>/</span>
          @if (eventId) {
            <a [routerLink]="['/organizer/events', eventId, 'attendees']" class="hover:text-foreground transition-colors truncate max-w-[180px]">{{ event?.title || 'Event' }}</a>
          }
          <span>/</span>
          <span class="text-foreground font-medium">Analytics</span>
        </nav>

        <p class="kicker mb-2">Sales analytics</p>
        <h1 class="font-display text-2xl font-semibold text-foreground mb-6">{{ event?.title }}</h1>

        @if (loading) {
          <div class="flex justify-center py-20"><span class="spinner spinner-lg"></span></div>
        } @else if (data) {

          <!-- KPI cards -->
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
            <div class="card p-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                <lucide-icon [img]="icons.Wallet" class="w-4 h-4"></lucide-icon>
                <span class="text-xs font-medium uppercase tracking-wide">Net revenue</span>
              </div>
              <p class="num text-2xl font-bold text-foreground">{{ '$' + (data.kpis.net_revenue | number:'1.2-2') }}</p>
              @if (data.kpis.refunded > 0) {
                <p class="text-xs text-muted-foreground mt-0.5">−{{ '$' + (data.kpis.refunded | number:'1.2-2') }} refunded</p>
              }
            </div>
            <div class="card p-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                <lucide-icon [img]="icons.Ticket" class="w-4 h-4"></lucide-icon>
                <span class="text-xs font-medium uppercase tracking-wide">Tickets sold</span>
              </div>
              <p class="num text-2xl font-bold text-foreground">{{ data.kpis.tickets_sold }}</p>
              <p class="text-xs text-muted-foreground mt-0.5">{{ data.kpis.sold_through_pct }}% of {{ data.kpis.capacity }} capacity</p>
            </div>
            <div class="card p-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                <lucide-icon [img]="icons.UserCheck" class="w-4 h-4"></lucide-icon>
                <span class="text-xs font-medium uppercase tracking-wide">Checked in</span>
              </div>
              <p class="num text-2xl font-bold text-foreground">{{ data.kpis.checked_in }}</p>
              <p class="text-xs text-muted-foreground mt-0.5">{{ data.kpis.checkin_rate_pct }}% of sold</p>
            </div>
            <div class="card p-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1.5">
                <lucide-icon [img]="icons.TrendingUp" class="w-4 h-4"></lucide-icon>
                <span class="text-xs font-medium uppercase tracking-wide">Avg order</span>
              </div>
              <p class="num text-2xl font-bold text-foreground">{{ '$' + (data.kpis.avg_order_value | number:'1.2-2') }}</p>
              <p class="text-xs text-muted-foreground mt-0.5">{{ data.kpis.paid_orders }} paid · {{ data.kpis.pending }} pending</p>
            </div>
          </div>

          <!-- 30-day timeline -->
          <div class="card p-5 mb-8">
            <h2 class="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
              <lucide-icon [img]="icons.BarChart3" class="w-4 h-4 text-muted-foreground"></lucide-icon>
              Registrations — last 30 days
            </h2>
            @if (maxTickets === 0) {
              <p class="text-sm text-muted-foreground py-6 text-center">No registrations in the last 30 days.</p>
            } @else {
              <div class="flex items-end gap-[3px] h-32">
                @for (day of data.timeline; track day.date) {
                  <div class="flex-1 flex flex-col justify-end group relative">
                    <div
                      class="rounded-t bg-ember/80 group-hover:bg-ember transition-colors min-h-[2px]"
                      [style.height.%]="day.tickets / maxTickets * 100"
                    ></div>
                    <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block bg-foreground text-background text-[10px] font-medium rounded px-1.5 py-0.5 whitespace-nowrap z-10">
                      {{ day.date | date:'MMM d' }}: {{ day.tickets }} · {{ '$' + day.revenue }}
                    </div>
                  </div>
                }
              </div>
              <div class="flex justify-between text-[10px] text-muted-foreground mt-1.5">
                <span>{{ data.timeline[0].date | date:'MMM d' }}</span>
                <span>{{ data.timeline[data.timeline.length - 1].date | date:'MMM d' }}</span>
              </div>
            }
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <!-- By ticket type -->
            <div class="card p-5">
              <h2 class="text-sm font-semibold text-foreground mb-3">Sales by ticket type</h2>
              @if (data.by_ticket_type.length === 0) {
                <p class="text-sm text-muted-foreground py-4 text-center">No sales yet.</p>
              } @else {
                <div class="space-y-2">
                  @for (t of data.by_ticket_type; track t.name) {
                    <div class="flex items-center justify-between text-sm py-1.5 border-b border-border/60 last:border-0">
                      <span class="text-foreground font-medium">{{ t.name }}</span>
                      <span class="text-muted-foreground">{{ t.count }} · <span class="num font-semibold text-foreground">{{ '$' + (t.revenue | number:'1.2-2') }}</span></span>
                    </div>
                  }
                </div>
              }
            </div>

            <!-- By promoter -->
            <div class="card p-5">
              <h2 class="text-sm font-semibold text-foreground mb-3">Sales by promoter</h2>
              @if (data.by_affiliate.length === 0) {
                <p class="text-sm text-muted-foreground py-4 text-center">No affiliate-attributed sales.</p>
              } @else {
                <div class="space-y-2">
                  @for (a of data.by_affiliate; track a.name) {
                    <div class="flex items-center justify-between text-sm py-1.5 border-b border-border/60 last:border-0">
                      <span class="text-foreground font-medium">{{ a.name }}</span>
                      <span class="text-muted-foreground">{{ a.count }} · <span class="num font-semibold text-foreground">{{ '$' + (a.revenue | number:'1.2-2') }}</span></span>
                    </div>
                  }
                </div>
              }
            </div>
          </div>

        } @else {
          <p class="text-sm text-muted-foreground text-center py-16">Could not load analytics for this event.</p>
        }
      </div>
    </div>
  `,
})
export class EventAnalyticsComponent implements OnInit {
  eventId = 0;
  event: EventModel | null = null;
  data: EventAnalytics | null = null;
  loading = false;

  readonly icons = { TrendingUp, Ticket, UserCheck, Wallet, BarChart3 };

  constructor(private route: ActivatedRoute, private eventService: EventService) {}

  get maxTickets(): number {
    if (!this.data) return 0;
    return Math.max(...this.data.timeline.map(d => d.tickets), 0);
  }

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.loading = true;
    this.eventService.getEvent(this.eventId).subscribe({
      next: ev => { this.event = ev; },
      error: () => {},
    });
    this.eventService.getEventAnalytics(this.eventId).subscribe({
      next: d => { this.data = d; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }
}
