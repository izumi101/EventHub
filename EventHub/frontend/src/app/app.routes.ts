import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';

import { HomeComponent } from './components/home/home.component';
import { EventDetailComponent } from './components/event-detail/event-detail.component';
import { EventFormComponent } from './components/event-form/event-form.component';
import { LoginComponent } from './components/login/login.component';
import { RegisterComponent } from './components/register/register.component';
import { ProfileComponent } from './components/profile/profile.component';
import { MyEventsComponent } from './components/my-events/my-events.component';
import { MyRegistrationsComponent } from './components/my-registrations/my-registrations.component';
import { PaymentSuccessComponent } from './components/payment-success/payment-success.component';
import { PaymentCancelComponent } from './components/payment-cancel/payment-cancel.component';
import { NotFoundComponent } from './components/not-found/not-found.component';

export const routes: Routes = [
  { path: '', component: HomeComponent, title: 'EventHub — Discover Events' },
  { path: 'events/:id', component: EventDetailComponent, title: 'EventHub — Event Details' },
  { path: 'events/:id/group', loadComponent: () => import('./components/group-booking/group-booking.component').then(m => m.GroupBookingComponent), canActivate: [authGuard], title: 'EventHub — Group Booking' },
  { path: 'booking/:token', loadComponent: () => import('./components/booking-claim/booking-claim.component').then(m => m.BookingClaimComponent), title: 'EventHub — Claim Your Seat' },
  { path: 'create-event', component: EventFormComponent, canActivate: [authGuard], title: 'EventHub — Create Event' },
  { path: 'edit-event/:id', component: EventFormComponent, canActivate: [authGuard], title: 'EventHub — Edit Event' },
  { path: 'login', component: LoginComponent, title: 'EventHub — Sign In' },
  { path: 'forgot-password', loadComponent: () => import('./components/forgot-password/forgot-password.component').then(m => m.ForgotPasswordComponent), title: 'EventHub — Reset Password' },
  { path: 'register', component: RegisterComponent, title: 'EventHub — Create Account' },
  { path: 'profile', component: ProfileComponent, canActivate: [authGuard], title: 'EventHub — Profile' },
  { path: 'favorites', loadComponent: () => import('./components/favorites/favorites.component').then(m => m.FavoritesComponent), canActivate: [authGuard], title: 'EventHub — Favorites' },
  { path: 'my-events', component: MyEventsComponent, canActivate: [authGuard], title: 'EventHub — My Events' },
  { path: 'my-registrations', component: MyRegistrationsComponent, canActivate: [authGuard], title: 'EventHub — My Tickets' },
  { path: 'my-bookings', loadComponent: () => import('./components/my-bookings/my-bookings.component').then(m => m.MyBookingsComponent), canActivate: [authGuard], title: 'EventHub — My Bookings' },
  { path: 'admin/moderation', loadComponent: () => import('./components/admin-moderation/admin-moderation.component').then(m => m.AdminModerationComponent), canActivate: [authGuard], title: 'EventHub — Moderation' },
  { path: 'organizer/dashboard', loadComponent: () => import('./components/dashboard/dashboard.component').then(m => m.DashboardComponent), canActivate: [authGuard], title: 'EventHub — Organizer Dashboard' },
  { path: 'organizer/events/:id/attendees', loadComponent: () => import('./components/attendee-list/attendee-list.component').then(m => m.AttendeeListComponent), canActivate: [authGuard], title: 'EventHub — Attendee List' },
  { path: 'organizer/events/:id/analytics', loadComponent: () => import('./components/event-analytics/event-analytics.component').then(m => m.EventAnalyticsComponent), canActivate: [authGuard], title: 'EventHub — Analytics' },
  { path: 'organizer/events/:id/checkin-lists', loadComponent: () => import('./components/checkin-lists/checkin-lists.component').then(m => m.CheckinListsComponent), canActivate: [authGuard], title: 'EventHub — Check-in Lists' },
  { path: 'organizer/events/:id/waitlist', loadComponent: () => import('./components/event-waitlist/event-waitlist.component').then(m => m.EventWaitlistComponent), canActivate: [authGuard], title: 'EventHub — Waitlist' },
  { path: 'organizer/events/:id/promo-codes', loadComponent: () => import('./components/promo-codes/promo-codes.component').then(m => m.PromoCodesComponent), canActivate: [authGuard], title: 'EventHub — Promo Codes' },
  { path: 'organizer/events/:id/questions', loadComponent: () => import('./components/event-questions/event-questions.component').then(m => m.EventQuestionsComponent), canActivate: [authGuard], title: 'EventHub — Checkout Questions' },
  { path: 'organizer/events/:id/ticket-types', loadComponent: () => import('./components/ticket-types/ticket-types.component').then(m => m.TicketTypesComponent), canActivate: [authGuard], title: 'EventHub — Ticket Types' },
  { path: 'organizer/events/:id/settings', loadComponent: () => import('./components/event-settings/event-settings.component').then(m => m.EventSettingsComponent), canActivate: [authGuard], title: 'EventHub — Event Settings' },
  { path: 'scan', loadComponent: () => import('./components/scan/scan.component').then(m => m.ScanComponent), canActivate: [authGuard], title: 'EventHub — Scan Tickets' },
  { path: 'validate/:uuid', loadComponent: () => import('./components/validate-ticket/validate-ticket.component').then(m => m.ValidateTicketComponent), canActivate: [authGuard], title: 'EventHub — Validate Ticket' },
  { path: 'payment/success', component: PaymentSuccessComponent, title: 'EventHub — Payment Success' },
  { path: 'payment/cancel', component: PaymentCancelComponent, title: 'EventHub — Payment Cancelled' },
  { path: '**', component: NotFoundComponent, title: 'EventHub — Page Not Found' },
];
