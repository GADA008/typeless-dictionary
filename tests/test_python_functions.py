#!/usr/bin/env python3
"""
测试 import_dictionary.py 和 export_dictionary.py 的 Python 功能。

覆盖：
1. load_words() — JSON dict/array、文本文件、内联列表
2. save_progress() / load_progress() — 进度持久化
3. Unicode 词条的 JSON 序列化/反序列化
4. collect_words_from_dom 返回值的错误处理
5. export 的 txt 输出路径逻辑
"""

import sys
import os
import json
import tempfile

# 将 scripts 目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from import_dictionary import load_words, load_progress, save_progress
import import_dictionary

passed = 0
failed = 0


def assert_eq(actual, expected, name):
    global passed, failed
    if actual == expected:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        print(f"     expected: {expected}")
        print(f"     actual:   {actual}")
        failed += 1


def assert_true(condition, name):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}")
        failed += 1


# ═══════════════════════════════════════
# 测试 1: load_words — JSON dict 格式
# ═══════════════════════════════════════
print("\n📋 Test 1: load_words — JSON dict 格式 (含 words 字段)")

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump({
        "account": "test@test.com",
        "count": 3,
        "words": ["Claude", "新世纪福音战士", "résumé"]
    }, f, ensure_ascii=False)
    f.flush()
    words = load_words(f.name)

assert_eq(words, ["Claude", "新世纪福音战士", "résumé"], "解析 JSON dict 中的 words 数组")
os.unlink(f.name)


# ═══════════════════════════════════════
# 测试 2: load_words — JSON array 格式
# ═══════════════════════════════════════
print("\n📋 Test 2: load_words — JSON array 格式")

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(["word1", "word2", "señor"], f, ensure_ascii=False)
    f.flush()
    words = load_words(f.name)

assert_eq(words, ["word1", "word2", "señor"], "解析 JSON 数组")
os.unlink(f.name)


# ═══════════════════════════════════════
# 测试 3: load_words — 纯文本格式
# ═══════════════════════════════════════
print("\n📋 Test 3: load_words — 纯文本格式 (行分隔，跳过注释)")

with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
    f.write("# This is a comment\n")
    f.write("Claude\n")
    f.write("\n")  # 空行
    f.write("新世紀エヴァンゲリオン\n")
    f.write("# Another comment\n")
    f.write("über\n")
    f.flush()
    words = load_words(f.name)

assert_eq(words, ["Claude", "新世紀エヴァンゲリオン", "über"], "解析文本文件，跳过注释和空行")
os.unlink(f.name)


# ═══════════════════════════════════════
# 测试 4: load_words — 内联列表
# ═══════════════════════════════════════
print("\n📋 Test 4: load_words — 内联列表")

words = load_words(["hello", "世界", "🎵"])
assert_eq(words, ["hello", "世界", "🎵"], "直接传入列表")


# ═══════════════════════════════════════
# 测试 5: 多语言 Unicode 词条完整性
# ═══════════════════════════════════════
print("\n📋 Test 5: 多语言 Unicode 词条 JSON 往返测试")

multi_lang = [
    "Claude",                    # 英文
    "新世纪福音战士",              # 中文
    "新世紀エヴァンゲリオン",       # 日语
    "résumé",                    # 法语
    "señor",                     # 西班牙语
    "über",                      # 德语
    "Привет",                    # 俄语
    "안녕하세요",                  # 韩语
    "مرحبا",                     # 阿拉伯语
    "🎵🎶",                      # Emoji
]

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump({"words": multi_lang}, f, ensure_ascii=False)
    f.flush()
    roundtrip = load_words(f.name)

assert_eq(roundtrip, multi_lang, "多语言词条 JSON 序列化/反序列化完全一致")
os.unlink(f.name)


# ═══════════════════════════════════════
# 测试 6: save_progress / load_progress
# ═══════════════════════════════════════
print("\n📋 Test 6: 进度保存与加载")

# 使用临时文件替代默认路径
orig_progress = import_dictionary.PROGRESS_FILE
test_progress = tempfile.mktemp(suffix='.json')
import_dictionary.PROGRESS_FILE = test_progress

try:
    # 初始状态：无进度文件
    assert_eq(load_progress(), set(), "无进度文件时返回空 set")

    # 保存进度
    test_imported = {"Claude", "新世纪福音战士", "résumé"}
    save_progress(test_imported)
    assert_true(os.path.exists(test_progress), "进度文件已创建")

    # 加载进度
    loaded = load_progress()
    assert_eq(loaded, test_imported, "加载的进度与保存的一致")

    # 验证 JSON 结构
    with open(test_progress, 'r', encoding='utf-8') as pf:
        data = json.load(pf)
    assert_eq(data['count'], 3, "进度文件中的 count 正确")
    assert_true('updated_at' in data, "进度文件包含 updated_at 时间戳")
    assert_eq(sorted(data['imported']), sorted(list(test_imported)), "进度文件中的词条列表正确")

finally:
    import_dictionary.PROGRESS_FILE = orig_progress
    if os.path.exists(test_progress):
        os.unlink(test_progress)


# ═══════════════════════════════════════
# 测试 7: export 错误返回值处理
# ═══════════════════════════════════════
print("\n📋 Test 7: collect_words_from_dom 错误返回值处理")

# 模拟 export_dictionary.py 中 collect_words_from_dom 的返回值解析逻辑
def parse_dom_result(result):
    """复制自 export_dictionary.py 的 collect_words_from_dom 返回值解析"""
    if not result or not isinstance(result, str):
        return set()
    if result.startswith(('JS_ERROR', 'RECV_ERROR', 'PARSE_ERROR', 'TIMEOUT')):
        return set()
    try:
        return set(json.loads(result))
    except (json.JSONDecodeError, TypeError):
        return set()

assert_eq(parse_dom_result(None), set(), "None 返回空 set")
assert_eq(parse_dom_result(""), set(), "空字符串返回空 set")
assert_eq(parse_dom_result("JS_ERROR: some error"), set(), "JS_ERROR 返回空 set")
assert_eq(parse_dom_result("RECV_ERROR: timeout"), set(), "RECV_ERROR 返回空 set")
assert_eq(parse_dom_result("PARSE_ERROR: {bad}"), set(), "PARSE_ERROR 返回空 set")
assert_eq(parse_dom_result("TIMEOUT"), set(), "TIMEOUT 返回空 set")
assert_eq(parse_dom_result("not valid json"), set(), "非法 JSON 返回空 set")
assert_eq(parse_dom_result(123), set(), "非字符串类型返回空 set")
assert_eq(
    parse_dom_result('["Claude", "新世紀エヴァンゲリオン"]'),
    {"Claude", "新世紀エヴァンゲリオン"},
    "正常 JSON 数组正确解析"
)


# ═══════════════════════════════════════
# 测试 8: export txt 输出路径逻辑
# ═══════════════════════════════════════
print("\n📋 Test 8: export txt 输出路径逻辑")

def resolve_txt_path(out_path):
    """复制自 export_dictionary.py 的 txt 路径解析逻辑"""
    if out_path.endswith('.json'):
        return out_path[:-5] + '.txt'
    elif not out_path.endswith('.txt'):
        return out_path + '.txt'
    return out_path

assert_eq(resolve_txt_path("words.json"), "words.txt", ".json → .txt 替换")
assert_eq(resolve_txt_path("typeless_dictionary.json"), "typeless_dictionary.txt", "默认文件名替换")
assert_eq(resolve_txt_path("words.txt"), "words.txt", "已有 .txt 不变")
assert_eq(resolve_txt_path("myexport"), "myexport.txt", "无扩展名追加 .txt")
assert_eq(resolve_txt_path("path/to/file.json"), "path/to/file.txt", "带路径的 .json 替换")


# ═══════════════════════════════════════
# 结果汇总
# ═══════════════════════════════════════
print(f"\n{'═' * 50}")
print(f"结果: {passed} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
else:
    print("所有测试通过 ✅")
