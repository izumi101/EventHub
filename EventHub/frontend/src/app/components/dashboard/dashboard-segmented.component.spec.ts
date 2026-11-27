import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { DashboardSegmentedComponent, type SegmentedOption } from './dashboard-segmented.component';

const OPTIONS: SegmentedOption[] = [
  { value: 'a', label: 'Alpha' },
  { value: 'b', label: 'Beta' },
  { value: 'c', label: 'Gamma' },
];

@Component({
  standalone: true,
  imports: [DashboardSegmentedComponent],
  template: `
    <app-dashboard-segmented
      [options]="options"
      [value]="value()"
      label="Letters"
      (valueChange)="value.set($event)"
    />
  `,
})
class HostComponent {
  readonly options = OPTIONS;
  readonly value = signal('b');
}

function render(initial = 'b') {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({ imports: [HostComponent] });
  const fixture = TestBed.createComponent(HostComponent);
  fixture.componentInstance.value.set(initial);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const radios = () => Array.from(el.querySelectorAll<HTMLButtonElement>('[role="radio"]'));
  const press = (index: number, key: string) => {
    radios()[index].dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    fixture.detectChanges();
  };
  return { fixture, host: fixture.componentInstance, el, radios, press };
}

describe('DashboardSegmentedComponent', () => {
  it('is a named radio group with the chosen option checked', () => {
    const { el, radios } = render();
    expect(el.querySelector('[role="radiogroup"]')!.getAttribute('aria-label')).toBe('Letters');
    expect(radios().map((r) => r.getAttribute('aria-checked'))).toEqual(['false', 'true', 'false']);
    expect(radios().map((r) => r.textContent.trim())).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('puts only the chosen option in the tab order', () => {
    const { radios } = render();
    expect(radios().map((r) => r.getAttribute('tabindex'))).toEqual(['-1', '0', '-1']);
  });

  it('keeps one option reachable when the value matches none', () => {
    const { radios } = render('nope');
    expect(radios().map((r) => r.getAttribute('tabindex'))).toEqual(['0', '-1', '-1']);
  });

  it('chooses on click', () => {
    const { host, fixture, radios } = render();
    radios()[2].click();
    fixture.detectChanges();
    expect(host.value()).toBe('c');
  });

  it.each([
    ['ArrowRight', 'c'],
    ['ArrowDown', 'c'],
    ['ArrowLeft', 'a'],
    ['ArrowUp', 'a'],
    ['Home', 'a'],
    ['End', 'c'],
  ])('%s from the middle chooses %s and moves focus there', (key, expected) => {
    const { host, radios, press } = render();
    press(1, key);
    expect(host.value()).toBe(expected);
    expect(document.activeElement).toBe(radios().find((r) => r.dataset['value'] === expected));
  });

  it('wraps around at both ends', () => {
    const first = render('a');
    first.press(0, 'ArrowLeft');
    expect(first.host.value()).toBe('c');

    const last = render('c');
    last.press(2, 'ArrowRight');
    expect(last.host.value()).toBe('a');
  });

  it('leaves other keys alone', () => {
    const { host, press } = render();
    press(1, 'a');
    expect(host.value()).toBe('b');
  });
});
