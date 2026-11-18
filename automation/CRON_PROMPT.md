# Cursor Automation — täglicher Preischeck → Teams

Diesen Text als **Automation-Prompt** (Cron) verwenden. Branch: `main`.

```
Arbeite im Repository erdoBF/chipstore-preischeck auf Branch main.

1) python3 preischeck.py --out output --state-dir state --no-pdf
   Bei Meldung, dass Chrome/Chromium fehlt: nicht installieren (--no-pdf braucht kein Chrome).

2) Wenn der Befehl fehlschlägt oder die Datei output/preischeck-JJJJ-MM-TT.teams.txt fehlt oder leer ist: nichts senden, abbrechen.

3) Lies output/preischeck-JJJJ-MM-TT.teams.txt (Datum heute, Zeitzone Europe/Berlin, Format YYYY-MM-DD).
   Sende den kompletten Dateiinhalt genau einmal per send_microsoft_teams_message in den konfigurierten Teams-Kanal.
   Keine eigene Zusammenfassung, kein „Demo“-Prefix, kein PDF.

4) Committe state/preischeck-JJJJ-MM-TT.state.json auf main (nur diese State-Datei, falls neu/geändert) und pushe, damit der Tagesvergleich (🔴/🟡) beim nächsten Lauf funktioniert. Keine anderen Dateien unter output/ committen.

Am Programm, am HTML/PDF-Layout und an den Report-Texten nichts ändern, außer der Nutzer fordert es ausdrücklich.
```