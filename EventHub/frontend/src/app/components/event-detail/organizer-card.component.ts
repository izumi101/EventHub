import { Component, Input } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { Event } from '../../models/models';

/** Who runs the event. Organizers have no brand name or profile page yet. */
@Component({
  selector: 'app-organizer-card',
  standalone: true,
  imports: [TranslocoPipe],
  template: `
    <div class="organizer-card">
      <span class="organizer-avatar" aria-hidden="true">{{ initial }}</span>
      <div class="min-w-0">
        <p class="text-xs text-muted-foreground">{{ 'footer.organizer' | transloco }}</p>
        <p class="text-[0.9375rem] font-semibold text-foreground truncate">{{ name }}</p>
      </div>
    </div>
  `,
})
export class OrganizerCardComponent {
  @Input({ required: true }) organizer!: Event['organizer'];

  get name(): string {
    const o = this.organizer;
    const full = `${o.first_name} ${o.last_name}`.trim();
    return full || o.username;
  }

  get initial(): string {
    return (this.name.charAt(0) || 'O').toUpperCase();
  }
}
