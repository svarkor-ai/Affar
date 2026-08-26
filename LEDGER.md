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
