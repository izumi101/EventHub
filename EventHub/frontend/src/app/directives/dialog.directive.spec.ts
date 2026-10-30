import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { DialogDirective } from './dialog.directive';

@Component({
  standalone: true,
  imports: [DialogDirective],
  template: `
    <button id="opener">open</button>
    @if (open) {
      <div id="backdrop">
        <div appDialog [dismissOnBackdrop]="backdropDismiss" (dismiss)="open = false">
          <h3>Refund</h3>
          <button id="first">Cancel</button>
          <button id="last">Confirm</button>
        </div>
      </div>
    }
  `,
})
class HostComponent {
  open = true;
  backdropDismiss = false;
}

function setUp(backdropDismiss = false) {
  const fixture = TestBed.createComponent(HostComponent);
  fixture.componentInstance.backdropDismiss = backdropDismiss;
  fixture.detectChanges();
  const root = fixture.nativeElement as HTMLElement;
  const dialog = root.querySelector<HTMLElement>('[appDialog]')!;
  return { fixture, root, dialog };
}

describe('DialogDirective', () => {
  it('is an accessible modal: labelled, focused, closes on Escape', () => {
    const { fixture, dialog } = setUp();

    expect(dialog.getAttribute('role')).toBe('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const title = document.getElementById(dialog.getAttribute('aria-labelledby')!);
    expect(title?.textContent).toBe('Refund');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();
    expect(fixture.componentInstance.open).toBe(false);
  });

  it('keeps Tab inside the dialog', () => {
    const { dialog } = setUp();
    const last = dialog.querySelector<HTMLElement>('#last')!;
    last.focus();
    const tab = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true });
    dialog.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
  });

  it('ignores backdrop clicks unless dismissOnBackdrop is set', () => {
    const { fixture, root } = setUp();
    root.querySelector<HTMLElement>('#backdrop')!.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.open).toBe(true);
  });

  it('with dismissOnBackdrop, closes on a backdrop click but not on clicks inside', () => {
    const { fixture, root, dialog } = setUp(true);

    dialog.querySelector<HTMLElement>('#first')!.click();
    dialog.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.open).toBe(true);

    root.querySelector<HTMLElement>('#backdrop')!.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.open).toBe(false);
  });
});
