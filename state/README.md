# Preischeck Tagesvergleich

`preischeck-YYYY-MM-DD.state.json` — vom Skript geschrieben, für die Teams-Punkte gegenüber dem letzten Lauf.

`gap` ist „teurer als BestCheck“ (gestern rot oder gelb). `win` ist „Bestpreis CHIP“ (gestern grün). Daraus werden 🔴 Bestpreis verloren und 🟢 Bestpreis gewonnen. Ältere Dateien haben dieselben Felder und bleiben gültig.

Der tägliche Cursor Automation-Lauf commitet und pusht die neue State-Datei auf `main`.