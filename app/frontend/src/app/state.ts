import { Injectable, computed, signal } from '@angular/core';
import {
  BudgetStats,
  DashboardResponse,
  PlausibilityRunResponse,
  PredictionRunResponse,
  RunDetail,
  UploadSummary,
} from '../api';

export type ViewKey = 'upload' | 'plausibility' | 'review' | 'dashboard' | 'warengruppen' | 'anreichern';

// 'plausibility' is kept in ViewKey for backward compat but removed from nav order (merged into 'review').
// 'warengruppen' is a master-data screen reached via a separate sidebar entry — deliberately NOT part of the
// linear funnel, so it carries no step number.
const STEP_ORDER: ViewKey[] = ['upload', 'review', 'dashboard'];

export interface ChangeLogEntry {
  timestamp: string;
  stage: 'plausibility' | 'regrouping';
  row_index: number;
  field_changed: string;
  old_value: string;
  new_value: string;
  user_action: 'accept' | 'reject' | 'manual_wg_change';
}

@Injectable({ providedIn: 'root' })
export class AppState {
  readonly view = signal<ViewKey>('upload');
  /** Id des aktiven (persistierten) Laufs — für Status-Polling & Resume. */
  readonly runId = signal<string | null>(null);
  readonly upload = signal<UploadSummary | null>(null);
  readonly plausibility = signal<PlausibilityRunResponse | null>(null);
  readonly prediction = signal<PredictionRunResponse | null>(null);
  readonly dashboard = signal<DashboardResponse | null>(null);
  readonly budget = signal<BudgetStats | null>(null);
  readonly changeLog = signal<ChangeLogEntry[]>([]);

  readonly stepIndex = computed(() => STEP_ORDER.indexOf(this.view()));

  isCompleted(step: ViewKey): boolean {
    const i = STEP_ORDER.indexOf(step);
    if (i < 0) return false;
    if (i === 0) return this.upload() != null && this.view() !== 'upload';
    if (i === 1) return this.prediction() != null && this.view() !== 'review';
    return false;
  }

  isActive(step: ViewKey): boolean {
    return this.view() === step;
  }

  go(step: ViewKey) {
    this.view.set(step);
  }

  logChange(entry: ChangeLogEntry) {
    this.changeLog.update((log) => [...log, entry]);
  }

  /**
   * Stellt einen persistierten Lauf aus der DB wieder her (Resume).
   * Füllt alle Signals, projiziert die aktuellen Entscheidungen zurück auf die
   * Prediction-Zeilen (damit das Review-Table den Stand zeigt) und rekonstruiert
   * das Änderungs-Log. Springt anschließend ins Review, wo weitergearbeitet wird.
   */
  loadRun(detail: RunDetail, navigate = true) {
    this.runId.set(detail.run.id);
    this.upload.set(detail.upload);
    this.plausibility.set(detail.plausibility ?? null);

    const pred = detail.prediction ?? null;
    if (pred) {
      const decByRow = new Map((detail.decisions ?? []).map((d) => [d.row_index, d]));
      const rows = pred.rows.map((r) => {
        const d = decByRow.get(r.row_index);
        if (!d) return r;
        // 'regroup' (Plausibilitäts-Stufe) auf die Review-Semantik 'new_wg' mappen.
        const decision = d.decision === 'regroup' ? 'new_wg' : d.decision;
        return { ...r, _decision: decision, _selected_wg: d.selected_wg ?? null, _auto: false };
      });
      this.prediction.set({ ...pred, rows });
    } else {
      this.prediction.set(null);
    }

    // Dashboard wird beim Navigieren neu vom Backend geholt (rehydrierter State).
    this.dashboard.set(null);
    this.changeLog.set(
      (detail.change_log ?? []).map((c) => ({
        timestamp: c.timestamp,
        stage: c.stage as ChangeLogEntry['stage'],
        row_index: c.row_index,
        field_changed: c.field_changed,
        old_value: c.old_value,
        new_value: c.new_value,
        user_action: c.user_action as ChangeLogEntry['user_action'],
      })),
    );

    if (navigate) this.view.set('review');
  }

  /** Entfernt alle Log-Einträge einer Zeile — hält das Audit-Log konsistent, wenn eine Entscheidung zurückgenommen wird. */
  clearRowLog(rowIndex: number) {
    this.changeLog.update((log) => log.filter((e) => e.row_index !== rowIndex));
  }

  exportLog() {
    const log = this.changeLog();
    if (!log.length) return;
    const headers: (keyof ChangeLogEntry)[] = [
      'timestamp',
      'stage',
      'row_index',
      'field_changed',
      'old_value',
      'new_value',
      'user_action',
    ];
    const csvRows = log.map((e) =>
      headers.map((h) => JSON.stringify(String(e[h] ?? ''))).join(','),
    );
    const csv = [headers.join(','), ...csvRows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `change-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  reset() {
    this.runId.set(null);
    this.upload.set(null);
    this.plausibility.set(null);
    this.prediction.set(null);
    this.dashboard.set(null);
    this.budget.set(null);
    this.changeLog.set([]);
    this.view.set('upload');
  }
}
