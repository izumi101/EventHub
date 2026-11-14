import { Component } from '@angular/core';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, House, ArrowLeft } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';

@Component({
  selector: 'app-not-found',
  standalone: true,
  imports: [RouterModule, LucideAngularModule, TranslocoPipe],
  template: `
    <div class="min-h-dvh bg-background flex items-center justify-center px-4 py-12">
      <div class="text-center animate-fade-in max-w-md">
        <p
          class="font-display font-semibold leading-none mb-2 select-none"
          style="font-size:clamp(5rem,18vw,9rem);color:var(--ember-500)"
        >
          404
        </p>
        <p class="kicker mb-3">{{ 'notFound.lostTheTrail' | transloco }}</p>
        <h1 class="font-display text-2xl font-semibold text-foreground mb-2">
          {{ 'notFound.thisPageHasLeft' | transloco }}
        </h1>
        <p class="text-sm text-muted-foreground mb-8 max-w-xs mx-auto">
          {{ 'notFound.thePageYouRe' | transloco }}
        </p>
        <div class="flex flex-wrap items-center justify-center gap-3">
          <a routerLink="/" class="btn btn-primary flex items-center gap-1.5">
            <lucide-icon [img]="icons.House" class="w-4 h-4" aria-hidden="true" />
            {{ 'notFound.backToHome' | transloco }}
          </a>
          <button (click)="goBack()" class="btn btn-secondary flex items-center gap-1.5">
            <lucide-icon [img]="icons.ArrowLeft" class="w-4 h-4" aria-hidden="true" />
            {{ 'notFound.goBack' | transloco }}
          </button>
        </div>
      </div>
    </div>
  `,
})
export class NotFoundComponent {
  readonly icons = { House, ArrowLeft };
  goBack(): void {
    window.history.back();
  }
}
