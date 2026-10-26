# TODOS – Warengruppen-Katalog (CRUD)

Offene Arbeitspakete für den Warengruppen-Katalog auf Branch `warengruppe-crud`.
Betroffene Kernmodule:

- Backend API: `app/backend/app/api/warengruppen.py`
- Backend Service: `app/backend/app/services/warengruppen.py`
- Backend Schemas: `app/backend/app/schemas/models.py`
- ORM: `app/backend/app/models/orm.py` (`Warengruppe`, `Emissionsfaktor`)
- Seed: `app/backend/scripts/seed_warengruppen.py`
- Frontend View: `app/frontend/src/app/views/warengruppen/` (`warengruppen.ts` / `.html` / `.scss`)
- Generierter API-Client: `app/frontend/src/api/` (nach Backend-Schema-Änderung neu generieren, siehe CLAUDE.md → "Regenerate OpenAPI client")

> Hinweis Migrationen: `init_db()` führt nur `create_all` aus (legt **nur fehlende Tabellen** an, **kein** ALTER bestehender Tabellen, kein Alembic). Jede Spaltenänderung an `warengruppe` braucht daher eine manuelle Migration oder – nur in der Entwicklung – ein Zurücksetzen des `pgdata`-Volumes (`docker compose down -v`).

---

## 1. Vorlage und Import: Präfix für die Emissionsspalten

**Ziel:** Emissionsfaktor-Spalten in Import-Vorlage und Import-Parsing erhalten einen sprechenden Präfix (z. B. `e_2024`, `e_2025`), damit sie sich von anderen numerischen Spalten klar abheben und nicht versehentlich als Jahr fehlinterpretiert werden.

### Backend
- [ ] `services/warengruppen.py` → `import_rows()`: Jahres-Erkennung von „reine Ziffern" auf den Präfix umstellen.
  - Aktuell: `year_cols = [c for c in df.columns if str(c).strip().isdigit()]` und `jahr=int(str(c).strip())` (Zeilen ~276 und ~311).
  - Neu: Spaltenname matcht `e_<jahr>` (z. B. Regex `^e_(\d{4})$`, case-insensitive); das Jahr aus der Capture-Group ziehen.
  - **Abwärtskompatibilität entscheiden:** entweder weiterhin auch reine Jahreszahlen akzeptieren (sanfte Migration) oder hart auf Präfix umstellen. Empfehlung: beide Formen lesen, aber nur `e_<jahr>` in der Vorlage anbieten.
- [ ] Fehlermeldung in `import_rows()` (`f"Zeile {pos}: Emissionsfaktor '{c}' ist keine Zahl …"`) auf den neuen Spaltennamen abstimmen.

### Frontend
- [ ] `warengruppen.ts` → `templateHeader` (Zeilen ~359–367): `'2024', '2025'` durch `'e_2024', 'e_2025'` ersetzen.
- [ ] `templateAoa()`: Beispielwerte unter den neuen Spalten belassen; Kopf-Kommentar/Hilfetext zum Präfix ergänzen.
- [ ] Import-Dialog (`warengruppen.html`): kurzer Hinweistext „Emissionsfaktor-Spalten mit Präfix `e_<Jahr>`, z. B. `e_2024`".

### Abnahme
- [ ] Vorlage herunterladen (XLSX und CSV), unverändert wieder importieren → Emissionsfaktoren landen korrekt unter den jeweiligen Jahren.
- [ ] Reine Zahlenspalte ohne Präfix (z. B. eine Betrags-Spalte) wird **nicht** mehr fälschlich als Emissionsfaktor-Jahr eingelesen.
- [ ] README/Hinweis zum Importformat in `Use Case/scripts/README.md` bzw. CLAUDE.md aktualisiert, falls das Importformat dort dokumentiert ist.

---

## 2. Deaktivieren von Warengruppen (statt/zusätzlich zum Löschen) — ✅ umgesetzt

**Hintergrund:** Warengruppen sollen nicht immer hart gelöscht werden.
- Sind sie **historisch mit Buchungseinträgen verknüpft**, müssen sie aus Nachvollziehbarkeitsgründen erhalten bleiben → vollständiges Löschen unterbinden, stattdessen deaktivieren.
- Oder sie sollen für die Zukunft erhalten bleiben und ggf. später **wieder aktiviert** werden.

Eine deaktivierte Warengruppe wird **nicht mehr** an die LLM-Pipelines (Prädiktion/Plausibilität) als Vorschlagsziel gegeben, bleibt aber für die Emissionsberechnung historischer Buchungen (`ef_lookup`) und im Audit-Trail erhalten.

### Datenmodell / Migration
- [x] `models/orm.py` → `Warengruppe`: Feld `aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)` ergänzt (Default „aktiv"; ORM-Inserts setzen den Wert, daher ohne `server_default`).
- [x] **Automatische additive Migration** statt manuellem ALTER: `core/db.py::init_db()` ruft `_run_additive_migrations()` → `_add_column_if_missing()` (Inspector-geprüft, idempotent, dialekt-passend `TRUE`/`1`). Läuft bei jedem Start, backfillt bestehende Zeilen auf aktiv → **kein** `down -v` auf der VM nötig.
- [x] `scripts/seed_warengruppen.py` / `seed_from_excel()`: keine Änderung nötig — neu angelegte Warengruppen erhalten `aktiv=True` über den ORM-Default.

### Schemas
- [x] `schemas/models.py`: `aktiv: bool = True` in `WarengruppeRow` aufgenommen. **Bewusst nicht** in `WarengruppeUpsertRequest` — so kann das Speichern im Edit-Modal den Status nicht versehentlich zurücksetzen; Statuswechsel läuft ausschließlich über die dedizierten Endpunkte. Zusätzlich `BulkDeleteResult.blocked`, `BulkActiveRequest`, `BulkActiveResult`.
- [x] `_to_row()` in `services/warengruppen.py` um `aktiv=bool(wg.aktiv)` ergänzt.

### Service / Geschäftslogik
- [x] `services/warengruppen.py` → `to_catalog()`: nur aktive Warengruppen (`filter(Warengruppe.aktiv.is_(True))`). Fallback aufs Excel hängt jetzt an `total==0` (Tabelle leer), nicht an den gefilterten Zeilen — eine geseedete, aber komplett deaktivierte Tabelle bleibt maßgeblich.
- [x] `ef_lookup()`: **nicht** gefiltert — historische Emissionsberechnung bleibt korrekt.
- [x] Aktivieren/Deaktivieren: **dedizierte Endpunkte** (Option B) `set_active()` / `bulk_set_active()`, alle mit `invalidate_catalog_caches()`.
- [x] **Löschschutz** in `delete()` und `bulk_delete()`: `historical_references()` prüft Werte-Referenzen gegen `wg_id`/`wg_name` in `sample.wg_id_original`, `decision_event.old_value`/`new_value`, `correction_memory.predicted_wg`/`corrected_wg`. `delete()` → `WarengruppeReferencedError` (Router mappt auf **409**); `bulk_delete()` meldet referenzierte IDs in `BulkDeleteResult.blocked` und löscht den Rest.

### Frontend
- [x] `warengruppen.ts` / `.html`: Status-Spalte mit Badge „aktiv / inaktiv"; inaktive Zeilen dezent abgeschwächt.
- [x] Aktion „Deaktivieren"/„Aktivieren" je Zeile **und** im Edit-Modal.
- [x] Filter „alle / nur aktive / nur inaktive" (kombiniert mit der Textsuche über den MatTable-Filter).
- [x] Lösch-Button bleibt; 409-Meldung wird via `formatError` angezeigt (verweist auf „Deaktivieren"). Bulk-Löschen meldet blockierte IDs als Hinweis (`notice`).
- [x] Bulk-Aktion „Deaktivieren"/„Aktivieren" für die Mehrfachauswahl ergänzt.
- [x] Generierter API-Client neu generiert.

### Abnahme
- [ ] Deaktivierte Warengruppe erscheint **nicht** mehr als Vorschlag in einem neuen Prädiktions-/Plausibilitätslauf. *(manuell zu prüfen, siehe Verifikation im Plan)*
- [ ] Dashboard/Emissionsberechnung eines alten Laufs mit einer inzwischen deaktivierten Warengruppe rechnet weiterhin korrekt.
- [ ] Hartes Löschen einer referenzierten Warengruppe wird mit verständlicher Meldung blockiert; Deaktivieren funktioniert.
- [ ] Reaktivieren stellt die Warengruppe wieder als Vorschlagsziel her (`invalidate_catalog_caches()` greift).

### FK-Migrationspfad (Technische Schuld)

Warengruppen-Referenzen liegen **derzeit als Werte** vor, nicht als Fremdschlüssel:
`sample.wg_id_original`, `decision_event.old_value`/`new_value`,
`correction_memory.predicted_wg`/`corrected_wg`. Der Löschschutz vergleicht deshalb
Werte gegen **beide** Schlüssel (`wg_id` **und** `wg_name`).

- Der gesamte Wertevergleich ist absichtlich in **einer** Funktion gekapselt:
  `services/warengruppen.py::historical_references()` (+ Rückgabetyp `WgReferences`).
  Beim späteren FK-Umbau werden **nur** deren Query-Rümpfe durch FK-`COUNT`s ersetzt —
  die Aufrufer (`delete`/`bulk_delete`) und die Rückgabeform bleiben unverändert.
- `prediction_result.suggested_wg_name` wird **bewusst nicht** gezählt (unbestätigter
  Modell-Vorschlag ≠ historisches Pairing) — beim FK-Umbau mitentscheiden, ob echte
  FKs auch auf Vorschläge zeigen sollen.
- Restschärfe des Wertevergleichs (Namens-Kollisionen zweier Warengruppen, Groß-/Klein­schreibung,
  nicht getrimmte Werte) ist bekannt und akzeptiert; der FK-Umbau löst das endgültig.
- Out of scope in diesem Arbeitspaket: das Einführen der Fremdschlüssel-Spalten +
  Backfill der historischen Werte auf `warengruppe.id`.

---

## 3. LLM-Enrichment integrieren (Bulk und atomar) — ✅ umgesetzt (2026-07-01)

**Ziel:** Beschreibung sowie Beispiele (`enthalten` / `nicht_enthalten`) einer Warengruppe per LLM erzeugen lassen – direkt aus der CRUD-Oberfläche, sowohl für eine einzelne Warengruppe (atomar) als auch für mehrere/alle (Bulk). Dies portiert die bestehende, offline gefahrene Anreicherung in die Web-App.

> ✅ **Umgesetzt.** Backend: `services/enrichment.py` (OpenAI-Client wie `embeddings.py`, `SYSTEM_BASE` + Per-Feld-Direktiven aus dem Notebook, `enrich_one`/`refine_one`, In-Memory-Cache), `services/enrichment_batch.py` (Hintergrund-Daemon wie `orchestrator.py`), Router `api/enrichment.py` (10 Endpunkte), Schemas in `schemas/models.py`, ORM-Tabellen `enrichment_batch`/`enrichment_proposal` (auto via `create_all`, Startup-Recovery in `core/db.py`). History-Signal `history_signal(s)` in `services/warengruppen.py` — **komplementär** zu „learn from history" (nur lesend, keine Änderung an `memory.py`/`hints.py`/`orchestrator.py`). **Entscheidung:** Modus ist **per-Feld** (`lassen`/`ergänzen`/`neu`), verallgemeinert die drei Notebook-Modi; die Regex-Kommentar-Klassifikation aus `process_overlay_review.py` entfällt, weil die Anmerkungen strukturiert pro Feld vorliegen. Frontend: geteiltes Panel `shared/enrich-review.ts` (atomar `mode="generate"` + Bulk-Queue `mode="review"`), „✨ KI-Vorschlag"-Overlay im Warengruppen-Edit-Modal, Wizard `views/enrich/` (Sidebar „Katalog anreichern", `ViewKey 'anreichern'`). OpenAPI-Client neu generiert; `ng build` grün.
>
> **Verifiziert (ohne API-Kosten):** History-Aggregation (Zu-/Abfluss, Namensabgleich), kompletter Bulk-Flow mit gemocktem LLM (Persistenz je Warengruppe, Fortschritt, **Apply erhält die Emissionsfaktoren**, Refine, Reject, Restart-Recovery), HTTP-Smoke via TestClient (Read-Endpunkte, 400 bei leerer Auswahl, **503 mit klarer Meldung bei fehlendem Schlüssel**).
>
> **Live verifiziert (2026-07-01, Browser):** `/preview` liefert echte `gpt-4o`-Vorschläge; kompletter Wizard-Durchlauf (Auswahl → Konfig → Hintergrund-Lauf → Review → Übernehmen mit **DB-Write + EF-Erhalt**) und atomarer Pfad (Preset „Behutsam" erhält die Beschreibung wörtlich und ergänzt die Beispiele), keine Konsolenfehler. Der veraltete Angular-Starter-Spec `app.spec.ts` wurde durch einen echten Smoke-Test ersetzt (`provideHttpClient()` + Login-View-Assertion) → **`npm test` grün (2/2)**.

**Vorhandene Referenzlogik (wiederverwenden, nicht neu erfinden):**
- `Use Case/notebooks/02_warengruppen_enrichment.ipynb` – System-Prompts, Modus-Logik (`neu` = volle Generierung nur aus dem Namen; `ergänzung_beispiele` = Beschreibung respektieren, nur Beispiele; `verbessern`), JSON-Ausgabe `wg_desc_llm` / `wg_examples_enthalten_llm` / `wg_examples_nicht_enthalten_llm`.
- `Use Case/scripts/llm_caller.py` – konkreter API-Aufruf + Cache + System-Prompt.
- `app/backend/app/services/embeddings.py` – Muster für OpenAI-Client im Backend (Schlüssel-Auflösung über env → `ENV_FILE`-Fallback, Thread-Lock, Lazy-Init). Genauso aufbauen.

### Backend – neuer Service `services/enrichment.py`
- [ ] OpenAI-Client analog `embeddings.py` (Lazy-Init, Schlüssel-Auflösung, konfigurierbares Modell via Env, z. B. `UC44_ENRICH_MODEL`, Default passend zum Notebook).
- [ ] System-Prompt + Modus-Logik aus dem Notebook übernehmen:
  - Modus aus dem Ist-Zustand der Warengruppe ableiten (Beschreibung vorhanden? Beispiele vorhanden?).
  - Vorhandene Beschreibung **respektieren**, wenn nur Beispiele fehlen.
- [ ] JSON-Antwort robust parsen (kein Markdown, genau die drei Felder) und in `WarengruppeUpsertRequest`-kompatible Felder (`beschreibung`, `examples_enthalten`, `examples_nicht_enthalten`) mappen; Bullet-Splitting wie `_shared/catalog.py` → `_split_bullets`.
- [ ] Caching (analog `.cache/` der Standalone-Modelle bzw. Schlüssel = `wg_id` + Hash des Namens/Beschreibung), um Doppelaufrufe und Kosten zu vermeiden.
- [ ] Kosten-/Token-Erfassung zurückgeben (für UI-Hinweis und Budget).

### Backend – API (`api/warengruppen.py`)
- [ ] **Atomar:** `POST /api/warengruppen/{wg_id}/enrich`
  - Liefert einen **Vorschlag** zurück (Beschreibung + Beispiele), ohne sofort zu speichern → Nutzer prüft und übernimmt (siehe Frontend). Optionaler Query-Param `apply=true` zum direkten Speichern.
  - Bei `apply=true`: speichern via bestehender `update()`-Logik, `invalidate_catalog_caches()` läuft dort bereits.
- [ ] **Bulk:** `POST /api/warengruppen/enrich`
  - Request-Body mit Auswahl: konkrete `wg_ids`, oder Flag „nur fehlende" (Beschreibung/Beispiele leer), oder „alle".
  - Antwort: Liste von Vorschlägen bzw. Ergebnis-Zusammenfassung (erstellt/aktualisiert/übersprungen/Fehler – analog `ImportResult`).
  - Lange Laufzeit beachten: entweder synchron mit kleinem Limit, oder als Hintergrund-Job analog `services/orchestrator.py` mit Status-Polling. Für den ersten Wurf reicht ein synchroner Lauf über die Auswahl mit hartem Obergrenzen-Limit.
- [ ] Neue Pydantic-Schemas in `schemas/models.py`: `EnrichRequest`, `EnrichSuggestion`, `EnrichResult`.

### Frontend (`warengruppen.ts` / `.html`)
- [ ] **Atomar:** Button „KI-Vorschlag" im Edit-Modal. Holt den Vorschlag, zeigt ihn als Vorschau (Beschreibung + Beispiele), Nutzer kann Felder übernehmen/verwerfen, bevor er speichert.
- [ ] **Bulk:** Aktion „Auswahl anreichern" / „Fehlende anreichern" über die bestehende Mehrfachauswahl. Fortschritts-/Ergebnisanzeige (analog Import-Ergebnis).
- [ ] Lade-/Kostenhinweis (Tokens/USD aus der Antwort) und sauberes Fehler-Handling über `formatError`.
- [ ] Generierten API-Client nach Schema-Änderung neu generieren.

### Abnahme
- [ ] Atomar: Für eine Warengruppe ohne Beschreibung/Beispiele liefert „KI-Vorschlag" sinnvolle deutsche Inhalte; nach Übernahme + Speichern erscheinen sie im Prompt-Katalog (`to_catalog`) – `invalidate_catalog_caches()` greift.
- [ ] Modus-Logik: Bei vorhandener Beschreibung wird diese **nicht** überschrieben, nur Beispiele ergänzt.
- [ ] Bulk über „nur fehlende": ausschließlich Warengruppen ohne Beschreibung/Beispiele werden angereichert; Ergebnis-Zusammenfassung stimmt.
- [ ] Cache verhindert doppelte API-Aufrufe bei wiederholtem Lauf ohne Änderung.
- [ ] Kein API-Schlüssel gesetzt → klare, nutzerfreundliche Fehlermeldung statt Stacktrace.

---

## Querschnitt / nicht vergessen
- [x] Nach jeder Backend-Schema-Änderung: OpenAPI-Client neu generieren (`python scripts/dump_openapi.py` → `npm run openapi:generate`). *(für Punkt 2 erledigt)*
- [ ] `npm test` (Karma) für die geänderte Frontend-View grün halten.
- [x] Migrationsschritt für `warengruppe.aktiv` in `app/DEPLOY.md` dokumentiert — **automatische** additive Migration (VM: **kein** `down -v`).
- [x] CLAUDE.md (Abschnitt Warengruppen-Katalog / `warengruppen.py` + Schema-Migrationen) nachgezogen.
