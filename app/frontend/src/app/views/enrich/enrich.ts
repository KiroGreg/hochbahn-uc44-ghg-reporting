import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  BulkEnrichRequest,
  EnrichBatchDetail,
  EnrichBatchStatus,
  EnrichContent,
  EnrichPlan,
  EnrichProposal,
  EnrichmentService,
  FieldAnnotations,
  HistorySignal,
  WarengruppeRow,
  WarengruppenService,
} from '../../../api';
import { EnrichReviewComponent } from '../../shared/enrich-review';
import { formatError } from '../../util/error';

type Action = 'lassen' | 'ergänzen' | 'neu';

/**
 * Wizard „Katalog anreichern" — Auswahl → Konfiguration → Lauf → Review.
 * Der Lauf läuft als Hintergrund-Batch im Backend; der Wizard pollt den Status
 * (wie review.ts) und nimmt beim erneuten Öffnen einen laufenden Batch wieder auf.
 * Die Review-Queue nutzt dasselbe <app-enrich-review>-Panel wie das atomare Modal.
 */
@Component({
  selector: 'view-enrich',
  standalone: true,
  imports: [CommonModule, FormsModule, EnrichReviewComponent],
  templateUrl: './enrich.html',
  styleUrl: './enrich.scss',
})
export class EnrichView implements OnInit, OnDestroy {
  private readonly api = inject(EnrichmentService);
  private readonly wgApi = inject(WarengruppenService);

  protected readonly step = signal<1 | 2 | 3 | 4>(1);
  protected readonly loading = signal(false);
  protected readonly error = signal('');

  // --- Schritt 1: Auswahl ---
  protected readonly rows = signal<WarengruppeRow[]>([]);
  protected readonly flux = signal<Record<string, { influx: number; outflux: number }>>({});
  protected readonly selected = signal<Set<string>>(new Set());
  protected readonly search = signal('');
  protected readonly onlyIncomplete = signal(false);
  protected readonly onlyHistory = signal(false);

  // --- Schritt 2: Konfiguration ---
  protected readonly autoPlan = signal(true);
  protected readonly plan = signal<EnrichPlan>({
    beschreibung: 'neu',
    examples_enthalten: 'neu',
    examples_nicht_enthalten: 'neu',
  });
  protected readonly useHistory = signal(false);
  protected readonly PLAN_FIELDS = [
    { key: 'beschreibung' as const, label: 'Beschreibung' },
    { key: 'examples_enthalten' as const, label: 'Beispiele enthält' },
    { key: 'examples_nicht_enthalten' as const, label: 'Beispiele nicht enthält' },
  ];

  // --- Schritt 3: Lauf ---
  protected readonly batchId = signal<string | null>(null);
  protected readonly status = signal<EnrichBatchStatus | null>(null);
  protected readonly resumable = signal<EnrichBatchStatus | null>(null);
  private poll: ReturnType<typeof setInterval> | null = null;

  // --- Schritt 4: Review ---
  protected readonly detail = signal<EnrichBatchDetail | null>(null);
  protected readonly expanded = signal<string | null>(null);
  protected readonly propHist = signal<Record<string, HistorySignal>>({});
  private readonly rowBusy = signal<Set<string>>(new Set());

  ngOnInit() {
    this.loadCatalog();
    this.checkResume();
  }

  ngOnDestroy() {
    this.stopPoll();
  }

  // --- Schritt 1: Auswahl --------------------------------------------------

  loadCatalog() {
    this.loading.set(true);
    this.error.set('');
    this.wgApi.listWarengruppenApiWarengruppenGet().subscribe({
      next: (rs) => {
        this.rows.set(rs.filter((r) => r.aktiv !== false));
        this.loading.set(false);
      },
      error: (e) => {
        this.loading.set(false);
        this.error.set(formatError(e, 'Katalog konnte nicht geladen werden'));
      },
    });
    this.api.historySignalsApiEnrichmentHistorySignalsGet().subscribe({
      next: (m) => this.flux.set((m as Record<string, { influx: number; outflux: number }>) ?? {}),
      error: () => {},
    });
  }

  completeness(r: WarengruppeRow) {
    const desc = !!(r.beschreibung && r.beschreibung.trim());
    const inc = (r.examples_enthalten?.length ?? 0) > 0;
    const exc = (r.examples_nicht_enthalten?.length ?? 0) > 0;
    return { desc, inc, exc, complete: desc && inc && exc, count: (desc ? 1 : 0) + (inc ? 1 : 0) + (exc ? 1 : 0) };
  }

  fluxOf(wgId: string) {
    return this.flux()[wgId] ?? { influx: 0, outflux: 0 };
  }

  protected readonly filtered = computed<WarengruppeRow[]>(() => {
    const q = this.search().trim().toLowerCase();
    const oi = this.onlyIncomplete();
    const oh = this.onlyHistory();
    const list = this.rows().filter((r) => {
      if (q && !(r.wg_name.toLowerCase().includes(q) || r.wg_id.toLowerCase().includes(q))) return false;
      if (oi && this.completeness(r).complete) return false;
      if (oh) {
        const f = this.fluxOf(r.wg_id);
        if (f.influx === 0 && f.outflux === 0) return false;
      }
      return true;
    });
    return list.sort((a, b) => {
      const fa = this.fluxOf(a.wg_id);
      const fb = this.fluxOf(b.wg_id);
      const ha = fa.influx + fa.outflux;
      const hb = fb.influx + fb.outflux;
      if (hb !== ha) return hb - ha; // meiste Korrektur-Historie zuerst
      return this.completeness(a).count - this.completeness(b).count; // unvollständigste zuerst
    });
  });

  isSel(id: string) {
    return this.selected().has(id);
  }
  toggleSel(id: string) {
    const n = new Set(this.selected());
    if (n.has(id)) n.delete(id);
    else n.add(id);
    this.selected.set(n);
  }
  allFilteredSelected() {
    const d = this.filtered();
    return d.length > 0 && d.every((r) => this.selected().has(r.wg_id));
  }
  toggleAllFiltered() {
    const d = this.filtered();
    const n = new Set(this.selected());
    if (this.allFilteredSelected()) d.forEach((r) => n.delete(r.wg_id));
    else d.forEach((r) => n.add(r.wg_id));
    this.selected.set(n);
  }
  selectIncomplete() {
    const n = new Set(this.selected());
    this.filtered().forEach((r) => {
      if (!this.completeness(r).complete) n.add(r.wg_id);
    });
    this.selected.set(n);
  }
  clearSelection() {
    this.selected.set(new Set());
  }

  // --- Schritt 2: Konfiguration --------------------------------------------

  setAction(field: 'beschreibung' | 'examples_enthalten' | 'examples_nicht_enthalten', val: Action) {
    this.plan.set({ ...this.plan(), [field]: val });
  }

  toConfig() {
    if (!this.selected().size) return;
    this.step.set(2);
  }

  // --- Schritt 3: Lauf -----------------------------------------------------

  startRun() {
    const ids = [...this.selected()];
    if (!ids.length) return;
    this.error.set('');
    const body: BulkEnrichRequest = {
      wg_ids: ids,
      plan: this.autoPlan() ? null : this.plan(),
      use_history: this.useHistory(),
    };
    this.api.startBatchApiEnrichmentBatchPost(body).subscribe({
      next: (st) => {
        this.batchId.set(st.id);
        this.status.set(st);
        this.step.set(3);
        this.startPoll();
      },
      error: (e) => this.error.set(formatError(e, 'Anreicherung konnte nicht gestartet werden')),
    });
  }

  private startPoll() {
    this.stopPoll();
    this.tick();
    this.poll = setInterval(() => this.tick(), 1500);
  }
  private stopPoll() {
    if (this.poll) {
      clearInterval(this.poll);
      this.poll = null;
    }
  }
  private tick() {
    const id = this.batchId();
    if (!id) return;
    this.api.batchStatusApiEnrichmentBatchBatchIdStatusGet(id).subscribe({
      next: (st) => {
        this.status.set(st);
        if (st.status === 'done' || st.status === 'failed') {
          this.stopPoll();
          if (st.status === 'done') this.loadDetail();
          else this.error.set(st.error || 'Lauf fehlgeschlagen.');
        }
      },
      error: () => {},
    });
  }

  progressPct(): number {
    const s = this.status();
    if (!s || !s.total) return 0;
    return Math.min(100, Math.round(((s.done ?? 0) / s.total) * 100));
  }

  // --- Resume --------------------------------------------------------------

  private checkResume() {
    this.api.listBatchesApiEnrichmentBatchGet().subscribe({
      next: (bs) => {
        const running = bs.find((b) => b.status === 'running');
        if (running) {
          this.batchId.set(running.id);
          this.status.set(running);
          this.step.set(3);
          this.startPoll();
          return;
        }
        const newest = bs[0];
        if (newest && newest.status === 'done' && (newest.done ?? 0) > 0) this.resumable.set(newest);
      },
      error: () => {},
    });
  }

  openReview(b: EnrichBatchStatus) {
    this.batchId.set(b.id);
    this.status.set(b);
    this.resumable.set(null);
    this.loadDetail();
  }

  // --- Schritt 4: Review ---------------------------------------------------

  loadDetail() {
    const id = this.batchId();
    if (!id) return;
    this.api.batchDetailApiEnrichmentBatchBatchIdGet(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.status.set(d.status);
        this.step.set(4);
      },
      error: (e) => this.error.set(formatError(e, 'Vorschläge konnten nicht geladen werden')),
    });
  }

  protected readonly proposals = computed<EnrichProposal[]>(() => {
    const d = this.detail();
    if (!d) return [];
    const rank = (p: EnrichProposal) => (p.state === 'pending' ? 0 : 1);
    return [...(d.proposals ?? [])].sort((a, b) => {
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
      const ka = a.suggestion.konfidenz ?? 999;
      const kb = b.suggestion.konfidenz ?? 999;
      return ka - kb; // unsichere zuerst
    });
  });

  protected readonly reviewed = computed(
    () => this.proposals().filter((p) => p.state === 'accepted' || p.state === 'rejected').length,
  );

  changed(p: EnrichProposal): boolean {
    const c = p.current;
    const s = p.suggestion;
    return (
      (c.beschreibung || '') !== (s.beschreibung || '') ||
      (c.examples_enthalten || []).join('\n') !== (s.examples_enthalten || []).join('\n') ||
      (c.examples_nicht_enthalten || []).join('\n') !== (s.examples_nicht_enthalten || []).join('\n')
    );
  }

  expand(p: EnrichProposal) {
    if (this.expanded() === p.id) {
      this.expanded.set(null);
      return;
    }
    this.expanded.set(p.id);
    if (!this.propHist()[p.wg_id]) {
      this.api.historySignalApiEnrichmentHistorySignalWgIdGet(p.wg_id).subscribe({
        next: (h) => this.propHist.update((m) => ({ ...m, [p.wg_id]: h })),
        error: () => {},
      });
    }
  }

  isBusy(id: string) {
    return this.rowBusy().has(id);
  }
  private setBusy(id: string, b: boolean) {
    this.rowBusy.update((s) => {
      const n = new Set(s);
      if (b) n.add(id);
      else n.delete(id);
      return n;
    });
  }
  private replaceProp(u: EnrichProposal) {
    this.detail.update((d) => (d ? { ...d, proposals: (d.proposals ?? []).map((p) => (p.id === u.id ? u : p)) } : d));
  }

  onApply(p: EnrichProposal, ev: { content: EnrichContent }) {
    this.setBusy(p.id, true);
    this.error.set('');
    this.api.applyProposalApiEnrichmentProposalProposalIdApplyPost(p.id, { content: ev.content }).subscribe({
      next: (u) => {
        this.setBusy(p.id, false);
        this.replaceProp(u);
        this.expanded.set(null);
      },
      error: (e) => {
        this.setBusy(p.id, false);
        this.error.set(formatError(e, 'Übernehmen fehlgeschlagen'));
      },
    });
  }

  onReject(p: EnrichProposal) {
    this.setBusy(p.id, true);
    this.api.rejectProposalApiEnrichmentProposalProposalIdRejectPost(p.id).subscribe({
      next: (u) => {
        this.setBusy(p.id, false);
        this.replaceProp(u);
        this.expanded.set(null);
      },
      error: (e) => {
        this.setBusy(p.id, false);
        this.error.set(formatError(e, 'Verwerfen fehlgeschlagen'));
      },
    });
  }

  onRefine(p: EnrichProposal, ev: { annotations: FieldAnnotations; content: EnrichContent }) {
    this.setBusy(p.id, true);
    this.error.set('');
    this.api
      .refineProposalApiEnrichmentProposalProposalIdRefinePost(p.id, { annotations: ev.annotations, content: ev.content })
      .subscribe({
        next: (u) => {
          this.setBusy(p.id, false);
          this.replaceProp(u);
        },
        error: (e) => {
          this.setBusy(p.id, false);
          this.error.set(formatError(e, 'Überarbeitung fehlgeschlagen'));
        },
      });
  }

  acceptAllHigh() {
    const ps = this.proposals().filter(
      (p) => p.state === 'pending' && (p.suggestion.konfidenz ?? 0) >= 85 && this.changed(p),
    );
    for (const p of ps) {
      const content: EnrichContent = {
        beschreibung: p.suggestion.beschreibung ?? null,
        examples_enthalten: p.suggestion.examples_enthalten ?? [],
        examples_nicht_enthalten: p.suggestion.examples_nicht_enthalten ?? [],
      };
      this.onApply(p, { content });
    }
  }

  highConfidenceCount(): number {
    return this.proposals().filter(
      (p) => p.state === 'pending' && (p.suggestion.konfidenz ?? 0) >= 85 && this.changed(p),
    ).length;
  }

  // --- Navigation ----------------------------------------------------------

  restart() {
    this.stopPoll();
    this.batchId.set(null);
    this.status.set(null);
    this.detail.set(null);
    this.expanded.set(null);
    this.selected.set(new Set());
    this.error.set('');
    this.step.set(1);
    this.loadCatalog();
    this.checkResume();
  }
}
