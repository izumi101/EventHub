import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';
import {
  ApiMessageResponse,
  AuthResponse,
  PasswordResetTokenResponse,
  RefreshTokenResponse,
  RegistrationCodeResponse,
  User,
} from '../models/models';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private apiUrl = `${environment.apiUrl}/auth`;
  private readonly accessTokenKey = 'access_token';
  private readonly refreshTokenKey = 'refresh_token';
  private readonly userKey = 'user';
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  constructor(private http: HttpClient) {
    this.loadUser();
  }

  private loadUser(): void {
    const userData = localStorage.getItem(this.userKey);
    if (userData) {
      this.currentUserSubject.next(JSON.parse(userData));
    }
  }

  get currentUser(): User | null {
    return this.currentUserSubject.value;
  }

  get isLoggedIn(): boolean {
    return !!this.getToken();
  }

  getToken(): string | null {
    return localStorage.getItem(this.accessTokenKey);
  }

  register(
    username: string,
    email: string,
    password: string,
    password2: string,
    verification_code: string,
    first_name: string = '',
    last_name: string = '',
    phone: string = ''
  ): Observable<AuthResponse> {
    // Always registers an attendee — organizer accounts are created by admins.
    return this.http.post<AuthResponse>(`${this.apiUrl}/register/`, {
      username, email, password, password2, verification_code, first_name, last_name, phone
    }).pipe(
      tap(res => this.handleAuth(res))
    );
  }

  /** Admin-only: provision a new organizer account. */
  adminCreateOrganizer(payload: {
    username: string; email: string; password: string;
    first_name?: string; last_name?: string; phone?: string;
  }): Observable<User> {
    return this.http.post<User>(`${this.apiUrl}/admin/organizers/`, payload);
  }

  login(username: string, password: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${this.apiUrl}/login/`, {
      username, password
    }).pipe(
      tap(res => this.handleAuth(res))
    );
  }

  logout(): void {
    const refresh = localStorage.getItem(this.refreshTokenKey);
    this.http.post(`${this.apiUrl}/logout/`, { refresh }).subscribe();
    this.forceLogout();
  }

  /** Clear auth state locally without API call (used when tokens are expired) */
  forceLogout(): void {
    localStorage.removeItem(this.accessTokenKey);
    localStorage.removeItem(this.refreshTokenKey);
    localStorage.removeItem(this.userKey);
    this.currentUserSubject.next(null);
  }

  getProfile(): Observable<User> {
    return this.http.get<User>(`${this.apiUrl}/profile/`).pipe(
      tap(user => {
        localStorage.setItem(this.userKey, JSON.stringify(user));
        this.currentUserSubject.next(user);
      })
    );
  }

  updateProfile(data: Partial<User>): Observable<User> {
    return this.http.put<User>(`${this.apiUrl}/profile/`, data).pipe(
      tap(user => {
        localStorage.setItem(this.userKey, JSON.stringify(user));
        this.currentUserSubject.next(user);
      })
    );
  }

  changePassword(oldPassword: string, newPassword: string, newPassword2: string): Observable<ApiMessageResponse> {
    return this.http.post<ApiMessageResponse>(`${this.apiUrl}/change-password/`, {
      old_password: oldPassword,
      new_password: newPassword,
      new_password2: newPassword2,
    });
  }

  uploadAvatar(file: File): Observable<User> {
    const fd = new FormData();
    fd.append('avatar', file);
    return this.http.post<User>(`${this.apiUrl}/profile/avatar/`, fd).pipe(
      tap(user => {
        localStorage.setItem(this.userKey, JSON.stringify(user));
        this.currentUserSubject.next(user);
      })
    );
  }

  deleteAvatar(): Observable<User> {
    return this.http.delete<User>(`${this.apiUrl}/profile/avatar/`).pipe(
      tap(user => {
        localStorage.setItem(this.userKey, JSON.stringify(user));
        this.currentUserSubject.next(user);
      })
    );
  }

  refreshToken(): Observable<RefreshTokenResponse> {
    const refresh = localStorage.getItem(this.refreshTokenKey);
    return this.http.post<RefreshTokenResponse>(`${this.apiUrl}/token/refresh/`, { refresh }).pipe(
      tap(res => {
        localStorage.setItem(this.accessTokenKey, res.access);
      })
    );
  }

  private handleAuth(res: AuthResponse): void {
    localStorage.setItem(this.accessTokenKey, res.tokens.access);
    localStorage.setItem(this.refreshTokenKey, res.tokens.refresh);
    localStorage.setItem(this.userKey, JSON.stringify(res.user));
    this.currentUserSubject.next(res.user);
  }

  // ---- Registration Add-ons ---- //

  sendRegistrationCode(email: string): Observable<RegistrationCodeResponse> {
    return this.http.post<RegistrationCodeResponse>(`${this.apiUrl}/register/send-code/`, { email });
  }

  verifyRegistrationCode(email: string, code: string): Observable<ApiMessageResponse> {
    return this.http.post<ApiMessageResponse>(`${this.apiUrl}/register/verify-code/`, { email, code });
  }

  // ---- Password Reset Flow ---- //

  requestPasswordReset(identifier: string): Observable<ApiMessageResponse> {
    return this.http.post<ApiMessageResponse>(`${this.apiUrl}/password-reset/request/`, { identifier });
  }

  verifyResetCode(identifier: string, code: string): Observable<PasswordResetTokenResponse> {
    return this.http.post<PasswordResetTokenResponse>(`${this.apiUrl}/password-reset/verify/`, { identifier, code });
  }

  confirmPasswordReset(resetToken: string, newPassword: string, newPassword2: string): Observable<ApiMessageResponse> {
    return this.http.post<ApiMessageResponse>(`${this.apiUrl}/password-reset/confirm/`, {
      reset_token: resetToken,
      new_password: newPassword,
      new_password2: newPassword2,
    });
  }
}
