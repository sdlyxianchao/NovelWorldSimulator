# -*- coding: utf-8 -*-
"""小说世界AI模拟 · 统一入口。

本工具定位为**小说写作辅助工具**：在你已有的小说设定范围内推演情节，
产出可供改写、对照、续写的素材——不是自动写小说，也不是游戏。

用法：
    python main.py                 # 启动图形界面
    python main.py --mock          # 演示模式（零成本，不调用真实 LLM）

等价于直接运行 main_gui.py。

English:
Novel World AI Simulation · Unified entry point.
This tool is positioned as a **novel writing assistance tool**: it extrapolates plot within the
scope of your existing novel settings,
producing material that can be rewritten, compared, or continued -- it is not automatic novel
writing, nor is it a game.
Usage:
    python main.py                 # Launch the graphical interface
    python main.py --mock          # Demo mode (zero cost, does not call a real LLM)
Equivalent to running main_gui.py directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))


def main():
    from main_gui import main as gui_main
    gui_main()


if __name__ == '__main__':
    main()
