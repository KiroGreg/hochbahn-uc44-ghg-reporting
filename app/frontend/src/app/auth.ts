import { HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { catchError, map, of, throwError } from 'rxjs';

const STORAGE_KEY = 'uc44-token';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly token = signal<string | null>(this._load());
  readonly authenticated = signal<boolean>(false);

  private _load(): string | null {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }

  setToken(token: string | null) {
    this.token.set(token);
    try {
      if (token) localStorage.setItem(STORAGE_KEY, token);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore quota / private-mode errors */
    }
  }

  /** Hits the auth-check endpoint. Returns true if 200, false on 401. */
  verify() {
    return this.http.get<{ ok: boolean }>('/api/auth/check').pipe(
      map(() => {
        this.authenticated.set(true);
        return true;
      }),
      catchError(() => {
        this.authenticated.set(false);
        return of(false);
      }),
    );
  }

  /** Is auth enabled on the server at all? (no token required) */
  status() {
    return this.http.get<{ auth_enabled: boolean }>('/api/auth/status');
  }

  logout() {
    this.setToken(null);
    this.authenticated.set(false);
  }
}

/** Functional HTTP interceptor — attaches the bearer token to every
 *  request to /api/*. Skips the auth-status probe (no token needed)
 *  to avoid a token-less 401 on first load. */
export const tokenInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.token();
  if (!token) return next(req);
  if (!req.url.startsWith('/api/')) return next(req);
  if (req.url.startsWith('/api/auth/status')) return next(req);
  const cloned = req.clone({
    setHeaders: { Authorization: `Bearer ${token}` },
  });
  return next(cloned).pipe(
    catchError((err: HttpErrorResponse) => {
      // Token rejected — drop it and bounce back to the login screen.
      if (err.status === 401 && !req.url.startsWith('/api/auth/')) {
        auth.logout();
      }
      return throwError(() => err);
    }),
  );
};
