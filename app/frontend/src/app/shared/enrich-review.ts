import { Component, EventEmitter, Input, Output, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  EnrichContent,
  EnrichPlan,
  EnrichSuggestion,
  FieldAnnotations,
  HistorySignal,
} from '../../api';

type Action = 'lassen' | 'ergänzen' | 'neu';

/**
 * Wiederverwendbares Diff-/Anmerkungs-Panel für das LLM-Enrichment einer
 * Warengruppe — die eine Einheit, die sowohl das atomare Vorschlags-Modal (mode
 * 'generate') als auch die Bulk-Review-Queue des Wizards (mode 'review') nutzen.
 *
 * Es ist „dumm" gegenüber Persistenz: es rendert Ist/Vorschlag je Feld, sammelt
 * Per-Feld-Plan, Historie-Schalter und „Anmerkung für KI" und emittiert
 * generate / refine / apply / rejected — der Container ruft die API auf und
 * reicht ein neues `suggestion` zurück.
 */
@Component({
  selector: 'app-enrich-review',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="er">
      <!-- Kopf: Plan-Steuerung + Historie + Generieren (nur im Generieren-Modus) -->
      @if (mode === 'generate') {
        <div class="er-head">
          <div class="er-plan">
            @for (f of FIELDS; track f.key) {
              <label class="er-planfld">
                <span>{{ f.label }}</span>
                <select [ngModel]="plan()[f.key]" (ngModelChange)="setAction(f.key, $event)">
                  <option value="lassen">lassen</option>
                  <option value="ergänzen">ergänzen</option>
                  <option value="neu">neu</option>
                </select>
              </label>
            }
          </div>
          <div class="er-presets">
            <span class="er-presets-lbl">Presets:</span>
            <button type="button" class="er-chip" (click)="preset('alles')">Alles neu</button>
            <button type="button" class="er-chip" (click)="preset('beispiele')">Nur Beispiele</button>
            <button type="button" class="er-chip" (click)="preset('beschreibung')">Nur Beschreibung</button>
            <button type="button" class="er-chip" (click)="preset('verbessern')">Behutsam</button>
          </div>
          <div class="er-histrow">
            <label class="er-hist" [class.er-hist-off]="!hasHistory()">
              <input type="checkbox" [ngModel]="useHistory()" (ngModelChange)="useHistory.set($event)"
                     [disabled]="!hasHistory()" />
              Historie einbeziehen
              @if (hist(); as h) {
                <span class="er-flux" title="manuelle Korrekturen: Zuflüsse / Abflüsse">
                  ↑{{ h.influx_count }} ↓{{ h.outflux_count }}
                </span>
              }
            </label>
            <span class="er-spacer"></span>
            <button type="button" class="er-btn er-btn-primary" [disabled]="busy" (click)="onGenerate()">
              {{ busy ? 'Generiere…' : (sug() ? '↻ Neu generieren' : '✨ Vorschlag generieren') }}
            </button>
          </div>
        </div>
      }

      <!-- Meta des aktuellen Vorschlags -->
      @if (sug(); as s) {
        <div class="er-meta">
          @if (s.konfidenz != null) {
            <span class="er-badge" [class.er-lo]="s.konfidenz < 70" [class.er-hi]="s.konfidenz >= 85">
              Konfidenz {{ s.konfidenz }}
            </span>
          }
          @if (s.status) { <span class="er-badge er-status">{{ s.status }}</span> }
          @if (s.history_used) { <span class="er-badge er-histused" title="Vorschlag nutzte historische Korrekturen">Historie</span> }
          @if (s.anmerkung) { <span class="er-note">{{ s.anmerkung }}</span> }
          @if (s.cost_usd) {
            <span class="er-cost">{{ (s.prompt_tokens || 0) + (s.completion_tokens || 0) }} Tok · \${{ s.cost_usd | number: '1.0-4' }}</span>
          }
        </div>
      }

      @if (mode === 'review' && provenance().length) {
        <details class="er-prov">
          <summary>Begründung aus der Historie ({{ provenance().length }})</summary>
          <ul>
            @for (p of provenance(); track $index) { <li>{{ p }}</li> }
          </ul>
        </details>
      }

      <!-- Felder: Ist | Vorschlag (editierbar) + Anmerkung -->
      <div class="er-fields">
        <!-- Beschreibung -->
        <div class="er-field">
          <div class="er-field-h">Beschreibung
            <button type="button" class="er-mini" title="Auf Ist zurücksetzen" (click)="resetDesc()">↺</button>
          </div>
          <div class="er-cols">
            <div class="er-ist">{{ curDesc() || '—' }}</div>
            <textarea class="er-edit" rows="3" [ngModel]="editDesc()" (ngModelChange)="editDesc.set($event)"
                      placeholder="Vorschlag / Bearbeitung"></textarea>
          </div>
          <input class="er-ann" [ngModel]="annDesc()" (ngModelChange)="annDesc.set($event)"
                 placeholder="Anmerkung für KI (z. B. kürzer, keine Marken)…" />
        </div>

        <!-- Beispiele enthält -->
        <div class="er-field">
          <div class="er-field-h">Beispiele — ENTHÄLT <em>(eine Zeile pro Eintrag)</em>
            <button type="button" class="er-mini" title="Auf Ist zurücksetzen" (click)="resetInc()">↺</button>
          </div>
          <div class="er-cols">
            <div class="er-ist">
              @if (curInc().length) { <ul>@for (x of curInc(); track $index) { <li>{{ x }}</li> }</ul> }
              @else { <span class="er-empty">—</span> }
            </div>
            <textarea class="er-edit" rows="4" [ngModel]="editInc()" (ngModelChange)="editInc.set($event)"
                      placeholder="Ein Eintrag pro Zeile"></textarea>
          </div>
          <input class="er-ann" [ngModel]="annInc()" (ngModelChange)="annInc.set($event)"
                 placeholder="Anmerkung für KI…" />
        </div>

        <!-- Beispiele nicht enthält -->
        <div class="er-field">
          <div class="er-field-h">Beispiele — NICHT ENTHÄLT <em>(eine Zeile pro Eintrag)</em>
            <button type="button" class="er-mini" title="Auf Ist zurücksetzen" (click)="resetExc()">↺</button>
          </div>
          <div class="er-cols">
            <div class="er-ist">
              @if (curExc().length) { <ul>@for (x of curExc(); track $index) { <li>{{ x }}</li> }</ul> }
              @else { <span class="er-empty">—</span> }
            </div>
            <textarea class="er-edit" rows="4" [ngModel]="editExc()" (ngModelChange)="editExc.set($event)"
                      placeholder="Ein Eintrag pro Zeile"></textarea>
          </div>
          <input class="er-ann" [ngModel]="annExc()" (ngModelChange)="annExc.set($event)"
                 placeholder="Anmerkung für KI…" />
        </div>
      </div>

      <!-- Footer -->
      <div class="er-foot">
        <button type="button" class="er-btn" [disabled]="busy || !hasAnnotations()" (click)="onRefine()"
                title="Anmerkungen per KI einarbeiten">
          {{ busy ? 'Arbeite ein…' : '↻ Mit KI überarbeiten' }}
        </button>
        <span class="er-spacer"></span>
        @if (showReject) {
          <button type="button" class="er-btn er-btn-ghost" [disabled]="busy" (click)="rejected.emit()">Verwerfen</button>
        }
        <button type="button" class="er-btn" [disabled]="busy" (click)="cancelled.emit()">Abbrechen</button>
        <button type="button" class="er-btn er-btn-primary" [disabled]="busy || !sug()" (click)="onApply()">
          {{ applyLabel }}
        </button>
      </div>
    </div>
  `,
  styles: [`
    .er { display: flex; flex-direction: column; gap: 12px; }
    .er-head { display: flex; flex-direction: column; gap: 8px; padding: 10px; border: 1px solid var(--bd, #e5e7eb); border-radius: 8px; background: var(--bg2, #f8fafc); }
    .er-plan { display: flex; gap: 12px; flex-wrap: wrap; }
    .er-planfld { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--fg2, #64748b); }
    .er-planfld select { height: 30px; border: 1px solid var(--bd, #cbd5e1); border-radius: 6px; padding: 0 6px; background: #fff; }
    .er-presets { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .er-presets-lbl { font-size: 12px; color: var(--fg2, #64748b); }
    .er-chip { border: 1px solid var(--bd, #cbd5e1); background: #fff; border-radius: 999px; padding: 3px 10px; font-size: 12px; cursor: pointer; }
    .er-chip:hover { background: var(--bg2, #eef2f7); }
    .er-histrow { display: flex; align-items: center; gap: 8px; }
    .er-hist { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
    .er-hist-off { opacity: 0.55; }
    .er-flux { font-size: 12px; color: var(--blue, #0d9af2); font-weight: 600; }
    .er-spacer { flex: 1; }
    .er-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .er-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: #e2e8f0; color: #334155; }
    .er-badge.er-lo { background: #fee2e2; color: #b91c1c; }
    .er-badge.er-hi { background: #dcfce7; color: #15803d; }
    .er-status { background: #e0e7ff; color: #4338ca; }
    .er-histused { background: rgba(13,154,242,0.15); color: #0369a1; }
    .er-note { font-size: 12px; color: var(--fg2, #64748b); font-style: italic; }
    .er-cost { font-size: 11px; color: var(--fg2, #94a3b8); margin-left: auto; }
    .er-prov { font-size: 12px; color: var(--fg2, #64748b); }
    .er-prov ul { margin: 6px 0 0; padding-left: 18px; }
    .er-fields { display: flex; flex-direction: column; gap: 14px; }
    .er-field-h { font-size: 12px; font-weight: 600; color: var(--fg2, #475569); margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
    .er-field-h em { font-weight: 400; color: var(--fg3, #94a3b8); }
    .er-mini { margin-left: auto; border: none; background: transparent; cursor: pointer; font-size: 14px; color: var(--fg2, #64748b); }
    .er-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: stretch; }
    .er-ist { font-size: 13px; color: var(--fg2, #64748b); background: var(--bg2, #f8fafc); border: 1px solid var(--bd, #eef2f7); border-radius: 6px; padding: 6px 8px; overflow: auto; }
    .er-ist ul { margin: 0; padding-left: 16px; }
    .er-empty { color: var(--fg3, #cbd5e1); }
    .er-edit { width: 100%; box-sizing: border-box; border: 1px solid var(--bd, #cbd5e1); border-radius: 6px; padding: 6px 8px; font: inherit; font-size: 13px; resize: vertical; }
    .er-ann { width: 100%; box-sizing: border-box; margin-top: 6px; border: 1px dashed var(--bd, #cbd5e1); border-radius: 6px; padding: 5px 8px; font-size: 12px; }
    .er-foot { display: flex; align-items: center; gap: 8px; border-top: 1px solid var(--bd, #eef2f7); padding-top: 10px; }
    .er-btn { height: 34px; padding: 0 14px; border: 1px solid var(--bd, #cbd5e1); background: #fff; border-radius: 8px; cursor: pointer; font-size: 13px; }
    .er-btn:disabled { opacity: 0.5; cursor: default; }
    .er-btn-primary { background: var(--blue, #0d9af2); border-color: var(--blue, #0d9af2); color: #fff; font-weight: 600; }
    .er-btn-ghost { color: #b91c1c; }
  `],
})
export class EnrichReviewComponent {
  protected readonly FIELDS = [
    { key: 'beschreibung' as const, label: 'Beschreibung' },
    { key: 'examples_enthalten' as const, label: 'enthält' },
    { key: 'examples_nicht_enthalten' as const, label: 'nicht enthält' },
  ];

  @Input() mode: 'generate' | 'review' = 'generate';
  @Input() wgName = '';
  @Input() wgId: string | null = null;
  @Input() busy = false;
  @Input() applyLabel = 'Übernehmen';
  @Input() showReject = false;

  protected readonly plan = signal<EnrichPlan>({
    beschreibung: 'neu',
    examples_enthalten: 'neu',
    examples_nicht_enthalten: 'neu',
  });
  private planTouched = false;
  protected readonly useHistory = signal(false);
  protected readonly hist = signal<HistorySignal | null>(null);
  protected readonly sug = signal<EnrichSuggestion | null>(null);

  protected readonly curDesc = signal('');
  protected readonly curInc = signal<string[]>([]);
  protected readonly curExc = signal<string[]>([]);
  protected readonly editDesc = signal('');
  protected readonly editInc = signal('');
  protected readonly editExc = signal('');
  protected readonly annDesc = signal('');
  protected readonly annInc = signal('');
  protected readonly annExc = signal('');

  @Input() set current(v: EnrichContent | null | undefined) {
    const c = v ?? { beschreibung: null, examples_enthalten: [], examples_nicht_enthalten: [] };
    this.curDesc.set(c.beschreibung ?? '');
    this.curInc.set(c.examples_enthalten ?? []);
    this.curExc.set(c.examples_nicht_enthalten ?? []);
    if (!this.planTouched) this.plan.set(this.derive(c));
    if (!this.sug()) this.resetAllEdits();
  }

  @Input() set suggestion(v: EnrichSuggestion | null | undefined) {
    this.sug.set(v ?? null);
    if (v) {
      this.editDesc.set(v.beschreibung ?? '');
      this.editInc.set((v.examples_enthalten ?? []).join('\n'));
      this.editExc.set((v.examples_nicht_enthalten ?? []).join('\n'));
      if (v.plan) this.plan.set(v.plan);
      this.annDesc.set('');
      this.annInc.set('');
      this.annExc.set('');
    }
  }

  @Input() set historySignal(v: HistorySignal | null | undefined) {
    this.hist.set(v ?? null);
  }

  @Output() generate = new EventEmitter<{ plan: EnrichPlan; useHistory: boolean }>();
  @Output() refine = new EventEmitter<{ annotations: FieldAnnotations; content: EnrichContent }>();
  @Output() apply = new EventEmitter<{ content: EnrichContent }>();
  @Output() rejected = new EventEmitter<void>();
  @Output() cancelled = new EventEmitter<void>();

  protected hasHistory(): boolean {
    const h = this.hist();
    return !!h && ((h.influx_count ?? 0) > 0 || (h.outflux_count ?? 0) > 0);
  }

  protected readonly hasAnnotations = computed(
    () => !!(this.annDesc().trim() || this.annInc().trim() || this.annExc().trim()),
  );

  /** Top-Bestelltexte aus der Historie, als Begründung im Review-Modus. */
  protected readonly provenance = computed<string[]>(() => {
    const h = this.hist();
    if (!h) return [];
    const inn = (h.top_influx ?? []).slice(0, 5).map((i) => `→ ${i.text} (${i.count}×)`);
    const out = (h.top_outflux ?? []).slice(0, 5).map((i) => `⤳ ${i.text} (${i.count}×)`);
    return [...inn, ...out];
  });

  private derive(c: EnrichContent): EnrichPlan {
    return {
      beschreibung: (c.beschreibung ?? '').trim() ? 'lassen' : 'neu',
      examples_enthalten: (c.examples_enthalten ?? []).length ? 'lassen' : 'neu',
      examples_nicht_enthalten: (c.examples_nicht_enthalten ?? []).length ? 'lassen' : 'neu',
    };
  }

  setAction(field: 'beschreibung' | 'examples_enthalten' | 'examples_nicht_enthalten', val: Action) {
    this.planTouched = true;
    this.plan.set({ ...this.plan(), [field]: val });
  }

  preset(name: 'alles' | 'beispiele' | 'beschreibung' | 'verbessern') {
    this.planTouched = true;
    const p: Record<string, EnrichPlan> = {
      alles: { beschreibung: 'neu', examples_enthalten: 'neu', examples_nicht_enthalten: 'neu' },
      beispiele: { beschreibung: 'lassen', examples_enthalten: 'neu', examples_nicht_enthalten: 'neu' },
      beschreibung: { beschreibung: 'neu', examples_enthalten: 'lassen', examples_nicht_enthalten: 'lassen' },
      verbessern: { beschreibung: 'ergänzen', examples_enthalten: 'ergänzen', examples_nicht_enthalten: 'ergänzen' },
    };
    this.plan.set(p[name]);
  }

  private toLines(s: string): string[] {
    return s.split('\n').map((x) => x.trim()).filter(Boolean);
  }

  private resetAllEdits() {
    this.editDesc.set(this.curDesc());
    this.editInc.set(this.curInc().join('\n'));
    this.editExc.set(this.curExc().join('\n'));
  }
  resetDesc() { this.editDesc.set(this.curDesc()); }
  resetInc() { this.editInc.set(this.curInc().join('\n')); }
  resetExc() { this.editExc.set(this.curExc().join('\n')); }

  private editedContent(): EnrichContent {
    return {
      beschreibung: this.editDesc().trim() || null,
      examples_enthalten: this.toLines(this.editInc()),
      examples_nicht_enthalten: this.toLines(this.editExc()),
    };
  }

  private annotationsObj(): FieldAnnotations {
    return {
      beschreibung: this.annDesc().trim() || null,
      examples_enthalten: this.annInc().trim() || null,
      examples_nicht_enthalten: this.annExc().trim() || null,
    };
  }

  onGenerate() {
    this.generate.emit({ plan: this.plan(), useHistory: this.useHistory() });
  }
  onRefine() {
    this.refine.emit({ annotations: this.annotationsObj(), content: this.editedContent() });
  }
  onApply() {
    this.apply.emit({ content: this.editedContent() });
  }
}
