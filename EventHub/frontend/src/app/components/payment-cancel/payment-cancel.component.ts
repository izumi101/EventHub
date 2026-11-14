import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, CircleX } from 'lucide-angular';
import { TranslocoPipe } from '@jsverse/transloco';

@Component({
  selector: 'app-payment-cancel',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule, TranslocoPipe],
  template: `
    <div class="min-h-screen bg-muted flex items-center justify-center px-4 py-12 pt-20">
      <div class="card w-full max-w-sm p-8 shadow-md text-center animate-scale-in">
        <div class="flex flex-col items-center gap-3 mb-6">
          <div
            class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center"
          >
            <lucide-icon
              [img]="icons.CircleX"
              class="w-8 h-8 text-[color:var(--destructive)]"
              aria-hidden="true"
            />
          </div>
          <h1 class="text-xl font-bold text-foreground">
            {{ 'paymentCancel.paymentCancelled' | transloco }}
          </h1>
          <p class="text-sm text-muted-foreground max-w-xs">
            {{ 'paymentCancel.noChargesWereMade' | transloco }}
          </p>
        </div>

        <div class="flex flex-col gap-2">
          <a routerLink="/my-registrations" class="btn btn-primary btn-full">
            {{ 'paymentCancel.viewMyRegistrations' | transloco }}
          </a>
          <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
            {{ 'eventDetail.backToEvents' | transloco }}
          </a>
        </div>
      </div>
    </div>
  `,
})
export class PaymentCancelComponent {
  readonly icons = { CircleX };
}
