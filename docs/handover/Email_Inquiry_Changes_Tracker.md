# Email inquiry automation — change tracker

Source: the owner's list, pasted 2026-10-01/02, numbered [1]–[17] below for
cross-reference. Reorganised by SCREEN (2026-10-03) so work and status are
grouped the way the product actually is — six tabs plus the handful of
requests that cut across all of them.

Legend: ✅ done & verified · 🔧 in progress · ⬜ not started · ❌ dropped
(owner said to drop it)

Each ✅ is only marked once a real test passes or it's been checked in the
running app — nothing is marked done from memory.

---

## 6 · All mail

The screen worked on first, because it's where every piece of mail lands
before anything else happens to it.

- ✅ **[4][14] Show a mail "as a whole," not just its subject** — DONE.
  Body and attachment names are now saved for every mail, and reading one
  in full is one click/double-click away.
- ✅ **[7] Delete one or many mails** — DONE. Tick one or several
  (ctrl/shift-click), press "Delete selected," confirm, gone for good.
- ✅ **Crash/lag fix (2026-10-02)** — a real bug the above surfaced:
  redrawing this tab could re-trigger its own "row selected" handler
  mid-rebuild, reading a list that hadn't caught up yet — a Qt-level
  reentrancy bug, which is what crashes an app instead of just raising an
  error. Fixed by blocking the table's own signals during the rebuild.
- ✅ **Popup redesign (2026-10-03)** — a real complaint: the reading pane
  from the [4] fix never closed — it sat open on screen from the moment a
  row was picked. Replaced with a proper popup: double-click a row, or
  press "Open mail," read the full mail in its own window, and close it
  — the window does not linger.
- ✅ **"No text" message was misleading for old mail (2026-10-03)** — a
  real mail logged before the [4] fix existed has no body ever saved for
  it, and `worklist.append()` never retroactively updates an
  already-logged message (by design — it protects corrections a person
  already made). Checked the owner's own real data file and confirmed:
  every "inquiry"-category entry on file is from a test thread reused
  since before this round, while freshly-arriving mail today correctly
  has its text. The popup now says so plainly instead of showing the
  same "(no text in this mail)" a genuinely blank mail gets — that one
  line reading identically for both cases was the real, reported
  confusion. No backfill was built for the old entries themselves (would
  need a live mailbox re-fetch); flag if that's wanted.
- ✅ **[2] Show the time the mail arrived (2026-10-03)** — DONE. A new
  "Time" column, the reader's own local clock (not the sender's — a 9am
  mail from a different timezone must not read as 9am here either, same
  conversion the register's own "Time received" column already used).
  Verified by a new test pinned against the fixture's known timestamp.
- ✅ **[5] "This one is really a: Inquiry" should also create the actual
  register row (2026-10-03)** — DONE. Confirmed the real gap first:
  correcting a mail only ever taught Prism how to sort that sender's
  FUTURE mail — the mail in front of you stayed out of the register.
  Now, picking "Inquiry" also adds a real row (same shape a fresh check
  would have made), unless one already exists for that exact mail (no
  duplicates). One real limitation: the original attachment FILES were
  never saved for a mail that wasn't actionable at the time it arrived —
  only their names were kept, so a mail registered this way shows what
  was attached but can't recover the files themselves. Verified by 4 new
  tests (registers it, no duplicate on a second correction, no duplicate
  when already registered, not registered when corrected to something
  else), full suite clean.
- ✅ **[11] Resizable columns, and a Body column (2026-10-03)** — DONE.
  Every column in this tab was previously locked to either Stretch or
  ResizeToContents — both of those override a mouse drag, which was the
  actual bug behind "From is too wide." All seven columns (From, Subject,
  Body, Sorted as, Why, Date, Time) are now freely resizable, seeded with
  sane starting widths. Body is new: a one-line preview, so "what is this
  about" rarely even needs the popup. Verified by 3 new tests.
- ✅ **[8] A "mark as a reminder" option (2026-10-03)** — DONE. Scoped to
  exactly what the owner confirmed: flag a mail for follow-up, nothing
  more — no due date, no separate list. A "Mark as reminder"/"Unmark" pin
  button next to "This one is really a: ___", the flag shows in a new
  column and survives a redraw. Verified by 4 new tests (flags it, a
  second press unflags it, the flag survives being redrawn, nothing
  selected does nothing).
- ❌ **[16] "Open this exact mail in Gmail"** — dropped, owner's
  instruction (2026-10-03). Was "left for later"; now not wanted at all.
- ✅ **[1] A one-button "reset everything" (2026-10-03)** — DONE. One
  button, well apart from "Delete selected" so the two can't be
  misclicked for each other, with a strong confirmation (states plainly
  that it clears the whole register and every mail log, and this cannot
  be undone). Clears the register, every worklist log (arrived, replies,
  orders, sent — not just this tab's), and rewinds every configured
  mailbox's read-bookmark to zero, so the next check re-reads each
  mailbox from the start. Nothing already saved to disk (a drawing, a
  quotation, a PO already filed into an inquiry's folder) is touched —
  same principle as the existing per-row delete. Verified by 5 new tests
  (register emptied, every worklist kind emptied, the bookmark reset,
  the on-screen table goes blank too, saying "no" touches nothing) plus
  2 new tests for the new `worklist.clear()` function it's built on.

[3] moved out of this section (2026-10-03, owner's correction) — it was
never an All-mail item. See Cross-cutting below.

## 1 · To quote

- ✅ **[5]** Receiving end of the All-mail fix above — DONE together with
  it (see item [5] under All mail). A mail marked "this really is an
  inquiry" now appears here as a real row.
- ✅ **View, save, and attach a customer's file (2026-10-03)** — not from
  the original list; a follow-up ask. Every row, in every section (To
  quote, No answer yet, They answered, Order came, All inquiries — one
  shared mechanism, so no separate work per tab) and the Prepare-a-
  quotation window itself all got a "View attachments" action: open the
  real file, save a copy elsewhere, or push it straight into Prism's own
  attachment tray (the same one the sidebar's favourites already use) —
  so using a customer's drawing with any of Prism's AI tools is one
  click, not save-then-reattach by hand. Verified by 8 new tests across
  both the inquiry screen and the quotation window, including the full
  chain from a click through to the signal main_window actually
  connects to. Full suite and app selftest clean.
- ⬜ **[7]** Delete already works one row at a time (pre-existing, this
  session). Multi-select delete, same as All mail, not done yet here.
- ⬜ **[15][17] Colour grading** — grey once quoted rather than vanishing,
  green for pending, more states as useful (see the General section).

## 2 · No answer yet

- ✅ **View, save, and attach a customer's file** — same shared mechanism
  as To quote (2026-10-03); see that section.
- ⬜ **[7]** Same as To quote: single-row delete exists; multi-select
  doesn't yet.
- ⬜ **[16]** Sent + received, subject + body + image, same depth as
  All mail will get.

## 3 · They answered

- ✅ **[10] An accepted reply wasn't showing up here** — DONE. Root cause
  found and fixed: whether a reply counted depended on Prism's topic
  sorter guessing right first; a plain "Confirmed, please proceed" guesses
  neither inquiry nor order, so the part of the code that links a reply to
  its inquiry never ran. Fixed so being part of an existing inquiry's
  thread always counts, regardless of what the sorter guessed. A genuine
  mail bounce is still deliberately excluded, so a failed delivery can
  never be mistaken for a real answer.
- ✅ **View, save, and attach a customer's file** — same shared mechanism
  as To quote (2026-10-03); see that section.
- ⬜ **[7]** Multi-select delete not done here yet.
- ⬜ **[16]** Same sent/received/open-in-Gmail depth as All mail.

## 4 · Order came

- ✅ **View, save, and attach a customer's file** — same shared mechanism
  as To quote (2026-10-03); see that section.
- ⬜ **[7]** Multi-select delete not done here yet.
- ⬜ **[16]** Same sent/received depth as All mail.

## 5 · All inquiries

The master list across every stage.

- ✅ **View, save, and attach a customer's file** — same shared mechanism
  as To quote (2026-10-03); see that section.
- ⬜ **[7]** Multi-select delete not done here yet.
- ⬜ **[15][17] The KJ Pharmatech colour-graded client file** — this is
  the natural home for it: converted / no reply / quoted / yet to be
  quoted, plus whatever further states are useful, each its own colour,
  the way the owner described a real fab house's own client sheet working.
- ⬜ **[6] One file per inquiry holding everything** — sender, date, time,
  what was asked, each image's own code, current stage, the images
  themselves. Belongs here conceptually (it's the inquiry's own record)
  even though [16]'s per-tab visibility is a different, smaller ask.

## Cross-cutting (not one screen)

- ✅ **[9] OCR misreads a product detail, and a bad guess was shown as
  certain** — DONE. Real example: "SS Locker 8 Comp" read back wrong, and
  an unrelated catalogue row shown as if Prism were sure of it. Fixed:
  a picture read badly enough that only one generic word survived no
  longer passes as a "Confident match" — it correctly asks to be checked
  instead. Scoped narrowly so it didn't break a legitimate single-word
  exact-code case elsewhere (caught in testing, reverted the first, too
  broad attempt). Caveat: the raw misread itself ("8" becoming unreadable)
  couldn't be reproduced without the real photo — this fix stops it being
  silently trusted, which was the dangerous half.
- ✅ **Quotation window: noisy error, auto-picking a matched rate-list
  item (2026-10-03)** — not from the owner's original list; a real pasted
  error log. Picking a quotation's matched item fired a price
  recalculation before the window's own preview box existed yet, three
  times in a row (the first failure's side effects re-triggered it
  twice more). Reproduced exactly (same traceback, same line numbers) and
  confirmed the window did NOT actually crash or close — Qt was silently
  swallowing each exception and the window still finished opening
  correctly — but relying on that silently is fragile and the repeated
  error log is a real problem on its own. Fixed: the premature
  recalculation no longer fires; the window's own proper one still runs
  once everything exists. Verified by reproducing the bug in isolation
  first, confirming the fix removes it, full suite clean.
- ✅ **Quotation window: view/save/attach a customer's file** — the
  Prepare-a-quotation window got the same "View attachments" action as
  every register tab (2026-10-03; see "To quote"). It has no
  attach-to-Prism signal of its own — it relays through the inquiry
  screen that opened it, the one thing main_window is actually wired to.
- ⬜ **Every inquiry gets the same inquiry number, and the register isn't
  the same for every inquiry (2026-10-03)** — reported, not yet
  investigated. Owner asked to log this and come back to it later.
- ⬜ **[12] Colour grading, generally** — overlaps [15]/[17] above; being
  tracked as one piece of work under All inquiries rather than built
  piecemeal per tab.
- ⬜ **[3] Proper formatting and saving of files** — moved here from All
  mail (2026-10-03, owner's correction: not an All-mail item). Scope
  still needs pinning down — which files, which screen.
- ❌ **[13]** Dropped — an incomplete sentence in the original list, owner
  said to drop it.

---

## Summary

| Status | Items |
|---|---|
| ✅ Done & verified | 1, 2, 4, 5, 8, 9, 10, 11, 14 (14 is the same fix as 4), plus the All-mail crash fix, the popup redesign, the Quotation window fix, and view/save/attach-to-Prism on every register tab + the quotation window |
| 🔧 Partially covered, work remains | 7 |
| ⬜ Not started | 3, 6, 12, 15, 17, plus the inquiry-number/register bug |
| ❌ Dropped | 13, 16 (owner's instruction, 2026-10-03 — was "left for later", now dropped outright) |

Working one screen at a time. This file updates as each piece lands —
nothing is marked ✅ without a real test passing or a check in the app.
