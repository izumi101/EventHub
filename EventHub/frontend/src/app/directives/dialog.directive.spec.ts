import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { DialogDirective } from './dialog.directive';

@Component({
  standalone: true,
  imports: [DialogDirective],
  template: `
    <button id="opener">open</button>
    @if (open) {
      <div appDialog (dismiss)="open = false">
        <h3>Refund</h3>
        <button id="first">Cancel</button>
        <button id="last">Confirm</button>
      </div>
    }
  `,
})
class HostComponent {
  open = true;
}

describe('DialogDirective', () => {
  it('is an accessible modal: labelled, focused, closes on Escape', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const dialog: HTMLElement = fixture.nativeElement.querySelector('[appDialog]');

    expect(dialog.getAttribute('role')).toBe('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const title = document.getElementById(dialog.getAttribute('aria-labelledby')!);
    expect(title?.textContent).toBe('Refund');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();
    expect(fixture.componentInstance.open).toBe(false);
  });

  it('keeps Tab inside the dialog', () => {
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const dialog: HTMLElement = fixture.nativeElement.querySelector('[appDialog]');
    const last: HTMLElement = dialog.querySelector('#last')!;
    last.focus();
    const tab = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true });
    dialog.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
  });
});
