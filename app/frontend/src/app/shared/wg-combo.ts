import {
  Component,
  ElementRef,
  HostListener,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

/**
 * Suchbares Warengruppen-Dropdown — Ersatz für das native <select> in der
 * KI-Prüfungs-Tabelle. Bei sehr vielen Warengruppen tippt der Nutzer statt zu
 * scrollen; das Suchfeld und die „➕ Neue Warengruppe…"-Aktion liegen in einem
 * fixierten Kopfbereich (`flex:none`), während nur die Optionsliste scrollt —
 * so bleibt das Anlegen einer neuen WG immer im Sichtbereich.
 *
 * Selbst angelegte Warengruppen (`customWgs`) werden mit einem „NEU"-Badge und
 * einem ⋮-Menü (Umbenennen / Löschen) markiert; die eigentliche Aktion erledigt
 * der Eltern-View über die Outputs `renameWg` / `deleteWg`.
 *
 * Popup und ⋮-Menü liegen position:fixed am Viewport (Koordinaten aus
 * getBoundingClientRect), damit sie nicht vom overflow:hidden der Tabelle/Card
 * oder der scrollenden Optionsliste abgeschnitten werden — Muster wie TipComponent.
 *
 * Usage:
 *   <app-wg-combo [value]="selected" [suggested]="kiVorschlag" [catalog]="alleWg"
 *     [customWgs]="eigeneWg" (pick)="onPick($event)" (addNew)="onAddNew()"
 *     (renameWg)="onRename($event)" (deleteWg)="onDelete($event)"></app-wg-combo>
 */
@Component({
  selector: 'app-wg-combo',
  standalone: true,
  imports: [FormsModule],
  template: `
    <button type="button" class="wg-combo-trigger"
      [class.wg-ai]="showingSuggestion()"
      [title]="displayText()"
      (click)="toggle()">
      <span class="wg-combo-text">{{ displayText() }}{{ showingSuggestion() ? ' (KI)' : '' }}</span>
      <span class="wg-combo-caret">▾</span>
    </button>

    @if (open()) {
      <div #panel class="wg-combo-panel"
        [style.top.px]="panelTop()"
        [style.left.px]="panelLeft()"
        [style.width.px]="panelWidth()"
        [style.maxHeight.px]="panelMaxH()">
        <!-- fixierter Kopf: Suche + Neue-WG-Aktion (scrollen nicht weg) -->
        <div class="wg-combo-head">
          <input #search class="wg-combo-search" placeholder="Warengruppe suchen…"
            [ngModel]="query()" (ngModelChange)="onQuery($event)" (keydown)="onKey($event)">
          <button type="button" class="wg-combo-add" (click)="chooseAddNew()">
            ➕ Neue Warengruppe…
          </button>
        </div>
        <div class="wg-combo-list">
          @if (filtered().length) {
            @for (o of filtered(); track o.name; let i = $index) {
              <div class="wg-combo-opt" role="option"
                [class.is-ai]="o.isAi"
                [class.is-active]="i === highlight()"
                [class.is-sel]="o.name === value()"
                (click)="choose(o.name)"
                (mouseenter)="highlight.set(i)">
                <span class="wg-combo-text">{{ o.name }}</span>
                @if (o.isAi) { <span class="wg-combo-ai-tag">KI</span> }
                @if (o.isCustom) {
                  <span class="wg-combo-new-tag">NEU</span>
                  <span class="wg-combo-dots" title="Bearbeiten / Löschen"
                    (click)="openMenu($event, o.name)">⋮</span>
                }
              </div>
            }
          } @else {
            <div class="wg-combo-empty">Keine Treffer</div>
          }
        </div>
      </div>
    }

    @if (menuWg()) {
      <div class="wg-combo-actions" [style.top.px]="menuTop()" [style.left.px]="menuLeft()">
        <button type="button" (click)="emitRename()">Umbenennen</button>
        <button type="button" class="danger" (click)="emitDelete()">Löschen</button>
      </div>
    }
  `,
})
export class WgComboComponent {
  /** Manuell gewählte WG (Override) oder null, wenn (noch) der KI-Vorschlag gilt. */
  readonly value = input<string | null>(null);
  /** KI-Vorschlag (suggested_wg_name) — wird oben als markierte Option gelistet. */
  readonly suggested = input<string | null>(null);
  /** Vollständiger Warengruppen-Katalog (bereits alphabetisch sortiert erwartet). */
  readonly catalog = input<string[]>([]);
  /** Namen der vom Nutzer selbst angelegten WGs → „NEU"-Badge + ⋮-Menü. */
  readonly customWgs = input<ReadonlySet<string>>(new Set());

  /** Gewählte WG. */
  readonly pick = output<string>();
  /** Nutzer möchte eine neue WG anlegen. */
  readonly addNew = output<void>();
  /** Nutzer möchte eine selbst angelegte WG umbenennen (Eltern-View prompt + Logik). */
  readonly renameWg = output<string>();
  /** Nutzer möchte eine selbst angelegte WG löschen. */
  readonly deleteWg = output<string>();

  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly searchEl = viewChild<ElementRef<HTMLInputElement>>('search');
  private readonly panelEl = viewChild<ElementRef<HTMLElement>>('panel');

  protected readonly open = signal(false);
  protected readonly query = signal('');
  protected readonly highlight = signal(0);

  protected readonly panelTop = signal(0);
  protected readonly panelLeft = signal(0);
  protected readonly panelWidth = signal(240);
  protected readonly panelMaxH = signal(300);

  /** Name der WG, deren ⋮-Aktionsmenü gerade offen ist (oder null). */
  protected readonly menuWg = signal<string | null>(null);
  protected readonly menuTop = signal(0);
  protected readonly menuLeft = signal(0);

  constructor() {
    // Sobald das Panel offen ist und das Suchfeld gerendert wurde: fokussieren.
    effect(() => {
      if (this.open()) this.searchEl()?.nativeElement.focus();
    });
  }

  protected readonly displayText = computed(
    () => this.value() ?? this.suggested() ?? '— WG wählen —',
  );
  protected readonly showingSuggestion = computed(
    () => !this.value() && !!this.suggested(),
  );

  /** Gefilterte Optionen: KI-Vorschlag zuerst (falls Treffer), dann übriger Katalog. */
  protected readonly filtered = computed<ReadonlyArray<{ name: string; isAi: boolean; isCustom: boolean }>>(() => {
    const q = this.query().trim().toLowerCase();
    const sug = this.suggested();
    const custom = this.customWgs();
    const match = (s: string) => !q || s.toLowerCase().includes(q);
    const out: { name: string; isAi: boolean; isCustom: boolean }[] = [];
    if (sug && match(sug)) out.push({ name: sug, isAi: true, isCustom: false });
    for (const wg of this.catalog()) {
      if (wg === sug) continue;
      if (match(wg)) out.push({ name: wg, isAi: false, isCustom: custom.has(wg) });
    }
    return out;
  });

  toggle() {
    if (this.open()) this.close();
    else this.openPanel();
  }

  private openPanel() {
    this.query.set('');
    this.highlight.set(0);
    this.place();
    this.open.set(true);
    // Inner-Scrolls (Tabelle) und Resize würden das fix positionierte Panel
    // vom Trigger lösen → in dem Fall einfach schließen.
    window.addEventListener('scroll', this.onScrollOrResize, true);
    window.addEventListener('resize', this.onScrollOrResize);
  }

  private close() {
    if (!this.open()) return;
    this.open.set(false);
    this.menuWg.set(null);
    window.removeEventListener('scroll', this.onScrollOrResize, true);
    window.removeEventListener('resize', this.onScrollOrResize);
  }

  private readonly onScrollOrResize = (e: Event) => {
    // Scrollen INNERHALB des Panels (Optionsliste): Panel bleibt offen, aber das an
    // eine Zeile gepinnte ⋮-Menü würde verrutschen → nur dieses schließen.
    if (e.type === 'scroll' && this.panelEl()?.nativeElement.contains(e.target as Node)) {
      this.menuWg.set(null);
      return;
    }
    // Scroll des dahinterliegenden Inhalts / Resize → alles schließen.
    this.close();
  };

  onQuery(q: string) {
    this.query.set(q);
    this.highlight.set(0);
    this.menuWg.set(null);
  }

  onKey(e: KeyboardEvent) {
    const list = this.filtered();
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.highlight.set(Math.min(this.highlight() + 1, list.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.highlight.set(Math.max(this.highlight() - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const o = list[this.highlight()];
      if (o) this.choose(o.name);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      this.close();
    }
  }

  choose(name: string) {
    this.pick.emit(name);
    this.close();
  }

  chooseAddNew() {
    this.addNew.emit();
    this.close();
  }

  /** ⋮ angeklickt: Aktionsmenü für diese WG öffnen/schließen (ohne die Option zu wählen). */
  openMenu(e: MouseEvent, name: string) {
    e.stopPropagation();
    if (this.menuWg() === name) {
      this.menuWg.set(null);
      return;
    }
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const width = 160;
    let left = r.right - width;
    if (left < 8) left = 8;
    this.menuLeft.set(left);
    this.menuTop.set(r.bottom + 2);
    this.menuWg.set(name);
  }

  emitRename() {
    const n = this.menuWg();
    if (n) this.renameWg.emit(n);
    this.close();
  }

  emitDelete() {
    const n = this.menuWg();
    if (n) this.deleteWg.emit(n);
    this.close();
  }

  @HostListener('document:click', ['$event'])
  onDocClick(e: MouseEvent) {
    if (this.open() && !this.host.nativeElement.contains(e.target as Node)) this.close();
  }

  /** Positioniert das Panel unter (oder bei wenig Platz über) dem Trigger. */
  private place() {
    const el = this.host.nativeElement.querySelector('.wg-combo-trigger') as HTMLElement | null;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    const width = Math.min(Math.max(r.width, 240), vw - 2 * margin);
    let left = r.left;
    if (left + width > vw - margin) left = vw - margin - width;
    if (left < margin) left = margin;

    const spaceBelow = vh - r.bottom - margin;
    const spaceAbove = r.top - margin;
    const desired = 300;
    let top: number;
    let maxH: number;
    if (spaceBelow >= 180 || spaceBelow >= spaceAbove) {
      top = r.bottom + 4;
      maxH = Math.min(desired, spaceBelow);
    } else {
      maxH = Math.min(desired, spaceAbove);
      top = r.top - 4 - maxH;
    }

    this.panelTop.set(top);
    this.panelLeft.set(left);
    this.panelWidth.set(width);
    this.panelMaxH.set(maxH);
  }
}
