import { Routes } from '@angular/router';
import { authGuard } from './guards/auth.guard';
import { roleGuard } from './guards/role.guard';

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
  { path: '', component: HomeComponent, title: 'routeTitles.discoverEvents' },
  { path: 'events/:id', component: EventDetailComponent, title: 'routeTitles.eventDetails' },
  {
    path: 'events/:id/group',
    loadComponent: () =>
      import('./components/group-booking/group-booking.component').then(
        (m) => m.GroupBookingComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.groupBooking',
  },
  {
    path: 'booking/:token',
    loadComponent: () =>
      import('./components/booking-claim/booking-claim.component').then(
        (m) => m.BookingClaimComponent,
      ),
    title: 'routeTitles.claimYourSeat',
  },
  {
    path: 'create-event',
    component: EventFormComponent,
    canActivate: [roleGuard('organizer')],
    title: 'routeTitles.createEvent',
  },
  {
    path: 'edit-event/:id',
    component: EventFormComponent,
    canActivate: [authGuard],
    title: 'routeTitles.editEvent',
  },
  { path: 'login', component: LoginComponent, title: 'routeTitles.signIn' },
  {
    path: 'forgot-password',
    loadComponent: () =>
      import('./components/forgot-password/forgot-password.component').then(
        (m) => m.ForgotPasswordComponent,
      ),
    title: 'routeTitles.resetPassword',
  },
  { path: 'register', component: RegisterComponent, title: 'routeTitles.createAccount' },
  {
    path: 'profile',
    component: ProfileComponent,
    canActivate: [authGuard],
    title: 'routeTitles.profile',
  },
  {
    path: 'profile/security',
    loadComponent: () =>
      import('./components/security/security-settings.component').then(
        (m) => m.SecuritySettingsComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.security',
  },
  {
    path: 'profile/notifications',
    loadComponent: () =>
      import('./components/notification-preferences/notification-preferences.component').then(
        (m) => m.NotificationPreferencesComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.notificationSettings',
  },
  {
    path: 'favorites',
    loadComponent: () =>
      import('./components/favorites/favorites.component').then((m) => m.FavoritesComponent),
    canActivate: [authGuard],
    title: 'routeTitles.favorites',
  },
  {
    path: 'my-events',
    component: MyEventsComponent,
    canActivate: [authGuard],
    title: 'routeTitles.myEvents',
  },
  {
    path: 'my-registrations',
    component: MyRegistrationsComponent,
    canActivate: [authGuard],
    title: 'routeTitles.myTickets',
  },
  {
    path: 'my-bookings',
    loadComponent: () =>
      import('./components/my-bookings/my-bookings.component').then((m) => m.MyBookingsComponent),
    canActivate: [authGuard],
    title: 'routeTitles.myBookings',
  },
  {
    path: 'admin/moderation',
    loadComponent: () =>
      import('./components/admin-moderation/admin-moderation.component').then(
        (m) => m.AdminModerationComponent,
      ),
    canActivate: [roleGuard('admin')],
    title: 'routeTitles.moderation',
  },
  {
    path: 'organizer/dashboard',
    loadComponent: () =>
      import('./components/dashboard/dashboard.component').then((m) => m.DashboardComponent),
    canActivate: [roleGuard('organizer')],
    title: 'routeTitles.organizerDashboard',
  },
  {
    path: 'organizer/events/:id/attendees',
    loadComponent: () =>
      import('./components/attendee-list/attendee-list.component').then(
        (m) => m.AttendeeListComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.attendeeList',
  },
  {
    path: 'organizer/events/:id/analytics',
    loadComponent: () =>
      import('./components/event-analytics/event-analytics.component').then(
        (m) => m.EventAnalyticsComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.analytics',
  },
  {
    path: 'organizer/events/:id/checkin-lists',
    loadComponent: () =>
      import('./components/checkin-lists/checkin-lists.component').then(
        (m) => m.CheckinListsComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.checkInLists',
  },
  {
    path: 'organizer/events/:id/waitlist',
    loadComponent: () =>
      import('./components/event-waitlist/event-waitlist.component').then(
        (m) => m.EventWaitlistComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.waitlist',
  },
  {
    path: 'organizer/events/:id/promo-codes',
    loadComponent: () =>
      import('./components/promo-codes/promo-codes.component').then((m) => m.PromoCodesComponent),
    canActivate: [authGuard],
    title: 'routeTitles.promoCodes',
  },
  {
    path: 'organizer/events/:id/questions',
    loadComponent: () =>
      import('./components/event-questions/event-questions.component').then(
        (m) => m.EventQuestionsComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.checkoutQuestions',
  },
  {
    path: 'organizer/events/:id/ticket-types',
    loadComponent: () =>
      import('./components/ticket-types/ticket-types.component').then(
        (m) => m.TicketTypesComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.ticketTypes',
  },
  {
    path: 'organizer/events/:id/settings',
    loadComponent: () =>
      import('./components/event-settings/event-settings.component').then(
        (m) => m.EventSettingsComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.eventSettings',
  },
  {
    path: 'scan',
    loadComponent: () => import('./components/scan/scan.component').then((m) => m.ScanComponent),
    canActivate: [authGuard],
    title: 'routeTitles.scanTickets',
  },
  {
    path: 'validate/:uuid',
    loadComponent: () =>
      import('./components/validate-ticket/validate-ticket.component').then(
        (m) => m.ValidateTicketComponent,
      ),
    canActivate: [authGuard],
    title: 'routeTitles.validateTicket',
  },
  {
    path: 'payment/success',
    component: PaymentSuccessComponent,
    title: 'routeTitles.paymentSuccess',
  },
  {
    path: 'payment/cancel',
    component: PaymentCancelComponent,
    title: 'routeTitles.paymentCancelled',
  },
  { path: '**', component: NotFoundComponent, title: 'routeTitles.pageNotFound' },
];
