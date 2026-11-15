import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { BehaviorSubject, Subject } from 'rxjs';
import { LanguageSyncService } from './language-sync.service';
import { LanguageService } from './language.service';
import { AuthService } from '../services/auth.service';
import { environment } from '../../environments/environment';
import type { Lang } from './languages';

const URL = `${environment.apiUrl}/auth/profile/notifications/`;

describe('LanguageSyncService', () => {
  let http: HttpTestingController;
  let user$: BehaviorSubject<{ id: number } | null>;
  let switched$: Subject<Lang>;
  let lang: ReturnType<typeof signal<Lang>>;
  let loggedIn: boolean;

  function start(): void {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: AuthService,
          useValue: {
            currentUser$: user$,
            get isLoggedIn() {
              return loggedIn;
            },
          },
        },
        { provide: LanguageService, useValue: { lang, switched$ } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    TestBed.inject(LanguageSyncService).start();
  }

  beforeEach(() => {
    user$ = new BehaviorSubject<{ id: number } | null>(null);
    switched$ = new Subject<Lang>();
    lang = signal<Lang>('ru');
    loggedIn = false;
  });

  afterEach(() => http.verify());

  it('does nothing for a signed-out visitor', () => {
    start();
    switched$.next('kk');
    http.expectNone(URL);
  });

  it('saves the language when a signed-in user switches it', () => {
    user$.next({ id: 1 });
    loggedIn = true;
    start();
    http
      .expectOne({ method: 'GET', url: URL })
      .flush({ email_address: '', language: 'ru', types: [] });

    lang.set('kk');
    switched$.next('kk');
    const req = http.expectOne({ method: 'PATCH', url: URL });
    expect(req.request.body).toEqual({ language: 'kk' });
    req.flush({});
  });

  it('after sign-in, saves the UI language once if the stored one differs', () => {
    start();
    loggedIn = true;
    user$.next({ id: 7 });
    http
      .expectOne({ method: 'GET', url: URL })
      .flush({ email_address: '', language: '', types: [] });
    const req = http.expectOne({ method: 'PATCH', url: URL });
    expect(req.request.body).toEqual({ language: 'ru' });
    req.flush({});

    // The same user again (e.g. a profile refresh): no new check.
    user$.next({ id: 7 });
    http.expectNone(URL);
  });

  it('leaves a matching stored language alone', () => {
    loggedIn = true;
    user$.next({ id: 3 });
    start();
    http
      .expectOne({ method: 'GET', url: URL })
      .flush({ email_address: '', language: 'ru', types: [] });
    http.expectNone({ method: 'PATCH', url: URL });
  });

  it('ignores failures', () => {
    loggedIn = true;
    user$.next({ id: 3 });
    start();
    http.expectOne(URL).flush({}, { status: 500, statusText: 'Server Error' });
    switched$.next('en');
    http.expectOne({ method: 'PATCH', url: URL }).flush({}, { status: 503, statusText: 'Down' });
  });
});
