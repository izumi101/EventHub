import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { CheckInResponse } from '../../models/models';
import { LucideAngularModule, CheckCircle, AlertTriangle, XCircle, RefreshCw } from 'lucide-angular';

@Component({
  selector: 'app-validate-ticket',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="min-h-screen bg-muted flex items-center justify-center px-4 py-12 pt-20">
      <div class="card w-full max-w-sm p-8 shadow-md text-center animate-scale-in">

        @if (loading) {
          <div class="flex flex-col items-center gap-4 py-8">
            <span class="spinner spinner-lg"></span>
            <p class="text-sm text-muted-foreground">Verifying ticket...</p>
          </div>

        } @else if (status === 'success') {
          <div class="flex flex-col items-center gap-3 mb-6">
            <div class="w-16 h-16 rounded-full bg-[color:var(--pine-50)] flex items-center justify-center">
              <lucide-icon [img]="icons.CheckCircle" class="w-8 h-8 text-[color:var(--pine-600)]" aria-hidden="true"></lucide-icon>
            </div>
            <h1 class="text-xl font-bold text-foreground">Access granted</h1>
            <p class="text-sm text-muted-foreground">Ticket is valid</p>
          </div>

          @if (result) {
            <div class="rounded-lg border border-border bg-muted/40 divide-y divide-border text-sm mb-6 text-left">
              <div class="px-4 py-3 flex justify-between gap-3">
                <span class="text-muted-foreground flex-shrink-0">Attendee</span>
                <span class="font-medium text-foreground text-right">{{ result.attendee }}</span>
              </div>
              @if (result.event) {
                <div class="px-4 py-3 flex justify-between gap-3">
                  <span class="text-muted-foreground flex-shrink-0">Event</span>
                  <span class="font-medium text-foreground text-right">{{ result.event }}</span>
                </div>
              }
            </div>
          }

          <button (click)="recheck()" class="btn btn-primary btn-full">
            <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" aria-hidden="true"></lucide-icon>
            Next ticket
          </button>

        } @else if (status === 'used') {
          <div class="flex flex-col items-center gap-3 mb-6">
            <div class="w-16 h-16 rounded-full bg-[color:var(--warning-50)] flex items-center justify-center">
              <lucide-icon [img]="icons.AlertTriangle" class="w-8 h-8 text-warning" aria-hidden="true"></lucide-icon>
            </div>
            <h1 class="text-xl font-bold text-foreground">Already scanned</h1>
            <p class="text-sm text-muted-foreground">This ticket has been used</p>
          </div>

          @if (result) {
            <div class="rounded-lg border border-transparent bg-[color:var(--warning-50)] divide-y divide-border text-sm mb-6 text-left">
              <div class="px-4 py-3 flex justify-between gap-3">
                <span class="text-warning flex-shrink-0">Attendee</span>
                <span class="font-medium text-warning text-right">{{ result.attendee }}</span>
              </div>
              @if (result.checked_in_at) {
                <div class="px-4 py-3 flex justify-between gap-3">
                  <span class="text-warning flex-shrink-0">First scan</span>
                  <span class="font-medium text-warning">{{ result.checked_in_at | date:'HH:mm, MMM d' }}</span>
                </div>
              }
            </div>
          }

          <button (click)="recheck()" class="btn btn-secondary btn-full">
            <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" aria-hidden="true"></lucide-icon>
            Next ticket
          </button>

        } @else {
          <!-- Error -->
          <div class="flex flex-col items-center gap-3 mb-6">
            <div class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center">
              <lucide-icon [img]="icons.XCircle" class="w-8 h-8 text-[color:var(--destructive)]" aria-hidden="true"></lucide-icon>
            </div>
            <h1 class="text-xl font-bold text-foreground">Validation failed</h1>
            <p class="text-sm text-muted-foreground max-w-xs">
              {{ errorMessage || 'Invalid ticket or insufficient permissions.' }}
            </p>
          </div>

          <div class="flex flex-col gap-2">
            <button (click)="recheck()" class="btn btn-primary btn-full">
              <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" aria-hidden="true"></lucide-icon>
              Retry
            </button>
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
              Back to home
            </a>
          </div>
        }
      </div>
    </div>
  `,
})
export class ValidateTicketComponent implements OnInit {
  loading = true;
  status: 'success' | 'used' | 'error' = 'error';
  result: CheckInResponse | null = null;
  errorMessage = '';
  uuid: string | null = null;

  readonly icons = { CheckCircle, AlertTriangle, XCircle, RefreshCw };

  constructor(private route: ActivatedRoute, private eventService: EventService) {}

  ngOnInit(): void {
    this.uuid = this.route.snapshot.paramMap.get('uuid');
    this.recheck();
  }

  recheck(): void {
    if (!this.uuid) { this.status = 'error'; this.loading = false; return; }
    this.loading = true;
    this.eventService.checkIn(this.uuid).subscribe({
      next: res => {
        this.status = res.status === 'used' ? 'used' : 'success';
        this.result = res;
        this.loading = false;
      },
      error: err => {
        this.status = 'error';
        this.errorMessage = err.error?.error || 'Validation failed.';
        this.loading = false;
      },
    });
  }
}
