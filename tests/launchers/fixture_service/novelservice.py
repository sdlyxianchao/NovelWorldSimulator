# -*- coding: utf-8 -*-
"""判据用的**假创作服务**（替掉 `novelservices/MuMuAINovel/backend/novelservice.py`）。

为什么不能直接用真的：真服务 `start` 会去建 venv、装依赖、首次还要下 470MB 模型，
判据不可能为了一条断言跑几分钟（更不该在测试里去下载东西）。

它只做一件事：**把收到的动作记下来**（`calls.txt`）。于是判据可以断言
"主窗口退出之后，启动器确实调了 `stop`" —— 那是启动器那一侧的**契约**；
至于 `stop` 本身停不停得掉进程，是 `novelservice.py` 自己的事（`do_stop` 里
有 `taskkill` + 等它真死 + 校验，另有判据守）。

由 `start.exe` 的环境变量 `NWS_TEST_SERVICE_DIR` 指过来。

English:
The **fake creation service** used for the assertions (replaces
`novelservices/MuMuAINovel/backend/novelservice.py`).
Why not use the real one directly: the real service's `start` will create a venv, install
dependencies, and on first run also download a 470MB model,
the assertions can't possibly take several minutes for a single assertion (and even less should
they download things during tests).
It does only one thing: **record the actions it receives** (`calls.txt`). Thus the assertions
can assert
"after the main window exits, the launcher did indeed call `stop`" -- that is the **contract**
on the launcher's side;
as for whether `stop` itself can actually kill the process, that is `novelservice.py`'s own
business (in `do_stop`
there is `taskkill` + waiting for it to actually die + verification, guarded by separate
assertions).
Pointed here by `start.exe`'s environment variable `NWS_TEST_SERVICE_DIR`.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    with (here / 'calls.txt').open('a', encoding='utf-8') as f:
        f.write(json.dumps({
            'action': action,
            'argv': sys.argv[1:],
            'pid': os.getpid(),
            'at': time.time(),
        }, ensure_ascii=False) + '\n')
    # 支持一个 `sleep N` 动作，用来伪造"服务正在跑"的状态。
    # [EN] Support a `sleep N` action, used to fake the "service is running" state.
    if action == 'sleep' and len(sys.argv) > 2:
        time.sleep(float(sys.argv[2]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
