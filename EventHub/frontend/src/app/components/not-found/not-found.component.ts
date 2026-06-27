import { Component } from '@angular/core';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, Home, ArrowLeft } from 'lucide-angular';

@Component({
  selector: 'app-not-found',
  standalone: true,
  imports: [RouterModule, LucideAngularModule],
  template: `
    <div class="min-h-dvh bg-background flex items-center justify-center px-4 py-12">
      <div class="text-center animate-fade-in max-w-md">
        <p class="font-display font-semibold leading-none mb-2 select-none" style="font-size:clamp(5rem,18vw,9rem);color:var(--ember-500)">404</p>
        <p class="kicker mb-3">Lost the trail</p>
        <h1 class="font-display text-2xl font-semibold text-foreground mb-2">This page has left the venue.</h1>
        <p class="text-sm text-muted-foreground mb-8 max-w-xs mx-auto">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div class="flex flex-wrap items-center justify-center gap-3">
          <a routerLink="/" class="btn btn-primary flex items-center gap-1.5">
            <lucide-icon [img]="icons.Home" class="w-4 h-4" aria-hidden="true"></lucide-icon>
            Back to home
          </a>
          <button (click)="goBack()" class="btn btn-secondary flex items-center gap-1.5">
            <lucide-icon [img]="icons.ArrowLeft" class="w-4 h-4" aria-hidden="true"></lucide-icon>
            Go back
          </button>
        </div>
      </div>
    </div>
  `,
})
export class NotFoundComponent {
  readonly icons = { Home, ArrowLeft };
  goBack(): void { window.history.back(); }
}
