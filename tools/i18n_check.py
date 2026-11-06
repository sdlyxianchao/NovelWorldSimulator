# -*- coding: utf-8 -*-
"""i18n 完整性检查：找出 t(...) 里还没登记英文的中文 key。

用法：
    python tools/i18n_check.py            # 检查**全部产品源码**（默认，回归跑的就是这个）
    python tools/i18n_check.py --gui      # 只查 gui/app_flet.py（改界面时想快一点）
    python tools/i18n_check.py --all      # 同默认，留着兼容旧习惯

★★ 2026-10-26：**默认范围从"只有 app_flet.py"改成"全部产品源码"**。
   原来是默认查一个文件、`--all` 才查全项目，而回归里谁也没带 `--all` ——
   于是「回收站面板整页七十多条文案没登记英文」这件事，工具查得出来、却一次都没查过。
   **默认值就是实际执行的那条路**：能查全的就别把默认设在最窄的那一格。

English:
i18n completeness check: find Chinese keys in t(...) that have no English registered yet.
Usage:
    python tools/i18n_check.py            # check **all product source** (default; what the regression runs)
    python tools/i18n_check.py --gui      # only gui/app_flet.py (when tweaking the UI)
    python tools/i18n_check.py --all      # same as default, kept for muscle memory

★★ 2026-10-26: **the default scope changed from "app_flet.py only" to "all product source"**.
   It used to check one file by default and need `--all` for the project, and nothing in the
   regression passed `--all` -- so "the whole recycle-bin pane has 70-odd untranslated strings"
   was detectable by the tool and never once detected. **The default is the path that actually
   runs**: if you can check everything, do not park the default at the narrowest slot.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from i18n import _ZH2EN, LANGS  # noqa: E402

HAN = re.compile(r'[\u4e00-\u9fff]')


def keys_in(path: Path) -> list[str]:
    src = path.read_text(encoding='utf-8')
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 't'
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.append(node.args[0].value)
    return out


def duplicate_keys() -> list[tuple[str, int]]:
    """找出 `i18n.py` 里**同一个 key 写了两次**的条目。

    为什么必须查：Python 字典字面量遇到重复 key 是**静默覆盖**（后者赢），
    运行时看不出任何异常 —— 两个词条只有一个生效，而"哪个生效"取决于
    书写顺序。踩过：开始界面区块写了一条 `'退出程序'`，文件尾部另有一条，
    结果界面上是后者，前面那条纯属白写、还让人以为改过。
    （AST 里数字典节点的 key 数得到的是**全部**条目，所以查得出来；
     运行时 `len(_ZH2EN)` 查不出来。）
    
        English:
    Find entries in `i18n.py` where **the same key is written twice**.
        Why this must be checked: a Python dict literal **silently overwrites** on duplicate keys (the latter wins),
        no exception is visible at runtime -- only one of the two entries takes effect, and "which one takes effect" depends on
        the writing order. Learned the hard way: the start screen section wrote a `'退出程序'`, and there was another one at the end of the file,
        and the result on screen was the latter; the earlier one was written for nothing and made people think it had been changed.
        (Counting the keys of a dict node in the AST gives you **all** entries, so this can be detected;
         at runtime `len(_ZH2EN)` cannot detect it.)
    """
    src = (ROOT / 'i18n.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k in node.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                counts[k.value] = counts.get(k.value, 0) + 1
    return sorted(((k, n) for k, n in counts.items() if n > 1),
                  key=lambda x: -x[1])


def main() -> int:
    # 默认查**全部产品源码**；`--gui` 才缩到 app_flet.py（见文件头的说明）。
    # [EN] Default is **all product source**; `--gui` narrows it to app_flet.py (see the header).
    check_all = '--gui' not in sys.argv
    files = [ROOT / 'gui' / 'app_flet.py']
    if check_all:
        # ⚠ 只扫**产品源码**（与 `verify_config_sweep` 的 D1 同一口径）：
        #   `tools/` `developers/` `tests/` 里的 `t('中文')` 不是给用户看的
        #   （探针与判据的临时文案、改名时留下的备份副本都在这儿）——
        #   不排掉它们，`--all` 会报一堆**根本不进界面**的假缺译，
        #   而假缺译比真缺译更坏：看多了就没人看这一项了。
        # [EN] ⚠ Only scan **product source code** (same criteria as D1 in `verify_config_sweep`):
        # [EN] `t('中文')` in `tools/` `developers/` `tests/` is not meant for users
        # [EN] (temporary strings for probes and criteria, backup copies left behind from renames are all here)
        # [EN] --
        # [EN] Without excluding them, `--all` will report a bunch of false missing translations that **never
        # [EN] reach the UI**,
        # [EN] and false missing translations are worse than real ones: once you see too many, nobody looks at
        # [EN] this item anymore.
        _skip = {'.venv', '__pycache__', '.git', 'logs', 'assets', 'packages',
                 'generated-images', '发布版本', 'node_modules', '.workbuddy',
                 'samples', 'tools', 'developers', 'tests'}
        files = [p for p in ROOT.rglob('*.py')
                 if not any(s in p.parts for s in _skip)
                 and 'i18n.py' not in p.name]

    total_keys: set[str] = set()
    for f in files:
        try:
            ks = [k for k in keys_in(f) if HAN.search(k)]
        except Exception as e:  # noqa: BLE001
            print(f'  (跳过 {f.name}: {e})')
            continue
        total_keys.update(ks)

    missing = sorted(k for k in total_keys if k not in _ZH2EN)
    dupes = duplicate_keys()
    print(f'语言: {", ".join(LANGS)}')
    print(f'中文 key: {len(total_keys)} 条')
    print(f'已登记英文: {len(total_keys) - len(missing)} 条')
    print(f'缺译: {len(missing)} 条')
    for m in missing:
        print('  -', repr(m))
    print(f'重复 key: {len(dupes)} 条')
    for k, n in dupes:
        print(f'  - {k!r} 出现 {n} 次（后者会**静默覆盖**前者）')
    return 1 if (missing or dupes) else 0


if __name__ == '__main__':
    raise SystemExit(main())
