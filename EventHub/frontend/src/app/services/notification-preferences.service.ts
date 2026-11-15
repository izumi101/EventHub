import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import type { components } from '../api/openapi';

// API shapes come from the backend's OpenAPI schema (see models/models.ts).
export type NotificationPreferences = components['schemas']['NotificationPreferences'];
export type NotificationTypePreference = components['schemas']['NotificationTypePreference'];
/** Language notifications and emails are written in ('' means English). */
export type NotificationLanguage = components['schemas']['LanguageEnum'] | '';
/** The email type an unsubscribe link switches off. */
export type UnsubscribeInfo = components['schemas']['Unsubscribe'];

/** Email on/off per notification type (in-app notifications are always on). */
@Injectable({ providedIn: 'root' })
export class NotificationPreferencesService {
  private http = inject(HttpClient);

  private url = `${environment.apiUrl}/auth/profile/notifications/`;
  private unsubscribeUrl = `${environment.apiUrl}/notifications/unsubscribe/`;

  get(): Observable<NotificationPreferences> {
    return this.http.get<NotificationPreferences>(this.url);
  }

  /** Only the types sent are changed; the others keep their setting. */
  setEmail(changes: Record<string, boolean>): Observable<NotificationPreferences> {
    return this.http.patch<NotificationPreferences>(this.url, { email: changes });
  }

  /** The language the server writes this user's notifications and emails in. */
  setLanguage(language: NotificationLanguage): Observable<NotificationPreferences> {
    return this.http.patch<NotificationPreferences>(this.url, { language });
  }

  /** What an unsubscribe link (from an email) switches off. Changes nothing. */
  describeUnsubscribe(token: string): Observable<UnsubscribeInfo> {
    return this.http.get<UnsubscribeInfo>(this.unsubscribeUrl, {
      params: new HttpParams().set('token', token),
    });
  }

  /** Switches off the email type of an unsubscribe link; no sign-in needed. */
  unsubscribe(token: string): Observable<UnsubscribeInfo> {
    return this.http.post<UnsubscribeInfo>(this.unsubscribeUrl, { token });
  }
}
