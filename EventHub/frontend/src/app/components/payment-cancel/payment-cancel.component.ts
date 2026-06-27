import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, XCircle } from 'lucide-angular';

@Component({
  selector: 'app-payment-cancel',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="min-h-screen bg-muted flex items-center justify-center px-4 py-12 pt-20">
      <div class="card w-full max-w-sm p-8 shadow-md text-center animate-scale-in">

        <div class="flex flex-col items-center gap-3 mb-6">
          <div class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center">
            <lucide-icon [img]="icons.XCircle" class="w-8 h-8 text-[color:var(--destructive)]" aria-hidden="true"></lucide-icon>
          </div>
          <h1 class="text-xl font-bold text-foreground">Payment cancelled</h1>
          <p class="text-sm text-muted-foreground max-w-xs">
            No charges were made. Your registration is on hold — you can retry or browse other events.
          </p>
        </div>

        <div class="flex flex-col gap-2">
          <a routerLink="/my-registrations" class="btn btn-primary btn-full">
            View my registrations
          </a>
          <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
            Back to events
          </a>
        </div>
      </div>
    </div>
  `,
})
export class PaymentCancelComponent {
  readonly icons = { XCircle };
}
