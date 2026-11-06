# -*- coding: utf-8 -*-
"""验证：**源码里写下的每一条中文文案，都登记了英文**（i18n 覆盖率）。

用户（2026-10-06）：「英语界面下面，很多消息是不是也都得英语化」

★ 为什么这里只是一个**转发壳**：真正做事的代码只有一份 —— `tools/i18n_check.py`。
  但它不叫 `verify_*`，而全量回归只认 `tools/verify_*.py`（`declared()` 用
  `glob('verify_*.py')` 对表、`_run_one()` 直接拼 `tools/{name}.py` 去跑），
  所以登记进分组表的只能是"名字对得上"的那一支。
  这里**不复制**任何检查逻辑：复制一份出来，两边的口径迟早会不一样（本工程的老毛病）。

★ 为什么需要一个"看源码"的判据，`verify_ui_english` 不够吗：
  那一支量的是"**真的被打开过**的界面"。没被打开的窗口（回收站面板、
  折叠起来的外部服务说明、只在报错时才铺开的分支）它一个字都看不到 ——
  实测回收站整页七十多条没有英文，那一支一直绿着。
  **两支分工：一支管"看得见的"，一支管"写下来的"。**

English:
Verification: **every Chinese string written in the source has English registered** (i18n coverage).
User (2026-10-06): "Under the English UI, should many messages also be Englishized"
★ Why this is only a **forwarding shell**: the code that does the work exists once --
  `tools/i18n_check.py`. But it is not named `verify_*`, and the full regression only recognizes
  `tools/verify_*.py` (`declared()` globs `verify_*.py`, `_run_one()` runs `tools/{name}.py`),
  so only a correctly named script can go into the group table.
  **No check logic is copied here**: a copy would drift from the original sooner or later.
★ Why a source-level criterion when `verify_ui_english` exists:
  that one measures the screens **actually opened**. A window nobody opens (the recycle-bin pane,
  the collapsed external-service notes, error-only branches) is invisible to it -- and the whole
  recycle-bin page had 70-odd untranslated strings while it stayed green.
  **Two jobs: one guards what is seen, one guards what is written.**
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import i18n_check  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(i18n_check.main())
