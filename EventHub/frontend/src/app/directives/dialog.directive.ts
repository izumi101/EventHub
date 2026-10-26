import { AfterViewInit, Directive, ElementRef, EventEmitter, HostListener, OnDestroy, Output, inject } from '@angular/core';

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])', 'select:not([disabled])',
  'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',');

let nextId = 0;

/**
 * Makes a modal panel accessible: role="dialog" + aria-modal, labelled by its
 * first heading, focus moved inside on open and trapped while open, Escape
 * emits (dismiss), and focus returns to the opener on close.
 *
 *   <div class="card" appDialog (dismiss)="close()">…</div>
 */
@Directive({
  selector: '[appDialog]',
  standalone: true,
  host: { role: 'dialog', 'aria-modal': 'true', tabindex: '-1' },
})
export class DialogDirective implements AfterViewInit, OnDestroy {
  @Output() dismiss = new EventEmitter<void>();

  private readonly el: HTMLElement = inject(ElementRef).nativeElement;
  private readonly opener = document.activeElement as HTMLElement | null;

  ngAfterViewInit(): void {
    const heading = this.el.querySelector<HTMLElement>('h1, h2, h3');
    if (heading && !this.el.hasAttribute('aria-labelledby')) {
      heading.id ||= `dialog-title-${++nextId}`;
      this.el.setAttribute('aria-labelledby', heading.id);
    }
    (this.focusables()[0] ?? this.el).focus();
  }

  ngOnDestroy(): void {
    this.opener?.focus?.();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.dismiss.emit();
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
    return Array.from(this.el.querySelectorAll<HTMLElement>(FOCUSABLE))
      .filter(e => e.offsetParent !== null || e === document.activeElement);
  }
}
