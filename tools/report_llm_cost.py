# -*- coding: utf-8 -*-
r"""LLM 花费体检（命令行薄壳）—— **实现在 `llm/cost_advisor.py`**。

    .venv\Scripts\python.exe tools\report_llm_cost.py          # 最近 7 天
    .venv\Scripts\python.exe tools\report_llm_cost.py --days 3
    .venv\Scripts\python.exe tools\report_llm_cost.py --all    # 全部历史

★★★ 2026-11-01：这个脚本原来自带一整份取数 + 排版逻辑，而「天机 · 花费与优化」
   那一页也要同一份报表。**同一件事两处实现 ⇒ 迟早有一处忘了跟着最新**
   （改了阈值，界面与命令行给出两个结论，而两边看着都正常）。
   ⇒ 取数与排版都搬进 `llm/cost_advisor.report()`，这里只留参数解析与打印。

它**不是判据**（不断言红绿），是一个看得懂的报告 —— 因为"省钱"这件事
先要**看见**，才谈得上改。数据来自 `usage.db` 的 `usage_log`（每次真调用一行），
`cache_tok` 是其中命中厂商前缀缓存的部分（约按 1/10 计价）。

English:
LLM cost checkup (a thin CLI shell) -- **the implementation is `llm/cost_advisor.py`**.
★★★ 2026-11-01: this script used to carry its own copy of the query + formatting logic,
but the "Tianji · Cost & Tuning" tab needs the same report. **One thing, two
implementations = sooner or later one of them stops keeping up.** So both moved into
`cost_advisor.report()` and only argument parsing + printing remain here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from llm import cost_advisor as A                       # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--days', type=float, default=7, help='看最近几天（默认 7）')
    ap.add_argument('--all', action='store_true', help='看全部历史')
    ap.add_argument('--top', type=int, default=A.TOP_ROWS, help='列前几项（默认 18）')
    ap.add_argument('--scope', default='', help='只看某个项目（书名）；空 = 软件整体')
    args = ap.parse_args()

    if not A.db_file().exists():
        print(f'找不到台账：{A.db_file()}\n（跑一次程序之后才会有）')
        return 1
    days = None if args.all else args.days
    print()
    print(A.report(days, scope=(args.scope or None), top=args.top))
    return 0


if __name__ == '__main__':
    sys.exit(main())
