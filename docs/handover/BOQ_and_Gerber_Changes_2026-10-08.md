# BOQ add-on and Gerber Anonymizer — changes, 2026-10-03 to 2026-10-08

What landed in this round of work, for anyone picking this up cold.

---

## 1 · Gerber Anonymizer — drill holes appearing on a job with no drill

**Reported by:** Rishabh, over WhatsApp — "mai toh auto drill generate kar raha
hai khud se" / "jaha drill nahi hai wala v drill kardiya" (it's auto-generating
drill, even where there is none).

**Files:** `prism_terminal/core/gerber.py` (the engine — also used by the main
app's own Gerber measurement, not just the anonymizer), synced into
`devtools/gerber_anonymizer_package/core/gerber.py` and
`devtools/GerberAnonymizer_Package.zip`.

**Root cause:** `_sniff()`'s content-detection for Excellon drill files had
two regexes meant to catch a drill file missing its `M48` header. Neither
required the `%` marker every real Excellon file has, header or not. So an
unrelated plain-text file — a BOM note, a dimension/panel-drawing legend,
anything with a line that merely looks like a tool definition (`T1C.031`)
plus a line starting with `X` — got misclassified as a drill file. With no
`%` to find the real body, the parser fell back to scanning the file's whole
content for hit lines, and a stray dimension note like `X12.500Y8.300` was
counted as a drilled hole.

**Fix:** both sniff checks now also require `%` to be present in the file —
closes the gap without touching the legitimate "no-M48-header" case the
loose check was built for.

**Verified:** reproduced the bug first (stashed the fix inside the
`prism_terminal` submodule's own repo, confirmed the new tests fail with
exactly this symptom, restored the fix, confirmed they pass). Two new
regression tests in `tests/test_gerber.py`
(`DrillsSurviveBothFormatsTheyArriveIn` and `TheOverloadedTxtExtension`).
Full `test_gerber.py` suite clean. Rebuilt the anonymizer zip after catching
and fixing a packaging mistake of my own (a stray duplicate zip entry from a
bad `zip -q` invocation).

**Not yet done:** Rishabh hasn't confirmed the fix against his own job yet.

---

## 2 · BOQ add-on — three related changes

**File:** `addons/boq/dialog.py` unless noted.

### a) The write-up AI gets the priced CSV, as reference only

At "Make my BOQ", the writer AI (Claude, Kimi, …) now also receives the
priced grid as it stands — a CSV — alongside the usual templates/notes. If
nothing is priced yet, it gets the measured-quantities CSV instead. The
drawing itself is still never attached to this stage (unchanged rule, see
`TheDrawingNeverReachesAnAI` in `tests/test_boq_dialog.py`).

The prompt explicitly marks it **REFERENCE ONLY**: the AI is told not to
recompute totals or change any quantity, and that the offline workbook is
the firm's record, not its own write-up.

Bug found and fixed along the way: the first version built the reference as
a bare `{path, name}` dict. The automation layer expects the full attachment
record `CB.files.attach()` builds (it reads `size` off it), so the stage
crashed *before sending the prompt* — the symptom reported was "it gave
Claude the file, but not the prompt." Fixed by using `CB.files.attach()`
like every other attachment.

### b) "Recheck with the drawing" — explicit consent before the drawing ever leaves

A new footer button, enabled once there is an answer and a drawing is
attached. Clicking it pops a confirmation — *"You are now permitting
`<file>` to be sent to `<agent>` so it can recheck the measured quantities.
The drawing file leaves this computer. Continue?"* — default **No**. Only on
**Yes** does the writer AI receive the drawing, the measured figures and the
previous answer, and return a corrected table in the same result box.

This is the one deliberate exception to the "drawing never reaches an AI"
rule, and it is opt-in per press, every time.

### c) Post-completion follow-up — same popup Prism core uses everywhere else

The BOQ screen now opens `dialogs/followup_dialog.py`'s `FollowupDialog`
(the "Anything to change?" window) right after a write-up, instead of the
main window offering it silently after the dialog closes.

- Shows the answer and the saved CSV as a deliverable.
- A one-click **"Verify and remake"** button (only shown when a drawing is
  attached) — fills in a ready-made prompt, still asks the same drawing
  consent, then reruns with the drawing.
- A typed follow-up sends only the files the user adds themselves in that
  popup — never the drawing.
- Loops: the popup reopens after each answer, until "No, I'm done".

`dialogs/followup_dialog.py` gained one new, optional constructor parameter,
`quick_actions` — a list of one-click prompt buttons. Core behaviour is
unchanged when it isn't passed, so nothing else using `FollowupDialog`
changed.

`main_window.py`'s own post-dialog follow-up bridge
(`_offer_followup_for_dialog`) is now skipped for BOQ and BOM
(`BoqDialog.owns_followup = True`), so the window isn't offered twice.

**Verified:** 86 tests passing across `tests/test_boq_dialog.py`,
`tests/test_boq_file_guardrail.py`, `tests/test_boq_pricing.py`,
`tests/test_followup_session.py`, `tests/test_followup_plan.py`. New tests
cover: the priced CSV is sent and the drawing is not (for a normal run); the
reference attachment has the fields the automation layer needs; the
follow-up popup offers "Verify and remake" only when a drawing is attached;
saying No sends nothing; Yes sends the drawing with the measured figures; a
typed follow-up sends only the user's own files.

**Not yet done:** none of this has been run against a live Claude / Kimi /
Perplexity session — only unit-tested with a mocked `AutomationWorker`. The
priced grid's units look suspect in a screenshot the owner shared (every row
labelled "unit", one at 637,521.16) — flagged, not investigated.

---

## 3 · Housekeeping

- `lang/_catalogue.json` regenerated via `devtools/extract_strings.py` — 38
  strings added (all from this round's inquiry + BOQ work), **0 removed**
  (checked key-by-key, not just by eye).
- App selftest (`QT_QPA_PLATFORM=offscreen PRISM_SELFTEST=1 python3
  main.py`) passes.

### My own mistake, caught and fixed mid-session

A `git stash` command meant to scope to `prism_terminal/core/gerber.py` was
run from the wrong directory, and — because the intended stash push silently
matched nothing — the following `git stash pop` instead popped the owner's
own pre-existing `stash@{0}` ("Rounds 47-52 in-progress app work before
pulling Lumi/packaging release"). That pop conflicted on
`lang/_catalogue.json` and left Git conflict markers in it, which later
broke `extract_strings.py`. Fixed by restoring that one generated file to
`HEAD` and regenerating it. `stash@{0}` is still intact and un-dropped — it
was never lost, just applied where it shouldn't have been. All later stash
operations this session were scoped correctly (verified against the right
repo before running).

---

## Known, not fixed

- `tests/test_gates.py` has 6 pre-existing failures (confirmed unrelated to
  this round's changes — they fail identically against the committed BOQ
  dialog) in the main window's reel/plan flow. The test also leaks the
  owner's real `~/.prism` config — including the mail password and API key
  — into its failure output, which is a test-isolation bug worth fixing on
  its own.
- The inquiry-automation items from the earlier 17-item list — see
  `docs/handover/Email_Inquiry_Changes_Tracker.md` for that work, tracked
  separately.
