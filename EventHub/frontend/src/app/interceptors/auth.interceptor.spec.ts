import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { authInterceptor } from './auth.interceptor';

describe('authInterceptor', () => {
  let client: HttpClient;
  let http: HttpTestingController;
  const router = { url: '/my-registrations', navigate: vi.fn() };

  beforeEach(() => {
    localStorage.clear();
    router.navigate.mockReset();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: router },
      ],
    });
    client = TestBed.inject(HttpClient);
    http = TestBed.inject(HttpTestingController);
    localStorage.setItem('access_token', 'expired');
    localStorage.setItem('refresh_token', 'refresh-1');
  });

  afterEach(() => http.verify());

  it('sends the token only to our own API', () => {
    client.get('/api/events/').subscribe();
    client.get('https://evil.example/api/steal').subscribe();

    expect(http.expectOne('/api/events/').request.headers.get('Authorization')).toBe('Bearer expired');
    expect(http.expectOne('https://evil.example/api/steal').request.headers.has('Authorization')).toBe(false);
  });

  it('refreshes once for parallel 401s and retries every request', () => {
    const done: string[] = [];
    client.get<string>('/api/a/').subscribe(v => done.push(v));
    client.get<string>('/api/b/').subscribe(v => done.push(v));

    http.expectOne('/api/a/').flush(null, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/b/').flush(null, { status: 401, statusText: 'Unauthorized' });

    // Exactly one refresh request for both failures.
    http.expectOne('/api/auth/token/refresh/').flush({ access: 'fresh', refresh: 'refresh-2' });

    const retryA = http.expectOne('/api/a/');
    const retryB = http.expectOne('/api/b/');
    expect(retryA.request.headers.get('Authorization')).toBe('Bearer fresh');
    expect(retryB.request.headers.get('Authorization')).toBe('Bearer fresh');
    retryA.flush('A');
    retryB.flush('B');
    expect(done.sort()).toEqual(['A', 'B']);
    expect(localStorage.getItem('refresh_token')).toBe('refresh-2');
  });

  it('logs out and goes to login when the refresh fails', () => {
    let failed = false;
    client.get('/api/a/').subscribe({ error: () => (failed = true) });
    http.expectOne('/api/a/').flush(null, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/auth/token/refresh/').flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(failed).toBe(true);
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(router.navigate).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/my-registrations' } });
  });
});
