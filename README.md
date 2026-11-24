# CHIP Store Preischeck

Täglicher Vergleich der CHIP-Store-Preise mit den Angeboten auf BestCheck. Das Skript schreibt eine Teams-Nachricht (`output/preischeck-JJJJ-MM-TT.teams.txt`). Die Automation schickt genau diesen Text in den Teams-Kanal.

```bash
python3 preischeck.py --out output --state-dir state --no-pdf
```

## Was verglichen wird

- Sortiment: alle Produkt-URLs der CHIP-Store-Sitemap mit `changefreq` hourly. Preis, Streichpreis und EAN kommen aus dem JSON-LD der Produktseite. Der CHIP-Store-Preis ist versandfrei und damit der Endpreis.
- BestCheck: Suche über die EAN. Ein Treffer gilt nur, wenn die Produktseite im Frontend diese EAN zeigt und einen Block „Preisvergleich zu …“ hat. Ein einzelner Suchtreffer ohne diese Prüfung wird verworfen.
- Angebote kommen von `https://www.bestcheck.de/api/product/{id}/offers/`. Endpreis = Artikelpreis plus ausgewiesene Versandkosten.
- Aussteller, Ausstellungsware und Vorführgeräte zählen nicht mit. Der Händler dieTechnik wird immer ausgelassen, auch wenn die BestCheck-Seite das Wort „Aussteller“ nicht anzeigt. Beim WINBOT mini 2 folgt danach Cyberport.

## Warum die Suche allein nicht reicht

Die BestCheck-Suche liefert bei einer unbekannten EAN manchmal genau ein fremdes Produkt. Beispiel: die EAN der BE COOL Inverter-Klimaanlage landete auf dem SHX-Konvektor, und Kaufland stand dort mit 76,59 €. Auf der Klimageräte-Seite von BestCheck gibt es diesen Preis nicht. Seit dem 19. November 2026 muss die EAN auf der Produktseite stehen. Sonst wandert der Artikel in „Auf Bestcheck nicht gelistet“.

Der Samsung Galaxy Z Flip8 256GB bleibt vergleichbar: seine EAN steht auf der BestCheck-Seite, und Alza ist dort als Angebot sichtbar.

## Teams-Nachricht

Die farbigen Punkte stehen in der Teams-Nachricht. Verglichen wird mit der letzten State-Datei vor dem heutigen Datum (`state/preischeck-JJJJ-MM-TT.state.json`). Die Automation speichert die neue Datei auf `main`. Ein Produkt, das gestern in `win` stand, war grün (Bestpreis CHIP). Ein Produkt in `gap` war teurer als BestCheck, egal ob der Punkt rot oder gelb war.

Reihenfolge der Tabellen:

1. **Teurer als BestCheck**
2. **Geteilter Preis**
3. **Bestpreis, andere Händler sind teurer**
4. **Auf Bestcheck nicht gelistet**

In jeder Tabelle stehen zuerst die Produkte mit dem Wort „WINBOT“ oder „Enzo“ im Namen (Groß-/Kleinschreibung egal, nur ganze Wörter), danach alle übrigen. Beide Gruppen sind alphabetisch sortiert. Groß- und Kleinschreibung spielt keine Rolle, ä/ö/ü zählen wie a/o/u, ß wie ss. Der Satz zu den größten Abständen in der Kurzfassung bleibt nach Betrag sortiert.

### Farblogik

Teams hat keinen dunkleren roten und keinen dunkleren grünen Punkt als 🔴 und 🟢. Deshalb gilt:

- 🔴 **Bestpreis verloren** ist dunkelrot und das bisherige Rot. Gestern Bestpreis beim CHIP Store, heute ist der Bestpreis woanders.
- 🟠 **neu/geändert** ist das bisherige Rot, heller. Der Artikel ist neu in der Teurer-Tabelle oder CHIP-Preis, Abstand oder günstigster Endpreis haben sich geändert, und gestern war er nicht Bestpreis.
- 🟡 **unverändert**: gleicher CHIP-Preis, gleicher Abstand, gleicher günstigster Endpreis wie beim letzten Lauf.
- ⚪ **geteilter Preis**: der CHIP-Endpreis ist der günstigste, andere Händler liegen auf demselben Betrag. Auch dann, wenn der Artikel gestern grün oder teurer war.
- 🟢 **Bestpreis gewonnen** ist dunkelgrün und das bisherige Grün. Gestern lag der Bestpreis woanders, heute ist CHIP günstiger.
- 🟩 **Bestpreis**: CHIP ist günstiger als der nächste Händler, und der Artikel war gestern nicht in der Teurer-Tabelle. Einen helleren grünen Punkt gibt es nicht, deshalb das grüne Quadrat.
- ⚫ **nicht gelistet**: keine sichtbare BestCheck-Seite mit dieser EAN. Auch dann, wenn der Artikel gestern teurer oder Bestpreis war.

Beim ersten Lauf ohne State-Datei gibt es kein Dunkelrot und kein Dunkelgrün. Jede Zeile in „Teurer als BestCheck“ ist neu/geändert.

## Zuverlässigkeit

- **Code-Version:** Die zweite Zeile der Teams-Nachricht zeigt `Code-Version: <hash>`. Das ist der Git-Hash des Codes, der den Bericht erzeugt hat. Steht dort nicht der aktuelle Hash von `main`, lief der Bericht auf einer alten Kopie.
- **Neuester Code:** Der Automation-Prompt (`automation/CRON_PROMPT.md`) holt zuerst `git fetch origin main` und `git reset --hard origin/main`. So läuft nie ein veralteter Checkout.
- **Unvollständige Daten:** Seiten, die nicht abrufbar sind, werden nicht mehr stillschweigend übersprungen und nicht mehr als „nicht gelistet“ oder „einziger Anbieter“ gewertet. Fehlen bis zu 10 % der Produkte, steht oben in der Nachricht „⚠ n von N Produkten konnten heute nicht abgerufen werden“, und diese Produkte fehlen im Bericht. Fehlen mehr, endet das Programm mit Fehler und die Automation sendet nur eine Zeile „nicht erstellt“.
- **Wartungsmodus:** Ist chipstore.de im Wartungsmodus, bricht das Programm nach wenigen Sekunden ab. Ist nur die Sitemap nicht erreichbar, nutzt es die zuletzt gespeicherte Liste `state/product-urls.json`.

## Änderungen am 19. November 2026

- Code-Version in der Nachricht, Zuverlässigkeitsprüfungen (siehe oben) und `git reset --hard origin/main` am Anfang des Automation-Prompts. Anlass: Der Lauf von 10:01 Uhr hat eine alte Programmversion benutzt (Kaufland 76,59 € und dieTechnik 179,90 € standen noch im Bericht) und nur 73 statt rund 100 Artikel verglichen, weil der Shop nicht durchgehend erreichbar war.
- Aussteller und Vorführgeräte werden vor dem Vergleich entfernt. dieTechnik (Händler-ID 1120) wird immer ausgelassen, weil dieser Shop Aussteller führt. Beim Ecovacs WINBOT mini 2 bleibt Cyberport mit 199,00 € der nächste Händler, nicht dieTechnik mit 179,90 €.
- Falsche Suchtreffer ohne EAN auf der BestCheck-Seite werden nicht mehr verglichen. Die Mobile Inverter Klima fällt dadurch aus dem Vergleich mit Kaufland.
- Vierte Teams-Tabelle „Auf Bestcheck nicht gelistet“ mit schwarzem Punkt.

## Änderungen am 20. November 2026

- Wechsel der Preislage zum Vortag: gestern Bestpreis und heute teurer wird dunkelrot (🔴), gestern teurer und heute Bestpreis wird dunkelgrün (🟢). Beide stehen in der Legende.
- Teams hat keinen dunkleren Punkt als das bisherige Rot und Grün. Dunkelrot und dunkelgrün sind deshalb 🔴 und 🟢. „neu/geändert“ ist der hellere Punkt 🟠, der normale Bestpreis das grüne Quadrat 🟩.

## Änderungen am 24. November 2026

- Produkte in jeder Tabelle stehen alphabetisch. ä/ö/ü zählen wie a/o/u, ß wie ss, Groß- und Kleinschreibung ist egal. Die drei größten Abstände in der Kurzfassung bleiben nach Betrag geordnet.
- WINBOT- und Enzo-Produkte stehen in jeder Tabelle an erster Stelle, danach der Rest alphabetisch. Die kurz zuvor eingeführte Fettschrift für diese Produkte ist zurückgenommen.
