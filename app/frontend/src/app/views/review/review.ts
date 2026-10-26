import { Component, OnDestroy, OnInit, computed, inject, isDevMode, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  CatalogEntry,
  ComparisonResult,
  PlausibilityService,
  PredictionRow,
  PredictionService,
  RunStatus,
  RunsService,
} from '../../../api';
import { AppState } from '../../state';
import { formatError } from '../../util/error';
import { TipComponent } from '../../shared/tip';
import { WgComboComponent } from '../../shared/wg-combo';
import { SelectComponent, SelectOption } from '../../shared/select';

type Decision = 'ok' | 'reject' | 'new_wg';
type RowWithDecision = PredictionRow & {
  _decision?: Decision;
  _selected_wg?: string | null;
  /** true, wenn die Entscheidung automatisch per Auto-Übernahme gesetzt wurde (nicht manuell). */
  _auto?: boolean;
};
type SortEntry = { col: string; dir: 'asc' | 'desc' };

/** Sentinel-Wert der „➕ Neue Warengruppe…“-Option im WG-Dropdown. */
const ADD_NEW_WG = '__add_new_wg__';

@Component({
  selector: 'view-review',
  standalone: true,
  imports: [CommonModule, FormsModule, TipComponent, WgComboComponent, SelectComponent],
  templateUrl: './review.html',
})
export class ReviewView implements OnInit, OnDestroy {
  private readonly api = inject(PredictionService);
  private readonly plausibilityApi = inject(PlausibilityService);
  private readonly runsApi = inject(RunsService);
  protected readonly state = inject(AppState);

  protected readonly busy = signal(false);
  protected readonly maxRows = signal(50);
  protected readonly error = signal('');
  /** Aus früheren Korrekturen gelernte Hinweise in die Prediction einspeisen.
   *  Per Default an (Wunsch 2026-07-21) — abwählbar bleibt es z. B. für
   *  bewusste Baseline-Läufe im Memory-Vergleich. */
  protected readonly enableHints = signal(true);
  /** Vergleich Baseline vs. Memory (Stichproben der geänderten Vorhersagen). */
  protected readonly comparison = signal<ComparisonResult | null>(null);
  protected readonly comparing = signal(false);
  // Tracks which phase of the combined run is active
  protected readonly phase = signal<'idle' | 'checking' | 'predicting'>('idle');
  /** Live-Fortschritt des serverseitigen Laufs (aus der DB gepollt). */
  protected readonly runStatus = signal<RunStatus | null>(null);
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  /** Fortschritts-Prozente (min. 5% sichtbar, solange noch keine Zahlen da sind). */
  protected readonly plausPct = computed(() => {
    const s = this.runStatus();
    return s?.plaus_total ? Math.min(100, ((s.plaus_done ?? 0) / s.plaus_total) * 100) : 5;
  });
  protected readonly predPct = computed(() => {
    const s = this.runStatus();
    return s?.pred_total ? Math.min(100, ((s.pred_done ?? 0) / s.pred_total) * 100) : 5;
  });
  protected readonly confFilter = signal<'all' | 'hoch' | 'mittel' | 'niedrig'>('all');
  protected readonly statusFilter = signal<'all' | 'pending' | 'ok' | 'reject' | 'new_wg'>('all');
  protected readonly catalog = signal<string[]>([]);
  /** Vom Nutzer in dieser Sitzung selbst angelegte WGs (für „NEU"-Badge + ⋮-Menü). */
  protected readonly customWgs = signal<ReadonlySet<string>>(new Set());
  /** Im Template referenzierbarer Sentinel für die „Neue Warengruppe“-Option. */
  protected readonly ADD_NEW_WG = ADD_NEW_WG;

  protected readonly sortCols = signal<SortEntry[]>([]);
  protected readonly filters = signal<Record<string, string>>({});
  protected readonly wgFilter = signal<string>('');
  protected readonly wgBisherFilter = signal<string>('');
  protected readonly betragFilter = signal<string>('');
  readonly isMock = signal(false);
  protected readonly expandedRows = signal<Set<number>>(new Set());
  protected readonly autoConfThreshold = signal<'hoch' | 'mittel' | 'niedrig'>('hoch');
  protected readonly autoCostThreshold = signal<number>(1000);

  /**
   * Betrags-Filter der Tabelle (Dropdown wie WG-bisher / Warengruppe).
   * Genau zwei Bereiche, deren Grenze stets dem „Auto-Übernahme bis Betrag"-Wert
   * (`autoCostThreshold`) folgt: „< Betrag" (= die auto-übernehmbaren) und „≥ Betrag".
   * Die Bucket-Keys bleiben stabil, sodass eine aktive Auswahl beim Ändern des
   * Schwellenwerts erhalten bleibt und nur neu gegen die verschobene Grenze filtert.
   */
  private readonly betragBuckets = computed<ReadonlyArray<{ key: string; label: string; test: (v: number) => boolean }>>(() => {
    const cost = this.autoCostThreshold();
    if (cost == null) return [];
    const grenze = this.formatBetrag(cost);
    return [
      { key: 'lt', label: `< ${grenze}`, test: (v) => v < cost },
      { key: 'gte', label: `≥ ${grenze}`, test: (v) => v >= cost },
    ];
  });

  /** Lookup-Map: row_index → Plausibility-Signale aus Modell 1 */
  protected readonly plausMap = computed(() => {
    const rows = (this.state.plausibility()?.rows ?? []) as any[];
    const m = new Map<number, { widersprechend: string[]; unterstuetzend: string[]; reason: string }>();
    for (const r of rows) {
      m.set(r.row_index, {
        widersprechend: r.widersprechende_signale ?? [],
        unterstuetzend: r.unterstuetzende_signale ?? [],
        reason: r.reason ?? '',
      });
    }
    return m;
  });

  ngOnInit() {
    if (isDevMode() && !this.state.prediction()) {
      import('../../dev/mock-data').then(({ MOCK_UPLOAD, MOCK_PLAUSIBILITY, MOCK_PREDICTION, MOCK_CATALOG }) => {
        if (!this.state.upload()) this.state.upload.set(MOCK_UPLOAD);
        if (!this.state.plausibility()) this.state.plausibility.set(MOCK_PLAUSIBILITY);
        this.state.prediction.set(MOCK_PREDICTION);
        this.catalog.set(MOCK_CATALOG);
        this.isMock.set(true);
      });
      return;
    }
    this.api.catalogApiPredictionCatalogGet().subscribe({
      next: (entries: CatalogEntry[]) =>
        this.catalog.set(entries.map((e) => e.name).sort((a, b) => a.localeCompare(b, 'de'))),
      error: () => {
        if (isDevMode()) import('../../dev/mock-data').then(m => this.catalog.set(m.MOCK_CATALOG));
      },
    });

    // Wiederaufnahme: läuft für den aktiven Lauf serverseitig noch eine Analyse
    // (z.B. nach Tab-Wechsel oder Resume eines laufenden Laufs), Polling
    // fortsetzen; ist sie fertig, aber die Tabelle noch leer, Ergebnisse laden.
    const id = this.state.runId();
    if (id && !this.state.prediction()) {
      this.runsApi.runStatusApiRunsRunIdStatusGet(id).subscribe({
        next: (s) => {
          if (s.status === 'running') {
            this.applyStatus(s);
            this.startPolling(id);
          } else if (s.status === 'done') {
            this.loadResults(id);
          }
        },
        error: () => {},
      });
    }
  }

  protected rows = computed<RowWithDecision[]>(() => {
    const r = this.state.prediction();
    return (r?.rows ?? []) as RowWithDecision[];
  });

  protected sortedFiltered = computed<RowWithDecision[]>(() => {
    let rows = this.rows();
    const cf = this.confFilter();
    const sf = this.statusFilter();
    const wf = this.wgFilter();
    const wbf = this.wgBisherFilter();
    const betf = this.betragFilter();
    const betBucket = betf ? this.betragBuckets().find((b) => b.key === betf) : undefined;
    const filters = this.filters();
    const sorts = this.sortCols();

    rows = rows.filter((r) => {
      if (cf !== 'all' && r.confidence !== cf) return false;
      if (sf === 'pending' && r._decision != null) return false;
      if (sf === 'ok' && r._decision !== 'ok') return false;
      if (sf === 'reject' && r._decision !== 'reject') return false;
      if (sf === 'new_wg' && r._decision !== 'new_wg') return false;
      if (wf && r.suggested_wg_name !== wf) return false;
      if (wbf && (r.current_wg_name ?? '') !== wbf) return false;
      if (betBucket && !(r.betrag_eur != null && betBucket.test(r.betrag_eur))) return false;
      return true;
    });

    for (const [col, val] of Object.entries(filters)) {
      const v = val.toLowerCase();
      rows = rows.filter((r) => this.colValue(r, col).toLowerCase().includes(v));
    }

    // Entschiedene Zeilen rutschen IMMER ans Ende — egal ob aktiv sortiert oder nicht.
    // Innerhalb der beiden Gruppen (offen / erledigt) gilt dann die eigentliche Sortierung.
    if (sorts.length) {
      rows = [...rows].sort((a, b) => {
        const aD = a._decision != null ? 1 : 0;
        const bD = b._decision != null ? 1 : 0;
        if (aD !== bD) return aD - bD;
        for (const s of sorts) {
          const cmp = this.colValue(a, s.col).localeCompare(this.colValue(b, s.col), 'de');
          if (cmp !== 0) return s.dir === 'asc' ? cmp : -cmp;
        }
        return (a.suggested_wg_name ?? '').localeCompare(b.suggested_wg_name ?? '', 'de');
      });
    } else {
      const confOrder: Record<string, number> = { niedrig: 0, mittel: 1, hoch: 2 };
      rows = [...rows].sort((a, b) => {
        const aD = a._decision != null ? 1 : 0;
        const bD = b._decision != null ? 1 : 0;
        if (aD !== bD) return aD - bD;
        // Primär: Konfidenz (unsicher zuerst).
        const byConf = (confOrder[a.confidence] ?? 99) - (confOrder[b.confidence] ?? 99);
        if (byConf !== 0) return byConf;
        // Sekundär: Betrag (höchster zuerst); unbekannte Beträge ans Ende.
        const ab = a.betrag_eur ?? -Infinity;
        const bb = b.betrag_eur ?? -Infinity;
        if (ab !== bb) return bb - ab;
        return (a.suggested_wg_name ?? '').localeCompare(b.suggested_wg_name ?? '', 'de');
      });
    }

    return rows;
  });

  protected confirmedCount = computed(
    () => this.rows().filter((r) => r._decision === 'ok').length,
  );

  protected readonly summary = computed(() => {
    const rows = this.rows();
    const plausStats = this.state.plausibility()?.stats;
    return {
      plausible: plausStats?.plausible ?? 0,
      highMed: rows.filter((r) => r.confidence === 'hoch' || r.confidence === 'mittel').length,
      low: rows.filter((r) => r.confidence === 'niedrig').length,
      decided: rows.filter((r) => r._decision != null).length,
    };
  });

  /**
   * Anzahl der Zeilen, die ein Klick auf „Auto-Bestätigen" verändern würde — in BEIDE Richtungen:
   * offene, erfüllende Zeilen, die neu bestätigt würden, PLUS automatisch gesetzte Haken,
   * die bei strengerem Niveau wieder entfernt würden. Reagiert auf das Dropdown, sodass man
   * die Auswirkung schon vor dem Klick sieht.
   */
  protected readonly autoAffected = computed(() => {
    return this.rows().filter((r) => {
      const qualifies = this.autoQualifies(r);
      return (r._auto && !qualifies) || (r._decision == null && qualifies);
    }).length;
  });

  /**
   * Erfüllt eine Zeile beide Auto-Übernahme-Kriterien?
   * 1. Konfidenz erreicht das gewählte Niveau, UND
   * 2. der Betrag liegt unter dem eingestellten Kostenschwellenwert (req 2.1.2 / 2.2).
   * Ein leeres Betrags-Limit oder ein unbekannter Betrag blockiert nicht — dann zählt nur die Konfidenz.
   */
  private autoQualifies(r: RowWithDecision): boolean {
    // Only rows that actually carry a KI-Vorschlag may auto-confirm — a
    // high confidence with no suggested_wg_name would otherwise confirm an
    // empty Warengruppe.
    if (!r.suggested_wg_name) return false;
    const confOrder: Record<string, number> = { niedrig: 0, mittel: 1, hoch: 2 };
    const threshold = confOrder[this.autoConfThreshold()] ?? 2;
    const confOk = (confOrder[r.confidence] ?? -1) >= threshold;
    const cost = this.autoCostThreshold();
    const costOk = cost == null || r.betrag_eur == null || r.betrag_eur < cost;
    return confOk && costOk;
  }

  protected readonly confCounts = computed(() => {
    const rows = this.rows();
    return {
      hoch: rows.filter((r) => r.confidence === 'hoch').length,
      mittel: rows.filter((r) => r.confidence === 'mittel').length,
      niedrig: rows.filter((r) => r.confidence === 'niedrig').length,
    };
  });

  protected readonly decisionCounts = computed(() => {
    const rows = this.rows();
    return {
      pending: rows.filter((r) => r._decision == null).length,
      ok: rows.filter((r) => r._decision === 'ok').length,
      reject: rows.filter((r) => r._decision === 'reject').length,
      new_wg: rows.filter((r) => r._decision === 'new_wg').length,
    };
  });

  protected readonly distribution = computed(() => {
    const plausible = this.summary().plausible;
    const { hoch, mittel, niedrig } = this.confCounts();
    const total = plausible + hoch + mittel + niedrig || 1;
    return {
      ok:   plausible / total * 100,
      high: hoch      / total * 100,
      med:  mittel    / total * 100,
      low:  niedrig   / total * 100,
    };
  });

  protected readonly confSortLabel = computed(() => {
    const s = this.sortCols().find((x) => x.col === 'confidence');
    return s?.dir === 'asc' ? 'sicher → unsicher' : 'unsicher → sicher';
  });

  protected readonly suggestedWgOptions = computed(() => {
    const counts = new Map<string, number>();
    for (const r of this.rows()) {
      if (r.suggested_wg_name) {
        counts.set(r.suggested_wg_name, (counts.get(r.suggested_wg_name) ?? 0) + 1);
      }
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  });

  protected readonly wgBisherOptions = computed(() => {
    const counts = new Map<string, number>();
    for (const r of this.rows()) {
      const name = r.current_wg_name ?? '';
      if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }));
  });

  /** Betrags-Buckets samt Trefferzahl für das Filter-Dropdown der Betragsspalte. */
  protected readonly betragOptions = computed(() => {
    const rows = this.rows();
    return this.betragBuckets().map((b) => ({
      key: b.key,
      label: b.label,
      count: rows.filter((r) => r.betrag_eur != null && b.test(r.betrag_eur)).length,
    }));
  });

  // ── Optionslisten für die generischen <app-select>-Dropdowns ──────────────
  /** Statische Optionen (Anzahl Zeilen / Auto-Konfidenz-Niveau). */
  protected readonly maxRowsSelectOptions: ReadonlyArray<SelectOption> = [
    { value: 20, label: '20' },
    { value: 50, label: '50' },
    { value: 100, label: '100' },
    { value: 500, label: '500' },
    { value: null, label: 'Alle' },
  ];
  protected readonly autoConfSelectOptions: ReadonlyArray<SelectOption> = [
    { value: 'hoch', label: 'KI sehr sicher' },
    { value: 'mittel', label: 'KI sicher' },
    { value: 'niedrig', label: 'KI unsicher' },
  ];
  protected readonly statusSelectOptions = computed<SelectOption[]>(() => {
    const c = this.decisionCounts();
    return [
      { value: 'all', label: 'Alle Aktionen' },
      { value: 'pending', label: `Ausstehend (${c.pending})` },
      { value: 'ok', label: `✓ Bestätigt (${c.ok})` },
      { value: 'reject', label: `✗ Abgelehnt (${c.reject})` },
      { value: 'new_wg', label: `WG geändert (${c.new_wg})` },
    ];
  });
  protected readonly confSelectOptions = computed<SelectOption[]>(() => {
    const c = this.confCounts();
    return [
      { value: 'all', label: 'Alle' },
      { value: 'hoch', label: `sehr sicher (${c.hoch})` },
      { value: 'mittel', label: `sicher (${c.mittel})` },
      { value: 'niedrig', label: `unsicher (${c.niedrig})` },
    ];
  });
  protected readonly wgBisherSelectOptions = computed<SelectOption[]>(() => [
    { value: '', label: `Alle (${this.rows().length})` },
    ...this.wgBisherOptions().map((o) => ({ value: o.name, label: `${o.name} (${o.count})` })),
  ]);
  protected readonly betragSelectOptions = computed<SelectOption[]>(() => [
    { value: '', label: `Alle (${this.rows().length})` },
    ...this.betragOptions().map((o) => ({ value: o.key, label: `${o.label} (${o.count})` })),
  ]);
  protected readonly wgFilterSelectOptions = computed<SelectOption[]>(() => [
    { value: '', label: `Alle (${this.rows().length})` },
    ...this.suggestedWgOptions().map((o) => ({ value: o.name, label: `${o.name} (${o.count})` })),
  ]);

  /** Analyse starten. `withHints` überschreibt das Checkbox-Signal — die
   *  beiden Re-Analyse-Buttons wählen damit explizit mit/ohne gelernte
   *  Korrekturen; die Start-Karte ruft `run()` und nutzt die Checkbox. */
  run(withHints: boolean = this.enableHints()) {
    this.busy.set(true);
    this.error.set('');
    this.phase.set('checking');
    this.runStatus.set(null);

    this.runsApi
      .analyzeApiRunsAnalyzePost({ max_rows: this.maxRows(), enable_hints: withHints })
      .subscribe({
      next: (status) => {
        this.state.runId.set(status.id);
        this.applyStatus(status);
        this.startPolling(status.id);
      },
      error: (e) => {
        this.phase.set('idle');
        if (isDevMode()) {
          import('../../dev/mock-data').then(({ MOCK_PLAUSIBILITY, MOCK_PREDICTION, MOCK_CATALOG }) => {
            this.state.plausibility.set(MOCK_PLAUSIBILITY);
            this.state.prediction.set(MOCK_PREDICTION);
            this.catalog.set(MOCK_CATALOG);
            this.isMock.set(true);
            this.busy.set(false);
          });
        } else {
          this.busy.set(false);
          this.error.set(formatError(e, 'Analyse konnte nicht gestartet werden'));
        }
      },
    });
  }

  private startPolling(id: string) {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      this.runsApi.runStatusApiRunsRunIdStatusGet(id).subscribe({
        next: (s) => {
          this.applyStatus(s);
          if (s.status === 'done') {
            this.stopPolling();
            this.loadResults(id);
          } else if (s.status === 'failed') {
            this.stopPolling();
            this.busy.set(false);
            this.phase.set('idle');
            this.error.set(s.error || 'Analyse fehlgeschlagen');
          }
        },
        error: () => {
          /* transienter Poll-Fehler: nächster Tick versucht es erneut */
        },
      });
    }, 1500);
  }

  private stopPolling() {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private applyStatus(s: RunStatus) {
    this.runStatus.set(s);
    this.busy.set(s.status === 'running');
    this.phase.set(s.stage === 'prediction' ? 'predicting' : 'checking');
  }

  /** Lauf ist fertig → vollständige Ergebnisse + Entscheidungen aus der DB laden. */
  private loadResults(id: string) {
    this.runsApi.getRunApiRunsRunIdGet(id).subscribe({
      next: (detail) => {
        this.state.loadRun(detail, false);
        this.isMock.set(false);
        this.phase.set('idle');
        this.busy.set(false);
        this.runStatus.set(null);
      },
      error: (e) => {
        this.busy.set(false);
        this.phase.set('idle');
        this.error.set(formatError(e, 'Ergebnisse konnten nicht geladen werden'));
      },
    });
  }

  ngOnDestroy() {
    this.stopPolling();
  }

  /** Baseline- vs. Memory-Vorhersagen für den aktiven Lauf laden (Stichproben). */
  loadComparison() {
    const id = this.state.runId();
    if (!id) return;
    if (this.comparison()) {
      this.comparison.set(null); // toggle aus
      return;
    }
    this.comparing.set(true);
    this.runsApi.compareApiRunsRunIdCompareGet(id).subscribe({
      next: (c) => {
        this.comparison.set(c);
        this.comparing.set(false);
      },
      error: (e) => {
        this.comparing.set(false);
        this.error.set(formatError(e, 'Vergleich fehlgeschlagen'));
      },
    });
  }

  /**
   * Wird NUR beim Klick auf „Auto-Bestätigen" ausgeführt (nicht beim Dropdown-Wechsel).
   * Gleicht die automatisch gesetzten Haken mit der aktuellen Konfidenz-Schwelle ab:
   * - Strengere Regel: zuvor automatisch gesetzte Haken, die nicht mehr erfüllen, werden entfernt.
   * - Lockerere Regel: jetzt erfüllende, noch offene Zeilen werden automatisch bestätigt.
   * Manuelle Entscheidungen (✓ / ✗ / WG geändert) bleiben unberührt.
   */
  autoAccept() {
    for (const r of this.rows()) {
      const qualifies = this.autoQualifies(r);
      if (r._auto && !qualifies) {
        this.undecide(r);
      } else if (r._decision == null && qualifies) {
        this.decide(r, 'ok', true);
      }
    }
  }

  /** Nimmt eine Entscheidung zurück (Zeile zurück auf Ausgangszustand) und bereinigt das Audit-Log. */
  private undecide(row: RowWithDecision) {
    row._decision = undefined;
    row._selected_wg = null;
    row._auto = false;
    this.state.clearRowLog(row.row_index);
    // Auch im Backend löschen, sonst wendet das Dashboard die Entscheidung weiter an.
    if (!this.isMock()) {
      this.api
        .clearDecisionApiPredictionDecisionRowIndexDelete(row.row_index)
        .subscribe({ error: () => {} });
    }
    const pr = this.state.prediction();
    if (pr) this.state.prediction.set({ ...pr, rows: [...pr.rows] });
  }

  /** Setzt ALLE getroffenen Entscheidungen zurück auf den Ausgangszustand. */
  resetDecisions() {
    for (const r of this.rows()) {
      r._decision = undefined;
      r._selected_wg = null;
      r._auto = false;
    }
    this.state.changeLog.set([]);
    const pr = this.state.prediction();
    if (pr) this.state.prediction.set({ ...pr, rows: [...pr.rows] });
  }

  /**
   * Klick auf ✓ / ✗: Ist die Entscheidung bereits aktiv, wird sie rückgängig
   * gemacht (nur diese Zeile, ohne alle anderen zu berühren); sonst wird sie gesetzt.
   */
  toggleDecide(row: RowWithDecision, decision: 'ok' | 'reject') {
    if (row._decision === decision) {
      this.undecide(row);
    } else {
      this.decide(row, decision);
    }
  }

  decide(row: RowWithDecision, decision: Decision, isAuto = false) {
    const oldDecision = row._decision ?? '—';
    row._decision = decision;
    row._auto = isAuto;
    if (!this.isMock()) {
      this.api
        .decisionApiPredictionDecisionPost({
          row_index: row.row_index,
          decision,
          // On accepting the suggestion, persist the accepted WG as the target.
          new_wg_name: decision === 'ok' ? row.suggested_wg_name ?? null : null,
          old_value: String(oldDecision),
        })
        .subscribe({ error: () => {} });
    }
    // Force sortedFiltered + summary to re-compute reactively
    const pr = this.state.prediction();
    if (pr) this.state.prediction.set({ ...pr, rows: [...pr.rows] });
    this.state.logChange({
      timestamp: new Date().toISOString(),
      stage: 'regrouping',
      row_index: row.row_index,
      field_changed: 'decision',
      old_value: oldDecision,
      new_value: decision,
      user_action: decision === 'ok' ? 'accept' : 'reject',
    });
  }

  /**
   * Auswahl in der zusammengeführten "Warengruppe"-Spalte.
   * KI-Vorschlag (= suggested_wg_name) → als Übernahme ('ok') werten;
   * jede andere WG → manueller Wechsel ('new_wg'). Leerwert → zurücksetzen.
   */
  wgPick(row: RowWithDecision, newWg: string) {
    if (newWg === ADD_NEW_WG) {
      this.promptNewWg(row);
      return;
    }
    if (!newWg) {
      row._selected_wg = null;
      row._decision = undefined;
      const pr = this.state.prediction();
      if (pr) this.state.prediction.set({ ...pr, rows: [...pr.rows] });
      return;
    }
    if (newWg === row.suggested_wg_name) {
      // KI-Vorschlag (wieder) gewählt → kein manueller Override, als Bestätigung markieren
      row._selected_wg = null;
      this.decide(row, 'ok');
    } else {
      this.wgChange(row, newWg);
    }
  }

  /**
   * Fragt per Prompt nach dem Namen einer neuen Warengruppe, fügt sie dem
   * Katalog hinzu (alphabetisch einsortiert) und setzt sie als manuelle Auswahl
   * der Zeile. Bricht der Nutzer ab, springt das Dropdown auf den vorherigen Wert zurück.
   */
  private promptNewWg(row: RowWithDecision) {
    const name = (window.prompt('Name der neuen Warengruppe:') ?? '').trim();
    if (name) {
      if (!this.catalog().includes(name)) {
        this.catalog.set([...this.catalog(), name].sort((a, b) => a.localeCompare(b, 'de')));
      }
      // Als selbst angelegt merken → „NEU"-Badge + ⋮-Menü im Dropdown.
      this.customWgs.set(new Set(this.customWgs()).add(name));
      this.wgChange(row, name);
    } else {
      // Auswahl verwerfen → Select per Re-Compute zurück auf den vorherigen Wert
      const pr = this.state.prediction();
      if (pr) this.state.prediction.set({ ...pr, rows: [...pr.rows] });
    }
  }

  /**
   * Benennt eine selbst angelegte WG um (Prompt). Aktualisiert den Katalog, das
   * Custom-Set und alle Zeilen, die diese WG manuell gesetzt hatten — inkl.
   * Backend-Entscheidung und Audit-Log via `wgChange`.
   */
  renameCustomWg(oldName: string) {
    const next = (window.prompt('Neuer Name der Warengruppe:', oldName) ?? '').trim();
    if (!next || next === oldName) return;
    if (this.catalog().includes(next)) {
      window.alert(`„${next}" existiert bereits.`);
      return;
    }
    // Katalog: alten Namen ersetzen, alphabetisch neu sortieren.
    this.catalog.set(
      this.catalog().map((wg) => (wg === oldName ? next : wg)).sort((a, b) => a.localeCompare(b, 'de')),
    );
    // Custom-Set umhängen.
    const cs = new Set(this.customWgs());
    cs.delete(oldName);
    cs.add(next);
    this.customWgs.set(cs);
    // Betroffene Zeilen auf den neuen Namen umstellen (loggt + Backend).
    for (const r of this.rows()) {
      if (r._selected_wg === oldName) this.wgChange(r, next);
    }
  }

  /**
   * Löscht eine selbst angelegte WG (mit Rückfrage). Entfernt sie aus Katalog und
   * Custom-Set; Zeilen, die sie gesetzt hatten, werden zurückgesetzt (undecide).
   */
  deleteCustomWg(name: string) {
    const affected = this.rows().filter((r) => r._selected_wg === name);
    const hint = affected.length ? `\n\n${affected.length} Zeile(n) verlieren dadurch ihre Auswahl.` : '';
    if (!window.confirm(`Warengruppe „${name}" löschen?${hint}`)) return;
    for (const r of affected) this.undecide(r);
    this.catalog.set(this.catalog().filter((wg) => wg !== name));
    const cs = new Set(this.customWgs());
    cs.delete(name);
    this.customWgs.set(cs);
  }

  wgChange(row: RowWithDecision, newWg: string) {
    if (!newWg) {
      row._selected_wg = null;
      row._decision = undefined;
      row._auto = false;
      const pr = this.state.prediction();
      if (pr) this.state.prediction.set({ ...pr, rows: [...pr.rows] });
      return;
    }
    const oldWg = row._selected_wg ?? '—';
    row._selected_wg = newWg;
    row._decision = 'new_wg';
    row._auto = false;
    if (!this.isMock()) {
      this.api
        .decisionApiPredictionDecisionPost({
          row_index: row.row_index,
          decision: 'new_wg',
          new_wg_name: newWg,
          old_value: String(oldWg),
        })
        .subscribe({ error: () => {} });
    }
    // Force re-compute
    const pr = this.state.prediction();
    if (pr) this.state.prediction.set({ ...pr, rows: [...pr.rows] });
    this.state.logChange({
      timestamp: new Date().toISOString(),
      stage: 'regrouping',
      row_index: row.row_index,
      field_changed: 'wg_name',
      old_value: oldWg,
      new_value: newWg,
      user_action: 'manual_wg_change',
    });
  }

  toggleSort(col: string) {
    const current = this.sortCols();
    const existing = current.find((s) => s.col === col);
    if (!existing) {
      // Die Default-Ansicht (ohne aktiven Sort) zeigt Konfidenz bereits unsicher→sicher
      // (entspricht 'desc'). Erster Klick muss daher auf 'asc' (sicher→unsicher) wechseln,
      // sonst ändert sich sichtbar nichts und es wirkt, als würde der erste Klick ignoriert.
      const defaultDir: 'asc' | 'desc' = 'asc';
      this.sortCols.set([...current, { col, dir: defaultDir }]);
    } else {
      const newDir = existing.dir === 'asc' ? 'desc' : 'asc';
      this.sortCols.set(current.map((s) => (s.col === col ? { col, dir: newDir } : s)));
    }
  }

  setFilter(col: string, val: string) {
    const f = { ...this.filters() };
    if (val) {
      f[col] = val;
    } else {
      delete f[col];
    }
    this.filters.set(f);
  }

  toggleExpand(rowIndex: number) {
    const s = new Set(this.expandedRows());
    if (s.has(rowIndex)) s.delete(rowIndex); else s.add(rowIndex);
    this.expandedRows.set(s);
  }

  isExpanded(rowIndex: number): boolean {
    return this.expandedRows().has(rowIndex);
  }

  goDashboard() {
    this.state.go('dashboard');
  }

  badge(c: string): string {
    return c === 'hoch' ? 'c-gr' : c === 'mittel' ? 'c-am' : 'c-rd';
  }

  confidenceLabel(c: string): string {
    return c === 'hoch' ? 'sehr sicher' : c === 'mittel' ? 'sicher' : c === 'niedrig' ? 'unsicher' : c;
  }

  /** Betrag als € ohne Nachkommastellen; fehlender Betrag → „—". */
  formatBetrag(v: number | null | undefined): string {
    if (v == null) return '—';
    return v.toLocaleString('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
  }

  private colValue(r: RowWithDecision, col: string): string {
    switch (col) {
      case 'bestelltext': return r.bestelltext ?? '';
      case 'suggested_wg_name': return r.suggested_wg_name ?? '';
      case 'confidence': return r.confidence ?? '';
      default: return '';
    }
  }
}
