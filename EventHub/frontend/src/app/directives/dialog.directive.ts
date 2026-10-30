import {
  AfterViewInit,
  Directive,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnDestroy,
  Output,
  Renderer2,
  booleanAttribute,
  inject,
} from '@angular/core';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

let nextId = 0;

/**
 * Makes a modal panel accessible: role="dialog" + aria-modal, labelled by its
 * first heading, focus moved inside on open and trapped while open, Escape
 * emits (dismiss), and focus returns to the opener on close.
 *
 *   <div class="card" appDialog (dismiss)="close()">…</div>
 *
 * With `dismissOnBackdrop`, a click on the overlay around the panel (its parent
 * element) emits (dismiss) too, while clicks inside the panel stay inside it.
 * The pointer gesture mirrors Escape, so the backdrop itself needs no handler:
 *
 *   <div class="fixed inset-0 bg-black/50">
 *     <div class="card" appDialog dismissOnBackdrop (dismiss)="close()">…</div>
 *   </div>
 */
@Directive({
  selector: '[appDialog]',
  standalone: true,
  host: { role: 'dialog', 'aria-modal': 'true', tabindex: '-1' },
})
export class DialogDirective implements AfterViewInit, OnDestroy {
  @Input({ transform: booleanAttribute }) dismissOnBackdrop = false;
  @Output() readonly dismiss = new EventEmitter<void>();

  private readonly el: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly renderer = inject(Renderer2);
  private readonly opener = document.activeElement as HTMLElement | null;
  private unlistenBackdrop?: () => void;

  ngAfterViewInit(): void {
    const heading = this.el.querySelector<HTMLElement>('h1, h2, h3');
    if (heading && !this.el.hasAttribute('aria-labelledby')) {
      heading.id ||= `dialog-title-${++nextId}`;
      this.el.setAttribute('aria-labelledby', heading.id);
    }
    const backdrop = this.el.parentElement;
    if (this.dismissOnBackdrop && backdrop) {
      this.unlistenBackdrop = this.renderer.listen(backdrop, 'click', () => {
        this.dismiss.emit();
      });
    }
    (this.focusables()[0] ?? this.el).focus();
  }

  ngOnDestroy(): void {
    this.unlistenBackdrop?.();
    this.opener?.focus();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.dismiss.emit();
  }

  /** Clicks inside the panel must not reach the backdrop (and close the dialog). */
  @HostListener('click', ['$event'])
  keepClickInside(event: MouseEvent): void {
    if (this.dismissOnBackdrop) event.stopPropagation();
  }

  @HostListener('keydown', ['$event'])
  trapTab(event: KeyboardEvent): void {
    if (event.key !== 'Tab') return;
    const items = this.focusables();
    if (!items.length) {
      event.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      last.focus();
      event.preventDefault();
    } else if (!event.shiftKey && document.activeElement === last) {
      first.focus();
      event.preventDefault();
    }
  }

  private focusables(): HTMLElement[] {
    return Array.from(this.el.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (e) => e.offsetParent !== null || e === document.activeElement,
    );
  }
}
