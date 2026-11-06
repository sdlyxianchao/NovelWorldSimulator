#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把中英两份 README 摆成「仓库该有的样子」。

两个远端要的**门面不一样**：

    GitHub → `README.md` 是**英文**（国际访客先看到英文），中文放 `README.zh-CN.md`
    Gitee  → `README.md` 是**中文**，英文放 `README.en.md`

源码目录里则是 `README.md`（中文）+ `README_EN.md`（英文）。所以每次发布都要**换位**，
而换位不只是改文件名 —— 两份 README 顶上的语言条互相指着对方，不跟着改就会
「点『English』还在原地」。

    python publish/readme_variant.py github <发布工作区>
    python publish/readme_variant.py gitee  <发布工作区>

★★★ 为什么单独一个脚本，而不是在 publish.ps1 里写几行 Replace
    PowerShell 那边要处理中文编码（BOM / 无 BOM）、要数命中次数、要判坏链，
    写起来全是引号和转义。这里用 Python 一次做完，并且**把判据也写在同一处**：
    换位之后两条 README 里的相对链接必须全都在盘上 —— 门面文档里点开是 404，
    比没有 README 更难看。

★★★ 为什么替换要「断言命中 1 次」而不是 `str.replace` 一把梭
    `README.md` 这个字符串在中文版里出现不止一次（比如 `samples/README.md`）。
    拿它做全局替换会把**别的链接**改坏，而且坏得很整齐、看不出来。
    所以只认 `[English](README_EN.md)` / `[中文](README.md)` 这两个**完整**的语言条，
    命中数不是 1 就报错停下 —— 那说明 README 的语言条被改过，得人看一眼。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ZH = 'README.md'
EN = 'README_EN.md'

# 换位后各自的新名字
GH_ZH = 'README.zh-CN.md'
GH_EN = 'README.md'
GI_ZH = 'README.md'
GI_EN = 'README.en.md'

# 语言条（完整形态，含方括号）—— 只认这两个，别的一律不碰
ZH_LANG = '[English](README_EN.md)'
EN_LANG = '[中文](README.md)'

LINK_RE = re.compile(r'!?\[[^\]]*\]\(\s*<?([^)>]+?)>?\s*\)')
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
SKIP_PREFIX = ('http://', 'https://', 'mailto:', '#', 'data:', 'ftp://')


def read(p: Path) -> str:
    # newline='' 保留原样；写回时统一 LF，避免 Windows 上整文件 diff
    with open(p, encoding='utf-8', newline='') as fh:
        return fh.read().replace('\r\n', '\n')


def write(p: Path, text: str) -> None:
    with open(p, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


def swap(text: str, old: str, new: str, *, what: str, where: Path) -> str:
    """把语言条换掉，并且要求**恰好命中一次**。

    0 次 = README 结构变了（或这份文件根本不对）；2 次以上 = 不能确定该改哪一处。
    两种都该停下来让人看，而不是猜一个。
    """
    n = text.count(old)
    if n != 1:
        raise SystemExit(
            f'[FAIL] {where.name} 里 {what} 出现 {n} 次（要求恰好 1 次）：{old!r}\n'
            f'       语言条被改过？先看一眼再发。'
        )
    return text.replace(old, new, 1)


def broken_links(md: Path) -> list[str]:
    """返回这份 markdown 里**指向本机不存在的东西**的相对链接。

    只查这一份 / 这两份文件，不做全库扫描 —— 全库那些是历史遗留，
    混进来会淹掉「这次换位有没有改坏」这个真正要回答的问题。
    """
    base = md.parent
    text = read(md)
    bad: list[str] = []
    for m in list(LINK_RE.finditer(text)) + list(IMG_RE.finditer(text)):
        raw = m.group(1).strip()
        if not raw or raw.lower().startswith(SKIP_PREFIX):
            continue
        target = raw.split('#', 1)[0].split('?', 1)[0].strip()
        if not target:
            continue                      # 纯锚点（#section）
        # 只查「看起来像本仓库里的路径」：带协议头/绝对路径的已经在上面跳过了
        p = (base / target).resolve()
        if not p.exists():
            bad.append(f'{md.name} → {raw}')
    return bad


def variant(mode: str, dst: Path) -> int:
    zh_src = dst / ZH
    en_src = dst / EN
    for p in (zh_src, en_src):
        if not p.exists():
            print(f'[FAIL] 工作区里没有 {p.name}：{dst}')
            return 2

    zh = read(zh_src)
    en = read(en_src)

    if mode == 'github':
        # 英文当门面，中文挪到 README.zh-CN.md
        en = swap(en, EN_LANG, '[中文](README.zh-CN.md)',
                  what='英文版的语言条', where=en_src)
        zh = swap(zh, ZH_LANG, '[English](README.md)',
                  what='中文版的语言条', where=zh_src)
        out_zh, out_en = GH_ZH, GH_EN
    elif mode == 'gitee':
        # 中文当门面，英文挪到 README.en.md
        zh = swap(zh, ZH_LANG, '[English](README.en.md)',
                  what='中文版的语言条', where=zh_src)
        # 英文版里那句 [中文](README.md) 正好仍然指向中文门面，不用改
        out_zh, out_en = GI_ZH, GI_EN
    else:
        print(f'[FAIL] 不认识的模式：{mode}（只有 github / gitee）')
        return 2

    write(dst / out_en, en)
    if out_zh != out_en:
        write(dst / out_zh, zh)

    # 换位后旧名字要清掉，否则仓库里同时躺着三份 README，谁也说不清哪份是门面
    for stale in (ZH, EN):
        if stale not in (out_zh, out_en):
            p = dst / stale
            if p.exists():
                p.unlink()

    print(f'  [OK] {mode}: 门面 {out_en}（{len(en):,} 字符）'
          f'｜另一语言 {out_zh}（{len(zh):,} 字符）')

    bad = []
    for name in (out_zh, out_en):
        bad += broken_links(dst / name)
    if bad:
        print(f'  [FAIL] {mode} 的 README 里有 {len(bad)} 个坏链：')
        for b in bad[:12]:
            print(f'         {b}')
        if len(bad) > 12:
            print(f'         …… 还有 {len(bad) - 12} 个')
        return 1
    print(f'  [OK] {mode}: 两份 README 的相对链接全部落在盘上')
    return 0


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    mode = sys.argv[1].lower()
    dst = Path(sys.argv[2]).resolve()
    if not dst.is_dir():
        print(f'[FAIL] 目录不存在：{dst}')
        return 2
    return variant(mode, dst)


if __name__ == '__main__':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    raise SystemExit(main())
