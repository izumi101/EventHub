import { Injectable, signal, inject } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { EventService } from '../services/event.service';

export interface EventContext {
  id: string;
  title: string;
}

@Injectable({ providedIn: 'root' })
export class LayoutService {
  private router = inject(Router);
  private eventService = inject(EventService);

  collapsed = signal(false);
  mobileOpen = signal(false);
  /** Sidebar groups the visitor toggled; untouched groups are absent. */
  groupOpen = signal<Partial<Record<string, boolean>>>({});
  eventContext = signal<EventContext | null>(null);

  private cachedEventId: string | null = null;

  constructor() {
    const saved = localStorage.getItem('sidebar_collapsed');
    if (saved !== null) this.collapsed.set(saved === 'true');

    try {
      const savedGroups = localStorage.getItem('sidebar_groups');
      if (savedGroups)
        this.groupOpen.set(JSON.parse(savedGroups) as Partial<Record<string, boolean>>);
    } catch {
      /* ignore */
    }

    this.router.events
      .pipe(filter((e) => e instanceof NavigationEnd))
      .subscribe((e) => this.onNavigation(e.urlAfterRedirects));

    this.onNavigation(this.router.url);
  }

  private onNavigation(url: string): void {
    const match = /\/organizer\/events\/([^/?#]+)/.exec(url) ?? /\/edit-event\/([^/?#]+)/.exec(url);

    if (match) {
      const id = match[1];
      if (id !== this.cachedEventId) {
        this.cachedEventId = id;
        this.eventService.getEvent(+id).subscribe({
          next: (event) => this.eventContext.set({ id, title: event.title }),
          error: () => this.eventContext.set({ id, title: 'Event' }),
        });
      }
    } else {
      if (this.cachedEventId !== null) {
        this.cachedEventId = null;
        this.eventContext.set(null);
      }
    }

    this.mobileOpen.set(false);
  }

  toggleCollapsed(): void {
    const next = !this.collapsed();
    this.collapsed.set(next);
    localStorage.setItem('sidebar_collapsed', String(next));
  }

  toggleMobile(): void {
    this.mobileOpen.set(!this.mobileOpen());
  }

  closeMobile(): void {
    this.mobileOpen.set(false);
  }

  toggleGroup(id: string): void {
    const groups = { ...this.groupOpen() };
    groups[id] = !groups[id];
    this.groupOpen.set(groups);
    localStorage.setItem('sidebar_groups', JSON.stringify(groups));
  }

  isGroupOpen(id: string, defaultVal = true): boolean {
    return this.groupOpen()[id] ?? defaultVal;
  }
}
