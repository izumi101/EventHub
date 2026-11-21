import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { throwError } from 'rxjs';
import { RegisterComponent } from './register.component';
import { AuthService } from '../../services/auth.service';
import { I18nTestingModule } from '../../i18n/testing';

function setup(failure: unknown) {
  const auth = {
    sendRegistrationCode: vi.fn(() => throwError(() => failure)),
    verifyRegistrationCode: vi.fn(() => throwError(() => failure)),
  };
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, RegisterComponent],
    providers: [provideRouter([]), { provide: AuthService, useValue: auth }],
  });
  const cmp = TestBed.createComponent(RegisterComponent).componentInstance;
  return cmp;
}

function failEmailStep(failure: unknown): string[] {
  const cmp = setup(failure);
  cmp.email = 'a@b.co';
  cmp.username = 'alice';
  cmp.nextStep();
  return cmp.errors;
}

function failCodeStep(failure: unknown): string[] {
  const cmp = setup(failure);
  cmp.currentStep = 2;
  cmp.verification_code = '123456';
  cmp.nextStep();
  return cmp.errors;
}

describe('RegisterComponent request errors', () => {
  it('shows the server message for a rejected email (4xx)', () => {
    expect(failEmailStep({ status: 400, error: { error: 'Email already registered' } })).toEqual([
      'Email already registered',
    ]);
  });

  it('keeps the domain message when a 4xx has no usable body', () => {
    expect(failEmailStep({ status: 400, error: null })).toEqual([
      'Failed to send verification code.',
    ]);
  });

  it('says the service is unavailable when sending the code hits a 500', () => {
    const errors = failEmailStep({ status: 500, error: { error: 'smtp exploded' } });
    expect(errors).toEqual(['The service is temporarily unavailable. Try again in a minute.']);
  });

  it('says the service is unavailable when verifying the code hits a 503', () => {
    const errors = failCodeStep({ status: 503, error: null });
    expect(errors).toEqual(['The service is temporarily unavailable. Try again in a minute.']);
  });

  it('shows the server message for a wrong code (4xx)', () => {
    expect(failCodeStep({ status: 400, error: { error: 'Code expired' } })).toEqual([
      'Code expired',
    ]);
  });

  it('reports a dropped connection instead of an invalid code', () => {
    expect(failCodeStep({ status: 0, error: null })).toEqual([
      'No connection to the server. Check your internet and try again.',
    ]);
  });
});
