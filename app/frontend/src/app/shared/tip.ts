import { Component, input, signal } from '@angular/core';

/**
 * Inline contextual-help icon. Renders a small ⓘ badge; hovering shows
 * a styled tooltip positioned with position:fixed so it escapes any
 * overflow:hidden ancestor (cards, table wrappers, etc.).
 *
 * Usage: <app-tip text="Explanation text here"></app-tip>
 */
@Component({
  selector: 'app-tip',
  standalone: true,
  template: `
    <span class="tip-icon"
      (mouseenter)="show($event)"
      (mouseleave)="hide()">i</span>
    @if (visible()) {
      <div class="tip-box" [style.top.px]="top" [style.left.px]="left">{{ text() }}</div>
    }
  `,
})
export class TipComponent {
  readonly text = input('');

  protected visible = signal(false);
  protected top = 0;
  protected left = 0;

  show(e: MouseEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    this.top = r.bottom + 8;
    this.left = r.left + r.width / 2;
    this.visible.set(true);
  }

  hide() {
    this.visible.set(false);
  }
}
