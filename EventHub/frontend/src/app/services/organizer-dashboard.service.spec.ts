import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { environment } from '../../environments/environment';
import {
  DEFAULT_SALES_RANGE,
  OrganizerDashboardService,
  SALES_RANGES,
} from './organizer-dashboard.service';
import {
  reviewsSummary,
  salesChart,
  todayBlock,
  todayEvent,
} from '../components/dashboard/dashboard.testing';

const API = `${environment.apiUrl}/organizer`;

describe('OrganizerDashboardService', () => {
  let http: HttpTestingController;
  let service: OrganizerDashboardService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    service = TestBed.inject(OrganizerDashboardService);
  });

  afterEach(() => {
    http.verify();
  });

  it('reads the summary from organizer/dashboard/', () => {
    let tickets = -1;
    service.getSummary().subscribe((s) => (tickets = s.tickets_sold));
    const req = http.expectOne(`${API}/dashboard/`);
    expect(req.request.method).toBe('GET');
    req.flush({ tickets_sold: 9 });
    expect(tickets).toBe(9);
  });

  it('sends every given list parameter under the API names', () => {
    service
      .getEvents({
        tab: 'past',
        search: 'jazz',
        ordering: '-tickets_sold',
        page: 3,
        pageSize: 20,
      })
      .subscribe();
    const req = http.expectOne((r) => r.url === `${API}/events/`);
    expect(req.request.params.keys().sort()).toEqual([
      'ordering',
      'page',
      'page_size',
      'search',
      'tab',
    ]);
    expect(req.request.params.get('tab')).toBe('past');
    expect(req.request.params.get('search')).toBe('jazz');
    expect(req.request.params.get('ordering')).toBe('-tickets_sold');
    expect(req.request.params.get('page')).toBe('3');
    expect(req.request.params.get('page_size')).toBe('20');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('omits empty parameters so the server defaults apply', () => {
    service.getEvents({ search: '   ', ordering: undefined, page: undefined }).subscribe();
    const req = http.expectOne((r) => r.url === `${API}/events/`);
    expect(req.request.params.keys()).toEqual([]);
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('trims the search and cuts it to the 100 characters the API accepts', () => {
    service.getEvents({ search: `  ${'x'.repeat(130)}  ` }).subscribe();
    const req = http.expectOne((r) => r.url === `${API}/events/`);
    expect(req.request.params.get('search')).toBe('x'.repeat(100));
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('asks the activity feed for a limit and the cursor of the previous page', () => {
    service.getActivity({ limit: 10, cursor: 'abc' }).subscribe();
    const req = http.expectOne((r) => r.url === `${API}/activity/`);
    expect(req.request.params.get('limit')).toBe('10');
    expect(req.request.params.get('cursor')).toBe('abc');
    req.flush({ results: [], next_cursor: null });
  });

  it('sends no cursor for the first page of the feed', () => {
    service.getActivity({ limit: 10, cursor: null }).subscribe();
    const req = http.expectOne((r) => r.url === `${API}/activity/`);
    expect(req.request.params.has('cursor')).toBe(false);
    req.flush({ results: [], next_cursor: null });
  });

  describe('batch A', () => {
    it('asks for the 30-day chart when no range is given', () => {
      service.getSales().subscribe();
      const req = http.expectOne((r) => r.url === `${API}/sales/`);
      expect(req.request.method).toBe('GET');
      expect(req.request.params.get('range')).toBe('30d');
      req.flush({});
    });

    it.each(SALES_RANGES)('sends range=%s', (range) => {
      service.getSales(range).subscribe();
      const req = http.expectOne((r) => r.url === `${API}/sales/`);
      expect(req.request.params.keys()).toEqual(['range']);
      expect(req.request.params.get('range')).toBe(range);
      req.flush({});
    });

    it('returns the chart payload as the API sent it', () => {
      const chart = salesChart();
      let received: unknown;
      service.getSales('7d').subscribe((c) => (received = c));
      http.expectOne((r) => r.url === `${API}/sales/`).flush(chart);
      expect(received).toEqual(chart);
    });

    it('offers the three windows, with 30 days as the default', () => {
      expect(SALES_RANGES).toEqual(['7d', '30d', '90d']);
      expect(DEFAULT_SALES_RANGE).toBe('30d');
    });

    it('reads the today block from organizer/today/ without parameters', () => {
      let more = -1;
      service.getToday().subscribe((t) => (more = t.more));
      const req = http.expectOne(`${API}/today/`);
      expect(req.request.method).toBe('GET');
      expect(req.request.params.keys()).toEqual([]);
      req.flush(todayBlock([todayEvent(1)], 2));
      expect(more).toBe(2);
    });

    it('reads the reviews summary from organizer/reviews/ without parameters', () => {
      let average: number | null = -1;
      service.getReviews().subscribe((r) => (average = r.average));
      const req = http.expectOne(`${API}/reviews/`);
      expect(req.request.method).toBe('GET');
      expect(req.request.params.keys()).toEqual([]);
      req.flush(reviewsSummary());
      expect(average).toBe(4.42);
    });

    it('passes a server error on to the caller', () => {
      let status = 0;
      service.getSales().subscribe({
        error: (err: { status: number }) => (status = err.status),
      });
      http
        .expectOne((r) => r.url === `${API}/sales/`)
        .flush({ detail: 'nope' }, { status: 500, statusText: 'Server Error' });
      expect(status).toBe(500);
    });
  });
});
