import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { EventService, EventQuestion, QuestionType } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { Event as EventModel } from '../../models/models';
import { LucideAngularModule, MessageSquare, Plus, Trash2, GripVertical } from 'lucide-angular';

@Component({
  selector: 'app-event-questions',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-3xl py-8">

        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">Dashboard</a>
          <span>/</span>
          @if (eventId) {
            <a [routerLink]="['/organizer/events', eventId, 'attendees']" class="hover:text-foreground transition-colors truncate max-w-[180px]">{{ event?.title || 'Event' }}</a>
          }
          <span>/</span>
          <span class="text-foreground font-medium">Questions</span>
        </nav>

        <div class="flex items-center justify-between mb-2">
          <h1 class="text-2xl font-bold text-foreground flex items-center gap-2">
            <lucide-icon [img]="icons.MessageSquare" class="w-6 h-6 text-primary"></lucide-icon>
            Checkout questions
          </h1>
          <button (click)="showForm = !showForm" class="btn btn-primary btn-sm flex items-center gap-1.5">
            <lucide-icon [img]="icons.Plus" class="w-4 h-4"></lucide-icon> Add question
          </button>
        </div>
        <p class="text-sm text-muted-foreground mb-6">Ask attendees for extra info when they register for {{ event?.title }}.</p>

        @if (showForm) {
          <div class="card p-5 mb-6 animate-slide-up">
            <h2 class="font-semibold text-foreground mb-4">New question</h2>
            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">Question</label>
                <input [(ngModel)]="form.label" placeholder="e.g. What's your t-shirt size?" class="input w-full" />
              </div>
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-foreground mb-1.5">Type</label>
                  <select [(ngModel)]="form.question_type" class="input w-full">
                    <option value="text">Short text</option>
                    <option value="textarea">Long text</option>
                    <option value="dropdown">Dropdown</option>
                    <option value="checkbox">Checkbox (yes/no)</option>
                    <option value="date">Date</option>
                    <option value="phone">Phone</option>
                  </select>
                </div>
                <div class="flex items-end">
                  <label class="flex items-center gap-2 text-sm text-foreground cursor-pointer pb-2">
                    <input type="checkbox" [(ngModel)]="form.is_required" class="w-4 h-4 rounded" />
                    Required
                  </label>
                </div>
              </div>
              @if (form.question_type === 'dropdown') {
                <div>
                  <label class="block text-sm font-medium text-foreground mb-1.5">Options (one per line)</label>
                  <textarea [(ngModel)]="optionsText" rows="3" placeholder="Small&#10;Medium&#10;Large" class="input resize-none w-full"></textarea>
                </div>
              }
            </div>
            <div class="flex gap-2 mt-4">
              <button (click)="showForm = false" class="btn btn-secondary flex-1">Cancel</button>
              <button (click)="create()" [disabled]="!form.label.trim() || saving" class="btn btn-primary flex-1">
                {{ saving ? 'Adding…' : 'Add question' }}
              </button>
            </div>
          </div>
        }

        @if (loading) {
          <div class="flex justify-center py-16"><span class="spinner spinner-lg"></span></div>
        } @else if (questions.length === 0) {
          <div class="flex flex-col items-center justify-center py-16 text-center">
            <div class="w-14 h-14 rounded-2xl bg-muted flex items-center justify-center mb-4">
              <lucide-icon [img]="icons.MessageSquare" class="w-7 h-7 text-muted-foreground/50"></lucide-icon>
            </div>
            <h3 class="font-semibold text-foreground mb-1">No questions yet</h3>
            <p class="text-sm text-muted-foreground">Add questions to collect info at checkout.</p>
          </div>
        } @else {
          <div class="space-y-2">
            @for (q of questions; track q.id) {
              <div class="card p-4 flex items-center gap-3">
                <lucide-icon [img]="icons.GripVertical" class="w-4 h-4 text-muted-foreground/40 flex-shrink-0"></lucide-icon>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-foreground">{{ q.label }}</span>
                    @if (q.is_required) { <span class="text-[10px] font-bold uppercase text-ember bg-[color:var(--destructive-50)] px-1.5 py-0.5 rounded">Required</span> }
                  </div>
                  <p class="text-xs text-muted-foreground mt-0.5 capitalize">
                    {{ q.question_type }}
                    @if (q.question_type === 'dropdown' && q.options.length) { · {{ q.options.join(', ') }} }
                  </p>
                </div>
                <button (click)="remove(q)" class="btn btn-ghost btn-sm text-ember hover:text-[color:var(--destructive)]">
                  <lucide-icon [img]="icons.Trash2" class="w-4 h-4"></lucide-icon>
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
  eventId = 0;
  event: EventModel | null = null;
  questions: EventQuestion[] = [];
  loading = true;
  showForm = false;
  saving = false;

  form: { label: string; question_type: QuestionType; is_required: boolean } = {
    label: '', question_type: 'text', is_required: false,
  };
  optionsText = '';

  readonly icons = { MessageSquare, Plus, Trash2, GripVertical };

  constructor(
    private route: ActivatedRoute,
    private eventService: EventService,
    private toast: ToastService,
  ) {}

  ngOnInit(): void {
    this.eventId = Number(this.route.snapshot.paramMap.get('id'));
    this.eventService.getEvent(this.eventId).subscribe(e => this.event = e);
    this.load();
  }

  load(): void {
    this.loading = true;
    this.eventService.getEventQuestions(this.eventId).subscribe({
      next: q => { this.questions = q; this.loading = false; },
      error: () => { this.loading = false; this.toast.error('Failed to load questions.'); },
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
      payload.options = this.optionsText.split('\n').map(s => s.trim()).filter(Boolean);
    }
    this.eventService.createQuestion(this.eventId, payload).subscribe({
      next: () => {
        this.toast.success('Question added.');
        this.saving = false;
        this.showForm = false;
        this.form = { label: '', question_type: 'text', is_required: false };
        this.optionsText = '';
        this.load();
      },
      error: err => {
        this.saving = false;
        this.toast.error(err.error?.options?.[0] || 'Could not add question.');
      },
    });
  }

  remove(q: EventQuestion): void {
    this.eventService.deleteQuestion(q.id).subscribe({
      next: () => { this.questions = this.questions.filter(x => x.id !== q.id); this.toast.success('Deleted.'); },
      error: () => this.toast.error('Delete failed.'),
    });
  }
}
