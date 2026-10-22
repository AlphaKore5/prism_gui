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

## 7. "Verify and remake" opened a fresh window instead of continuing the one already on screen

Noted 2026-10-22, from the owner. **Done (2026-10-22).**

**What happened:** after a BOQ is written (without the drawing ever
touching the AI — the engine is handed the measured figures only), the
owner's usual move is "Verify and remake": send the DWG file itself so an
agent can check the measured quantities against it. Instead of carrying
on in the live-progress window the ordinary follow-up (or the write-up
itself) was already shown in, pressing it — or running a plain
follow-up, then "Verify and remake" straight after — popped a brand new
`BoqRunDialog` window each time. The owner wanted this to work the way
Prism core's own Run screen does: ONE window for the session, carried
from job to job, not a fresh one per click — the two genuinely different
DWG-sending moments ("Recheck with drawing," before the main pipeline
even runs, versus "Verify and remake" after a BOQ already exists) were
never the issue; the window itself was the thing resetting.

What shipped:
  - **`addons/boq/run_dialog.py`**: `BoqRunDialog.restart(title, stage,
    agent, note="")` — undoes a prior `finish_*()` lock, swaps in a fresh
    `StageCard` for the new stage/agent (a stale "done"/"error" card
    redrawn as "running" would still carry the old job's timeline dot and
    elapsed clock, so a new one replaces it via the stored layout
    reference, `self._card_row`, rather than reusing the old widget), and
    re-enables Skip / Use fallback / Stop while relocking Close.
  - **`addons/boq/dialog.py`**: `self._fu_dialog` is now initialised once
    in `__init__` (`None`) and kept for the life of the dialog.
    `_start_followup_run` builds a `BoqRunDialog` only the FIRST time;
    every later call — a second follow-up, "Verify and remake" after one,
    a follow-up after a recheck, any order — calls `restart()` on the
    SAME instance instead.
  - **`.exec()` → `.show()` + `.raise_()` + `.activateWindow()`**: the old
    code's modal `.exec()` enters its own blocking event loop and only
    returns once the window closes, so the same instance could never be
    reused for a later job without destroying it first. `setModal(True)`
    (already set in `__init__`) keeps the BOQ dialog from being clicked
    underneath it either way — this is the same non-blocking pattern
    `main_window.py` uses for its one, app-lifetime `OutputPanel`.
  - Tests: 3 in `tests/test_boq_dialog.py::TheLiveWindowIsReusedAcrossFollowUps`
    (verify-and-remake after a follow-up reuses the window and not a
    second one; a third call restarts again rather than building a
    third; the window is shown, never exec()'d, so no test can hang) + 4
    in `tests/test_boq_run_dialog.py::RestartReusesTheWindowForTheNextJob`
    (restart undoes a lock, swaps the card, drops the old note, and can
    finish again afterwards) + `_FakeRunDialog` in `test_boq_dialog.py`
    gained `restart()`/`show()`/`raise_()`/`activateWindow()` and a
    `construct_calls` counter so a test can tell a reuse from a rebuild.
    81/81 across both BOQ dialog test files, full suite unaffected
    (nothing outside BOQ touches `BoqRunDialog`).

**CORRECTION, 2026-10-22, same day — the fix above was real but incomplete,
and marking it "Done" without catching that was wrong.** The owner tested
it: "Make with drawing," then a follow-up ("generate a docx of this") on
top of it still opened a fresh browser tab/chat — and the same thing
happened following up after an ordinary "Make my BOQ". What shipped above
fixed Prism's OWN small progress popup (`BoqRunDialog`) — a real, correct
fix, and still needed — but it is not what "opens a new tab" meant. The
actual new tab is the BROWSER's own tab for the writing agent's chat
(Claude.ai / ChatGPT, etc.), controlled entirely separately, inside
`prism_terminal/core/automation.py` — a layer the first pass of this item
never looked at. Caught only because the owner tested the real app end to
end rather than trusting the earlier write-up.

**What was actually wrong:** the engine already has a working mechanism
for exactly this — `resume_urls`, a `{stage: chat_url}` dict passed into
`AutomationWorker`/`automation.run()` that tells it to navigate straight
back to an existing conversation instead of opening a fresh tab
(`core/automation.py`'s `_open_agent_page` checks it before deciding
whether to open a new tab at all). `addons/step/dialog.py`'s own
follow-up handler already uses it correctly. **`addons/boq/dialog.py`
simply never called it, on any follow-up, ever** — every `_send_followup`
call built a brand-new `custom_stages` job with no `resume_urls`, so the
engine had no way to know a chat already existed to go back to, and
always opened a new one. BOQ already tracked everything needed to fix
this (`self._stage_agents_map`, `self._links`) — the pieces existed, nobody
had wired them to this specific parameter.

**The actual fix:**
  - **`addons/boq/dialog.py`**: two new fields, `self._last_agent` /
    `self._last_link` — "who answered most recently, and that exact
    chat's own URL" — updated at the end of EVERY completed stage
    (`_on_written` for the first write-up, `_on_followed_up` for every
    follow-up/recheck after it, so a third follow-up resumes the SECOND
    one's chat, not reaches back to the very first).
  - **`_fu_start_next`** now builds `resume_urls = {self._fu_stage:
    self._last_link} if tool == self._last_agent and self._last_link else
    None` before constructing the `AutomationWorker`, and passes it
    through. Guarded on the SAME agent answering again — switching
    agents (or falling back to a different one mid-chain after a
    failure) correctly resumes nothing, because there is no chat of that
    OTHER tool's to go back to; it falls through to the existing
    full-context prompt instead, exactly as before. The same check
    `addons/step/dialog.py`'s `_on_answer_followup` already makes, not a
    new pattern invented for BOQ.
  - Groq's own branch in `_send_followup` is untouched and unaffected —
    it has no browser page at all, so `self._last_link` stays empty
    whenever Groq last answered, and resume correctly never triggers for
    it, with no special-casing needed.
  - 6 new tests in `tests/test_boq_dialog.py::
    AFollowUpResumesTheSameChatInsteadOfOpeningAFreshOne`: a first
    write-up leaves its chat resumable; a same-agent follow-up actually
    gets `resume_urls`; switching agents gets `None`; a SECOND follow-up
    resumes the FIRST follow-up's chat, not the original write-up's;
    "Make with drawing" as the very first action (nothing to resume yet)
    gets `None`; a mid-chain fallback to a different tool also gets
    `None`. 136/136 across the full BOQ+BOM+site-facts sweep.
  - **Said plainly, for the record:** the first pass at item 7 was
    reported as "Done" without actually tracing where a new browser tab
    comes from in the engine — it fixed a real problem, just not the one
    that was reported, and that gap wasn't caught until the owner tested
    it directly. The fix above is now verified against the actual
    mechanism that opens a tab, not just against Prism's own popup.

## 8. "Recheck with the drawing" and "Verify and remake" are the same job — renamed and made available from the start

Noted 2026-10-22, from the owner. **Done (2026-10-22).**

**The owner's point:** "Verify and remake" (the follow-up window's quick
action) and "Recheck with the drawing" (the button next to the result box)
send the exact same thing — the drawing file itself, with explicit consent
— to do the exact same job. The button should be renamed **"Make with
drawing"** and stand next to **"Make my BOQ"** from the start, not stay
disabled until a BOQ already exists: "Make my BOQ" uses the offline
measured quantities alone; "Make with drawing" gives the drawing file to
the AI directly, after asking permission again.

What shipped:
  - **Button renamed** — `i18n.t("Recheck with the drawing")` →
    `i18n.t("Make with drawing")`. `devtools/extract_strings.py` run after:
    2 new strings, 1 retired.
  - **Enabled by a drawing alone, not by also requiring an existing
    answer.** Previously gated on `bool(self.cad_path) and bool(texts)`
    (three separate spots: construction, after a write-up, and
    `_set_busy`) — now just `bool(self.cad_path)`, and also turned on the
    moment a drawing finishes measuring (`_on_measured`), not only after
    "Make my BOQ" has already run once. This is the actual fix: before,
    the button genuinely could not be pressed until a BOQ existed, which
    is why it only ever behaved like a recheck.
  - **One new prompt, used only when there is nothing to verify yet** —
    `MAKE_WITH_DRAWING_PROMPT`, next to the existing `VERIFY_PROMPT`.
    `VERIFY_PROMPT`'s own wording ("remake... in the same format as the
    previous answer... list what changed") only makes sense once an
    answer exists; pressing "Make with drawing" before any BOQ is written
    now sends the new prompt instead, asking the agent to read the
    drawing directly and cross-check it against the locally measured
    figures.
  - **The "PREVIOUS ANSWER" section is now conditional**, not always
    appended — `_send_followup` only adds it when `self.result` actually
    has text. Before this, pressing the button with no existing answer
    would have sent `"PREVIOUS ANSWER:\n\n"`, which reads as a blank
    previous answer rather than there being none.
  - **The live-progress window's title branches the same way** —
    "Making your BOQ from the drawing" when there is nothing previous
    (checked off whether the built prompt actually contains
    `"PREVIOUS ANSWER:"`, not by re-reading `self.result`, which could in
    principle have changed by the time the window opens), "Verifying
    against the drawing" otherwise — unchanged from before this item.
  - Both call sites still reach the SAME engine stage key, `"recheck"` —
    no change needed in `prism_terminal/core/contract.py`'s
    `_WRITING_STAGES` or anywhere else engine-side; only the prompt text
    and the window title differ between the two moments.
  - 5 new tests in `tests/test_boq_dialog.py` (the button's new label; on
    even with no answer yet; the no-previous-answer prompt omits
    "PREVIOUS ANSWER" and reads as making, not verifying, with the
    matching window title; the with-previous-answer path is unchanged)
    + the one stale test from item 2's era renamed to describe what is
    actually true now instead of what used to be true. 110/110 across
    the full BOQ+BOM sweep (`test_boq_dialog.py`, `test_boq_run_dialog.py`,
    `test_boq_file_guardrail.py`, `test_boq_pricing.py`).

## 9. A sample BOQ/template as a reference — discoverable, without sending the drawing

Noted 2026-10-22, from the owner. **Done (2026-10-22).**

**What was asked:** "there should be option for the user to just give in
the sample BOQs/template for the BOQs... such that they could be given as
the reference to the AI for creation of better BOQs without actually
giving the drawing file to the AIs."

**What was actually true before this item:** the mechanism already
existed and already worked exactly as asked — `prism_terminal/core/
boq.py:classify_inputs` has always sorted an attached sample/previous BOQ
(`.docx`/`.doc`/`.xlsx`/`.xls`/`.csv`/`.ods`/`.pdf`) into its own
`templates` role, described to the writing agent as "an example BOQ
showing the firm's usual style" — and the drawing is a SEPARATE role
(`cad`) that is never folded into it. This was never built in this
session; checked directly in the engine before touching anything. The
real problem was pure discoverability: nothing on screen ever told the
user a sample/template could be attached at all, so in practice nobody
attached one on purpose.

What shipped:
  - **A standing invitation**, `self.template_hint`, under the drawing
    format note: "You can also attach a sample BOQ or your usual
    template above — Prism will match its style, logo and layout. This
    is separate from the drawing, which is only ever sent to an AI after
    you say so, in 'Make with drawing'." — naming item 8's button
    directly, so the one reassurance the owner asked for (the drawing is
    not swept up in this) sits right next to the invitation, not in a
    different part of the screen.
  - **Turns into a confirmation once one actually lands** —
    `_update_template_hint()`, called from `_absorb()` whenever
    `classify_inputs` returns at least one template: "N sample
    template(s) attached — Prism will match the style shown. [same
    drawing reassurance]", singular/plural worded correctly, the count
    rising as more are attached rather than resetting.
  - **Scope, stated plainly**: no change to `classify_inputs`, no change
    to what gets sent to the AI or how — this item is screen text only,
    making an existing, already-correct behaviour visible and trustable.
  - 4 new tests in
    `tests/test_boq_dialog.py::AttachingASampleTemplateIsDiscoverableAndConfirmed`
    (the standing invitation's wording before anything is attached;
    attaching one confirms it with a count and still names "Make with
    drawing"; a second one updates the count and pluralises; a plain
    `.txt` note — classified as "notes", not "templates" — leaves the
    hint alone). `devtools/extract_strings.py` run after: 4 new strings,
    none removed. 114/114 across the full BOQ+BOM sweep.

## 10. "Price it" sat there, static and useless, before a BOQ even existed

Noted 2026-10-22, from the owner, with a screenshot. **Done (2026-10-22)
— both parts, after the owner's own clarification resolved the tension
part two originally flagged.**

**What was reported:** the "Price it (optional)" card appeared right
after a drawing was measured — before "Make my BOQ" had even been
pressed — sitting there empty and inert. The owner's own words: "this is
now staying static and honestly this is useless, as we can decide the
pricing based on just the measured quantities, we can add this feature
once the BOQ is formed." Proposed flow: form the BOQ first; once it
exists, let the user bring a price list as a later, deliberate step, and
"use the groq-inhouse agent to fill in the details in the BOQ document
that are already made like excel and word."

**Part one — shipped.** The card's DATA has been ready since the
measurement finished all along (`price_table.set_quantities()` in
`_on_measured`); only its VISIBILITY moved. `self.price_box.setVisible
(True)` no longer fires there — it now fires once a BOQ actually has
text, in both places that can produce the first one: `_on_written` (the
ordinary "Make my BOQ" path) and `_on_followed_up` (item 8's "Make with
drawing" used as the very first action, before any BOQ exists). A
write-up that comes back with nothing leaves the card hidden, same as
before pricing could ever have existed. 2 new tests in
`tests/test_boq_pricing.py` (shown once a real write-up lands; a write-up
with nothing back leaves it hidden) + the one stale test from this
card's original build renamed and corrected (it asserted the OLD
"visible right after measuring" behaviour, which is exactly what this
item reports as the problem). 116/116 across the full BOQ+BOM sweep. One
real bug caught building the test: calling `_on_written` with real text
reaches `_offer_followup()`, which opens a real `FollowupDialog` — had to
patch it the same way every other BOQ test on this path already does, or
the test hangs forever (CLAUDE.md: never exec()/a QEventLoop in a test).

**Part two — the owner's clarification, and what it actually meant.**
Asked to resolve the tension against `boq_price.py`'s "no number of
record is ever produced by an AI, without exception" rule (option (a)/
(b)/(c) above, as originally written). The owner's answer: "basically i
want that BOQ in any format gets filled in with the number from the
pricing list the user will attach, that's it" — option (b), and simpler
than first described: no AI merge step at all. The numbers were always
going to come from the user's own attached price list (the existing
deterministic matcher, unchanged); the actual, narrower gap was that
"any format" wasn't true yet — `write_boq_xlsx`/`_csv`/`_pdf` existed in
`core/boq_price.py`, `write_boq_docx` did not, so Word was the one format
the priced numbers could never reach. No Groq, no AI, no rule change
needed — this was a missing writer, not a missing merge.

What shipped:
  - **`prism_terminal/core/boq_price.py`: `write_boq_docx(boq, path)`**,
    fourth alongside the existing three. Reuses the SAME `Boq` model and
    the SAME canonical Decimal methods the other writers call
    (`subtotal()`/`contingency_amount()`/`pre_tax_total()`/
    `gst_amount()`/`grand_total()`) — nothing here recomputes a total
    independently, so Word can never disagree with Excel/CSV/PDF by a
    paisa. The CGST/SGST split mirrors `boq_html()`'s own approach
    exactly (SGST = `gst_amount() - cgst`, not computed separately, so
    the two halves always sum to the exact total). A table per the same
    `_COLS` header `write_boq_xlsx` uses, a merged section-header row
    per section, a sub-total row per section, then the same roll-up
    (sub-total → contingency → GST/IGST → grand total) and the same
    amount-in-words line. Guarded by a new `HAVE_DOCX` flag, same
    pattern as `HAVE_XLSX` — `python-docx` is already a project
    dependency, used elsewhere in the engine. Word has no formula cells,
    so unlike the xlsx sheet this is a flat, once-computed table — the
    docstring says so plainly, and that editing a rate here does not
    re-flow the totals the way Excel's live formulas do.
  - **`addons/boq/pricing.py`**: a fourth export button, "Save as
    Word…", next to Excel/CSV/PDF, wired through the same `export(kind,
    path)` / `_export(kind)` methods every other format already uses —
    no new code path, one new dict entry in each.
  - 1 new test, `tests/test_boq_pricing.py::TheExportsWriteWhatTheGridShows
    ::test_docx_has_the_same_grid_and_totals_as_every_other_format` —
    opens the real .docx with `python-docx` and checks the matched rate,
    the computed amount and the grand total are all actually in the
    table, the same shape the existing `test_csv`/`test_xlsx_has_live
    _formulas` tests already check for their own formats. `devtools/
    extract_strings.py` run after: 2 new strings, none removed. 117/117
    across the full BOQ+BOM sweep.
  - Manually verified directly against `core/boq_price.py` before
    wiring the UI: built a real priced `Boq`, wrote it, re-opened the
    .docx with `python-docx` and confirmed the table, the matched rate,
    and the GRAND TOTAL row all round-tripped correctly.

## 11. Prism's own offline measurement was wrong — first real-client-file bug, and the process for the next one

Noted 2026-10-22, from the owner, testing a real HVAC drawing end to end
(`HVAC_BOQ_TEST`, outside this repo: `hvac_sample.dxf`). **Done
(2026-10-22) — the bug, the fix, and the process for every future one.**

**What the owner actually found:** made a BOQ the normal way (measured
figures only, no drawing sent). Separately, out of curiosity, gave the
real drawing directly to an AI and got a second BOQ. Compared the two —
the AI's version was more accurate, and by a lot. Checked myself, directly
against the real file (not by trusting either generated document): Prism's
own offline measurement said the supply duct was **78.82 m**. It is
actually **38.80 m** — confirmed independently. Opened the raw DXF entity
by entity and found the exact cause: the duct is drawn as two parallel
lines 800mm apart (completely normal, professional HVAC drafting
practice), and `core.boq.measure()` was summing every line on the layer —
both edges counted as if they were two separate ducts.

**The uncomfortable part, said plainly:** the only reason the AI-written
version was right is that the real drawing left Prism's offline, "no AI
ever sees it" path. That is exactly the gap this fix closes — teaching
the *offline* measurer the convention, so the drawing never has to leave
the machine to get a correct number.

**The owner's instruction, which sets how every future one of these gets
handled:** don't call it "a suspicious layer" and stop there — that's not
a real fix. Teach Prism's code the actual rule, write the rule down
somewhere durable, and when a client brings more test files and more bugs
turn up, work through the same loop every time: find it, understand the
real drawing convention behind it, fix the measuring code itself, write
the rule down, test it so it can't come back.

**What shipped:**
  - **`prism_terminal/core/boq.py`: `_collapse_duct_pairs()`.** Before
    summing a layer's LINE lengths, looks for pairs that are roughly
    parallel, roughly the same length, and a small constant perpendicular
    distance apart (a run's own width) — treats a matched pair as ONE
    run's two edges, not two, and drops the short stub that closes a
    paired run's open end (not route length). Anything that doesn't match
    is measured exactly as it always was — this only ever acts on a
    genuine double-line pair, never an ordinary single-line run.
  - **A visible note, not a silent correction** — `measure()`'s existing
    `notes` list gets an entry naming the layer and how many pairs were
    read this way, "verify before pricing." The inference is real and the
    fix is real, but it is still an inference, not a raw measurement, and
    the module's whole promise is that nothing here is silently trusted.
  - **A real false positive caught and fixed before shipping, not after**
    — the first version (offset < 0.6 × length) nearly read a 24 m × 14 m
    room's opposite walls as one 24 m duct (ratio 0.58, close to every
    real duct pair's own ratio). Tightened to 0.5, confirmed against both
    the real duct geometry and a synthetic room, documented as the known
    edge of the current rule, not quietly tuned away and forgotten.
  - **`prism_terminal/core/HVAC_DRAWING_RULES.md`** (new) — the rule book
    the owner asked for. Rule 1 is this bug, in full: the convention, what
    broke, exactly what the fix does, and — importantly — what it does
    NOT yet handle (LWPOLYLINE double-lines, two genuinely separate runs
    accidentally sharing one layer, a tapering reducer's true centreline).
    Above rule 1, a numbered **process** section: get the client's real
    file and an independent ground truth, compare line by line, read the
    raw DXF coordinates rather than guessing from the symptom, name the
    general drawing CONVENTION responsible (not the one file), fix the
    measuring code itself, write the rule down in this same shape, add a
    synthetic regression test built from the real geometry (never the
    client's actual file kept in the repo), and re-run every rule's tests
    together before shipping the next one. `core/boq.py`'s own module
    docstring now points here.
  - 5 new tests, `tests/test_double_line_ducts.py`: a simple two-edge
    duct; the real client geometry reconstructed synthetically (pinned to
    within 100mm of the AI's own independent 38.80 m reading, nowhere
    near the old 78.82 m); an ordinary single-line run, untouched; two
    separate same-length parallel pipes on two different layers, both
    kept at their own full length; and the room-walls false positive
    that was caught and fixed, now locked in as a permanent regression
    guard. 130/130 across the full BOQ+BOM+site-facts sweep.
  - Checked which other add-ons this core-engine change could reach
    before calling it safe: only `addons/boq/dialog.py` and `addons/boq/
    measured.py` call `core.boq` at all — Gerber, STEP and every other
    add-on measure through their own, separate engines, untouched.

## 12. Item 7's real fix, and HVAC_DRAWING_RULES.md gated to HVAC requests only

Noted 2026-10-22/23, from the owner. **Done.**

### 12a. The real "opens a fresh tab" fix (item 7 was incomplete)

The owner tested item 7 directly: "Make with drawing," then a follow-up
on top of it, still opened a fresh browser tab — and the same thing
happened following up after "Make my BOQ". Item 7's write-up had been
marked "Done" without actually tracing where a browser tab comes from;
it fixed Prism's own small progress popup, which was real, but not what
"opens a new tab" meant.

**What was actually wrong:** the engine already has a working mechanism
for this — `resume_urls`, a `{stage: chat_url}` dict passed into
`AutomationWorker`/`core.automation.run()` that makes it navigate back to
an existing conversation instead of opening a fresh tab
(`_open_agent_page` checks it before deciding whether to open a new one
at all). `addons/step/dialog.py`'s own follow-up handler already uses it.
`addons/boq/dialog.py` simply never called it on any follow-up.

What shipped:
  - **`addons/boq/dialog.py`**: `self._last_agent` / `self._last_link` —
    who answered most recently, and that exact chat's own URL — updated
    at the end of every completed stage (`_on_written` for the first
    write-up, `_on_followed_up` for every follow-up/recheck after it, so
    a third follow-up resumes the SECOND one's chat, not the very first).
  - **`_fu_start_next`** builds `resume_urls = {self._fu_stage:
    self._last_link} if tool == self._last_agent and self._last_link else
    None` before constructing the `AutomationWorker`. Guarded on the SAME
    agent answering again — a different agent, or a mid-chain fallback to
    one, correctly resumes nothing (no chat of that other tool's exists),
    the same check `addons/step/dialog.py`'s `_on_answer_followup` makes.
  - Groq's branch is untouched — no browser page, so `self._last_link`
    stays empty whenever Groq last answered, and resume never triggers
    for it, with no special-casing needed.
  - 6 new tests,
    `tests/test_boq_dialog.py::AFollowUpResumesTheSameChatInsteadOfOpeningAFreshOne`.
  - **Said plainly:** the first pass at item 7 was reported "Done" without
    tracing the actual mechanism that opens a browser tab. This one is
    verified against that real mechanism, not just against Prism's own
    popup.

### 12b. HVAC_DRAWING_RULES.md gated — only when the request says "HVAC"

The owner's instruction, once item 11's fix was shipped: these rules are
trade-specific, verified against real HVAC drawings specifically, and
must never quietly start reading an electrical, plumbing or civil
drawing's lines differently too just because the geometry happens to
look similar. Going forward, more test folders will come in, each may
surface its own bug, and each fix gets taught into the code and written
into the rule book the same way rule 1 was (see HVAC_DRAWING_RULES.md's
own process section) — but the rules only ever engage when the person's
own request actually names HVAC. Nothing here is guessed from the
drawing's layer names or file name.

What shipped:
  - **`prism_terminal/core/boq.py`**: `measure(dxf_path, hvac=False)` —
    a new parameter. `_collapse_duct_pairs` (rule 1) only runs when
    `hvac=True`; otherwise every layer is measured exactly as it was
    before rule 1 ever existed — the plain sum, double-counted duct and
    all. The module docstring and `HVAC_DRAWING_RULES.md` both say so.
  - **`workers.py`**: `MeasureWorker` takes `hvac: bool = False` and
    passes it straight through to `boq.measure`.
  - **`addons/boq/dialog.py:_measure()`** decides `hvac` by checking
    `"hvac" in self.ask.text().lower()` — the person's own request text,
    read live off the ask box (not `self.request`, which isn't set until
    "Make" is pressed, well after measuring already ran). Typing "HVAC"
    anywhere in the request turns the rules on for that run; nothing
    else does. **Known limitation, stated plainly:** if the drawing is
    attached before "HVAC" is typed into the box, measuring has already
    run without the flag — type HVAC into the request before or
    alongside attaching the drawing.
  - **The audit-trail gap from item 11 is also closed here**: rule 1's
    own note (`q["notes"]`) was being computed but never actually shown
    anywhere — `_on_measured` only ever read the DXF *converter's* notes
    (a different list, `MeasureWorker.done`'s second value), never
    `q.get("notes")`. Both are now joined into the same line the person
    already sees under "Measured from your drawing" (`self.csv_label`),
    and `write_quantities_csv` now appends each note as its own `note`
    row in the exported CSV too, so it survives being emailed or filed
    away, not only shown once in the live app.
  - 7 new tests: `tests/test_double_line_ducts.py::
    TheRuleOnlyAppliesWhenHvacIsAskedFor` (hvac=False keeps the old,
    un-collapsed reading; hvac=True applies the rule) +
    `tests/test_boq_dialog.py::TheHvacFlagComesOnlyFromTheAskBox` (the
    word "HVAC" turns it on, case-insensitively; a different trade or no
    text yet leaves it off). The existing double-line-duct tests were
    updated to pass `hvac=True` explicitly, since they test the rule
    itself and must still exercise it now that it is opt-in.
  - Full BOQ+BOM+site-facts sweep green throughout (142 at last count);
    full project suite + `PRISM_SELFTEST` run before this push.

**Where to actually check this in the Prism UI, for the owner:**
  1. Attach the drawing with "HVAC" somewhere in the request text box.
  2. Once measured, open **"Measured from your drawing"** — the table
     shows the corrected length per layer directly (e.g. the supply duct
     reading ~38.3 m, not ~78.8 m).
  3. Just below the table, the green **"Saved so you can check every
     number →"** line now also shows the audit note when a rule fired —
     "M-DUCT-SUPPLY: read N pair(s) of lines as one run's two edges... —
     verify before pricing" — directly under that line, in amber/⚠ style.
  4. The exported CSV at that same path (openable in Excel) has the same
     numbers in rows, plus a `note` row for each one a rule touched.
  5. To see the difference for yourself: leave "HVAC" out of the request
     text for the same drawing and measure again — the duct layer reads
     the old, doubled number instead, with no note — proving the gate
     itself, not just the fix.
