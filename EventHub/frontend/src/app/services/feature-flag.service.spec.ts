import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { FeatureFlagService } from './feature-flag.service';
import { AuthService } from './auth.service';
import { environment } from '../../environments/environment';

const FLAGS_URL = `${environment.apiUrl}/feature-flags/`;
const LOGIN_URL = `${environment.apiUrl}/auth/login/`;

function signIn(id: number): void {
  localStorage.setItem('access_token', 't');
  localStorage.setItem('user', JSON.stringify({ id, username: `user${id}` }));
}

describe('FeatureFlagService', () => {
  let http: HttpTestingController;

  function setUp(): FeatureFlagService {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    return TestBed.inject(FeatureFlagService);
  }

  beforeEach(() => localStorage.clear());
  afterEach(() => http.verify());

  it('asks nothing and keeps every flag off while signed out', () => {
    const flags = setUp();
    http.expectNone(FLAGS_URL);
    expect(flags.isEnabled('payments.freedompay')).toBe(false);
    expect(flags.loaded()).toBe(false);
  });

  it('loads the flags once for a stored session', () => {
    signIn(1);
    const flags = setUp();
    const scanner = flags.flag('checkin.offline_scanner');

    const req = http.expectOne(FLAGS_URL);
    expect(req.request.method).toBe('GET');
    req.flush({ flags: { 'payments.freedompay': true, 'checkin.offline_scanner': false } });

    expect(flags.isEnabled('payments.freedompay')).toBe(true);
    expect(flags.isEnabled('checkin.offline_scanner')).toBe(false);
    expect(scanner()).toBe(false);
    expect(flags.loaded()).toBe(true);

    // A profile update for the same user doesn't refetch.
    TestBed.inject(AuthService).getProfile().subscribe();
    http.expectOne(`${environment.apiUrl}/auth/profile/`).flush({ id: 1, username: 'renamed' });
    http.expectNone(FLAGS_URL);
  });

  it('keeps every flag off when the request fails', () => {
    signIn(1);
    const flags = setUp();
    http.expectOne(FLAGS_URL).flush({ detail: 'boom' }, { status: 500, statusText: 'Server Error' });
    expect(flags.isEnabled('payments.freedompay')).toBe(false);
    expect(flags.isEnabled('checkin.offline_scanner')).toBe(false);
    expect(flags.loaded()).toBe(false);
  });

  it('treats anything but true as off', () => {
    signIn(1);
    const flags = setUp();
    http.expectOne(FLAGS_URL).flush({ flags: { 'payments.freedompay': 'yes' } });
    expect(flags.isEnabled('payments.freedompay')).toBe(false);
  });

  it('forgets the flags on logout and loads them for the next user', () => {
    signIn(1);
    const flags = setUp();
    const auth = TestBed.inject(AuthService);
    const freedomPay = flags.flag('payments.freedompay');
    http.expectOne(FLAGS_URL).flush({ flags: { 'payments.freedompay': true, 'checkin.offline_scanner': true } });
    expect(freedomPay()).toBe(true);

    auth.forceLogout();
    expect(freedomPay()).toBe(false);
    expect(flags.loaded()).toBe(false);
    http.expectNone(FLAGS_URL);

    auth.login('user2', 'secret-123').subscribe();
    http.expectOne(LOGIN_URL).flush({
      user: { id: 2, username: 'user2' },
      tokens: { access: 'a2', refresh: 'r2' },
    });
    http.expectOne(FLAGS_URL).flush({ flags: { 'payments.freedompay': false, 'checkin.offline_scanner': true } });
    expect(freedomPay()).toBe(false);
    expect(flags.isEnabled('checkin.offline_scanner')).toBe(true);
  });

  it('refresh() re-reads the flags and keeps them when that fails', () => {
    signIn(1);
    const flags = setUp();
    http.expectOne(FLAGS_URL).flush({ flags: { 'payments.freedompay': true, 'checkin.offline_scanner': false } });

    flags.refresh();
    http.expectOne(FLAGS_URL).flush({ flags: { 'payments.freedompay': true, 'checkin.offline_scanner': true } });
    expect(flags.isEnabled('checkin.offline_scanner')).toBe(true);

    flags.refresh();
    http.expectOne(FLAGS_URL).error(new ProgressEvent('offline'));
    expect(flags.isEnabled('checkin.offline_scanner')).toBe(true);
  });
});
