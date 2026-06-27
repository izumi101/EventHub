import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, Users, Clock, CheckCircle, XCircle, Ticket } from 'lucide-angular';

interface WaitlistEntry {
  id: number;
  username: string;
  status: 'waiting' | 'offered' | 'converted' | 'expired';
  position: number;
  offer_expires_at: string | null;
  created_at: string;
}

@Component({
  selector: 'app-event-waitlist',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-4xl py-8">

        <!-- Breadcrumb -->
        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6" aria-label="Breadcrumb">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">Dashboard</a>
          <span>/</span>
          <span class="text-foreground font-medium truncate max-w-xs">{{ event?.title || 'Event' }}</span>
          <span>/</span>
          <span class="text-muted-foreground">Waitlist</span>
        </nav>

        <!-- Header -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground">Waitlist</h1>
            @if (event) {
              <p class="text-sm text-muted-foreground mt-1">
                {{ event.title }} · {{ event.date | date:'MMM d, y' }}
              </p>
            }
          </div>

          <!-- Summary chips -->
          @if (!loading && entries.length > 0) {
            <div class="flex items-center gap-2 flex-wrap text-sm">
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900">
                <lucide-icon [img]="icons.Clock" class="w-3.5 h-3.5"></lucide-icon>
                {{ countByStatus('waiting') }} waiting
              </span>
              @if (countByStatus('offered') > 0) {
                <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900">
                  <lucide-icon [img]="icons.Ticket" class="w-3.5 h-3.5"></lucide-icon>
                  {{ countByStatus('offered') }} offered
                </span>
              }
              @if (countByStatus('converted') > 0) {
                <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-900">
                  <lucide-icon [img]="icons.CheckCircle" class="w-3.5 h-3.5"></lucide-icon>
                  {{ countByStatus('converted') }} converted
                </span>
              }
            </div>
          }
        </div>

        @if (loading) {
          <div class="flex items-center justify-center py-16 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">Loading waitlist…</span>
          </div>

        } @else if (entries.length === 0) {
          <div class="card p-12 flex flex-col items-center justify-center text-center">
            <lucide-icon [img]="icons.Users" class="w-10 h-10 text-muted-foreground/40 mb-3"></lucide-icon>
            <p class="text-base font-medium text-foreground mb-1">No one on the waitlist</p>
            <p class="text-sm text-muted-foreground">
              People join automatically when the event sells out.
            </p>
          </div>

        } @else {
          <div class="card overflow-hidden">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border bg-muted/40">
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide w-12">#</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">User</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Status</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Joined</th>
                  <th class="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Offer expires</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border">
                @for (entry of entries; track entry.id) {
                  <tr class="hover:bg-muted/30 transition-colors" [class.opacity-50]="entry.status === 'expired'">
                    <td class="px-4 py-3 text-muted-foreground font-mono text-xs">
                      {{ entry.status === 'waiting' ? entry.position : '—' }}
                    </td>
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-2">
                        <div class="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary flex-shrink-0">
                          {{ entry.username.charAt(0).toUpperCase() }}
                        </div>
                        <span class="font-medium text-foreground">{{ entry.username }}</span>
                      </div>
                    </td>
                    <td class="px-4 py-3">
                      <span class="badge" [class]="statusBadgeClass(entry.status)">
                        {{ statusLabel(entry.status) }}
                      </span>
                    </td>
                    <td class="px-4 py-3 text-xs text-muted-foreground">
                      {{ entry.created_at | date:'MMM d, y · HH:mm' }}
                    </td>
                    <td class="px-4 py-3 text-xs text-muted-foreground">
                      @if (entry.offer_expires_at) {
                        <span [class.text-rose-500]="isExpiringSoon(entry.offer_expires_at)">
                          {{ entry.offer_expires_at | date:'MMM d · HH:mm' }}
                        </span>
                      } @else {
                        —
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }

      </div>
    </div>
  `,
})
export class EventWaitlistComponent implements OnInit {
  eventId: number | null = null;
  event: EventModel | null = null;
  entries: WaitlistEntry[] = [];
  loading = true;

  readonly icons = { Users, Clock, CheckCircle, XCircle, Ticket };

  constructor(
    private route: ActivatedRoute,
    private eventService: EventService,
  ) {}

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.eventId = +id;
      this.eventService.getEvent(this.eventId).subscribe(e => { this.event = e; });
      this.eventService.getEventWaitlist(this.eventId).subscribe({
        next: entries => { this.entries = entries; this.loading = false; },
        error: () => { this.loading = false; },
      });
    }
  }

  countByStatus(status: string): number {
    return this.entries.filter(e => e.status === status).length;
  }

  statusBadgeClass(status: string): string {
    const map: Record<string, string> = {
      waiting: 'badge-pending',
      offered: 'badge badge-info',
      converted: 'badge-confirmed',
      expired: 'badge-cancelled',
    };
    return map[status] ?? 'badge-pending';
  }

  statusLabel(status: string): string {
    const map: Record<string, string> = {
      waiting: 'Waiting',
      offered: 'Offered',
      converted: 'Converted',
      expired: 'Expired',
    };
    return map[status] ?? status;
  }

  isExpiringSoon(expiresAt: string): boolean {
    return new Date(expiresAt).getTime() - Date.now() < 2 * 60 * 60 * 1000;
  }
}
