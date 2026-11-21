import { TestBed } from '@angular/core/testing';
import { I18nTestingModule } from '../../i18n/testing';
import type {
  DashboardOrdering,
  DashboardTab,
  DashboardTabs,
} from '../../services/organizer-dashboard.service';
import { DashboardToolbarComponent } from './dashboard-toolbar.component';

function setup(
  inputs: { tab?: DashboardTab; counts?: DashboardTabs | null; ordering?: DashboardOrdering } = {},
) {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({ imports: [I18nTestingModule, DashboardToolbarComponent] });
  const fixture = TestBed.createComponent(DashboardToolbarComponent);
  const cmp = fixture.componentInstance;
  fixture.componentRef.setInput('tab', inputs.tab ?? 'upcoming');
  fixture.componentRef.setInput(
    'counts',
    inputs.counts === undefined ? { upcoming: 15, past: 2, drafts: 1, inactive: 0 } : inputs.counts,
  );
  fixture.componentRef.setInput('ordering', inputs.ordering ?? 'date');
  fixture.detectChanges();
  const chosen: DashboardTab[] = [];
  const orderings: DashboardOrdering[] = [];
  const searches: string[] = [];
  cmp.tabChange.subscribe((t) => chosen.push(t));
  cmp.orderingChange.subscribe((o) => orderings.push(o));
  cmp.searchInput.subscribe((s) => searches.push(s));
  const el = fixture.nativeElement as HTMLElement;
  const tabs = () => Array.from(el.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
  return { fixture, el, tabs, chosen, orderings, searches };
}

describe('DashboardToolbarComponent', () => {
  it('is a tablist of four tabs with the server counts and the selected one marked', () => {
    const { el, tabs } = setup({ tab: 'drafts' });
    expect(el.querySelector('[role="tablist"]')).not.toBeNull();
    expect(tabs().map((t) => t.textContent.replace(/\s+/g, ' ').trim())).toEqual([
      'Upcoming 15',
      'Past 2',
      'Drafts 1',
      'Inactive 0',
    ]);
    expect(tabs().map((t) => t.getAttribute('aria-selected'))).toEqual([
      'false',
      'false',
      'true',
      'false',
    ]);
  });

  it('keeps only the selected tab in the tab order (roving tabindex)', () => {
    const { tabs } = setup({ tab: 'past' });
    expect(tabs().map((t) => t.getAttribute('tabindex'))).toEqual(['-1', '0', '-1', '-1']);
  });

  it('shows no counts while they are unknown', () => {
    const { tabs } = setup({ counts: null });
    expect(tabs().map((t) => t.textContent.trim())).toEqual([
      'Upcoming',
      'Past',
      'Drafts',
      'Inactive',
    ]);
  });

  it('reports a clicked tab', () => {
    const { tabs, chosen } = setup();
    tabs()[1].click();
    expect(chosen).toEqual(['past']);
  });

  it('moves with the arrow keys, wraps, and supports Home and End', () => {
    const { tabs, chosen } = setup({ tab: 'upcoming' });
    const key = (index: number, k: string) =>
      tabs()[index].dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));
    key(0, 'ArrowRight');
    key(0, 'ArrowLeft');
    key(0, 'End');
    key(3, 'Home');
    key(1, 'ArrowRight');
    expect(chosen).toEqual(['past', 'inactive', 'inactive', 'upcoming', 'drafts']);
  });

  it('moves focus to the tab it selects and ignores other keys', () => {
    const { tabs, chosen } = setup();
    tabs()[0].focus();
    tabs()[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(document.activeElement).toBe(tabs()[1]);
    tabs()[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    expect(chosen).toEqual(['past']);
  });

  it('lists the five sorts and shows the given one as selected', () => {
    const { el } = setup({ tab: 'past', ordering: '-date' });
    const select = el.querySelector<HTMLSelectElement>('[data-testid="dashboard-sort"]')!;
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      'date',
      '-date',
      '-tickets_sold',
      '-checkin_rate',
      '-sold_through',
    ]);
    expect(select.value).toBe('-date');
    expect(Array.from(select.options).map((o) => o.textContent.trim())).toEqual([
      'Date, soonest first',
      'Date, latest first',
      'Most tickets sold',
      'Check-in rate',
      'Sell-through',
    ]);
  });

  it('reports a changed sort and every keystroke of the search', () => {
    const { el, orderings, searches } = setup();
    const select = el.querySelector<HTMLSelectElement>('[data-testid="dashboard-sort"]')!;
    select.value = '-tickets_sold';
    select.dispatchEvent(new Event('change'));
    expect(orderings).toEqual(['-tickets_sold']);

    const input = el.querySelector<HTMLInputElement>('[data-testid="dashboard-search"]')!;
    input.value = 'ja';
    input.dispatchEvent(new Event('input'));
    expect(searches).toEqual(['ja']);
    expect(input.getAttribute('aria-label')).toBe('Search events by title or location');
  });
});
