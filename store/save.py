# -*- coding: utf-8 -*-
"""版本快照：自动落盘 + 手动快照 + 管理。

用途：推演过程中保存「某一刻的完整世界状态」，方便回到该节点换一种走法再推一遍，
产出多版结果供写作者做废案对照。

目录名沿用 `存档/`（历史兼容，本质是版本快照）。
Projects/<项目名>/存档/
├── 自动保存_2026-10-04-20-00/
│   ├── 存档信息.json
│   ├── 本地设定集/
│   ├── 每天的生活/
│   ├── 关键事件/
│   └── state.db
└── 手动存档_第一版推演/
    └── ...

English:
Version snapshots: auto-save + manual snapshot + management.
Purpose: save "the complete world state at a certain moment" during the simulation, so you can
return to that node and try a different path to re-simulate,
producing multiple versions of results for the writer to cross-reference as discarded drafts.
The directory name follows `存档/` (backward compatible, essentially version snapshots).
Projects/<project name>/存档/
│   └── state.db
    └── ...
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from config import CFG
from util.io import atomic_write_text, ensure_dir
from util.text import now_str

_LOG = __import__("logging").getLogger("nws.store")


class SaveManager:
    """存档管理器。
        English:
    Archive manager.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.save_dir = project_dir / "存档"

    def create_save(self, name: str = "", description: str = "",
                    source_run_dir: Path | None = None,
                    world_state: dict | None = None) -> Path:
        """创建存档。

        Args:
            name: 存档名，空则自动用时间戳
            description: 存档描述（剧情摘要）
            source_run_dir: 源运行文件夹路径
            world_state: 世界状态快照

        Returns:
            存档目录路径
        
                English:
        Create archive.
                Args:
                    name: archive name, if empty auto-use timestamp
                    description: archive description (plot summary)
                    source_run_dir: source run folder path
                    world_state: world state snapshot
                Returns:
                    archive directory path
        """
        # 生成存档名
        # [EN] Generate archive name
        if not name:
            name = f"自动保存_{now_str('%Y-%m-%d-%H-%M')}"
        else:
            # 清理文件名
            # [EN] Sanitize filename
            name = self._sanitize_name(name)

        save_path = self.save_dir / name
        ensure_dir(save_path)

        # 复制运行文件夹内容
        # [EN] Copy run folder contents
        if source_run_dir and source_run_dir.exists():
            self._copy_run_contents(source_run_dir, save_path)

        # 保存存档信息
        # [EN] Save archive info
        save_info = {
            "名称": name,
            "描述": description,
            "时间": now_str("%Y-%m-%d %H:%M:%S"),
            # 世界状态
            # [EN] World state
            "故事天数": world_state.get("game_day", 0) if world_state else 0,
            "故事时间": world_state.get("clock_display", "") if world_state else "",
            "当前节点": world_state.get("current_node", "") if world_state else "",
            "张力": world_state.get("tension", 0) if world_state else 0,
            "事件数": world_state.get("event_count", 0) if world_state else 0,
            # 场景信息
            # [EN] Scene info
            "天气": world_state.get("weather", "") if world_state else "",
            "场景": world_state.get("scene", "") if world_state else "",
            "场景描述": world_state.get("scene_desc", "") if world_state else "",
            # 人物
            # [EN] Characters
            "在场人物": world_state.get("on_stage", []) if world_state else [],
            "后台人物": world_state.get("off_stage", []) if world_state else [],
            # 剧情
            # [EN] Plot
            "活跃故事线": world_state.get("active_lines", []) if world_state else [],
            "激活伏笔": world_state.get("activated_foreshadows", []) if world_state else [],
        }
        atomic_write_text(save_path / "存档信息.json",
                         json.dumps(save_info, ensure_ascii=False, indent=2))

        _LOG.info("存档创建成功: %s", save_path.name)
        return save_path

    def list_saves(self) -> list[dict]:
        """列出所有存档。
                English:
        List all archives.
        """
        if not self.save_dir.exists():
            return []

        saves = []
        for save_path in sorted(self.save_dir.iterdir(), reverse=True):
            if not save_path.is_dir():
                continue

            info_path = save_path / "存档信息.json"
            if info_path.exists():
                try:
                    info = json.loads(info_path.read_text(encoding="utf-8"))
                    info["路径"] = str(save_path)
                    saves.append(info)
                except Exception as e:
                    _LOG.warning("读取存档信息失败 %s: %s", save_path.name, e)
                    saves.append({
                        "名称": save_path.name,
                        "描述": "（信息读取失败）",
                        "时间": "未知",
                        "路径": str(save_path),
                    })
            else:
                # 从文件夹名推断信息
                # [EN] Infer info from folder name
                saves.append({
                    "名称": save_path.name,
                    "描述": "（无存档信息）",
                    "时间": "未知",
                    "路径": str(save_path),
                })

        return saves

    def get_save_info(self, save_name: str) -> dict | None:
        """获取指定存档的详细信息。
                English:
        Get detailed info of the specified archive.
        """
        save_path = self.save_dir / save_name
        info_path = save_path / "存档信息.json"

        if info_path.exists():
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
                info["路径"] = str(save_path)
                return info
            except Exception:
                pass

        return None

    def delete_save(self, save_name: str) -> bool:
        """删除存档。
                English:
        Delete archive.
        """
        save_path = self.save_dir / save_name
        if save_path.exists():
            try:
                shutil.rmtree(save_path)
                _LOG.info("存档已删除: %s", save_name)
                return True
            except Exception as e:
                _LOG.error("删除存档失败 %s: %s", save_name, e)
        return False

    def _copy_run_contents(self, source: Path, dest: Path) -> None:
        """复制运行文件夹内容到存档。
                English:
        Copy run folder contents to archive.
        """
        # 需要复制的目录
        # [EN] Directories to copy
        dirs_to_copy = ["本地设定集", "每天的生活", "关键事件", "快照"]

        for dir_name in dirs_to_copy:
            src_dir = source / dir_name
            if src_dir.exists():
                dst_dir = dest / dir_name
                try:
                    if dst_dir.exists():
                        shutil.rmtree(dst_dir)
                    shutil.copytree(src_dir, dst_dir)
                except Exception as e:
                    _LOG.warning("复制 %s 失败: %s", dir_name, e)

        # 复制数据库
        # [EN] Copy database
        db_src = source / "state.db"
        if db_src.exists():
            try:
                shutil.copy2(db_src, dest / "state.db")
            except Exception as e:
                _LOG.warning("复制数据库失败: %s", e)

        # 复制关键文件
        # [EN] Copy key files
        files_to_copy = ["任务介绍.md", "运行小结.md", "大纲建议.md",
                        "故事文档", "考据笔记.md", "合规报告.md"]
        for file_name in files_to_copy:
            src_file = source / file_name
            if src_file.exists():
                try:
                    if src_file.is_dir():
                        dst_file = dest / file_name
                        if dst_file.exists():
                            shutil.rmtree(dst_file)
                        shutil.copytree(src_file, dst_file)
                    else:
                        shutil.copy2(src_file, dest / file_name)
                except Exception as e:
                    _LOG.warning("复制 %s 失败: %s", file_name, e)

    def _sanitize_name(self, name: str) -> str:
        """清理文件名。
                English:
        Sanitize filename.
        """
        bad_chars = '<>:"/\\|?*'
        for c in bad_chars:
            name = name.replace(c, '_')
        return name.strip() or f"存档_{now_str('%Y%m%d_%H%M%S')}"


def auto_save_on_day_end(project_dir: Path, run_dir: Path,
                         world_state: dict) -> Path | None:
    """每天结束时自动存档。
        English:
    Auto-save at the end of each day.
    """
    save_mgr = SaveManager(project_dir)
    description = _generate_auto_description(world_state)
    return save_mgr.create_save(
        name="",  # 自动用时间戳
        # [EN] Auto-use timestamp
        description=description,
        source_run_dir=run_dir,
        world_state=world_state,
    )


def auto_save_on_key_event(project_dir: Path, run_dir: Path,
                           world_state: dict, event_desc: str) -> Path | None:
    """关键事件时自动存档。
        English:
    Auto-save on key events.
    """
    save_mgr = SaveManager(project_dir)
    description = f"关键事件：{event_desc}\n\n{_generate_auto_description(world_state)}"
    return save_mgr.create_save(
        name="",  # 自动用时间戳
        # [EN] Auto-use timestamp
        description=description,
        source_run_dir=run_dir,
        world_state=world_state,
    )


def _generate_auto_description(world_state: dict) -> str:
    """生成自动存档描述。
        English:
    Generate auto-save description.
    """
    parts = []
    parts.append(f"游戏第 {world_state.get('game_day', 0)} 天")
    parts.append(f"当前节点：{world_state.get('current_node', '?')}")
    parts.append(f"张力：{world_state.get('tension', 0):.1f}")

    on_stage = world_state.get('on_stage', [])
    if on_stage:
        parts.append(f"在场人物：{', '.join(on_stage[:4])}")

    return "\n".join(parts)