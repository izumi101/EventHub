import { Injectable, signal, inject } from '@angular/core';
import { EventService, type UserNotification } from './event.service';
import { AuthService } from './auth.service';

@Injectable({ providedIn: 'root' })
export class NotificationService {
  private eventService = inject(EventService);
  private auth = inject(AuthService);

  notifications = signal<UserNotification[]>([]);
  unreadCount = signal<number>(0);

  private interval?: ReturnType<typeof setInterval>;

  constructor() {
    // React to login/logout so the badge appears right after signing in
    // (not only when the app happens to boot with a stored session).
    this.auth.currentUser$.subscribe((user) => {
      if (user) this.startPolling();
      else this.stopPolling();
    });
  }

  private startPolling(): void {
    if (this.interval) return; // already polling
    this.load();
    this.interval = setInterval(() => this.load(), 30_000); // every 30s
  }

  private stopPolling(): void {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = undefined;
    }
    this.notifications.set([]);
    this.unreadCount.set(0);
  }

  load(): void {
    this.eventService.getNotifications().subscribe({
      next: (list) => {
        this.notifications.set(list);
        this.unreadCount.set(list.filter((n) => !n.is_read).length);
      },
      error: () => {
        // Background poll: keep the last known list; the next tick retries.
      },
    });
  }

  markRead(id?: number): void {
    this.eventService.markNotificationRead(id).subscribe({
      next: () => this.load(),
      error: () => {
        // The badge stays as it was; the next poll reconciles it.
      },
    });
  }
}
