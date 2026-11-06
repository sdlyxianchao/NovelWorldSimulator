# -*- coding: utf-8 -*-
"""UI 测试运行器。

运行所有 UI 测试：
1. Headless 组件测试
2. 对话框集成测试（实际构建对话框）

用法：
    python tests/ui/run_all.py

English:
UI test runner.
Run all UI tests:
1. Headless component tests
2. Dialog integration tests (actually build dialogs)
Usage:
    python tests/ui/run_all.py
"""
import sys
import os
import subprocess
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent
UI_DIR = Path(__file__).resolve().parent


def run_test(script: str, timeout: int = 60) -> bool:
    """运行单个测试脚本。
        English:
    Run a single test script.
    """
    print(f"\n{'='*60}")
    print(f"运行: {script}")
    print('='*60)

    script_path = UI_DIR / script
    if not script_path.exists():
        print(f"✗ 测试脚本不存在: {script_path}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(APP_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, 'MOCK_LLM': 'true'},
        )

        print(result.stdout)

        if result.returncode != 0:
            print(f"✗ 测试失败 (返回码: {result.returncode})")
            if result.stderr:
                print(f"错误: {result.stderr[:2000]}")
            return False

        return True
    except subprocess.TimeoutExpired:
        print("✗ 测试超时")
        return False
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        return False


def main():
    """主函数。
        English:
    Main function.
    """
    print("=" * 60)
    print("UI 测试套件")
    print("=" * 60)

    tests = [
        "test_gui_headless.py",
        "test_dialogs_integration.py",
        "test_ingest_flow.py",
    ]

    passed = 0
    failed = 0

    for test in tests:
        if run_test(test):
            passed += 1
        else:
            failed += 1

    # 检查集成测试结果文件
    # [EN] Check the integration test result file
    result_file = APP_DIR / 'logs' / 'ui_test_result.txt'
    if result_file.exists():
        print(f"\n{'='*60}")
        print("对话框集成测试结果")
        print('='*60)
        content = result_file.read_text(encoding='utf-8')
        print(content)

        # 检查是否有错误
        # [EN] Check whether there are errors
        if 'ERR\t' in content or 'ERR ' in content:
            failed += 1

    # 总结
    # [EN] Summary
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"测试套件通过: {passed}")
    print(f"测试套件失败: {failed}")

    if failed == 0:
        print("\n✅ 所有 UI 测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())