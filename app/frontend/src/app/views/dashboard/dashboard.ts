import { Component, computed, inject, isDevMode, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import * as XLSX from 'xlsx';
import { DashboardResponse, DashboardService, PredictionRow } from '../../../api';
import { AppState } from '../../state';
import { TipComponent } from '../../shared/tip';
import { SelectComponent } from '../../shared/select';

type PredictionRowWithFinal = PredictionRow & {
  _decision?: 'ok' | 'reject' | 'new_wg';
  _selected_wg?: string | null;
};

// Minimal layout model for inline SVG Sankey rendering.
type SankeyNode = {
  name: string;
  side: 'left' | 'right';
  value: number;
  x: number;
  y: number;
  rectY: number;
  height: number;
  labelHeight: number;
  slotHeight: number;
};

type SankeyLink = {
  source: string;
  target: string;
  value: number;
  label: string;
  items: string[];
  strokeWidth: number;
  path: string;
  color: string;
};

type SankeyLayout = {
  width: number;
  height: number;
  unitLabel: string;
  totalChanges: number;
  nodes: SankeyNode[];
  links: SankeyLink[];
};

@Component({
  selector: 'view-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, TipComponent, SelectComponent],
  templateUrl: './dashboard.html',
  styles: `
    .sankey-wrap{overflow:auto}
    .sankey-svg{width:100%;min-width:900px;height:auto;display:block}
    .sankey-node{fill:var(--bg-card);stroke:var(--bd);stroke-width:1}
    .sankey-node.right{fill:color-mix(in srgb, var(--blue) 9%, var(--bg-card))}
    .sankey-node.left{fill:color-mix(in srgb, var(--green) 10%, var(--bg-card))}
    .sankey-link{fill:none;stroke-linecap:round;opacity:.7;transition:opacity .2s ease}
    .sankey-link:hover{opacity:.95}
    .sankey-label-box{overflow:visible}
    .sankey-label-card{display:flex;flex-direction:column;gap:4px;line-height:1.25;overflow-wrap:anywhere;word-break:break-word}
    .sankey-label-card.left{text-align:right;align-items:flex-end}
    .sankey-label-card.right{text-align:left;align-items:flex-start}
    .sankey-label-name{color:var(--t1);font-size:12px;font-weight:600}
    .sankey-label-meta{color:var(--t2);font-size:11px}
    .sankey-empty{display:grid;place-items:center;min-height:320px;text-align:center}
  `,
})
export class DashboardView {
  private readonly api = inject(DashboardService);
  private readonly http = inject(HttpClient);
  protected readonly state = inject(AppState);

  protected readonly tab = signal<'co2' | 'eur'>('co2');
  protected readonly loading = signal(false);
  protected readonly selectedYear = signal<number | null>(null);

  constructor() {
    // Daten erst laden, wenn die KI-Prüfung in dieser Sitzung gelaufen ist.
    // Sonst würde das Dashboard den (geteilten) In-Memory-Stand einer früheren
    // Analyse zeigen, bevor der Nutzer überhaupt eine Excel hochgeladen hat.
    if (this.state.prediction()) {
      this.refresh();
    } else if (isDevMode()) {
      // Im Dev-Modus weiterhin Beispiel-Daten, damit das Dashboard isoliert testbar bleibt.
      this.loadMockDashboard();
    }
  }

  refresh(year?: number | null) {
    const effectiveYear = year === undefined ? this.selectedYear() : year;
    this.selectedYear.set(effectiveYear ?? null);
    this.loading.set(true);
    const params = new HttpParams({
      fromObject: effectiveYear != null ? { jahr: String(effectiveYear) } : {},
    });
    this.http.get<DashboardResponse>('/api/dashboard', { params }).subscribe({
      next: (r) => {
        // Dev-Mode: erreichbares, aber leeres Backend (keine Analyse gelaufen) → Mock statt leerem Dashboard
        if (isDevMode() && !r?.top_wg?.length) {
          this.loadMockDashboard();
        } else {
          this.state.dashboard.set(r);
          this.selectedYear.set(r?.selected_year ?? effectiveYear ?? null);
          this.loading.set(false);
        }
      },
      // Dev-Mode: Backend nicht erreichbar → Beispiel-Daten laden (wie in der Review-View)
      error: () => {
        if (isDevMode()) {
          this.loadMockDashboard();
        } else {
          this.loading.set(false);
        }
      },
    });
  }

  private loadMockDashboard() {
    import('../../dev/mock-data').then(({ MOCK_DASHBOARD }) => {
      this.state.dashboard.set(MOCK_DASHBOARD);
      this.loading.set(false);
    });
  }

  setTab(t: 'co2' | 'eur') {
    this.tab.set(t);
  }

  onYearChange(year: number | null) {
    this.refresh(year);
  }

  protected readonly yearOptions = computed(() => {
    const years = [...(this.state.dashboard()?.available_years ?? [])]
      .filter((y): y is number => typeof y === 'number' && Number.isFinite(y))
      .sort((a, b) => b - a);
    return [{ value: null, label: 'Aktuell (neueste EF)' }, ...years.map((y) => ({ value: y, label: String(y) }))];
  });

  protected readonly kpis = computed(() => this.state.dashboard()?.kpis);
  protected readonly funnel = computed(() => this.state.dashboard()?.funnel);
  protected readonly topWg = computed(() => this.state.dashboard()?.top_wg ?? []);
  protected readonly predictionRows = computed<PredictionRowWithFinal[]>(
    () => (this.state.prediction()?.rows ?? []) as PredictionRowWithFinal[],
  );

  /** Detailtabelle: nach Betrag (€) absteigend sortiert — größter Betrag zuerst. */
  protected readonly detailRows = computed(() =>
    [...this.topWg()].sort((a, b) => b.eur_after - a.eur_after),
  );

  /**
   * Balkendiagramm (req 4.2): Top-10 Warengruppen nach der aktiven Metrik
   * (CO₂e nachher bzw. Ausgaben), absteigend sortiert, Breite relativ zum Maximum.
   */
  protected readonly barChart = computed(() => {
    const co2 = this.tab() === 'co2';
    const items = this.topWg()
      .map((r) => ({ name: r.wg_name, value: co2 ? r.co2_after_t : r.eur_after }))
      .filter((d) => d.value > 0)
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
    const max = items.reduce((m, d) => Math.max(m, d.value), 0) || 1;
    return items.map((d) => ({ ...d, pct: (d.value / max) * 100 }));
  });

  /**
   * Histogramm (req 4.4): Emissionsrate je WG = Gesamtwert (CO₂e bzw. €) / Anzahl Bestellungen.
   * `regrouped_count` ist backend-seitig die Gruppengröße (Anzahl Zeilen je WG, req 4.4.2).
   * Absteigend nach Rate sortiert (req 4.4.3), Top-10.
   */
  protected readonly histogram = computed(() => {
    const co2 = this.tab() === 'co2';
    const items = this.topWg()
      .map((r) => {
        const total = co2 ? r.co2_after_t : r.eur_after;
        const count = r.regrouped_count || 0;
        return { name: r.wg_name, count, rate: count > 0 ? total / count : 0 };
      })
      .filter((d) => d.rate > 0)
      .sort((a, b) => b.rate - a.rate)
      .slice(0, 10);
    const max = items.reduce((m, d) => Math.max(m, d.rate), 0) || 1;
    return items.map((d) => ({ ...d, pct: (d.rate / max) * 100 }));
  });

  // Build flows from original WG to final reviewed WG.
  protected readonly sankey = computed<SankeyLayout | null>(() => {
    const rows = this.predictionRows()
      .map((row) => {
        const source = row.current_wg_name?.trim();
        const target = this.finalWg(row);
        const item = row.bestelltext?.trim() || `Zeile ${row.row_index}`;
        return source && target && source !== target ? { source, target, item } : null;
      })
      .filter((row): row is { source: string; target: string; item: string } => row != null);

    if (!rows.length) return null;

    const grouped = new Map<string, { source: string; target: string; value: number; items: string[] }>();
    for (const row of rows) {
      const key = `${row.source}__${row.target}`;
      const current = grouped.get(key);
      if (current) {
        current.value += 1;
        current.items.push(row.item);
      } else {
        grouped.set(key, { source: row.source, target: row.target, value: 1, items: [row.item] });
      }
    }

    const flows = [...grouped.values()].sort((a, b) => b.value - a.value).slice(0, 12);
    if (!flows.length) return null;

    const sourceTotals = new Map<string, number>();
    const targetTotals = new Map<string, number>();
    for (const flow of flows) {
      sourceTotals.set(flow.source, (sourceTotals.get(flow.source) ?? 0) + flow.value);
      targetTotals.set(flow.target, (targetTotals.get(flow.target) ?? 0) + flow.value);
    }

    const width = 1100;
    const nodeWidth = 16;
    const padTop = 28;
    const padBottom = 24;
    const gap = 14;
    const leftX = 170;
    const rightX = width - 170 - nodeWidth;
    const total = flows.reduce((sum, flow) => sum + flow.value, 0);
    const maxNodes = Math.max(sourceTotals.size, targetTotals.size);
    const innerHeight = Math.max(320, flows.length * 44, maxNodes * 56);
    const usableHeight = innerHeight - Math.max(0, maxNodes - 1) * gap;
    const pxPerUnit = usableHeight / total;

    const leftLayout = this.layoutSankeyNodes(sourceTotals, 'left', leftX, padTop, gap, pxPerUnit);
    const rightLayout = this.layoutSankeyNodes(
      targetTotals,
      'right',
      rightX,
      padTop,
      gap,
      pxPerUnit,
    );
    const leftNodes = leftLayout.nodes;
    const rightNodes = rightLayout.nodes;
    const height = Math.max(leftLayout.endY, rightLayout.endY) + padBottom;
    const leftOffsets = new Map<string, number>();
    const rightOffsets = new Map<string, number>();

    // Stack link segments within each source/target node.
    const links = flows.map((flow, index) => {
      const left = leftNodes.get(flow.source)!;
      const right = rightNodes.get(flow.target)!;
      const thickness = Math.max(8, flow.value * pxPerUnit);
      const leftOffset = leftOffsets.get(flow.source) ?? 0;
      const rightOffset = rightOffsets.get(flow.target) ?? 0;
      const y1 = left.rectY + leftOffset + thickness / 2;
      const y2 = right.rectY + rightOffset + thickness / 2;
      leftOffsets.set(flow.source, leftOffset + thickness);
      rightOffsets.set(flow.target, rightOffset + thickness);
      const x1 = left.x + nodeWidth;
      const x2 = right.x;
      const cx = (x2 - x1) * 0.42;

      return {
        source: flow.source,
        target: flow.target,
        value: flow.value,
        label: `${flow.source} → ${flow.target}: ${this.fmt((flow.value / total) * 100, { maximumFractionDigits: 1 })}% (${flow.value}/${total})`,
        items: flow.items,
        strokeWidth: thickness,
        path: `M ${x1} ${y1} C ${x1 + cx} ${y1}, ${x2 - cx} ${y2}, ${x2} ${y2}`,
        color: this.linkColor(index),
      };
    });

      return {
      width,
      height,
      unitLabel: 'Anteil aller Umgruppierungen',
      totalChanges: total,
      nodes: [...leftNodes.values(), ...rightNodes.values()],
      links,
    };
  });

  // Final WG after review decisions.
  private finalWg(row: PredictionRowWithFinal) {
    if (row._decision === 'ok') return row.suggested_wg_name?.trim() ?? null;
    if (row._decision === 'new_wg') return row._selected_wg?.trim() ?? null;
    return null;
  }

  // Reserve vertical slot for node bar + wrapped label block.
  private layoutSankeyNodes(
    totals: Map<string, number>,
    side: 'left' | 'right',
    x: number,
    startY: number,
    gap: number,
    pxPerUnit: number,
  ) {
    const entries = [...totals.entries()].sort((a, b) => b[1] - a[1]);
    const nodes = new Map<string, SankeyNode>();
    let y = startY;
    for (const [name, value] of entries) {
      const height = Math.max(18, value * pxPerUnit);
      const labelLines = this.wrapSankeyLabel(name, 22);
      const labelHeight = labelLines.length * 15 + 18;
      const slotHeight = Math.max(height, labelHeight);
      const rectY = y + Math.max(0, (slotHeight - height) / 2);
      nodes.set(name, {
        name,
        side,
        value,
        x,
        y,
        rectY,
        height,
        labelHeight,
        slotHeight,
      });
      y += slotHeight + gap;
    }
    return { nodes, endY: y - gap };
  }

  // Keep labels inside the visible viewport.
  protected nodeLabelX(node: SankeyNode) {
    return node.side === 'left' ? Math.max(8, node.x - this.nodeLabelWidth() - 14) : node.x + 28;
  }

  protected nodeLabelWidth() {
    return 150;
  }

  protected nodeLabelY(node: SankeyNode) {
    return node.y;
  }

  protected nodeLabelHeight(node: SankeyNode) {
    return node.labelHeight;
  }

  protected nodeLabelMeta(node: SankeyNode, totalChanges: number) {
    return `${this.fmt(node.value, { maximumFractionDigits: 0 })} · ${this.fmt((node.value / totalChanges) * 100, { maximumFractionDigits: 1 })}%`;
  }

  protected linkTooltip(link: SankeyLink) {
    return `${link.label}\n\nBetroffene Billing Items:\n${link.items.map((item) => `- ${item}`).join('\n')}`;
  }

  // Heuristic line count for label box height.
  private wrapSankeyLabel(label: string, maxChars: number) {
    const words = label.split(/\s+/).filter(Boolean);
    if (!words.length) return [''];
    const lines: string[] = [];
    let current = '';
    for (const word of words) {
      const next = current ? `${current} ${word}` : word;
      if (next.length <= maxChars || !current) {
        current = next;
        continue;
      }
      lines.push(current);
      current = word;
    }
    if (current) lines.push(current);
    return lines;
  }

  private linkColor(index: number) {
    const palette = [
      '#0f766e',
      '#0284c7',
      '#65a30d',
      '#d97706',
      '#7c3aed',
      '#db2777',
      '#0891b2',
      '#4f46e5',
    ];
    return palette[index % palette.length];
  }

  fmt(n: number | undefined, opts?: Intl.NumberFormatOptions) {
    if (n == null) return '—';
    return n.toLocaleString('de-DE', opts);
  }

  exportExcel() {
    const wb = XLSX.utils.book_new();
    const date = new Date().toISOString().slice(0, 10);

    // Sheet 1: KPIs
    const k = this.kpis();
    const f = this.funnel();
    const kpiRows = [
      ['KPI', 'Wert'],
      ['CO₂e vorher (t)', k?.co2_before_t ?? ''],
      ['CO₂e nachher (t)', k?.co2_after_t ?? ''],
      ['CO₂e Korrektur (%)', k?.co2_delta_pct ?? ''],
      ['Nicht berechenbar', k?.not_calculable ?? ''],
      ['Umgruppierungsrate (%)', k?.regroup_rate_pct ?? ''],
      ['Gesamtausgaben (€)', k?.eur_total ?? ''],
      ['Top-WG Anteil (%)', k?.top_wg_share_pct ?? ''],
      ['Ausgaben umgruppiert (€)', k?.eur_regrouped ?? ''],
      ['Ø EUR / Eintrag', k?.eur_avg_per_entry ?? ''],
      [],
      ['Analyse-Trichter', ''],
      ['Upload gesamt', f?.total ?? ''],
      ['Wahrscheinlich falsch', f?.not_plausible ?? ''],
      ['Neu zugeordnet', f?.regrouped ?? ''],
      ['Unsicher / offen', f?.low_open ?? ''],
    ];
    const wsKpis = XLSX.utils.aoa_to_sheet(kpiRows);
    XLSX.utils.book_append_sheet(wb, wsKpis, 'KPIs');

    // Sheet 2: Top-Warengruppen
    const wgHeader = ['Warengruppe', 'CO₂e vorher (t)', 'CO₂e nachher (t)', 'Veränderung (%)', 'Ausgaben vorher (€)', 'Ausgaben nachher (€)', 'Anzahl Bestellungen', 'EF vorhanden'];
    const wgRows = this.topWg().map((r) => [
      r.wg_name,
      r.co2_before_t,
      r.co2_after_t,
      r.delta_pct,
      r.eur_before,
      r.eur_after,
      r.regrouped_count,
      r.ef_ok ? 'Ja' : 'Nein',
    ]);
    const wsWg = XLSX.utils.aoa_to_sheet([wgHeader, ...wgRows]);
    XLSX.utils.book_append_sheet(wb, wsWg, 'Top-Warengruppen');

    // Sheet 3: Änderungsprotokoll
    const log = this.state.changeLog();
    const logHeader = ['Zeitstempel', 'Stufe', 'Zeilen-ID', 'Feld', 'Alt', 'Neu', 'Aktion'];
    const logRows = log.map((e) => [e.timestamp, e.stage, e.row_index, e.field_changed, e.old_value, e.new_value, e.user_action]);
    const wsLog = XLSX.utils.aoa_to_sheet([logHeader, ...logRows]);
    XLSX.utils.book_append_sheet(wb, wsLog, 'Änderungsprotokoll');

    XLSX.writeFile(wb, `THG-Analyse-${date}.xlsx`);
  }
}
