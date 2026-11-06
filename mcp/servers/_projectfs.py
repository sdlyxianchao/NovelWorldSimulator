# -*- coding: utf-8 -*-
"""项目文件夹读取助手（给 mcp/servers/ 下的服务器共用）。

只做「读」——MCP 服务器是外部进程，绝不允许改小说数据。
这是刻意的：软件的铁律是「程序永不反写项目文件夹」（设计稿 §1），
一个跑在独立进程里的服务器更不该有写权限。

目录约定（设计稿 §10.1）：

    Projects/<项目名>/
    ├── 设定集/                  ← 项目级：人物.yaml / 世界观.md / 伏笔与悬线.yaml ...
    ├── 第N次模拟yyyy-MM-dd-HH-mm/
    │   ├── 本地设定集/           ← 本次运行冻结的设定
    │   ├── 每天的生活/           ← 每日叙事体（小说参考素材）
    │   ├── 关键事件/             ← 每事件一卡
    │   └── 考据笔记.md / 运行小结.md ...

定位项目目录的优先级：
    --project-dir <路径>  >  环境变量 NWS_PROJECT_DIR  >  当前工作目录

English:
Project folder reading helper (shared by servers under mcp/servers/).
Only do "read" — MCP servers are external processes, absolutely not allowed to modify novel
data.
This is intentional: the software's iron rule is "the program never writes back to the project
folder" (design doc §1),
a server running in a separate process even less should have write permission.
Directory conventions (design doc §10.1):
    Projects/<project name>/
Priority for locating the project directory:
    --project-dir <path>  >  environment variable NWS_PROJECT_DIR  >  current working directory
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import yaml

# ── 目录名常量（集中放，改约定时只改这里）──
# [EN] ── Directory name constants (centralized; when conventions change, only change here) ──
SETTINGS_DIR = '设定集'
LOCAL_SETTINGS_DIR = '本地设定集'
DAILY_DIR = '每天的生活'
EVENT_DIR = '关键事件'
RUN_PATTERN = re.compile(r'^第(\d+)次模拟')

# 设定集里的九件套 + 派生文件
# [EN] The nine-piece set in the setting collection + derived files
CHARACTERS = '人物.yaml'
WORLDVIEW = '世界观.md'
PLACES = '地点.yaml'
RELATIONS = '关系.yaml'
FORESHADOW = '伏笔与悬线.yaml'
PLOT = '剧情走向.md'
GENRE_CARD = '类型卡.yaml'
STYLE_CARD = '风格卡.yaml'
PROGRESS = '故事进度.yaml'
STORY_SO_FAR = '已发生故事线.md'

TEXT_SUFFIXES = {'.md', '.txt', '.yaml', '.yml', '.json'}


class ProjectNotFound(Exception):
    """项目目录不存在或不像一个项目 —— 转成 isError 响应，别让客户端崩。
        English:
    Project directory does not exist or does not look like a project — turn into an isError
    response, don't let the client crash.
    """


# ══════════════════════════════════════════════════════════════
#  定位
# [EN] Locate
# ══════════════════════════════════════════════════════════════
def resolve_project_dir() -> Path:
    """按优先级找出项目目录，并做基本合理性检查。
        English:
    Find the project directory by priority, and do basic sanity checks.
    """
    explicit = '--project-dir' in sys.argv
    if explicit:
        i = sys.argv.index('--project-dir')
        candidate = sys.argv[i + 1] if i + 1 < len(sys.argv) else ''
    else:
        candidate = os.environ.get('NWS_PROJECT_DIR', '')

    root = Path(candidate).expanduser() if candidate else Path.cwd()
    if not root.exists():
        raise ProjectNotFound(
            f'项目目录不存在：{root}\n'
            '请在 mcp_servers.yaml 里给这个服务器传 --project-dir，'
            '或设置环境变量 NWS_PROJECT_DIR。')
    return root.resolve()


def looks_like_project(root: Path) -> bool:
    """是不是一个项目文件夹（有 .nwsproj、或至少有个设定集目录）。
        English:
    Whether it is a project folder (has .nwsproj, or at least a 设定集 directory).
    """
    if not root.exists():
        return False
    if any(root.glob('*.nwsproj')):
        return True
    return (root / SETTINGS_DIR).is_dir() or any(
        d.is_dir() and RUN_PATTERN.match(d.name) for d in root.iterdir())


def settings_dir(root: Path) -> Path | None:
    """项目级设定集；没有就退到最近一次运行里的本地设定集。
        English:
    Project-level setting collection; if none, fall back to the local setting collection in the most
    recent run.
    """
    project_level = root / SETTINGS_DIR
    if project_level.is_dir() and any(project_level.iterdir()):
        return project_level
    run = latest_run_dir(root)
    if run and (run / LOCAL_SETTINGS_DIR).is_dir():
        return run / LOCAL_SETTINGS_DIR
    return project_level if project_level.is_dir() else None


def run_dirs(root: Path) -> list[Path]:
    """所有运行文件夹，按序号升序。
        English:
    All run folders, in ascending order by index.
    """
    if not root.is_dir():
        return []
    found = [(int(m.group(1)), d) for d in root.iterdir()
             if d.is_dir() and (m := RUN_PATTERN.match(d.name))]
    return [d for _, d in sorted(found, key=lambda t: t[0])]


def latest_run_dir(root: Path) -> Path | None:
    runs = run_dirs(root)
    return runs[-1] if runs else None


# ══════════════════════════════════════════════════════════════
#  读
# [EN] Read
# ══════════════════════════════════════════════════════════════
def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def read_yaml(path: Path) -> object:
    """宽容解析：小说项目里的 yaml 可能是人手写的，格式不保证规范。
        English:
    Lenient parsing: yaml in a novel project may be hand-written, format is not guaranteed to be
    standard.
    """
    text = read_text(path)
    if not text.strip():
        return None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def as_list(data: object) -> list:
    """把 yaml 结果统一成列表：列表原样返回，字典包一层，None 给空表。
        English:
    Normalize yaml results into a list: return lists as-is, wrap dicts in a layer, give None an
    empty list.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 有的文件写成 {人物: [...]}，把内层列表提出来
        # [EN] Some files are written as {character: [...]}, extract the inner list
        for v in data.values():
            if isinstance(v, list):
                return v
        return [data]
    return []


def characters(root: Path) -> list[dict]:
    """全部人物卡。
        English:
    All character cards.
    """
    sd = settings_dir(root)
    if not sd:
        return []
    return [c for c in as_list(read_yaml(sd / CHARACTERS))
            if isinstance(c, dict)]


def find_character(root: Path, name: str) -> dict | None:
    """按姓名查人物，支持模糊（「沈」能命中「主角」）。
        English:
    Look up a character by name, supports fuzzy matching ("沈" can match "主角").
    """
    people = characters(root)
    for c in people:
        if str(c.get('姓名', '')).strip() == name.strip():
            return c
    for c in people:
        if name.strip() and name.strip() in str(c.get('姓名', '')):
            return c
    return None


def foreshadows(root: Path) -> list[dict]:
    sd = settings_dir(root)
    if not sd:
        return []
    return [f for f in as_list(read_yaml(sd / FORESHADOW)) if isinstance(f, dict)]


def progress_nodes(root: Path) -> list[dict]:
    """故事进度表的节点列表。
        English:
    The node list of the story progress table.
    """
    sd = settings_dir(root)
    if not sd:
        return []
    data = read_yaml(sd / PROGRESS)
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return [n for n in v if isinstance(n, dict)]
    return [n for n in as_list(data) if isinstance(n, dict)]


def iter_text_files(root: Path, *, include_runs: bool = True):
    """遍历可检索的文本文件。跳过隐藏目录与二进制。
        English:
    Traverse searchable text files. Skip hidden directories and binaries.
    """
    if not root.is_dir():
        return
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = p.relative_to(root)
        if any(part.startswith('.') for part in rel.parts):
            continue
        if not include_runs and RUN_PATTERN.match(rel.parts[0] if rel.parts else ''):
            continue
        yield p


def search(root: Path, query: str, *, limit: int = 5, context: int = 1,
           include_runs: bool = True) -> list[dict]:
    """全文检索：返回带文件名与行号的命中片段。

    大小写不敏感（英文关键词有用）；中文本来就无大小写。
    
        English:
    Full-text search: return matched snippets with filename and line number.
        Case-insensitive (useful for English keywords); Chinese has no case anyway.
    """
    needle = query.strip().lower()
    if not needle:
        return []
    hits: list[dict] = []
    for path in iter_text_files(root, include_runs=include_runs):
        lines = read_text(path).splitlines()
        for i, line in enumerate(lines):
            if needle not in line.lower():
                continue
            lo = max(0, i - context)
            hi = min(len(lines), i + context + 1)
            hits.append({
                '文件': str(path.relative_to(root)).replace('\\', '/'),
                '行号': i + 1,
                '片段': '\n'.join(lines[lo:hi]).strip(),
            })
            if len(hits) >= limit:
                return hits
    return hits


def daily_files(root: Path) -> list[Path]:
    """所有「每天的生活」文件（跨运行文件夹），按名字排序。
        English:
    All "daily life" files (across run folders), sorted by name.
    """
    out: list[Path] = []
    for run in run_dirs(root):
        d = run / DAILY_DIR
        if d.is_dir():
            out.extend(sorted(p for p in d.iterdir()
                              if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES))
    return out


def event_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for run in run_dirs(root):
        d = run / EVENT_DIR
        if d.is_dir():
            out.extend(sorted(p for p in d.iterdir()
                              if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES))
    return out


def summarize_for_humans(root: Path) -> str:
    """给客户端看一眼的项目概况（工具返回的公共头部）。
        English:
    Project overview for the client to glance at (common header returned by tools).
    """
    parts = [f'项目目录：{root}']
    if not looks_like_project(root):
        parts.append('⚠ 这个目录里没找到 .nwsproj 或设定集/，可能不是小说项目。')
    sd = settings_dir(root)
    if sd:
        parts.append(f'设定集：{sd.relative_to(root)}（{len(list(sd.iterdir()))} 个文件）')
    runs = run_dirs(root)
    parts.append(f'运行文件夹：{len(runs)} 次'
                 + (f'，最新 {runs[-1].name}' if runs else ''))
    people = characters(root)
    if people:
        names = '、'.join(str(c.get('姓名', '?')) for c in people[:12])
        parts.append(f'人物 {len(people)} 位：{names}')
    return '\n'.join(parts)
