# Cursor Automation — täglicher Preischeck → Teams

Diesen Text als **Automation-Prompt** (Cron) verwenden. Repository `erdoBF/chipstore-preischeck`, Branch `main`.

```
Arbeite im Repository erdoBF/chipstore-preischeck auf Branch main.

1) Immer zuerst den neuesten Code holen, auch wenn schon ein Checkout vorhanden ist:
   git fetch origin main
   git checkout main
   git reset --hard origin/main
   Verwende niemals eine alte Kopie von preischeck.py, auch keine aus Notizen oder Memories.

2) python3 preischeck.py --out output --state-dir state --no-pdf
   Chrome/Chromium nicht installieren (--no-pdf braucht keins).

3) Prüfe, bevor du sendest:
   - Der Befehl endete mit Exit-Code 0.
   - Die Datei output/preischeck-JJJJ-MM-TT.teams.txt existiert (Datum heute in Europe/Berlin).
   - In der zweiten Zeile der Datei steht „Code-Version: <hash>“, und <hash> ist gleich der Ausgabe von git rev-parse --short HEAD.
   - Die Datei enthält die Überschrift „## Auf Bestcheck nicht gelistet“ oder die Kennzahl „Auf Bestcheck nicht gelistet“.
   - Steht bei „Datensätze prüfen“ eine Zahl größer 0, enthält die Datei die Überschrift „## Datensätze prüfen“.
   - Die Legende enthält „Bestpreis verloren“ und „Bestpreis gewonnen“.
   Ist eine Prüfung nicht erfüllt, oder endete der Befehl mit einem Fehler: Sende die Auswertung nicht. Schicke stattdessen genau diese eine Zeile per Teams-Werkzeug: „Preischeck vom TT.MM.JJJJ nicht erstellt: <erste Fehlermeldung des Programms oder die nicht erfüllte Prüfung>“. Beende danach den Lauf.

4) Sende den kompletten Inhalt von output/preischeck-JJJJ-MM-TT.teams.txt genau einmal mit dem Teams-Werkzeug in den konfigurierten Kanal.
   Keine eigene Zusammenfassung, keine eigene Tabelle, kein „Demo“-Präfix, kein PDF.
   Die Produktzeilen sind bereits alphabetisch sortiert. Die Reihenfolge nicht ändern.

5) Committe state/preischeck-JJJJ-MM-TT.state.json und state/product-urls.json auf main (nur diese Dateien, falls neu oder geändert) und pushe. So funktioniert der Tagesvergleich (🔴 Bestpreis verloren, 🟠 neu/geändert, 🟡 unverändert, 🟢 Bestpreis gewonnen) beim nächsten Lauf. Keine Dateien unter output/ committen.

Ändere nichts am Programm, am Layout und an den Texten.
```
