import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpEventType } from '@angular/common/http';
import { RunSummary, RunsService, UploadService } from '../../../api';
import { AppState } from '../../state';
import { formatError } from '../../util/error';
import { TipComponent } from '../../shared/tip';

@Component({
  selector: 'view-upload',
  standalone: true,
  imports: [CommonModule, TipComponent],
  templateUrl: './upload.html',
})
export class UploadView implements OnInit {
  private readonly api = inject(UploadService);
  private readonly runsApi = inject(RunsService);
  protected readonly state = inject(AppState);

  protected readonly progress = signal(0);
  protected readonly busy = signal(false);
  protected readonly status = signal('');

  /** Verlauf: persistierte Läufe aus der DB für die „Letzte Läufe"-Liste. */
  protected readonly runs = signal<RunSummary[]>([]);
  protected readonly loadingRun = signal(false);

  ngOnInit() {
    this.refreshRuns();
  }

  private refreshRuns() {
    this.runsApi.listRunsApiRunsGet().subscribe({
      next: (rs) => this.runs.set(rs),
      error: () => this.runs.set([]),
    });
  }

  /** Einen früheren Lauf aus der DB wiederherstellen und ins Review springen. */
  resume(id: string) {
    this.loadingRun.set(true);
    this.runsApi.getRunApiRunsRunIdGet(id).subscribe({
      next: (detail) => {
        this.state.loadRun(detail);
        this.loadingRun.set(false);
      },
      error: (e) => {
        this.loadingRun.set(false);
        this.status.set('Fehler: ' + formatError(e, 'Lauf konnte nicht geladen werden'));
      },
    });
  }

  formatRunDate(iso: string): string {
    const d = new Date(iso);
    return isNaN(d.getTime())
      ? iso
      : d.toLocaleString('de-DE', {
          day: '2-digit',
          month: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        });
  }

  runStatusLabel(r: RunSummary): string {
    if (r.status === 'running') return '⟳ läuft…';
    if (r.status === 'failed') return '⚠ fehlgeschlagen';
    if (r.has_prediction) return 'Analyse abgeschlossen';
    if (r.has_plausibility) return 'Plausibilität geprüft';
    return 'Nur hochgeladen';
  }

  runStatusColor(r: RunSummary): string {
    if (r.status === 'running') return 'var(--blue)';
    if (r.status === 'failed') return 'var(--red, #c0392b)';
    if (r.has_prediction) return 'var(--green)';
    return 'var(--t2)';
  }

  pickFile(input: HTMLInputElement) {
    input.click();
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
  }

  onDrop(event: DragEvent, input: HTMLInputElement) {
    event.preventDefault();
    event.stopPropagation();
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    // Trigger the same native file-input change flow so validation stays in one place
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    this.upload(file);
  }

  onFile(event: Event) {
    const input = event.target as HTMLInputElement;
    const f = input.files?.[0];
    if (!f) return;
    this.upload(f);
  }

  upload(file: File) {
    this.busy.set(true);
    this.status.set('Wird gelesen…');
    this.progress.set(0);

    this.api
      .uploadFileApiUploadFilePost(file, 'events', true)
      .subscribe({
        next: (event: any) => {
          if (event.type === HttpEventType.UploadProgress && event.total) {
            this.progress.set(Math.round((event.loaded / event.total) * 90));
          } else if (event.type === HttpEventType.Response) {
            this.progress.set(100);
            this.status.set(`✓ ${event.body.row_count.toLocaleString('de-DE')} Einträge geladen`);
            this.state.upload.set(event.body);
            this.busy.set(false);
          }
        },
        error: (e) => {
          this.busy.set(false);
          this.status.set('Fehler: ' + formatError(e, 'Upload fehlgeschlagen'));
        },
      });
  }

  loadSample() {
    this.busy.set(true);
    this.status.set('Lade Beispieldatei…');
    this.progress.set(40);
    this.api.loadSampleApiUploadSamplePost().subscribe({
      next: (s) => {
        this.progress.set(100);
        this.status.set(`✓ ${s.row_count.toLocaleString('de-DE')} Einträge geladen`);
        this.state.upload.set(s);
        this.busy.set(false);
      },
      error: (e) => {
        this.busy.set(false);
        this.status.set('Fehler: ' + formatError(e, 'Sample konnte nicht geladen werden'));
      },
    });
  }

  goNext() {
    this.state.go('review');
  }
}
