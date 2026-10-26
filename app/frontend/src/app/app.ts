import { Component, computed, inject, isDevMode, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DashboardService } from '../api';
import { AppState, ViewKey } from './state';
import { AuthService } from './auth';
import { LoginView } from './views/login/login';
import { UploadView } from './views/upload/upload';
import { ReviewView } from './views/review/review';
import { DashboardView } from './views/dashboard/dashboard';
import { WarengruppenView } from './views/warengruppen/warengruppen';
import { EnrichView } from './views/enrich/enrich';

const TITLES: Record<ViewKey, string> = {
  upload: 'Upload & Spalten-Mapping',
  plausibility: 'Prüfung — Modell 1',
  review: 'KI-Prüfung — Plausibilität & Warengruppen',
  dashboard: 'THG-Dashboard & Statistiken',
  warengruppen: 'Warengruppen-Katalog — Stammdaten & Emissionsfaktoren',
  anreichern: 'Katalog anreichern — KI-Beschreibungen & Beispiele',
};

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, LoginView, UploadView, ReviewView, DashboardView, WarengruppenView, EnrichView],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly state = inject(AppState);
  protected readonly auth = inject(AuthService);
  private readonly dashboardApi = inject(DashboardService);

  protected readonly theme = signal<'light' | 'dark'>(
    (typeof localStorage !== 'undefined' && (localStorage.getItem('thg-t') as 'light' | 'dark')) ||
      'light',
  );

  protected readonly title = computed(() => TITLES[this.state.view()]);
  protected readonly stepBadge = computed(() => {
    const i = this.state.stepIndex();
    return i >= 0 ? `Schritt ${i + 1} von 3` : '';
  });

  protected readonly steps: { key: ViewKey; main: string; sub: string }[] = [
    { key: 'upload', main: 'Upload', sub: 'Excel & Mapping' },
    { key: 'review', main: 'KI-Prüfung', sub: 'Analyse & Entscheidung' },
    { key: 'dashboard', main: 'Dashboard', sub: 'THG & Statistiken' },
  ];

  constructor() {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', this.theme());
    }
    this._bootstrapAuth();
  }

  /** On boot: ask the server whether auth is required, and if a token
   *  is already stored, validate it before showing the shell. */
  private _bootstrapAuth() {
    this.auth.status().subscribe({
      next: (s) => {
        if (!s.auth_enabled) {
          // Server runs without a token — treat as authenticated.
          this.auth.authenticated.set(true);
          this.refreshBudget();
          return;
        }
        if (this.auth.token()) {
          this.auth.verify().subscribe((ok) => {
            if (ok) this.refreshBudget();
            else this.auth.setToken(null);
          });
        }
      },
      error: () => {
        // Server unreachable — keep showing the login screen.
      },
    });
  }

  logout() {
    this.auth.logout();
    this.state.reset();
  }

  toggleTheme() {
    const next = this.theme() === 'dark' ? 'light' : 'dark';
    this.theme.set(next);
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', next);
    }
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('thg-t', next);
    }
  }

  go(step: ViewKey) {
    this.state.go(step);
    this.refreshBudget();
  }

  refreshBudget() {
    this.dashboardApi.budgetApiDashboardBudgetGet().subscribe({
      next: (b) => this.state.budget.set(b),
      error: () => {
        if (isDevMode()) import('./dev/mock-data').then(m => this.state.budget.set(m.MOCK_BUDGET));
      },
    });
  }

  stepClass(step: ViewKey): string {
    if (this.state.isActive(step)) return 'sd-act';
    if (this.state.isCompleted(step)) return 'sd-done';
    return 'sd-pen';
  }

  stepLabel(step: ViewKey, idx: number): string {
    return this.state.isCompleted(step) ? '✓' : String(idx + 1);
  }

  /** Funnel numbers in the sidebar. */
  funnel = computed(() => {
    const u = this.state.upload();
    const p = this.state.plausibility();
    const pr = this.state.prediction();
    const d = this.state.dashboard();
    const total = u?.row_count ?? 0;
    const notPlausible = p?.stats?.implausible ?? 0;
    const regrouped = pr?.stats?.regrouped_high_med ?? 0;
    const lowOpen = pr?.stats?.low_confidence ?? 0;
    return {
      total,
      notPlausible,
      regrouped,
      lowOpen,
      pNot: total ? Math.min(100, Math.round((notPlausible / total) * 100)) : 0,
      pReg: total ? Math.min(100, Math.round((regrouped / total) * 100)) : 0,
      pLow: total ? Math.min(100, Math.round((lowOpen / total) * 100)) : 0,
    };
  });

  budgetPct = computed(() => {
    const b = this.state.budget();
    if (!b || !b.budget_usd) return 0;
    return Math.min(100, (b.spent_usd / b.budget_usd) * 100);
  });
}
