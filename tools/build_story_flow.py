# -*- coding: utf-8 -*-
"""把**已有的推演**补上 `剧情总览.json`（回填）。

用户 2026-10-26：
    「另外，请在这一次处理中把目前和之前已经进行的推演的数据由你生成一下，
      后续的数据则由软件自动生成」

★ "后续自动"落在两处（`sim/loop` 的日界与收工，见 `_refresh_story_flow`）；
  这个脚本只负责**已经跑过的那些** —— 它们跑在功能出现之前，盘上没有那份文件。

★ 生成逻辑**不在这里**：走 `plot.flow.ensure_flow`，和界面、和推演循环是同一份。
  这个脚本要是自己再算一遍，就会出现"脚本补出来的图和界面画的图不一样"
  （本项目最贵的一类 bug：同一件事两处实现）。

跑法：
    .venv\\Scripts\\python.exe tools/build_story_flow.py              # 所有项目
    .venv\\Scripts\\python.exe tools/build_story_flow.py --project 望江楼模拟项目
    .venv\\Scripts\\python.exe tools/build_story_flow.py --force      # 已有也重算

English:
Backfill `剧情总览.json` for **existing runs**. ★ "Automatically later" lives in two hooks
(`sim/loop`, day boundary + wrap-up, see `_refresh_story_flow`); this script only covers runs that
happened before the feature existed and therefore have no such file. ★ The generation logic is **not
here**: it goes through `plot.flow.ensure_flow`, the same one the UI and the loop use -- a second copy
would produce "the script's chart differs from the UI's chart", the most expensive class of bug in
this project.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                   # noqa: E402
from plot import flow as PF                              # noqa: E402
from store.project import list_run_dirs                  # noqa: E402


def _projects(root: Path, want: str = '') -> list[Path]:
    if not root.is_dir():
        return []
    out = [d for d in sorted(root.iterdir())
           if d.is_dir() and ((d / f'{d.name}.nwsproj').is_file() or (d / '设定集').is_dir())]
    if want:
        out = [d for d in out if d.name == want]
    return out


def build_one(project: Path, run: Path, *, force: bool) -> dict:
    data = PF.ensure_flow(project, run, force=force)
    s = data.get('stats') or {}
    return {'run': run.name, 'points': int(s.get('points') or 0),
            'played': int(s.get('played') or 0), 'days': int(s.get('days') or 0),
            'scenes': int(s.get('scenes') or 0), 'choices': int(s.get('choices') or 0),
            'path': str(PF.flow_path(run))}


def main() -> int:
    ap = argparse.ArgumentParser(description='回填剧情总览')
    ap.add_argument('--project', default='', help='只处理这个项目（文件夹名）')
    ap.add_argument('--root', default='', help='项目根目录（默认取配置里的）')
    ap.add_argument('--force', action='store_true', help='已有也重算')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    root = Path(a.root) if a.root else Path(CFG.projects_dir())
    projects = _projects(root, a.project)
    if not projects:
        print(f'没有找到项目：{root}')
        return 0

    total = 0
    for proj in projects:
        runs = list_run_dirs(proj)
        if not runs:
            if not a.quiet:
                print(f'\n== {proj.name}：没有推演')
            continue
        print(f'\n== {proj.name}（{len(runs)} 次推演）')
        for run in runs:
            try:
                r = build_one(proj, run, force=a.force)
            except Exception as e:                           # noqa: BLE001
                print(f'  ✗ {run.name}：{e!r}')
                continue
            total += 1
            print(f'  ✓ {r["run"]}：{r["points"]} 站 / 演过 {r["played"]} 站 / '
                  f'{r["days"]} 天 {r["scenes"]} 幕 / 选择点 {r["choices"]}')
            if not a.quiet:
                print(f'      → {r["path"]}')
    print(f'\n共处理 {total} 次推演。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
