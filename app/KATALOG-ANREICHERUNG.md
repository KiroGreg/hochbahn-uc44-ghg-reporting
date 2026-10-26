# Katalog anreichern — KI-Beschreibungen & Beispiele

Erzeugt oder verbessert **Beschreibung** und **Beispiele** (`enthält` / `nicht enthält`)
einer Warengruppe per LLM — direkt aus der Weboberfläche. Das portiert die zuvor offline
gefahrene Anreicherung (`Use Case/notebooks/02_warengruppen_enrichment.ipynb`) in die App,
sowohl **atomar** (eine Warengruppe) als auch als **Bulk-Lauf** (viele auf einmal), immer mit
menschlicher Kontrolle vor dem Speichern.

> Voraussetzung: ein gültiger `OPENAI_API_KEY` (in `app/.env` oder `Use Case/models/.env`).
> Ohne Schlüssel liefert die Oberfläche eine klare Fehlermeldung statt eines Absturzes.

---

## Für Fachpersonen (Bedienung)

### A) Atomar — eine Warengruppe

1. **Warengruppen-Katalog** öffnen → Zeile **Bearbeiten**.
2. Im Modal **„✨ KI-Vorschlag — Beschreibung & Beispiele"** klicken.
3. Oben den **Plan** wählen (pro Feld `lassen` / `ergänzen` / `neu`, siehe unten) — er ist
   sinnvoll vorbelegt. Optional **„Historie einbeziehen"** anhaken.
4. **Vorschlag generieren.** Links steht der Ist-Zustand, rechts der (editierbare) Vorschlag.
5. Prüfen. Du kannst den Text direkt **bearbeiten**, ein Feld per **↺** auf den Ist-Wert
   zurücksetzen, oder eine **„Anmerkung für KI"** hinterlassen und **„Mit KI überarbeiten"**
   klicken — dann arbeitet das Modell dein Feedback ein (beliebig oft wiederholbar).
6. **„In Formular übernehmen"** schreibt die Werte ins Bearbeiten-Formular.
   **Gespeichert wird erst mit „Speichern".**

### B) Bulk — viele auf einmal (Wizard „Katalog anreichern")

Sidebar-Eintrag **„Katalog anreichern"**. Vier Schritte:

1. **Auswahl** — Tabelle aller aktiven Warengruppen mit
   - **Vollständigkeit** (drei Punkte: **B**eschreibung / Beispiele **E**nthält / **N**icht-enthält),
   - **Historie** (↑ manuelle Zuflüsse, ↓ Abflüsse — siehe unten).
   Filter „nur unvollständige" / „nur mit Korrektur-Historie", Sortierung nach Historie, sowie
   „Unvollständige wählen". Mehrfachauswahl per Checkbox.
2. **Konfiguration** — **Plan pro Warengruppe automatisch ableiten** (empfohlen: füllt leere
   Felder, lässt gefüllte) *oder* ein einheitlicher Plan; dazu der **Historie**-Schalter.
3. **Lauf** — läuft im **Hintergrund**. Fortschrittsbalken. Du kannst die Seite verlassen und
   später zurückkehren — ein laufender oder abgeschlossener Lauf wird **wieder aufgenommen**.
4. **Review** — Warteschlange, sinnvoll sortiert (unsichere zuerst, „unverändert" nach unten).
   Jede Zeile aufklappen → dasselbe Diff-Panel wie beim atomaren Pfad. Pro Vorschlag
   **Übernehmen & speichern** / **Verwerfen** / **Mit KI überarbeiten**. Sammelaktion
   **„Alle hochkonfidenten übernehmen"**.

### Der Per-Feld-Modus

Jedes der drei Felder bekommt eine eigene Aktion:

| Aktion     | Wirkung |
|------------|---------|
| `lassen`   | Feld bleibt unverändert (der bestehende Wert wird 1:1 durchgereicht). |
| `ergänzen` | Bestehendes respektieren: Beschreibung nur bei hartem Fehler ändern, Beispiele behutsam ergänzen. |
| `neu`      | Frisch generieren (Beschreibung aus dem Namen; Beispiele aus Name + Beschreibung). |

Auto-Ableitung: **leeres Feld → `neu`, gefülltes → `lassen`.** Presets setzen alle drei auf
einmal: *Alles neu*, *Nur Beispiele*, *Nur Beschreibung*, *Behutsam* (alle `ergänzen`).

### „Historie einbeziehen" (optional)

Bezieht die **manuellen Korrekturen** der bisherigen Läufe als Hinweis in den Prompt ein:

- **Zufluss** (Positionen, die jemand manuell *in* diese Warengruppe umgruppiert hat) →
  schärft **Beschreibung** und **enthält**.
- **Abfluss** (Positionen, die manuell *heraus* korrigiert wurden) → schärft **nicht enthält**.

Muster werden **verallgemeinert**, nie wörtlich übernommen — die Fachperson entscheidet im
Review, was in den Katalog wandert. Dies ist **ergänzend** zum bestehenden „learn from history"
(das einzelne Fälle zur Laufzeit einspielt), nicht dessen Ersatz.

### Wichtig

- **Nichts wird gespeichert, bis du übernimmst** (atomar: erst mit „Speichern"; Bulk: erst mit
  „Übernehmen & speichern" je Vorschlag).
- **Emissionsfaktoren und der Name bleiben beim Übernehmen erhalten** — nur Beschreibung und
  Beispiele ändern sich.

---

## Für Entwickler (Architektur)

**Backend**
- `app/backend/app/services/enrichment.py` — OpenAI-Client (Muster aus `services/embeddings.py`),
  `SYSTEM_BASE` + Per-Feld-Direktiven aus dem Notebook, `derive_plan`, `enrich_one`, `refine_one`,
  robustes JSON-Parsing, In-Memory-Cache. Modell via `UC44_ENRICH_MODEL` (Default `gpt-4o`),
  Temperatur via `UC44_ENRICH_TEMPERATURE` (Default `0.2`).
- `app/backend/app/services/enrichment_batch.py` — Hintergrund-Daemon (Muster aus
  `services/orchestrator.py`): persistiert jeden Vorschlag sofort, Fortschritt = `COUNT(proposal)`.
- `app/backend/app/services/warengruppen.py` — `history_signal(wg_id)` / `history_signals_all()`;
  liest nur `decision_event`/`sample` (verändert die Memory-Tabellen **nicht**).
- `app/backend/app/api/enrichment.py` — Router `/api/enrichment`:
  - atomar (synchron, nichts persistiert): `POST /preview`, `POST /refine`,
    `GET /history-signal/{wg_id}`, `GET /history-signals`.
  - Bulk (Hintergrund, persistiert): `POST /batch`, `GET /batch[/{id}[/status]]`,
    `POST /proposal/{id}/apply|reject|refine`.
- `app/backend/app/models/orm.py` — neue Tabellen `enrichment_batch` (Lifecycle wie `run`) und
  `enrichment_proposal`. Werden von `create_all` automatisch angelegt (keine Migration);
  steckengebliebene `running`-Batches werden beim Start auf `failed` zurückgesetzt
  (`core/db.py::init_db()`).
- Schemas in `app/backend/app/schemas/models.py` (`EnrichPlan`, `EnrichContent`,
  `EnrichSuggestion`, `HistorySignal`, `EnrichProposal`, …).

**Frontend**
- `app/frontend/src/app/shared/enrich-review.ts` — `<app-enrich-review>`, das geteilte
  Diff-/Anmerkungs-Panel (`mode="generate"` atomar, `mode="review"` im Wizard).
- `app/frontend/src/app/views/warengruppen/` — „✨ KI-Vorschlag"-Overlay im Edit-Modal.
- `app/frontend/src/app/views/enrich/` — Wizard-View; Sidebar-Eintrag + `ViewKey 'anreichern'`
  in `state.ts` / `app.ts` / `app.html`.

**Nach Backend-Schema-Änderungen** den OpenAPI-Client neu generieren
(`npm run openapi` im Frontend — Dump + Generate; siehe `CLAUDE.md`).

Weitere Details: `CLAUDE.md` (Abschnitt „LLM enrichment") und das Referenz-Notebook
`Use Case/notebooks/02_warengruppen_enrichment.ipynb`.
