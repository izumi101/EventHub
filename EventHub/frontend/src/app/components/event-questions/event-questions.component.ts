import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService, EventQuestion, QuestionType } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, MessageSquare, Plus, Trash2, GripVertical } from 'lucide-angular';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-event-questions',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideAngularModule, TranslocoPipe],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">
        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">{{
            'nav.dashboard' | transloco
          }}</a>
          <span>/</span>
          @if (eventId) {
            <a
              [routerLink]="['/organizer/events', eventId, 'attendees']"
              class="hover:text-foreground transition-colors truncate max-w-[180px]"
              >{{ event?.title || ('nav.event' | transloco) }}</a
            >
          }
          <span>/</span>
          <span class="text-foreground font-medium">{{ 'nav.questions' | transloco }}</span>
        </nav>

        <div class="flex items-center justify-between mb-2">
          <h1 class="text-2xl font-bold text-foreground flex items-center gap-2">
            <lucide-icon [img]="icons.MessageSquare" class="w-6 h-6 text-primary" />
            {{ 'questions.checkoutQuestions' | transloco }}
          </h1>
          <button
            (click)="showForm = !showForm"
            class="btn btn-primary btn-sm flex items-center gap-1.5"
          >
            <lucide-icon [img]="icons.Plus" class="w-4 h-4" />
            {{ 'questions.addQuestion' | transloco }}
          </button>
        </div>
        <p class="text-sm text-muted-foreground mb-6">
          {{ 'questions.askAttendeesForExtra' | transloco: { title: event?.title } }}
        </p>

        @if (showForm) {
          <div class="card p-5 mb-6 animate-slide-up">
            <h2 class="font-semibold text-foreground mb-4">
              {{ 'questions.newQuestion' | transloco }}
            </h2>
            <div class="space-y-4">
              <div>
                <label
                  for="event-questions-label"
                  class="block text-sm font-medium text-foreground mb-1.5"
                  >{{ 'questions.question' | transloco }}</label
                >
                <input
                  id="event-questions-label"
                  [(ngModel)]="form.label"
                  [placeholder]="'questions.eGWhatS' | transloco"
                  class="input w-full"
                />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label
                    for="event-questions-question-type"
                    class="block text-sm font-medium text-foreground mb-1.5"
                    >{{ 'promo.type' | transloco }}</label
                  >
                  <select
                    id="event-questions-question-type"
                    [(ngModel)]="form.question_type"
                    class="input w-full"
                  >
                    <option value="text">{{ 'questions.shortText' | transloco }}</option>
                    <option value="textarea">{{ 'questions.longText' | transloco }}</option>
                    <option value="dropdown">{{ 'questions.dropdown' | transloco }}</option>
                    <option value="checkbox">{{ 'questions.checkboxYesNo' | transloco }}</option>
                    <option value="date">{{ 'common.date' | transloco }}</option>
                    <option value="phone">{{ 'common.phone' | transloco }}</option>
                  </select>
                </div>
                <div class="flex items-end">
                  <label
                    class="flex items-center gap-2 text-sm text-foreground cursor-pointer pb-2"
                  >
                    <input type="checkbox" [(ngModel)]="form.is_required" class="w-4 h-4 rounded" />
                    {{ 'common.required' | transloco }}
                  </label>
                </div>
              </div>
              @if (form.question_type === 'dropdown') {
                <div>
                  <label
                    for="event-questions-options-text"
                    class="block text-sm font-medium text-foreground mb-1.5"
                    >{{ 'questions.optionsOnePerLine' | transloco }}</label
                  >
                  <textarea
                    id="event-questions-options-text"
                    [(ngModel)]="optionsText"
                    rows="3"
                    [placeholder]="'questions.smallMediumLarge' | transloco"
                    class="input resize-none w-full"
                  ></textarea>
                </div>
              }
            </div>
            <div class="flex gap-2 mt-4">
              <button (click)="showForm = false" class="btn btn-secondary flex-1">
                {{ 'common.cancel' | transloco }}
              </button>
              <button
                (click)="create()"
                [disabled]="!form.label.trim() || saving"
                class="btn btn-primary flex-1"
              >
                {{ (saving ? 'questions.adding' : 'questions.addQuestion') | transloco }}
              </button>
            </div>
          </div>
        }

        @if (loading) {
          <div class="flex justify-center py-16"><span class="spinner spinner-lg"></span></div>
        } @else if (questions.length === 0) {
          <div class="flex flex-col items-center justify-center py-16 text-center">
            <div class="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.MessageSquare" class="w-7 h-7 text-muted-foreground/50" />
            </div>
            <h3 class="font-semibold text-foreground mb-1">
              {{ 'questions.noQuestionsYet' | transloco }}
            </h3>
            <p class="text-sm text-muted-foreground">
              {{ 'questions.addQuestionsToCollect' | transloco }}
            </p>
          </div>
        } @else {
          <div class="space-y-2">
            @for (q of questions; track q.id) {
              <div class="card p-4 flex items-center gap-3">
                <lucide-icon
                  [img]="icons.GripVertical"
                  class="w-4 h-4 text-muted-foreground/40 flex-shrink-0"
                />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-foreground">{{ q.label }}</span>
                    @if (q.is_required) {
                      <span
                        class="text-[10px] font-bold uppercase text-ember bg-[color:var(--destructive-50)] px-1.5 py-0.5 rounded"
                        >{{ 'common.required' | transloco }}</span
                      >
                    }
                  </div>
                  <p class="text-xs text-muted-foreground mt-0.5 capitalize">
                    {{ q.question_type }}
                    @if (q.question_type === 'dropdown' && q.options.length) {
                      · {{ q.options.join(', ') }}
                    }
                  </p>
                </div>
                <button
                  (click)="remove(q)"
                  class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]"
                >
                  <lucide-icon [img]="icons.Trash2" class="w-4 h-4" />
                </button>
              </div>
            }
          </div>
        }
      </div>
    </div>
  `,
})
export class EventQuestionsComponent implements OnInit {
  private i18n = inject(LanguageService);
  private route = inject(ActivatedRoute);
  private eventService = inject(EventService);
  private toast = inject(ToastService);

  eventId = 0;
  event: EventModel | null = null;
  questions: EventQuestion[] = [];
  loading = true;
  showForm = false;
  saving = false;

  form: { label: string; question_type: QuestionType; is_required: boolean } = {
    label: '',
    question_type: 'text',
    is_required: false,
  };
  optionsText = '';

  readonly icons = { MessageSquare, Plus, Trash2, GripVertical };

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.eventService.getEvent(this.eventId).subscribe((e) => (this.event = e));
    this.load();
  }

  load(): void {
    this.loading = true;
    this.eventService.getEventQuestions(this.eventId).subscribe({
      next: (q) => {
        this.questions = q;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.toast.error(this.i18n.t('questions.failedToLoadQuestions'));
      },
    });
  }

  create(): void {
    if (!this.form.label.trim()) return;
    this.saving = true;
    const payload: Partial<EventQuestion> = {
      label: this.form.label.trim(),
      question_type: this.form.question_type,
      is_required: this.form.is_required,
      order: this.questions.length,
    };
    if (this.form.question_type === 'dropdown') {
      payload.options = this.optionsText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
    }
    this.eventService.createQuestion(this.eventId, payload).subscribe({
      next: () => {
        this.toast.success(this.i18n.t('questions.questionAdded'));
        this.saving = false;
        this.showForm = false;
        this.form = { label: '', question_type: 'text', is_required: false };
        this.optionsText = '';
        this.load();
      },
      error: (err) => {
        this.saving = false;
        this.toast.error(
          apiErrorMessage(err, this.i18n.t('questions.couldNotAddQuestion'), 'options'),
        );
      },
    });
  }

  remove(q: EventQuestion): void {
    this.eventService.deleteQuestion(q.id).subscribe({
      next: () => {
        this.questions = this.questions.filter((x) => x.id !== q.id);
        this.toast.success(this.i18n.t('eventSettings.deleted'));
      },
      error: () => this.toast.error(this.i18n.t('eventSettings.deleteFailed')),
    });
  }
}
