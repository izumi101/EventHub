import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { LanguageService } from '../../i18n/language.service';
import { I18nTestingModule } from '../../i18n/testing';
import type { ReviewsSummary } from '../../services/organizer-dashboard.service';
import { DashboardReviewsComponent } from './dashboard-reviews.component';
import { recentReview, reviewsSummary } from './dashboard.testing';

const URL = `${environment.apiUrl}/organizer/reviews/`;

function setup() {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [I18nTestingModule, DashboardReviewsComponent],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(DashboardReviewsComponent);
  fixture.detectChanges();
  const el = fixture.nativeElement as HTMLElement;
  const q = (testId: string) => el.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  const all = (testId: string) =>
    Array.from(el.querySelectorAll<HTMLElement>(`[data-testid="${testId}"]`));
  const text = (testId: string) => q(testId)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
  const request = () => http.expectOne((r) => r.url === URL);
  const answer = (summary: ReviewsSummary) => {
    request().flush(summary);
    fixture.detectChanges();
  };
  return { http, fixture, el, q, all, text, request, answer };
}

const NO_REVIEWS: ReviewsSummary = {
  count: 0,
  average: null,
  distribution: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 },
  recent: [],
};

describe('DashboardReviewsComponent', () => {
  describe('states', () => {
    it('shows a skeleton while loading', () => {
      const { q, request } = setup();
      expect(q('reviews-loading')).not.toBeNull();
      expect(q('reviews-loading')!.innerHTML).toContain('motion-reduce:animate-none');
      request();
    });

    it('says "No reviews yet" when nobody has reviewed an event, with no stars or bars', () => {
      const { q, text, answer } = setup();
      answer(NO_REVIEWS);
      expect(text('reviews-empty')).toContain('No reviews yet');
      expect(q('reviews-average')).toBeNull();
      expect(q('reviews-distribution')).toBeNull();
      expect(q('reviews-recent')).toBeNull();
      expect(q('reviews')!.querySelector('[role="img"]')).toBeNull();
    });

    it('shows an error with a retry, and the reviews once it works', () => {
      const { q, request, answer, fixture } = setup();
      request().flush({}, { status: 500, statusText: 'Server Error' });
      fixture.detectChanges();
      expect(q('reviews-error')!.getAttribute('role')).toBe('alert');
      q('reviews-error')!.querySelector('button')!.click();
      fixture.detectChanges();
      expect(q('reviews-loading')).not.toBeNull();
      answer(reviewsSummary());
      expect(q('reviews-error')).toBeNull();
      expect(q('reviews-average')).not.toBeNull();
    });
  });

  describe('average', () => {
    it('shows one decimal, the stars as an image named "4.4 out of 5", and the count', () => {
      const { q, text, answer } = setup();
      answer(reviewsSummary({ average: 4.42, count: 12 }));
      expect(text('reviews-average')).toBe('4.4');
      const stars = q('reviews')!.querySelector('[role="img"]')!;
      expect(stars.getAttribute('aria-label')).toBe('4.4 out of 5');
      expect(text('reviews-count')).toBe('12 reviews');
    });

    it('fills the stars to the exact average', () => {
      const { q, answer } = setup();
      answer(reviewsSummary({ average: 4.42 }));
      const fill = q('reviews')!.querySelector<HTMLElement>('[data-testid="stars-fill"]')!;
      expect(parseFloat(fill.style.width)).toBeCloseTo(88.4);
    });

    it('keeps the decimal on a perfect score and uses the singular for one review', () => {
      const { q, text, answer } = setup();
      answer(
        reviewsSummary({
          average: 5,
          count: 1,
          distribution: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 1 },
          recent: [recentReview(1)],
        }),
      );
      expect(text('reviews-average')).toBe('5.0');
      expect(q('reviews')!.querySelector('[role="img"]')!.getAttribute('aria-label')).toBe(
        '5.0 out of 5',
      );
      expect(text('reviews-count')).toBe('1 review');
    });

    it('uses the decimal comma and the plural of the language', async () => {
      const { q, text, answer, fixture } = setup();
      answer(reviewsSummary({ average: 4.42, count: 12 }));
      await TestBed.inject(LanguageService).setLang('ru');
      fixture.detectChanges();
      expect(text('reviews-average')).toBe('4,4');
      expect(q('reviews')!.querySelector('[role="img"]')!.getAttribute('aria-label')).toBe(
        '4,4 из 5',
      );
      expect(text('reviews-count')).toBe('12 отзывов');
    });
  });

  describe('distribution', () => {
    it('lists the ratings from 5 to 1 with their counts', () => {
      const { all, answer } = setup();
      answer(reviewsSummary());
      const rows = all('reviews-row');
      expect(rows.map((r) => r.querySelector('.sr-only')!.textContent.trim())).toEqual([
        '5 out of 5: 8',
        '4 out of 5: 2',
        '3 out of 5: 1',
        '2 out of 5: 1',
        '1 out of 5: 0',
      ]);
      expect(all('reviews-row-count').map((c) => c.textContent.trim())).toEqual([
        '8',
        '2',
        '1',
        '1',
        '0',
      ]);
    });

    it('sizes each bar by its share of all reviews', () => {
      const { all, answer } = setup();
      answer(reviewsSummary());
      const widths = all('reviews-bar').map((b) => parseFloat(b.style.width));
      expect(widths[0]).toBeCloseTo((8 / 12) * 100);
      expect(widths[1]).toBeCloseTo((2 / 12) * 100);
      expect(widths[4]).toBe(0);
    });
  });

  describe('latest reviews', () => {
    it('shows author, rating, comment and event, with the event linked', () => {
      const { all, q, answer } = setup();
      answer(
        reviewsSummary({
          recent: [
            recentReview(1, {
              author: 'Aigerim K.',
              rating: 4,
              comment: 'Lovely venue',
              event_id: 21,
              event_title: 'Jazz night',
            }),
          ],
        }),
      );
      const [review] = all('review');
      expect(review.querySelector('[data-testid="review-author"]')!.textContent.trim()).toBe(
        'Aigerim K.',
      );
      expect(review.querySelector('[role="img"]')!.getAttribute('aria-label')).toBe('4 out of 5');
      expect(review.querySelector('[data-testid="review-comment"]')!.textContent.trim()).toBe(
        'Lovely venue',
      );
      const link = review.querySelector('[data-testid="review-event"]')!;
      expect(link.textContent.trim()).toBe('Jazz night');
      expect(link.getAttribute('href')).toBe('/events/21');
      expect(q('reviews-recent')).not.toBeNull();
    });

    it('writes the age of a review relative to now, with the exact time to hand', () => {
      const { q, answer } = setup();
      answer(reviewsSummary());
      const time = q('review-time')!;
      expect(time.textContent.trim()).toMatch(/^2 hr\. ago$/);
      expect(time.getAttribute('datetime')).toBeTruthy();
      expect(time.getAttribute('title')).toBeTruthy();
    });

    it('shows a review without a comment as just a rating', () => {
      const { all, answer } = setup();
      answer(reviewsSummary({ recent: [recentReview(1, { comment: '' })] }));
      const [review] = all('review');
      expect(review.querySelector('[data-testid="review-comment"]')).toBeNull();
      expect(review.querySelector('[data-testid="review-toggle"]')).toBeNull();
    });

    it('keeps a short comment whole, with no "More"', () => {
      const { q, answer } = setup();
      answer(reviewsSummary({ recent: [recentReview(1, { comment: 'Short and sweet' })] }));
      expect(q('review-toggle')).toBeNull();
    });

    it('clamps a long comment to 3 lines and expands it on "More"', () => {
      const { q, fixture, answer } = setup();
      const long = 'It was a wonderful evening with great music. '.repeat(8);
      answer(reviewsSummary({ recent: [recentReview(1, { comment: long })] }));
      const comment = q('review-comment')!;
      const toggle = q('review-toggle') as HTMLButtonElement;
      expect(comment.classList).toContain('line-clamp-3');
      expect(toggle.textContent.trim()).toBe('More');
      expect(toggle.getAttribute('aria-expanded')).toBe('false');
      expect(toggle.getAttribute('aria-controls')).toBe(comment.id);

      toggle.click();
      fixture.detectChanges();
      expect(comment.classList).not.toContain('line-clamp-3');
      expect(toggle.textContent.trim()).toBe('Less');
      expect(toggle.getAttribute('aria-expanded')).toBe('true');

      toggle.click();
      fixture.detectChanges();
      expect(comment.classList).toContain('line-clamp-3');
    });

    it('offers "More" for a comment of many short lines, and expands only that review', () => {
      const { all, fixture, answer } = setup();
      answer(
        reviewsSummary({
          recent: [
            recentReview(1, { comment: 'a\nb\nc\nd' }),
            recentReview(2, { comment: 'x'.repeat(200) }),
          ],
        }),
      );
      const toggles = all('review-toggle') as HTMLButtonElement[];
      expect(toggles).toHaveLength(2);
      toggles[0].click();
      fixture.detectChanges();
      const comments = all('review-comment');
      expect(comments[0].classList).not.toContain('line-clamp-3');
      expect(comments[1].classList).toContain('line-clamp-3');
    });

    it('breaks a long unbroken word instead of overflowing the card', () => {
      const { q, answer } = setup();
      answer(reviewsSummary({ recent: [recentReview(1, { comment: 'w'.repeat(500) })] }));
      expect(q('review-comment')!.classList).toContain('break-words');
    });
  });

  describe('privacy', () => {
    it('shows only the name the server sent, and no email address anywhere', () => {
      const { el, answer } = setup();
      answer(reviewsSummary());
      expect(el.textContent).not.toMatch(/\S+@\S+/);
    });

    it('does not show an email address even if one slipped into the author', () => {
      const { all, el, answer } = setup();
      answer(
        reviewsSummary({
          recent: [
            recentReview(1, { author: 'dias.a@example.com' }),
            recentReview(2, { author: '  ' }),
          ],
        }),
      );
      expect(all('review-author').map((a) => a.textContent.trim())).toEqual([
        'Anonymous',
        'Anonymous',
      ]);
      expect(el.textContent).not.toContain('@');
      expect(el.textContent).not.toContain('example.com');
    });
  });
});
