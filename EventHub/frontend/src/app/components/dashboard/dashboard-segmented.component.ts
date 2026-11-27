import { Component, ElementRef, computed, input, output, viewChildren } from '@angular/core';

export interface SegmentedOption {
  value: string;
  label: string;
}

/**
 * A small single-choice toggle (the sales range, the revenue currency): a
 * radio group in the accessible sense. One button is in the tab order, the
 * arrow keys move the choice, Home and End jump to the ends.
 */
@Component({
  selector: 'app-dashboard-segmented',
  standalone: true,
  template: `
    <div
      role="radiogroup"
      [attr.aria-label]="label()"
      class="inline-flex max-w-full overflow-x-auto rounded-md border border-border bg-muted/50 p-0.5 gap-0.5"
    >
      @for (o of options(); track o.value) {
        <button
          #radio
          type="button"
          role="radio"
          [attr.aria-checked]="o.value === value()"
          [attr.tabindex]="o.value === tabValue() ? 0 : -1"
          [attr.data-value]="o.value"
          (click)="valueChange.emit(o.value)"
          (keydown)="onKeydown($event)"
          class="px-3 py-1 text-xs font-medium rounded-sm whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          [class]="
            o.value === value()
              ? 'bg-background text-foreground shadow-xs'
              : 'text-muted-foreground hover:text-foreground'
          "
        >
          {{ o.label }}
        </button>
      }
    </div>
  `,
})
export class DashboardSegmentedComponent {
  readonly options = input.required<readonly SegmentedOption[]>();
  readonly value = input.required<string>();
  /** The accessible name of the group. */
  readonly label = input.required<string>();
  readonly valueChange = output<string>();

  private readonly radios = viewChildren<ElementRef<HTMLButtonElement>>('radio');

  /** The one option in the tab order: the chosen one, or the first when none matches. */
  protected readonly tabValue = computed(() => {
    const options = this.options();
    return options.some((o) => o.value === this.value()) ? this.value() : options[0]?.value;
  });

  onKeydown(event: KeyboardEvent): void {
    const options = this.options();
    const last = options.length - 1;
    // The focused button counts, not the chosen one: the page applies a choice a moment later.
    const focused = this.radios().findIndex((r) => r.nativeElement === event.target);
    const current =
      focused >= 0
        ? focused
        : Math.max(
            0,
            options.findIndex((o) => o.value === this.value()),
          );
    let next: number;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        next = current === last ? 0 : current + 1;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        next = current === 0 ? last : current - 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }
    event.preventDefault();
    this.valueChange.emit(options[next].value);
    this.radios()[next]?.nativeElement.focus();
  }
}
