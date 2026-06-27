import { Injectable, signal } from '@angular/core';
import { EventService } from './event.service';
import { AuthService } from './auth.service';

@Injectable({ providedIn: 'root' })
export class NotificationService {
  notifications = signal<any[]>([]);
  unreadCount = signal<number>(0);

  private interval?: ReturnType<typeof setInterval>;

  constructor(private eventService: EventService, private auth: AuthService) {
    // React to login/logout so the badge appears right after signing in
    // (not only when the app happens to boot with a stored session).
    this.auth.currentUser$.subscribe(user => {
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
      next: list => {
        this.notifications.set(list);
        this.unreadCount.set(list.filter((n: any) => !n.is_read).length);
      },
      error: () => {},
    });
  }

  markRead(id?: number): void {
    this.eventService.markNotificationRead(id).subscribe({
      next: () => this.load(),
      error: () => {},
    });
  }
}
