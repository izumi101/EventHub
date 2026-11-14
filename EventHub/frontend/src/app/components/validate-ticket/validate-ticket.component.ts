import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService } from '../../services/event.service';
import { CheckInResponse } from '../../models/models';
import {
  LucideAngularModule,
  CircleCheckBig,
  TriangleAlert,
  CircleX,
  RefreshCw,
} from 'lucide-angular';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-validate-ticket',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule, TranslocoPipe, LocalDatePipe],
  template: `
    <div class="min-h-screen bg-muted flex items-center justify-center px-4 py-12 pt-20">
      <div class="card w-full max-w-sm p-8 shadow-md text-center animate-scale-in">
        @if (loading) {
          <div class="flex flex-col items-center gap-4 py-8">
            <span class="spinner spinner-lg"></span>
            <p class="text-sm text-muted-foreground">
              {{ 'scan.verifyingTicket' | transloco }}
            </p>
          </div>
        } @else if (status === 'success') {
          <div class="flex flex-col items-center gap-3 mb-6">
            <div
              class="w-16 h-16 rounded-full bg-[color:var(--pine-50)] flex items-center justify-center"
            >
              <lucide-icon
                [img]="icons.CircleCheckBig"
                class="w-8 h-8 text-[color:var(--pine-600)]"
                aria-hidden="true"
              />
            </div>
            <h1 class="text-xl font-bold text-foreground">
              {{ 'scan.accessGranted' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground">{{ 'validate.ticketIsValid' | transloco }}</p>
          </div>

          @if (result) {
            <div
              class="rounded-lg border border-border bg-muted/40 divide-y divide-border text-sm mb-6 text-left"
            >
              <div class="px-4 py-3 flex justify-between gap-3">
                <span class="text-muted-foreground flex-shrink-0">{{
                  'attendees.attendee' | transloco
                }}</span>
                <span class="font-medium text-foreground text-right">{{ result.attendee }}</span>
              </div>
              @if (result.event) {
                <div class="px-4 py-3 flex justify-between gap-3">
                  <span class="text-muted-foreground flex-shrink-0">{{
                    'nav.event' | transloco
                  }}</span>
                  <span class="font-medium text-foreground text-right">{{ result.event }}</span>
                </div>
              }
            </div>
          }

          <button (click)="recheck()" class="btn btn-primary btn-full">
            <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" aria-hidden="true" />
            {{ 'validate.nextTicket' | transloco }}
          </button>
        } @else if (status === 'used') {
          <div class="flex flex-col items-center gap-3 mb-6">
            <div
              class="w-16 h-16 rounded-full bg-[color:var(--warning-50)] flex items-center justify-center"
            >
              <lucide-icon
                [img]="icons.TriangleAlert"
                class="w-8 h-8 text-warning"
                aria-hidden="true"
              />
            </div>
            <h1 class="text-xl font-bold text-foreground">
              {{ 'scan.alreadyScanned' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground">
              {{ 'scan.thisTicketHasBeen' | transloco }}
            </p>
          </div>

          @if (result) {
            <div
              class="rounded-lg border border-transparent bg-[color:var(--warning-50)] divide-y divide-border text-sm mb-6 text-left"
            >
              <div class="px-4 py-3 flex justify-between gap-3">
                <span class="text-warning flex-shrink-0">{{
                  'attendees.attendee' | transloco
                }}</span>
                <span class="font-medium text-warning text-right">{{ result.attendee }}</span>
              </div>
              @if (result.checked_in_at) {
                <div class="px-4 py-3 flex justify-between gap-3">
                  <span class="text-warning flex-shrink-0">{{ 'scan.firstScan' | transloco }}</span>
                  <span class="font-medium text-warning">{{
                    result.checked_in_at | localDate: 'HH:mm, MMM d'
                  }}</span>
                </div>
              }
            </div>
          }

          <button (click)="recheck()" class="btn btn-secondary btn-full">
            <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" aria-hidden="true" />
            {{ 'validate.nextTicket' | transloco }}
          </button>
        } @else {
          <!-- Error -->
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
              {{ 'validate.validationFailed' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground max-w-xs">
              {{ errorMessage || ('scan.invalidTicketOrInsufficient' | transloco) }}
            </p>
          </div>

          <div class="flex flex-col gap-2">
            <button (click)="recheck()" class="btn btn-primary btn-full">
              <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" aria-hidden="true" />
              {{ 'common.retry' | transloco }}
            </button>
            <a routerLink="/" class="btn btn-ghost btn-full text-muted-foreground">
              {{ 'notFound.backToHome' | transloco }}
            </a>
          </div>
        }
      </div>
    </div>
  `,
})
export class ValidateTicketComponent implements OnInit {
  private i18n = inject(LanguageService);
  private route = inject(ActivatedRoute);
  private eventService = inject(EventService);

  loading = true;
  status: 'success' | 'used' | 'error' = 'error';
  result: CheckInResponse | null = null;
  errorMessage = '';
  uuid: string | null = null;

  readonly icons = { CircleCheckBig, TriangleAlert, CircleX, RefreshCw };

  ngOnInit(): void {
    this.uuid = this.route.snapshot.paramMap.get('uuid');
    this.recheck();
  }

  recheck(): void {
    if (!this.uuid) {
      this.status = 'error';
      this.loading = false;
      return;
    }
    this.loading = true;
    this.eventService.checkIn(this.uuid).subscribe({
      next: (res) => {
        this.status = res.status === 'used' ? 'used' : 'success';
        this.result = res;
        this.loading = false;
      },
      error: (err) => {
        this.status = 'error';
        this.errorMessage = apiErrorMessage(
          err,
          this.i18n.t('validate.validationFailed2'),
          'error',
        );
        this.loading = false;
      },
    });
  }
}
