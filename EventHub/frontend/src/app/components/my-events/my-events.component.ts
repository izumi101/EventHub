import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { ModalService } from '../../services/modal.service';
import { ToastService } from '../../services/toast.service';
import { Event } from '../../models/models';
import { LucideAngularModule, Plus, Calendar, MapPin, Edit, Trash2, Users, Eye, Copy } from 'lucide-angular';

@Component({
  selector: 'app-my-events',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">

        <!-- Header -->
        <div class="flex items-center justify-between mb-7">
          <div>
            <h1 class="text-2xl font-bold text-foreground">My Events</h1>
            <p class="text-sm text-muted-foreground mt-1">Events you have created</p>
          </div>
          <a routerLink="/create-event" class="btn btn-primary flex items-center gap-1.5">
            <lucide-icon [img]="icons.Plus" class="w-4 h-4" aria-hidden="true"></lucide-icon>
            Create event
          </a>
        </div>

        <!-- Loading -->
        @if (loading) {
          <div class="flex items-center justify-center py-20 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">Loading your events...</span>
          </div>

        } @else if (events.length === 0) {
          <!-- Empty -->
          <div class="flex flex-col items-center justify-center py-20 text-center">
            <div class="w-14 h-14 rounded-full bg-muted flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.Calendar" class="w-6 h-6 text-muted-foreground" aria-hidden="true"></lucide-icon>
            </div>
            <h3 class="text-base font-semibold text-foreground mb-1">No events yet</h3>
            <p class="text-sm text-muted-foreground mb-5 max-w-xs">
              Create your first event to start managing attendees.
            </p>
            <a routerLink="/create-event" class="btn btn-primary btn-sm flex items-center gap-1.5">
              <lucide-icon [img]="icons.Plus" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
              Create event
            </a>
          </div>

        } @else {
          <div class="card divide-y divide-border">
            @for (event of events; track event.id) {
              <div class="flex items-center gap-4 p-4 hover:bg-muted/40 transition-colors">

                <!-- Thumbnail -->
                <div class="w-16 h-12 rounded-md bg-muted overflow-hidden flex-shrink-0">
                  @if (event.image) {
                    <img [src]="event.image" [alt]="event.title" class="w-full h-full object-cover" />
                  } @else {
                    <div class="w-full h-full flex items-center justify-center bg-secondary">
                      <span class="text-lg font-bold text-muted-foreground/20">{{ event.title.charAt(0) }}</span>
                    </div>
                  }
                </div>

                <!-- Info -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-0.5">
                    <span class="badge {{ statusBadgeClass(event.status) }} text-2xs">{{ event.status }}</span>
                  </div>
                  <p class="text-sm font-semibold text-foreground truncate">{{ event.title }}</p>
                  <div class="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                    <span class="flex items-center gap-1">
                      <lucide-icon [img]="icons.Calendar" class="w-3 h-3" aria-hidden="true"></lucide-icon>
                      {{ event.date | date:'MMM d, y' }}
                    </span>
                    <span class="flex items-center gap-1 truncate">
                      <lucide-icon [img]="icons.MapPin" class="w-3 h-3" aria-hidden="true"></lucide-icon>
                      {{ event.location }}
                    </span>
                  </div>
                </div>

                <!-- Actions -->
                <div class="flex items-center gap-1 flex-shrink-0">
                  <a
                    [routerLink]="['/events', event.id]"
                    class="btn btn-ghost btn-sm p-2"
                    title="Preview event"
                    aria-label="Preview event"
                  >
                    <lucide-icon [img]="icons.Eye" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                  </a>
                  <a
                    [routerLink]="['/organizer/events', event.id, 'attendees']"
                    class="btn btn-ghost btn-sm p-2"
                    title="Manage attendees"
                    aria-label="Manage attendees"
                  >
                    <lucide-icon [img]="icons.Users" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                  </a>
                  <a
                    [routerLink]="['/edit-event', event.id]"
                    class="btn btn-ghost btn-sm p-2"
                    title="Edit event"
                    aria-label="Edit event"
                  >
                    <lucide-icon [img]="icons.Edit" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                  </a>
                  <button
                    (click)="cloneEvent(event.id)"
                    [disabled]="cloningId === event.id"
                    class="btn btn-ghost btn-sm p-2"
                    title="Duplicate event"
                    aria-label="Duplicate event"
                  >
                    @if (cloningId === event.id) {
                      <span class="spinner spinner-sm"></span>
                    } @else {
                      <lucide-icon [img]="icons.Copy" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                    }
                  </button>
                  <button
                    (click)="deleteEvent(event.id, event.title)"
                    class="btn btn-ghost btn-sm p-2 text-muted-foreground hover:text-destructive hover:bg-[color:var(--destructive-50)]"
                    title="Delete event"
                    aria-label="Delete event"
                  >
                    <lucide-icon [img]="icons.Trash2" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                  </button>
                </div>
              </div>
            }
          </div>
        }
      </div>
    </div>
  `,
})
export class MyEventsComponent implements OnInit {
  events: Event[] = [];
  loading = false;
  cloningId: number | null = null;

  readonly icons = { Plus, Calendar, MapPin, Edit, Trash2, Users, Eye, Copy };

  constructor(
    private eventService: EventService,
    private modalService: ModalService,
    private toastService: ToastService,
  ) {}

  ngOnInit(): void {
    this.loadEvents();
  }

  loadEvents(): void {
    this.loading = true;
    this.eventService.getMyEvents().subscribe({
      next: res => { this.events = res.results; this.loading = false; },
      error: () => { this.toastService.error('Failed to load events.'); this.loading = false; },
    });
  }

  cloneEvent(id: number): void {
    this.cloningId = id;
    this.eventService.cloneEvent(id).subscribe({
      next: () => {
        this.cloningId = null;
        this.toastService.success('Event duplicated as a draft.');
        this.loadEvents();
      },
      error: () => { this.cloningId = null; this.toastService.error('Could not duplicate event.'); },
    });
  }

  statusBadgeClass(status: string): string {
    const map: Record<string, string> = {
      published:  'badge-published',
      pending:    'badge-pending',
      rejected:   'badge-rejected',
      cancelled:  'badge-rejected',
      completed:  'badge-completed',
    };
    return map[status] ?? 'badge-pending';
  }

  async deleteEvent(id: number, title: string): Promise<void> {
    const ok = await this.modalService.open({
      title: 'Delete Event',
      message: `Delete "${title}"? This cannot be undone and all registrations will be cancelled.`,
      confirmText: 'Delete Event',
      cancelText: 'Keep Event',
      isDestructive: true,
    });
    if (!ok) return;
    this.eventService.deleteEvent(id).subscribe({
      next: () => {
        this.events = this.events.filter(e => e.id !== id);
        this.toastService.success('Event deleted.');
      },
      error: () => this.toastService.error('Failed to delete event.'),
    });
  }
}
