# ERP – Mentorský návod (pre úplného začiatočníka)

Tento návod ťa prevedie *od nuly* k spusteniu projektu vo **Visual Studio Code** a k pripojeniu na **MySQL**.
Nižšie sú presné kroky bez skákania.

## 0) Čo si práve dostal
Do projektu som pridal/opravil:
- `.env.example` – vzor pre tvoje tajné nastavenia (DB, e‑mail).
- `scripts/health_check.py` – jednoduchý test pripojenia k DB.
- `static/js/profitability.js` a `static/js/costs.js` – oživí sekcie Kancelária → Ziskovosť a Náklady.
- `.vscode/launch.json` – VS Code vie spustiť `app.py` jedným klikom.
- `requirements.txt` – zoznam Python knižníc.
- `.gitignore` – aby sa tajomstvá a logy necommitovali.
- Update `db_connector.py` – podporuje `DB_NAME` aj `DB_DATABASE` s defaultom `erp`.

## 1) Príprava prostredia
1. Nainštaluj *Python 3.11+* (https://www.python.org).
2. Nainštaluj *VS Code* (https://code.visualstudio.com/) a rozšírenie **Python**.
3. Nainštaluj *MySQL Server 8* a *MySQL Workbench*.
4. Vytvor MySQL používateľa (napr. `erp_user`) a **heslo si zapamätaj**.

## 2) Vytvor databázu `erp`
V MySQL Workbench spusti:
```sql
DROP DATABASE IF EXISTS erp;
CREATE DATABASE erp CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```
> Ak máš pripravené `.sql` skripty, importuj ich v Workbench v poradí, ktorý uvádzam v súbore `sql_active/zz_README_EXECUTION_ORDER.txt` (súčasť balíka).

## 3) Konfigurácia projektu (.env)
1. V koreňovom priečinku projektu vytvor súbor `.env` (podľa `.env.example`) a doplň **svoje** údaje:
   ```
   DB_HOST=localhost
   DB_USER=erp_user
   DB_PASSWORD=TVOJE_HESLO
   DB_DATABASE=erp
   ```
   *(E‑mail nastavenia nechaj prázdne, ak ich teraz nepotrebuješ.)*

## 4) Inštalácia závislostí
Otvor VS Code → Terminal:
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## 5) Otestuj pripojenie k DB
```bash
python scripts/health_check.py
```
Uvidíš:
```
DB OK: {{'ok': 1}}   # alebo podobný výstup
Missing essential tables: None  # ak chýbajú, importuj SQL skripty
```

## 6) Spustenie aplikácie (debug)
- Otvor VS Code, vľavo klikni na **Run and Debug** (alebo F5).
- Vyber konfiguráciu **Flask (app.py)** a spusti.
- Aplikácia beží na `http://127.0.0.1:5000` (alebo `http://localhost:5000`).

## 7) Modul Kancelária – základné sekcie
- **Ziskovosť:** JS `static/js/profitability.js` volá API `POST /api/kancelaria/profitability/getData` a vykreslí prehľad.
- **Náklady:** JS `static/js/costs.js` volá API `POST /api/kancelaria/costs/getData`.

### Ako sa inicializujú tieto moduly?
V tvojej šablóne (HTML) by mali existovať elementy:
```html
<div id="section-profitability"></div>
<div id="section-costs"></div>
```
A skripty by mali byť načítané (typicky na konci stránky):
```html
<script src="/static/js/profitability.js"></script>
<script src="/static/js/costs.js"></script>
<script>
  // Spustenie modulov po načítaní stránky
  if (window.initializeProfitabilityModule) initializeProfitabilityModule();
  if (window.initializeCostsModule) initializeCostsModule();
</script>
```
Neboj sa, **nezasahuje to do vzhľadu** – iba dopĺňame obsah do existujúcich sekcií.

## 8) Najčastejšie problémy (FAQ)
- **Chyba pripojenia k DB:** skontroluj `.env` a či MySQL beží.
- **Chýbajúce tabuľky:** importuj SQL skripty v `sql_active/`.
- **E‑mail neodchádza:** vyplň `MAIL_*` premenné v `.env` alebo nechaj e‑mailové funkcie vypnuté.

## 9) Bezpečnosť
- Nikdy necommituj `.env`.
- Heslá ukladaj do správcu hesiel.
- V produkcii nastav `FLASK_DEBUG=False`.

---
*Mentorský tip:* rob malé kroky. Spusti health‑check → importuj tabuľky → znova health‑check → spusti aplikáciu.
