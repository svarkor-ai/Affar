# Affär — fullständigt affärssystem (fullstack ERP)

**STATUS 2026-08-25 (integration av fas 2a):** Backend-moduler levererade som tarballs i
teddy-workspace, integrerade här i repot. MEN: C1-config saknas (650.2 blocker — appen
startar inte utan den), customers-router saknas, frontend (nicke 650.13) saknas i
workspace. Reparation dispatcherar till teddy (config+customers) och nicke (frontend).

**GOAL:** Ett fullständigt, fungerande affärssystem (fullstack ERP) med orderhantering
(inkl. internationell tracking, POC), fakturor, betalning, kunddata och inköp, i en
frontend med de användartyper som ett komplett system kräver. Byggs mot ett befintligt
affärssystem som mall (ERPNext) och hostas på vm106.

**ACCEPTANCE (fas 2+):** appen serverar på sibbamala.com/affar (efter att repo gjorts
publikt), fullstack fungerar end-to-end, frontend täcker användartyper, och ett reellt
flöde (order→faktura→betalning, resp. kund→inköp) bevisas med verkliga anrop.

**Ägarens beslut (2026-08-25):**
1. Basval: delegerat till mig — "Välj en bra bas", "enklaste som är skalbar".
2. Fullstack (frontend + backend + databas).
3. Vill ha en plan i flera faser → fasindelat bygge, MVP först.
4. Enklaste skalbara lösning → FastAPI + SQLAlchemy + SQLite (→Postgres-skalväg),
   React (Vite) frontend, JSON REST API.
5. Throwaway → hostas på vm106 enligt skills (publik auto-lane sibbamala.com/affar).

**Mall:** ERPNext (Frappe) domänmodell — kanonisk open-source-full-ERP med exakt dessa
moduler (Order, Invoice, Payment, Customer, Supplier, Item, Purchase, Delivery/tracking).

**Scope-guard:** demo-affärssystem. "Betalning" = registrering av mottagna betalningar
(simulerad), INGEN riktig betalningsgateway / inga riktiga pengar. Kunddata = demo/fiktiv.
Hålls inom throwaway/lokal ram tills det ev. publiceras — då via extern-exponeringsgatens
publik auto-lane.

**Användartyper (komplett system):**
- Admin (användare, roller, system)
- Försäljning/order (skapa/bearbeta ordrar, tracking)
- Ekonomi/fakturering (fakturor, betalningar)
- Inköp (suppliers, purchase orders)
- Kundvy (spåra sin order via tracking-id)

**Status:** Fas 1 pågår (plan → arkitektur → DA-granskning). Repot svarkor-ai/Affar är
tomt — bygger från noll.

## Fas 2b + tracking-write klar (2026-08-26)
C1-config hard-fail, customers-modul, React/Vite-frontend, hosting.yaml (8110), tracking write-side C21. 248 pytest grona (audit-verifierat 2026-09-23), E2E verifierat live. Nasta: publicering vm106 (fas 2c) kraver GitHub-remote + reconciler-lane.

## Security + logic audit PASS (2026-09-23, MC 1325)
Delegerad audit (2 subagenter) av master 709b319+cbd5a25: 0xP0/P1/P2. P3: publika demo-lösenord (intentionellt PoC), CORS default '*' (env-fix), saknad duplikat-invoice_no-test, LEDGER test-räknare stale (rättad här). 1323.1 startup-migration landad i master (cbd5a25) — mirror 7cdbf5b bar redan fixen. Evidens: /srv/workspace/affar-audit-20260923/.

## Full-function QA + F1/F6-fixar (2026-09-24, MC 1349/1350/1351)
QA (UI + API E2E, 39 steg): PASS med findings. F3-F5 kontraktsdrift landade 2026-09-23
(6c3e14d + 3fed96f, 251 pytest). F1: betalning mot redan betald faktura → 409 (ägarens
beslut 2026-09-24, alternativ A); 1175.3 refund-flöde omskrivet till cancel-först
(56b48c0). F6: Payments Datum-kolumnen läser paid_at (9de1c3e, dist byggd om). 252
pytest gröna på merged master (orchestrator-verifierat). F2 klassad designval: PO
re-receive är idempotent 200 (guard i purchase.py:138, ingen dubbel stock-in) — lämnas.
Kvar: vm106-spegeln synkar fortfarande inte (live visar index-DnFNfO3g.js) — reconciler
på vm106 behöver kick (ingen SSH-åtkomst från vm105). Evidens: /srv/workspace/affar-audit-20260923/.
