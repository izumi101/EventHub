import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { UnsubscribeComponent } from './unsubscribe.component';
import { I18nTestingModule } from '../../i18n/testing';
import { environment } from '../../../environments/environment';

const URL = `${environment.apiUrl}/notifications/unsubscribe/`;

describe('UnsubscribeComponent', () => {
  let fixture: ComponentFixture<UnsubscribeComponent>;
  let http: HttpTestingController;

  const text = (): string => (fixture.nativeElement as HTMLElement).textContent;
  const button = (): HTMLButtonElement | null =>
    (fixture.nativeElement as HTMLElement).querySelector('button.btn-primary');

  function create(token: string | null): void {
    TestBed.configureTestingModule({
      imports: [UnsubscribeComponent, I18nTestingModule],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { queryParamMap: convertToParamMap(token === null ? {} : { token }) },
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(UnsubscribeComponent);
    fixture.detectChanges();
  }

  afterEach(() => http.verify());

  it('shows the type and changes nothing until confirmed', () => {
    create('tok:en');
    const req = http.expectOne((r) => r.url === URL && r.method === 'GET');
    expect(req.request.params.get('token')).toBe('tok:en');
    req.flush({ type: 'event_reminder', label: 'Event reminder' });
    fixture.detectChanges();
    expect(text()).toContain('Stop sending “Event reminder” emails to you?');
    http.expectNone({ method: 'POST', url: URL });
  });

  it('unsubscribes on confirm and links to the settings', () => {
    create('tok');
    http.expectOne(`${URL}?token=tok`).flush({ type: 'event_reminder', label: 'Event reminder' });
    fixture.detectChanges();
    button()!.click();
    const post = http.expectOne({ method: 'POST', url: URL });
    expect(post.request.body).toEqual({ token: 'tok' });
    post.flush({ type: 'event_reminder', label: 'Event reminder' });
    fixture.detectChanges();
    expect(text()).toContain('you will no longer receive “Event reminder” emails');
    const link = (fixture.nativeElement as HTMLElement).querySelector(
      'a[href="/profile/notifications"]',
    );
    expect(link).not.toBeNull();
  });

  it('reports a failed save and lets the user retry', () => {
    create('tok');
    http.expectOne(`${URL}?token=tok`).flush({ type: 'event_reminder', label: 'Event reminder' });
    fixture.detectChanges();
    button()!.click();
    http.expectOne({ method: 'POST', url: URL }).flush({}, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(text()).toContain('Could not unsubscribe');
    expect(button()!.disabled).toBe(false);
  });

  it('explains an invalid link', () => {
    create('forged');
    http
      .expectOne(`${URL}?token=forged`)
      .flush(
        { error: 'This unsubscribe link is invalid.' },
        { status: 400, statusText: 'Bad Request' },
      );
    fixture.detectChanges();
    expect(text()).toContain('This unsubscribe link is invalid or incomplete');
    expect(button()).toBeNull();
  });

  it('needs no request without a token', () => {
    create(null);
    http.expectNone(URL);
    expect(text()).toContain('This unsubscribe link is invalid or incomplete');
  });
});
