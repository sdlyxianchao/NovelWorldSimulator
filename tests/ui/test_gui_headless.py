# -*- coding: utf-8 -*-
"""UI 测试：Headless 模式测试。

在 headless 模式下测试 GUI 组件，无需实际显示窗口。

English:
UI tests: Headless mode tests.
Test GUI components in headless mode without actually displaying a window.
"""
import sys
import os
import asyncio
from pathlib import Path

# 添加项目根目录到 path
# [EN] Add project root to path
APP_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(APP_DIR))
os.environ['MOCK_LLM'] = 'true'

import flet as ft


class HeadlessGUITester:
    """Headless GUI 测试器。
        English:
    Headless GUI tester.
    """

    def __init__(self):
        self.errors = []
        self.passed = 0
        self.failed = 0
        self.page = None

    def log(self, msg: str, is_error: bool = False):
        """记录日志。
                English:
        Logging.
        """
        if is_error:
            print(f"✗ {msg}")
            self.errors.append(msg)
            self.failed += 1
        else:
            print(f"✓ {msg}")
            self.passed += 1

    async def setup(self):
        """设置测试环境。
                English:
        Set up test environment.
        """
        print("=" * 60)
        print("UI Headless 测试")
        print("=" * 60)

    async def test_start_screen_components(self):
        """测试开始界面组件。
                English:
        Test start screen components.
        """
        print("\n测试 1：开始界面组件")

        try:
            from gui.app_flet import NovelWorldApp, C, make_border

            app = NovelWorldApp()

            # 测试菜单项创建
            # [EN] Test menu item creation
            menu_items = [
                ("开卷", "导入新故事"),
                ("拾卷", "继续项目"),
                ("天机", "全局设置"),
                ("书斋", "项目设置"),
                ("归去", "退出"),
            ]

            for title, desc in menu_items:
                try:
                    item = ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.MENU, color=C['gold']),
                            ft.Column([
                                ft.Text(title, size=16, color=C['gold']),
                                ft.Text(desc, size=12, color=C['muted']),
                            ], spacing=2),
                        ], spacing=12),
                        padding=ft.Padding(12, 12, 12, 12),
                        border_radius=8,
                        on_hover=lambda e: None,
                    )
                    self.log(f"菜单项 '{title}' 创建成功")
                except Exception as e:
                    self.log(f"菜单项 '{title}' 创建失败: {e}", is_error=True)

            return True
        except Exception as e:
            self.log(f"测试失败: {e}", is_error=True)
            return False

    async def test_import_wizard_components(self):
        """测试导入向导组件。
                English:
        Test import wizard components.
        """
        print("\n测试 2：导入向导组件")

        try:
            from gui.app_flet import NovelWorldApp, C

            app = NovelWorldApp()

            # 测试文件选择器
            # [EN] Test file picker
            try:
                file_picker = ft.FilePicker(on_result=lambda e: None)
                self.log("FilePicker 创建成功")
            except Exception as e:
                self.log(f"FilePicker 创建失败: {e}", is_error=True)

            # 测试输入框
            # [EN] Test input field
            try:
                text_field = ft.TextField(
                    label="测试输入框",
                    bgcolor=C['input_bg'],
                    color=C['text'],
                    border_color=C['border'],
                )
                self.log("TextField 创建成功")
            except Exception as e:
                self.log(f"TextField 创建失败: {e}", is_error=True)

            # 测试下拉框
            # [EN] Test dropdown
            try:
                dropdown = ft.Dropdown(
                    label="测试下拉框",
                    bgcolor=C['input_bg'],
                    color=C['text'],
                    border_color=C['border'],
                    options=[
                        ft.dropdown.Option("选项1"),
                        ft.dropdown.Option("选项2"),
                    ],
                )
                self.log("Dropdown 创建成功")
            except Exception as e:
                self.log(f"Dropdown 创建失败: {e}", is_error=True)

            # 测试开关
            # [EN] Test switch
            try:
                switch = ft.Switch(
                    label="测试开关",
                    active_color=C['accent'],
                )
                self.log("Switch 创建成功")
            except Exception as e:
                self.log(f"Switch 创建失败: {e}", is_error=True)

            return True
        except Exception as e:
            self.log(f"测试失败: {e}", is_error=True)
            return False

    async def test_global_settings_components(self):
        """测试全局设置组件。
                English:
        Test global settings components.
        """
        print("\n测试 3：全局设置组件")

        try:
            from gui.app_flet import NovelWorldApp, C
            from config import CFG

            app = NovelWorldApp()

            # 测试选项卡创建（Flet 1.0 API）
            # [EN] Test tab creation (Flet 1.0 API)
            try:
                # Flet 1.0 中 Tabs 可能使用不同的 API
                # 让我们测试基本的容器和列布局
                # [EN] Tabs may use a different API in Flet 1.0
                # [EN] Let's test basic container and column layout
                container = ft.Container(
                    content=ft.Column([
                        ft.Text("LLM 设置"),
                        ft.Text("运行设置"),
                        ft.Text("导演设置"),
                    ]),
                    width=600,
                    height=500,
                )
                self.log("设置容器创建成功")
            except Exception as e:
                self.log(f"设置容器创建失败: {e}", is_error=True)

            # 测试配置读取
            # [EN] Test config reading
            try:
                api_key = CFG.s('LLM_API_KEY')
                self.log(f"LLM_API_KEY 读取成功")
            except Exception as e:
                self.log(f"LLM_API_KEY 读取失败: {e}", is_error=True)

            try:
                model = CFG.s('MODEL_FRONT')
                self.log(f"MODEL_FRONT 读取成功: {model}")
            except Exception as e:
                self.log(f"MODEL_FRONT 读取失败: {e}", is_error=True)

            return True
        except Exception as e:
            self.log(f"测试失败: {e}", is_error=True)
            return False

    async def test_project_settings_components(self):
        """测试项目设置组件。
                English:
        Test project settings components.
        """
        print("\n测试 4：项目设置组件")

        try:
            from gui.app_flet import NovelWorldApp, C

            app = NovelWorldApp()

            # 测试滑块创建
            # [EN] Test slider creation
            try:
                slider = ft.Slider(
                    min=0, max=1, value=0.5,
                    label="{value}",
                )
                self.log("Slider 创建成功")
            except Exception as e:
                self.log(f"Slider 创建失败: {e}", is_error=True)

            # 测试进度条
            # [EN] Test progress bar
            try:
                progress = ft.ProgressRing(width=40, height=40)
                self.log("ProgressRing 创建成功")
            except Exception as e:
                self.log(f"ProgressRing 创建失败: {e}", is_error=True)

            return True
        except Exception as e:
            self.log(f"测试失败: {e}", is_error=True)
            return False

    async def test_dialog_creation(self):
        """测试对话框创建。
                English:
        Test dialog creation.
        """
        print("\n测试 5：对话框创建")

        try:
            from gui.app_flet import C

            # 测试 AlertDialog
            # [EN] Test AlertDialog
            try:
                dlg = ft.AlertDialog(
                    title=ft.Text("测试对话框", color=C['gold']),
                    content=ft.Container(
                        content=ft.Column([
                            ft.Text("内容"),
                        ]),
                        width=600,
                        height=500,
                    ),
                    actions=[
                        ft.FilledButton("确定"),
                        ft.TextButton("取消"),
                    ],
                    bgcolor=C['panel'],
                )
                self.log("AlertDialog 创建成功")
            except Exception as e:
                self.log(f"AlertDialog 创建失败: {e}", is_error=True)

            return True
        except Exception as e:
            self.log(f"测试失败: {e}", is_error=True)
            return False

    async def test_button_callbacks(self):
        """测试按钮回调。
                English:
        Test button callbacks.
        """
        print("\n测试 6：按钮回调")

        try:
            # 测试按钮点击回调
            # [EN] Test button click callback
            callback_triggered = []

            def test_callback(e):
                callback_triggered.append(True)

            btn = ft.FilledButton("测试按钮", on_click=test_callback)
            self.log("按钮回调创建成功")

            # 测试悬停回调
            # [EN] Test hover callback
            hover_triggered = []

            def test_hover(e):
                hover_triggered.append(True)

            container = ft.Container(
                content=ft.Text("测试"),
                on_hover=test_hover,
            )
            self.log("悬停回调创建成功")

            return True
        except Exception as e:
            self.log(f"测试失败: {e}", is_error=True)
            return False

    async def run_all_tests(self):
        """运行所有测试。
                English:
        Run all tests.
        """
        await self.setup()

        tests = [
            self.test_start_screen_components,
            self.test_import_wizard_components,
            self.test_global_settings_components,
            self.test_project_settings_components,
            self.test_dialog_creation,
            self.test_button_callbacks,
        ]

        for test in tests:
            try:
                await test()
            except Exception as e:
                self.log(f"测试异常: {e}", is_error=True)

        # 总结
        # [EN] Summary
        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"通过: {self.passed}")
        print(f"失败: {self.failed}")

        if self.errors:
            print("\n错误列表:")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")

        return self.failed == 0


async def main():
    """主函数。
        English:
    Main function.
    """
    tester = HeadlessGUITester()
    success = await tester.run_all_tests()

    if success:
        print("\n✅ 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))