#!/usr/bin/env python3
"""
Export Typeless dictionary words via Electron DevTools.

Prerequisites:
    pip3 install websocket-client

Usage:
    python3 export_dictionary.py [--output words.json] [--start-typeless]

--start-typeless: automatically kill and restart Typeless with debug flags.
"""

import json
import time
import urllib.request
import argparse
import subprocess
import sys
import os

try:
    import websocket
except ImportError:
    print("ERROR: pip3 install websocket-client")
    sys.exit(1)

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
WS_TIMEOUT = 10  # WebSocket 接收超时（秒）

_msg_id = 0


def _next_id():
    """递增 CDP 消息 ID，避免与异步事件混淆。"""
    global _msg_id
    _msg_id += 1
    return _msg_id


def start_typeless_with_debug():
    """Kill Typeless and restart with remote debugging enabled."""
    print("Restarting Typeless with remote debugging...")
    subprocess.run(['killall', 'Typeless'], capture_output=True)
    time.sleep(1.5)
    subprocess.Popen(
        ['/Applications/Typeless.app/Contents/MacOS/Typeless',
         f'--remote-debugging-port={CDP_PORT}',
         '--remote-allow-origins=*'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # Wait for CDP to be ready
    for i in range(15):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"{CDP_URL}/json/list", timeout=2)
            print("Typeless ready.")
            return True
        except Exception:
            pass
    print("ERROR: Typeless did not start with remote debugging.")
    return False


def get_hub_ws_url():
    """Find the Hub page WebSocket debugger URL."""
    try:
        pages = json.loads(urllib.request.urlopen(f"{CDP_URL}/json/list", timeout=5).read())
    except Exception:
        return None
    for p in pages:
        if 'Hub' in p.get('title', ''):
            return p['webSocketDebuggerUrl']
    return None


def evaluate(ws, expr, timeout=WS_TIMEOUT):
    """Evaluate JavaScript in the Hub page and return result."""
    msg_id = _next_id()
    ws.send(json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True}
    }))
    old_timeout = ws.timeout
    ws.timeout = timeout
    try:
        result = json.loads(ws.recv())
    except Exception as e:
        return f"RECV_ERROR: {e}"
    finally:
        ws.timeout = old_timeout
    try:
        val = result.get('result', {}).get('result', {}).get('value')
        if val is None:
            desc = result.get('result', {}).get('result', {}).get('description', '')
            exc = result.get('result', {}).get('exceptionDetails', {})
            if exc:
                return f"JS_ERROR: {exc.get('text', '')}"
            return desc
        return val
    except (AttributeError, TypeError):
        return f"PARSE_ERROR: {result}"


def get_account_info(ws):
    """Try to get current Typeless account email."""
    return evaluate(ws, """
    (() => {
        try {
            const store = JSON.parse(localStorage.getItem('app-storage') || '{}');
            return store?.userData?.email || 'unknown';
        } catch { return 'unknown'; }
    })();
    """)


def navigate_to_dictionary(ws):
    """Click Dictionary in the sidebar."""
    evaluate(ws, """
        document.querySelectorAll('button').forEach(b => {
            if (b.textContent.trim() === 'Dictionary') b.click();
        }); 'ok';
    """)
    time.sleep(1.5)


def collect_words_from_dom(ws):
    """Collect visible dictionary words from the DOM.

    使用精准 DOM 定位：只在滚动容器内采集，按元素类型过滤 UI 文本。
    避免全页面 skip set 误杀合法词条（如 "All", "Edit", "Home"）。
    """
    result = evaluate(ws, """
    (() => {
        // 定位词典列表的滚动容器（与 export_words 滚动逻辑一致）
        let container = null;
        document.querySelectorAll('div').forEach(d => {
            if (d.scrollHeight > d.clientHeight && d.clientHeight > 100
                && d.scrollHeight > 300) {
                container = d;
            }
        });
        if (!container) container = document.body;

        // 词条旁的元数据标签（非用户词汇，是 UI 显示的分类标签）
        const metaLabels = new Set(['Added manually', 'Auto-added', 'Manually-added']);

        const words = new Set();
        const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
        while (walker.nextNode()) {
            const node = walker.currentNode;
            const t = node.textContent.trim();
            if (!t || t.length === 0 || t.length > 200) continue;
            // 跳过按钮内的文本（Edit, Delete, New word 等交互元素）
            const el = node.parentElement;
            if (el && (el.tagName === 'BUTTON' || el.closest('button'))) continue;
            // 跳过词条元数据标签
            if (metaLabels.has(t)) continue;
            words.add(t);
        }
        return JSON.stringify([...words]);
    })();
    """)
    if not result or not isinstance(result, str):
        return set()
    if result.startswith(('JS_ERROR', 'RECV_ERROR', 'PARSE_ERROR', 'TIMEOUT')):
        return set()
    try:
        return set(json.loads(result))
    except (json.JSONDecodeError, TypeError):
        return set()


def export_words(ws):
    """Scroll through the dictionary list to collect all words."""
    navigate_to_dictionary(ws)

    all_words = set()

    # Scroll in small increments to catch all virtualized items
    prev_count = -1
    no_change_count = 0

    for scroll_pos in range(0, 50000, 200):
        evaluate(ws, f"""
            document.querySelectorAll('div').forEach(d => {{
                if (d.scrollHeight > d.clientHeight && d.clientHeight > 100
                    && d.scrollHeight > 300) {{
                    d.scrollTop = {scroll_pos};
                }}
            }}); 'ok';
        """)
        time.sleep(0.2)

        visible = collect_words_from_dom(ws)
        all_words.update(visible)

        if len(all_words) == prev_count:
            no_change_count += 1
            if no_change_count >= 5:
                break  # No new words after 5 scroll steps
        else:
            no_change_count = 0
        prev_count = len(all_words)

    # Also scroll back to top to catch any items only rendered at top
    evaluate(ws, """
        document.querySelectorAll('div').forEach(d => {
            if (d.scrollHeight > d.clientHeight && d.clientHeight > 100) d.scrollTop = 0;
        }); 'ok';
    """)
    time.sleep(0.3)
    all_words.update(collect_words_from_dom(ws))

    return sorted(all_words)


def main():
    parser = argparse.ArgumentParser(description='Export Typeless dictionary')
    parser.add_argument('--output', '-o', default='typeless_dictionary.json',
                        help='Output file (default: typeless_dictionary.json)')
    parser.add_argument('--format', '-f', choices=['json', 'txt'], default='json')
    parser.add_argument('--start-typeless', '-s', action='store_true',
                        help='Auto-restart Typeless with remote debugging')
    args = parser.parse_args()

    # Start Typeless with debug if requested
    if args.start_typeless:
        if not start_typeless_with_debug():
            sys.exit(1)
        time.sleep(2)

    # Connect
    ws_url = get_hub_ws_url()
    if not ws_url:
        print("ERROR: Cannot connect to Typeless Hub.")
        print("Run with --start-typeless or manually start:")
        print(f"  /Applications/Typeless.app/Contents/MacOS/Typeless --remote-debugging-port={CDP_PORT} '--remote-allow-origins=*' &")
        sys.exit(1)

    print("Connecting to Typeless Hub...")
    ws = websocket.create_connection(ws_url)

    try:
        account = get_account_info(ws)
        print(f"Account: {account}")

        words = export_words(ws)
        print(f"Exported {len(words)} words")

        output_data = {
            "account": account,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "count": len(words),
            "words": words
        }

        out_path = args.output
        if args.format == 'json':
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
        else:
            # 确保 txt 格式使用正确的文件扩展名
            if out_path.endswith('.json'):
                out_path = out_path[:-5] + '.txt'
            elif not out_path.endswith('.txt'):
                out_path += '.txt'
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(f"# Typeless Dictionary Export — {account}\n")
                f.write(f"# {time.strftime('%Y-%m-%d %H:%M')}\n\n")
                f.write('\n'.join(words))

        print(f"Saved to {out_path}")
        for w in words:
            print(f"  {w}")
    finally:
        ws.close()


if __name__ == '__main__':
    main()
