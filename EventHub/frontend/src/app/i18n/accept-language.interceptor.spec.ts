import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../environments/environment';
import { acceptLanguageInterceptor } from './accept-language.interceptor';
import { LanguageService } from './language.service';
import { I18nTestingModule } from './testing';

describe('acceptLanguageInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [I18nTestingModule],
      providers: [
        provideHttpClient(withInterceptors([acceptLanguageInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  it('sends the active language to our own API and follows switches', async () => {
    http.get(`${environment.apiUrl}/events/`).subscribe();
    expect(
      backend.expectOne(`${environment.apiUrl}/events/`).request.headers.get('Accept-Language'),
    ).toBe('en');

    await TestBed.inject(LanguageService).setLang('kk');
    http.get(`${environment.apiUrl}/events/`).subscribe();
    expect(
      backend.expectOne(`${environment.apiUrl}/events/`).request.headers.get('Accept-Language'),
    ).toBe('kk');
  });

  it('leaves third-party requests alone', () => {
    http.get('https://example.com/x').subscribe();
    expect(backend.expectOne('https://example.com/x').request.headers.has('Accept-Language')).toBe(
      false,
    );
  });

  it('keeps an explicit Accept-Language header', () => {
    http.get(`${environment.apiUrl}/a/`, { headers: { 'Accept-Language': 'fr' } }).subscribe();
    expect(
      backend.expectOne(`${environment.apiUrl}/a/`).request.headers.get('Accept-Language'),
    ).toBe('fr');
  });
});
