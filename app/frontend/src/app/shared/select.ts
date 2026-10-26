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

export interface SelectOption {
  value: any;
  label: string;
}

/**
 * Generisches Custom-Select — Ersatz für native <select> dort, wo das geöffnete
 * Menü ebenfalls im App-Stil erscheinen soll (nicht nur das geschlossene Feld).
 *
 * Bewusst ohne die WG-spezifischen Extras des WgComboComponent (kein „Neue WG",
 * keine KI/NEU-Badges). Bei langen Listen (> 8 Optionen) erscheint automatisch ein
 * Suchfeld. Das Popup liegt position:fixed (wie WgComboComponent / TipComponent),
 * damit es nicht vom overflow:hidden der Tabelle/Card abgeschnitten wird.
 *
 * Usage:
 *   <app-select [options]="opts" [value]="val" (valueChange)="val.set($event)"></app-select>
 *   <app-select class="sel-fill" ...>  // füllt die Breite des Containers (Tabellenkopf)
 */
@Component({
  selector: 'app-select',
  standalone: true,
  imports: [FormsModule],
  template: `
    <button type="button" class="sel-trigger" [title]="selectedLabel()" (click)="toggle()">
      <span class="sel-text">{{ selectedLabel() }}</span>
      <span class="sel-caret">▾</span>
    </button>

    @if (open()) {
      <div #panel class="sel-panel" tabindex="-1"
        [style.top.px]="panelTop()"
        [style.left.px]="panelLeft()"
        [style.minWidth.px]="panelWidth()"
        [style.maxHeight.px]="panelMaxH()"
        (keydown)="onKey($event)">
        @if (showSearch()) {
          <div class="sel-head">
            <input #search class="sel-search" placeholder="Suchen…"
              [ngModel]="query()" (ngModelChange)="onQuery($event)" (keydown)="onKey($event)">
          </div>
        }
        <div class="sel-list">
          @for (o of filtered(); track $index; let i = $index) {
            <div class="sel-opt"
              [class.is-sel]="o.value === value()"
              [class.is-active]="i === highlight()"
              (click)="choose(o)"
              (mouseenter)="highlight.set(i)">
              {{ o.label }}
            </div>
          } @empty {
            <div class="sel-empty">Keine Treffer</div>
          }
        </div>
      </div>
    }
  `,
})
export class SelectComponent {
  readonly options = input<ReadonlyArray<SelectOption>>([]);
  readonly value = input<any>(null);
  readonly placeholder = input<string>('— wählen —');
  readonly valueChange = output<any>();

  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly searchEl = viewChild<ElementRef<HTMLInputElement>>('search');
  private readonly panelEl = viewChild<ElementRef<HTMLElement>>('panel');

  protected readonly open = signal(false);
  protected readonly query = signal('');
  protected readonly highlight = signal(0);

  protected readonly panelTop = signal(0);
  protected readonly panelLeft = signal(0);
  protected readonly panelWidth = signal(160);
  protected readonly panelMaxH = signal(300);

  constructor() {
    effect(() => {
      if (!this.open()) return;
      // Suchfeld fokussieren, sonst das Panel (für Pfeiltasten-Navigation).
      const el = this.searchEl()?.nativeElement ?? this.panelEl()?.nativeElement;
      el?.focus();
    });
  }

  protected readonly selectedLabel = computed(() => {
    const v = this.value();
    return this.options().find((o) => o.value === v)?.label ?? this.placeholder();
  });

  /** Suchfeld erst ab längeren Listen einblenden — bei 3–5 Optionen overkill. */
  protected readonly showSearch = computed(() => this.options().length > 8);

  protected readonly filtered = computed<ReadonlyArray<SelectOption>>(() => {
    const q = this.query().trim().toLowerCase();
    if (!q) return this.options();
    return this.options().filter((o) => o.label.toLowerCase().includes(q));
  });

  toggle() {
    if (this.open()) this.close();
    else this.openPanel();
  }

  private openPanel() {
    this.query.set('');
    // Highlight auf den aktuell gewählten Eintrag (oder 0).
    const idx = this.options().findIndex((o) => o.value === this.value());
    this.highlight.set(idx >= 0 ? idx : 0);
    this.place();
    this.open.set(true);
    window.addEventListener('scroll', this.onScrollOrResize, true);
    window.addEventListener('resize', this.onScrollOrResize);
  }

  private close() {
    if (!this.open()) return;
    this.open.set(false);
    window.removeEventListener('scroll', this.onScrollOrResize, true);
    window.removeEventListener('resize', this.onScrollOrResize);
  }

  private readonly onScrollOrResize = (e: Event) => {
    // Scrollen innerhalb des Panels (lange Liste) darf nicht schließen.
    if (e.type === 'scroll' && this.panelEl()?.nativeElement.contains(e.target as Node)) return;
    this.close();
  };

  onQuery(q: string) {
    this.query.set(q);
    this.highlight.set(0);
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
      if (o) this.choose(o);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      this.close();
    }
  }

  choose(o: SelectOption) {
    this.valueChange.emit(o.value);
    this.close();
  }

  @HostListener('document:click', ['$event'])
  onDocClick(e: MouseEvent) {
    if (this.open() && !this.host.nativeElement.contains(e.target as Node)) this.close();
  }

  /** Positioniert das Panel unter (oder bei wenig Platz über) dem Trigger. */
  private place() {
    const el = this.host.nativeElement.querySelector('.sel-trigger') as HTMLElement | null;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    const width = Math.min(Math.max(r.width, 160), vw - 2 * margin);
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
