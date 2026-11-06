# -*- coding: utf-8 -*-
"""工艺库加载器（设计稿 §8）：加载 playbook / 类型档案 / 案例库。

craft/ 目录结构：
├── playbooks/     教科书 playbook（方法论）
├── genres/        类型档案（YAML）
└── cases/         案例库（Markdown）

English:
Craft library loader (design doc §8): load playbook / genre profiles / case library.
craft/ directory structure:
├── playbooks/     textbook playbook (methodology)
├── genres/        genre profiles (YAML)
└── cases/         case library (Markdown)
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from config import CFG

_LOG = __import__("logging").getLogger("nws.craft")

CRAFT_DIR = Path(__file__).parent


class CraftLoader:
    """工艺库加载器：加载并缓存工艺库内容。
        English:
    Craft library loader: load and cache craft library contents.
    """

    def __init__(self):
        self._playbooks: dict[str, dict] = {}
        self._genres: dict[str, dict] = {}
        self._cases: dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        """加载全部工艺库内容。
                English:
        Load all craft library contents.
        """
        if self._loaded:
            return

        # 加载 playbooks
        # [EN] Load playbooks
        self._load_playbooks()

        # 加载 genres
        # [EN] Load genres
        self._load_genres()

        # 加载 cases
        # [EN] Load cases
        self._load_cases()

        self._loaded = True
        _LOG.info("工艺库加载完成: %d playbook, %d 类型档案, %d 案例",
                  len(self._playbooks), len(self._genres), len(self._cases))

    def _load_playbooks(self) -> None:
        """加载教科书 playbook。
                English:
        Load textbook playbooks.
        """
        playbook_dir = CRAFT_DIR / "playbooks"
        if not playbook_dir.exists():
            return

        for f in playbook_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._playbooks[f.stem] = data
            except Exception as e:
                _LOG.warning("加载 playbook 失败 %s: %s", f.name, e)

    def _load_genres(self) -> None:
        """加载类型档案。
                English:
        Load genre profiles.
        """
        genre_dir = CRAFT_DIR / "genres"
        if not genre_dir.exists():
            return

        for f in genre_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._genres[f.stem] = data
            except Exception as e:
                _LOG.warning("加载类型档案失败 %s: %s", f.name, e)

    def _load_cases(self) -> None:
        """加载案例库。
                English:
        Load case library.
        """
        case_dir = CRAFT_DIR / "cases"
        if not case_dir.exists():
            return

        for f in case_dir.glob("*.md"):
            try:
                self._cases[f.stem] = f.read_text(encoding="utf-8")
            except Exception as e:
                _LOG.warning("加载案例失败 %s: %s", f.name, e)

    def reload(self) -> None:
        """热重载工艺库。
                English:
        Hot-reload craft library.
        """
        self._loaded = False
        self._playbooks.clear()
        self._genres.clear()
        self._cases.clear()
        self.load()

    # ── 查询接口 ──
    # [EN] ── Query interface ──
    def get_playbook(self, name: str) -> dict | None:
        """获取指定 playbook。
                English:
        Get the specified playbook.
        """
        return self._playbooks.get(name)

    def get_all_playbooks(self) -> dict[str, dict]:
        """获取所有 playbook。
                English:
        Get all playbooks.
        """
        return dict(self._playbooks)

    def get_genre(self, genre_name: str) -> dict | None:
        """获取指定类型档案。
                English:
        Get the specified genre profile.
        """
        # 支持模糊匹配
        # [EN] Support fuzzy matching
        for key, data in self._genres.items():
            if genre_name in key or key in genre_name:
                return data
        return None

    def get_all_genres(self) -> dict[str, dict]:
        """获取所有类型档案。
                English:
        Get all genre profiles.
        """
        return dict(self._genres)

    def get_case(self, case_name: str) -> str | None:
        """获取指定案例。
                English:
        Get the specified case.
        """
        return self._cases.get(case_name)

    def get_all_cases(self) -> dict[str, str]:
        """获取所有案例。
                English:
        Get all cases.
        """
        return dict(self._cases)

    def get_relevant_playbooks(self, genre: str, structure: str) -> list[dict]:
        """获取与指定类型/结构相关的 playbook。
                English:
        Get playbooks related to the specified genre/structure.
        """
        relevant = []
        for name, pb in self._playbooks.items():
            # 检查 playbook 是否标记了适用类型
            # [EN] Check whether a playbook is marked with an applicable type
            if "适用类型" in pb:
                if genre in pb["适用类型"] or structure in pb["适用类型"]:
                    relevant.append(pb)
            elif "通用" in name or "基础" in name:
                relevant.append(pb)
        return relevant

    def get_relevant_cases(self, genre: str) -> list[str]:
        """获取与指定类型相关的案例。
                English:
        Get cases related to the specified genre.
        """
        relevant = []
        for name, content in self._cases.items():
            if genre in name or "通用" in name:
                relevant.append(content)
        return relevant


# 全局单例
# [EN] Global singleton
craft_loader = CraftLoader()