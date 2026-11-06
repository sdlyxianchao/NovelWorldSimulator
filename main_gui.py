# -*- coding: utf-8 -*-
"""小说世界AI模拟 · GUI 入口。

使用 Flet 构建的水墨丹青风格桌面界面。
启动后直接显示开始界面。

用法：
    python main_gui.py
    python main_gui.py --mock  # 演示模式

English:
Novel world AI simulation · GUI entry.
Ink-wash painting style desktop interface built with Flet.
Show start screen directly after launch.
Usage:
    python main_gui.py
    python main_gui.py --mock  # demo mode
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))


def main():
    parser = argparse.ArgumentParser(description='小说世界AI模拟（GUI）')
    parser.add_argument('--mock', action='store_true', help='演示模式')
    args = parser.parse_args()

    # 设置环境变量
    # [EN] Set environment variables
    if args.mock:
        import os
        os.environ['MOCK_LLM'] = 'true'

    # 初始化日志系统
    # [EN] Initialize logging system
    from logger import nws_logger
    nws_logger.info("程序启动  /  Program started", category="system")
    nws_logger.info(f"演示模式 / Demo mode: {args.mock}", category="system")

    # 初始化配置
    # [EN] Initialize configuration
    from config import CFG, ENV_PATH

    # 演示模式：写入内存配置（CFG 只读 .env，不认环境变量，所以必须显式 set）
    # [EN] Demo mode: write in-memory config (CFG only reads .env, does not recognize environment
    # [EN] variables, so must explicitly set)
    if not ENV_PATH.exists():
        CFG.save()
        nws_logger.info(f"生成配置文件 / Created config file: {ENV_PATH}", category="config")

    if args.mock:
        CFG.set('MOCK_LLM', 'true')   # 仅本次运行生效，不落盘
        # [EN] Only effective for this run, not persisted to disk

    # 初始化界面语言（.env 的 LANGUAGE，可在天机里切换）
    # [EN] Initialize UI language (.env's LANGUAGE, can be switched in 天机)
    from i18n import set_lang
    nws_logger.info(f"界面语言 / UI language: {set_lang(CFG.s('LANGUAGE'))}", category="config")

    # 检查 Flet 运行时（首次运行时）
    # [EN] Check Flet runtime (on first run)
    nws_logger.info("检查 Flet 运行时...  /  Checking the Flet runtime...", category="system")
    from flet_setup import ensure_flet_ready, PACKAGES_DIR, get_package_filename, FLET_DOWNLOAD_URL
    if not ensure_flet_ready():
        filename = get_package_filename() or "flet-*.zip/tar.gz"
        nws_logger.error(
            f"Flet 运行时未就绪 / Flet runtime not ready, need: {filename}",
            category="system"
        )
        print("\n[!] Flet 运行时未就绪  /  Flet runtime is not ready")
        print(f"请将 {filename} 放到（put it in）:")
        print(f"  {PACKAGES_DIR}")
        print("\n下载地址（download from）:")
        print(f"  {FLET_DOWNLOAD_URL}/{filename}")
        sys.exit(1)

    # 启动 GUI（使用 Flet）
    # [EN] Start GUI (using Flet)
    nws_logger.info("启动 GUI...  /  Launching the GUI...", category="ui")
    try:
        from gui.app_flet import start_gui
        start_gui()
    except Exception as e:
        nws_logger.exception("GUI 启动失败  /  GUI failed to start", category="ui")
        raise


if __name__ == '__main__':
    main()