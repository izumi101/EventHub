import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { PaymentCancelComponent } from './payment-cancel.component';

describe('PaymentCancelComponent', () => {
  function render(): HTMLElement {
    TestBed.configureTestingModule({
      imports: [PaymentCancelComponent],
      providers: [provideRouter([])],
    });
    const fixture = TestBed.createComponent(PaymentCancelComponent);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('tells the buyer nothing was charged and does not claim a confirmed payment', () => {
    const el = render();
    const text = el.textContent;
    expect(el.querySelector('h1')?.textContent).toContain('Payment cancelled');
    expect(text).toContain('No charges were made');
    expect(text).not.toContain('Payment confirmed');
  });

  it('offers a way back to the held registration and to the event list', () => {
    const hrefs = Array.from(render().querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/my-registrations');
    expect(hrefs).toContain('/');
  });
});
