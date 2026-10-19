# WhatsApp tabs — what AiSensy has, what we have, what is missing

18-Oct-2026. Goal: every tab as capable as the AiSensy section it replaces. Nothing is dropped
or judged "not needed" (standing rule since 20-Sep); waves in §10 only order
the work by dependency.

**How this was made.** The platform spec (`docs/WHATSAPP_PLATFORM_SPEC.md`, §3 and WS4–WS16)
for the target; AiSensy's own help centre, tutorials, feature pages and the 2026 AI Agents 2.0
release notes (links in §12) for what each section really does; our code for what exists today —
the screen (`addons/whatsapp/`), the backend (`prism-wa/prism_wa/`), the route table (`ops.py`).
Nothing here was seen inside a logged-in AiSensy dashboard (see §11).

**Gap type.** `UI` = backend already exists, only the screen is missing (cheapest).
`BE+UI` = both are missing. `Meta` = built in parallel but verified only when Meta approves.
`People` = needs staff or a vendor, not code.

---

## 0. Build status (19-Oct-2026)

Every gap in §2–§9 that code can close has been built, on the backend (prism-wa), the licence server's allow-list and the desktop screens, each with tests
(real Postgres, a fake Meta, a fake Razorpay, a fake OpenID Connect provider that really signs tokens). **None of it has been run against Meta, Razorpay or a real
identity provider live** — what is unproven is listed in prism-wa's `DEPLOY.md` ("Done in code, not yet proven live").

| Slice | What is now there |
|---|---|
| 1 Contacts | filter builder, columns, bulk bar, add / delete, tags and attributes managers, segments, import mapping and history, opt-in/out keywords, blocked |
| 2 Inbox | state filters and counts, History, template send into a closed window, chat profile (attributes, counts, journey), agent-rules editor, notification preferences |
| 3 Campaigns | retry toggle, audience builder, per-recipient table and export, retargeting by reply, attribute fallback, AiSensy-shaped API-campaign endpoint, auto-pause on category change; Broadcasts folded in |
| 4 Media | send / receive / store, library and quota, composer attach, media canned messages, welcome media, flow image step, template and campaign headers |
| 5 Templates | Authentication, limited-time-offer, carousel, media header, TTL, AI writer, a library of 100+ by industry |
| 6 Usage and reports | usage ledger, dashboard, plan and usage, reports and CSVs, messaging limits, business profile, outbound webhooks, links and QR, live inbox |
| 7 Automations | 23 flow steps (media, pin, calendar conditions, webhook, Conversions API, sell…), canvas editor, results, AI flow writer, 38-flow library, holidays; AI agents with draft / published copies, profile, skills, actions, knowledge (site crawl, embeddings), test numbers, hand-off webhook, gaps and analytics; automatic birthday / reminder / drip messages |
| 8 Ads | click-to-WhatsApp, website and lead-form ads (always made paused), targeting with search and reach estimate, picture upload, AI copy, people lists and look-alikes, review state, results over time, suggestions applied only on approval, Facebook sign-in |
| 9 Commerce and enterprise | **Shop** tab: catalogue (CSV import, pull / push with Meta, product / list / catalogue messages), carts become orders, payments by Razorpay links or Meta's order_details, dropped-webhook reconciliation, expiry, refunds, dashboard, failed-payment reminders, chatbot steps that show products and ask for payment · **Forms** tab: six starting points, editor, Flow JSON, publish, live booking forms with the encrypted endpoint, answers onto the contact, CSV · audit log · single sign-on (OIDC) with enforcement · branding, resellers and commission · coexistence with the WhatsApp Business app |

**Not built, because code cannot build it** (the standing rule: report, never call "not needed")

* Virtual numbers (bought from a carrier), a dedicated account manager, priority support and turbo onboarding — people and vendors.
* Single sign-on through **SAML** (needs an XML-signature library and an agreement with each provider); OpenID Connect is built.
* Pointing a reseller's **own domain** at Prism (the address is stored; DNS and certificates are arranged by hand).
* **WhatsApp Status ads** and **Webviews** — AiSensy markets them but no mechanism is documented (§9, §11); verify first.
* **AI image generation for ad pictures** — ads take a picture from the Media Library and AI writes the words; generating the picture needs an image model account.
* Meta's approvals: Payments (India), Marketing API advanced access, Embedded Signup, catalogue and Flows endpoint review; every Meta-gated item is built and waits on them.

---

## 1. Where each AiSensy section lands in our tabs

| AiSensy | Our tab | Note |
|---|---|---|
| Live Chat + History | **Inbox** | History has no home yet |
| Contacts (CRM) + Manage → Tags, Attributes | **Contacts** | tags/attributes managers have no home |
| Manage → Template Message (+ Library, AI generator) | **Templates** | |
| Campaigns (+ Launch → Broadcast / API campaign, analytics, retargeting) | **Campaigns** | |
| Flow Builder + AI Agents | **Automations** | |
| Ads Manager | **Ads** | |
| *(no equivalent — a broadcast is Contacts → select → Broadcast, or Campaigns → Launch)* | **Broadcasts** | older quick-send; superseded by Campaigns |
| Manage + Profile (agents, canned messages, live-chat settings, notifications, API key, webhooks, integrations, media library, billing) | **Settings** | |
| Dashboard / reports, Catalogue, Payments, Forms, WhatsApp link/QR/button | *no tab* | §9 |

---

## 2. Inbox  (AiSensy: Live Chat + History)

| Capability | AiSensy | Ours today | Gap |
|---|---|---|---|
| Chat states | Active (bot) · Requesting (needs a person, pinned to a top bar) · Intervened (agent owns, bot off) · Closed. Intervene / Resolve; resolving hands the chat back to the bot | Take over · Resolve · Hand back · "Not taken / With X". Filters are only **All / Unread / Opted out** | `UI` state filters with counts (Requesting, Mine, Unassigned, With bot, Resolved); requesting chats pinned and alerting |
| Who sees a chat | Only the agent who intervened (managers see all); **Agent rules** = an agent sees only chats whose attribute/tag matches | Database enforces visibility; agent rules exist in the backend (`inbox.py`, segment-filter rules) | `UI` rules editor per agent |
| Transfer, auto-resolve | Transfer between agents; auto-resolve after 24 h | Transfer… ✅; "Close quiet chats after" ✅ | — |
| **History page** | Chats idle 24 h+; read-only for agents; filter by name, mobile, tags, source, first-message tag, intervened / requested / closed, campaigns, last seen, created, any attribute; edit tags and attributes; **start a conversation by sending a template** | None. Idle chats stay in the one list | `UI` History view + template picker (template send exists) |
| Reopening a closed window | Template picker | Amber banner "Template only", no picker | `UI` |
| Chat profile | Status, last active, **template-message count, session-message count, unresolved queries**, source, first-message tag, campaigns received, **attributes (view/edit)**, tags (automated: first-message / API / broadcast; manual), **payments history**, **Customer Journey** timeline (which agent intervened, tags added, campaigns sent, with times) | Tags, email, company, opt-in/out, reply window, copy number | `UI` attributes view/edit (backend has them); `BE+UI` counts and journey (needs an events timeline table); payments waits on WS12 |
| **Media in chat** | Send and receive image, file, audio, video, location; Media Library (1 / 5 / 10 GB by plan); media by link for template approval | Text only. `send.py` has **no media kinds**; inbound media ids are parsed (`events.py`) but never downloaded, stored or shown | `BE+UI` send media, fetch + store inbound, thumbnail / player, media library, storage quota. **Largest single gap in the module** |
| Canned messages | `/` to open; text ≤ 4096 with `$FirstName`, `$Name`, custom attributes, `{{1}}`; **media canned messages**; personal favourites pinned on top; ≤ 200 per project | Quick replies with `/`, `{first_name}` `{name}`, text only, no favourites, no cap | `UI` favourites; `BE+UI` media quick replies |
| Welcome / off-hours | Separate welcome (inside hours) and off-hours messages; text, image, file or **template**; time zone and weekly hours | Welcome + closed message, hours, time zone, "at most once every N h" — text only | `BE+UI` image / file / template variants |
| Notifications | Sound on/off; push on up to 5 devices (Windows, Android) | Unread count on the tab | `UI` desktop toast + sound + per-user preference + Requesting alert |
| Filters / search | Smart chat filtering by tag, campaign, attribute | Text search by name / number | `UI` filter bar over the segment engine (exists) |
| Composer | Emoji, attachments, canned messages | Plain text, ticks, retry on failure | `UI/BE` emoji, reply-to, reactions, typing and read receipts (WS10) |
| Live updates | Browser app, live | Refresh on a timer ("Updated 8:44 PM") | `BE+UI` realtime (SSE, spec §2) |
| Mobile | Browser app on phone and PC; push | None | `BE+UI` PWA companion (spec: later) |

---

## 3. Contacts  (AiSensy: Contacts CRM + Manage → Tags, Attributes)

| Capability | AiSensy | Ours today | Gap |
|---|---|---|---|
| Table | Name, Mobile, **Tags, Source, Status (active / inactive 24 h), State (intervened / requesting / closed / handled by assistant), Last Active, Created At, First-Message Tag**, every attribute | Name, number, company/email search; chips All / Opted in / Opted out; count | `UI` columns, sort, column chooser (data exists) |
| **Filter** | Last seen, created, opted in, incoming blocked, tags, source, campaigns, attributes; multi-level AND; a dot shows a filter is on | None | `UI` filter builder over the segment DSL (`segments.py`: tags, name, email, first-message tag, flags, created, last seen, typed attributes, campaign interaction, AND/OR) |
| Bulk actions | Select (all matching) → **Broadcast**, **Manage Tags** (add/remove on the whole selection), Export, Delete | Single contact only | `UI` selection + bulk bar; a bulk-tag route is probably needed (`BE`, small) |
| Add one contact | Form, no CSV | Only via import | `UI` (upsert exists) |
| Delete / erase | Delete contacts | `contacts/erase` route exists | `UI` |
| Import | CSV ≤ 200k; map any column to any attribute; ≤ 100 tags per contact, comma-separated; custom source; re-import **updates**, chats kept; **Import History** with added / updated / failed counts and a downloadable failure report | Preview table, tags, consent attestation, sample file, row errors, update-in-place ✅ | `UI` column → attribute mapping; `BE+UI` import-history table and failure-report download |
| Export | All or the filtered set | Export ✅ | `UI` export-selection |
| Tags manager | Create / rename / delete tags; plan caps 10 / 100 / 250 / 500 | Add a tag inline | `UI` manager page + cap display |
| Attributes manager | User attributes (typed) and **global attributes**; caps 5 / 20 / 50 / 100; built-ins `$Name $FirstName $LastName $MobileNumber` | Backend `attribute_defs` + `contact_attributes` exist; no screen | `UI` |
| Saved segments | 2 / 10 / 50 by plan | "Saved group" inside Campaigns, tags only | `UI` Segments page |
| Opt-in / opt-out | Keyword automation (≤ 5 each) with confirmation message; opted-out flag; **blocked users** ("incoming blocked") | Consent ledger and opt flags exist; opted-out shown | `UI` keyword settings; blocked-users filter |
| Sync | Google Sheets sync (no CSV), CRMs | None | `BE+UI` (WS14) |

---

## 4. Templates  (AiSensy: Manage → Template Message)

| Capability | AiSensy | Ours today | Gap |
|---|---|---|---|
| Category | Utility · Authentication · Marketing | Marketing, Utility | `UI` add Authentication |
| Type | Text, Image, Video, File, Location, **Carousel**, **Limited-Time Offer** | Text header only. The backend lint already understands carousel, LTO, authentication and image / video / document / location headers | `UI` builders for each; `BE+UI` header-media sample upload (Resumable Upload) |
| Body / footer / variables | ≤ 1024, `{{1}}…`, sample values, bold / italic / strike / mono | ✅ plus live phone preview and "as you type" Meta-rule check | — |
| Buttons | CTA URL (static or dynamic `{{n}}`) + phone; quick replies (≤ 3; LTO up to 10) | Quick reply, Visit website (dynamic), Call phone ✅ | `UI` LTO coupon + expiry, copy-code, OTP |
| Carousel | 2–10 cards, per-card body, media attached at send time, 1–2 buttons | — | `UI` card editor; per-card click tracking exists in backend |
| Library | 100+ ready templates, 8 industries; pick → submit | **14** entries | content: author 100+ (spec WS4 adds construction) |
| **AI generator** | Describe it → category (auto) → tone → goal (clicks / reads / replies / conversions) → templates with a live compliance check | — (`llm.py` exists to reuse) | `BE+UI` generator; rewrite suggestion for rejected templates |
| Status | Pending / Approved / Rejected + reason; Sync Status | List, filters, quality, update from Meta, reasons ✅ | — |
| Template TTL | Message validity (Premium) | — | `BE+UI` |
| Category re-classification | Meta flips Utility → Marketing: AiSensy **auto-pauses** running campaigns and cancels scheduled ones (setting: Campaign Settings → Auto-pause on category change) | `template_category_update` event is parsed, nothing acts on it | `BE+UI` (also in §5) |
| Per-template stats | — (campaign level) | — | optional: sends / reads / clicks per template |

---

## 5. Campaigns  (AiSensy: Campaigns + Broadcast composer + API campaigns)

| Capability | AiSensy | Ours today | Gap |
|---|---|---|---|
| Composer | Name (unique) → approved template → parameters (attributes, **with fallback value if the attribute is empty**) → media file → Send now / Schedule | Template, sending number, variable mapping (same text / their name / a saved detail / per-person), media **URL**, test send, check-then-send ✅ | `BE+UI` attribute fallback; `BE+UI` pick media from disk / library (we take a URL) |
| Audience | From Contacts: any filter, selection, imported list | Everyone opted in, or by tags, or a saved tag group | `UI` the full filter builder (§3) + a CSV audience + exclusions |
| Preflight | — (basic) | Reach count, cost estimate, blocking reasons ✅ | `BE` tier headroom needs a messaging-limit reader (none today) |
| Schedule | ≤ 2 months, time zones, edit / cancel; CSV scheduler | Send later, repeat (daily / weekly / monthly), per-person local time, reschedule, cancel ✅ | — |
| **Retry failed** | Toggle → ≤ 3 retries, each delayed up to 24 h; "Scheduled Retries" tracker; advised against Meta's frequency cap | Backend retry (≤ 3, `delay_minutes`) built; **no toggle on screen** | `UI` |
| Analytics | Status (Sent / Live / Stopped / Paused), type, audience, sent, delivered, read, replied, clicked, failed (**on WhatsApp / not on WhatsApp**); per-section **name lists**; spend (Pro) | Funnel counts, failed count, "{r} meant, {s} sent" | `UI` per-recipient table with status and reason, filter and export; `BE+UI` plain-language failure reasons (incl. "Spam rate limit hit" = Meta frequency cap) |
| Retargeting | From any section: read / delivered-not-read / replied / clicked / by quick-reply payload | Clicked, didn't read, replied, read ✅ | `UI` "by which reply" |
| Click tracking | URL buttons, per-card (Pro) | Own redirector + counts ✅ | — |
| **API campaigns** | "+Launch → API campaign": a named, live-toggled campaign; `POST …/campaign/t1/api/v2` with `apiKey, campaignName, destination, userName, source, media, templateParams, tags, attributes, location` — what Zapier / Pabbly / CRMs already call | `/api/v1/campaigns` exists, different shape; no "API campaign" object or screen | `BE+UI` an AiSensy-compatible endpoint so a customer's existing integration only changes the URL; screen to create / toggle / copy the JSON |
| Reports | Downloadable Campaign, User, Overview, Opt-in/out (Premium) | None | `BE+UI` needs a usage ledger (none) |
| QR-code campaign | Yes | None | `UI` (§9 Acquire) |
| Quality / limits | Quality-rating article, broadcast-limit guide | Quality shown on the number | `BE+UI` messaging-limit tier + headroom |
| Speed | 40 / 250 / 1,000 msg/s by plan | Plan limits in data ✅ | — |

**Broadcasts tab (§1).** AiSensy has no separate Broadcasts page. Ours is the older quick-send
(type a template name, pick tags, past broadcasts). Fold it in: a **Broadcast** button on a Contacts
selection opens the Campaigns composer pre-filled; "Past broadcasts" merges into the Campaigns list;
then the tab goes. *Owner's call.*

---

## 6. Automations  (AiSensy: Flow Builder add-on + AI Agents)

### Flows

| Capability | AiSensy | Ours today | Gap |
|---|---|---|---|
| Builder | Drag-and-drop canvas, threads between blocks, save / enable toggle, test | A list of steps with "then" pickers (not a canvas); draft / publish / versions / rollback; Try-it console; problem list ✅ | `UI` canvas (spec WS8: node-graph in `QWebEngineView`) |
| Triggers | Keywords (hi, hello…), **regex**, template quick-reply, QR / link, click-to-WhatsApp ad (several ads → one flow) | Keyword, regex, first message, default, ad ids, template button ✅ | `UI` link / QR trigger |
| Message blocks | Text, quick replies (3), **image + button**, list, **section list**, **single product**, **multi-product**, template, request intervention | Text, buttons, list, template, hand-over ✅ | `BE+UI` image / media block, section list, product blocks (need catalogue, WS12), location / address request, carousel |
| Logic | Ask a question (+ save to attribute, **validation**), set attribute, tag, **time-based and date-based conditions** (business hours, holidays), fallback intent (text / image / video) | Ask (+ validation, tries), condition, set attribute, tags, delay, wait-for-reply timeout, fallback ✅ | `BE+UI` time / date condition and business-hours node |
| API request | GET / POST / PUT / PATCH / DELETE, params, headers, raw JSON with `$attr`, **Test**, capture response → attributes, status-code branches | ✅ incl. works / fails branches, SSRF-guarded | `UI` response → attributes mapping and a Test button on the step |
| Integrations in a flow | **Conversions API** event (lead / purchase) → Meta; Dialogflow connect | — | `BE+UI` CAPI node (Meta-gated); webhook-out node |
| WhatsApp Form / Payment blocks | Native forms, UPI payment | — | WS11 / WS12 `Meta` |
| Library | 30+ flows | **6** | content |
| **AI flow generator** | Prompt → flow | — | `BE+UI` (schema-constrained output, auto-repair) |
| Flow analytics | — (basic) | "{n} customers in it now" | `UI` runs, completion, drop-off per step, hand-overs |
| Limits | 5 bots on the add-on | Plan limit in data ✅ | — |

### AI agents  (AiSensy "AI Agents 2.0", July 2026 — six sections)

| AiSensy section | What it holds | Ours today | Gap |
|---|---|---|---|
| Business Profile | Business name, website, description, **greeting**, **ground rules**; **AI drafts it from your website URL** | One "Instructions" box | `UI` structured profile; `BE+UI` draft-from-URL |
| Voice | Tone and answer length | — | `UI` presets |
| Skills | Tasks: FAQ / support, **human handoff** (when to, when not to), lead qualification, appointment booking, bulk enquiry, feedback, **collect these variables and save them** | Hand-over words, reply cap | `BE+UI` skills with variables → attributes |
| Knowledge | Crawl a page, upload **PDF / DOC / DOCX / TXT / CSV** (≤ 50 MB, PDF ≤ 30 pages), paste text; each source shows a status (Ready); delete a stale source | Text, Q&A, one web page, PDF / DOCX, forget ✅ | `BE+UI` multi-page site crawl, TXT / CSV, status badges, re-crawl; **retrieval** — ours is Postgres full-text (keywords). A customer who writes "Can I send the product back?" will miss a source titled "return policy"; the spec's pgvector embeddings are needed, and for Hindi / Hinglish |
| Actions | System: `update_contact`, `search_knowledge`, `escalate_to_human`; **Custom API actions** (order status, slots, booking, refund); **business actions** from connected apps (Razorpay, Shopify) | — | `BE+UI` (spec WS9 tools, secrets vault) |
| Settings | **Fallback message**; which numbers it runs on; handoff on/off, trigger phrases, message, **handoff webhook (URL, auth, headers)**; up to 3 **test numbers** (500 free test messages) | Fallback is "hand to the team"; allowance meter ✅ | `UI` fallback text; `BE+UI` handoff webhook; per-number scoping |
| Train / Live | Train mode (unpublished draft) vs Live mode (published), New Chat, **Publish** (Paused / Published) | One "Try it" box on the saved agent | `BE+UI` draft vs published |
| Metering | 1 reply = 1 AI message; packs | ✅ | — |
| Memory | AiSensy: **none across sessions** (documented) | Last turns only | optional edge: rolling summary (spec WS9) |
| Analytics | — | Usage only | `BE+UI` resolution rate, hand-off rate, **top unanswered → add to knowledge** (your own `kb_gaps` design, spec §1.4) |

### Automations with no home yet (AiSensy "Automation" plan rows)

Birthday / anniversary messages (attribute-date match) · drip sequences · appointment and payment
reminders · order and shipping updates (we have Shopify / WooCommerce under Settings → Stores) ·
authentication-code automation · abandoned-cart delay (✅ in Stores). `BE+UI`.

---

## 7. Ads  (AiSensy: Ads Manager)

| Capability | AiSensy | Ours today | Gap |
|---|---|---|---|
| Ad types | **Click-to-WhatsApp · Website (traffic, with a Meta Pixel) · Lead Form · WhatsApp Status** | Click-to-WhatsApp only | `BE+UI` the other three (`Meta`) |
| Connect | "Continue with Facebook" → business → page → ad account → OTP links the WhatsApp number | Paste ad-account id, page id and access token | `Meta` Facebook Login for Business + Advanced Access review |
| Money | **Ad credits** bought in-app (UPI / card / wallet); ₹1,000 free to new users | Customer's own Meta ad account bills them | design choice — say which |
| Creative | Name, caption, headline, **image 1080×1080 from media library / device / URL**, CTA, **AI creative generator**, "create the ad from a prompt" | Name, text, headline, **picture hash** (typed) | `UI` image picker + preview; `BE+UI` AI creatives (needs Media Library, §2) |
| Targeting | Saved audiences; country / city / region; gender; age; **interests, behaviours, demographics (keyword search)**; **lookalike**; **customer list upload**; website visitors; placements (Facebook / Instagram feed, stories, explore, reels, marketplace) | Countries, age range, "Show it in" | `BE+UI` the rest; **custom audience from a Prism segment** (hashed phones, spec WS13) |
| Budget | Daily or **lifetime**; start / end / **custom schedule**; estimated total and reach | Daily budget | `UI` |
| Status | Pending Review → In Process → Active; rejection reason; Sync Status | Running / Paused / Archived | `UI` Pending-review and rejection-reason display |
| Analytics | Impressions, reach, clicks, **outbound clicks**, spend, CTR, CPC, cost per result, WhatsApp conversations, **performance over time**, date filter | Times shown, people, clicks, spend, chats started, cost per chat | `UI` CTR / CPC, chart over time, date range |
| Attribution | `ctwa_clid` → contact; ad → flow; **Conversions API** back to Meta | `ctwa_clid` capture + ad-trigger ✅ | `Meta` CAPI event node |
| Optimiser | — (spec adds an approval-mode loop) | — | `BE+UI` |

---

## 8. Settings  (AiSensy: Manage + profile)

| Capability | AiSensy | Ours today | Gap |
|---|---|---|---|
| Numbers | Connect (Embedded Signup), **quality rating**, **messaging limit tier**, display-name status, buy an Indian virtual number | Connect card, list, quality ✅ | `BE+UI` messaging-limit reader and display-name status; virtual number = `People` / vendor |
| **Business profile** | About, address, email, websites, photo, category | — | `BE+UI` (`/whatsapp_business_profile`) |
| Blue tick | Application help | — | `UI` checklist (Meta clock, WS0) |
| Agents | Owner adds agents / managers (username, display name, password); roles; **agent rules**; extra seats ₹750; transfer | Team list: role, available, hide numbers, hours ✅ | `UI` add / remove a teammate; rules editor; seat billing note |
| Live-chat settings | Auto-resolve; welcome and off-hours | ✅ (text only) | see §2 |
| Canned messages | ≤ 200, media, favourites | Quick replies ✅ text | see §2 |
| Notifications | Sound, push (5 devices) | — | `UI` |
| Campaign settings | Auto-pause on category change; retry defaults | — | `BE+UI` |
| Tags / Attributes | Managers | — | `UI` (§3) |
| **Webhooks (outbound)** | 1 (Premium) / 3 (Unlimited) by plan | None (`webhook_endpoints` table does not exist) | `BE+UI` (WS14): message received / status / hand-off / campaign done / payment / opt-out / flow response, signed, retried, delivery log + replay |
| **Integrations hub** | App Store: Shopify, WooCommerce, OpenCart, Razorpay, PayU, Zapier, Pabbly, Integrately, Google Sheets, WebEngage, CleverTap, LeadSquared, Zoho, HubSpot, Dialogflow | Shopify, WooCommerce ✅ | `BE+UI` a hub page plus: payment links (Razorpay / PayU), Zapier / Pabbly (needs the API-campaign endpoint, §5), Sheets sync, the CRMs |
| API keys | One key | Scoped keys with per-minute limit, revoke ✅ (AiSensy has one key) | — |
| **Plan and usage** | Plan, add-ons, **wallet credits, GST invoices**, AI-message packs | Plan limits exist as data; nothing on screen | `BE+UI` plan + limits view; **usage ledger from Meta's `pricing` (none today)** |
| Media library | Storage by plan | None | `BE+UI` (§2) |
| Compliance | Opt-in / opt-out keywords, blocked users | Consent ledger | `UI` |
| Security | 2FA, delete account | Prism seats are licence-based | n/a — decide whether needed |

---

## 9. Things AiSensy has that have no tab at all

| Area | What | Spec | Gap |
|---|---|---|---|
| **Dashboard and reports** | Overview / Campaign / User / Opt-in-out report downloads (Premium); home statistics not confirmed | WS7, WS15 | `BE+UI` — blocked on the **usage ledger** |
| **History** | Idle chats | WS10 | `UI` (§2) |
| **Catalogue and Commerce** | Catalogue, cart, single / multi-product messages, UPI payments, payments dashboard, failed-payment retargeting | WS12 | `BE+UI` `Meta` |
| **Forms** | Native WhatsApp Forms (appointment booking, lead capture) | WS11 | `BE+UI` `Meta` (encrypted endpoint) |
| **Acquire** | Free WhatsApp link, QR code, website button / widget | WS14 | `BE+UI` small; no Meta gate |
| **Webviews** | Marketed; mechanism unconfirmed | §9 item 5 | verify first |
| Partner / enterprise | White-label, SSO, audit log | WS15 | `BE+UI` |

The spec's information architecture (WS16) lists **Segments · Forms · Commerce · Analytics · Team ·
Acquire** as their own pages; the tab strip has none yet.

---

## 10. Order of work (dependency only — nothing dropped)

**Wave A — screens on backend that already exists.** Inbox state filters and History · chat profile
with attributes · Contacts filter builder, columns, bulk bar, add / delete, Tags and Attributes
managers, Segments page · Campaign retry toggle, full audience builder, per-recipient table and export
· template editor: Authentication, LTO, carousel (lint already there) · agent-rules editor · opt-in /
out keywords · flow response mapping and Test button · Broadcasts folded into Campaigns.

**Wave B — backend and screen together.** Media (send, receive, store, library, quota) — unlocks media
canned messages, welcome media, flow image blocks, template headers, ad creatives · **usage ledger**
(unlocks dashboard, reports, campaign spend, plan and usage page) · messaging-limit reader and
business profile · outbound webhooks · AiSensy-compatible API-campaign endpoint · embeddings + site
crawler + skills + actions + draft/published for AI agents · AI generators (template, flow, ad
creative) · category-change auto-pause · birthday and drip automations · notifications · realtime
(SSE) · journey timeline · Acquire tools · flow canvas.

**Wave C — Meta-gated, built alongside, verified as approvals land.** Facebook Login for ads;
Website / Lead-form / Status ads; Conversions API; catalogue and payments; forms; coexistence; blue tick.

Content to author alongside: templates 14 → 100+ (with construction), flows 6 → 30+, agent library.

---

## 11. What is unverified, and what would close it

* Everything about AiSensy is from its **public** pages. Column layouts, button positions and
  anything behind the login (Live Chat, Contacts, Campaign analytics, Flow Builder, Ads Manager) was
  not seen. Screenshots of those five from your AiSensy account would turn this list into exact
  screens (the same way Leads copied Apollo).
* AiSensy's own tutorial says **Authentication templates are not available for Indian numbers**;
  Meta's reference says otherwise. Check before building the OTP template.
* WhatsApp **Status ads** and **Webviews**: AiSensy markets them; no mechanism confirmed (spec §9).
* Plan numbers (tags, seats, speed) are those you pasted on 17-Oct, not re-fetched.
* The AI-agent retrieval claim (keyword search misses paraphrases) is from how full-text search
  works, not from a measured test on our data. Test it with a real FAQ set before choosing.

## 12. Sources (AiSensy, read 18-Oct-2026)

Help centre `wiki.aisensy.com`: Live Chat Panel · Understanding Chat Profile · Live Chat Settings ·
Notification Preferences · Welcome and Off-hours auto-replies · Canned Messages · Add Agents and
Managers · Agent Rules · History page (chats, filter and profile, initiate a conversation) · Import /
export contacts · Attributes · Broadcast how-to (20 steps) · Campaign Analytics · Retargeting ·
Failed Retries · Attribute fallback · Template creation · LTO · Carousel · Frequency Capping ·
Chatbot Flow Builder · API Request in flows · Build an AI Agent · Click-to-WhatsApp ads · Website
ads · Conversions API · Integrations index. Product pages `aisensy.com/features/*` (broadcasting,
retargeting, click tracking, whatsapp-support, ai-agents, meta-ads-manager, template generator) and
`news.aisensy.com` (AI Agents 2.0, 23-Jul-2026; campaign auto-pause, 14-Nov-2025). Our side:
`addons/whatsapp/*`, `prism-wa/prism_wa/*` (ops route table, `segments.py`, `templates.py`,
`campaigns.py`, `send.py`, `events.py`, `inbox.py`), `docs/WHATSAPP_PLATFORM_SPEC.md`.
