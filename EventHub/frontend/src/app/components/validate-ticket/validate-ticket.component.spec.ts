import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { throwError } from 'rxjs';
import { ValidateTicketComponent } from './validate-ticket.component';
import { EventService } from '../../services/event.service';
import { I18nTestingModule } from '../../i18n/testing';

function render(failure: unknown) {
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, ValidateTicketComponent],
    providers: [
      provideRouter([]),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: { get: () => 'ticket-uuid' } } },
      },
      { provide: EventService, useValue: { checkIn: vi.fn(() => throwError(() => failure)) } },
    ],
  });
  const fixture = TestBed.createComponent(ValidateTicketComponent);
  fixture.detectChanges();
  return (fixture.nativeElement as HTMLElement).textContent || '';
}

describe('ValidateTicketComponent errors', () => {
  it('shows the server reason when the ticket is rejected (4xx)', () => {
    const text = render({ status: 400, error: { error: 'Ticket already cancelled' } });
    expect(text).toContain('Ticket already cancelled');
  });

  it('falls back to the domain message when a 4xx has no usable body', () => {
    expect(render({ status: 400, error: null })).toContain('Validation failed.');
  });

  it('says the service is unavailable on a 500, never the server text', () => {
    const text = render({ status: 500, error: { error: 'Traceback (most recent call last)' } });
    expect(text).toContain('The service is temporarily unavailable. Try again in a minute.');
    expect(text).not.toContain('Traceback');
    expect(text).not.toContain('Validation failed.');
  });

  it('says there is no connection when the request never reached the server', () => {
    const text = render({ status: 0, error: new ProgressEvent('error') });
    expect(text).toContain('No connection to the server.');
  });
});
