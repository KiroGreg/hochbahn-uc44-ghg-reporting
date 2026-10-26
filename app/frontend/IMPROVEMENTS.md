# Frontend — Offene Verbesserungen & UX-Empfehlungen

Dieses Dokument listet alle empfohlenen UX-Verbesserungen sowie noch offene Anforderungen
aus den Meetings mit Levke Albertsen (Hamburger Hochbahn) und dem Requirements-Dokument
`Orga/Requirements-after-06-05`.

---

## Implementierungs-Status (Stand: 2026-06-06, Session 4)

| # | Beschreibung | Status | Aufwand |
|---|---|---|---|
| 1 | Plausibility + Regrouping zusammenführen | ✅ Umgesetzt | Groß |
| 2 | Sprache vereinfachen | ✅ Umgesetzt | Klein |
| 3 | Unsichere Fälle standardmäßig oben | ✅ Umgesetzt | Klein |
| 4 | Auto-Accept mit konfigurierbarem Schwellenwert (req 2.1.1 / 2.2) — Regression behoben | ✅ Umgesetzt | Mittel |
| 5 | Betrag (€) in den Tabellen (Anzeige, Filter-Dropdown, Sortierung, Kostenschwelle) (req 1.1 / 1.2 / 2.1.2) | ✅ Umgesetzt (Session 6) | Mittel |
| 6 | WG-Dropdown: nur vollständige Katalogliste (KI-Vorschlag-Optgroup entfernt) | ✅ Umgesetzt | Klein |
| 7 | Unwichtige Spalten ausblenden | ✅ Umgesetzt | Klein |
| 8 | Dashboard — fehlende Visualisierungen | ⏳ Teilweise (4.2 ✅, 4.4 ✅; 4.1/4.3 offen) | Groß |
| 9 | Excel-Export im Dashboard | ✅ Umgesetzt | Klein |
| 10 | Corporate Design Hochbahn | ✅ Umgesetzt | Mittel |
| 11 | Shneiderman 8 Regeln + UI-Qualität | ✅ Umgesetzt | Klein |
| 12 | Spaltenfilter: Konfidenz- und KI-Vorschlag-Dropdown mit Häufigkeitsanzeige | ✅ Umgesetzt | Klein |
| 13 | Aktionsfilter: granular nach Bestätigt / Abgelehnt / WG geändert / Ausstehend | ✅ Umgesetzt | Klein |
| 14 | Lesbarkeit: Schriftgrößen systemweit angehoben | ✅ Umgesetzt | Klein |
| 15 | Upload-Zone zentriert + vergrößert | ✅ Umgesetzt | Klein |
| 16 | Schriftgrößen Session 3: weitere Erhöhungen | ✅ Umgesetzt | Klein |
| 17 | Step-Name "Korrektur" → "KI-Prüfung" + Beschreibungen | ✅ Umgesetzt | Klein |
| 18 | Tooltips nutzerfreundlich überarbeitet, Icons blau | ✅ Umgesetzt | Klein |
| 19 | Sortierung: nur Konfidenz sortierbar, Toolbar-Button | ✅ Umgesetzt | Klein |
| 30 | Konfidenz-Spaltenheader: Klick-Sortierung entfernt, App-Tip ergänzt | ✅ Umgesetzt | Klein |
| 20 | Info-Text oben, nutzerorientiert umformuliert | ✅ Umgesetzt | Klein |
| 21 | Ergebnis-Verteilungsdiagramm (4 Segmente) | ✅ Umgesetzt | Klein |
| 22 | KPI-Boxen: 4 → 2 (Analysiert + Nicht plausibel) | ✅ Umgesetzt | Klein |
| 23 | Farb-Konsistenz: Diagramm ↔ Konfidenz-Chips | ✅ Umgesetzt | Klein |
| 24 | API-Budget-Widget in Sidebar im Dev-Mode sichtbar | ✅ Umgesetzt | Klein |
| 25 | PlausibilityView-Deadcode gelöscht (plausibility.ts/.html, Import, @case) | ✅ Umgesetzt | Klein |
| 26 | Drag-and-Drop Upload-Zone (dragover + drop Events) | ✅ Umgesetzt | Klein |
| 27 | "WG bisher"-Spaltenfilter mit Dropdown + Häufigkeitszähler | ✅ Umgesetzt | Klein |
| 28 | Dashboard: ML-Jargon im Funnel vereinheitlicht, avg_confidence mit Label | ✅ Umgesetzt | Klein |
| 29 | Mock-Daten: statische Imports → dynamische import() — im Prod-Bundle nie geladen | ✅ Umgesetzt | Klein |
| 31 | Aubergine-Rahmen um den Hauptinhalt (GitLab-Stil, gerundete Ecken) | ✅ Umgesetzt | Klein |
| 32 | Aubergine Top-Leiste (`#tbar`) für globale Aktionen (Dateiname, Schritt, Theme, Logout) | ✅ Umgesetzt | Klein |
| 33 | Sidebar-Schriftgrößen auf GitLab-Niveau angehoben | ✅ Umgesetzt | Klein |
| 34 | Hochbahn-Logo in der Sidebar statt Textzeile | ✅ Umgesetzt | Klein |
| 35 | Review: Auto-Übernahme aus Karte in die Toolbar verschoben (mittig, rot umrandet) | ✅ Umgesetzt | Klein |
| 36 | Review: Sortier-Button-Bug behoben (erster Klick wirkungslos) | ✅ Umgesetzt | Klein |
| 37 | Review: Entschiedene Zeilen bleiben immer unten (auch bei aktivem Sort) | ✅ Umgesetzt | Klein |
| 38 | Theme-Wechsel: Flackern zwischen Sidebar & Rahmen behoben (synchrone Transition) | ✅ Umgesetzt | Klein |
| 39 | Dashboard: Balkendiagramm Top-WG nach Emissionen/Ausgaben (req 4.2) + MOCK_DASHBOARD | ✅ Umgesetzt | Klein |
| 40 | Review: Spalten "KI-Vorschlag" + "Neue WG wählen" zu einer Spalte "Warengruppe" zusammengeführt | ✅ Umgesetzt | Klein |
| 41 | UI-Politur: Expand-Pfeil größer/blau, sichtbarere Scrollbar, Scrollbar läuft nicht mehr in die gerundeten Ecken | ✅ Umgesetzt | Klein |
| 42 | Dashboard: Histogramm Emissionsrate/WG (req 4.4) + Sankey-Platzhalter; redundante Funnel- & Ranking-Box ersetzt | ✅ Umgesetzt | Klein |
| 43 | Review: Reset-Button + reaktive Auto-Übernahme (Schwellen-Dropdown bewertet Haken live neu); „Korrekt"-Segment auf Brand-Leuchtblau | ✅ Umgesetzt | Klein |
| 44 | Backend liefert `betrag_eur`; Review: Betrags-Spalte mit Filter-Dropdown, Standard-Sortierung Konfidenz→Betrag, aktive Kostenschwelle bei Auto-Übernahme | ✅ Umgesetzt (Session 6) | Mittel |
| 45 | Review: voller Zell-Text per Hover — `title` auf „WG bisher" und dem Warengruppe-Select (ergänzt die bestehenden Hovertexte auf Bestelltext/Betrag) | ✅ Umgesetzt (Session 7) | Klein |
| 46 | Review: eigene Warengruppe manuell anlegen — „➕ Neue Warengruppe…"-Option im WG-Dropdown (Prompt, wird in den Katalog einsortiert und der Zeile zugewiesen) | ✅ Umgesetzt (Session 7) | Klein |
| 47 | Dashboard: zeigt erst nach abgeschlossener KI-Prüfung Daten — Gate auf `state.prediction()`, sonst Empty-State (kein geteilter In-Memory-Stand mehr vor dem Upload) | ✅ Umgesetzt (Session 7) | Klein |
| 48 | Review: ✓/✗ als Toggle — Buttons bleiben sichtbar, der aktive ist gefüllt, erneuter Klick macht nur diese eine Zeile rückgängig (`toggleDecide` → `undecide`). Neuer Backend-Endpoint `DELETE /api/prediction/decision/{row_index}`, damit das Dashboard die zurückgenommene Entscheidung nicht weiter anwendet | ✅ Umgesetzt (Session 7) | Klein |
| 49 | Tooltip: doppelte Anzeige behoben — natives `[title]` aus `TipComponent` entfernt, nur noch das gestylte `.tip-box`-Popup erscheint beim Hovern | ✅ Umgesetzt (Session 7) | Klein |
| 50 | Dashboard-Detailtabelle: nach Betrag (€) absteigend sortiert statt nach CO₂-nachher (`detailRows`-Computed in `dashboard.ts`, Header „Betrag ↓") | ✅ Umgesetzt (Session 7) | Klein |

**Mock-Daten für lokales Testen** sind eingebaut (siehe Ende dieses Dokuments). Alle Imports sind dynamisch — der Production-Build referenziert den Chunk nie.

48 von 50 Punkten umgesetzt · Dashboard-Charts: 4.2 + 4.4 ✅, 4.1/4.3 offen

---

## 1. Plausibility-Check + Regrouping zusammenführen ✅

**Quelle:** Meeting 27.05 — *"Step 2 and Step 3: Everything should be possible in one step"* (Levke)

### Warum geändert?

**Vorher:** Der Nutzer musste denselben Datensatz in zwei getrennten Schritten durcharbeiten:
1. In Schritt 2 (Plausibility) jede Zeile als "Korrekt" oder "→ Regrouping" markieren
2. Dann zu Schritt 3 navigieren und dieselben Zeilen nochmals bestätigen

Das war doppelte Arbeit ohne Mehrwert. Levke formulierte es direkt: *"Everything should be possible in one step."* Außerdem war die 4-stufige Navigation konzeptionell verwirrend — die beiden Modelle sind technische Implementierungsdetails, keine nutzerrelevanten Schritte.

**Nachher:** Upload → KI analysiert automatisch im Hintergrund (Modell 1, dann Modell 2) → Nutzer sieht genau eine Tabelle und trifft Entscheidungen.

### Was technisch geändert wurde (2026-06-05)

- `src/app/state.ts` — `STEP_ORDER` auf 3 Schritte reduziert (`upload → review → dashboard`); `'plausibility'` bleibt im ViewKey-Typ für Rückwärtskompatibilität, ist aber aus der Navigation raus
- `src/app/app.ts` — Steps-Array auf 3 Einträge reduziert, `stepBadge` zeigt "Schritt X von 3", TITLES angepasst
- `src/app/views/upload/upload.ts` — `goNext()` navigiert direkt zu `'review'` statt `'plausibility'`
- `src/app/views/review/review.ts` — Injiziert jetzt auch `PlausibilityService`; `run()` kettet beide API-Aufrufe: erst `/api/plausibility/run`, dann automatisch `/api/prediction/run`; neues `phase`-Signal (`'idle' | 'checking' | 'predicting'`) für den Ladezustand
- `src/app/views/review/review.html` — Startbedingung von `state.plausibility() && !result` auf `state.upload() && !result` geändert; zweistufiger Ladebalken zeigt welches Modell gerade läuft
- `src/app/views/plausibility/plausibility.ts/.html` — Komponente ist noch im Code (über `@case ('plausibility')` in `app.html` erreichbar als Fallback), aber aus der Sidebar-Navigation entfernt

### Vorher/Nachher: Nutzerfluss

```
Vorher (4 Schritte):
Upload → [Plausibility starten] → Zeilen entscheiden → [Regrouping starten] → Zeilen nochmal entscheiden → Dashboard

Nachher (3 Schritte):
Upload → [Analyse starten] → Zeilen einmal entscheiden → Dashboard
```

### Noch zu tun

Die Plausibility-Komponente ist jetzt dead code und kann gelöscht werden:
- `src/app/views/plausibility/plausibility.ts` + `plausibility.html` — löschen
- `src/app/app.ts` — `PlausibilityView`-Import entfernen
- `src/app/app.html` — `@case ('plausibility')`-Block entfernen

---

## 2. Sprache vereinfachen — kein ML-Fachjargon ✅

### Warum geändert?

**Vorher:** Die Begriffe im Interface spiegelten das technische Backend-Datenmodell wider: "Plausibilitäts-Check", "Regrouping", "Confidence", "implausibel", "Objektbez.-Fallback". Ein Hochbahn-Sachbearbeiter, der täglich mit Rechnungen arbeitet, versteht keinen dieser Begriffe ohne Erklärung.

**Nachher:** Die Sprache beschreibt was der Nutzer tun soll, nicht was das Modell intern macht. "WG behalten" ist eine klare Handlungsanweisung. "KI sehr sicher" kommuniziert Unsicherheit ohne Zahlenwert. "Wahrscheinlich falsch" sagt direkt was das System denkt.

### Was technisch geändert wurde (2026-06-05)

Geändert in `plausibility.html`, `review.html`, `app.ts`, `app.html`.
Neue Hilfsmethode `confidenceLabel(c)` in `plausibility.ts` und `review.ts`:
mappt Backend-Werte (`hoch/mittel/niedrig`) → lesbare Labels (`sehr sicher / sicher / unsicher`),
ohne die internen Signalwerte zu verändern (Filter und Logik weiter auf Original-Werten).

### Vorher/Nachher: Label-Tabelle

| Vorher (technisch) | Nachher (nutzerfreundlich) | Begründung |
|---|---|---|
| `✓ Korrekt` | `WG behalten` | Beschreibt die Konsequenz, nicht eine abstrakte Bewertung |
| `→ Regrouping` | `WG ändern` | Klar was passiert; "Regrouping" ist ein internes Konzept |
| `Confidence: hoch` | `KI sehr sicher` | Macht den Ursprung (KI) und den Grad explizit |
| `Confidence: mittel` | `KI sicher` | — |
| `Confidence: niedrig` | `KI unsicher` | Warnung ohne Fachbegriff |
| `Plausibilitäts-Check` | `Prüfung` | Alltagssprache |
| `Regrouping` | `Korrektur` | Beschreibt was der Nutzer macht, nicht das Modell |
| `Nicht plausibel` | `Wahrscheinlich falsch` | Konkrete Aussage statt logischem Fachausdruck |
| `Objektbez.-Fallback` | *(entfernt)* | Nur intern relevant; Nutzer braucht das nicht wissen |
| `Auto-Bestätigung` | `Alle sicheren Fälle übernehmen` | Beschreibt die Aktion, nicht einen technischen Modus |
| `regrouped` (Sidebar) | `neu zugeordnet` | Deutsch statt Denglisch |
| `niedrig · offen` (Sidebar) | `unsicher · offen` | Konsistent mit neuem Konfidenz-Vokabular |

---

## 3. Tabelle: Unsichere Fälle oben, sichere unten ✅

### Warum geändert?

**Vorher:** Die Tabelle zeigte alle Zeilen in der Reihenfolge wie das Backend sie zurückgab (Row-Index aufsteigend). Der Nutzer musste selbst scrollen und filtern um herauszufinden, wo manueller Einsatz nötig ist.

**Nachher:** Zeilen mit KI-Konfidenz "unsicher" stehen oben — das sind genau die Fälle, bei denen der Nutzer nicht einfach auf den KI-Vorschlag vertrauen kann. Zeilen mit getroffener Entscheidung rutschen ans Ende, weil sie "erledigt" sind und aus dem Fokus verschwinden sollen.

**Motivierendes Zitat (Meeting 06.05, Levke):** *"Sort by values (monetary values), so focus on more important ones first."* — anfangs nur Konfidenz-Sortierung (der wichtigere erste Schritt), da `betrag_eur` im Backend fehlte. Seit Session 6 (Punkt 44) ist die Betrags-Sortierung als zweites Kriterium aktiv.

### Was technisch geändert wurde (2026-06-05)

Default-Sortierung in `sortedFiltered` (beide Komponenten), aktiv wenn kein manueller User-Sort:

```typescript
// Niedrig-Konfidenz zuerst, entschiedene Zeilen ans Ende
const confOrder = { niedrig: 0, mittel: 1, hoch: 2 };
rows = [...rows].sort((a, b) => {
  const aD = a._decision != null ? 1 : 0;
  const bD = b._decision != null ? 1 : 0;
  if (aD !== bD) return aD - bD;                                    // Entschiedene ans Ende
  return (confOrder[a.confidence] ?? 99) - (confOrder[b.confidence] ?? 99); // Unsichere oben
});
```

**Reaktivitäts-Trick:** Angular Signals verfolgen keine tiefen Objekt-Mutationen. Da `row._decision` direkt mutiert wird, würde `sortedFiltered` normalerweise nicht neu berechnen. Lösung: `decide()` ruft `state.plausibility.set({ ...p })` auf (Shallow-Spread erzeugt neues Objekt → Signal-Update → `sortedFiltered` re-evaluiert, liest die bereits mutierten `_decision`-Werte).

### Noch offen

~~Sortierung nach `betrag_eur` als zweites Kriterium ist vorbereitet aber blockiert durch Punkt 5.~~
✅ Umgesetzt (Session 6, Punkt 44): Die Standard-Sortierung sortiert jetzt primär nach Konfidenz (unsicher zuerst), sekundär nach Betrag (höchster zuerst); unbekannte Beträge rutschen ans Ende.

---

## 4. Primärer Button: "Alle sicheren Vorschläge übernehmen" + konfigurierbarer Schwellenwert ✅

### Warum geändert?

**Vorher (Zusammenführung 2026-06-05):** Der häufigste Nutzerweg war versteckt. `autoAccept()` war in der Plausibility-View implementiert und hieß "Auto-Bestätigung". Bei der Zusammenführung zu einer Review-View (Punkt 1) wurde die Funktion portiert, dabei aber fälschlicherweise auf `hoch || mittel` hardcodiert und die konfigurierbaren Schwellenwerte (req 2.1.1, req 2.2) weggelassen.

**Nachher (Korrektur 2026-06-05):** Eine prominente Zusammenfassungskarte oben zeigt live:
- Wie viele Einträge die KI als korrekt eingestuft hat (WG bleibt)
- Wie viele Vorschläge den aktuell eingestellten Schwellenwert erfüllen
- Wie viele manuell geprüft werden müssen

Darunter eine Einstellungskarte (req 2.2):
- **Konfidenz-Dropdown** (Standard: "KI sehr sicher" = `hoch`) — wählbar: sehr sicher / sicher / unsicher
- **Betrag-Input** (Standard: 1000 €) — deaktiviert mit ⚠-Hinweis bis Backend `betrag_eur` liefert

Der Button zeigt immer die Anzahl der Zeilen, die aktuell übernommen würden (`autoCount`).

### Was technisch geändert wurde (req 2.1.1 + 2.2, 2026-06-05)

In `review.ts`:
```typescript
protected readonly autoConfThreshold = signal<'hoch' | 'mittel' | 'niedrig'>('hoch');
protected readonly autoCostThreshold = signal<number>(1000);

protected readonly summary = computed(() => {
  const rows = this.rows();
  const plausStats = this.state.plausibility()?.stats;
  const confOrder: Record<string, number> = { niedrig: 0, mittel: 1, hoch: 2 };
  const threshold = confOrder[this.autoConfThreshold()] ?? 2;
  return {
    plausible: plausStats?.plausible ?? 0,
    highMed: rows.filter(r => r.confidence === 'hoch' || r.confidence === 'mittel').length,
    low: rows.filter(r => r.confidence === 'niedrig').length,
    decided: rows.filter(r => r._decision != null).length,
    autoCount: rows.filter(r => r._decision == null && (confOrder[r.confidence] ?? -1) >= threshold).length,
  };
});

autoAccept() {
  const confOrder: Record<string, number> = { niedrig: 0, mittel: 1, hoch: 2 };
  const threshold = confOrder[this.autoConfThreshold()] ?? 2;
  for (const r of this.rows()) {
    if (r._decision) continue;
    // TODO: also check r.betrag_eur < this.autoCostThreshold() once backend provides betrag_eur
    if ((confOrder[r.confidence] ?? -1) >= threshold) this.decide(r, 'ok');
  }
}
```

`summary.autoCount` ist reaktiv gegenüber `autoConfThreshold` und `rows()` — der Button-Zähler aktualisiert sich live beim Ändern des Dropdowns.

---

## 5. Betrag (€) in den Tabellen — ✅ Umgesetzt (Session 6)

### Warum wichtig?

Levke hat explizit nach Betrags-Sortierung gefragt (Meeting 06.05): *"Sort by values (monetary values), so focus on more important ones first."* Eine Fehlzuordnung bei einer 50.000 €-Rechnung ist gravierender als bei einer 12 €-Rechnung. Ohne Betragsinfo kann der Nutzer nicht nach Impact priorisieren.

Außerdem ist der Betragsschwellenwert in Anforderung 2.1.2 beschrieben: Auto-Matching soll nur für Einträge unter 1.000 € gelten (geringeres Risiko).

### Was umgesetzt wurde

**Backend** — `betrag_eur: float | None` ist jetzt Teil von `PlausibilityRow` und `PredictionRow` (`schemas/models.py`). Der Betrag stammt aus der hochgeladenen Excel-Datei: die Spaltenerkennung liegt zentral in `core/data.py` (`AMOUNT_COLUMNS`, `amount_column()`, `amount_series()`) und wird von `services/plausibility.py`, `services/prediction.py` **und** `services/dashboard.py` gemeinsam genutzt (vorher hatte das Dashboard eine eigene Kopie `_amount_column`). Pro Zeile wird der Wert über den DataFrame-Index gelesen und auf 2 Nachkommastellen gerundet; fehlt eine Betragsspalte, bleibt das Feld `null`.

**Frontend** (`review.ts` / `review.html`):
- **Betrags-Spalte** zwischen „WG bisher" und „Warengruppe", rechtsbündig formatiert über `formatBetrag()` (`toLocaleString('de-DE', …)`); fehlender Betrag → „—".
- **Filter-Dropdown** wie bei den anderen Spalten (`betragFilter`-Signal, `betragOptions()` mit Trefferzahl je Bereich). Genau zwei Bereiche, deren Grenze stets dem „Auto-Übernahme bis Betrag"-Wert (`autoCostThreshold`) folgt: `< X €` (die auto-übernehmbaren Zeilen) und `≥ X €`. `betragBuckets` ist dazu ein Computed über `autoCostThreshold`.
- **Standard-Sortierung** primär nach Konfidenz (unsicher zuerst), sekundär nach Betrag (höchster zuerst).
- **Kostenschwelle aktiv:** `autoQualifies()` bündelt jetzt Konfidenz- **und** Kostenkriterium (`betrag_eur < autoCostThreshold`); ein leeres Limit oder unbekannter Betrag blockiert nicht. `autoAffected` (Vorschau-Zähler) und `autoAccept()` nutzen denselben Helper.

Der TypeScript-Client wurde regulär neu generiert (`scripts/dump_openapi.py` → `npm run openapi:generate`); inhaltlich änderten sich nur `prediction-row.ts` und `plausibility-row.ts`.

---

## 6. Top-5 WG-Vorschläge im Dropdown ✅

### Warum geändert?

**Vorher:** Das Dropdown im Review-Screen zeigte alle ~190 Warengruppen alphabetisch, beginnend mit "A". Der KI-Vorschlag war nur als Text in der Nachbarspalte sichtbar — um ihn auszuwählen musste der Nutzer ihn aus dem Dropdown heraussuchen.

**Nachher (Meeting 27.05, Levke):** *"Can we suggest the dropdown list where top-5 suggestions are listed? — Yes"*. Der KI-Vorschlag steht jetzt als erste Option ganz oben in einer eigenen Gruppe, darunter alle WGs.

### Was technisch geändert wurde (2026-06-05)

In `review.html` wurde `<optgroup>` eingeführt:

```html
<!-- Vorher: flache Liste -->
<option value="">— Wählen —</option>
@for (wg of catalog(); track wg) {
  <option [value]="wg">{{ wg }}</option>
}

<!-- Nachher: KI-Vorschlag oben, dann alle -->
<option value="">— Wählen —</option>
@if (r.suggested_wg_name) {
  <optgroup label="KI-Vorschlag">
    <option [value]="r.suggested_wg_name">{{ r.suggested_wg_name }}</option>
  </optgroup>
  <optgroup label="Alle Warengruppen">
    @for (wg of catalog(); track wg) { <option [value]="wg">{{ wg }}</option> }
  </optgroup>
} @else {
  @for (wg of catalog(); track wg) { <option [value]="wg">{{ wg }}</option> }
}
```

**Hinweis für spätere Erweiterung:** Das Backend gibt aktuell nur einen Vorschlag zurück. Falls Top-N gewünscht wird, müsste `PredictionRow` um `top_suggestions: string[]` erweitert werden.

---

## 7. Unwichtige Spalten ausblenden ✅

### Warum geändert?

**Vorher:** Die Tabellen zeigten technische Felder die für den eigentlichen Entscheidungsprozess irrelevant sind:
- **Widersprechende Signale:** Nützlich für neugierige Nutzer oder Debugging, aber für die Entscheidung "WG behalten" vs. "WG ändern" nicht notwendig — die Begründungsspalte daneben sagt dasselbe in lesbarer Form
- **Signal: Obj.bez.:** Ein internes Flag ob das Modell auf die Objektbezeichnung statt auf den Bestelltext zurückgegriffen hat — komplett irrelevant für den Nutzer
- **Objektbez.-Fallback (KPI):** Interne Metrik über die Datenqualität, kein Entscheidungskriterium

Breite Tabellen erzwingen horizontales Scrollen und erschweren den Fokus auf die relevanten Spalten.

### Was technisch geändert wurde (2026-06-05)

**Widersprechende Signale (Plausibility → Review):** Statt komplett zu entfernen, wird die Information per ▸/▾-Toggle pro Zeile zugänglich gemacht. Zeigt Begründung (Modell 1), widersprechende Signale (rot) und unterstützende Signale (grün). Nach der Zusammenführung von Plausibility + Review war der Toggle nur noch in der toten `plausibility.html` vorhanden — er wurde in `review.html` portiert (2026-06-05).

```typescript
// plausibility.ts — Neue Methoden
protected readonly expandedRows = signal<Set<number>>(new Set());
toggleExpand(rowIndex: number) { ... }
isExpanded(rowIndex: number): boolean { ... }
```

```html
<!-- plausibility.html — Expand-Zeile nach jeder Tabellenzeile -->
@if (isExpanded(r.row_index)) {
  <tr style="background:var(--bg-alt)">
    <td></td>
    <td colspan="5">
      <!-- widersprechende + unterstützende Signale als Chips -->
    </td>
  </tr>
}
```

**Signal: Obj.bez. (Review):** Komplett entfernt. Das `<col>`, `<th>` und alle `<td>` wurden gelöscht.

**Objektbez.-Fallback KPI-Karte:** Aus `plausibility.html` entfernt. War die vierte KPI-Karte in einer Reihe von vier. Die anderen drei (Analysiert, Wahrscheinlich falsch, KI unsicher) sind nutzerrelevant.

---

## 8. Dashboard — fehlende Visualisierungen ❌

**Status: Nicht implementiert** — Alle vier Anforderungen aus `Orga/Requirements-after-06-05` (4.1–4.4) stehen noch aus.

### Warum wichtig?

Das Dashboard soll nicht nur Zahlen zeigen, sondern den Impact der KI-Korrekturen visualisieren. Ohne Charts ist es schwer zu kommunizieren, dass Rechnungsposition X vorher falschen Emissionen zugeordnet war und danach korrekten. Das ist der eigentliche Mehrwert des Tools für den CSRD-Report.

### 8.1 Sankey-Diagramm (Anforderung 4.1)

Zeigt welche WG in welche andere WG gewechselt haben (Vorher → Nachher).

**Empfohlene Library:** `d3-sankey` oder `ngx-charts`

**Neue Datei:** `src/app/views/dashboard/sankey.ts`

Backend braucht neuen Endpunkt:
`GET /api/dashboard/sankey` → `[{from: "WG alt", to: "WG neu", count: 42}, ...]`

### 8.2 Balkendiagramm Top-WG Emissionen (Anforderung 4.2) ✅ Umgesetzt (Session 5)

Top-10 Warengruppen nach der aktiven Metrik (CO₂e nachher bzw. Ausgaben), horizontale Balken.
Siehe Punkt 39 unten. Reines Frontend (`barChart`-computed in `dashboard.ts`, `.bc-*`-Styles in `styles.scss`), Daten aus `top_wg`.

### 8.3 Zeitfilter nach Buchungsdatum (Anforderung 4.3)

Datumsbereich-Picker oben im Dashboard. Erfordert Backend-Unterstützung:
`GET /api/dashboard?von=2024-01-01&bis=2024-12-31`

### 8.4 Histogramm: Emissionen pro WG (Anforderung 4.4)

Einheitliche Emissionsrate = CO₂e gesamt / Anzahl Einträge je WG. Standard-Sortierung absteigend.

---

## 9. Excel-Export im Dashboard ✅

### Warum geändert?

**Vorher:** Der "↓ Excel exportieren"-Button in `dashboard.html` existierte, hatte aber keinen Click-Handler — er tat nichts.

**Nachher:** Klick löst echten Download aus. Excel ist das Standardformat bei Hamburger Hochbahn für Berichte und Nachweise. Die Mitarbeitenden werden die Ergebnisse in bestehende Excel-basierte Prozesse einspeisen — deshalb `.xlsx` statt CSV.

### Was technisch geändert wurde (2026-06-05)

- `xlsx` (SheetJS) installiert: `npm install xlsx`
- `exportExcel()`-Methode in `DashboardView`:

```typescript
// 3 Sheets: KPIs, Top-Warengruppen, Änderungsprotokoll
const wb = XLSX.utils.book_new();
// Sheet 1: KPIs (CO₂e vorher/nachher, Ausgaben, Trichter)
// Sheet 2: Top-WG-Tabelle mit allen Spalten
// Sheet 3: Audit-Log (Zeitstempel, Zeilen-ID, Alt/Neu, Nutzeraktion)
XLSX.writeFile(wb, `THG-Analyse-${date}.xlsx`);
```

- Button in `dashboard.html`: `(click)="exportExcel()"` ergänzt

---

## 10. Corporate Design Hochbahn (Anforderung N.1) ✅

### Warum geändert?

**Vorher:** Das Interface verwendete generische Blautöne ohne Bezug zu Hamburger Hochbahn. Levke Albertsen hat am 27.05.2026 das offizielle Brandbook mit den vier Hochbahn-Primärfarben übermittelt.

**Nachher:** 60-30-10-Regel umgesetzt:
- **60 %** Weiß/helle Hintergründe (Content-Bereich)
- **30 %** Aubergine für Sidebar und Navigation
- **10 %** Rot für primäre Buttons, Leuchtblau für Badges und Balken

### Hochbahn-Farben

| Farbe | Hex | Verwendung |
|---|---|---|
| Rot (Primär) | `#E2011F` | Primäre Buttons (`.bp`), aktiver Step-Dot, Header-Akzentlinie |
| Aubergine | `#470F34` | Sidebar-Hintergrund (`--bg-side` light), dark mode `#2a0d1e` |
| Weiß | `#FFFFFF` | Content-Bereich, Karten, Formulare |
| Leuchtblau | `#0D9AF2` | Dekorative Balken, Badge-Fills |

**Kontraste (WCAG AA):** Weiß auf Aubergine = 15,7:1 ✓ · Weiß auf Rot = 4,5:1 ✓ · `#0069b4` (Text-Blau) auf Weiß = 5,5:1 ✓

### Was technisch geändert wurde (2026-06-05)

- `src/styles.scss` — `:root` erhält `--hb-rot`, `--hb-aubergine`, `--hb-leuchtblau` als Brand-Konstanten. Light-Theme: `--bg-side: #470F34`, `--red: #E2011F`, `--blue: #0069b4` (lesbares Dunkelblau für Text). Dark-Theme: `--bg-side: #2a0d1e`, `--red: #ff3d55`.
- `src/styles.scss` — `.bp` und `.tbtn.ta` nutzen jetzt `var(--red)` statt `var(--blue)`. `.bp:hover` setzt `background: var(--red)` explizit, damit `.btn:hover { background: var(--bg-hov) }` nicht überschreibt. Dropzone-Hover auf Rot umgestellt.
- `src/app/app.scss` — `#sb` Sidebar auf `var(--bg-side)` (Aubergine). Alle Kind-Elemente (Texte, Funnel, Budget-Widget, Step-Dots, Trennlinien) auf `rgba(255,255,255,…)` umgestellt. Aktiver Step (`.step-act`) hat roten Linksbalken + rote Hintergrundtönung für mehr Hochbahn-Charakter.
- `src/app/app.scss` — `#tb` Header-Bar erhält `border-bottom: 2px solid var(--hb-rot)` als Brand-Anker.
- `src/app/app.html` — Sidebar-Badges auf semi-transparentes Weiß/Blau umgestellt. Funnel-Zahlen verwenden jetzt hartcodierte Hochbahn-Farben. `[class.step-act]`-Binding auf aktiven Step-Eintrag.

### Bug-Fixes (nach Review, 2026-06-05)

**Problem:** Primär-Buttons (`.btn.bp`) wurden auf Hover weiß.
**Ursache:** `.btn:hover { background: var(--bg-hov) }` hat `.bp:hover { filter: brightness(...) }` überschrieben, weil `filter` die Hintergrundfarbe nicht schützt.
**Fix:** `.bp:hover` setzt jetzt `background: var(--red)` explizit vor dem Filter.

**Problem:** Rote `:focus-visible`-Umrandungen erschienen beim Mausklick auf Filter-Buttons.
**Fix:** `:focus-visible` auf allen Buttons/Selects auf dezentes Blau geändert (`var(--blue)`), Selects erhalten nur noch `border-color: var(--blue)` ohne `outline`. Action-Buttons (`.a-ok`, `.a-no`) ohne eigenen `:focus-visible`-Override.

**Problem:** Sidebartext schwer lesbar — Step-Labels, Sub-Labels und Trichter-Titel zu transparent.
**Fix:** `.sl-m` auf `#fff` (100 %), `.sl-s` auf `rgba(255,255,255,0.72)`, `.ftit` auf `rgba(255,255,255,0.65)`, `.sbh-pre` auf `rgba(255,255,255,0.7)` erhöht.

**Problem:** Dropdown "Neue WG wählen" zeigte "⏳ Lädt…" nach Navigation zurück zur Review-Ansicht.
**Ursache:** Beim Zurücknavigieren ist `prediction` bereits gesetzt → `ngOnInit` ruft die Catalog-API auf → schlägt im Dev-Mode lautlos fehl → `catalog` bleibt leer → Fallback-Label "⏳ Lädt…" wurde angezeigt.
**Fix (review.ts):** Error-Handler des Catalog-Calls fällt in dev mode auf `MOCK_CATALOG` zurück. Label in `review.html` auf unveränderliches "— WG wählen —" geändert.

**Problem:** Dropdown-Selects hatten unterschiedliche Breiten je nach Zellinhalt.
**Fix (styles.scss):** `.wg-select` erhält `width: 100%; box-sizing: border-box` — füllt die fest definierte Tabellenspalte vollständig aus.

**Problem:** Info-Icons ⓘ (`TipComponent`) passten nicht ins Layout der Spaltenüberschriften — zu badge-artig, zu groß, zu viel visuelles Gewicht.
**Fix (styles.scss):** `.tip-icon` komplett neu gestaltet: 12 px, kein Hintergrund, subtiler `1px solid var(--t3)`-Umriss, `opacity: 0.55` im Ruhezustand. Bei Hover: `opacity: 1`, Border und Schrift in Hochbahn Leuchtblau `#0D9AF2`. Integriert sich unauffällig in Tabellen-Header und Inline-Labels.

---

## 11. Shneiderman 8 Goldene Regeln + UI-Qualität ✅

### Warum geändert?

**Prüfung aller 8 Regeln** und gezielte Umsetzung der fehlenden Punkte.

### Regelcheck (2026-06-05)

| # | Regel | Vorher | Umgesetzt |
|---|---|---|---|
| 1 | **Konsistenz** — gleiche Buttons, Abstände, Farben | Primärfarbe inkonsistent (blau mal hier, mal dort) | ✅ Alle `.bp`-Buttons einheitlich rot; `.tbtn.ta` auch rot |
| 2 | **Shortcuts für erfahrene Nutzer** | Keine `:focus-visible`-Stile | ✅ Keyboard-Focus-Ring (roter Outline 2px) auf allen Buttons, Selects, Action-Buttons |
| 3 | **Informatives Feedback** | Lade-Phasen vorhanden | ✅ Bereits vorhanden (Ladebalken, Phase-Anzeige) |
| 4 | **Abgeschlossenheit zeigen** | "Schritt X von 3" Badge, Step-Dots | ✅ Bereits vorhanden; Step-Dot aktiv = Rot, erledigt = Grün |
| 5 | **Fehlerprävention** | `title`-Tooltip auf autoAccept | ✅ Erweiterter `title` mit Konsequenz-Beschreibung + `aria-label` |
| 6 | **Rückgängig machen** | Nicht vorhanden | ⚠️ Bewusst nicht implementiert — Scope zu groß; Audit-Log ermöglicht manuelle Nachverfolgung |
| 7 | **Kontrolle beim Nutzer** | Keine Auto-Navigation | ✅ Bereits korrekt — alle Aktionen erfordern expliziten Klick |
| 8 | **Kurzzeitgedächtnis entlasten** | Button-Label "→ Dashboard" nichtssagend; Upload-Button falsch beschriftet | ✅ "→ Dashboard" → "Auswertung ansehen →"; Upload-Button → "KI-Analyse starten →" |

### Was technisch geändert wurde (2026-06-05)

- `src/styles.scss` — `:focus-visible` auf `.btn`, `.btn.bp`, `.tbtn`, `.abtn.a-ok`, `.abtn.a-no`, `select` ergänzt (roter Outline-Ring)
- `src/app/app.html` — `aria-label` auf den Theme-Toggle- und Logout-Buttons ergänzt
- `src/app/views/review/review.html` — `autoAccept`-Button: erweiterter `title` + `aria-label`; "→ Dashboard" → "Auswertung ansehen →"
- `src/app/views/upload/upload.html` — Button-Label korrigiert: "Plausibilitäts-Check starten →" → "KI-Analyse starten →" (war nach Zusammenführen der Steps inkorrekt)

### UI-Qualität: weitere Verbesserungen

- **Mobile Grundlagen** — `@media (max-width: 768px)` in `app.scss`: Sidebar auf 180 px, KPI-Grid auf 2 Spalten, g2-Grid auf 1 Spalte
- **Sidebar-Trennung** — `border-right: none` + `box-shadow: 2px 0 8px rgba(0,0,0,0.18)` statt Border — wirkt weniger technisch, mehr App-like

---

## Mock-Daten für lokales Testen (seit 2026-06-05)

### Warum eingebaut?

Der OpenAI-Key hat kein Guthaben, weshalb Schritt 2 und 3 lokal mit einem 500-Fehler enden.
Um die UI trotzdem testen zu können, werden bei einem Backend-Fehler im dev mode automatisch
realistische Beispieldaten geladen, statt eine Fehlermeldung zu zeigen.
In Production (`ng build`) ist dieser Code nie aktiv — `isDevMode()` gibt dort `false` zurück.

**Datei:** `src/app/dev/mock-data.ts`

Enthält:
- `MOCK_UPLOAD` — 47 Einträge, 12 Warengruppen
- `MOCK_PLAUSIBILITY` — 7 implausible + 2 plausible Zeilen, Stats mit total=47
- `MOCK_PREDICTION` — 7 Zeilen mit KI-Vorschlägen (hoch/mittel/niedrig gemischt)
- `MOCK_CATALOG` — 14 Warengruppen für das WG-Dropdown

**Verhalten:**
- `review.ts` `ngOnInit()`: wenn `isDevMode()` und kein `state.prediction()` → Mock sofort laden, kein Klick nötig
- `run()`: bei Backend-Fehler im dev mode → automatisch Mock statt Fehlermeldung, `isMock = true`
- `decide()` / `wgChange()` / `autoAccept()`: wenn Mock aktiv → API-Call übersprungen, Audit-Log läuft normal weiter
- Gelbes `DEV`-Banner am Seitenanfang signalisiert Mock-Modus

---

---

## 12. Spaltenfilter: Dropdown statt Texteingabe ✅

### Was geändert wurde (2026-06-05, Session 2)

**Konfidenz-Spalte:** Text-Input durch `<select>` ersetzt. Optionen zeigen alle drei Konfidenz-Stufen mit Live-Zähler (aus allen Zeilen, nicht aus gefilterten). Treibt das bestehende `confFilter`-Signal direkt. Das redundante Konfidenz-Dropdown aus der Filter-Leiste oben wurde entfernt.

**KI-Vorschlag-Spalte:** Text-Input durch `<select>` ersetzt. Optionen werden aus den tatsächlich vorhandenen WG-Vorschlägen berechnet, absteigend nach Häufigkeit sortiert, je mit Anzahl in Klammern. Nutzt neues `wgFilter`-Signal mit **Exakt-Matching** (`!==`) statt `includes()` — verhindert Substring-Kollisionen (z. B. "Büro" würde sonst auch "Büromaterial" treffen).

Neue Computed-Properties in `review.ts`:
```typescript
confCounts    // { hoch: N, mittel: N, niedrig: N } aus rows()
suggestedWgOptions  // [{ name, count }] absteigend nach count
decisionCounts      // { pending, ok, reject, new_wg } aus rows()
```

---

## 13. Aktionsfilter: granular nach Entscheidungstyp ✅

### Was geändert wurde (2026-06-05, Session 2)

`statusFilter`-Signal von `'all' | 'pending' | 'done'` auf `'all' | 'pending' | 'ok' | 'reject' | 'new_wg'` erweitert. Das Filter-Dropdown in der Toolbar zeigt jetzt:
- Alle Aktionen
- Ausstehend (N)
- ✓ Bestätigt (N)
- ✗ Abgelehnt (N)
- WG geändert (N) ← wenn Nutzer manuell WG aus Dropdown gewählt hat

Zähler kommen aus `decisionCounts` und aktualisieren sich live nach jeder Nutzerentscheidung.

---

## 14. Lesbarkeit: Schriftgrößen angehoben ✅

### Was geändert wurde (2026-06-05, Session 2)

Basis war `13px` global — viele Elemente lagen deutlich darunter und waren schwer lesbar.

| Element | Vorher | Nachher |
|---|---|---|
| `table td` | 11px | **13px** |
| `th` (Spaltenköpfe) | 9px | **11px** |
| `.kl` (KPI-Labels) | 9px | **11px** |
| `.chip` (Konfidenz-Badges) | 10px | **11px** |
| `.th-filter` (Spalten-Filter/Dropdowns) | 9px | **11px** |
| `.wg-select` | 10px | **12px** |
| `.badge` | 9px | **10px** |

---

## Zusammenfassung: Noch offene Punkte (für die nächste Session)

| Priorität | Was | Wo anfangen |
|---|---|---|
| **Mittel** | Dashboard: Sankey (req 4.1) | Platzhalter-Karte steht; Backend-Endpunkt `/api/dashboard/sankey` (WG vorher→nachher) + Sankey-Komponente (z. B. d3-sankey) ergänzen |
| **Mittel** | Dashboard: Zeitfilter nach Buchungsdatum (req 4.3) | Backend-Param `?von=&bis=`; Datums-Picker im Dashboard |
| **Niedrig (optional)** | Review-WG-Dropdown: echtes Custom-Dropdown statt nativem `<select>` | Natives `<option>` kann kein echtes Badge/Fett zuverlässig darstellen — der KI-Vorschlag trägt daher nur das Suffix „(KI)". Für einen echten KI-Badge (farbiger Chip, Icon) bräuchte es eine eigene Dropdown-Komponente (z. B. CDK Overlay / Listbox). Aufwand mittel, rein kosmetisch. |
| **Niedrig** | Shneiderman Regel 6: Undo für autoAccept | Snapshot vor `autoAccept()` speichern, "Rückgängig"-Button einblenden |

---

## Session 3 — UX-Verbesserungen (2026-06-05)

### 15. Upload-Zone: Zentriert & vergrößert ✅

Die Drag-and-Drop-Zone stand linksbündig oben. Neues `.dz-center`-Wrapper-Div zentriert sie vertikal und horizontal mit `min-height: calc(100vh - var(--th) - 32px)`. `max-width` auf 760 px, Innenabstand auf `70px 40px` erhöht. Zentrierungslayout gilt nur für den leeren Zustand (kein Summary), nicht für die Spalten-Bestätigungsansicht.

### 16. Schriftgrößen: Weitere Erhöhungen ✅

Aufbauend auf Session 2. Zusätzlich angehoben:

| Element | Vorher | Nachher |
|---|---|---|
| `body` global | 13 px | **14 px** |
| `.btn` | 11 px | 12 px |
| `.alert`, `.card-h`, `th` | 11 px | 12 px |
| `.kl`, `.dz-sub` | 11 px | 12 px |
| `.ks`, `.tsm`, `.dz-hint` | 10 px | 11 px |
| `select`, `.tbtn`, `.th-filter` | 11 px | 12 px |
| `.abtn` | 10 px | 11 px |

### 17. Step-Name "Korrektur" → "KI-Prüfung" ✅

"Korrektur" klang wie eine Fehlerkorrektur; "Modell 1+2: Prüfung & WG" war Entwickler-Sprache.

| Feld | Vorher | Nachher |
|---|---|---|
| Sidebar `main` | Korrektur | **KI-Prüfung** |
| Sidebar `sub` | Modell 1+2: Prüfung & WG | **Analyse & Entscheidung** |
| Seitentitel | Korrektur — Modell 2 | **KI-Prüfung — Plausibilität & Warengruppen** |

### 18. Tooltips nutzerfreundlich + Icons blau ✅

Alle `<app-tip>`-Texte mit Entwickler-Inhalten bereinigt:
- "Backend muss betrag_eur liefern" → "Diese Funktion wird in Kürze verfügbar sein"
- "Modell 1 / Modell 2" → "die KI"
- "req 2.1.1", "Feintuning" → entfernt bzw. allgemeinverständlich ersetzt

`.tip-icon` in `styles.scss`: Farbe von `var(--t3)` (grau) auf `var(--blue)` geändert, Opacity 0.55 → 0.6. Neue Chip-Klasse `.c-lb` (Leuchtblau) ergänzt.

### 19. Sortierung vereinfacht ✅ → weiter vereinfacht (2026-06-06)

- **KI-Vorschlag**: Sortier-UI entfernt — Spalte immer A→Z als Sekundärsortierung
- **Bestelltext**: Sortier-UI ebenfalls entfernt
- **Konfidenz** (Session 3): Einzige sortierbare Spalte, Klick auf Header löste Sortierung aus
- **Konfidenz** (Session 4, 2026-06-06): Klick-Sortierung aus dem Spalten-Header entfernt — Sortierung ausschließlich über den Toolbar-Button. Der Header zeigt jetzt ein ⓘ-Tooltip wie alle anderen Spalten. `sortIcon()`, `sortActive()`, `sortTitle()` aus `review.ts` gelöscht (waren nur noch im Header genutzt).

**Begründung:** Zwei parallele Wege zur selben Aktion (Header-Klick + Toolbar-Button) waren inkonsistent. Der Toolbar-Button ist sichtbarer und expliziter.

### 20. Info-Text: Position + Inhalt ✅

Block an den Seitenanfang verschoben (vor DEV-Banner und alle Cards). Text umformuliert:
> *"Die KI analysiert alle Einträge automatisch und schlägt bei Bedarf eine bessere Kategorie vor. Du legst selbst fest, ab welcher KI-Sicherheit und bis zu welchem Betrag Vorschläge automatisch übernommen werden — den Rest prüfst du manuell."*

ℹ-Icon entfernt. "Auto-Bestätigen (N)" als Button-Label statt "Übernehmen (N)".

### 21. Ergebnis-Verteilungsdiagramm (4 Segmente) ✅

Aus der alten `PlausibilityView` portiert und erweitert. Sitzt zwischen KPI-Kacheln und Tabellen-Toolbar.

| Segment | Farbe | Quelle |
|---|---|---|
| Korrekt | Blau `var(--blue)` | `plausibility.stats.plausible` |
| KI sehr sicher | Grün `var(--green)` | `confCounts().hoch` |
| KI sicher | Amber `var(--amber)` | `confCounts().mittel` |
| KI unsicher | Rot `var(--red)` | `confCounts().niedrig` |

Neues `distribution()` computed in `review.ts` berechnet prozentuale Anteile für die Flex-Breiten.

### 22. KPI-Boxen: 4 → 2 ✅

Die vier Boxen "Eingabe aus Modell 1 / Neu zugeordnet / KI unsicher / Bestätigt" waren redundant mit dem Verteilungsdiagramm. Ersetzt durch zwei gleichbreite Boxen (`.g2`-Grid):
- **Analysiert** — Gesamtanzahl aus `state.upload()?.row_count`
- **Nicht plausibel** — aus `state.plausibility()?.stats?.implausible`

### 24. API-Budget-Widget in Sidebar (Dev-Mode) ✅

Das Budget-Widget (`sbudg`) war schon im Sidebar-HTML vorhanden, aber hinter `@if (b)` — ohne Backend-Verbindung blieb `b` null und das Widget war unsichtbar.

Fix: `MOCK_BUDGET` in `src/app/dev/mock-data.ts` ergänzt (`BudgetStats` mit Beispielwerten: $1.24 / $25, 54 Calls, 312 Cache-Hits, gpt-4o-mini). In `app.ts` lädt `refreshBudget()` bei Backend-Fehler im Dev-Mode jetzt `MOCK_BUDGET` — das Widget erscheint damit auch lokal ohne laufendes Backend.

In Production ändert sich nichts: `isDevMode()` ist dort `false`, der Fallback greift nie.

---

### 23. Farb-Konsistenz: Diagramm ↔ Konfidenz-Chips ✅

Vorher: Diagramm nutzte Leuchtblau/Dunkelblau für KI-Konfidenz, Tabellen-Chips nutzen Grün/Amber.

`badge()` in `review.ts` zurück auf `c-gr` (sehr sicher) / `c-am` (sicher) / `c-rd` (unsicher). Diagramm-Farben angepasst: Leuchtblau/Dunkelblau → Grün/Amber. "Korrekt" im Diagramm nutzt Blau als neutrale Sonderkategorie.

---

## Session 5 — Layout-Rahmen, Logo, Dashboard-Charts & Review-Feinschliff (2026-06-07/08)

### 31. Aubergine-Rahmen um den Hauptinhalt (GitLab-Stil) ✅

**Quelle:** Wunsch nach mehr Struktur/Tiefe im Content-Bereich, Vorbild GitLab (oberer Balken + zarte Seitenränder, gerundete Inhalts-Ecken).

**Umsetzung (`app.scss`):**
- `#app` erhält `background: var(--bg-side)` (Aubergine) — damit die abgerundeten Ecken Aubergine durchscheinen lassen.
- `#mn` bildet den Rahmen über **Padding** (nicht `border`): `padding-top: 45px`, `padding-right: 35px`, `padding-bottom: 8px`, Hintergrund Aubergine. Links kein Rahmen (grenzt direkt an Sidebar).
  - **Warum Padding statt Border:** Bei `border` + `border-radius` berechnet der Browser den inneren Eckradius als `radius − border-width` → bei 45px Border und 8px Radius wären die inneren Ecken scharf (0). Mit Padding bleibt der innere Radius konstant.
- Innere weiße Panel-Ecken: `border-radius: 8px` auf `#tb` (oben links/rechts) und `#va` (unten links/rechts). Die Aubergine von `#mn`/`#app` scheint in den Eck-Bögen durch.
- Sidebar-`box-shadow` (`#sb`) entfernt → nahtloser, kantenloser Übergang Sidebar ↔ Rahmen (identische Farbe).

### 32. Aubergine Top-Leiste (`#tbar`) für globale Aktionen ✅

**Quelle:** Der obere Rahmenbereich war leer; bei GitLab stehen dort rechts nützliche Aktionen.

**Vorher:** Die weiße Header-Zeile `#tb` enthielt Titel **und** rechtsbündig Dateiname, Schritt-Badge, Theme-Toggle und Logout.

**Nachher:** Neue Aubergine-Leiste `#tbar` (Höhe 45px) im oberen Rahmenbereich nimmt die rechtsbündigen globalen Elemente auf; der Titel (`#tb-ttl`) bleibt allein in der weißen `#tb`-Leiste. Da der Header in `app.html` global (nicht pro View) ist, gilt das automatisch für Upload / KI-Prüfung / Dashboard.

- Neue `.tbar-btn`-Klasse: transparente Buttons mit halbtransparenter weißer Border/Text, Hover hellt auf — passend zur Sidebar-Ästhetik.
- `.t-meta` und `#s-badge` für den dunklen Hintergrund umgestylt (helle Schrift / halbtransparenter weißer Chip).
- Alte `#tog`-Styles (Theme-Toggle im weißen Header) entfernt — jetzt ungenutzt.

> Hinweis: Dateiname und Schritt-Badge sind globaler State und erscheinen in allen Views (Fallback `—`). Verhalten unverändert, nur die Elemente wurden verschoben.

### 33. Sidebar-Schriftgrößen auf GitLab-Niveau angehoben ✅

Viele Sidebar-Texte waren mit 9–11px schwer lesbar. Angehoben (`app.scss` + Inline-Styles in `app.html`):

| Element | Vorher | Nachher |
|---|---|---|
| Step-Labels (`.sl-m`, Upload/KI-Prüfung/Dashboard) | 11px | **14px** |
| Step-Sub-Labels (`.sl-s`) | 9px | **12px** |
| Titel "THG Analyse" (`.sbh-ttl`) | 15px | **18px** |
| Trichter-Zahlen (`.fnum`) | 11px | **14px** |
| Trichter-Labels (inline) | 10px | **12px** |
| Trichter-/Budget-Titel (`.ftit`, `.btit`) | 9px | **11px** |
| Budget-Werte (`.brow2`) | 10px | **13px** |
| Budget-Detail (inline) | 9px | **11px** |
| Footer (`.sfoot`) | 9px | **11px** |
| Sidebar-Badges (`.brow .badge`, scoped) | 10px | **11px** |

Globaler `.badge`-Stil bleibt unangetastet — nur Sidebar-Instanzen via `.brow .badge` vergrößert.

### 34. Hochbahn-Logo in der Sidebar ✅

**Vorher:** Textzeile "HAMBURGER HOCHBAHN AG".

**Nachher:** Offizielles Logo oben links (`<img class="sbh-logo" src="hochbahn-logo-trim.png">`), "THG Analyse" bleibt darunter.

- **Quelldatei:** `public/hochbahn-logo-2.webp` (860×478, hochauflösend, aber mit viel Weißraum-Padding).
- **Aufbereitung:** Mit PIL auf die Inhalts-Bounding-Box zugeschnitten → `public/hochbahn-logo-trim.png` (860×157). Wichtig: Crop-Box auf Bildgrenzen clampen, sonst füllt PIL außerhalb liegende Bereiche mit Schwarz (erzeugte sonst dünne schwarze Striche links/rechts).
- **Darstellung:** Auf weißem, abgerundetem Plättchen (`.sbh-logo`, weiches Shadow). Nötig, weil der graue "HOCHBAHN"-Schriftzug sonst auf Aubergine unlesbar wäre — so bleiben Markenrot + Lesbarkeit erhalten.
- **Größe & Ausrichtung (Feinschliff):** Bildbreite auf **85px** reduziert (vorher 155px, dominierte den Kopfbereich). Linke Kante des Plättchens bündig mit dem Titel "THG Analyse" (`margin-left: 0`).
- Altes, blasses `Hochbahn-logo.png` gelöscht.

### 35. Review: Auto-Übernahme aus Karte in die Toolbar ✅

**Vorher:** Die "Automatisch übernehmen"-Leiste (Konfidenz-Schwelle + Betrag + Button) steckte zusammen mit der "KI-Analyse abgeschlossen"-Zusammenfassung in einer Karte — der wichtigste Button ging unter.

**Zwischenschritt (verworfen):** Eigene, prominente "★ Empfohlener nächster Schritt"-Karte unter dem Verteilungsdiagramm — wirkte zu aufdringlich und erzeugte zwei dicke rote Vollton-Buttons übereinander.

**Nachher:** Auto-Übernahme sitzt in der Tabellen-Toolbar (`review.html`), **mittig** zwischen Filtergruppe und Audit-Log-Gruppe (zwei `.f1`-Spacer flankieren `.auto-accept`).
- Button rot **umrandet** (`.aa-btn` in `styles.scss`: roter Rand, rote Schrift, heller Hintergrund) statt Vollton-Rot — fällt auf, ohne mit dem soliden "Auswertung ansehen →" zu konkurrieren.
- Konfidenz-Dropdown (`autoConfThreshold`) + Betrag-Input (`autoCostThreshold`) daneben.
- Die "KI-Analyse abgeschlossen"-Karte ist jetzt rein informativ (roter Akzentrand entfernt).
- **Betrag-Schwellenwert wieder aktiv:** Input ist nicht mehr `disabled`, zweiweg-gebunden an `autoCostThreshold`; der "⚠ ausstehend"-Warn-Chip wurde entfernt. Der `// TODO … betrag_eur`-Check in `autoAccept()` bleibt — sobald das Backend `betrag_eur` liefert, nur diese Zeile aktivieren. **→ Erledigt in Session 6 (Punkt 44): der Kosten-Check ist aktiv (`autoQualifies()`).**

### 36. Review: Sortier-Button-Bug behoben (erster Klick wirkungslos) ✅

**Symptom:** Der Konfidenz-Sortier-Button ("unsicher → sicher") tat beim ersten Klick nichts, erst der zweite wirkte.

**Ursache:** Die Default-Ansicht (kein aktiver Sort) zeigt Konfidenz bereits unsicher→sicher (entspricht `desc`). `toggleSort` startete für `confidence` ebenfalls mit `dir: 'desc'` → identische Reihenfolge, kein sichtbarer Effekt. Erst der zweite Klick (`asc`) änderte etwas.

**Fix (`review.ts`):** Erster Klick startet jetzt mit `dir: 'asc'` (sicher→unsicher) — das Gegenteil der Default-Ansicht, also sofort sichtbar. Folge-Klicks toggeln normal.

### 37. Review: Entschiedene Zeilen bleiben immer unten ✅

**Vorher:** Erledigte Zeilen (`_decision != null`) rutschten nur in der Default-Ansicht ans Ende. Sobald nach Konfidenz sortiert wurde, mischten sie sich wieder zwischen die offenen Zeilen.

**Nachher:** Der `if (sorts.length)`-Zweig in `sortedFiltered` (`review.ts`) bekommt dieselbe "decided last"-Vorsortierung wie der Default-Zweig. Erst offen/erledigt gruppieren, dann innerhalb der Gruppen die Spalten-Sortierung. Offene Aufgaben stehen damit durchgehend oben — unabhängig vom Sortier-Zustand.

### 38. Theme-Wechsel: Flackern zwischen Sidebar & Rahmen behoben ✅

**Symptom:** Beim Umschalten auf Dark Mode flackerte kurz eine Naht zwischen Sidebar und Hauptinhalt-Rahmen — sie wechselten nicht gleichzeitig.

**Ursache:** Nur `#sb` (Sidebar) hatte `transition: background 0.2s ease`. Die gleichfarbigen Aubergine-Rahmen-Elemente (`#app`, `#mn`) sowie `#tb`/`#va` hatten **keine** Transition → sie wechselten sofort, während die Sidebar 0.2s nachzog. Da Sidebar und Rahmen dieselbe Farbe haben und aneinandergrenzen, entstand währenddessen eine sichtbare Kante.

**Fix (`app.scss`):** Alle Shell-Elemente (`#app`, `#sb`, `#mn`, `#tb`, `#va`) nutzen jetzt einheitlich `transition: var(--tr)` (= `background 0.2s ease, border-color 0.2s ease, color 0.2s ease`). Damit faden alle Flächen synchron, keine Naht mehr. Cards/Tabellen/Buttons hatten `var(--tr)` bereits — nur die Layout-Hülle fehlte.

### 39. Dashboard: Balkendiagramm Top-WG nach Emissionen/Ausgaben (req 4.2) ✅

**Quelle:** Anforderung 4.2 / 4.2.1 — Balkendiagramm der WG mit den meisten Emissionen, Top-10 oder weniger.

**Umsetzung (reines Frontend, kein Backend-Aufwand):**
- `barChart`-computed in `dashboard.ts`: nimmt `top_wg`, mappt auf die aktive Metrik (`co2_after_t` im CO₂-Tab, `eur_after` im EUR-Tab), filtert `> 0`, sortiert absteigend, nimmt Top-10 und berechnet die Balkenbreite relativ zum Maximum.
- Neue Karte in `dashboard.html` direkt unter den KPI-Kacheln: horizontale Balken (WG-Label · Balken · Wert), reagiert auf den CO₂/EUR-Tab-Umschalter.
- `.bc-*`-Styles in `styles.scss` (div-Balken, konsistent mit dem bestehenden `.dbar`/`.fbar`-Ansatz — keine neue Chart-Library). CO₂-Balken grün, EUR-Balken Leuchtblau.
- **`MOCK_DASHBOARD`** in `mock-data.ts` ergänzt (10 WG-Einträge, KPIs, Funnel) und `dashboard.ts` `refresh()`-Error-Handler lädt es im Dev-Mode — damit ist das Dashboard (und das Diagramm) jetzt auch lokal ohne Backend sichtbar (vorher blieb es leer).

> Hinweis: Bundle-Budget-Warnung für `app.scss` (+338 B über 4 kB) nach den Style-Ergänzungen dieser Session — unkritisch (nur Warnung), ggf. später Budget in `angular.json` anheben oder Styles zusammenfassen.

**Mock-Daten korrigiert & konsistent gemacht (alle Zahlen ergeben 47):**
- `MOCK_PLAUSIBILITY.stats`: `plausible` 38→**40**, `unklar` 2→**0** → 40 plausibel + 7 implausibel = 47. Damit zeigt das Dashboard ("korrekt" = `total − not_plausible` = 40) dieselbe Zahl wie die Review-Übersicht (`plausible` = 40).
- `MOCK_PREDICTION.stats.regrouped_high_med` 5→**6** → passt zu den 7 rows (5×hoch + 1×mittel = 6 high/med, 1×niedrig). Behebt den sichtbaren Widerspruch "6 neue WG" (Review-Karte, aus rows) vs. "5 neu zugeordnet" (Sidebar-Funnel, aus stats — liest `regrouped_high_med`).
- `MOCK_DASHBOARD`: `funnel.regrouped` 5→**6**, `regroup_rate_pct` 10.6→**12.8** (6/47).
  - **Korrektur (Session 5, später):** `regrouped_count` ist backend-seitig **nicht** die Zahl der Umgruppierungen, sondern die **Gruppengröße `n`** (Anzahl Bestellungen je WG, siehe `services/dashboard.py` `n=("__amount","size")`). Die Mock-Werte wurden daher auf realistische Bestellzahlen je WG gesetzt (Summe ≈ 47) — Grundlage für das Histogramm (Punkt 42). Die „Anzahl"-Spalte im Top-WG-Detail zeigt damit Bestellzahlen, nicht „6".
- **Robusteres Laden:** `dashboard.ts` `refresh()` lädt das Mock jetzt nicht nur bei API-Fehler, sondern auch wenn das Backend erreichbar ist, aber ein **leeres** Resultat (`top_wg` leer) liefert — sonst blieb das Dashboard im Dev-Mode leer.

**Konsistenz-Modell (Dev-Mock):** 47 gesamt = 40 plausibel + 7 implausibel · die 7 implausiblen = 6 high/med (neu zugeordnet) + 1 niedrig (unsicher/offen) · Auto-Bestätigen-Default (Schwelle „sehr sicher"/hoch) erfasst die 5 hoch-Zeilen → Button zeigt „(5)".

### 40. Review: "KI-Vorschlag" + "Neue WG wählen" zu einer Spalte "Warengruppe" ✅

**Quelle:** Zwei getrennte Spalten ("KI-Vorschlag" als Text + "Neue WG wählen" als Dropdown) waren redundant und breit. Zusammengeführt zu einer Spalte → eine Spalte gespart, intuitiverer Workflow.

**Verhalten (`review.html` + `review.ts`):**
- Ein einziges Dropdown pro Zeile, **vorausgewählt auf den KI-Vorschlag** (`[ngModel]="r._selected_wg ?? r.suggested_wg_name ?? ''"`) — der Nutzer sieht den Vorschlag sofort, ohne zu klicken.
- Der KI-Vorschlag ist die **erste Option**, fett + mit Suffix „(KI)", darunter `<optgroup>` „Andere Warengruppen" alphabetisch (Helper `catalogOthers()` blendet den Vorschlag dort aus, um Dopplung zu vermeiden).
- Neue Methode `wgPick()`: gewählter Wert = KI-Vorschlag → als Übernahme `decide('ok')`; andere WG → `wgChange()` → `new_wg`. In beiden Fällen wird die Zeile „erledigt" (opacity 0.65), genau wie zuvor.
- ✓ in der Aktion-Spalte bestätigt weiterhin den (vorausgewählten) KI-Vorschlag; ✗ lehnt ab; manueller WG-Wechsel lässt die Aktion-Spalte leer (req 2.3.1).
- Solange der unveränderte KI-Vorschlag angezeigt wird, ist der Dropdown-Text dezent blau (`.wg-ai`); bei manuellem Override normale Schriftfarbe — visueller Hinweis „KI-Wert vs. selbst gewählt".
- Spalten-Filter (KI-Vorschlag-Häufigkeit) wandert in den „Warengruppe"-Header; Spaltenbreiten neu verteilt (eine Spalte weniger), Expand-Detailzeile `colspan` 6→5.

> Ersetzt die Rationale von Punkt 6 (dort wurde der KI-Vorschlag bewusst aus dem Dropdown entfernt, weil er in einer eigenen Spalte stand — diese Spalte gibt es jetzt nicht mehr).

> **Optionales Folge-Improvement (Niedrig):** Echtes Custom-Dropdown statt nativem `<select>`. Native `<option>`-Elemente lassen sich plattformübergreifend nicht zuverlässig mit Badge/Fett gestalten — der KI-Vorschlag trägt daher nur das Suffix „(KI)". Für einen echten KI-Badge (farbiger Chip/Icon im Dropdown) bräuchte es eine eigene Komponente (z. B. Angular CDK Listbox/Overlay). Rein kosmetisch, mittlerer Aufwand. Siehe Tabelle „Noch offene Punkte".

### 41. UI-Politur: Expand-Pfeil, Scrollbar & gerundete Ecken ✅

- **Expand-Pfeil** (▸/▾ für die Modell-1-Begründung) war mit 11px grau leicht zu übersehen → 16px, fett, Leuchtblau (`review.html`).
- **Scrollbar sichtbarer:** `::-webkit-scrollbar` 5px→10px, Thumb in `var(--t3)` (Grau, Hover `var(--t2)`), abgerundet, transparenter Rand via `background-clip: padding-box` (wirkt schlanker, klebt nicht am Rand). Firefox via `scrollbar-width: thin` + `scrollbar-color`.
- **Scrollbar nicht mehr in den Ecken:** Header (`#tb`) + Body (`#va`) sind jetzt in ein `.panel` gewickelt, das die 8px-Rundung + `overflow: hidden` trägt. Der Scroll passiert im inneren `#va` (ohne eigene Rundung) → die Scrollbar wird sauber von den runden Panel-Ecken geclippt, statt in sie hineinzulaufen. `#tb`/`#va` haben keine eigenen `border-radius` mehr.

### 42. Dashboard: Histogramm (req 4.4) + Sankey-Platzhalter, redundante Boxen ersetzt ✅

**Quelle:** Die beiden `.g2`-Boxen waren redundant — „Zweistufiger Analyse-Durchlauf" doppelte den Analyse-Trichter der Sidebar, „Top-WG Ranking" war eine abgespeckte Version der „Top-WG Detail"-Tabelle darunter.

**Box 1 (Analyse-Durchlauf) → Histogramm „Emissionsintensität je Warengruppe" (req 4.4):**
- `histogram`-computed in `dashboard.ts`: Rate = aktive Metrik (CO₂e nachher bzw. €) **/ Anzahl Bestellungen** je WG (`regrouped_count` = backend `n` = Gruppengröße, req 4.4.1). Filtert Rate > 0, sortiert absteigend (req 4.4.3), Top-10.
- **Horizontale Balken** (`.bc-row` + `.bc-bar.bc-hist` in Aubergine) über die **volle Breite** — mit Rate-Spalte (`.hist-rate`) und **Anzahl-Spalte „n=…"** (`.hist-n`, req 4.4.2). Reagiert auf den CO₂/EUR-Tab.
- Anordnung: full-width unter dem Balkendiagramm (4.2) — nicht mehr in der halbbreiten `.g2`-Box. (Kurzzeitig vertikal getestet, auf Wunsch wieder horizontal, da besser lesbar.)

**Klare Titel + Info-Tooltips für alle Dashboard-Boxen** (damit der Unterschied der Diagramme sofort klar ist):
- Balkendiagramm (4.2): „Größte Emittenten/Ausgabenposten je Warengruppe" — **Gesamtwerte** (wo liegt der größte Hebel).
- Histogramm (4.4): „Emissionsintensität je Warengruppe" — **pro Bestellung** (CO₂-intensive Kategorien, mengenunabhängig).
- Detailtabelle: „Warengruppen vorher/nachher" mit Tooltip zu allen Spalten.
- Sankey: „Umverteilung der Warengruppen (Vorher → Nachher)".

**Box 2 (Top-WG Ranking) → Platzhalter „Umverteilung der Warengruppen" (req 4.1):** ans **untere Ende** des Dashboards verschoben und **deutlich höher** (`.sankey-soon` min-height 440px, gestrichelter Rahmen) — dort sollen später Dutzende WG-Flüsse (Quelle links → Ziel rechts, Bandbreite = Volumen) dargestellt werden.

**Farben gemäß Corporate Design (`Use Case/Corporate Design Hochbahn.pdf`):**
- Das Balkendiagramm (4.2) nutzt Grün/Blau; das Histogramm (4.4) nutzt bewusst **Aubergine** (Brand-Primärfarbe) zur klaren Unterscheidung. Neue Theme-Variable `--chart-hist`: Light `#470F34` (Aubergine), Dark `#c76aa0` (hellere Aubergine-Abstufung, damit Balken auf dunklem Grund sichtbar bleiben — die Brand erlaubt „Abstufungen" der Primärfarben).
- **Brand-Konstanten verifiziert** gegen das PDF: `--hb-rot #E2011F`, `--hb-aubergine #470F34`, `--hb-leuchtblau #0D9AF2`, Weiß `#FFFFFF` — alle exakt korrekt. `--blue #0069b4` ist eine dunklere, WCAG-AA-taugliche Leuchtblau-Abstufung für Text (vom PDF-Abstufungs-Konzept gedeckt). Grün/Amber bleiben als semantische Konfidenz-Ampel (sehr sicher/sicher/unsicher) — laut Brandbook „Sekundärfarben im Ausnahmefall" zulässig.

**Mock-Korrektur:** `regrouped_count` in `MOCK_DASHBOARD` auf realistische Bestellzahlen je WG gesetzt (Summe ≈ 47), da es backend-seitig die Gruppengröße ist — Voraussetzung für sinnvolle Histogramm-Raten. Die Detailtabelle unten zeigt diese Zahlen in der „Bestellungen"-Spalte.

**Detailtabelle aufgeräumt:**
- Spalte „Conf. Ø" (durchschnittliche KI-Konfidenz) **entfernt** — das Backend setzt `avg_confidence` hart auf `"hoch"` (`services/dashboard.py`), die Spalte zeigte also produktiv für jede WG „sehr sicher" und war damit nutzlos/irreführend. `confidenceLabel()`/`confidenceBadge()` aus `dashboard.ts` gelöscht, ebenso aus dem Excel-Export.
- Δ-Symbol durch **„Veränderung"** (Header) + **↓/↑-Pfeile** in den Zellen ersetzt (grün = gesunken, rot = gestiegen) — lesbarer als das nackte Δ.
- Export-Labels korrigiert: „Δ (%)" → „Veränderung (%)", „Anzahl regrouped" → „Anzahl Bestellungen" (es ist die Gruppengröße, nicht die Umgruppierungszahl).

### 43. Review: Reset-Button + reaktive Auto-Übernahme + Brand-Blau im Diagramm ✅

**Ergebnis-Verteilungs-Diagramm:** Das „Korrekt"-Segment nutzte `var(--blue)` (`#0069b4` — eine dunklere Text-Abstufung), nicht das Brand-Leuchtblau. Auf **`var(--hb-leuchtblau)` `#0D9AF2`** umgestellt (Balken + Legende).

**Auto-Übernahme mit Abgleich beim Button-Klick + Reset (req 2.2):**
- Neues `_auto`-Flag pro Zeile unterscheidet **automatisch gesetzte** von **manuellen** Entscheidungen (`decide(row, decision, isAuto)`; manuelle ✓/✗/WG-Wechsel setzen `_auto = false`).
- **Der Abgleich passiert erst beim Klick auf „Auto-Bestätigen"** (nicht beim Dropdown-Wechsel): strengere Regel (z. B. sicher → sehr sicher) **entfernt** automatisch gesetzte Haken, die nicht mehr erfüllen; lockerere Regel **setzt** Haken für jetzt erfüllende, offene Zeilen. Manuelle Entscheidungen (✓ / ✗ / WG geändert) bleiben unberührt. Das Dropdown setzt nur das Niveau (`autoConfThreshold.set`).
- **Button zeigt die Anzahl ALLER betroffenen Zeilen** (`autoAffected`) — in beide Richtungen: offene erfüllende Zeilen, die neu bestätigt würden, PLUS automatisch gesetzte Haken, die bei strengerem Niveau wieder entfernt würden. Reagiert auf das Dropdown, sodass man die Auswirkung schon vor dem Klick sieht (Button deaktiviert, wenn 0 Zeilen betroffen).
- **Reset-Button „↺ Zurücksetzen"** (`resetDecisions`) setzt alle Entscheidungen auf den Ausgangszustand und leert das Audit-Log.
- **Audit-Log konsistent:** Zurückgenommene Entscheidungen werden via neuem `AppState.clearRowLog(rowIndex)` aus dem Log entfernt — kein „accept"-Eintrag bleibt zurück, wenn ein Haken wieder verschwindet.

**Reaktivitäts-Fix:** Entscheidungen mutieren die Zeilen-Objekte in-place; das bisherige `prediction.set({ ...pr })` ließ die `rows`-Array-**Referenz** unverändert, sodass abgeleitete Computeds (`autoAffected`, `summary`, …) memoisiert blieben und der Button-Zähler nach dem Klick stehen blieb. Alle Mutations-Pfade setzen jetzt `prediction.set({ ...pr, rows: [...pr.rows] })` (neue Array-Referenz) → die Zähler aktualisieren sich korrekt (z. B. auf 0 nach dem Anwenden). Die Chips/Opacity der Zeilen wurden vorher nur dank Zone.js-Change-Detection sichtbar, nicht über die Signal-Propagierung.

> Einschränkung (Backend): Im Nicht-Mock-Betrieb existiert kein „Entscheidung löschen"-Endpunkt — Reset/Revert wirken aktuell nur im Frontend-State. Für vollständige Persistenz bräuchte es einen DELETE-Pfad in `/api/prediction/decision`.

---

## Session 6 — Betrag (€): Anzeige, Filter, Sortierung & Kostenschwelle (2026-06-16)

### 44. Backend liefert `betrag_eur`; Review-Tabelle bekommt die Betragsspalte ✅

Schließt den letzten blockierten Punkt 5 (req 1.1 / 1.2 / 2.1.2). Damit ist Levkes Wunsch *„Sort by values (monetary values)"* vollständig erfüllt.

**Backend:**
- `betrag_eur: float | None` in `PlausibilityRow` **und** `PredictionRow` (`schemas/models.py`).
- Spaltenerkennung zentralisiert in `core/data.py`: `AMOUNT_COLUMNS` (`Wert/KWähr`, `Nettobetrag`, `Bruttobetrag`, `Wert`, `Betrag`), `amount_column()` und `amount_series()` (numerisch via `pd.to_numeric`, `NaN` → `null`). Das reale Beispielfile nutzt `Wert/KWähr`.
- `services/dashboard.py` nutzt jetzt denselben Helper (vorher eigene Kopie `_amount_column`) → eine einzige Quelle für „die Betragsspalte".
- `services/plausibility.py` + `services/prediction.py` lesen den Betrag pro Zeile über den DataFrame-Index und runden auf 2 Nachkommastellen.

**Frontend** (`review.ts` / `review.html`):
- **Spalte „Betrag"** zwischen „WG bisher" und „Warengruppe", rechtsbündig; `formatBetrag()` formatiert als € ohne Nachkommastellen, fehlender Betrag → „—". `colspan` der Detail-Zeile von 5 → 6, Spaltenbreiten neu verteilt (7 Spalten).
- **Filter-Dropdown** wie bei den anderen Spalten: `betragFilter`-Signal + `betragOptions()` mit Trefferzahl je Bereich. Genau **zwei Bereiche**, deren Grenze stets dem „Auto-Übernahme bis Betrag"-Wert folgt — `< X €` (die auto-übernehmbaren Zeilen) und `≥ X €`. `betragBuckets` ist ein Computed über `autoCostThreshold`; die Bucket-Keys (`lt`/`gte`) bleiben stabil, sodass eine aktive Auswahl beim Ändern des Schwellenwerts erhalten bleibt und nur gegen die verschobene Grenze neu filtert.
- **Standard-Sortierung:** primär Konfidenz (unsicher zuerst), sekundär Betrag (höchster zuerst), unbekannte Beträge ans Ende.
- **Kostenschwelle aktiv:** neuer Helper `autoQualifies(r)` bündelt Konfidenz- **und** Kostenkriterium (`betrag_eur < autoCostThreshold`); leeres Limit oder unbekannter Betrag blockiert nicht. `autoAffected` (Vorschau) und `autoAccept()` teilen sich den Helper — der frühere `// TODO … betrag_eur`-Kommentar ist entfernt.

**Mock-Daten:** Die 7 `MOCK_PREDICTION`-Zeilen haben gestaffelte Beträge (95 – 15.400 €) über alle Buckets, sodass Filter, Sortierung und Kostenschwelle im Dev-Mode sichtbar sind.

**Client-Regenerierung:** `scripts/dump_openapi.py` → `npm run openapi:generate` (regulärer Weg). Inhaltlich änderten sich nur `prediction-row.ts` + `plausibility-row.ts` (je `betrag_eur?: number | null`); der Rest des Diffs war reines Zeilenende-Rauschen und wurde auf CRLF renormalisiert.

### Dashboard-Feinschliff (Folge-Anpassung)

- **Balkendiagramm-Titel entschärft:** „Größte Emittenten / Ausgabenposten je Warengruppe" war irreführend (es sind WG-Gesamtwerte, keine „Emittenten"). Neu: **„Warengruppen mit den höchsten Gesamtemissionen"** bzw. **„… Gesamtausgaben"** (tab-abhängig).
- **Detailtabelle „Warengruppen vorher/nachher": Betrag-(€)-Spalte** zwischen „Bestellungen" und „EF" ergänzt (zeigt `eur_after`, den Gesamtbetrag der WG; im CO₂-Tab echter Mehrwert, da vorher/nachher dort t CO₂e zeigen). Spaltenbreiten neu verteilt (7 Spalten), Karten-Tooltip ergänzt. Der Excel-Export führte die Beträge bereits als eigene Spalten und blieb unverändert.

---

## Session 7 — Scrollbare Detailtabelle & suchbares WG-Dropdown (2026-06-17)

### Dashboard: Detailtabelle scrollt innerhalb der Box (~10 Zeilen)

Die Detailtabelle „Warengruppen vorher/nachher" zeigte zuvor **alle** Zeilen und konnte das Dashboard stark in die Länge ziehen. Jetzt:
- Tabelle in `<div class="tw-scroll">` gewickelt (`max-height: 372px; overflow-y: auto`) → die Box zeigt ~10 Zeilen, der Rest wird **innerhalb der Box** gescrollt.
- `.tw-scroll thead th` ist `position: sticky; top: 0` → der Spaltenkopf bleibt beim Scrollen sichtbar. Die Regeln sind über `.tw-scroll` nur auf die Dashboard-Detailtabelle gescoped; die Review-Tabelle bleibt unberührt.
- `MOCK_DASHBOARD.top_wg` von 10 → 21 Einträgen erweitert, damit der Scroll-Effekt im Dev-Mode sichtbar ist (absteigende `eur_after`, gemischte `delta_pct`-Vorzeichen, einige `ef_ok: false`).

### KI-Prüfung: natives WG-`<select>` → suchbares Combobox (`WgComboComponent`)

Auf Nachfrage: Bei sehr vielen Warengruppen musste man im nativen Dropdown bis ganz nach unten scrollen, um „➕ Neue Warengruppe…" zu erreichen. Eine `<option>` lässt sich in einem nativen `<select>` **nicht** sticky machen — daher Ersatz durch ein eigenes Widget:
- Neue, wiederverwendbare Komponente `src/app/shared/wg-combo.ts` (`<app-wg-combo>`). Trigger sieht aus wie das alte Select (inkl. blauer „(KI)"-Markierung, solange der KI-Vorschlag gilt — `showingSuggestion()`).
- **Popup** liegt `position: fixed` (Koordinaten aus `getBoundingClientRect`, gleiches Muster wie `TipComponent`), entkommt also dem `overflow:hidden` von Tabelle/Card; schließt bei Außenklick, `Escape`, Scroll und Resize.
- **Fixierter Kopf** (`.wg-combo-head`, `flex:none`): Suchfeld + „➕ Neue Warengruppe…" — beide bleiben immer im Sichtbereich, nur die Optionsliste (`.wg-combo-list`) scrollt. Damit ist die ursprüngliche Sticky-Idee erfüllt, ohne nach unten scrollen zu müssen.
- **Tippen filtert** (case-insensitive `includes`); KI-Vorschlag erscheint zuerst (mit „KI"-Tag). Tastatur: ↑/↓ bewegt das Highlight, Enter wählt, Escape schließt.
- Outputs `(pick)` / `(addNew)` mappen 1:1 auf die bestehende Logik: `wgPick(r, $event)` bzw. `wgPick(r, ADD_NEW_WG)` → Entscheidungs-/Audit-Pfade in `review.ts` unverändert. Ungenutztes `catalogOthers()` entfernt; alte `.wg-select`-Styles durch `.wg-combo-*` ersetzt.

**Zwei Folgefehler behoben:**
1. *Scrollen schloss das Dropdown:* Der `scroll`-Listener (capture) fing auch das Scrollen der Optionsliste ab. `onScrollOrResize` ignoriert jetzt Scrolls, deren Ziel im Panel liegt (`panelEl().contains(target)`) — nur ein Scroll des dahinterliegenden Inhalts schließt noch.
2. *Popup transparent nach WG-Auswahl:* Entschiedene Zeilen hatten `opacity: 0.65` auf der `<tr>` — das dimmte den gesamten Teilbaum inkl. des `position:fixed`-Popups (DOM-Kind der Zelle). Dimmung jetzt auf Zellen-Ebene (`tr.row-dim > td`), die WG-Zelle (`td.wg-cell`) bleibt deckend, nur ihr `.wg-combo-trigger` wird gedimmt → Popup wieder voll deckend.

**Selbst angelegte WGs verwaltbar (NEU-Badge + ⋮-Menü):**
- `review.ts` führt ein `customWgs`-Signal (`Set<string>`); `promptNewWg` trägt neue Namen ein. An die Combobox via `[customWgs]`.
- In der Optionsliste bekommen Custom-WGs ein grünes **„NEU"**-Badge und eine **⋮**-Schaltfläche. Das ⋮ öffnet ein kleines Aktionsmenü **Umbenennen / Löschen** — als eigene `position:fixed`-Ebene (z-index 1001), damit es nicht vom Overflow der scrollenden Liste abgeschnitten wird. (Die Optionszeile ist deshalb jetzt ein `<div role="option">` statt `<button>`, da sie ein klickbares Kind enthält; der ⋮-Klick `stopPropagation()`t, wählt also die Option nicht aus.)
- Outputs `(renameWg)` / `(deleteWg)` → `renameCustomWg()` / `deleteCustomWg()` im View. **Umbenennen** (Prompt) ersetzt den Namen im Katalog + Custom-Set und stellt alle betroffenen Zeilen via `wgChange()` um (loggt + Backend). **Löschen** (mit Rückfrage, inkl. Hinweis auf betroffene Zeilen) entfernt die WG und setzt betroffene Zeilen via `undecide()` zurück. Dubletten beim Umbenennen werden abgefangen.

### Alle Filter-Dropdowns als Custom-Widget (`SelectComponent`)

Native `<select>` zeigen ihr aufgeklapptes Menü im OS-Stil (nicht im App-Stil). Damit auch der **geöffnete** Zustand einheitlich aussieht, ersetzt eine generische Komponente `src/app/shared/select.ts` (`<app-select>`) alle nativen Selects der KI-Prüfung — **ohne** die WG-spezifischen Extras (kein „Neue WG", keine KI/NEU-Badges).
- Inputs `[options]` (`{value, label}[]`) / `[value]`, Output `(valueChange)`. Popup `position:fixed` (entkommt `overflow:hidden`), schließt bei Außenklick / Escape / Hintergrund-Scroll / Resize; Pfeiltasten + Enter zur Navigation. Ab > 8 Optionen erscheint automatisch ein **Suchfeld**.
- Betroffen: `max. Zeilen`, `Filter`-Status, `Auto-Übernahme ab`-Konfidenz sowie die Spaltenfilter **WG bisher / Betrag / Warengruppe / Konfidenz** (Letztere mit `class="sel-fill"` → volle Spaltenbreite). Optionslisten als Felder/Computeds in `review.ts` (`maxRowsSelectOptions`, `autoConfSelectOptions`, `statusSelectOptions`, `confSelectOptions`, `wgBisherSelectOptions`, `betragSelectOptions`, `wgFilterSelectOptions`).
- Der globale `select`-Stil (mit SVG-Caret) bleibt als Fallback für etwaige künftige native Selects; die Bestelltext-Filtereingabe bleibt ein normales `<input class="th-filter">`.

### Toolbar- & Eingabe-Feinschliff (KI-Prüfung)

- **Betragsfeld der Auto-Übernahme** (`bis Betrag (€)`): eigene Klasse `.amount-input` statt `.th-filter` (die `.th-filter` trug header-spezifisches `margin-top` / kleineres Padding). Größere Schrift (14px), breiteres Feld, **größere, dauerhaft sichtbare Spinner-Pfeile** (`::-webkit-inner-spin-button { opacity:1; width:17px; align-self:stretch }` → besser klickbar) und **Schrittweite 100** (`step="100"` `min="0"` statt 1er-Schritte).
- **Schrift in den Dropdowns nicht mehr CAPS/fett**: Trigger und Popup standen in den `th`-Spaltenköpfen und erbten `text-transform:uppercase` + `font-weight:700` + `letter-spacing`. `.sel-trigger` / `.sel-panel` / `.sel-opt` setzen das zurück (`text-transform:none`, `letter-spacing:normal`, `font-weight:400`); die gewählte Option wird dezent über Farbe (`var(--blue)`) statt fett markiert. Auch `.amount-input` ist `font-weight:400`.
- **Einheitliche Höhe** der Toolbar-Steuerelemente: `view-review .tbar .btn, .sel-trigger, .amount-input { height: 32px; box-sizing: border-box }` — Selects, Betragsfeld und alle Buttons (inkl. „↺ Zurücksetzen", „Auto-Bestätigen", „Log exportieren", „Auswertung ansehen") sind gleich hoch; Breiten dürfen variieren. Scoped auf `view-review`, damit die Dashboard-Toolbar unberührt bleibt.
- `.th-filter` (nur noch von der Bestelltext-Eingabe genutzt) bekam `margin-top: 5px` für etwas mehr Abstand zwischen Spaltentitel und Filterfeld; das ⋮-Aktionsmenü zeigt **„Umbenennen"/„Löschen"** als reinen Text (ohne Emojis).
