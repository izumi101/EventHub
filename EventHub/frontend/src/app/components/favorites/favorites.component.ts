import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { LucideAngularModule, Heart, Calendar, MapPin, Ticket } from 'lucide-angular';

@Component({
  selector: 'app-favorites',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-4xl py-8">
        <div class="flex items-center gap-3 mb-7">
          <div class="w-9 h-9 rounded-full bg-[color:var(--destructive-50)] dark:bg-rose-900/30 flex items-center justify-center">
            <lucide-icon [img]="icons.Heart" class="w-5 h-5 text-ember" aria-hidden="true"></lucide-icon>
          </div>
          <div>
            <h1 class="text-2xl font-bold text-foreground">Favorites</h1>
            <p class="text-sm text-muted-foreground mt-0.5">Events you saved</p>
          </div>
        </div>

        @if (loading) {
          <div class="flex justify-center py-20">
            <span class="spinner"></span>
          </div>
        } @else if (favorites.length === 0) {
          <div class="flex flex-col items-center justify-center py-24 text-center">
            <div class="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.Heart" class="w-7 h-7 text-muted-foreground" aria-hidden="true"></lucide-icon>
            </div>
            <h3 class="text-base font-semibold text-foreground mb-1">No favorites yet</h3>
            <p class="text-sm text-muted-foreground mb-5 max-w-xs">Tap ❤ on any event to save it here for quick access.</p>
            <a routerLink="/" class="btn btn-primary btn-sm">Discover events</a>
          </div>
        } @else {
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            @for (fav of favorites; track fav.id) {
              <div class="card overflow-hidden group hover:shadow-md transition-shadow">
                <!-- Image -->
                <div class="relative h-40 bg-muted overflow-hidden cursor-pointer" [routerLink]="['/events', fav.event.id]">
                  @if (fav.event.image) {
                    <img [src]="fav.event.image" [alt]="fav.event.title" class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" />
                  } @else {
                    <div class="w-full h-full bg-gradient-to-br from-primary/10 to-secondary flex items-center justify-center">
                      <lucide-icon [img]="icons.Ticket" class="w-10 h-10 text-primary/20" aria-hidden="true"></lucide-icon>
                    </div>
                  }
                  <!-- Unfavorite button -->
                  <button
                    (click)="$event.stopPropagation(); unfavorite(fav)"
                    class="absolute top-2 right-2 w-8 h-8 rounded-full bg-white/90 backdrop-blur-sm flex items-center justify-center shadow-sm hover:bg-[color:var(--destructive-50)] transition-colors"
                  >
                    <lucide-icon [img]="icons.Heart" class="w-4 h-4 text-ember" aria-hidden="true"></lucide-icon>
                  </button>
                </div>

                <div class="p-4">
                  <h3
                    class="font-semibold text-foreground leading-tight mb-2 cursor-pointer hover:text-primary transition-colors"
                    [routerLink]="['/events', fav.event.id]"
                  >{{ fav.event.title }}</h3>

                  <div class="space-y-1 text-xs text-muted-foreground">
                    <div class="flex items-center gap-1.5">
                      <lucide-icon [img]="icons.Calendar" class="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
                      <span>{{ fav.event.date | date:'EEE, MMM d, y' }}</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                      <lucide-icon [img]="icons.MapPin" class="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true"></lucide-icon>
                      <span class="truncate">{{ fav.event.location }}</span>
                    </div>
                  </div>

                  <div class="flex items-center justify-between mt-3 pt-3 border-t border-border">
                    <span class="text-sm font-semibold text-foreground">
                      {{ fav.event.is_free ? 'Free' : '$' + fav.event.price }}
                    </span>
                    <a [routerLink]="['/events', fav.event.id]" class="btn btn-sm btn-primary">
                      Get tickets
                    </a>
                  </div>
                </div>
              </div>
            }
          </div>
        }
      </div>
    </div>
  `,
})
export class FavoritesComponent implements OnInit {
  favorites: any[] = [];
  loading = false;
  readonly icons = { Heart, Calendar, MapPin, Ticket };

  constructor(private eventService: EventService, private toast: ToastService) {}

  ngOnInit(): void {
    this.loading = true;
    this.eventService.getFavorites().subscribe({
      next: list => { this.favorites = list; this.loading = false; },
      error: () => { this.loading = false; },
    });
  }

  unfavorite(fav: any): void {
    this.eventService.toggleFavorite(fav.event.id).subscribe({
      next: () => {
        this.favorites = this.favorites.filter(f => f.id !== fav.id);
        this.toast.success('Removed from favorites');
      },
      error: () => this.toast.error('Failed to remove'),
    });
  }
}
