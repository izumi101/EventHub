import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { authInterceptor } from './auth.interceptor';
import { environment } from '../../environments/environment';

const API = environment.apiUrl;

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
    client.get(`${API}/events/`).subscribe();
    client.get('https://evil.example/api/steal').subscribe();

    expect(http.expectOne(`${API}/events/`).request.headers.get('Authorization')).toBe(
      'Bearer expired',
    );
    expect(
      http.expectOne('https://evil.example/api/steal').request.headers.has('Authorization'),
    ).toBe(false);
  });

  it('refreshes once for parallel 401s and retries every request', () => {
    const done: string[] = [];
    client.get<string>(`${API}/a/`).subscribe((v) => done.push(v));
    client.get<string>(`${API}/b/`).subscribe((v) => done.push(v));

    http.expectOne(`${API}/a/`).flush(null, { status: 401, statusText: 'Unauthorized' });
    http.expectOne(`${API}/b/`).flush(null, { status: 401, statusText: 'Unauthorized' });

    // Exactly one refresh request for both failures.
    http.expectOne(`${API}/auth/token/refresh/`).flush({ access: 'fresh', refresh: 'refresh-2' });

    const retryA = http.expectOne(`${API}/a/`);
    const retryB = http.expectOne(`${API}/b/`);
    expect(retryA.request.headers.get('Authorization')).toBe('Bearer fresh');
    expect(retryB.request.headers.get('Authorization')).toBe('Bearer fresh');
    retryA.flush('A');
    retryB.flush('B');
    expect(done.sort()).toEqual(['A', 'B']);
    expect(localStorage.getItem('refresh_token')).toBe('refresh-2');
  });

  it('logs out and goes to login when the refresh fails', () => {
    let failed = false;
    client.get(`${API}/a/`).subscribe({ error: () => (failed = true) });
    http.expectOne(`${API}/a/`).flush(null, { status: 401, statusText: 'Unauthorized' });
    http
      .expectOne(`${API}/auth/token/refresh/`)
      .flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(failed).toBe(true);
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(router.navigate).toHaveBeenCalledWith(['/login'], {
      queryParams: { returnUrl: '/my-registrations' },
    });
  });
});
