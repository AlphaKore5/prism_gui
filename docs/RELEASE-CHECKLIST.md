# Release checklist

Why this exists: 1.6.2 and 1.6.3 shipped two stale copies of
`addons/inquiry/dialog.py` and `quotation.py` that silently overwrote the
pipeline-board work. The Email inquiries screen crashed on open, and colours,
multi-delete and PDF quotations were gone. CI was already red on all three
platforms, and nothing in the process looked at what had *disappeared* between
two releases. Every step below closes one of those gaps.

Run the automatic part first:

```bash
python3 devtools/prerelease_check.py --suite
```

It must end with `Automatic checks pass`. Then do the manual list, then publish.

## Rules

1. **Nobody publishes while a check is red.** Not "it was red before": add a known
   failure to `devtools/prerelease_known_failures.txt` with the reason, or fix it.
2. **A release commit touches only the release.** Version bump, `CHANGES.md`, and the
   work the release is for. Never copy a whole working tree onto it. Check
   `git diff --stat origin/main` before committing and read every file that is not yours.
3. **Pull by rebase, then diff.** After pulling a teammate's work, run
   `python3 devtools/prerelease_check.py` — check 3 lists every function, class and
   test that shipped in the last release and is gone now. A deliberate removal goes in
   `devtools/prerelease_removed_ok.txt` with the reason in a comment.
4. **Engine first.** Push `prism_terminal`, then `prism_gui` with the bumped gitlink.
   Check 1 fails if the engine commit is not on the engine's `origin/main`.
5. **Two people, one release.** The person cutting the release runs this on a clean
   clone of `origin/main`, not on a working copy that may hold unpushed local files.

## Automatic (devtools/prerelease_check.py)

| # | Check | What it catches |
|---|---|---|
| 1 | git | dirty tree, behind origin, engine commit not pushed |
| 2 | version | forgot to bump, no `CHANGES.md` entry |
| 3 | removed | anything that shipped last release and has vanished (the 1.6.2 overwrite) |
| 4 | contract | `enter()` called with a keyword it does not take (the 1.6.2 crash); Speak unwired |
| 5 | selftest | `PRISM_SELFTEST=1` offscreen |
| 6 | suite | a new failing test, or a test file whose process dies (segfault/abort) |

## Manual, on the built app, Windows and macOS first

Linux results prove nothing for customers. Use the *packaged* build, not source.

- [ ] Main task: type a task, Make a plan, Start the work reaches a result
- [ ] Main task: Speak, talk, Stop — the words land in the task box
- [ ] Email inquiries opens; Pipeline, Client file and All mail switch
- [ ] Check my mail now (test mailbox) finishes; newest inquiry is first
- [ ] Prepare a quotation → PDF with the ₹ glyph → Send to yourself arrives
- [ ] Revised quotation attaches Rev 2; They countered / Hold the price move the card
- [ ] Delete several rows with ctrl-click (cmd-click on a Mac)
- [ ] Save as Excel opens in Excel with colours and ₹
- [ ] Lumi button visible, drags, opens, remembers its place
- [ ] Settings → Check for updates offers the new version and Update installs it
- [ ] 125% and 150% scaling: board, drawer and dialogs not clipped

## Publishing (see RELEASING-UPDATES.md)

1. Tag; wait for CI to build all three platforms.
2. `devtools/release_all.py v<ver> <run-id>` with the offline signing key.
3. Verify per platform: signed manifest present, every update file uploaded.
4. Set Render `LATEST_CLIENT_VERSION`.
5. Update an older install from the app and confirm it starts on the new version.
