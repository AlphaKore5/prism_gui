# WhatsApp platform — full build spec

**Target: everything AiSensy sells, and nothing dropped.** Researched 20-Sep-2026
from aisensy.com (pricing, features, 98-item tutorial index, template / chatbot /
agent libraries, API reference, partner and enterprise pages) and Meta's own
developer docs. Every item below has a build approach; none is deferred for being
"not needed". Ordering is by dependency only (§7).

Companion: `docs/WHATSAPP_B0_CHECKLIST.md` (the Meta gate). This file is the
engineering half.

---

## 1. Ground truth

### 1.1 What exists today

| Layer | State |
|---|---|
| Prism GUI `addons/whatsapp/` | Rail panel → `WhatsAppWorkbench` with Inbox · Contacts · Broadcasts · Settings; all data via `license_client.py`; demo-data mode. `cloud_api.py` + `webhook.py` kept as the direct-Meta path. |
| Licence server (`prism-license-server`, FastAPI + Postgres, Render/Railway) | `/v1/whatsapp/*` proxy: seat + licence + `marketing` feature check, then reads Supabase with its own `service_role`, sends via n8n webhooks. Holds no Meta credentials. |
| Supabase | `contacts(tags[], opt_out)`, `conversations`, `messages`, `segments(filter jsonb)`, `campaigns`, `leads`, `tasks`, `users`, `activity_log`. |
| n8n (`SALESCRMMM`, 176 nodes) | Meta webhook receiver, Gemini lead-qualification + conversation agents, drip sequences, CRM command console, reply webhook. Sends with the n8n WhatsApp node. |
| Meta | Business portfolio AlphaKore, test WABA + real number `+91 97260 63133` (status *Pending*), Business Verification *Pending submission* (waiting on partnership PAN). |

### 1.2 Meta platform facts that shape the build (verified 20-Sep-2026)

- **BSUID / usernames.** Webhooks carry `contacts[].user_id` and `messages[].from_user_id` (BSUID, format `IN.<up to 128 alnum>`) since Mar/Apr 2026. From June 2026 users can adopt usernames; then `wa_id` / `from` (the phone number) is **omitted** unless the business messaged/received from that number in the last 30 days or the user is in the contact book. Sending to a BSUID uses `recipient` instead of `to` (API support from July 2026). One-tap / zero-tap / copy-code auth templates still need a phone number. Error `131062` = BSUID not supported for this message. `parent_user_id` exists for multi-portfolio managed businesses.
- **Pricing from 1-Oct-2026.** Service (free-form, in-window) messages become billable after the first **1,000 per business number per month**; utility templates inside the 24 h window stop being free; the 72 h CTWA free-entry window stays. Per-message billing since 1-Jul-2025. India rate card reported by third parties: marketing ₹0.8631, utility/auth ₹0.1150, +18 % GST — **confirm against Meta's CSV** before shipping the cost engine. Billing detail arrives in the status webhook `pricing{billable,pricing_model,category,type}`; analytics via `pricing_analytics`.
- **Messaging limits** are per **business portfolio**, shared by all numbers: 250 → 2,000 → 10,000 → 100,000 → unlimited unique users / 24 h. To reach 2,000: verify the business, or send 2,000 delivered template messages to unique numbers in 30 days at high quality. Upgrades evaluated every ~6 h once ≥50 % of the limit was used in 7 days. Current tier readable via `whatsapp_business_manager_messaging_limit` (`TIER_250` …).
- **Throughput:** 80 msg/s per number by default (inbound + outbound), auto-upgrade to 1,000 msg/s for numbers with unlimited tier. `130429` = throughput, `131056` = pair-rate (same recipient too fast).
- **Marketing Messages API** (`/marketing_messages`, same schema and billing): delivery optimisation for engaged audiences, TTL 12 h–30 d, GIF headers, benchmarks. Error `131063` ("marketing disabled on Cloud API") exists — see §9 whether it forces this path.
- **Templates:** create `POST /{waba}/message_templates`; name ≤512, lowercase alnum + `_`; statuses APPROVED/PENDING/REJECTED/PAUSED/DISABLED; 250 templates per unverified portfolio, 6,000 verified; ≤100 created per WABA per hour; errors `2388293` (variable/word ratio), `2388299` (variable at start/end), `132015` paused, `132016` disabled. Carousel 2–10 cards, media mandatory per card, all cards share button layout. LTO, coupon (copy-code), authentication (OTP one-tap/zero-tap/copy), flow, catalog, MPM buttons.
- **Interactive:** reply buttons ≤3 (title 20, id 256, body 1024, footer 60). List/CTA/product limits: take from Meta reference when building (§9).
- **WhatsApp Flows:** Flow JSON (10 MB cap; screens, `SingleColumnLayout`, components TextInput/Dropdown/DatePicker/CalendarPicker/RadioButtonsGroup/CheckboxGroup/OptIn/Image/PhotoPicker/DocumentPicker/EmbeddedLink/If/Switch/NavigationList/Form/Footer…; actions navigate/complete/data_exchange; routing model ≤10 branches). Endpoint: HTTPS, requests `{encrypted_flow_data, encrypted_aes_key, initial_vector}` — RSA-OAEP-SHA256 wrapped AES-128, AES-GCM body; response encrypted with **bit-flipped IV**; actions `ping`, `INIT`, `data_exchange`, `BACK`; HTTP **421** on decrypt failure; `X-Hub-Signature-256` on every call; one key pair per WABA for Solution/Tech providers. Error `132069` = flow messages throttled (10/hour when unhealthy).
- **Payments India:** gateways BillDesk, Razorpay, PayU, Zaakpay via a *payment configuration* (name ≤60) in Meta Business Suite. `interactive.type=order_details`, `action.name=review_and_pay`, `reference_id` ≤35, amounts `{value, offset:100}`, `total = subtotal + tax + shipping − discount`, UPI cap ₹5,00,000. Status webhooks `statuses[].type="payment"` (`captured`/`pending`). **Do not rely on webhooks alone** — `GET /{pnid}/payments/{config}/{reference_id}` reconciles; `POST /{pnid}/payments_refund`. `order_status` message states: pending, processing, partially_shipped, shipped, completed, canceled. Error `134011` = Payments ToS not accepted.
- **Tech Provider onboarding (Embedded Signup v4):** JS SDK → `{code, waba_id, phone_number_id}` → server exchanges code for a **customer-scoped business token** → register number → subscribe app to the WABA (optionally per-WABA `override_callback_uri`). Tech Providers use business tokens only and **do not share credit lines** — each customer adds their own payment method to their WABA, so Meta bills the customer directly. 10 new customers / rolling 7 days by default → 200 after Business Verification + App Review + Access Verification. Needs Advanced Access to `whatsapp_business_management` and `whatsapp_business_messaging`.
- **CTWA ads (Marketing API v25.0):** campaign `OUTCOME_ENGAGEMENT` → ad set `destination_type=WHATSAPP`, `optimization_goal=CONVERSATIONS`, `promoted_object{page_id, whatsapp_phone_number}` → creative with `page_welcome_message` (ice breakers) and `call_to_action WHATSAPP_MESSAGE` → ad → publish. Permissions `ads_management, pages_manage_ads, pages_read_engagement, pages_show_list`. Inbound referral carries `ctwa_clid`; conversions go back through Conversions API (`action_source: business_messaging`, `messaging_channel: whatsapp`).
- **Coexistence:** same number on the Business App and the API; ≤6 months 1:1 history sync at onboarding; groups stay app-only; broadcast lists become read-only.

### 1.3 Defects in today's stack — fixed first, they are foundations

1. **No webhook signature check.** The n8n Meta handler has no `X-Hub-Signature-256` verification; anyone who learns the URL can inject messages. Gateway verifies HMAC on the raw body.
2. **Identity = phone number.** `Get or Create Contact` keys on `wa_id`/`from`. With BSUIDs and usernames that breaks silently for users who adopt a username. Identity model becomes `(tenant, bsuid | phone)` with merge (§5).
3. **Cost blindness.** From 1-Oct the AI bot's own replies cost money past 1,000/number/month. Nothing tracks that today.
4. **Hot path in a canvas.** Ingest, send, retries and campaigns live in an n8n workflow that can't be unit-tested, replayed idempotently, or rate-limited per tenant. The API contract already exists (licence-server `/v1/whatsapp/*`), so the implementation can move behind it without touching the GUI (strangler).
5. **Failure-domain coupling.** The licence server's own README says its design assumes it can be down without stopping customers; an online-only CRM proxy inside it contradicts that. The WhatsApp hot path gets its own service; the licence server stays the auth authority.
6. **Secrets.** Service-role and Meta tokens were hardcoded in exports (fixed 15-Sep); per-tenant Meta tokens need envelope encryption, not env vars.
7. **Cross-tenant exposure in the Prism panel (found 20-Sep, in `Shakti_One_CRM`).** The panel reads `conversations`, `messages`, `contacts`, `segments`, `campaigns` through the licence server's service-role key with **no `tenant_id` filter**, and in the shared Supabase project `conversations`/`messages` have **no `tenant_id` column** (only `contacts`/`leads` gained one later — legacy rows may be NULL). The moment a second tenant's leads exist in those tables, any seat whose licence has `marketing` can read them. Close this in WS1 before any customer licence includes `marketing`; verify today with `select tenant_id, count(*) from contacts group by 1`.
   **Status 20-Sep: fixed in code, awaiting deploy.** `prism-wa/db/migrations/0001–0003` add and enforce `tenant_id` (plus RLS for a tenant-scoped role); the licence server now links each licence to one workspace (`licenses.whatsapp_tenant_id`), scopes every query to it, refuses unlinked licences, and takes a reply's recipient from the contact instead of the request. Also found and fixed on the way: `contacts.phone`/`email` were *globally* unique (two tenants could not hold the same number), and a reply could be aimed at any phone number by any seat.
8. **Broadcast contract mismatch.** The licence server posts `{campaign_id, template_name, language, recipients[]}` to `N8N_BROADCAST_WEBHOOK_URL`. The only broadcast workflow found (`Broadcast Send (Shakti)`, `/broadcast-send`) expects `{tenant, dry_run, broadcast_id, segment, template, vars, user_token|confirm, …}`, resolves the tenant from a **hard-coded slug (`shakti`)** and reads Shakti's `members`. Prism → Broadcasts cannot drive it as it stands.
9. **Two data models in one Supabase project.** Orena sales CRM (`contacts, leads, conversations, messages, tasks`) and the Shakti/tenant model (`members, wa_messages, broadcasts, broadcast_recipients, kb_chunks, kb_gaps, app_admins`). WS1 unifies them under one tenant-scoped model.
10. **Secret hygiene.** Per-tenant Meta tokens are plaintext columns in `tenants` (`wa_token`, `fb_page_token`, `wa_api_key`); one string is reused as both the Meta webhook verify token and the broadcast-send `confirm` bypass; several live secrets (a Moodle token, that shared string, a super-admin passphrase) are written in plaintext in the `Shakti_One_CRM` docs and exports. Rotate them; envelope-encrypt tokens (WS17).

### 1.4 Prior art — what you already built in `Shakti_One_CRM` (Orena / Shakti)

A production multi-tenant WhatsApp platform already exists (n8n + Supabase + EspoCRM + Gemini, Hostinger VPS behind Traefik). The spec builds **on** it rather than replacing it; the table says what is reused where.

| Already built | Where it lives | How this spec uses it |
|---|---|---|
| **Tenant spine**: `tenants` row per client with `wa_phone_number_id`, `wa_waba_id`, token, `fb_page_id`, `ig_user_id`, `espo_team_id`, `branding`, `bot_config`; inbound routed by `wa_phone_number_id` | `sql/shakti_multitenant_spine.sql`, onboarding spec docx | WS1/WS0 tenant model as-is; add `wabas`/`phone_numbers` tables and encrypt tokens |
| **RBAC**: owner / manager / accounts / front-desk via `app_admins`, RLS helpers `is_tenant_staff`, `tenant_role`, enforced in UI **and** DB | `sql/admin_erp_backend.sql` | WS10/WS15 roles; add agent role + number masking |
| **Admin console** (single-file, anon key + RLS; dashboard, inbox, members, payments, bookings, check-in, campaigns, staff, settings, reports; 3-pane inbox with tabs, search, unread, channel badges, resolved tags) | `admin-panel/index.html` (5.9k lines) | WS16 design reference for Inbox / Broadcasts / Team; also a ready web companion route for the mobile/PWA item |
| **Broadcast composer**: 5 steps (name → audience → template → schedule/test → review), opted-in gating, `{{n}} → member field | custom text`, live phone-bubble preview, test send, **dry-run by default**, role-gated, ~33 msg/s throttle, history, `broadcast_recipients` ledger with `unique(broadcast_id, member_id)`, status-webhook design, scheduler cron every 5 min | `docs/Broadcast_System_Design.md`, `broadcast_wf_vps.json`, `broadcast_scheduler_wf.json`, `sql/broadcast_backend.sql` | WS7 **is** this design: port the UX and ledger, replace the in-execution loop with the outbox queue, make it tenant-generic |
| **RAG knowledge base**: `kb_chunks` (pgvector 768-d, HNSW cosine, tenant-scoped `match_kb` RPC) + **learning loop** (`kb_gaps`, `log_gap`, staff teach → `/kb-teach` embeds as `learned`) | `sql/rag_kb.sql`, `sql/kb_learning.sql` | WS9 adopts both schemas unchanged; adds crawl/file ingestion and the "top unanswered → add to KB" UI |
| **Bot memory** (`wa_messages`, last ~8 turns per number, member-linked) | `sql/wa_memory.sql` | folded into the unified `messages` table (WS1) |
| **Aria lead agent + scoring** (P1/P2/P3 rubric, structured output), **follow-up sequencer** (D1/3/7/14, IST hours Mon–Sat 10–19), **daily digest**, **team command console** (REPLY / ASSIGN / STAGE / NOTE / LIST / REPORT / APPROVE / REJECT / STOP / RESUME / UPDATE / HELP with role matrix) | `SALESCRMMM`, `Orena_WhatsApp_Bot_Documentation.html` | WS8/WS9/WS14: keep as flow templates + automations; IST business-hours becomes a flow/business-hours setting; commands become a "team member" trigger lane |
| **Three-lane router** (interactive reply → structured flow · team member → command console · free text → AI fallback), `bot_sessions` navigation state, per-client config-driven menus (hybrid sales bot), payments/Calendly/courses/attendance plan | `WhatsApp_Automation_Engine_Plan.html`, `Hybrid_Sales_Bot_Spec.html` | WS8 engine is this router; `bot_sessions` ≡ `flow_runs`; WS12 follows the same Razorpay loop (link → webhook → confirm → reminder stop) |
| **Provisioning**: super-admin console `/orena-admin`, `/provision-client` workflow, 8-step onboarding, intake workbooks | onboarding spec docx, `docs/*Onboarding_Data_Requirements.xlsx` | WS0/WS15: becomes Embedded Signup + a tenant-setup wizard; the workbooks become the wizard's fields |
| **Infra**: Hostinger KVM VPS, n8n + Traefik + nginx containers (`/admin`, `/orena-admin`), Cloudflare tunnel, workflow backup script (`_backups`, sanitised) | `deploy/admin/docker-compose.yml`, `docs/ORENA_SYSTEM_HANDOFF.md` | WS17: the new Hetzner box can reuse this Traefik/Docker layout; it need not be greenfield |
| **Other channels**: Messenger + Instagram DM (Page-linked), Gmail, Meta Lead Ads, EspoCRM 2-way sync | handoff doc §8 | keep `channel` on `conversations`; IG/Messenger become gateway adapters (WS2) with the 24 h/no-broadcast rules noted in the handoff |
| **n8n MCP** (`n8n-mcp` via npx) | `Shakti_One_CRM/.mcp.json` | project-scoped, so it was absent in the Prism session; enabling it here would replace the REST workaround |

**Lessons already in your handoff doc that this spec must honour:** send via HTTP Request + token rather than the n8n WhatsApp-node credential (it fails with "Error fetching options" — and the reply webhook added to `SALESCRMMM` uses that node, so test it before relying on it); n8n JSON bodies need `={{ ({ ...obj }) }}`; load history with `.all()` not `.first()`; the phone unique index can't back `on_conflict` (insert → continue-on-error → fetch); Gemma needs a `responseSchema` and agent typeVersion ≥ 3.1; FB/IG DMs use PSID/IGSID, a 24 h window, and cannot be broadcast. The 14-Aug stress test found the same webhook-collision class of bug (two nodes on `POST /whatsapp-crm`) that the gateway design removes by construction.

---

## 2. Target architecture

```
  Meta Cloud API ──webhooks──►  prism-wa GATEWAY  ──►  jobs (Postgres, SKIP LOCKED)
       ▲                        (verify HMAC, dedupe,        │
       │                         normalise, persist)         ▼
       │                                              WORKERS
       │                        ┌─────────────────────────────────────────────┐
       │◄──── send/outbox ──────│ send · campaign · flow engine · AI agent ·  │
       │      (rate-limited,    │ scheduler · retries · status · payments ·   │
       │       idempotent)      │ ads sync · webhooks-out · analytics rollups │
       │                        └─────────────────────────────────────────────┘
       │                                   │            ▲
       │                                   ▼            │
       │                        Postgres (tenant-scoped, RLS) + pgvector + object store
       │                                   ▲
   Prism GUI ──► licence server (auth: seat + licence lease) ──► prism-wa REST + realtime (SSE/WS)
   Public API keys ─────────────────────────────────────────────►┘
   n8n  ◄── outbound events / REST ──► integrations glue (Shopify, CRMs, Sheets, Zapier…)
```

- **`prism-wa`** = one FastAPI service (same stack the team already runs), separate deploy from the licence server, on Hetzner. Two processes from one codebase: `api+gateway` and `worker`.
- **Auth:** Prism GUI keeps calling the licence server contract; the licence server mints a short-lived scoped lease that `prism-wa` verifies (Ed25519, same signer the client already trusts). Public API uses hashed, scoped API keys.
- **Queue:** Postgres `jobs` with `FOR UPDATE SKIP LOCKED` — no Redis until measured need. Every job idempotent by key.
- **Realtime:** SSE endpoint per seat (conversation events, assignments, handoffs, campaign progress); Prism side is a `_Worker` reading the stream.
- **n8n stays** as the integration hub and for tenant-specific automations; it stops being the hot path. Migration is endpoint by endpoint: `/reply`, `/broadcast` first.
- **Multi-tenant from day one:** `tenant_id` on every row, Postgres RLS, tokens per WABA envelope-encrypted, webhook routed by `phone_number_id → waba → tenant`.

---

## 3. Feature inventory → where it is built

| AiSensy capability (source) | WS | Meta mechanism | Gate |
|---|---|---|---|
| Free WhatsApp Business API provisioning, Embedded Signup | WS0, WS15 | Embedded Signup v4, business token | Tech Provider + App Review |
| Blue tick application (needs registered entity, ≥5 organic press links, tier ≥2, 2FA, approved display name) | WS0, WS16 | OBA request in Business Manager | Registered entity |
| Business profile editing | WS16 | `/{pnid}/whatsapp_business_profile` | — |
| Contacts: unlimited, tags (10/100/250/500), attributes (5/20/50/100), CSV import ≤200k, add single, export, delete, sources, first-message tag, global attributes | WS5 | — | — |
| Opt-in / opt-out keyword automation (≤5 keywords each), confirmation message, consent ledger | WS5 | honour `131050` | — |
| Audience segmentation (name, mobile, tags, source, first-message tag, intervened/requested/closed, campaigns, last seen, created, attributes; AND/OR) and saved segments (2/10/50) | WS6 | — | — |
| Broadcast & campaign manager, personalisation, template-message API, unlimited audience | WS7, WS3 | template send, tier-aware | Template approval, tier |
| Scheduler (≤2 months, time zones, edit/cancel), recurring, CSV scheduler, duplicate numbers in CSV | WS7 | — | — |
| Retargeting (delivered/read/replied/clicked/failed), click tracking, carousel per-card tracking | WS7 | status webhooks, button payloads, own redirector | — |
| Failed-message retry ≤3, delay ≤24 h | WS7, WS3 | error taxonomy | — |
| Campaign analytics + budget, downloadable reports (Campaign/User/Overview/Opt-in-out), template TTL | WS7, WS15 | `pricing` in statuses, TTL | — |
| Template creation, approvals tracking, guidelines checker, media / carousel / LTO / coupon / authentication templates, library 100+ across 8 industries, AI template generator | WS4 | Templates API + Resumable Upload | Meta review |
| Live chat shared inbox, Active/Requesting/Intervened/Closed, intervene/resolve, agent transfer, manager monitoring, auto-resolve 24 h, chat profile, history | WS10 | — | — |
| Agent rules / smart routing / user access control / number masking / agents+managers | WS10, WS15 | — | — |
| Canned messages, welcome & off-hours auto-replies | WS10 | — | — |
| Chatbot flow builder (keyword/regex/template/ad triggers; buttons, lists, product cards, API request, delay, timeout), 5→N bots, multi-ad triggers, template library 30+, AI flow generator, Dialogflow connect | WS8 | interactive messages, referral | — |
| AI agents: KB (site crawl, PDF/DOCX), memory, tools/skills, REST APIs, handoff + SLA, guardrails, usage metering, 3 test numbers, agent library | WS9 | — | LLM cost |
| WhatsApp Forms (native forms, appointment booking, CRM sync) | WS11 | WhatsApp Flows + endpoint | Flows key upload |
| WhatsApp Payments (UPI/cards/netbanking; Razorpay/PayU), payments dashboard, failed-payment retargeting | WS12 | Payments API India | Gateway + Meta approval |
| Catalogues, cart, single/multi-product, catalog message, profile display | WS12 | Commerce Manager + catalog messages | Catalog |
| Click-to-WhatsApp ads, lead-form ads, website-traffic ads, status ads, AI ad creatives, AI ads manager, conversions feedback | WS13 | Marketing API + CAPI | Ads permissions review |
| WhatsApp Webviews | WS13 | see §9 — mechanism to confirm | — |
| Acquisition tools: WhatsApp link, button, QR, website widget | WS14 | `wa.me` + prefilled text | — |
| APIs, webhooks (1/3), Zapier/Pabbly/Integrately, Shopify, WooCommerce, Razorpay, CRMs, abandoned cart, order updates, birthday/anniversary, drip | WS14 | — | — |
| Coexistence, migration from other BSP / Cloud API, KYC broadcast-limit uplift | WS0, WS15 | Coexistence onboarding, number migration | Meta |
| Mobile app (Android/iOS), notifications | WS10, WS16 | — | — |
| Billing: plans, add-ons (AI, flows, seats), wallet, GST, dunning; partner (affiliate/prime/white-label/API/integration) and enterprise (SSO, audit, SLA) | WS15 | — | — |

---

## 4. Workstreams

Each is independently buildable behind the contract shown. "Done" = the check that closes it.

### WS0 — Meta & compliance foundation (calendar-bound, start today)
Clocks and owners in §8. Build items: `prism-wa` config for app id/secret, Embedded Signup v4 hosted page (JS SDK) that returns `code/waba_id/phone_number_id`; token-exchange + register-number + subscribe-app job; per-WABA `override_callback_uri`; coexistence and migration onboarding paths; display-name status tracking; phone-number quality + tier readers.
**Done:** a fresh WABA onboards end-to-end on the test app and its webhooks land in the gateway attributed to the right tenant.

### WS1 — Data model & multi-tenancy (§5)
Migrations (alembic, same as licence server), RLS policies, seed data, backfill from today's Supabase tables (contacts.phone → identities).
**Done:** two tenants cannot read each other's rows under a non-owner DB role (test); backfill is idempotent.
**Slice 1 built 20-Sep (in `prism-wa/`, 54 tests on a real Postgres 17; not yet run against Supabase):** plain idempotent SQL rather than alembic, because the live schema is hand-run SQL and the files must paste into the Supabase editor — tenancy (0001), identity resolver + merge + audit (0002), `wa_app` role + RLS (0003), preflight, tested rollback. Remaining in WS1: `wabas`/`phone_numbers`, consent ledger, attributes, `tenant_id` on the legacy sales-pipeline tables, envelope-encrypted tokens.

### WS2 — Gateway
- `GET /webhook/wa` verify challenge; `POST /webhook/wa` returns 200 fast, after: HMAC-SHA256 of the raw body against app secret (constant-time), event-id dedupe (`wamid`+`status`+`timestamp`), raw event persisted, job enqueued. Never process inline.
- Normaliser → canonical `Event`: phone and/or BSUID (+`parent_user_id`, `username`), message type, text, media ids, interactive reply ids, `nfm_reply` (flow response), `order`, reactions, referral / `ctwa_clid`, statuses with `errors[]` and `pricing`, template status / quality / category updates, phone quality, account updates, coexistence echoes/history.
- Replay tool (`replay --since`) and a payload fixture library from Meta's samples (tests never hit the network).
**Done:** forged signature → 401 and no row; duplicate delivery → one message; fixtures for every type parse.

### WS3 — Send engine (outbox)
- `enqueue(tenant, to={phone|bsuid}, payload, kind, idem_key, campaign_id?)` is the only way anything sends (bot, agent reply, campaign, API, payments).
- Window logic: last inbound < 24 h → free-form allowed, else template required; automatic downgrade to template picker error in UI.
- Token bucket per number (default 80/s, configurable; 1,000/s once Meta upgrades), pair limiter (per recipient), portfolio tier counter (unique users/24 h) with **preflight refusal** rather than mid-campaign failure.
- Error taxonomy from Meta's table → `retry | backoff | fatal | fix-setup | user-optout`: retry `1,2,4,80007,130429,131000,131016,131049(24h+),131056,131057,133004,2494100`; never `131047 (→template), 131050 (→opt-out), 131026, 132000-132016, 130403, 190, 368`. Token errors (`190`) page the tenant admin.
- Media: upload API + id cache; template header handles via Resumable Upload.
- BSUID: use `recipient` when phone unknown; surface `131062` cleanly.
- Marketing path: route through `/marketing_messages` when the account requires/benefits (§9).
- Typing indicator + mark-as-read for bot UX.
**Done:** 10k-message soak at the configured rate with injected 130429/131056/131049 completes with correct terminal states and no duplicates on worker kill -9.

### WS4 — Templates
- Sync: list on connect, then webhooks `message_template_status_update`, `template_category_update`, `message_template_quality_update`; store status/reason/quality/category and reject reasons.
- Builder (Prism UI): header (text/image/video/document/location), body variables (named or positional, sample values), footer, buttons (quick reply ≤3? verify, URL static/dynamic, phone, copy-code, OTP, flow, catalog/MPM/SPM), carousel (2–10 cards), LTO (expiry), coupon, authentication (one-tap/zero-tap/copy-code + supported apps + code expiry), TTL. Live WhatsApp-style preview. Client-side lint mirroring Meta's rules (name pattern, 2388293, 2388299, char limits, category fit, 250/6,000 and 100/hr caps) — the "compliance check" AiSensy shows.
- AI generator: intent + tone (normal/festive/formal/friendly/urgent) + goal (click/read/reply/convert) + category (auto) → 3 variants, each linted; rejected templates get an LLM-assisted rewrite suggestion.
- Library: our own 100+ templates across the same 8 industries **plus construction** (quotation sent, follow-up, site-visit confirm, milestone payment reminder, RA bill, dispatch/delivery, BOQ ready) — authored fresh, not copied.
**Done:** create → submit → status arrives by webhook → visible in UI; lint rejects every documented failure case before submission.

### WS5 — Contacts / CRM
- Import: CSV ≤200k, only Name + Mobile required; phone normalisation with the India-default rule (bare 10-digit → +91), `+` E.164 otherwise; attribute and tag columns (`|`-separated) auto-create or map; upsert without deleting history; source `IMPORT/ORGANIC/API/custom`; consent attestation checkbox recorded in the ledger; row-level error report.
- Attributes: typed (string/number/date/bool/enum), global attributes, built-ins `$Name $FirstName $LastName $MobileNumber`, plan-limit enforcement, set from flows/API/forms/CSV/manual.
- Tags, first-message tag (auto from first inbound text/ad), source, custom events timeline, profile panel (status, last active, template vs session counts, unresolved queries, campaigns, payments, journey).
- Identity merge phone ↔ BSUID (§5), contact-book awareness, blocked users.
- Consent ledger: every opt-in/out with source, timestamp, text evidence; opt-out keywords (≤5) and opt-in keywords (≤5) auto-handled with optional confirmation; opted-out never receive business-initiated messages; `131050` also flips the flag.
- Export CSV, bulk delete, DPDP-style erasure.
**Done:** 200k-row import < 2 min; re-import is idempotent; erasure removes PII everywhere (test).

### WS6 — Segments & audience engine
Filter DSL (JSON): groups with AND/OR; fields = name, mobile, tags (has/has-any/has-none), source, first-message tag, attributes (typed operators), status flags (intervened/requested/closed), last seen, created, and **campaign interaction** (`campaign X: delivered|read|replied|clicked|failed`, optionally "not"). Compiled to parameterised SQL; live count preview; static vs dynamic segments; exclusion lists; plan caps 2/10/50. Retargeting = "new campaign from this campaign's clicked/read/replied set".
**Done:** DSL round-trips; property tests compare compiler output to a Python reference filter on random data.

### WS7 — Campaign engine
- Create: template + variable mapping (attribute / static / per-recipient CSV column) + media + audience (segment / CSV / API list) + schedule (now / ≤2 months with time zone / recurring / per-recipient local time) + retry policy (≤3 retries, delays ≤24 h, retryable codes only) + TTL.
- Preflight (blocking with reasons): template approved, params count match, media reachable, quality not red, portfolio tier headroom (unique users), opted-out removed, frequency cap, cost estimate (rate card × recipients by category, GST).
- Run: snapshot `campaign_recipients`, dispatch through WS3 with per-campaign rate; pause / resume / cancel / reschedule; auto-pause on quality drop or tier exhaustion; resume tomorrow automatically if over tier.
- Tracking: per-recipient timeline from status webhooks; reply attribution (first inbound within N h); **click tracking**: URL buttons rewritten through our redirector (`/r/{token}` → 302, logs contact + card + UTM); quick-reply payload ids carry `campaign:recipient:button`; carousel per-card ids.
- API-triggered campaigns: `POST /api/v2/campaign` (apiKey, campaignName, destination, userName, templateParams[], media, tags, attributes) compatible in spirit with what customers already integrate.
- Reports: Overview, Campaign, User, Opt-in/out CSV/XLSX; charts; cost from `pricing`.
**Done:** 5k-recipient campaign with injected failures finishes with retries honoured, counts reconcile to Meta status events, cancel mid-run stops within one batch.

### WS8 — Chatbot / flow engine + visual builder
- **Schema v1 (JSON):** `nodes[]`, `edges[]`, `entry`, per-node `settings`. Node types: `send_text`, `send_media`, `buttons` (≤3), `list`, `cta_url`, `location_request`, `address`, `product`, `product_list`, `catalog`, `carousel`, `flow` (WhatsApp Form), `payment`, `template`, `ask` (question + validator: text/number/email/phone/date/regex/options → save to attribute), `condition/switch` (attributes, tags, message, time, business hours), `set_attribute/tag/opt`, `delay`, `wait_reply_timeout` (fallback branch), `api_request` (method, URL, headers, params, raw JSON with `$attr` interpolation, **Test** button, response → attributes, status-code fallbacks), `agent` (hand to AI agent), `handoff` (Requesting state + notify), `jump_flow`, `webhook_out`, `dialogflow`, `end`.
- **Triggers:** keyword (exact/contains/starts), regex, template quick-reply payload, ad referral (`ad_id` / `ctwa_clid`, multiple ads → one flow), prefilled-text link/QR, first message, default fallback, schedule/API event.
- **Engine:** state per conversation (`flow_run{node, vars, waiting_for, deadline}`), step advance is idempotent by inbound event id, timers via jobs, a human `Intervened` state suspends the bot, business-hours aware, per-bot enable, versioned (draft/published/rollback), N bots per tenant (limit is a plan setting).
- **Builder (Prism):** node-graph editor in a `QWebEngineView` (the app already ships a web runtime for Studio) with React Flow or Drawflow; JSON in/out over a small bridge; validation before publish; side test console bound to a test number; import/export JSON.
- **AI flow generator:** prompt → schema-constrained LLM output → validate → auto-repair loop → open in builder.
- **Library:** own 30+ flow templates by use-case (order tracking, FAQ, appointment, lead qualification, site visit, quotation request, payment reminder, feedback…).
**Done:** a 12-node flow runs against the Meta test number end-to-end; kill worker mid-flow → resumes without double-sending; every node type has a contract test against a recorded payload.

### WS9 — AI agents
- **KB:** sources = website crawl (sitemap + robots aware, depth/limit, re-crawl schedule), PDF/DOCX/PPTX/TXT/CSV, pasted FAQ, catalogue export; chunk (semantic, ~500 tokens, overlap), embed → `pgvector`; per-agent namespaces; source citations kept.
- **Runtime:** function-calling loop (Gemini default, Groq/OpenAI fallback via one adapter), retrieval → answer with grounding rule ("say you don't know rather than guess"), persona/tone/guardrails/escalation rules from one config, reply in the customer's language (AiSensy is English-only here), max-turn and cost caps.
- **Tools/skills:** built-ins (capture lead field, qualification gate, book appointment via calendar, order/quotation status lookup, send payment request, send catalogue, tag/attribute set, escalate) + custom REST tools with dynamic variables and a secrets vault; tool outputs treated as untrusted text (prompt-injection defence).
- **Memory:** last-N messages + rolling contact summary + extracted facts (attributes).
- **Handoff:** conditions (explicit ask, low confidence, sentiment, N failed turns, keywords, sensitive topics) → `Requesting` state with an LLM summary card for the agent; SLA timer + notify.
- **Ops:** test console (Meta test numbers; free 500-message-style sandbox as a plan setting), usage ledger per "AI message" (every agent reply = 1), live dashboard (volume, resolution rate, handoff rate, top unanswered questions → "add to KB" one click), kill switch per tenant.
- **Library:** own agents — sales, lead qualification, appointment booking, support, event registration, admissions, bulk order, vehicle, **construction: site-visit + quotation enquiry**.
**Done:** eval harness (golden Q&A set per agent, graded automatically) passes ≥ target; injection test suite (malicious KB/tool text) never changes tool calls.

### WS10 — Live chat / multi-agent inbox
- States: **Active** (bot), **Requesting** (needs human), **Intervened** (agent owns), **Closed** (resolved → bot resumes). Auto-resolve after 24 h idle (setting). Only the intervening agent sees an intervened chat unless manager.
- Assignment: attribute/tag rules ("agent sees only chats with tag X / industry Y" as AiSensy), plus round-robin, least-busy, availability/working hours, skills; transfer between agents; manager monitor (all chats, response-time, first-response, unassigned, SLA breach).
- Roles: owner / manager / agent enforced in RLS and API, not just hidden in UI; **number masking** for agents (last 4 digits); access control matrix.
- Composer: 24 h window banner, template picker when closed, media, canned messages (`/shortcuts`, variables), internal notes, reactions, reply-to, typing + read receipts, emoji, message search, unread + presence.
- Auto-replies: welcome (in hours) and off-hours with time zone schedule, text/image/file/template, once per contact per N hours.
- Notifications: in-app realtime (SSE), desktop toast + sound in Prism, email/WhatsApp alert to managers on handoff; **mobile companion** (PWA on the same API first; native later) with push.
- History page (last 24 h boundary), profile panel embedded.
**Done:** two agents on one number never reply to the same customer (concurrency test); RLS test proves agent A cannot read agent B's intervened chat.

### WS11 — Forms (WhatsApp Flows)
- Builder in Prism: screens/components form editor that emits Flow JSON (current version), validator, preview; publish via Graph (`POST /{waba}/flows`, upload asset, publish); versions.
- Endpoint: per-WABA RSA key pair (generated server-side, private key never leaves KMS/envelope store), public-key upload, `ping/INIT/data_exchange/BACK`, AES-GCM with flipped IV, 421 on decrypt failure, `X-Hub-Signature-256` check, health-check validator, error-notification handler, p95 latency budget (Flows time out fast).
- Capture: `nfm_reply` → attributes/CRM/activity, flow token ↔ conversation mapping, dynamic screens (appointment slots from calendar, product pick from catalogue).
- Templates: lead capture, appointment booking, feedback/NPS, site-visit request, quotation request, KYC-lite.
- Sending: interactive `flow` message or template FLOW button from flows/campaigns/agent.
**Done:** a booking form round-trips with live slot availability on the test number; decrypt-failure path returns 421 (test with corrupted payload).

### WS12 — Commerce & payments
- Catalogue: store Commerce Manager `catalog_id`, product sync (read), send single/multi-product/catalog messages, cart (`order` inbound) → order record → payment request.
- Payments: per-WABA `payment_configuration` name, gateway credentials stay at the gateway; order builder (items, tax, shipping, discount, expiry) enforcing the total invariant and `offset:100`; `reference_id` generator (≤35, safe chars); send `order_details/review_and_pay`; `order_status` updates as fulfilment progresses; webhook `type:payment` handler **plus** a reconciliation job that polls the lookup API for every non-terminal payment; refunds (`instant|normal`); payments dashboard; failed/abandoned retargeting segment; ToS `134011` surfaced as a setup task.
- Interim/fallback: Razorpay payment links via CTA-URL message for tenants whose Meta payments approval hasn't landed — same order model, different transport.
**Done:** sandbox order paid via UPI on the gateway's test mode flips to `captured` via webhook **and** via reconciliation when the webhook is dropped (test).

### WS13 — Ads
- Connect: Facebook Login for Business → ad account + page + WhatsApp number linking; permissions listed in §1.2 (Advanced Access review needed).
- Create: CTWA (campaign → ad set → creative w/ `page_welcome_message` ice breakers → ad → publish), lead-form ads, website-traffic ads, WhatsApp-status placements; targeting (geo, age, gender, interests, behaviours, lookalike, **custom audience from a Prism segment** via hashed phone upload), budget/duration, creative upload (1080×1080) + **AI creative generator** (prompt + brand assets → image via a generation API, brand-safety lint).
- Attribution: capture `ctwa_clid`/`ad_id` from the referral into the contact; route by ad → flow/agent (multi-ad → one flow); send Conversions API events (lead, qualified, purchase) with `action_source=business_messaging`.
- Reporting: impressions, reach, clicks, CTR, CPC, spend, conversations started, cost per conversation; **AI optimiser** = rule loop (pause low-CTR creative, shift budget to best CPA, generate new variants) with human approval mode.
- Webviews: see §9.
**Done:** a PAUSED CTWA ad is created end-to-end on a test ad account; a click-through on the test ad shows `ctwa_clid` on the contact and routes to the configured flow.

### WS14 — Integrations, API, webhooks, acquisition
- Public REST API (versioned `/api/v2`): contacts, tags, attributes, opt-in/out, templates (list/send), messages, campaigns (create/send/status), flows trigger, conversations, segments. Scoped hashed API keys, rotation, per-key rate limits, idempotency keys, OpenAPI published.
- Outbound webhooks (per tenant, up to plan limit): events `message.received`, `message.status`, `conversation.handoff`, `campaign.completed`, `payment.updated`, `contact.opted_out`, `flow.response`; HMAC-signed, exponential retry, dead-letter + replay UI.
- Connectors: Shopify (OAuth or custom-app token; webhooks orders/create, orders/fulfilled, checkouts/create → abandoned-cart timers with configurable delay; template variable mapping from order fields incl. order id, tracking, amount), WooCommerce, Razorpay (payment events), Google Sheets, Zapier/Pabbly/Integrately (REST+webhooks), CRMs (EspoCRM already; LeadSquared, HubSpot, Zoho, Kylas), Dialogflow (CX/ES detect-intent node). **n8n** remains the escape hatch for the long tail.
- Automations: abandoned cart, order confirmation/shipping/delivery, appointment reminders, payment reminders, birthday/anniversary (attribute date match), drip sequences (existing `tasks` model generalised), LTO and authentication-code automation.
- Acquisition: `wa.me` link generator with prefilled text, QR (png/svg), website floating-button widget (JS snippet, UTM + source tag), "click to chat" attribution to source tag.
**Done:** OpenAPI contract tests; signed-webhook receiver sample verifies; Shopify test store abandoned-cart → template arrives after the configured delay.

### WS15 — Billing, limits, tenancy, admin
- **Model:** as a Tech Provider, customers pay Meta directly (payment method on their WABA) — Prism bills subscription + AI-message packs + seat add-ons only. A wallet/credit line exists only if Prism becomes a Solution Partner; keep the ledger abstraction so it can be added.
- Usage ledger from status `pricing` (billable, category), rate-card table (versioned; INR + GST), free-service-message counter per number (1,000/month from 1-Oct), per-campaign and per-agent cost views, budget alerts.
- Plan limits as data (tags, attributes, segments, agents, bots, AI messages, webhooks, schedule availability, throughput cap, storage) enforced server-side; the licence-server catalogue gets the new feature keys via the frozen-key rule (§ CLAUDE.md #6: `marketing` stays; new keys are additive).
- Storage quota (media), retention, GST invoices (Razorpay Phase 2 already planned in the licence server), dunning.
- Admin: extend the licence-server operator console with a tenant view (WABAs, numbers, tier, quality, usage, errors, webhook health).
- Partner / white-label (custom domain, branding, reseller sub-tenants, commission ledger), enterprise (SSO SAML/OIDC, audit log UI + export, SLA reporting, data residency).
**Done:** limit checks unit-tested at boundary values; ledger reconciles to Meta invoice for a test WABA.

### WS16 — Prism GUI
Information architecture (all under the existing `whatsapp` rail add-on, one folder, per `CONTRIBUTING.md`):
`Inbox · Contacts · Segments · Broadcasts · Templates · Flows · AI Agents · Forms · Commerce · Ads · Analytics · Team · Acquire · Settings` (numbers/profile/blue-tick/opt-in/auto-replies/API/webhooks/billing). Sub-navigation instead of 14 rail rows; each page lazy-built like today's workbench.
- Realtime worker (SSE) → signals; unread badges; notifications; offline banner; demo mode retained.
- Every network call in a `_Worker` subclass; only `core_bridge` imports the engine; no cross-add-on imports; `panel.py`/`workbench.py` shape retained; update `GOLDEN_*` lists in the same commit; `devtools/extract_strings.py` after copy; i18n (English, Hindi, Gujarati first).
- Verify against the real stylesheet at 1920 and 1366 (standing rule).
**Done:** each page has a headless construction test (no `processEvents`), a golden-list update, and a screenshot check through the real `MainWindow`.

### WS17 — Infra, security, operations
- Hetzner (or the existing Hostinger VPS layout — §1.4): Caddy or Traefik (TLS) → `prism-wa` api/gateway + worker(s) + n8n; Postgres (managed Supabase initially, self-host later) with pgvector; object storage (Hetzner Storage Box / S3-compatible) for media; staging stack wired to Meta test numbers; prod separate.
- Secrets: never in repo/exports; per-tenant Meta tokens envelope-encrypted (KMS-style key, rotate); n8n gets env-var references only.
- Observability: structured logs with `fbtrace_id`, metrics (queue depth, send rate, error-code histogram, webhook lag), alerts (token errors, tier exhaustion, quality drop, queue stall), uptime checks, Sentry.
- Backups: daily logical + WAL, off-box copy, **restore drill before launch** (the licence-server README's own rule).
- Security: HMAC on all webhooks in/out, rate limits, WAF, least-privilege DB roles, audit log on every admin action, dependency scanning; privacy: DPDP consent + erasure, retention windows, Meta messaging-policy opt-in evidence retained.
**Done:** restore drill passes; chaos test (kill worker/db failover) leaves no duplicate sends.

---

## 5. Data model (sketch — real DDL goes in alembic)

```
tenants(id, name, plan_id, status)                          wabas(id, tenant_id, waba_id, token_enc, key_ver, webhook_override, quality, tier)
phone_numbers(id, waba_id, phone_number_id, display, status, quality, mps_limit)
contacts(id, tenant_id, name, email, source, first_msg_tag, opted_in, opted_out, blocked, created_at, last_seen)
contact_identities(id, tenant_id, contact_id, kind ENUM(phone,bsuid,parent_bsuid), value, first_seen, last_seen, UNIQUE(tenant_id, kind, value))   -- username is a display attribute on contacts, NOT a key: it can be changed or released and re-taken by someone else
consent_ledger(id, contact_id, action ENUM(opt_in,opt_out), source, evidence, at)
attribute_defs(id, tenant_id, key, type, global, options) ; contact_attributes(contact_id, key, value jsonb)
tags(id, tenant_id, name) ; contact_tags(contact_id, tag_id)
segments(id, tenant_id, name, filter jsonb, dynamic bool)
conversations(id, tenant_id, contact_id, number_id, state ENUM(active,requesting,intervened,closed), assignee_id, last_inbound_at, last_active_at)
messages(id, tenant_id, conversation_id, direction, wamid, type, body jsonb, status, error jsonb, pricing jsonb, client_ref UNIQUE, created_at)
message_status_events(message_id, status, at, raw jsonb)
templates(id, waba_id, name, language, category, status, quality, components jsonb, reject_reason, meta_id)
campaigns(id, tenant_id, template_id, segment_id, schedule jsonb, retry jsonb, ttl, status, counts jsonb)
campaign_recipients(id, campaign_id, contact_id, params jsonb, status, attempts, next_attempt_at, wamid, error)
click_events(id, campaign_id, recipient_id, card, url, at) ; short_links(token, target, meta jsonb)
outbox(id, tenant_id, number_id, to jsonb, payload jsonb, kind, idem_key UNIQUE, state, attempts, run_at, error_class)
jobs(id, kind, payload jsonb, run_at, attempts, locked_by, state)      -- SKIP LOCKED
flows(id, tenant_id, name, published_version) ; flow_versions(id, flow_id, graph jsonb, state) ; flow_runs(id, conversation_id, flow_version_id, node, vars jsonb, waiting jsonb, deadline)
agents(id, tenant_id, config jsonb) ; kb_sources(id, agent_id, kind, uri, status) ; kb_chunks(id, source_id, text, embedding vector, meta jsonb) ; agent_runs(id, conversation_id, tokens, cost, tools jsonb, outcome)
forms(id, tenant_id, flow_json, meta_flow_id, status) ; form_responses(id, form_id, contact_id, payload jsonb)
orders(id, tenant_id, contact_id, reference_id, amount jsonb, items jsonb, status, gateway, config_name) ; payments(id, order_id, status, txn jsonb, refunds jsonb, last_checked)
ad_accounts(id, tenant_id, ...) ; ads(id, tenant_id, meta_ids jsonb, spec jsonb, status) ; ad_insights(ad_id, day, metrics jsonb)
users(id, tenant_id, role, agent_rules jsonb, working_hours, masked) ; canned_messages ; auto_reply_configs ; notes(conversation_id, user_id, text)
api_keys(id, tenant_id, hash, scopes, last_used) ; webhook_endpoints(id, tenant_id, url, events, secret) ; webhook_deliveries(...)
usage_ledger(id, tenant_id, number_id, kind, category, billable, qty, cost_paise, at, ref)   ; rate_cards(version, country, category, price)
audit_log(id, tenant_id, actor, action, detail jsonb, at)
```
Migration of today's tables: `contacts.phone → contact_identities(kind=phone)`; `messages`, `conversations`, `campaigns`, `segments` map 1:1 plus `tenant_id` backfill to the single current tenant.

---

## 6. Cross-cutting

- **BSUID readiness:** identity resolver used by gateway, send engine, campaigns, flows, API; UI shows username/masked phone when phone unknown; CSV import stores phones as identities so a later BSUID attaches to the same contact when the same user messages in; contact-book toggle documented in Settings.
- **Cost engine:** one function `estimate(category, country, n)` + one ledger writer fed by statuses; free-service counter per number; budget alerts; AI-bot replies counted as service messages.
- **Test strategy:** recorded Meta payload fixtures for every webhook type; fake Graph server for send tests (returns each error code); property tests for the segment compiler; contract tests for every flow node; eval harness for agents; load test at the configured mps; no test touches the real Meta network or a real `~/.prism` (existing conftest rules).
- **Libraries (content):** templates, flow templates and agents are written fresh per use-case and industry, including construction; AiSensy's library text is not copied.
- **Language:** English + Hindi + Gujarati first for UI and template/library content.

---

## 7. Build order and parallelisation

Dependency graph (arrow = needs):

```
WS1 ◄── WS2, WS3, WS5 ◄── WS6 ◄── WS7
WS2 + WS3 ◄── WS8, WS9, WS10, WS11, WS12, WS14
WS4 ◄── WS7 (templates) ; WS3 ◄── WS4 (media handles)
WS10 ◄── WS8/WS9 (handoff states) ; WS13 ◄── WS8 (ad→flow) ; WS15 ◄── all (limits, ledger)
WS16 tracks every WS (UI slice ships with its backend slice) ; WS17 runs alongside from day 0
```

**Waves (nothing dropped — this is only what can start when):**

| Wave | Streams (parallel) | Unblocks |
|---|---|---|
| 0 — day 0 | Meta clocks (§8) · infra skeleton on Hetzner · contracts (OpenAPI + event schemas + flow JSON schema) written first | everything |
| 1 — foundations | WS1 schema/RLS · WS2 gateway · WS3 send engine · WS5 contacts/identity · WS4 template sync | all feature streams |
| 2 — core product, all parallel | WS6+WS7 segments/campaigns · WS8 flow engine · WS9 AI runtime · WS10 live chat · WS4 builder + library · WS14 API/webhooks · WS16 UI slices | live pilot |
| 3 — externally gated, built in parallel, verified live as approvals land | WS11 forms · WS12 payments/commerce · WS13 ads · WS15 billing/limits/partner/enterprise · mobile companion | full parity |

**Two-day shape.** Contracts first (a few hours), then Waves 1+2 as ~8 parallel streams (agents and cofounders each take a WS against the written contract; the strangler design means the GUI keeps working the whole time because `/v1/whatsapp/*` doesn't change shape). Wave 3 streams are built in the same window but can only be *verified live* after Meta approves the relevant permission/config — that wait is calendar time, not build time, which is why §8 starts today.

Definition of done for the programme: every row of §3 has a passing automated check and, for Meta-gated rows, one recorded live run on a real approved asset.

### 7.1 Release milestones — by AiSensy plan (added 17-Oct-2026)

The buyers "want to use all features". AiSensy sells those features in tiers, so each tier is a shippable milestone on the **same build path** as §7 — M2 is M1 plus a layer, not a second build. Every plan number below is from AiSensy's pricing page **as pasted by the owner on 17-Oct-2026** (not re-fetched). Nothing in §3 is dropped: rows that are not on the pricing page sit in M6.

**Status at 17-Oct-2026, end of day:** the **backend** for M0, M1 and most of M2 is built in `prism-wa/` and tested against a real Postgres and a fake Graph API (see its README for the module-by-workstream table): gateway, queue and workers, ingest, send engine, encrypted tokens, Embedded Signup (server side), templates, contacts and consent, segments, campaigns, the team inbox with routing and database-enforced visibility, plans and their limits, the public API, Shopify/WooCommerce, and ads (paused-only). The licence server has the proxy routes (`/v1/whatsapp/p/*`) and the hand-off from n8n. **Not done:** every screen in the Prism desktop app for these features (the add-on still shows the old inbox, contacts and one-template broadcast), M3 (flows and AI), M4's outbound webhooks, report downloads and template TTL, M6, and any run against Meta live. Earlier that day (code read, app not run) the add-on had a partial inbox viewer, contacts with tags and an opt-out toggle, tag segments and a one-template broadcast over licence-server `/v1/whatsapp/*` → Supabase/n8n.

**Plan limits as data (WS15).** Blank = not stated on the page (the plan inherits the one to its left). Meta's per-message charges are the same on every plan; plans differ only in software.

| | Free | Basic | Pro | Premium | Unlimited |
|---|---|---|---|---|---|
| Price (₹/month) | 0 | 1,500 | 3,200 | 9,100 | 45,000 |
| Tags | 10 | 10 | 100 | 250 | 500 |
| Custom attributes | 5 | 5 | 20 | 50 | 100 |
| Saved segments | — | 2 | 10 | 50 | 50 |
| Agents included | — | 1 owner + 5 | | 1 owner + 9 | up to 200 |
| Broadcast speed (msg/s) | no broadcasting | 40 | | 250 | 1,000 |
| Outbound webhooks | — | — | — | 1 | 3 |
| Media storage | | 1 GB | | | |

Add-ons: Chatbot Flows ₹2,500/month (5 bots), AI Agent ₹1,350/month (1,000 AI messages; 500 free test messages), extra agent seat ₹750/month, Indian virtual number ₹2,000/year + GST. Meta charges, India from 1-Oct-2026: marketing ₹1.09, utility and authentication ₹0.145, service ₹0.145 after the first 1,000 free per number per month.

| Milestone | Parity target | What it adds (workstream) | Done when |
|---|---|---|---|
| **M0** Foundations | not plan-bound | Meta clocks (§8) · WS1 tenancy · WS2 gateway · WS3 send engine · WS17 skeleton | WS2 and WS3 "Done" checks pass; a test WABA onboards and its webhooks land under the right tenant |
| **M1** Basic | Free + Basic | Embedded Signup, blue-tick application, business-profile editing (WS0/16) · template create + approval tracking (WS4) · unlimited contacts, CSV import, 10 tags / 5 attributes (WS5) · 2 saved segments (WS6) · broadcast + retargeting + campaign manager, with delivered/read/replied tracking and template variables (WS7, no scheduler/click tracking/analytics yet) · template-message REST API (WS14) · multi-agent shared inbox, transfer, manager monitoring, 1 owner + 5 agents, seat billing (WS10/15) · Shopify + WooCommerce order, shipping and abandoned-cart messages, and an integrations page (WS14) · ads manager: click-to-WhatsApp, lead-form, website-traffic and sales ads (WS13) · limits as data: 40 msg/s, 1 GB, free-service counter (WS15) | every M1 row has a passing automated check; a PAUSED click-to-WhatsApp ad is created end to end on a test ad account |
| **M2** Pro | + Pro | 100 tags / 20 attributes / 10 segments · campaign scheduler and CSV scheduler · click tracking incl. per-card carousel · campaign budget and analytics (spend, delivery, reads, ROI — needs the cost engine, §6) · automatic failed-message retry (≤3, delay ≤24 h) · smart agent routing, custom agent rules, role-based access (RLS) · project REST APIs (WS7/10/14) | a 5k-recipient scheduled campaign finishes with retries and click counts reconciling to Meta status events; agent A cannot read agent B's intervened chat |
| **M3** Add-ons | Chatbot Flows + AI Agent | Flow engine and builder with keyword / template / QR / ad triggers, **delay and timeout nodes** (AiSensy lists these under Pro, but they live inside flows), cart and catalogue sharing (WS8 + the catalogue part of WS12), Shopify chatbot, AI flow generator · AI agent: knowledge-base Q&A, long-term memory, tools/skills/API calls, no-code builder, per-message metering (WS9) · extra-seat billing | WS8 and WS9 "Done" checks |
| **M4** Premium | + Premium | number masking · downloadable reports (Campaign, User, Overview, Opt-in/out) · template TTL · 250 msg/s · 1 owner + 9 agents · 250 tags / 50 attributes / 50 segments · 1 outbound webhook · duplicate numbers in a CSV broadcast · several ads → one flow trigger · priority support and turbo onboarding (people, not code) | report CSVs reconcile to the usage ledger |
| **M5** Unlimited / Enterprise | + Unlimited, Enterprise | up to 200 agents · 1,000 msg/s · 500 tags / 100 attributes · 3 webhooks · dedicated account manager (a person) · Enterprise: SSO, audit logs, custom throughput, custom integrations, SLA support, custom contracts and invoicing (WS15) | enterprise checks in WS15 |
| **M6** In our spec, not on the pricing page | beyond published plans | Forms / WhatsApp Flows (WS11) · payments (WS12) · coexistence and number migration · AI ad-creative generator and optimiser (WS13) · mobile companion · public acquisition tools beyond the basics | WS11, WS12, WS13 "Done" checks (all Meta-gated) |

**Decisions and checks before M1 ships**

1. **Wallet vs Meta billing.** AiSensy bills prepaid INR credits and invoices once. This spec assumes a Tech Provider: each customer adds a payment method on their own WABA and Meta bills them (§1.2, WS15). Decide before WS15 billing whether to stay that way or pursue a Solution Partner credit line (§9 item 8) — buyers used to one rupee invoice may find Meta billing a step backwards.
2. **Indian virtual numbers** (AiSensy: ₹2,000/year + GST, GST/MSME KYC) need a telephony vendor, not code. Not scheduled.
3. **People-delivered items** — priority support, turbo onboarding, dedicated account manager, solution architect, SLA — need staff and sit in M4/M5.
4. **Price check.** AiSensy charges ₹1.09 marketing and ₹0.145 other; §1.2's third-party figures (₹0.8631 / ₹0.1150) plus 18 % GST come to about ₹1.02 and ₹0.136, so AiSensy is roughly 7 % higher — margin or a newer Meta rate. Settle it from Meta's rate-card CSV (§9 item 2) before the cost engine is written.
5. **Cutover is per number** (unverified: a number lives with one provider at a time; see the migration row in §3), so a customer moves each number as the milestone it needs lands.
6. **Marketing API review** (WS13) and **blue-tick eligibility** are the long Meta clocks inside M1 — start them in M0.

---

## 8. Calendar-bound clocks — start today, they run while we build

| Clock | Needs | Typical wait | Unblocks |
|---|---|---|---|
| Partnership registration → firm PAN | in progress (≈ next week) | days | Business Verification |
| Business Verification (Security Centre → Continue; use UDYAM / firm PAN docs; **don't submit under a personal PAN**) | firm PAN/registration docs, address match | days–weeks | 2,000 tier, App Review, Access Verification, blue tick |
| Meta app: privacy-policy URL, icon, category | us | hours | App Review |
| App Review + Advanced Access `whatsapp_business_management` / `_messaging` | screen recordings (send + create template) | days | onboarding > 10 customers/wk, real customers' WABAs |
| Number `+91 97260 63133` out of *Pending* (verification + display-name review) | in-flight | hours–days | real-number pilot |
| Payment method on the WABA | us | minutes | any billable send |
| Templates submitted early (utility + marketing sets) | us | minutes–24 h each | broadcasts on day 1 |
| Payments: gateway account (Razorpay/PayU) + payment configuration + Payments ToS | gateway KYC | days–weeks | WS12 live |
| Catalogue in Commerce Manager | us | hours | WS12 catalogue |
| Marketing API: `ads_management`, `pages_manage_ads`, `pages_read_engagement`, `pages_show_list` review | screencast | days–weeks | WS13 live |
| Flows: public-key upload + Flow publish review | WS11 endpoint ready | hours–days | WS11 live |
| Blue tick | registered entity, ≥5 organic press links, tier ≥2, 2FA, approved display name | 7–10 business days after applying | badge |
| Second Business admin | a cofounder's email (not the same account) | minutes | lockout safety |

---

## 9. Verify-first (could not confirm from sources fetched; check before building the part)

1. **Marketing on Cloud API vs `/marketing_messages`** — what error `131063` triggers on and whether marketing templates must move to the MM API for this WABA/country.
2. **India rate card after 1-Oct-2026** — only third-party figures found (₹0.8631 / ₹0.1150); pull Meta's CSV.
3. **Interactive limits** — list messages (sections/rows/lengths), CTA URL, product/multi-product, carousel message JSON — the Meta pages rendered empty to my fetch; take exact limits from the reference at build time.
4. **Status-webhook exact shape** for `pricing`/`conversation` under the 2026 model, and `smb_message_echoes`/history events for coexistence.
5. **WhatsApp Webviews** — AiSensy markets it; mechanism (CTA URL opening an in-app browser vs a Meta feature) not confirmed.
6. **WhatsApp status ads** placement API support.
7. **Template button counts and template-in-carousel button rules** in the current API version (AiSensy's page says ≤2 buttons in carousel; Meta reference to confirm).
8. **Solution Partner path** (credit line, lower friction for wallets) — eligibility and timeline vs staying a Tech Provider.

---

## 10. Sources

AiSensy: pricing, features (broadcasting, chatbot, AI agents, forms, scheduler, retargeting, payments, support, automation, template/flow/ads generators, Meta Ads Manager), Blue Tick, Partner, Enterprise, Real Estate, Lead Generation pages; tutorials index (98) and tutorials for API reference, agent rules, live chat + chatbot, live-chat settings, auto-replies, chat profile, contacts import, attributes, filters, opt-in/out, carousel, retries, quality rating, coexistence, billing cycle, catalogue, CTWA, payments connection, Shopify; template message library; AI agent library; chatbot template pages.
Meta: business-scoped user IDs, messaging limits, pricing, error codes, templates overview, reply-button messages, Flow JSON, Flows endpoint, payments (India, payment gateways), Embedded Signup for Tech Providers, Click-to-WhatsApp (Marketing API), Marketing Messages API overview, WhatsApp changelog.
Third-party (cross-check only): YCloud and MyOperator Oct-2026 pricing summaries; Chatwoot, Typebot, Dify, WAHA, Twilio, Razorpay docs for reference designs.
