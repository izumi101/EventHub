import { TestBed, type ComponentFixture } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { NotificationPreferencesComponent } from './notification-preferences.component';
import type { NotificationPreferences } from '../../services/notification-preferences.service';
import { ToastService } from '../../services/toast.service';
import { environment } from '../../../environments/environment';

const URL = `${environment.apiUrl}/auth/profile/notifications/`;

function prefs(reminderOn = true): NotificationPreferences {
  return {
    email_address: 'alice@example.com',
    types: [
      {
        type: 'event_reminder',
        label: 'Event reminder',
        description: 'A reminder 24 hours before an event.',
        email_enabled: reminderOn,
        email_optional: true,
      },
      {
        type: 'event_cancelled',
        label: 'Event cancelled',
        description: 'An event you have a ticket for was cancelled.',
        email_enabled: true,
        email_optional: false,
      },
    ],
  };
}

describe('NotificationPreferencesComponent', () => {
  let fixture: ComponentFixture<NotificationPreferencesComponent>;
  let http: HttpTestingController;
  let toast: { success: ReturnType<typeof vi.fn>; error: ReturnType<typeof vi.fn> };

  const root = (): HTMLElement => fixture.nativeElement as HTMLElement;
  const toggles = (): HTMLInputElement[] => Array.from(root().querySelectorAll('input.toggle'));

  beforeEach(() => {
    toast = { success: vi.fn(), error: vi.fn() };
    TestBed.configureTestingModule({
      imports: [NotificationPreferencesComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ToastService, useValue: toast },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(NotificationPreferencesComponent);
    fixture.detectChanges();
    http.expectOne(URL).flush(prefs());
    fixture.detectChanges();
  });

  afterEach(() => http.verify());

  it('lists every type, with mandatory emails locked on', () => {
    const [reminder, cancelled] = toggles();
    expect(root().textContent).toContain('alice@example.com');
    expect(reminder.checked).toBe(true);
    expect(reminder.disabled).toBe(false);
    expect(cancelled.checked).toBe(true);
    expect(cancelled.disabled).toBe(true);
    expect(root().textContent).toContain('Always emailed.');
  });

  it('saves a switch with PATCH of that type only', () => {
    const [reminder] = toggles();
    reminder.click();
    const req = http.expectOne(URL);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ email: { event_reminder: false } });
    req.flush(prefs(false));
    fixture.detectChanges();
    expect(toggles()[0].checked).toBe(false);
    expect(toast.success).toHaveBeenCalled();
  });

  it('puts the switch back when saving fails', () => {
    const [reminder] = toggles();
    reminder.click();
    http
      .expectOne(URL)
      .flush(
        { email: ['These notification emails cannot be switched: event_reminder.'] },
        { status: 400, statusText: 'Bad Request' },
      );
    fixture.detectChanges();
    expect(toggles()[0].checked).toBe(true);
    expect(toast.error).toHaveBeenCalledWith(
      'These notification emails cannot be switched: event_reminder.',
    );
  });
});
