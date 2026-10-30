import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let auth: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('stores the rotated refresh token (the old one is blacklisted by the API)', () => {
    localStorage.setItem('refresh_token', 'old-refresh');
    auth.refreshToken().subscribe();

    const req = http.expectOne('/api/auth/token/refresh/');
    expect(req.request.body).toEqual({ refresh: 'old-refresh' });
    req.flush({ access: 'new-access', refresh: 'new-refresh' });

    expect(localStorage.getItem('access_token')).toBe('new-access');
    expect(localStorage.getItem('refresh_token')).toBe('new-refresh');
  });

  it('keeps the current refresh token when the API does not rotate', () => {
    localStorage.setItem('refresh_token', 'kept');
    auth.refreshToken().subscribe();
    http.expectOne('/api/auth/token/refresh/').flush({ access: 'a2' });
    expect(localStorage.getItem('refresh_token')).toBe('kept');
  });

  it('shares one refresh request between concurrent callers', () => {
    localStorage.setItem('refresh_token', 'r');
    const results: string[] = [];
    auth.refreshToken().subscribe(r => results.push(r.access));
    auth.refreshToken().subscribe(r => results.push(r.access));

    http.expectOne('/api/auth/token/refresh/').flush({ access: 'shared', refresh: 'r2' });
    expect(results).toEqual(['shared', 'shared']);

    // Once finished, the next refresh is a new request.
    auth.refreshToken().subscribe();
    http.expectOne('/api/auth/token/refresh/').flush({ access: 'later' });
  });

  it('keeps this device signed in after a password change', () => {
    auth.changePassword('old', 'New-pass-123', 'New-pass-123').subscribe();
    http.expectOne('/api/auth/change-password/').flush({
      message: 'ok', tokens: { access: 'fresh-access', refresh: 'fresh-refresh' },
    });
    expect(localStorage.getItem('access_token')).toBe('fresh-access');
    expect(localStorage.getItem('refresh_token')).toBe('fresh-refresh');
  });
});
