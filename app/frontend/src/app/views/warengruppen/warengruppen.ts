import { Component, OnInit, ViewChild, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatSort, MatSortModule } from '@angular/material/sort';
import * as XLSX from 'xlsx';
import {
  EmissionsfaktorRow,
  EnrichContent,
  EnrichmentService,
  EnrichPlan,
  EnrichRefineRequest,
  EnrichRequest,
  EnrichSuggestion,
  FieldAnnotations,
  HistorySignal,
  ImportResult,
  WarengruppeRow,
  WarengruppeUpsertRequest,
  WarengruppenService,
} from '../../../api';
import { formatError } from '../../util/error';
import { EnrichReviewComponent } from '../../shared/enrich-review';

/** Editable form model — examples are edited as newline-separated text. */
interface EditModel {
  wg_id: string; // empty while creating
  wg_name: string;
  beschreibung: string;
  examples_enthalten: string;
  examples_nicht_enthalten: string;
  emissionsfaktoren: EmissionsfaktorRow[];
  aktiv: boolean; // status; toggled via the activate/deactivate endpoints, not save()
}

/** Statusfilter für die Tabelle. */
type StatusFilter = 'alle' | 'aktiv' | 'inaktiv';

@Component({
  selector: 'view-warengruppen',
  standalone: true,
  imports: [CommonModule, FormsModule, MatTableModule, MatSortModule, EnrichReviewComponent],
  templateUrl: './warengruppen.html',
  styleUrl: './warengruppen.scss',
})
export class WarengruppenView implements OnInit {
  private readonly api = inject(WarengruppenService);
  private readonly enrichApi = inject(EnrichmentService);

  protected readonly rows = signal<WarengruppeRow[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  /** Nicht-fehlerhafte Hinweise (z. B. beim Bulk-Löschen blockierte, referenzierte WGs). */
  protected readonly notice = signal('');
  protected readonly search = signal('');
  /** Statusfilter: alle / nur aktive / nur inaktive. */
  protected readonly statusFilter = signal<StatusFilter>('alle');

  protected readonly editing = signal<EditModel | null>(null);
  protected readonly isNew = signal(false);
  protected readonly saving = signal(false);
  protected readonly pendingDelete = signal<string | null>(null);
  /** Läuft gerade ein (De-)Aktivieren für die im Modal offene Warengruppe? */
  protected readonly togglingActive = signal(false);

  /** Mehrfachauswahl für gebündeltes Löschen / (De-)Aktivieren (Set der wg_ids). */
  protected readonly selected = signal<Set<string>>(new Set());
  protected readonly pendingBulkDelete = signal(false);
  protected readonly bulkDeleting = signal(false);

  /** Bulk-Import (XLSX/CSV-Upload). */
  protected readonly importOpen = signal(false);
  protected readonly importing = signal(false);
  protected readonly importResult = signal<ImportResult | null>(null);
  protected readonly importError = signal('');

  /** Atomares KI-Vorschlags-Overlay (über dem Edit-Modal). */
  protected readonly enrichOpen = signal(false);
  protected readonly enrichBusy = signal(false);
  protected readonly enrichSuggestion = signal<EnrichSuggestion | null>(null);
  protected readonly enrichHistory = signal<HistorySignal | null>(null);
  protected readonly enrichError = signal('');
  /** Snapshot der Feldwerte beim Öffnen — stabil, damit die Ist-Spalte nicht bei
   *  jeder Change-Detection neu entsteht (sonst würde die Bearbeitung im Panel überschrieben). */
  protected readonly enrichCurrentContent = signal<EnrichContent>({
    beschreibung: null,
    examples_enthalten: [],
    examples_nicht_enthalten: [],
  });
  private enrichUseHistory = false;

  /** Klick-Popover für die Beispiel-Listen (ENTHÄLT / NICHT ENTHÄLT). */
  protected readonly examplesPopover = signal<{
    row: WarengruppeRow;
    top: number;
    left: number;
  } | null>(null);

  /** Spalten der Material-DataTable. Der Aktiv/Inaktiv-Status wird über die
   *  Zeilenfarbe angezeigt (keine eigene Spalte), das (De-)Aktivieren läuft
   *  ausschließlich über das Edit-Modal. */
  protected readonly displayedColumns = ['select', 'wg_id', 'wg_name', 'beschreibung', 'beispiele', 'ef', 'actions'];

  /** Quelle der mat-table — sortier- und filterbar, gespeist aus dem rows()-Signal. */
  protected readonly dataSource = new MatTableDataSource<WarengruppeRow>([]);

  /** MatSort steht in einem @if-Block — per Setter binden, sobald die Tabelle existiert. */
  @ViewChild(MatSort) set matSort(ms: MatSort | undefined) {
    if (ms) this.dataSource.sort = ms;
  }

  constructor() {
    // Sortierwerte: ID/Name alphabetisch, Emissionsfaktor numerisch (neuestes Jahr).
    this.dataSource.sortingDataAccessor = (row, col) => {
      switch (col) {
        case 'wg_id':
          return (row.wg_id ?? '').toLowerCase();
        case 'wg_name':
          return (row.wg_name ?? '').toLowerCase();
        case 'ef':
          return this.latestEf(row)?.wert ?? -Infinity;
        default:
          return '';
      }
    };
    // Kombinierter Filter (Text + Status): der filter-String ist ein JSON-Objekt
    // { q, status }, damit sich beide Dimensionen über den einen MatTable-Filter
    // abbilden lassen. Text sucht über Name, ID und Beschreibung.
    this.dataSource.filterPredicate = (row, filter) => {
      let q = '';
      let status: StatusFilter = 'alle';
      try {
        const f = JSON.parse(filter) as { q?: string; status?: StatusFilter };
        q = f.q ?? '';
        status = f.status ?? 'alle';
      } catch {
        q = filter; // Fallback, falls einmal ein reiner String gesetzt wird
      }
      const textOk =
        !q ||
        row.wg_name.toLowerCase().includes(q) ||
        row.wg_id.toLowerCase().includes(q) ||
        (row.beschreibung ?? '').toLowerCase().includes(q);
      const statusOk =
        status === 'alle' ||
        (status === 'aktiv' && row.aktiv) ||
        (status === 'inaktiv' && !row.aktiv);
      return textOk && statusOk;
    };
    // search()/statusFilter()-Signale → DataSource-Filter spiegeln. Der String ist
    // immer nicht-leer, damit das Prädikat auch bei reinem Statusfilter läuft.
    effect(() => {
      this.dataSource.filter = JSON.stringify({
        q: this.search().trim().toLowerCase(),
        status: this.statusFilter(),
      });
    });
  }

  ngOnInit() {
    this.reload();
  }

  reload() {
    this.loading.set(true);
    this.clearSelection();
    this.error.set('');
    this.api.listWarengruppenApiWarengruppenGet().subscribe({
      next: (rs) => {
        this.rows.set(rs);
        this.dataSource.data = rs;
        this.loading.set(false);
      },
      error: (e) => {
        this.loading.set(false);
        this.error.set(formatError(e, 'Katalog konnte nicht geladen werden'));
      },
    });
  }

  openExamples(row: WarengruppeRow, ev: MouseEvent) {
    ev.stopPropagation();
    const cur = this.examplesPopover();
    if (cur && cur.row.id === row.id) {
      this.examplesPopover.set(null);
      return;
    }
    const r = (ev.currentTarget as HTMLElement).getBoundingClientRect();
    this.examplesPopover.set({ row, top: r.bottom + 6, left: r.left });
  }

  closeExamples() {
    this.examplesPopover.set(null);
  }

  /** Most-recent-year emission factor for the list column. */
  latestEf(row: WarengruppeRow): EmissionsfaktorRow | null {
    const efs = row.emissionsfaktoren ?? [];
    if (!efs.length) return null;
    return efs.reduce((a, b) => (b.jahr > a.jahr ? b : a));
  }

  formatEf(v: number): string {
    return v.toLocaleString('de-DE', { maximumFractionDigits: 4 });
  }

  startCreate() {
    this.error.set('');
    this.pendingDelete.set(null);
    this.isNew.set(true);
    this.editing.set({
      wg_id: '',
      wg_name: '',
      beschreibung: '',
      examples_enthalten: '',
      examples_nicht_enthalten: '',
      emissionsfaktoren: [{ jahr: new Date().getFullYear(), wert: 0 }],
      aktiv: true,
    });
  }

  startEdit(row: WarengruppeRow) {
    this.error.set('');
    this.pendingDelete.set(null);
    this.isNew.set(false);
    this.editing.set({
      wg_id: row.wg_id,
      wg_name: row.wg_name,
      beschreibung: row.beschreibung ?? '',
      examples_enthalten: (row.examples_enthalten ?? []).join('\n'),
      examples_nicht_enthalten: (row.examples_nicht_enthalten ?? []).join('\n'),
      emissionsfaktoren: (row.emissionsfaktoren ?? [])
        .slice()
        .sort((a, b) => a.jahr - b.jahr)
        .map((e) => ({ jahr: e.jahr, wert: e.wert })),
      aktiv: row.aktiv ?? true, // Feld ist im generierten Client optional
    });
  }

  cancel() {
    this.editing.set(null);
    this.pendingDelete.set(null);
    this.error.set('');
  }

  addEf() {
    const e = this.editing();
    if (!e) return;
    const maxYear = e.emissionsfaktoren.reduce((m, ef) => Math.max(m, ef.jahr || 0), 0);
    const nextYear = maxYear ? maxYear + 1 : new Date().getFullYear();
    this.editing.set({
      ...e,
      emissionsfaktoren: [...e.emissionsfaktoren, { jahr: nextYear, wert: 0 }],
    });
  }

  removeEf(index: number) {
    const e = this.editing();
    if (!e) return;
    this.editing.set({
      ...e,
      emissionsfaktoren: e.emissionsfaktoren.filter((_, i) => i !== index),
    });
  }

  private toLines(s: string): string[] {
    return s
      .split('\n')
      .map((x) => x.trim())
      .filter(Boolean);
  }

  save() {
    const e = this.editing();
    if (!e) return;
    if (!e.wg_name.trim()) {
      this.error.set('Der Warengruppen-Name ist erforderlich.');
      return;
    }
    const payload: WarengruppeUpsertRequest = {
      wg_name: e.wg_name.trim(),
      beschreibung: e.beschreibung.trim() || null,
      examples_enthalten: this.toLines(e.examples_enthalten),
      examples_nicht_enthalten: this.toLines(e.examples_nicht_enthalten),
      emissionsfaktoren: e.emissionsfaktoren
        .filter((ef) => ef.jahr != null && ef.wert != null && !isNaN(ef.jahr) && !isNaN(ef.wert))
        .map((ef) => ({ jahr: Number(ef.jahr), wert: Number(ef.wert) })),
    };

    this.saving.set(true);
    this.error.set('');
    const obs = this.isNew()
      ? this.api.createWarengruppeApiWarengruppenPost(payload)
      : this.api.updateWarengruppeApiWarengruppenWgIdPut(e.wg_id, payload);
    obs.subscribe({
      next: () => {
        this.saving.set(false);
        this.editing.set(null);
        this.reload();
      },
      error: (err) => {
        this.saving.set(false);
        this.error.set(formatError(err, 'Speichern fehlgeschlagen'));
      },
    });
  }

  doDelete(wgId: string) {
    this.api.deleteWarengruppeApiWarengruppenWgIdDelete(wgId).subscribe({
      next: () => {
        this.pendingDelete.set(null);
        this.editing.set(null);
        this.reload();
      },
      error: (err) => {
        // 409 = historisch referenziert; die Backend-Meldung verweist auf „Deaktivieren".
        this.pendingDelete.set(null);
        this.error.set(formatError(err, 'Löschen fehlgeschlagen'));
      },
    });
  }

  // --- Aktivieren / Deaktivieren (Soft-Delete) -----------------------------
  // Statuswechsel ist bewusst nur aus dem Edit-Modal möglich (kein Zeilen- oder
  // Bulk-Toggle), damit ein (De-)Aktivieren eine gezielte Einzelaktion bleibt.

  /** Ruft den passenden activate/deactivate-Endpunkt für eine wg_id auf. */
  private setActive(wgId: string, aktiv: boolean) {
    return aktiv
      ? this.api.activateWarengruppeApiWarengruppenWgIdActivatePost(wgId)
      : this.api.deactivateWarengruppeApiWarengruppenWgIdDeactivatePost(wgId);
  }

  /** Toggle aus dem Edit-Modal — hält das Modal offen und aktualisiert den Status. */
  toggleActiveEditing() {
    const e = this.editing();
    if (!e || this.isNew()) return;
    this.togglingActive.set(true);
    this.error.set('');
    this.setActive(e.wg_id, !e.aktiv).subscribe({
      next: (updated) => {
        this.togglingActive.set(false);
        this.editing.set({ ...e, aktiv: updated.aktiv ?? !e.aktiv });
        this.reload();
      },
      error: (err) => {
        this.togglingActive.set(false);
        this.error.set(formatError(err, 'Statuswechsel fehlgeschlagen'));
      },
    });
  }

  // --- Mehrfachauswahl & Bulk-Löschen --------------------------------------

  isSelected(wgId: string): boolean {
    return this.selected().has(wgId);
  }

  toggleRow(wgId: string, ev?: Event) {
    ev?.stopPropagation();
    const next = new Set(this.selected());
    if (next.has(wgId)) next.delete(wgId);
    else next.add(wgId);
    this.selected.set(next);
  }

  /** Sind alle aktuell gefilterten Zeilen ausgewählt? */
  allFilteredSelected(): boolean {
    const data = this.dataSource.filteredData;
    if (!data.length) return false;
    const sel = this.selected();
    return data.every((r) => sel.has(r.wg_id));
  }

  /** Teilauswahl (für den indeterminate-Zustand der Kopf-Checkbox). */
  someFilteredSelected(): boolean {
    const data = this.dataSource.filteredData;
    const sel = this.selected();
    const n = data.reduce((acc, r) => acc + (sel.has(r.wg_id) ? 1 : 0), 0);
    return n > 0 && n < data.length;
  }

  toggleAll() {
    const data = this.dataSource.filteredData;
    const next = new Set(this.selected());
    if (this.allFilteredSelected()) {
      data.forEach((r) => next.delete(r.wg_id));
    } else {
      data.forEach((r) => next.add(r.wg_id));
    }
    this.selected.set(next);
  }

  clearSelection() {
    this.selected.set(new Set());
    this.pendingBulkDelete.set(false);
  }

  doBulkDelete() {
    const ids = [...this.selected()];
    if (!ids.length) return;
    this.bulkDeleting.set(true);
    this.error.set('');
    this.notice.set('');
    this.api
      .bulkDeleteWarengruppenApiWarengruppenBulkDeletePost({ wg_ids: ids })
      .subscribe({
        next: (res) => {
          this.bulkDeleting.set(false);
          // Referenzierte WGs werden nicht gelöscht, sondern separat gemeldet.
          if (res.blocked?.length) {
            this.notice.set(
              `${res.blocked.length} Warengruppe(n) wurden nicht gelöscht, weil sie ` +
                `historisch referenziert sind (${res.blocked.join(', ')}). ` +
                `Bitte stattdessen deaktivieren.`
            );
          }
          this.reload(); // setzt Auswahl & pendingBulkDelete zurück (lässt notice stehen)
        },
        error: (err) => {
          this.bulkDeleting.set(false);
          this.pendingBulkDelete.set(false);
          this.error.set(formatError(err, 'Löschen fehlgeschlagen'));
        },
      });
  }

  // --- Bulk-Import ----------------------------------------------------------

  openImport() {
    this.importResult.set(null);
    this.importError.set('');
    this.importOpen.set(true);
  }

  closeImport() {
    this.importOpen.set(false);
  }

  onImportFile(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.importing.set(true);
    this.importResult.set(null);
    this.importError.set('');
    this.api.importWarengruppenApiWarengruppenImportPost(file).subscribe({
      next: (res) => {
        this.importing.set(false);
        this.importResult.set(res);
        this.reload();
      },
      error: (err) => {
        this.importing.set(false);
        this.importError.set(formatError(err, 'Import fehlgeschlagen'));
      },
    });
    input.value = ''; // erlaubt erneutes Wählen derselben Datei
  }

  // --- Atomares KI-Enrichment (Vorschlags-Overlay) -------------------------

  /** Aktuelle (ggf. ungespeicherte) Feldwerte des Edit-Modals als EnrichContent. */
  private snapshotContent(): EnrichContent {
    const e = this.editing();
    return {
      beschreibung: e?.beschreibung?.trim() || null,
      examples_enthalten: e ? this.toLines(e.examples_enthalten) : [],
      examples_nicht_enthalten: e ? this.toLines(e.examples_nicht_enthalten) : [],
    };
  }

  openEnrich() {
    const e = this.editing();
    if (!e) return;
    this.enrichCurrentContent.set(this.snapshotContent());
    this.enrichSuggestion.set(null);
    this.enrichError.set('');
    this.enrichHistory.set(null);
    this.enrichUseHistory = false;
    this.enrichOpen.set(true);
    // Historien-Signal nur für bereits gespeicherte Warengruppen (mit wg_id).
    if (e.wg_id) {
      this.enrichApi.historySignalApiEnrichmentHistorySignalWgIdGet(e.wg_id).subscribe({
        next: (h) => this.enrichHistory.set(h),
        error: () => {},
      });
    }
  }

  closeEnrich() {
    this.enrichOpen.set(false);
    this.enrichBusy.set(false);
  }

  enrichGenerate(ev: { plan: EnrichPlan; useHistory: boolean }) {
    const e = this.editing();
    if (!e) return;
    this.enrichUseHistory = ev.useHistory;
    this.enrichBusy.set(true);
    this.enrichError.set('');
    const body: EnrichRequest = {
      wg_name: e.wg_name,
      content: this.enrichCurrentContent(),
      plan: ev.plan,
      use_history: ev.useHistory,
      wg_id: e.wg_id || null,
    };
    this.enrichApi.previewApiEnrichmentPreviewPost(body).subscribe({
      next: (s) => {
        this.enrichBusy.set(false);
        this.enrichSuggestion.set(s);
      },
      error: (err) => {
        this.enrichBusy.set(false);
        this.enrichError.set(formatError(err, 'KI-Vorschlag fehlgeschlagen'));
      },
    });
  }

  enrichRefine(ev: { annotations: FieldAnnotations; content: EnrichContent }) {
    const e = this.editing();
    if (!e) return;
    this.enrichBusy.set(true);
    this.enrichError.set('');
    const body: EnrichRefineRequest = {
      wg_name: e.wg_name,
      current: ev.content,
      annotations: ev.annotations,
      use_history: this.enrichUseHistory,
      wg_id: e.wg_id || null,
    };
    this.enrichApi.refineApiEnrichmentRefinePost(body).subscribe({
      next: (s) => {
        this.enrichBusy.set(false);
        this.enrichSuggestion.set(s);
      },
      error: (err) => {
        this.enrichBusy.set(false);
        this.enrichError.set(formatError(err, 'Überarbeitung fehlgeschlagen'));
      },
    });
  }

  /** Übernahme in das Formular — der Nutzer speichert danach regulär via save(). */
  enrichApply(ev: { content: EnrichContent }) {
    const e = this.editing();
    if (!e) return;
    this.editing.set({
      ...e,
      beschreibung: ev.content.beschreibung ?? '',
      examples_enthalten: (ev.content.examples_enthalten ?? []).join('\n'),
      examples_nicht_enthalten: (ev.content.examples_nicht_enthalten ?? []).join('\n'),
    });
    this.closeEnrich();
  }

  /** Spalten der Import-Vorlage — muss zum Backend-Kontrakt passen. */
  private readonly templateHeader: string[] = [
    'wg_id',
    'wg_name',
    'beschreibung',
    'beispiele_enthalten',
    'beispiele_nicht_enthalten',
    'e_2024',
    'e_2025',
  ];

  /** Vorlage als Array-of-Arrays: Kopfzeile + zwei Beispielzeilen (mit/ohne ID). */
  private templateAoa(): (string | number)[][] {
    return [
      this.templateHeader,
      [
        'wg-100',
        'Büromöbel',
        'Möbel für Büroräume',
        'Bürostühle | Schreibtische | Regale',
        'EDV-Hardware | Software',
        0.1234,
        0.1189,
      ],
      [
        '',
        'Neue Warengruppe (ID wird automatisch erzeugt)',
        'Beschreibung optional',
        'Beispiel A | Beispiel B',
        'Gegenbeispiel',
        0.2,
        0.19,
      ],
    ];
  }

  downloadTemplate(fmt: 'xlsx' | 'csv') {
    const ws = XLSX.utils.aoa_to_sheet(this.templateAoa());
    if (fmt === 'xlsx') {
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Warengruppen');
      XLSX.writeFile(wb, 'warengruppen-vorlage.xlsx');
      return;
    }
    // CSV: Semikolon als Spaltentrenner (kollidiert nicht mit dem Pipe-Listentrenner);
    // BOM, damit Excel die Umlaute als UTF-8 liest.
    const csv = XLSX.utils.sheet_to_csv(ws, { FS: ';' });
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'warengruppen-vorlage.csv';
    a.click();
    URL.revokeObjectURL(url);
  }
}
