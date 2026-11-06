# -*- coding: utf-8 -*-
"""判据用的**假主程序**。

替掉真正的 `main_gui.py`：真程序会开一个 Flet 窗口、要人关，判据跑不了。
这个假的只做三件事 —— 写标记、睡几秒、再写一次标记 —— 于是"启动器拉起主程序
→ 等它退出 → 收拾后台服务"这整条路可以在几秒内跑完并可断言。

由 `start.exe` 的环境变量 `NWS_TEST_APP` 指定，正常路径不会被用到。

English:
**Fake main program** used for the criterion.
Replaces the real `main_gui.py`: the real program opens a Flet window and waits for a human to
close it, so the criterion cannot run.
This fake one only does three things -- write a marker, sleep a few seconds, then write the
marker again -- so the whole path of "launcher starts the main program
-> waits for it to exit -> cleans up background services" can finish within a few seconds and be
asserted on.
Specified by the environment variable `NWS_TEST_APP` of `start.exe`; the normal path will not
use it.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def main() -> int:
    mark = Path(os.environ['NWS_STUB_MARK'])
    secs = float(os.environ.get('NWS_STUB_SECONDS', '3'))
    mark.write_text(
        'started\npid={p}\nargv={a}\ncwd={c}\n'.format(
            p=os.getpid(), a=sys.argv[1:], c=os.getcwd()),
        encoding='utf-8')
    time.sleep(secs)
    with mark.open('a', encoding='utf-8') as f:
        f.write('exited\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
