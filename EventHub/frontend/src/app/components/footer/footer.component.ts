import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { LucideAngularModule, Twitter, Linkedin, Github, ChevronUp, Mail, X } from 'lucide-angular';
import { AuthService } from '../../services/auth.service';
import { SearchService } from '../../services/search.service';

@Component({
  selector: 'app-footer',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule, LucideAngularModule],
  template: `
    <footer class="bg-card border-t border-border mt-auto">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">

        <!-- Newsletter Section -->
        <div class="bg-gradient-to-r from-primary/10 via-primary/5 to-transparent rounded-2xl border border-primary/20 p-6 sm:p-8 mb-12">
          <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
            <div>
              <h3 class="text-foreground font-semibold text-lg mb-1">Stay in the loop</h3>
              <p class="text-muted-foreground text-sm">Get notified about the hottest events in your city.</p>
            </div>
            <form (submit)="subscribeNewsletter($event)" class="flex gap-2 w-full sm:w-auto">
              <div class="flex items-center gap-2 bg-background border border-border rounded-xl px-4 py-2.5 flex-1 sm:w-64">
                <lucide-icon [img]="icons.Mail" class="w-4 h-4 text-muted-foreground flex-shrink-0"></lucide-icon>
                <input
                  type="email"
                  [(ngModel)]="newsletterEmail"
                  name="email"
                  placeholder="your@email.com"
                  required
                  class="bg-transparent text-foreground placeholder:text-muted-foreground outline-none text-sm flex-1 w-full"
                />
              </div>
              <button
                type="submit"
                class="bg-primary text-primary-foreground px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-primary/90 transition-colors whitespace-nowrap"
              >
                {{ newsletterSubmitted ? '✓ Subscribed!' : 'Subscribe' }}
              </button>
            </form>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-5 gap-8">
          
          <div class="col-span-1 md:col-span-2">
            <a routerLink="/" class="flex items-center gap-2 mb-4 group w-fit">
              <img src="assets/logo.png" alt="EventHub" class="w-8 h-8 rounded-lg object-cover transition-transform group-hover:scale-110" style="background:#12101a" />
              <span class="text-foreground font-semibold text-lg tracking-tight">EventHub</span>
            </a>
            <p class="text-muted-foreground text-sm leading-relaxed max-w-xs">
              Built for event lovers, by event lovers. Discover, book, and enjoy unforgettable experiences worldwide.
            </p>
            <div class="flex items-center gap-4 mt-6">
              <a href="https://twitter.com" target="_blank" rel="noopener noreferrer" class="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-[#1DA1F2] transition-all" aria-label="Twitter">
                <lucide-icon [img]="icons.Twitter" class="w-5 h-5"></lucide-icon>
              </a>
              <a href="https://linkedin.com" target="_blank" rel="noopener noreferrer" class="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-[#0A66C2] transition-all" aria-label="LinkedIn">
                <lucide-icon [img]="icons.Linkedin" class="w-5 h-5"></lucide-icon>
              </a>
              <a href="https://github.com" target="_blank" rel="noopener noreferrer" class="w-10 h-10 rounded-full bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-[#333] transition-all" aria-label="GitHub">
                <lucide-icon [img]="icons.Github" class="w-5 h-5"></lucide-icon>
              </a>
            </div>
          </div>
          
          <!-- Discover Column -->
          <div>
            <h3 class="text-foreground font-semibold mb-4">Discover</h3>
            <ul class="space-y-3">
              <li><a (click)="navigateToCategory('Concert')" class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer">Concerts</a></li>
              <li><a (click)="navigateToCategory('Festival')" class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer">Festivals</a></li>
              <li><a (click)="navigateToCategory('Conference')" class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer">Conferences</a></li>
              <li><a (click)="navigateToCategory('Workshop')" class="text-muted-foreground hover:text-foreground text-sm transition-colors block w-fit cursor-pointer">Workshops</a></li>
            </ul>
          </div>

          <!-- Organizer Column -->
          <div>
            <h3 class="text-sm font-semibold text-foreground mb-4">Organizer</h3>
            <ul class="space-y-3">
              <li><a (click)="navigateAuthenticated('/organizer/dashboard')" class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer">Dashboard</a></li>
              <li><a (click)="navigateAuthenticated('/create-event')" class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer">Create Event</a></li>
              <li><a (click)="navigateAuthenticated('/my-events')" class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer">My Events</a></li>
            </ul>
          </div>

          <!-- Support Column -->
          <div>
            <h3 class="text-sm font-semibold text-foreground mb-4">Support</h3>
            <ul class="space-y-3">
              <li><a href="mailto:eventhub.supporting@gmail.com?subject=Help%20Request" class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit">Help Center</a></li>
              <li><a href="mailto:eventhub.supporting@gmail.com?subject=General%20Inquiry" class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit">Contact Us</a></li>
              <li><a href="mailto:eventhub.supporting@gmail.com?subject=Refund%20Request" class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit">Refunds</a></li>
              <li><a (click)="openModal('faq')" class="text-sm text-muted-foreground hover:text-foreground transition-colors block w-fit cursor-pointer">FAQ</a></li>
            </ul>
          </div>
        </div>

        <!-- Bottom Bar -->
        <div class="mt-12 pt-8 border-t border-border flex flex-col sm:flex-row items-center justify-between gap-4">
          <p class="text-sm text-muted-foreground">
            © 2026 EventHub. All rights reserved.
          </p>
          <div class="flex items-center gap-6">
            <a (click)="openModal('terms')" class="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">Terms of Service</a>
            <a (click)="openModal('privacy')" class="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">Privacy Policy</a>
            <span class="text-xs text-muted-foreground opacity-50">|</span>
            <span class="text-xs text-primary font-medium tracking-wide">Made with ♥ in Almaty</span>
          </div>
        </div>
      </div>

      <!-- Back to Top Button -->
      <button
        *ngIf="showBackToTop"
        (click)="scrollToTop()"
        class="fixed bottom-6 right-6 w-11 h-11 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-lg shadow-primary/25 hover:bg-primary/90 transition-all z-40 animate-fade-in"
        aria-label="Back to top"
      >
        <lucide-icon [img]="icons.ChevronUp" class="w-5 h-5"></lucide-icon>
      </button>

      <!-- Modal Overlay (Terms / Privacy / FAQ) -->
      <div
        *ngIf="activeModal"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in"
        (click)="closeModal()"
      >
        <div
          class="bg-card border border-border rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-y-auto shadow-2xl"
          (click)="$event.stopPropagation()"
        >
          <!-- Modal Header -->
          <div class="sticky top-0 bg-card border-b border-border px-6 py-4 flex items-center justify-between rounded-t-2xl z-10">
            <h2 class="text-lg font-semibold text-foreground">{{ modalTitle }}</h2>
            <button (click)="closeModal()" class="w-8 h-8 rounded-lg bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors">
              <lucide-icon [img]="icons.X" class="w-4 h-4"></lucide-icon>
            </button>
          </div>

          <!-- Terms of Service Content -->
          <div *ngIf="activeModal === 'terms'" class="px-6 py-6 space-y-6 text-sm text-muted-foreground leading-relaxed">
            <p class="text-foreground font-medium">Last updated: April 15, 2026</p>

            <div>
              <h3 class="text-foreground font-semibold mb-2">1. Acceptance of Terms</h3>
              <p>By accessing and using EventHub, you agree to be bound by these Terms of Service and all applicable laws and regulations. If you do not agree with any of these terms, you are prohibited from using or accessing this site.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">2. Use License</h3>
              <p>Permission is granted to temporarily access the materials on EventHub for personal, non-commercial transitory viewing only. This license shall automatically terminate if you violate any of these restrictions.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">3. Event Listings</h3>
              <p>EventHub acts as a marketplace connecting event organizers with attendees. We do not guarantee the accuracy, completeness, or usefulness of any event listing. Event organizers are solely responsible for the accuracy of their listings.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">4. Ticket Purchases</h3>
              <p>All ticket sales are final unless the event is cancelled by the organizer. Refund policies are set by individual event organizers. EventHub facilitates the transaction but is not responsible for refund disputes between buyers and organizers.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">5. Account Responsibility</h3>
              <p>You are responsible for maintaining the confidentiality of your account credentials and for all activities that occur under your account. You must notify EventHub immediately of any unauthorized use of your account.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">6. Limitation of Liability</h3>
              <p>EventHub shall not be held liable for any damages arising from the use or inability to use the materials on the platform, even if EventHub has been notified orally or in writing of the possibility of such damage.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">7. Contact</h3>
              <p>For questions about these Terms, contact us at <a href="mailto:eventhub.supporting@gmail.com" class="text-primary hover:underline">eventhub.supporting@gmail.com</a>.</p>
            </div>
          </div>

          <!-- Privacy Policy Content -->
          <div *ngIf="activeModal === 'privacy'" class="px-6 py-6 space-y-6 text-sm text-muted-foreground leading-relaxed">
            <p class="text-foreground font-medium">Last updated: April 15, 2026</p>

            <div>
              <h3 class="text-foreground font-semibold mb-2">1. Information We Collect</h3>
              <p>We collect information you provide directly to us, such as when you create an account, purchase tickets, or contact us for support. This includes your name, email address, and payment information.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">2. How We Use Your Information</h3>
              <p>We use the information we collect to provide, maintain, and improve our services, process transactions, send you confirmations and updates about events you're registered for, and respond to your comments and questions.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">3. Information Sharing</h3>
              <p>We do not sell, trade, or otherwise transfer your personal information to outside parties. This does not include trusted third parties who assist us in operating our platform, conducting our business, or serving you, as long as those parties agree to keep this information confidential.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">4. Data Security</h3>
              <p>We implement industry-standard security measures to protect your personal information. All sensitive data is encrypted using SSL technology. However, no method of transmission over the Internet is 100% secure.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">5. Cookies</h3>
              <p>We use cookies to enhance your experience on our platform. You can choose to disable cookies through your browser settings, but this may affect the functionality of certain features.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">6. Your Rights</h3>
              <p>You have the right to access, correct, or delete your personal data at any time. You can manage your account information from your profile settings or by contacting our support team.</p>
            </div>

            <div>
              <h3 class="text-foreground font-semibold mb-2">7. Contact</h3>
              <p>For privacy-related inquiries, contact us at <a href="mailto:eventhub.supporting@gmail.com" class="text-primary hover:underline">eventhub.supporting@gmail.com</a>.</p>
            </div>
          </div>

          <!-- FAQ Content -->
          <div *ngIf="activeModal === 'faq'" class="px-6 py-6 space-y-5 text-sm text-muted-foreground leading-relaxed">
            <div *ngFor="let faq of faqItems" class="border-b border-border pb-5 last:border-b-0">
              <button
                (click)="faq.open = !faq.open"
                class="w-full flex items-center justify-between text-foreground font-semibold text-left gap-4"
              >
                <span>{{ faq.question }}</span>
                <span class="text-primary text-lg flex-shrink-0 transition-transform" [class.rotate-45]="faq.open">+</span>
              </button>
              <p *ngIf="faq.open" class="mt-3 text-muted-foreground animate-fade-in">{{ faq.answer }}</p>
            </div>
          </div>
        </div>
      </div>
    </footer>
  `,
  styles: [`
    .animate-fade-in {
      animation: fadeIn 0.2s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .rotate-45 {
      transform: rotate(45deg);
    }
  `]
})
export class FooterComponent {
  readonly icons = { Twitter, Linkedin, Github, ChevronUp, Mail, X };

  activeModal: 'terms' | 'privacy' | 'faq' | null = null;
  modalTitle = '';
  showBackToTop = false;
  newsletterEmail = '';
  newsletterSubmitted = false;

  faqItems = [
    { question: 'How do I purchase tickets?', answer: 'Browse events on the homepage, click on an event you like, and follow the checkout process to secure your tickets. You\'ll receive a confirmation email with your digital ticket.', open: false },
    { question: 'Can I get a refund?', answer: 'Refund policies are set by individual event organizers. If an event is cancelled, you will automatically receive a full refund. For other cases, contact the organizer directly or email eventhub.supporting@gmail.com.', open: false },
    { question: 'How do I become an organizer?', answer: 'Organizer accounts are created by EventHub administrators. Email eventhub.supporting@gmail.com to request one — once it\'s set up, you can create and manage events.', open: false },
    { question: 'Is my payment information secure?', answer: 'Yes. We use industry-standard SSL encryption and never store your full payment details on our servers. All transactions are processed through secure third-party payment providers.', open: false },
    { question: 'How do I contact support?', answer: 'You can reach our support team by emailing eventhub.supporting@gmail.com. We typically respond within 24 hours on business days.', open: false },
    { question: 'Can I transfer my ticket to someone else?', answer: 'Ticket transfer policies depend on the event organizer\'s settings. Check the event details page or contact the organizer for transfer options.', open: false },
  ];

  constructor(
    private router: Router,
    private authService: AuthService,
    private searchService: SearchService
  ) {
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
    this.router.navigate(['/']).then(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /** Navigate to authenticated route, redirect to login if not logged in */
  navigateAuthenticated(path: string): void {
    if (this.authService.isLoggedIn) {
      this.router.navigate([path]);
    } else {
      this.router.navigate(['/login']);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /** Open a legal/info modal */
  openModal(type: 'terms' | 'privacy' | 'faq'): void {
    this.activeModal = type;
    const titles: Record<string, string> = {
      terms: 'Terms of Service',
      privacy: 'Privacy Policy',
      faq: 'Frequently Asked Questions'
    };
    this.modalTitle = titles[type];
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

  /** Handle newsletter subscription */
  subscribeNewsletter(event: Event | any): void {
    event.preventDefault();
    if (!this.newsletterEmail) return;
    this.newsletterSubmitted = true;
    // Reset after 3 seconds
    setTimeout(() => {
      this.newsletterSubmitted = false;
      this.newsletterEmail = '';
    }, 3000);
  }
}
