# -*- coding: utf-8 -*-
"""验证：**演示模式（MOCK）里没有洞** —— 产品用到的每个用途都登记了假回复。

为什么要单独一条判据（2026-10-07 踩出来的）
--------------------------------------------
`llm/mock.py` 的 `_HANDLERS` 是一张表：**没登记**的用途会返回一句占位 JSON。
而调用方按各自的解析器去读它，于是表现分成两种：

* **露馅的**：`group_chat` 要的是"一句口语" —— 占位 JSON 于是被
  **当成台词推到屏幕上**（真跑一遍就看到了：`阿枝：{"结果": "【演示数据】…`）；
* **静默的**：`dispatch` / `backstage_summary` / `memory_compact` /
  `novel_polish` / `review` 都有兜底 —— 于是演示模式里这些功能**等于不存在**，
  而验证脚本测到的是"兜底路径"，不是真路径。

两种都不是"坏了"，但演示模式是**用户会盯着看的那一版**，也是验证脚本的默认环境，
所以这里钉一条：**产品源码里 `purpose=` 写到的每一个名字，`_HANDLERS` 里都要有。**

⚠ 口径：只扫产品源码（不含 `tools/` `developers/` `tests/`）——
  它们自己造桩，不需要 MOCK。反向不查：MOCK 里多登记几个没被用到的
  （`importance` / `optimize` 那种）不算问题。

用法：.venv\\Scripts\\python.exe tools/verify_mock.py
产出：assets/screenshots/mock_report.json

English:
Verification: **no holes in demo mode (MOCK)** — every purpose the product uses has a fake reply
registered.
Why a separate criterion (learned the hard way 2026-10-07)
--------------------------------------------
`llm/mock.py`'s `_HANDLERS` is a table: **unregistered** purposes return a placeholder JSON
line.
And callers read it with their own parsers, so the behavior splits into two kinds:
* **Exposed**: `group_chat` wants "a spoken line" — the placeholder JSON then gets
* **Silent**: `dispatch` / `backstage_summary` / `memory_compact` /
  `novel_polish` / `review` all have fallbacks — so in demo mode these features **might as well not exist**,
  and what the verification script tests is the "fallback path", not the real path.
Neither is "broken", but demo mode is **the version users will stare at**, and it's also the
default environment for the verification script,
so we nail down one rule here: **every name written as `purpose=` in product source code must
exist in `_HANDLERS`.**
⚠ Scope: only scan product source code (excluding `tools/` `developers/` `tests/`) ——
  they build their own stubs and don't need MOCK. Not checked in reverse: registering a few extra unused ones in MOCK
  (like `importance` / `optimize`) is not a problem.
Usage: .venv\\Scripts\\python.exe tools/verify_mock.py
Output: assets/screenshots/mock_report.json
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: 只扫这些目录（产品源码）。`tools/` `developers/` `tests/` 自己造桩。
# [EN] : only scan these directories (product source code). `tools/` `developers/` `tests/` build their
# [EN] own stubs.
SCAN_DIRS = ('agent', 'compliance', 'crew', 'craft', 'display', 'director',
             'export', 'gui', 'image_gen', 'ingest', 'llm', 'mcp', 'refs',
             'research', 'sim', 'skills', 'store', 'util', 'world')
SCAN_FILES = ('config.py', 'i18n.py', 'logger.py')


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _used_purposes() -> set[str]:
    """产品源码里出现过的全部 `purpose="…"`。
        English:
    All `purpose="…"` that appear in product source code.
    """
    out: set[str] = set()
    files: list[Path] = []
    for d in SCAN_DIRS:
        p = APP_DIR / d
        if p.is_dir():
            files += list(p.rglob('*.py'))
    files += [APP_DIR / f for f in SCAN_FILES]
    for f in files:
        if '__pycache__' in f.parts or not f.is_file():
            continue
        try:
            text = f.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        out |= set(re.findall(r'purpose\s*=\s*[\'"]([a-z_0-9]+)[\'"]', text))
    return out


def main() -> int:
    try:
        from llm import mock
    except Exception:                                            # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])
        return _finish()

    used = _used_purposes()
    have = set(getattr(mock, '_HANDLERS', {}) or {})
    ok('A1 扫到了产品源码里的用途（判据自己别是空的）',
       len(used) >= 25, f'{len(used)} 个：{sorted(used)[:6]}…')
    missing = sorted(used - have)
    ok('A2 ★★ 每个用途在演示模式里都有假回复（漏登记会露馅或静默降级）',
       not missing, f'漏登记：{missing}')

    # ── B 抽查几条"漏登记会很明显"的：不能是占位 JSON ──
    #   `placeholder` 是 `mock_reply` 里那句兜底，它的特征是"未登记该用途"。
    # [EN] ── B Spot-check a few "whose missing registration would be obvious": must not be placeholder
    # [EN] JSON ──
    # [EN] `placeholder` is the fallback line in `mock_reply`, its signature is "purpose not registered".
    def fake(purpose: str, msgs=None) -> str:
        try:
            return str(mock.mock_reply(msgs or [{'role': 'user',
                                                 'content': '在场人物：主角、阿枝'}],
                                       purpose=purpose) or '')
        except Exception as e:                                   # noqa: BLE001
            return f'<raised {e!r}>'

    for p in ('group_chat', 'dispatch', 'backstage_summary',
              'memory_compact', 'review', 'crew_settings'):
        got = fake(p)
        ok(f'B 抽查 `{p}`：拿到的是真内容，不是占位 JSON',
           got and '未登记该用途' not in got and '[演示数据] 演示输出' not in got,
           got[:60].replace('\n', '⏎'))

    # `group_chat` 要的是**一句台词**：不能是 JSON 形状
    # [EN] `group_chat` wants **a single line of dialogue**: must not be JSON-shaped
    gc = fake('group_chat')
    ok('B ★ `group_chat` 给的是一句话，不是一坨 JSON'
       '（它会被原样当成台词播到屏幕上）',
       not gc.strip().startswith('{') and len(gc.strip()) <= 40, gc[:40])

    # `dispatch` 要给得出认得的人名
    # [EN] `dispatch` must produce recognizable person names
    import json as _json
    try:
        d = _json.loads(fake('dispatch'))
        names = [r.get('人物') for r in (d.get('派活') or [])]
    except Exception:                                            # noqa: BLE001
        names = []
    ok('B `dispatch` 能给在场的人派活（派给不在场的人会被丢掉，等于没派）',
       names and all(n in ('主角', '阿枝') for n in names), str(names))

    # `novel_polish` 不能凭空编 —— 它要返回**给它的那段稿子**
    # [EN] `novel_polish` must not make things up out of thin air — it must return **the exact passage
    # [EN] given to it**
    body = fake('novel_polish', [{'role': 'user',
                                 'content': '把下面这段润色：\n---\n雨下了整夜。'}])
    ok('B `novel_polish` 把给它的稿子还回来（编一段新的会让导出物跟推演对不上）',
       '雨下了整夜' in body, body[:40])
    return _finish()


def _finish() -> int:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'mock_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n = len(report['checks'])
    print(f'\n演示模式完整性验证：{n - len(bad)}/{n}')
    return 0 if not bad and not report.get('fatal') else 2


if __name__ == '__main__':
    sys.exit(main())
