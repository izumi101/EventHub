import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { Category } from '../../models/models';

@Component({
  selector: 'app-event-form',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  template: `
    <div class="page-root">
      <div class="container max-w-2xl py-8">

        <!-- Header -->
        <div class="mb-7">
          <h1 class="text-2xl font-bold text-foreground">
            {{ editMode ? 'Edit event' : 'Create event' }}
          </h1>
          <p class="text-sm text-muted-foreground mt-1">
            {{ editMode ? 'Update your event details' : 'Fill in the details below — your event will be reviewed before publishing' }}
          </p>
        </div>

        <form (ngSubmit)="onSubmit()" novalidate>
          <div class="card divide-y divide-border">

            <!-- Core details -->
            <div class="p-5 space-y-4">
              <h2 class="text-sm font-semibold text-foreground">Event details</h2>

              <div>
                <label for="title" class="block text-sm font-medium text-foreground mb-1.5">
                  Title <span class="text-destructive">*</span>
                </label>
                <input
                  id="title"
                  type="text"
                  [(ngModel)]="formData.title"
                  name="title"
                  placeholder="e.g. Jazz Night at Almaty Arena"
                  class="input"
                  required
                />
              </div>

              <div>
                <label for="description" class="block text-sm font-medium text-foreground mb-1.5">
                  Description <span class="text-destructive">*</span>
                </label>
                <textarea
                  id="description"
                  [(ngModel)]="formData.description"
                  name="description"
                  placeholder="Describe what attendees can expect..."
                  rows="4"
                  class="input resize-none"
                  required
                ></textarea>
              </div>

              <!-- Cover image -->
              <div>
                <label class="block text-sm font-medium text-foreground mb-1.5">
                  Cover image <span class="text-muted-foreground font-normal">(optional, up to 5 MB)</span>
                </label>
                @if (imagePreview) {
                  <div class="relative rounded-lg overflow-hidden border border-border mb-2" style="aspect-ratio:16/7">
                    <img [src]="imagePreview" alt="Event cover preview" class="w-full h-full object-cover" />
                    <button type="button" (click)="clearImage()"
                      class="absolute top-2 right-2 btn btn-sm bg-black/60 text-white border-transparent hover:bg-black/80">
                      Remove
                    </button>
                  </div>
                }
                <input type="file" accept="image/*" (change)="onImageSelected($event)"
                  class="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-foreground file:cursor-pointer hover:file:bg-muted/70" />
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label for="category" class="block text-sm font-medium text-foreground mb-1.5">
                    Category <span class="text-destructive">*</span>
                  </label>
                  <select
                    id="category"
                    [(ngModel)]="formData.category"
                    name="category"
                    class="input"
                    required
                  >
                    <option value="" disabled>Select a category</option>
                    @for (cat of categories; track cat.id) {
                      <option [value]="cat.id">{{ cat.name }}</option>
                    }
                  </select>
                </div>

                <div>
                  <label for="max_participants" class="block text-sm font-medium text-foreground mb-1.5">
                    Max participants <span class="text-destructive">*</span>
                  </label>
                  <input
                    id="max_participants"
                    type="number"
                    [(ngModel)]="formData.max_participants"
                    name="max_participants"
                    class="input"
                    min="1"
                    required
                  />
                </div>
              </div>
            </div>

            <!-- Date & price -->
            <div class="p-5 space-y-4">
              <h2 class="text-sm font-semibold text-foreground">Schedule & pricing</h2>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label for="date" class="block text-sm font-medium text-foreground mb-1.5">
                    Start date & time <span class="text-destructive">*</span>
                  </label>
                  <input
                    id="date"
                    type="datetime-local"
                    [(ngModel)]="formData.date"
                    name="date"
                    class="input"
                    required
                  />
                </div>

                <div>
                  <label for="end_date" class="block text-sm font-medium text-foreground mb-1.5">
                    End date & time <span class="text-muted-foreground font-normal">(optional)</span>
                  </label>
                  <input
                    id="end_date"
                    type="datetime-local"
                    [(ngModel)]="formData.end_date"
                    name="end_date"
                    class="input"
                  />
                </div>

                <div>
                  <label for="price" class="block text-sm font-medium text-foreground mb-1.5">
                    Price — 0 for free
                  </label>
                  <input
                    id="price"
                    type="number"
                    [(ngModel)]="formData.price"
                    name="price"
                    class="input"
                    step="0.01"
                    min="0"
                  />
                </div>

                <div>
                  <label for="currency" class="block text-sm font-medium text-foreground mb-1.5">Currency</label>
                  <select id="currency" [(ngModel)]="formData.currency" name="currency" class="input">
                    <option value="USD">USD — US Dollar</option>
                    <option value="EUR">EUR — Euro</option>
                    <option value="GBP">GBP — British Pound</option>
                    <option value="KZT">KZT — Kazakhstani Tenge</option>
                    <option value="RUB">RUB — Russian Ruble</option>
                  </select>
                </div>
              </div>

              <!-- Ticket tiers hint -->
              <div class="flex items-start gap-2.5 p-3 rounded-lg bg-primary/5 border border-primary/20 text-sm">
                <p class="text-foreground/80">
                  This sets a single price. Want <strong>multiple tiers</strong> (VIP, Early Bird, Student, Donation)?
                  @if (editMode && eventId) {
                    <a [routerLink]="['/organizer/events', eventId, 'ticket-types']" class="text-primary font-medium hover:underline">Add ticket types →</a>
                  } @else {
                    <span class="text-muted-foreground">Create the event first, then open <strong>Tickets</strong> on the event to add tiers.</span>
                  }
                </p>
              </div>

              <!-- Tax & fees -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                <div>
                  <label for="tax" class="block text-sm font-medium text-foreground mb-1.5">Tax / VAT (%)</label>
                  <input id="tax" type="number" [(ngModel)]="formData.tax_percent" name="tax_percent" class="input" step="0.01" min="0" max="100" placeholder="0" />
                </div>
                <div>
                  <label for="fee" class="block text-sm font-medium text-foreground mb-1.5">Service fee (%)</label>
                  <input id="fee" type="number" [(ngModel)]="formData.service_fee_percent" name="service_fee_percent" class="input" step="0.01" min="0" max="100" placeholder="0" />
                </div>
              </div>
              <label class="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input type="checkbox" [(ngModel)]="formData.fees_passed_to_buyer" name="fees_passed_to_buyer" class="w-4 h-4 rounded" />
                Pass tax &amp; fees on to the buyer
                <span class="text-xs text-muted-foreground">(unchecked = you absorb them)</span>
              </label>

              <label class="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input type="checkbox" [(ngModel)]="formData.refundable" name="refundable" class="w-4 h-4 rounded" />
                Allow refund requests
                <span class="text-xs text-muted-foreground">(unchecked = tickets are non-refundable)</span>
              </label>
            </div>

            <!-- Venue -->
            <div class="p-5 space-y-4">
              <h2 class="text-sm font-semibold text-foreground">Venue</h2>

              <div>
                <label for="location" class="block text-sm font-medium text-foreground mb-1.5">
                  Venue name <span class="text-destructive">*</span>
                </label>
                <input
                  id="location"
                  type="text"
                  [(ngModel)]="formData.location"
                  name="location"
                  placeholder="e.g. Congress Hall, Almaty"
                  class="input"
                  required
                />
              </div>

              <div>
                <label for="address" class="block text-sm font-medium text-foreground mb-1.5">
                  Address <span class="text-muted-foreground font-normal">(optional)</span>
                </label>
                <input
                  id="address"
                  type="text"
                  [(ngModel)]="formData.address"
                  name="address"
                  placeholder="Street address"
                  class="input"
                />
              </div>

              <!-- Online toggle -->
              <div class="flex items-center justify-between p-3 rounded-lg border border-border bg-muted/30">
                <div>
                  <p class="text-sm font-medium text-foreground">Online event</p>
                  <p class="text-xs text-muted-foreground">Provide a meeting link for remote attendees</p>
                </div>
                <input
                  type="checkbox"
                  [(ngModel)]="formData.is_online"
                  name="is_online"
                  class="toggle"
                  [id]="'is-online'"
                  [attr.aria-label]="'Online event'"
                />
              </div>

              @if (formData.is_online) {
                <div class="animate-fade-in">
                  <label for="online_link" class="block text-sm font-medium text-foreground mb-1.5">
                    Meeting link <span class="text-destructive">*</span>
                  </label>
                  <input
                    id="online_link"
                    type="url"
                    [(ngModel)]="formData.online_link"
                    name="online_link"
                    placeholder="https://zoom.us/j/..."
                    class="input"
                  />
                </div>
              }
            </div>

            <!-- SEO (optional) -->
            <div class="p-5 space-y-4">
              <h2 class="text-sm font-semibold text-foreground">Search & social preview <span class="text-muted-foreground font-normal">(optional)</span></h2>
              <div>
                <label for="seo_title" class="block text-sm font-medium text-foreground mb-1.5">SEO title</label>
                <input id="seo_title" type="text" [(ngModel)]="formData.seo_title" name="seo_title"
                  maxlength="200" placeholder="Defaults to the event title" class="input" />
              </div>
              <div>
                <label for="seo_description" class="block text-sm font-medium text-foreground mb-1.5">SEO description</label>
                <textarea id="seo_description" [(ngModel)]="formData.seo_description" name="seo_description"
                  maxlength="500" rows="2" placeholder="Shown in search results and link previews" class="input resize-none"></textarea>
              </div>
            </div>

            <!-- Feedback + actions -->
            <div class="p-5">
              @if (error) {
                <div role="alert" class="p-3 rounded-lg bg-[color:var(--destructive-50)] border border-transparent text-sm text-[color:var(--destructive)] mb-4">
                  {{ error }}
                </div>
              }
              @if (success) {
                <div role="status" class="p-3 rounded-lg bg-[color:var(--pine-50)] border border-transparent text-sm text-[color:var(--pine-600)] mb-4">
                  {{ success }}
                </div>
              }

              <div class="flex items-center gap-3">
                <button
                  type="submit"
                  [disabled]="submitting"
                  class="btn btn-primary"
                >
                  @if (submitting) {
                    <span class="spinner spinner-sm"></span>
                    Saving...
                  } @else {
                    {{ editMode ? 'Save changes' : 'Create event' }}
                  }
                </button>
                <a routerLink="/" class="btn btn-ghost text-muted-foreground">Cancel</a>
              </div>
            </div>

          </div>
        </form>
      </div>
    </div>
  `,
})
export class EventFormComponent implements OnInit {
  formData = {
    title: '',
    description: '',
    category: '' as string | number,
    date: '',
    end_date: '',
    location: '',
    address: '',
    price: 0,
    max_participants: 100,
    is_online: false,
    online_link: '',
    tax_percent: 0,
    service_fee_percent: 0,
    fees_passed_to_buyer: true,
    refundable: true,
    currency: 'USD',
    seo_title: '',
    seo_description: '',
  };

  categories: Category[] = [];
  editMode = false;
  eventId: number | null = null;
  submitting = false;
  error = '';
  success = '';

  imageFile: File | null = null;
  imagePreview: string | null = null;
  imageCleared = false;

  constructor(
    private eventService: EventService,
    private route: ActivatedRoute,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.eventService.getCategories().subscribe({
      next: cats => { this.categories = cats; },
      error: () => { this.error = 'Failed to load categories.'; },
    });

    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.editMode = true;
      this.eventId = Number(id);
      this.eventService.getEvent(this.eventId).subscribe({
        next: ev => {
          this.formData = {
            title: ev.title,
            description: ev.description,
            category: ev.category.id,
            date: ev.date,
            end_date: ev.end_date ?? '',
            location: ev.location,
            address: ev.address,
            price: parseFloat(ev.price),
            max_participants: ev.max_participants,
            is_online: ev.is_online,
            online_link: ev.online_link,
            tax_percent: parseFloat(ev.tax_percent ?? '0') || 0,
            service_fee_percent: parseFloat(ev.service_fee_percent ?? '0') || 0,
            fees_passed_to_buyer: ev.fees_passed_to_buyer ?? true,
            refundable: ev.refundable ?? true,
            currency: ev.currency ?? 'USD',
            seo_title: ev.seo_title ?? '',
            seo_description: ev.seo_description ?? '',
          };
          this.imagePreview = ev.image;
        },
        error: () => { this.error = 'Failed to load event.'; },
      });
    }
  }

  onImageSelected(evt: Event): void {
    const input = evt.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      this.error = 'Image must be under 5 MB.';
      input.value = '';
      return;
    }
    this.error = '';
    this.imageFile = file;
    this.imageCleared = false;
    const reader = new FileReader();
    reader.onload = () => { this.imagePreview = reader.result as string; };
    reader.readAsDataURL(file);
  }

  clearImage(): void {
    this.imageFile = null;
    this.imagePreview = null;
    this.imageCleared = true;
  }

  onSubmit(): void {
    this.error = ''; this.success = '';

    if (!this.formData.title.trim()) { this.error = 'Title is required.'; return; }
    if (!this.formData.description.trim()) { this.error = 'Description is required.'; return; }
    if (!this.formData.category) { this.error = 'Please select a category.'; return; }
    if (!this.formData.date) { this.error = 'Start date is required.'; return; }
    if (!this.editMode && new Date(this.formData.date).getTime() < Date.now()) {
      this.error = 'The start date is in the past.'; return;
    }
    if (this.formData.end_date && new Date(this.formData.end_date) <= new Date(this.formData.date)) {
      this.error = 'The end date must be after the start date.'; return;
    }
    if (!this.formData.location.trim()) { this.error = 'Venue name is required.'; return; }
    if (this.formData.max_participants < 1) { this.error = 'Max participants must be at least 1.'; return; }
    if (this.formData.is_online && !this.formData.online_link.trim()) {
      this.error = 'Meeting link is required for online events.'; return;
    }

    this.submitting = true;

    const payload: Record<string, unknown> = {
      title: this.formData.title,
      description: this.formData.description,
      category_id: Number(this.formData.category),
      date: this.formData.date,
      location: this.formData.location,
      address: this.formData.address,
      price: this.formData.price,
      max_participants: this.formData.max_participants,
      is_online: this.formData.is_online,
      tax_percent: this.formData.tax_percent || 0,
      service_fee_percent: this.formData.service_fee_percent || 0,
      fees_passed_to_buyer: this.formData.fees_passed_to_buyer,
      refundable: this.formData.refundable,
      currency: this.formData.currency || 'USD',
      seo_title: this.formData.seo_title || '',
      seo_description: this.formData.seo_description || '',
    };
    if (this.formData.end_date) payload['end_date'] = this.formData.end_date;
    if (this.formData.is_online && this.formData.online_link) {
      payload['online_link'] = this.formData.online_link;
    }

    // A cover image upload switches the request to multipart form-data.
    let body: any = payload;
    if (this.imageFile || this.imageCleared) {
      const fd = new FormData();
      for (const [k, v] of Object.entries(payload)) fd.append(k, String(v));
      if (this.imageFile) fd.append('image', this.imageFile);
      else fd.append('image', ''); // cleared
      body = fd;
    }

    const req = this.editMode && this.eventId
      ? this.eventService.updateEvent(this.eventId, body)
      : this.eventService.createEvent(body);

    req.subscribe({
      next: ev => {
        this.success = this.editMode ? 'Event updated!' : 'Event created and submitted for review.';
        this.submitting = false;
        setTimeout(() => this.router.navigate(['/events', ev.id]), 1000);
      },
      error: err => {
        if (err.error && typeof err.error === 'object') {
          this.error = Object.values(err.error).flat().join(' ');
        } else {
          this.error = err.error?.detail || 'Failed to save event.';
        }
        this.submitting = false;
      },
    });
  }
}
