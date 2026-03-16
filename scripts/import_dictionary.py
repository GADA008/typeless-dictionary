#!/usr/bin/env python3
"""
Import words into Typeless dictionary via macOS Accessibility + clipboard paste.

Supports Chinese, emoji, and all Unicode characters.
Handles duplicates and errors gracefully.
Supports resumable imports via progress file.

Prerequisites:
    - Typeless app running (Hub window open)
    - osascript accessibility permission for Terminal/node
    - pbcopy (macOS built-in)

Usage:
    python3 import_dictionary.py words.json
    python3 import_dictionary.py words.txt
    python3 import_dictionary.py --words "word1" "word2" "新世纪福音战士"
    python3 import_dictionary.py words.json --dry-run
    python3 import_dictionary.py words.json --resume   # skip already-added words
    python3 import_dictionary.py words.json --verify    # verify after import
"""

import subprocess
import time
import json
import argparse
import sys
import os

PROGRESS_FILE = "/tmp/typeless_import_progress.json"


def osascript(script):
    """Run AppleScript and return stdout."""
    r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=20)
    return r.stdout.strip()


def ensure_dictionary_page():
    """Open Typeless Hub on Dictionary page. Returns True on success."""
    result = osascript('''
    tell application "System Events"
        if not (exists process "Typeless") then
            return "NOT_RUNNING"
        end if
        tell process "Typeless"
            set frontmost to true
            delay 0.3
            if not (exists window "Hub") then
                return "NO_HUB"
            end if
            tell window "Hub"
                set allElements to entire contents
                repeat with elem in allElements
                    try
                        if class of elem is button and name of elem is "Dictionary" then
                            click elem
                            delay 0.8
                            return "OK"
                        end if
                    end try
                end repeat
            end tell
            return "NO_DICT_BTN"
        end tell
    end tell
    ''')
    if result != "OK":
        print(f"ERROR: {result}")
        if result == "NOT_RUNNING":
            print("Start Typeless first: open -a Typeless")
        elif result == "NO_HUB":
            print("Open Typeless Hub window (click the menu bar icon → Hub)")
        sys.exit(1)
    return True


def check_modal_state():
    """Check if an 'Add to dictionary' modal is currently open."""
    result = osascript('''
    tell application "System Events"
        tell process "Typeless"
            tell window "Hub"
                set allElements to entire contents
                repeat with elem in allElements
                    try
                        if class of elem is static text and value of elem is "Add to dictionary" then
                            return "MODAL_OPEN"
                        end if
                    end try
                end repeat
                return "NO_MODAL"
            end tell
        end tell
    end tell
    ''')
    return result


def dismiss_modal():
    """Close modal if open (press Escape)."""
    if check_modal_state() == "MODAL_OPEN":
        osascript('''
        tell application "System Events"
            tell process "Typeless"
                key code 53 -- Escape
                delay 0.3
            end tell
        end tell
        ''')
        time.sleep(0.3)


def add_word(word):
    """
    Add a single word to Typeless dictionary.
    
    Uses pbcopy + Cmd+V for full Unicode support.
    Checks modal state before and after to handle errors.
    """
    # Dismiss any leftover modal from previous failed add
    dismiss_modal()

    # Set clipboard
    proc = subprocess.run(['pbcopy'], input=word.encode('utf-8'), capture_output=True, timeout=5)
    if proc.returncode != 0:
        return "CLIPBOARD_ERROR"

    result = osascript('''
    tell application "System Events"
        tell process "Typeless"
            set frontmost to true
            delay 0.1
            
            tell window "Hub"
                -- Click "New word" button
                set found to false
                set allElements to entire contents
                repeat with elem in allElements
                    try
                        if class of elem is button and name of elem is "New word" then
                            click elem
                            set found to true
                            exit repeat
                        end if
                    end try
                end repeat
                if not found then return "NO_NEW_WORD_BTN"
            end tell
            
            delay 0.4
            
            -- Clear input field (critical: prevents merge with previous rejected word)
            keystroke "a" using command down
            delay 0.05
            key code 51
            delay 0.1
            
            -- Paste from clipboard (supports Chinese/Unicode)
            keystroke "v" using command down
            delay 0.3
            
            -- Submit
            keystroke return
            delay 0.7
            
            return "OK"
        end tell
    end tell
    ''')

    # Verify modal closed (if still open, the word was rejected — likely duplicate)
    modal = check_modal_state()
    if modal == "MODAL_OPEN":
        dismiss_modal()
        return "DUPLICATE_OR_ERROR"

    return result


def load_words(source):
    """Load words from JSON file, text file, or list."""
    if isinstance(source, list):
        return source

    with open(source, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    # Try JSON
    try:
        data = json.loads(content)
        if isinstance(data, dict) and 'words' in data:
            return data['words']
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Line-separated text (skip comments and empty lines)
    return [line.strip() for line in content.split('\n')
            if line.strip() and not line.strip().startswith('#')]


def load_progress():
    """Load set of already-imported words from progress file."""
    if not os.path.exists(PROGRESS_FILE):
        return set()
    with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return set(data.get('imported', []))


def save_progress(imported_words):
    """Save progress for resumable imports."""
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            "imported": sorted(imported_words),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "count": len(imported_words)
        }, f, ensure_ascii=False, indent=2)


def verify_import(expected_words):
    """
    Verify words exist in dictionary by searching.
    Requires Typeless running with DevTools (port 9222).
    Returns (found, missing) sets.
    """
    try:
        import urllib.request
        import websocket as ws_mod
        pages = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=3).read())
        ws_url = None
        for p in pages:
            if 'Hub' in p.get('title', ''):
                ws_url = p['webSocketDebuggerUrl']
                break
        if not ws_url:
            print("  Verification skipped: no DevTools connection")
            return None, None

        ws = ws_mod.create_connection(ws_url, timeout=10)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {
            "expression": """
                document.querySelectorAll('button').forEach(b => {
                    if (b.textContent.trim() === 'Dictionary') b.click();
                }); 'ok';
            """, "returnByValue": True
        }}))
        ws.recv()
        time.sleep(1)

        # Collect all visible words
        ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {
            "expression": """
            (() => {
                const words = new Set();
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                while (walker.nextNode()) {
                    const t = walker.currentNode.textContent.trim();
                    if (t && t.length > 0 && t.length < 200) words.add(t);
                }
                return JSON.stringify([...words]);
            })();
            """, "returnByValue": True
        }}))
        raw = json.loads(ws.recv())
        # 安全解析 CDP 响应，防止意外结构导致崩溃
        try:
            visible = set(json.loads(raw['result']['result']['value']))
        except (KeyError, TypeError, json.JSONDecodeError):
            print("  Verification failed: unexpected DevTools response")
            ws.close()
            return None, None
        ws.close()

        found = set(expected_words) & visible
        missing = set(expected_words) - visible
        return found, missing
    except Exception as e:
        print(f"  Verification error: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(description='Import words into Typeless dictionary')
    parser.add_argument('input', nargs='?', help='Input file (JSON or text)')
    parser.add_argument('--words', '-w', nargs='+', help='Words to add directly')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Preview without adding')
    parser.add_argument('--resume', '-r', action='store_true', help='Skip words from previous run')
    parser.add_argument('--verify', action='store_true', help='Verify after import (needs DevTools)')
    parser.add_argument('--delay', '-d', type=float, default=0.0, help='Extra delay between words')
    parser.add_argument('--clear-progress', action='store_true', help='Clear progress file')
    args = parser.parse_args()

    if args.clear_progress:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print("Progress cleared.")
        return

    if not args.input and not args.words:
        parser.print_help()
        sys.exit(1)

    # Load words
    words = args.words if args.words else load_words(args.input)

    # Deduplicate preserving order
    seen = set()
    unique = []
    for w in words:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    words = unique

    # Resume: skip already-imported words
    if args.resume:
        already = load_progress()
        before = len(words)
        words = [w for w in words if w not in already]
        print(f"Resume mode: {before - len(words)} already done, {len(words)} remaining")

    print(f"Words to import: {len(words)}")

    if args.dry_run:
        for w in words:
            print(f"  [DRY] {w}")
        return

    if not words:
        print("Nothing to import.")
        return

    # Ensure Dictionary page
    ensure_dictionary_page()
    time.sleep(0.5)

    # Import
    success = 0
    duplicates = 0
    errors = []
    imported = load_progress() if args.resume else set()

    for i, word in enumerate(words):
        result = add_word(word)
        if result == "OK":
            success += 1
            imported.add(word)
            print(f"[{i+1}/{len(words)}] ✅ {word}")
        elif result == "DUPLICATE_OR_ERROR":
            duplicates += 1
            imported.add(word)  # Mark as done even if duplicate
            print(f"[{i+1}/{len(words)}] ⏭️  {word} (duplicate/exists)")
        else:
            errors.append((word, result))
            print(f"[{i+1}/{len(words)}] ❌ {word} — {result}")

        # Save progress periodically
        if (i + 1) % 10 == 0:
            save_progress(imported)

        if args.delay > 0:
            time.sleep(args.delay)

    # Final progress save
    save_progress(imported)

    print(f"\nResults: {success} added, {duplicates} duplicates, {len(errors)} errors")
    if errors:
        print("Failed:")
        for w, e in errors:
            print(f"  {w}: {e}")

    # Verify
    if args.verify:
        print("\nVerifying...")
        found, missing = verify_import(list(imported))
        if found is not None:
            print(f"  Verified: {len(found)} found, {len(missing)} not visible (may be off-screen)")
            if missing and len(missing) <= 10:
                print(f"  Not visible: {sorted(missing)}")

    # Cleanup progress on full success
    if not errors and os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("Progress file cleaned up.")


if __name__ == '__main__':
    main()
