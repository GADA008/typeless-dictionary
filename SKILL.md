---
name: typeless-dictionary
description: Manage Typeless voice input dictionary — export words from one account and import into another. Use when asked to add words to Typeless, export/backup Typeless dictionary, migrate dictionary between Typeless accounts, or manage custom vocabulary for voice input. Triggers on "Typeless dictionary", "add words to Typeless", "export Typeless words", "voice input dictionary".
---

# Typeless Dictionary Manager

Export and import custom dictionary words for the Typeless voice input app on macOS.

## Prerequisites

- **Typeless.app** installed and running
- **Accessibility**: Terminal/IDE added to System Settings → Privacy & Security → Accessibility
- **Export only**: `pip3 install websocket-client`

## Export

Extract words via Electron DevTools (CDP). Auto-restart recommended:

```bash
python3 scripts/export_dictionary.py --start-typeless --output words.json
python3 scripts/export_dictionary.py --output words.json          # Typeless already running with debug
python3 scripts/export_dictionary.py --start-typeless --format txt --output words.txt
```

Fallback (no DevTools, viewport only):

```bash
osascript -e 'tell application "System Events" to tell process "Typeless" to tell window "Hub" to return value of every static text of entire contents'
```

## Import

```bash
python3 scripts/import_dictionary.py words.json              # from file
python3 scripts/import_dictionary.py words.txt               # plain text
python3 scripts/import_dictionary.py --words "Claude" "明子玉" # inline
python3 scripts/import_dictionary.py words.json --dry-run     # preview
python3 scripts/import_dictionary.py words.json --resume      # resume interrupted
python3 scripts/import_dictionary.py words.json --verify      # verify after import
```

Progress saved to `/tmp/typeless_import_progress.json`. Use `--resume` to skip completed words.

## ⚠️ Three Critical Rules (Import)

Violating any of these causes silent data corruption.

**1. Never use `keystroke` for non-ASCII.** Chinese/Unicode → garbage output. Always clipboard-paste:

```applescript
-- WRONG: keystroke "新世纪" → outputs "aaa"
-- RIGHT:
set the clipboard to theWord
keystroke "v" using command down
```

**2. Always clear input before paste.** Rejected words leave old text in modal. Next paste appends → merge bug (`BAO` + `MemoRy` → `BAOMemoRy`):

```applescript
keystroke "a" using command down  -- select all
key code 51                       -- delete
```

**3. Check modal state after submit.** Modal still open after Enter = word rejected. Dismiss before proceeding:

```applescript
key code 53  -- Escape to close error/duplicate modal
```

## Account Migration

1. Log into source account → `python3 scripts/export_dictionary.py -s -o source.json`
2. Log out, log into target account
3. `python3 scripts/import_dictionary.py source.json --verify`

Typeless Hub must be visible and in foreground during both phases.
