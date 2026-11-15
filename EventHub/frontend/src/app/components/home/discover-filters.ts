import { ParamMap, Params } from '@angular/router';

/** Discover filter state; it lives in the URL (`/?q=&ai=1&city=&category=&free=1&online=1&sort=`). */
export interface DiscoverFilters {
  q: string;
  ai: boolean;
  city: string;
  category: number | null;
  free: boolean;
  online: boolean;
  sort: string;
}

export const DEFAULT_SORT = 'date';
export const SORTS = ['date', '-date', '-created_at', 'price', '-price'] as const;

export const EMPTY_FILTERS: DiscoverFilters = {
  q: '',
  ai: false,
  city: '',
  category: null,
  free: false,
  online: false,
  sort: DEFAULT_SORT,
};

/** The visitor's city is remembered (Q2); the URL wins when it names one. */
export const CITY_STORAGE_KEY = 'eventhub.city';

export function filtersFromParams(params: ParamMap, storedCity = ''): DiscoverFilters {
  const category = Number(params.get('category'));
  const sort = params.get('sort') ?? DEFAULT_SORT;
  return {
    q: (params.get('q') ?? '').trim(),
    ai: params.get('ai') === '1',
    city: (params.has('city') ? (params.get('city') ?? '') : storedCity).trim(),
    category: Number.isInteger(category) && category > 0 ? category : null,
    free: params.get('free') === '1',
    online: params.get('online') === '1',
    sort: (SORTS as readonly string[]).includes(sort) ? sort : DEFAULT_SORT,
  };
}

/** Query params for the URL: every key is present so a merge also clears. */
export function filtersToParams(f: DiscoverFilters): Params {
  return {
    q: f.q || null,
    ai: f.ai ? 1 : null,
    city: f.city || null,
    category: f.category,
    free: f.free ? 1 : null,
    online: f.online ? 1 : null,
    sort: f.sort === DEFAULT_SORT ? null : f.sort,
  };
}

/** `GET /events/` params — the same API params the old Discover page sent. */
export function filtersToApi(f: DiscoverFilters, page = 1) {
  const semantic = f.ai && !!f.q;
  return {
    page,
    upcoming: true, // Discover never shows events that already happened
    ...(semantic ? { q: f.q } : f.q ? { search: f.q } : {}),
    ...(f.city ? { location: f.city } : {}),
    ...(f.category !== null ? { category: f.category } : {}),
    ordering: f.sort,
    ...(f.free ? { is_free: true } : {}),
    ...(f.online ? { is_online: true } : {}),
  };
}

/**
 * Filters that narrow the list and hide the rails. The city is a standing
 * preference, so it does not hide them — it adds the "In <city>" rail.
 */
export function hasActiveFilters(f: DiscoverFilters): boolean {
  return !!f.q || f.category !== null || f.free || f.online || f.sort !== DEFAULT_SORT;
}

/** Badge on the mobile "Filters" button: what the sheet controls. */
export function sheetFilterCount(f: DiscoverFilters): number {
  return [!!f.city, f.free, f.online, f.sort !== DEFAULT_SORT].filter(Boolean).length;
}
