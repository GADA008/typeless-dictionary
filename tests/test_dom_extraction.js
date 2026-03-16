#!/usr/bin/env node
/**
 * 测试 export_dictionary.py 中的 DOM 词条提取逻辑。
 *
 * 用 jsdom 模拟 Typeless Hub 的 DOM 结构，验证：
 * 1. 基本词条采集（英文、中文、日语、法语、西班牙语等）
 * 2. 按钮内文本被正确过滤（Edit, Delete, New word）
 * 3. 元数据标签被过滤（Added manually, Auto-added）
 * 4. 曾经被 skip set 误杀的合法词条现在能正确采集（All, Home, Edit, Search）
 * 5. 容器定位 fallback 到 document.body
 * 6. 超长文本被过滤
 */

const { JSDOM } = require('jsdom');

let passed = 0;
let failed = 0;

function assert(condition, name) {
    if (condition) {
        console.log(`  ✅ ${name}`);
        passed++;
    } else {
        console.log(`  ❌ ${name}`);
        failed++;
    }
}

// 新版提取逻辑（与 export_dictionary.py 中的 JS 完全一致）
// 接收 window 对象以正确引用 NodeFilter
function extractWords(win) {
    const document = win.document;
    const NF = win.NodeFilter;
    let container = null;
    document.querySelectorAll('div').forEach(d => {
        if (d.scrollHeight > d.clientHeight && d.clientHeight > 100
            && d.scrollHeight > 300) {
            container = d;
        }
    });
    if (!container) container = document.body;

    const metaLabels = new Set(['Added manually', 'Auto-added', 'Manually-added']);

    const words = new Set();
    const walker = document.createTreeWalker(container, NF.SHOW_TEXT, null, false);
    while (walker.nextNode()) {
        const node = walker.currentNode;
        const t = node.textContent.trim();
        if (!t || t.length === 0 || t.length > 200) continue;
        const el = node.parentElement;
        if (el && (el.tagName === 'BUTTON' || el.closest('button'))) continue;
        if (metaLabels.has(t)) continue;
        words.add(t);
    }
    return [...words];
}

// 旧版提取逻辑（用于对比）
function extractWordsOld(win) {
    const document = win.document;
    const NF = win.NodeFilter;
    const skip = new Set([
        'Pro Trial','Home','History','Dictionary','Get mobile app',
        'Upgrade','New word','All','Auto-added','Manually-added',
        'Search','Added manually','Edit','Delete','No words yet',
        'Upgrade to Typeless Pro before your trial ends',
        'Typeless remembers your unique names and words, learned automatically from your edits or added manually by you.',
        'Typeless automatically learns your unique names and words from your edits and adds them to your personal dictionary.',
        'You can manually add your unique names and words to your personal dictionary.'
    ]);
    const words = new Set();
    const walker = document.createTreeWalker(document.body, NF.SHOW_TEXT, null, false);
    while (walker.nextNode()) {
        const t = walker.currentNode.textContent.trim();
        if (t && t.length > 0 && t.length < 200
            && !skip.has(t)
            && !/^\d+ of \d+ days/.test(t)
            && !/^Version/.test(t)
            && !/^v\d+\./.test(t)
            && !/^Check for/.test(t)
            && !/^Save \d+%/.test(t)) {
            words.add(t);
        }
    }
    return [...words];
}

/**
 * 构建模拟 Typeless Hub DOM
 * 结构：sidebar(导航按钮) + main area(词典滚动列表)
 */
function buildTypelessDOM(dictWords) {
    const dom = new JSDOM(`<!DOCTYPE html><html><body>
        <!-- 侧边栏 -->
        <div class="sidebar">
            <button>Home</button>
            <button>History</button>
            <button>Dictionary</button>
            <button>Get mobile app</button>
            <span>Pro Trial</span>
            <span>14 of 30 days</span>
            <span>Version 2.1.0</span>
            <span>Upgrade</span>
            <span>Save 50%</span>
            <span>Check for updates</span>
        </div>

        <!-- 词典主区域 -->
        <div class="dict-header">
            <button>New word</button>
            <button>All</button>
            <button>Auto-added</button>
            <button>Manually-added</button>
            <input placeholder="Search" />
            <span>No words yet</span>
            <span>Typeless remembers your unique names and words, learned automatically from your edits or added manually by you.</span>
        </div>

        <!-- 词典滚动列表（这是我们要采集的目标容器） -->
        <div class="dict-list" id="scroll-container">
            ${dictWords.map(w => `
            <div class="word-entry">
                <span class="word-text">${w}</span>
                <span class="word-meta">Added manually</span>
                <button class="action-btn">Edit</button>
                <button class="action-btn">Delete</button>
            </div>`).join('')}
        </div>
    </body></html>`, { url: 'http://localhost' });

    // 模拟滚动容器的尺寸（jsdom 默认所有尺寸为 0）
    const scrollContainer = dom.window.document.getElementById('scroll-container');
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 5000, configurable: true });
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 600, configurable: true });

    return dom;
}


// ═══════════════════════════════════════
// 测试 1: 多语言词条采集
// ═══════════════════════════════════════
console.log('\n📋 Test 1: 多语言词条采集');

const multiLangWords = [
    'Claude',                    // 英文
    '新世纪福音战士',              // 中文
    '新世紀エヴァンゲリオン',       // 日语
    'résumé',                    // 法语（带重音符）
    'señor',                     // 西班牙语（带 ñ）
    'über',                      // 德语（带 ü）
    'Привет',                    // 俄语
    '안녕하세요',                  // 韩语
    'مرحبا',                     // 阿拉伯语
    '🎵🎶',                      // Emoji
];

const dom1 = buildTypelessDOM(multiLangWords);
const result1 = extractWords(dom1.window);

for (const w of multiLangWords) {
    assert(result1.includes(w), `采集到 "${w}"`);
}


// ═══════════════════════════════════════
// 测试 2: 按钮文本被正确过滤
// ═══════════════════════════════════════
console.log('\n📋 Test 2: 按钮内文本过滤');

const dom2 = buildTypelessDOM(['TestWord']);
const result2 = extractWords(dom2.window);

assert(!result2.includes('Edit'), '按钮 "Edit" 被过滤');
assert(!result2.includes('Delete'), '按钮 "Delete" 被过滤');
assert(result2.includes('TestWord'), '词条 "TestWord" 被保留');


// ═══════════════════════════════════════
// 测试 3: 元数据标签被过滤
// ═══════════════════════════════════════
console.log('\n📋 Test 3: 元数据标签过滤');

const dom3 = buildTypelessDOM(['MyWord']);
const result3 = extractWords(dom3.window);

assert(!result3.includes('Added manually'), '"Added manually" 标签被过滤');
assert(result3.includes('MyWord'), '词条 "MyWord" 被保留');


// ═══════════════════════════════════════
// 测试 4: 旧版 skip set 会误杀的词条（核心回归测试）
// ═══════════════════════════════════════
console.log('\n📋 Test 4: 旧版 skip set 误杀的词条现在被正确采集');

const previouslyKilledWords = ['All', 'Home', 'Search', 'Edit', 'Delete', 'History', 'Upgrade'];
const dom4 = buildTypelessDOM(previouslyKilledWords);
const newResult = extractWords(dom4.window);
const oldResult = extractWordsOld(dom4.window);

for (const w of previouslyKilledWords) {
    // "Edit" 和 "Delete" 在按钮内，但作为词条文本出现在 .word-text span 中，应该被采集
    // 注意：如果词条文本和按钮文本同名，button 过滤只影响 button 内的文本
    const inNew = newResult.includes(w);
    const inOld = oldResult.includes(w);

    if (w === 'Edit' || w === 'Delete') {
        // 这两个词同时出现在词条 span 和 action button 中
        // 新版：词条 span 中的被采集，button 中的被过滤 → 最终应该出现
        assert(inNew, `新版采集到词条 "${w}"（来自 .word-text span）`);
        assert(!inOld, `旧版误杀了词条 "${w}"（被 skip set 过滤）← 这是旧版 bug`);
    } else {
        assert(inNew, `新版采集到词条 "${w}"`);
        assert(!inOld, `旧版误杀了词条 "${w}"（被 skip set 过滤）← 这是旧版 bug`);
    }
}


// ═══════════════════════════════════════
// 测试 5: 侧边栏 UI 文本不被采集（容器定位生效）
// ═══════════════════════════════════════
console.log('\n📋 Test 5: 侧边栏 UI 文本被排除（容器定位）');

const dom5 = buildTypelessDOM(['RealWord']);
const result5 = extractWords(dom5.window);

assert(!result5.includes('Pro Trial'), '侧边栏 "Pro Trial" 被排除');
assert(!result5.includes('Version 2.1.0'), '侧边栏 "Version 2.1.0" 被排除');
assert(!result5.includes('Save 50%'), '侧边栏 "Save 50%" 被排除');
assert(!result5.includes('Check for updates'), '侧边栏 "Check for updates" 被排除');
assert(result5.includes('RealWord'), '词条 "RealWord" 被保留');


// ═══════════════════════════════════════
// 测试 6: 超长文本被过滤
// ═══════════════════════════════════════
console.log('\n📋 Test 6: 超长文本过滤');

const longWord = 'A'.repeat(201);
const dom6 = buildTypelessDOM([longWord, 'ShortWord']);
const result6 = extractWords(dom6.window);

assert(!result6.includes(longWord), '超过 200 字符的文本被过滤');
assert(result6.includes('ShortWord'), '正常长度词条被保留');


// ═══════════════════════════════════════
// 测试 7: 无滚动容器时 fallback 到 document.body
// ═══════════════════════════════════════
console.log('\n📋 Test 7: 无滚动容器 fallback');

const domFlat = new JSDOM(`<!DOCTYPE html><html><body>
    <div><span>FallbackWord</span></div>
    <button>ShouldBeFiltered</button>
</body></html>`, { url: 'http://localhost' });
const resultFlat = extractWords(domFlat.window);

assert(resultFlat.includes('FallbackWord'), 'fallback 到 body 仍能采集词条');
assert(!resultFlat.includes('ShouldBeFiltered'), 'fallback 模式下按钮文本仍被过滤');


// ═══════════════════════════════════════
// 测试 8: 空词典
// ═══════════════════════════════════════
console.log('\n📋 Test 8: 空词典');

const domEmpty = buildTypelessDOM([]);
const resultEmpty = extractWords(domEmpty.window);

assert(resultEmpty.length === 0, '空词典返回空数组');


// ═══════════════════════════════════════
// 结果汇总
// ═══════════════════════════════════════
console.log(`\n${'═'.repeat(50)}`);
console.log(`结果: ${passed} passed, ${failed} failed`);
if (failed > 0) {
    process.exit(1);
} else {
    console.log('所有测试通过 ✅');
}
