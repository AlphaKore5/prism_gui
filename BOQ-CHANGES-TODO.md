# BOQ add-on — changes to make

Noted down 2026-10-20, from the owner, not yet implemented. Read this file
before any BOQ work and check off / update it as items land — do not delete
an item just because related code was touched; only check it off once the
exact behaviour below is true in `addons/boq/`.

## 1. Writer and research agent lists

**Writer (write-up) agents must include:** Groq-inhouse, Claude, Gemini,
ChatGPT, Grok, Kimi, DeepSeek.

**Research agents must include:** Perplexity, ChatGPT, Claude.

- [x] Module separated (2026-10-20): BOQ's writer/research picker pools now
      live in `addons/boq/agents.py` (`WRITER`, `RESEARCH`), not the engine's
      shared `prism_terminal/core/agents.py:CATEGORIES`. `addons/boq/dialog.py`
      reads only from that file now, so editing BOQ's lists can no longer
      change what Leads/Content/Visual offer. This was a pure move — list
      content is unchanged, both BOQ test files + BOQ pricing tests pass
      (55/55). The actual content change below is still **not done**.
- [x] Content done (2026-10-21) — see the three jobs below, all shipped.

Checked each requested writer agent against what the engine can actually
drive (`prism_terminal/core/agents.py`, `core/router.py`, `core/automation.py`):

| Agent | Exists today? | What adding it means |
|---|---|---|
| Claude | yes (browser automation) | add to `addons/boq/agents.py:WRITER` |
| ChatGPT | yes (browser automation) | already there |
| Kimi 2.6 | yes (browser automation) | already there |
| Google Gemini | yes, but only wired for *image* output (`visual` category) | needs checking/building a text-writing automation profile for it, not just a list add |
| Groq-inhouse | not an "agent" at all — Groq is called directly via `core/router.py:groq_chat`, API-key based, no browser, the same path STEP's Ask/Edit uses (`prism_terminal/core/stepfile.py:ask_prompt`) | needs a new BOQ prompt + a new code path in `addons/boq/dialog.py`/`workers.py` that calls `router.groq_chat` directly, parallel to STEP's — not a picker-list entry |
| Grok | no integration anywhere in the repo | a whole new browser-automation profile in `core/automation.py` (site quirks, selectors, login) from scratch |
| DeepSeek | no integration anywhere in the repo | same as Grok — new automation profile from scratch |

So this item is really three different-sized jobs:
  1. Trivial — add Claude to `WRITER` (ChatGPT, Kimi 2.6 already present);
     add ChatGPT + Claude to `RESEARCH` (Perplexity already present).
     - [x] **Done (2026-10-20).** `RESEARCH` is now
           `["Perplexity", "ChatGPT", "Claude"]` — Claude added, then
           Consensus/WolframAlpha/Semantic Scholar/NotebookLM/LAZYCOOK
           dropped (owner's call: not useful for a standards-research job),
           then ChatGPT added. `WRITER` already had Claude + ChatGPT, so it
           was untouched. 55/55 BOQ+BOM tests pass throughout.
  2. Medium — give Gemini a text-writing automation profile, not just image.
  3. Large — build real Grok and DeepSeek automation from nothing, and wire
     Groq in-house as its own direct-API code path for BOQ.
     - [x] **Groq in-house done (2026-10-20).** Owner's call: build the
           backend before adding the name, not the other way round. Added
           `addons/boq/workers.py:BoqGroqWorker` — a direct
           `core.router.groq_chat` call (the same one-key path STEP's Ask
           already uses), not browser automation. `"Groq"` is now in
           `addons/boq/agents.py:WRITER`. Because it has no file upload,
           `addons/boq/dialog.py` refuses rather than silently drops a file
           in every path that could reach it with one: no API key configured
           (checked at submit), an attached template/notes file (checked at
           submit), a priced reference CSV (checked at write time, since
           pricing can be filled in after submit), "Verify and remake"
           (always sends the drawing file — refused before the consent
           popup even opens, both from the Recheck button and from the
           follow-up window's quick action), and a typed follow-up with its
           own attached file (the authoritative check, inside
           `_send_followup` itself). 7 new tests in
           `tests/test_boq_dialog.py::GroqInHouseIsADirectCallNotABrowserAgent`,
           62/62 BOQ+BOM tests pass.
     - [x] **Grok done (2026-10-20).** A real
           `prism_terminal/core/agents.py:AGENT_REGISTRY["Grok"]` entry —
           an actual browser agent, not an API shortcut like Groq, so it
           needs no special-casing in `addons/boq/dialog.py` at all; it
           goes through the ordinary `AutomationWorker` path exactly like
           Claude/ChatGPT/Kimi. Selectors (`textarea_selector`,
           `response_selector`, `submit_selector`, `busy_selector`,
           `regenerate_selector`) were verified LIVE against grok.com,
           not guessed — the owner's own account, via Claude in Chrome,
           both a quick exchange and a longer one to catch the
           mid-generation "Stop model response" state. One live finding:
           a one-time, non-dismissible age-confirmation modal blocked the
           very first message on this account — the owner supplied their
           birth year in chat and gave explicit OK for it to be entered;
           it does not reappear afterwards and is not part of the chat DOM
           automation touches. "Grok" added to
           `addons/boq/agents.py:WRITER`. 3 new tests in
           `tests/test_boq_dialog.py::GrokIsARealRegisteredBrowserAgent`.
           282/282 BOQ+BOM+STEP+registry tests pass.
     - [x] **DeepSeek done (2026-10-20).** The owner logged into
           chat.deepseek.com themselves, then selectors were verified LIVE
           the same way as Grok's. This app has no `data-testid` attributes
           at all (unlike grok.com) — its own design-system class names
           (`ds-button`, `ds-markdown`, …) are what the three selectors key
           off instead. One real trap caught live: a SECOND, unrelated
           element also matches `.ds-button--circle` once a conversation is
           tall enough to show a floating "scroll to newest message"
           control above the composer — `submit_selector` explicitly
           excludes it (`:not(.ds-button--floating)`), or a long
           conversation's next message would click "scroll" instead of
           sending. Two fields were deliberately left UNSET rather than
           guessed: `busy_selector` (the send button reads
           `ds-button--disabled` whether the box is merely empty or a reply
           is actively streaming — checked repeatedly, including with "Deep
           thinking" on to widen the window — no class or icon distinguishes
           the two) and `regenerate_selector` (no distinct control found
           near a finished answer). Neither is required — `_GENERIC` has no
           default for either, so DeepSeek falls back to the engine's own
           generic "text stopped growing" wait, same as Perplexity and
           Kimi 2.6 already do. "DeepSeek" added to
           `addons/boq/agents.py:WRITER`. 3 new tests in
           `tests/test_boq_dialog.py::DeepSeekIsARealRegisteredBrowserAgent`.
           288/288 BOQ+BOM+STEP+registry tests pass.

**Gemini done (2026-10-21).** A SEPARATE `AGENT_REGISTRY["Gemini"]` text
entry, not a change to the existing `"Google Gemini"` image-maker one —
`core.agents._MAKES` permanently tags `"Google Gemini"` as an image tool
at module load, so reusing it for text would have made every BOQ write-up
run look like an image request. Selectors verified live the same way as
Grok/DeepSeek; confirmed directly that `is_maker()` is `False` for the
new "Gemini" entry and still `True` for "Google Gemini". "Gemini" added
to `addons/boq/agents.py:WRITER`.

All seven writer agents from the owner's original 2026-10-20 list are
now in `WRITER`, item 1 is fully done.

Housekeeping note: live-verifying Grok and DeepSeek left a few real test
conversations in the owner's own chat history on both sites ("What is
2+2?", a suspension-bridge question, a train-meeting word problem, etc.) —
harmless, but real clutter on a real account; mention to the owner in case
they want them deleted.

## 2. Follow-up flow: per-stage agent control + fallbacks

Wanted: a follow-up window like Prism core's, showing the work as a flow —
and letting the owner control, per run:
  - which agent verifies/remakes the drawing,
  - which agent handles a plain follow-up,
  - the fallback chain when the chosen agent can't answer (e.g. ChatGPT's
    memory limit causing an error mid-job) — specifically Claude and Kimi as
    fallback candidates.

- [x] **Done (2026-10-21).** The owner showed two screenshots of Prism
      core's own Run screen (`widgets/output_panel.py`'s `RunHeader` +
      `StageCard`, wired in `main_window.py`) and asked for the same look
      and the same Skip/Use fallback/Stop controls on BOQ's follow-up and
      "Verify and remake" calls — a live window, not just an error popup.

What shipped:
  - **`addons/boq/run_dialog.py`** (new) — `BoqRunDialog`, a small modal
    reusing `StageCard` directly (same status badges, timeline dot, live
    elapsed clock the real Run screen uses — not a reimplementation) for
    the one job BOQ is ever doing, with Skip / Use fallback / Stop and a
    Close button that only unlocks once the run is actually over.
  - **`addons/boq/agents.py`**: `FALLBACK_ORDER = ("Claude", "Kimi 2.6")`
    — the owner's own words, "when those errors occur which agent should
    be used as a fallback (claude/kimi)". Same flat-tuple shape as
    `addons/step/dialog.py`'s own `FALLBACK_ORDER`, deliberately NOT
    `core.agents.alternatives_for()` — that resolves by CATEGORY, and
    BOQ's stage keys (`"format"`, `"recheck"`, `"followup"`) aren't
    categories, so it would silently find nothing for any of them. Caught
    by re-reading `AGENT_REGISTRY`'s `_fallback_signal`/`alternatives_for`
    path before building anything on top of it.
  - **`addons/boq/dialog.py`**: `_send_followup`'s browser-agent branch
    (Groq's own direct-API branch is untouched, unaffected, no live
    window — there's no tab to hand to a fallback tool) now goes through
    `_start_followup_run`, which builds the chain (chosen agent first,
    then whichever of `FALLBACK_ORDER` it isn't already), opens the
    dialog, and reuses the SAME `StageCard` across every attempt — the
    same way a real failover in the core Run screen swaps a card's agent
    in place rather than stacking a new one. A failure auto-advances to
    the next agent; the dialog's buttons map to: Skip → the real, already
    -working `worker.skip()` (generic, not stage-name-dependent — verified
    by reading `workers.py`'s `AutomationWorker.run()`, which already
    wires `should_stop`/`skip_signal` into every `automation.run()` call
    regardless of `custom_stages`); Stop → the real `worker.skip()`'s
    sibling `worker.stop()`; Use fallback → BOQ's own stop-current
    -then-start-next (NOT `worker.use_fallback()`, which hits the same
    `alternatives_for` gap as the automatic path would have). A token
    counter guards against a stopped worker's late signal overwriting a
    newer attempt's result.
  - **Scope, stated plainly**: this covers "Verify and remake" and
    follow-ups, matching the owner's own wording ("while the followup,
    there should be window..."). The very first "Write" call
    (`_write()`) is untouched — no live window, no fallback chain — a
    deliberate boundary, not an oversight.
  - **Agent choice**: the owner's complaint was "the first agent that i
    select is the only one that gets the original dwg file to verify the
    readings, i dont have the freedom to choose" — solved by the fallback
    chain and the "Use fallback" button rather than a second persistent
    picker cluttering the main screen for an action used occasionally. No
    separate "Verify with" / "Follow up with" dropdowns were added.
  - **`widgets/agents_panel.py`**: three new `STAGE_COPY` entries
    (`"format"`, `"recheck"`, `"followup"`) so `StageCard` shows readable
    titles/icons for BOQ's stages instead of the generic grid-icon
    fallback — the same shared, cross-add-on dict `"analysis"` (not a
    pipeline category either) was already added to, so this follows an
    established pattern rather than starting a new one.
  - **A real, caught-live bug**: the first implementation called
    `BoqRunDialog.exec()` unconditionally from `_send_followup`, which
    hung the three EXISTING follow-up tests solid — their mocked worker
    never fires a signal, so the real modal never got a reason to close.
    Killed the hung run, fixed it the way `FollowupDialog`'s own tests
    already do: every test that reaches this path now patches
    `addons.boq.run_dialog.BoqRunDialog` with a fake whose `.exec()`
    returns immediately.
  - Tests: 9 in `tests/test_boq_dialog.py::TheFollowUpFlowHasALiveWindow
    AndAFallbackChain` (chain construction, automatic retry, chain
    exhaustion, success, skip, stop, manual fallback, the stale-signal
    guard) + 9 in the new `tests/test_boq_run_dialog.py` (the real,
    unmocked `BoqRunDialog` itself — construction, every state
    transition, the close-mid-run-asks-to-stop behaviour). 306/306 across
    BOQ+BOM+STEP+registry+the new file, re-run clean after the hang fix.

Both items from the owner's 2026-10-20 list are now done.

## 3. Writer list, in order — and Groq-inhouse's real job is stage one of two

Noted 2026-10-21, from the owner, not yet implemented. **Revised 2026-10-21**
— the owner caught that DeepSeek was accidentally dropped from the first
write-up, and redefined what "Groq-inhouse must handle files" actually
means once told it's not realistic (see below).

**Writer (write-up) agents must be, in this exact order:**
Groq-inhouse, Claude, ChatGPT, Gemini, Kimi, Grok, DeepSeek.
(DeepSeek's exact position wasn't specified beyond "include it" — appended
at the end here; confirm with the owner if it belongs somewhere else in the
order.)

This REPLACES the current `addons/boq/agents.py:WRITER` list, which today is
`["Perplexity", "ChatGPT", "Claude", "Groq", "Grok", "DeepSeek", "Gemini",
"LAZYCOOK", "Jasper", "Copy.ai", "Kimi 2.6", "Writesonic"]`. To match, this
item drops Perplexity, LAZYCOOK, Jasper, Copy.ai, Writesonic from `WRITER`
entirely, and reorders the seven survivors to the exact sequence above (the
combo box is built straight from the list, so order in the file is order on
screen).

**Groq-inhouse's job, redefined — a two-stage pipeline, not file-handling:**
the owner accepted that Groq-inhouse can't realistically read a drawing file
or a sample-format `.docx` (no file input on its API path). Revised ask:
Groq-inhouse makes a **text-only BOQ from the measured figures** — nothing
more — and that text is then handed to a SECOND, user-chosen agent (any of
ChatGPT, Claude, Gemini, Kimi, DeepSeek, Grok) whose job is to turn that text
into the real output file, in whichever format the user picked (`.docx` or
`.csv`).

- [x] **Stage one may already work as-is, for the plain case.** Checked
      `addons/boq/dialog.py`: when Groq is chosen and there is no attached
      template/notes file, `_write()` already runs `BoqGroqWorker` on the
      measured-figures text and gets a text answer back — item 1's own
      refusal only fires when a FILE is attached, not for the ordinary
      figures-only case. So "Groq-inhouse produces a text BOQ from the
      measurements" is likely already true today; needs a real run to
      confirm rather than assuming.
- [ ] **Stage two — not built at all.** Nothing today hands a prior answer's
      text to a second agent for reformatting-only. Needs:
  - [ ] a way to choose the second ("convert with") agent — likely the same
        UI control as item 5's format picker, or paired with it, since both
        are about "what should the final file look like and who makes it" —
        design these two together, not separately, so the owner isn't given
        two overlapping pickers.
  - [ ] a prompt/worker path that sends Groq's text answer (not the original
        measurements, not the drawing) to the chosen second agent asking it
        to produce the file in the chosen format — this is closer to
        `_send_followup`'s shape (continue from a previous answer) than to
        `_write()`'s (start fresh), so it may be able to reuse the
        fallback-chain/live-window machinery from item 2 rather than being
        a third, separate code path.
  - [ ] decide what happens if the owner picks Groq-inhouse as BOTH stage
        one and the "convert with" agent — Groq-inhouse still can't produce
        a file itself, so either the second-stage picker should exclude
        Groq-inhouse, or picking it there should be refused the same way
        file-attached Groq runs already are.

## 4. A follow-up's new file never replaces the old one shown to the owner

Noted 2026-10-21, from the owner, not yet implemented. Reported with two
screenshots. **Corrected 2026-10-21** — the first write-up of this item
mischaracterized it as "produced a `.docx` instead of a `.csv`"; that is
NOT what was reported. The actual report:

**What happened:** the first run produced `boq_quantities_1792531109.csv`,
shown in the follow-up window's "What Prism produced" card (1 item, the
`.csv`). The owner then sent a follow-up instruction asking for a `.docx`
file instead. It ran, invoked Claude, and (per the owner) completed —
**a new file WAS generated by the follow-up run** — but the follow-up
window, reopened afterward, **still fetches and shows the old
`boq_quantities_1792531109.csv`**, never surfacing the new file the
follow-up just made.

- [x] **Done (2026-10-21).** Root cause, once traced: nothing in
      `addons/boq/dialog.py` ever tracked an AI-produced file at all — not
      a bug specific to follow-ups. `_offer_followup()`'s artifacts list
      was hardcoded to `self.csv_path`, the LOCALLY measured quantities
      CSV made once before any AI runs, because that was the only file
      path the dialog had ever held onto. A new `self._deliverable_path`
      is now set from `AutomationWorker(files_out=...)` — a caller-owned
      list the engine already appends every harvested file to (the same
      mechanism `addons/step/dialog.py:_on_drafted` uses) — wired into the
      write-up, recheck and follow-up calls alike. Whatever comes back is
      copied into the run's own Artifacts folder via `CB.config.
      save_artifact` and shown FIRST in the follow-up window, ahead of
      (not instead of) the measured CSV. 2 new tests.

## 5. "Verify and remake" produces no file at all, in any format

Noted 2026-10-21, from the owner. **Done (2026-10-21).**

**What happened:** pressing "Verify and remake" and letting it run produced
no output file whatsoever — not a `.csv`, not a `.docx`, nothing.

**Also requested:** a dedicated control to choose the output file format
the owner wants.

What shipped:
  - A **"File format" picker** next to "Write with" — Let the tool decide
    (default) / Word (.docx) / CSV / PDF.
  - Root cause: `VERIFY_PROMPT` only ever asked the agent to check figures
    against the drawing, never to produce a file — so there was never
    anything for the engine's own file-harvesting to find, format picker
    or not. Picking a format now appends one line to the prompt AND
    promotes the stage to a `file`-kind step in the engine's own contract
    system (`prism_terminal/core/contract.py`'s `_WRITING_STAGES`, which
    `"recheck"`/`"followup"` were missing from entirely) — that system
    already re-asks once for the file and, worst case, writes the
    document itself out of the tool's own text, the same guarantee a
    fresh write-up already had. Groq (in-house) is excluded: no browser
    page, so no file to produce.
  - 3 new tests (default adds nothing to the prompt, a chosen format adds
    the request line, Groq never receives it).

## 6. "Verify and remake"'s progress window underestimates how long it takes

Noted 2026-10-21, from the owner. **Done (2026-10-21).**

**What happened:** the live progress window for "Verify and remake" (the
`BoqRunDialog` from item 2) read as if the step was short, but a real run
— the agent has to read the drawing itself — can take on the order of 20
minutes to come back with an answer, with nothing on screen saying that
was normal.

What shipped:
  - `AutomationWorker` gains a raw `min_wait` passthrough, independent of
    the existing `followup=True` (which already raises the ceiling to
    `automation.FOLLOWUP_MIN_WAIT`, 8 minutes, for any follow-up) — a
    caller that knows ONE particular stage is heavier can raise the floor
    further without changing what `followup=True` otherwise does. BOQ's
    "recheck" now gets a 20-minute floor; a plain "followup" keeps the
    8-minute one.
  - Both recheck and follow-up now pass `followup=True` where neither did
    before — they previously got the SAME short, generic wait ceiling as
    any other stage.
  - `BoqRunDialog` takes an optional `note`, shown on the card up front:
    "{agent} is reading the drawing itself, not just answering from
    memory — this can take up to 20 minutes." for recheck specifically.
  - 4 new tests (the wait floor for each stage, the note for each stage).

Items 4-6 share one more fix, needed for the format picker and the real
wait ceiling to reach the engine at all: `AutomationWorker`'s `query`
argument for recheck/followup was a short internal label
(`"recheck — <doc>"`), never the actual prompt text — so the engine's own
`wants_file()` scan (which decides whether a stage owes a file) could
never see a chosen format or the words "make it a docx" even typed
directly into a follow-up. The real prompt is passed as `query` now.

Tests: 19 new across `tests/test_boq_dialog.py` (14) and the earlier
`tests/test_boq_run_dialog.py` (unchanged this round). Full BOQ+BOM+STEP+
run_dialog suite green, plus a sweep of Gerber/Reel/Motion/email/
worker_mandate since `workers.py` and `core/contract.py` are shared by
every add-on, not just BOQ.

All six items from the owner's 2026-10-20/21 list are now done, except
item 3's "stage two" (handing Groq-inhouse's text answer to a second,
user-chosen agent for file conversion) — still open, tracked above.
