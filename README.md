# CHIP Store Preischeck

Täglicher Vergleich der CHIP-Store-Preise mit den Angeboten auf BestCheck. Das Skript schreibt eine Teams-Nachricht (`output/preischeck-JJJJ-MM-TT.teams.txt`). Die Automation schickt genau diesen Text in den Teams-Kanal.

```bash
python3 preischeck.py --out output --state-dir state --no-pdf
```

## Was verglichen wird

- Sortiment: alle Produkt-URLs der CHIP-Store-Sitemap mit `changefreq` hourly. Preis, Streichpreis und EAN kommen aus dem JSON-LD der Produktseite. Der CHIP-Store-Preis ist versandfrei und damit der Endpreis.
- BestCheck: Suche über die EAN. Ein Treffer gilt nur, wenn die Produktseite im Frontend diese EAN zeigt und einen Block „Preisvergleich zu …“ hat. Ein einzelner Suchtreffer ohne diese Prüfung wird verworfen.
- Angebote kommen von `https://www.bestcheck.de/api/product/{id}/offers/`. Endpreis = Artikelpreis plus ausgewiesene Versandkosten.
- Aussteller, Ausstellungsware und Vorführgeräte (erkannt am Angebotstext) zählen nicht mit.

## Warum die Suche allein nicht reicht

Die BestCheck-Suche liefert bei einer unbekannten EAN manchmal genau ein fremdes Produkt. Beispiel: die EAN der BE COOL Inverter-Klimaanlage landete auf dem SHX-Konvektor, und Kaufland stand dort mit 76,59 €. Auf der Klimageräte-Seite von BestCheck gibt es diesen Preis nicht. Seit dem 19. November 2026 muss die EAN auf der Produktseite stehen. Sonst wandert der Artikel in „Auf Bestcheck nicht gelistet“.

Der Samsung Galaxy Z Flip8 256GB bleibt vergleichbar: seine EAN steht auf der BestCheck-Seite, und Alza ist dort als Angebot sichtbar.

## Teams-Nachricht

Reihenfolge der Tabellen:

1. **Teurer als BestCheck**, roter Punkt bei neuen oder geänderten Abständen, gelber Punkt wenn der Abstand zum Vortag gleich ist.
2. **Geteilter Preis**, weißer Punkt. Der CHIP-Endpreis ist der günstigste, andere Händler liegen gleichauf.
3. **Bestpreis, andere Händler sind teurer**, grüner Punkt.
4. **Auf Bestcheck nicht gelistet**, schwarzer Punkt. Keine sichtbare BestCheck-Seite mit dieser EAN.

Der Tagesvergleich liest `state/preischeck-JJJJ-MM-TT.state.json` vom Vortag. Die Automation speichert die neue Datei auf `main`.

## Änderungen am 19. November 2026

- Aussteller und Vorführgeräte werden vor dem Vergleich entfernt. Der WINBOT MINI 2 von dieTechnik für 179,90 € ist so ein Aussteller und zählt nicht mehr als günstigeres Angebot.
- Falsche Suchtreffer ohne EAN auf der BestCheck-Seite werden nicht mehr verglichen. Die Mobile Inverter Klima fällt dadurch aus dem Vergleich mit Kaufland.
- Vierte Teams-Tabelle „Auf Bestcheck nicht gelistet“ mit schwarzem Punkt.
