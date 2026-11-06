#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交叉编译三个启动器（setup / start / uninstall）× 四个目标平台。

产出（`launchers/dist/<系统>-<架构>/`）
--------------------------------------
    windows-amd64/  start.exe   setup.exe   uninstall.exe
    linux-amd64/    start       setup       uninstall
    darwin-arm64/   start       setup       uninstall      （Apple Silicon）
    darwin-amd64/   start       setup       uninstall      （Intel Mac）

默认还会把**本机平台**那一套复制到工程根目录（Windows 上就是三个 .exe），
于是这台机器上"双击 start.exe"就是最终形态。`--no-root` 可以关掉。

用法
----
    .venv/Scripts/python.exe launchers/build.py
    .venv/Scripts/python.exe launchers/build.py --only windows/amd64
    .venv/Scripts/python.exe launchers/build.py --no-root

★★ 为什么编译完还要**逐个读文件头**（不是多此一举）
----------------------------------------------------
实测（2026-10-10）：

    GOOS=linux go build -ldflags "-H windowsgui"   → rc=0、**不报错、不警告**，
                                                     但产出的是 Windows PE（头 4 字节 4d5a）！
                                                     丢到 Linux 上根本跑不起来。
    GOOS=linux go build -ldflags "-s -w"           → 正常 ELF（7f454c46）✓
    GOOS=windows go build -ldflags "-H windowsgui" → PE 子系统 = 2（GUI，无控制台）✓

也就是说 `-H windowsgui` **只能给 windows 目标加**，加错了 Go 不会拦你。
所以这里做了两道自检：
  ① **格式对不对**（ELF / Mach-O / PE 各认各的魔数）—— 防"拷错了平台"；
  ② **Windows 的 PE 子系统必须是 2（GUI）** —— 防"忘了加 -H windowsgui"
     （子系统 =3 是控制台程序，双击就是一个黑框，正是这次要消灭的东西）。
这两条都是**读字节就能判**，不必真跑起来。

English:
Cross-compile three launchers (setup / start / uninstall) × four target platforms.
Output (`launchers/dist/<os>-<arch>/`)
--------------------------------------
    windows-amd64/  start.exe   setup.exe   uninstall.exe
    linux-amd64/    start       setup       uninstall
    darwin-arm64/   start       setup       uninstall      (Apple Silicon)
    darwin-amd64/   start       setup       uninstall      (Intel Mac)
By default also copies the **native platform** set to the project root directory (on Windows
that's the three .exe),
so on this machine "double-click start.exe" is the final form. `--no-root` can turn this off.
Usage
----
    .venv/Scripts/python.exe launchers/build.py
    .venv/Scripts/python.exe launchers/build.py --only windows/amd64
    .venv/Scripts/python.exe launchers/build.py --no-root
★★ Why after compiling we still **read each file header one by one** (it's not superfluous)
----------------------------------------------------
Field test (2026-10-10):
    GOOS=linux go build -ldflags "-H windowsgui"   → rc=0, **no error, no warning**,
                                                     but the output is a Windows PE (first 4 bytes 4d5a)!
                                                     Dropped on Linux it simply won't run.
    GOOS=linux go build -ldflags "-s -w"           → normal ELF (7f454c46) ✓
    GOOS=windows go build -ldflags "-H windowsgui" → PE subsystem = 2 (GUI, no console) ✓
In other words `-H windowsgui` **can only be added to the windows target**; if you add it wrong,
Go won't stop you.
So two self-checks are done here:
  ① **Is the format right** (ELF / Mach-O / PE each recognizes its own magic number) -- prevents "copied the wrong platform";
  ② **Windows PE subsystem must be 2 (GUI)** -- prevents "forgot to add -H windowsgui"
     (subsystem = 3 is a console program, double-click gives a black box, exactly what this is meant to eliminate).
Both of these are **decidable by reading bytes**, no need to actually run it.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
SRC = APP / 'launchers'
DIST = SRC / 'dist'

#: (GOOS, GOARCH, 后缀)。顺序即报告顺序。
# [EN] : (GOOS, GOARCH, suffix). Order is report order.
TARGETS: tuple[tuple[str, str, str], ...] = (
    ('windows', 'amd64', '.exe'),
    ('linux', 'amd64', ''),
    ('darwin', 'arm64', ''),
    ('darwin', 'amd64', ''),
)
MODES = ('setup', 'start', 'uninstall')

#: Go 工具链。默认走隔离目录（不动系统环境）；有 `NWS_GO` 就听它的。
# [EN] : Go toolchain. Defaults to an isolated directory (doesn't touch system environment); if
# [EN] `NWS_GO` exists, obey it.
DEFAULT_GO = Path(r'C:\Users\chao\.workbuddy\binaries\go\1.27.2\go')

MAGIC = {
    'windows': (b'MZ',),
    'linux': (b'\x7fELF',),
    # Mach-O 的四种魔数：64/32 位、大端/小端。我们出的都是 64 位小端（cffaedfe）。
    # [EN] Mach-O's four magic numbers: 64/32-bit, big-endian/little-endian. Ours are all 64-bit
    # [EN] little-endian (cffaedfe).
    'darwin': (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe',
               b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'),
}


def go_root() -> Path:
    for c in (os.environ.get('NWS_GO', ''), os.environ.get('GOROOT', '')):
        if c and (Path(c) / 'bin' / 'go.exe').exists():
            return Path(c)
    if (DEFAULT_GO / 'bin' / 'go.exe').exists():
        return DEFAULT_GO
    print('✗ 找不到 Go 工具链。设一下 NWS_GO，或装到 ' + str(DEFAULT_GO))
    sys.exit(2)


def version_tag() -> str:
    """版本串 = 日期 + 源码内容哈希前 8 位。

    ★ 为什么用**内容哈希**而不是 git 版本号：这个工程平时不一定在 git 里
      （交付形态是"一个绿色目录"），而"这个 exe 是哪份源码编的"必须**当场可查**。
      把哈希写进 `--selftest` 的输出里，就能回答"用户手上这个启动器是不是最新那版"。
    
        English:
    Version string = date + first 8 chars of source content hash.
        ★ Why use **content hash** instead of git version: this project isn't necessarily in git usually
          (the delivery form is "a green directory"), and "which source this exe was compiled from" must be **verifiable on the spot**.
          Write the hash into the `--selftest` output, then you can answer "is the launcher in the user's hands the latest version".
    """
    import datetime
    h = hashlib.sha1()
    for f in sorted(SRC.glob('*.go')) + [SRC / 'go.mod']:
        h.update(f.read_bytes())
    return f'{datetime.date.today():%Y%m%d}-{h.hexdigest()[:8]}'


def build_env(root: Path) -> dict:
    env = dict(os.environ)
    env['PATH'] = str(root / 'bin') + os.pathsep + env.get('PATH', '')
    env['GOROOT'] = str(root)
    # 缓存/模块目录放在工具链旁边（**别放工程里**：工程在 OneDrive 下，
    # 几百 MB 的编译缓存会被同步反复扫，而且会拖慢每一次构建）。
    # [EN] Cache/module directory goes next to the toolchain (**don't put it in the project**: the project
    # [EN] is under OneDrive,
    # [EN] hundreds of MB of build cache would be repeatedly scanned by sync, and would slow down every
    # [EN] build).
    env.setdefault('GOCACHE', str(root.parent / 'cache'))
    env.setdefault('GOMODCACHE', str(root.parent / 'pkgmod'))
    env['GOFLAGS'] = '-mod=mod'
    env.setdefault('GOPROXY', 'https://mirrors.aliyun.com/goproxy/,direct')
    env['CGO_ENABLED'] = '0'
    return env


def ldflags(goos: str, mode: str, ver: str) -> str:
    parts = ['-s', '-w']
    # ★★ 这一行是本文件最要紧的一句：`-H windowsgui` 只给 windows。
    #    见文件头那一段实测 —— 给错了 Go 不报错，只会给你一个跑不起来的文件。
    # [EN] ★★ This line is the most important one in this file: `-H windowsgui` is only given to windows.
    # [EN] See the field test at the top of the file -- giving it wrong, Go won't error, it will only give
    # [EN] you a file that won't run.
    if goos == 'windows':
        parts.append('-H windowsgui')
    parts.append(f'-X main.mode={mode}')
    parts.append(f'-X main.version={ver}')
    return ' '.join(parts)


def host_key() -> str:
    """本机对应哪个目标目录（用来决定"根目录该放哪一套"）。
        English:
    Which target directory this machine corresponds to (used to decide "which set to put in the root
    directory").
    """
    import platform
    if sys.platform.startswith('win'):
        return 'windows-amd64'
    if sys.platform == 'darwin':
        m = platform.machine().lower()
        return 'darwin-' + ('arm64' if m in ('arm64', 'aarch64') else 'amd64')
    return 'linux-amd64'


def build_one(goexe: Path, env: dict, goos: str, arch: str, mode: str,
              ver: str, out: Path) -> bool:
    # ⚠ `go` 必须写**绝对路径**：Windows 的 CreateProcess **不会**用我们传进去的
    #   `env["PATH"]` 去找可执行文件（它只看父进程的 PATH），
    #   写成裸 `go` 会直接 FileNotFoundError [WinError 2]。
    # [EN] ⚠ `go` must be written as an **absolute path**: Windows CreateProcess **will not** use the
    # [EN] `env["PATH"]`
    # [EN] we pass in to find the executable (it only looks at the parent process's PATH),
    # [EN] writing bare `go` will directly FileNotFoundError [WinError 2].
    cmd = [str(goexe), 'build', '-trimpath',
           '-ldflags', ldflags(goos, mode, ver),
           '-o', str(out), '.']
    e = dict(env, GOOS=goos, GOARCH=arch)
    r = subprocess.run(cmd, cwd=str(SRC), env=e,
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    if r.returncode != 0:
        print(f'  ✗ {goos}/{arch} {mode}：{(r.stderr or r.stdout).strip()[:400]}')
        return False
    return True


def check_format(p: Path, goos: str) -> bool:
    """① 魔数对不对（这是拦"-H windowsgui 给错了平台"的第一道）。
        English:
    ① Is the magic number right (this is the first line of defense against "-H windowsgui given to
    the wrong platform").
    """
    head = p.read_bytes()[:4]
    return any(head.startswith(m) for m in MAGIC[goos])


def pe_subsystem(p: Path) -> int:
    """读 PE 头的 Subsystem 字段（2=GUI/无控制台，3=Console）。

    偏移位置：DOS 头 0x3c 处是 PE 头偏移；PE 头 0x5c 处是 Subsystem（2 字节）。
    
        English:
    Read the Subsystem field of the PE header (2=GUI/no console, 3=Console).
        Offset location: at DOS header 0x3c is the PE header offset; at PE header 0x5c is Subsystem (2 bytes).
    """
    d = p.read_bytes()
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    return struct.unpack_from('<H', d, pe + 0x5c)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description='交叉编译三个启动器')
    ap.add_argument('--only', default='', help='只编某个目标，如 windows/amd64')
    ap.add_argument('--no-root', action='store_true',
                    help='不把本机平台那一套复制到工程根目录')
    a = ap.parse_args()

    root = go_root()
    env = build_env(root)
    ver = version_tag()

    print('═' * 62)
    print('  编译启动器 · 小说世界AI模拟')
    print('═' * 62)
    print(f'  Go      {root}')
    print(f'  版本串  {ver}')
    print(f'  模式    {", ".join(MODES)}')
    print()

    targets = [t for t in TARGETS
               if not a.only or f'{t[0]}/{t[1]}' == a.only]
    if not targets:
        print(f'✗ --only {a.only} 不在目标列表里：'
              + ', '.join(f'{o}/{ar}' for o, ar, _ in TARGETS))
        return 2

    bad: list[str] = []
    made: dict[str, list[Path]] = {}
    for goos, arch, suffix in targets:
        d = DIST / f'{goos}-{arch}'
        d.mkdir(parents=True, exist_ok=True)
        outs: list[Path] = []
        print(f'  {goos}/{arch}')
        for mode in MODES:
            out = d / (mode + suffix)
            if not build_one(root / 'bin' / 'go.exe', env, goos, arch, mode,
                             ver, out):
                bad.append(f'{goos}/{arch} {mode} 编译失败')
                continue
            # ① 格式
            # [EN] ① Format
            if not check_format(out, goos):
                got = out.read_bytes()[:4].hex()
                bad.append(f'{goos}/{arch} {mode} 格式不对（头 4 字节 {got}，'
                           f'期望 {MAGIC[goos][0].hex()}）'
                           f'—— 十有八九是 `-H windowsgui` 加到了非 windows 目标上')
                continue
            # ② Windows 必须是 GUI 子系统
            # [EN] ② Windows must be GUI subsystem
            note = ''
            if goos == 'windows':
                sub = pe_subsystem(out)
                if sub != 2:
                    bad.append(f'{goos}/{arch} {mode} 的 PE 子系统是 {sub}'
                               f'（应为 2=GUI）—— 双击会弹出控制台')
                    continue
                note = f'  subsystem={sub}'
            if suffix != '.exe':
                # Windows 上 chmod 对 NTFS 意义有限，但打包/拷到 Unix 前先立好权限位，
                # 免得漏了这一步（Unix 上少了执行位就是"双击没反应"）。
                # [EN] On Windows chmod has limited meaning for NTFS, but set permission bits before packaging/copying
                # [EN] to Unix,
                # [EN] to avoid missing this step (on Unix, missing the execute bit means "double-click does nothing").
                out.chmod(0o755)
            outs.append(out)
            print(f'    ✓ {mode + suffix:16s} {out.stat().st_size:>9,} B{note}')
        made[f'{goos}-{arch}'] = outs

    # ── 本机平台那一套 → 工程根目录 ──
    # [EN] ── Native platform set → project root directory ──
    host = host_key()
    if not a.no_root and host in made:
        print(f'\n  复制本机平台（{host}）到工程根目录')
        # ⚠ 只拷**这一次真编出来的**（`made[host]`），不是照着 `MODES` 去 dist 里捞。
        #   原先按 `MODES` 拷有个**不报错但给错结果**的毛病：某个模式编失败时，
        #   dist 里留着**上一版**的那个文件，于是根目录变成"新的 setup + 旧的 start"
        #   混搭 —— 而判据 A5 是拿根目录和 dist 比，两边都被污染反而看不出来。
        # ⚠ 另一个现实问题：**应用正在运行时 `start.exe` 被占用**（Windows 不让人
        #   覆盖运行中的映像），原先是甩一个 `PermissionError` 的 traceback、
        #   半路停下 —— 那是最难查的一种收尾（干了一半）。现在说清楚并返回非 0。
        # [EN] ⚠ Only copy **what was actually built this time** (`made[host]`), not fetch from dist according
        # [EN] to `MODES`.
        # [EN] The original copy-by-`MODES` had a **silent-but-wrong** flaw: when some mode fails to build,
        # [EN] dist keeps **the previous version** of that file, so the root becomes "new setup + old start"
        # [EN] mismatched -- and criterion A5 compares root against dist, both sides polluted so it can't be
        # [EN] detected.
        # [EN] ⚠ Another real problem: **`start.exe` is locked while the app is running** (Windows doesn't let
        # [EN] you
        # [EN] overwrite a running image), originally it threw a `PermissionError` traceback,
        # [EN] stopping halfway -- that's the hardest kind of ending to debug (half done). Now it says clearly
        # [EN] and returns non-zero.
        for src in made[host]:
            dst = APP / src.name
            try:
                shutil.copy2(src, dst)
            except OSError as e:
                bad.append(f'拷不到 {dst.name}（{e}）'
                           f'—— 多半是它正在运行：把应用窗口关掉再重跑一次')
                continue
            print(f'    ✓ {dst.name}')

    print()
    if bad:
        print(f'✗ {len(bad)} 个问题：')
        for b in bad:
            print('   ', b)
        return 1
    n = sum(len(v) for v in made.values())
    print(f'✓ 全部通过：{n} 个可执行文件，{len(made)} 个平台')
    print(f'  产物在 {DIST}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
