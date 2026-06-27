import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { Event } from '../../models/models';
import { LucideAngularModule, MapPin, Users, ArrowRight } from 'lucide-angular';

@Component({
  selector: 'app-event-card',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <article
      class="card-ticket card-hover flex flex-col cursor-pointer focus-ring h-full"
      [routerLink]="['/events', event.id]"
      [attr.aria-label]="'View details for ' + event.title"
      tabindex="0"
      (keydown.enter)="$event.preventDefault()"
    >
      <!-- Media -->
      <div class="relative bg-muted overflow-hidden"
           [class.aspect-video]="!featured"
           style="border-radius: 14px 14px 0 0"
           [style.aspect-ratio]="featured ? '21/9' : null">
        @if (event.image && !imageError) {
          <img
            [src]="event.image"
            [alt]="event.title"
            loading="lazy"
            (error)="imageError = true"
            class="w-full h-full object-cover transition-transform duration-500"
          />
        } @else {
          <div class="w-full h-full flex items-center justify-center" style="background:linear-gradient(135deg,#F4D9CC,#E8B8A2 55%,#CBB6A6)">
            <span class="font-display text-5xl font-semibold text-white/70 select-none">
              {{ event.title?.charAt(0)?.toUpperCase() || 'E' }}
            </span>
          </div>
        }

        <!-- Badges -->
        <div class="absolute top-2.5 left-2.5 flex gap-1.5">
          @if (event.is_free) { <span class="badge badge-free">Free</span> }
          @if (event.is_online) { <span class="badge badge-online">Online</span> }
          @if (!event.is_free && event.available_spots > 0 && event.available_spots < 10) {
            <span class="badge badge-hot">Selling fast</span>
          }
          @if (event.available_spots === 0) { <span class="badge badge-soldout">Sold out</span> }
        </div>
      </div>

      <!-- Perforation -->
      <div class="ticket-perf"></div>

      <!-- Body -->
      <div class="flex gap-3.5 p-4 flex-1">
        <!-- Date block -->
        <div class="date-block">
          <div class="d num">{{ event.date | date:'d' }}</div>
          <div class="m">{{ event.date | date:'MMM' }}</div>
        </div>

        <!-- Content -->
        <div class="flex flex-col flex-1 min-w-0">
          <p class="kicker mb-1.5 truncate" [class.kicker-hot]="featured">
            @if (featured) { Featured · }{{ event.category?.name || 'Event' }}
          </p>
          <h3 class="font-display font-medium text-foreground leading-snug line-clamp-2"
              [class]="featured ? 'text-2xl font-semibold' : 'text-[1.0625rem]'">
            {{ event.title }}
          </h3>

          @if (featured && event.description) {
            <p class="text-sm text-muted-foreground mt-2 line-clamp-2 max-w-xl">{{ event.description }}</p>
          }

          <div class="flex items-center gap-x-4 gap-y-1.5 mt-2.5 text-xs text-muted-foreground flex-wrap">
            <div class="flex items-center gap-1.5">
              <lucide-icon [img]="icons.MapPin" class="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
              <span class="truncate">{{ event.location }}</span>
            </div>
            @if (event.max_participants > 0) {
              <div class="flex items-center gap-1.5">
                <lucide-icon [img]="icons.Users" class="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
                <span>{{ event.available_spots }} spots left</span>
              </div>
            }
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-between pt-3.5 mt-auto"
               [class.border-t]="featured" [class.border-border]="featured">
            <span class="font-display text-base font-semibold num" [class.text-pine-600]="event.is_free">
              {{ event.is_free ? 'Free' : '$' + event.price }}
            </span>
            <span class="text-xs font-semibold text-ember inline-flex items-center gap-1 cta">
              {{ featured ? 'Get tickets' : 'View event' }}
              <lucide-icon [img]="icons.ArrowRight" class="w-3.5 h-3.5 cta-arrow transition-transform" aria-hidden="true"></lucide-icon>
            </span>
          </div>
        </div>
      </div>
    </article>
  `,
  styles: [`
    /* Fill the wrapper so cards in a rail/grid row share one height
       (the article inside is h-full with an mt-auto footer). */
    :host { display: block; height: 100%; }
    .line-clamp-2 {
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .text-pine-600 { color: var(--pine-600); }
    article:hover img { transform: scale(1.04); }
    article:hover .cta-arrow { transform: translateX(3px); }
  `],
})
export class EventCardComponent {
  @Input() event!: Event;
  @Input() featured = false;
  imageError = false;

  readonly icons = { MapPin, Users, ArrowRight };
}
