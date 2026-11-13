import { Component, inject } from '@angular/core';
import { Router, RouterModule } from '@angular/router';
import { LucideAngularModule, ChevronUp, X } from 'lucide-angular';
import { AuthService } from '../../services/auth.service';
import { SearchService } from '../../services/search.service';
import { DialogDirective } from '../../directives/dialog.directive';
import { GithubIcon, LinkedinIcon, TwitterIcon } from './brand-icons';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';

@Component({
  selector: 'app-footer',
  standalone: true,
  imports: [DialogDirective, RouterModule, LucideAngularModule, TranslocoPipe, LocalDatePipe],
  template: `
    <footer class="bg-card border-t border-border mt-auto">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div class="grid grid-cols-1 md:grid-cols-5 gap-8">
          <div class="col-span-1 md:col-span-2">
            <a routerLink="/" class="flex items-center gap-2 mb-4 group w-fit">
              <img
                src="assets/logo.png"
                alt="EventHub"
                class="w-8 h-8 rounded-lg object-cover transition-transform group-hover:scale-110"
                style="background:#12101a"
              />
              <span class="text-foreground font-semibold text-lg tracking-tight">EventHub</span>
            </a>
            <p class="text-muted-foreground text-sm leading-relaxed max-w-xs">
              {{ 'footer.tagline' | transloco }}
            </p>
            <div class="flex items-center gap-4 mt-6">
              <a
                href="https://twitter.com"
                target="_blank"
                rel="noopener noreferrer"
                class="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-[#1DA1F2] transition-all"
                aria-label="Twitter"
              >
                <lucide-icon [img]="icons.Twitter" class="w-5 h-5" />
              </a>
              <a
                href="https://linkedin.com"
                target="_blank"
                rel="noopener noreferrer"
                class="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-[#0A66C2] transition-all"
                aria-label="LinkedIn"
              >
                <lucide-icon [img]="icons.Linkedin" class="w-5 h-5" />
              </a>
              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                class="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-[#333] transition-all"
                aria-label="GitHub"
              >
                <lucide-icon [img]="icons.Github" class="w-5 h-5" />
              </a>
            </div>
          </div>

          <!-- Discover Column -->
          <div>
            <h3 class="text-foreground font-semibold mb-4">{{ 'footer.discover' | transloco }}</h3>
            <ul class="space-y-3">
              <li>
                <button
                  type="button"
                  (click)="navigateToCategory('Concert')"
                  class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer"
                >
                  {{ 'footer.concerts' | transloco }}
                </button>
              </li>
              <li>
                <button
                  type="button"
                  (click)="navigateToCategory('Festival')"
                  class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer"
                >
                  {{ 'footer.festivals' | transloco }}
                </button>
              </li>
              <li>
                <button
                  type="button"
                  (click)="navigateToCategory('Conference')"
                  class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer"
                >
                  {{ 'footer.conferences' | transloco }}
                </button>
              </li>
              <li>
                <button
                  type="button"
                  (click)="navigateToCategory('Workshop')"
                  class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer"
                >
                  {{ 'footer.workshops' | transloco }}
                </button>
              </li>
            </ul>
          </div>

          <!-- Organizer Column -->
          <div>
            <h3 class="text-sm font-semibold text-foreground mb-4">
              {{ 'footer.organizer' | transloco }}
            </h3>
            <ul class="space-y-3">
              <li>
                <button
                  type="button"
                  (click)="navigateAuthenticated('/organizer/dashboard')"
                  class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer"
                >
                  {{ 'nav.dashboard' | transloco }}
                </button>
              </li>
              <li>
                <button
                  type="button"
                  (click)="navigateAuthenticated('/create-event')"
                  class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer"
                >
                  {{ 'nav.createEvent' | transloco }}
                </button>
              </li>
              <li>
                <button
                  type="button"
                  (click)="navigateAuthenticated('/my-events')"
                  class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer"
                >
                  {{ 'nav.myEvents' | transloco }}
                </button>
              </li>
            </ul>
          </div>

          <!-- Support Column -->
          <div>
            <h3 class="text-sm font-semibold text-foreground mb-4">
              {{ 'footer.support' | transloco }}
            </h3>
            <ul class="space-y-3">
              <li>
                <a
                  href="mailto:eventhub.supporting@gmail.com?subject=Help%20Request"
                  class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit"
                  >{{ 'footer.helpCenter' | transloco }}</a
                >
              </li>
              <li>
                <a
                  href="mailto:eventhub.supporting@gmail.com?subject=General%20Inquiry"
                  class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit"
                  >{{ 'footer.contactUs' | transloco }}</a
                >
              </li>
              <li>
                <a
                  href="mailto:eventhub.supporting@gmail.com?subject=Refund%20Request"
                  class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit"
                  >{{ 'footer.refunds' | transloco }}</a
                >
              </li>
              <li>
                <button
                  type="button"
                  (click)="openModal('faq')"
                  class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer"
                >
                  {{ 'footer.faq.title' | transloco }}
                </button>
              </li>
            </ul>
          </div>
        </div>

        <!-- Bottom Bar -->
        <div
          class="mt-12 pt-8 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4"
        >
          <p class="text-sm text-muted-foreground">
            {{ 'footer.rights' | transloco: { year: 2026 } }}
          </p>
          <div class="flex items-center gap-6">
            <button
              type="button"
              (click)="openModal('terms')"
              class="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              {{ 'footer.termsTitle' | transloco }}
            </button>
            <button
              type="button"
              (click)="openModal('privacy')"
              class="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              {{ 'footer.privacyTitle' | transloco }}
            </button>
            <span class="text-xs text-muted-foreground opacity-50">|</span>
            <span class="text-xs text-primary font-medium tracking-wide">{{
              'footer.madeIn' | transloco
            }}</span>
          </div>
        </div>
      </div>

      <!-- Back to Top Button -->
      @if (showBackToTop) {
        <button
          (click)="scrollToTop()"
          class="fixed bottom-6 right-6 w-11 h-11 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-lg shadow-primary/25 hover:bg-primary/90 transition-all z-40 animate-fade-in"
          [attr.aria-label]="'footer.backToTop' | transloco"
        >
          <lucide-icon [img]="icons.ChevronUp" class="w-5 h-5" />
        </button>
      }

      <!-- Modal Overlay (Terms / Privacy / FAQ) -->
      @if (activeModal) {
        <div
          class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in"
        >
          <div
            class="bg-card border border-border rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto shadow-2xl"
            appDialog
            dismissOnBackdrop
            (dismiss)="closeModal()"
          >
            <!-- Modal Header -->
            <div
              class="sticky top-0 bg-card border-b border-border px-6 py-4 flex items-center justify-between rounded-t-2xl z-10"
            >
              <h2 class="text-lg font-semibold text-foreground">
                {{ 'footer.' + activeModal + 'Title' | transloco }}
              </h2>
              <button
                (click)="closeModal()"
                [attr.aria-label]="'common.close' | transloco"
                class="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
              >
                <lucide-icon [img]="icons.X" class="w-4 h-4" />
              </button>
            </div>

            <!-- Terms of Service / Privacy Policy content -->
            @if (activeModal === 'terms' || activeModal === 'privacy') {
              <div class="px-6 py-6 space-y-6 text-sm text-muted-foreground leading-relaxed">
                <p class="text-foreground font-medium">
                  {{
                    'footer.lastUpdated' | transloco: { date: (legalDate | localDate: 'longDate') }
                  }}
                </p>

                @for (n of legalSections; track n) {
                  <div>
                    <h3 class="text-foreground font-semibold mb-2">
                      {{ n }}. {{ 'footer.' + activeModal + '.s' + n + 'Title' | transloco }}
                    </h3>
                    <p>{{ 'footer.' + activeModal + '.s' + n + 'Body' | transloco }}</p>
                  </div>
                }

                <div>
                  <h3 class="text-foreground font-semibold mb-2">
                    7. {{ 'footer.contactTitle' | transloco }}
                  </h3>
                  <p>
                    {{ 'footer.' + activeModal + '.contactBody' | transloco }}
                    <a
                      href="mailto:eventhub.supporting@gmail.com"
                      class="text-primary hover:underline"
                      >eventhub.supporting@gmail.com</a
                    >.
                  </p>
                </div>
              </div>
            }

            <!-- FAQ Content -->
            @if (activeModal === 'faq') {
              <div class="px-6 py-6 space-y-5 text-sm text-muted-foreground leading-relaxed">
                @for (faq of faqItems; track faq.n) {
                  <div class="border-b border-border pb-5 last:border-b-0">
                    <button
                      (click)="faq.open = !faq.open"
                      class="w-full flex items-center justify-between text-foreground font-semibold text-left gap-4"
                    >
                      <span>{{ 'footer.faq.q' + faq.n | transloco }}</span>
                      <span
                        class="text-primary text-lg flex-shrink-0 transition-transform"
                        [class.rotate-45]="faq.open"
                        >+</span
                      >
                    </button>
                    @if (faq.open) {
                      <p class="mt-3 text-muted-foreground animate-fade-in">
                        {{ 'footer.faq.a' + faq.n | transloco }}
                      </p>
                    }
                  </div>
                }
              </div>
            }
          </div>
        </div>
      }
    </footer>
  `,
  styles: [
    `
      .animate-fade-in {
        animation: fadeIn 0.2s ease-out;
      }
      @keyframes fadeIn {
        from {
          opacity: 0;
          transform: translateY(8px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
      .rotate-45 {
        transform: rotate(45deg);
      }
    `,
  ],
})
export class FooterComponent {
  private router = inject(Router);
  private authService = inject(AuthService);
  private searchService = inject(SearchService);

  readonly icons = {
    Twitter: TwitterIcon,
    Linkedin: LinkedinIcon,
    Github: GithubIcon,
    ChevronUp,
    X,
  };

  activeModal: 'terms' | 'privacy' | 'faq' | null = null;
  showBackToTop = false;

  /** Questions and answers live in the translation files as `footer.faq.q<n>` / `a<n>`. */
  faqItems = [1, 2, 3, 4, 5, 6].map((n) => ({ n, open: false }));

  /** Legal documents have six numbered sections plus a contact section (rendered separately). */
  readonly legalSections = [1, 2, 3, 4, 5, 6];
  readonly legalDate = '2026-04-15';

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('scroll', () => {
        this.showBackToTop = window.scrollY > 400;
      });
    }
  }

  /** Navigate to home page and filter by category name via SearchService */
  navigateToCategory(categoryName: string): void {
    this.searchService.setSearchQuery(categoryName);
    this.searchService.setSearchLocation('');
    void this.router.navigate(['/']).then(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /** Navigate to authenticated route, redirect to login if not logged in */
  navigateAuthenticated(path: string): void {
    if (this.authService.isLoggedIn) {
      void this.router.navigate([path]);
    } else {
      void this.router.navigate(['/login']);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /** Open a legal/info modal */
  openModal(type: 'terms' | 'privacy' | 'faq'): void {
    this.activeModal = type;
    document.body.style.overflow = 'hidden';
  }

  /** Close the modal */
  closeModal(): void {
    this.activeModal = null;
    document.body.style.overflow = '';
  }

  /** Scroll to top smoothly */
  scrollToTop(): void {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
}
