import { Component, ElementRef, HostListener, ViewChild, inject, signal } from '@angular/core';
import { LucideAngularModule, Bell } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';
import { NotificationService } from '../services/notification.service';
import { LocalDatePipe } from '../i18n/locale.pipes';

let nextId = 0;

/**
 * Bell + dropdown, shared by the consumer top nav and the workspace topbar.
 * The button's name starts with "Notifications" (e2e relies on it).
 */
@Component({
  selector: 'app-notification-bell',
  standalone: true,
  imports: [LucideAngularModule, TranslocoPipe, LocalDatePipe],
  template: `
    <div class="relative">
      <button
        #trigger
        type="button"
        (click)="toggle($event)"
        class="nav-icon-btn focus-ring relative"
        [attr.aria-expanded]="open()"
        [attr.aria-controls]="panelId"
        [attr.aria-label]="
          notif.unreadCount() > 0
            ? ('nav.notificationsUnread' | transloco: { count: notif.unreadCount() })
            : ('nav.notifications' | transloco)
        "
      >
        <lucide-icon [img]="icons.Bell" class="w-[18px] h-[18px]" aria-hidden="true" />
        @if (notif.unreadCount() > 0) {
          <span class="nav-badge" aria-hidden="true">
            {{ notif.unreadCount() > 9 ? '9+' : notif.unreadCount() }}
          </span>
        }
      </button>

      @if (open()) {
        <!-- Clicks inside the panel must not reach the document listener that closes it. -->
        <div
          [id]="panelId"
          class="topbar-notif-dropdown"
          role="presentation"
          (click)="$event.stopPropagation()"
        >
          <div class="flex items-center justify-between px-4 py-3 border-b border-border">
            <span class="font-semibold text-foreground text-sm">{{
              'nav.notifications' | transloco
            }}</span>
            @if (notif.unreadCount() > 0) {
              <button
                type="button"
                (click)="notif.markRead(); close(true)"
                class="text-xs text-primary hover:underline focus-ring rounded"
              >
                {{ 'nav.markAllRead' | transloco }}
              </button>
            }
          </div>
          <div class="max-h-80 overflow-y-auto divide-y divide-border">
            @if (notif.notifications().length === 0) {
              <div class="px-4 py-8 text-center text-sm text-muted-foreground">
                {{ 'nav.noNotifications' | transloco }}
              </div>
            }
            @for (n of notif.notifications(); track n.id) {
              <button
                type="button"
                class="block w-full text-left px-4 py-3 text-sm cursor-pointer transition-colors focus-ring"
                [class]="n.is_read ? 'hover:bg-muted' : 'bg-[color:var(--ember-50)] hover:bg-muted'"
                (click)="notif.markRead(n.id); close(true)"
              >
                @if (n.title.trim()) {
                  <span class="block font-medium text-foreground leading-tight">{{ n.title }}</span>
                }
                @if (n.body.trim()) {
                  <span class="block text-muted-foreground mt-0.5 text-xs leading-relaxed">
                    {{ n.body }}
                  </span>
                }
                <span class="block text-muted-foreground text-[11px] mt-1">
                  {{ n.created_at | localDate: 'MMM d, HH:mm' }}
                </span>
              </button>
            }
          </div>
        </div>
      }
    </div>
  `,
})
export class NotificationBellComponent {
  readonly notif = inject(NotificationService);
  readonly open = signal(false);
  readonly panelId = `notif-panel-${++nextId}`;
  readonly icons = { Bell };

  @ViewChild('trigger') private trigger?: ElementRef<HTMLButtonElement>;

  @HostListener('document:click')
  onDocumentClick(): void {
    this.open.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.open()) this.close(true);
  }

  toggle(event: MouseEvent): void {
    event.stopPropagation();
    this.open.set(!this.open());
    if (this.open()) this.notif.load();
  }

  close(returnFocus: boolean): void {
    this.open.set(false);
    if (returnFocus) this.trigger?.nativeElement.focus();
  }
}
