# -*- coding: utf-8 -*-
"""验证安装器：桌面图标 / 开始菜单 / 卸载，三平台各自的产物都查一遍。

为什么要有这个脚本
------------------
安装器会往**用户桌面和开始菜单**写东西，这类改动不能靠「看着像对的」就交付。
但也不能为了测试就往真实桌面上放图标 —— 所以：

  - 所有真实写入都用 `--dest-root` 指向临时目录
  - Windows 的 .lnk **真建真读**：建完用 PowerShell 回读 TargetPath /
    IconLocation / WorkingDirectory / Description，逐项断言
  - macOS / Linux 的分支在本机（Windows）**强制切平台跑一遍**，
    真的把 .app 包和 .desktop 文件写出来，再校验内容与权限位
    （.icns 生成依赖 macOS 的 sips，在别处会优雅降级，这是预期行为）
  - 卸载后断言「安装时创建的每一项」都真的没了
  - 安全性断言：--purge 的删除目标里**绝不能出现小说项目目录**

产出：assets/screenshots/install_report.json

English:
Verify the installer: desktop icon / start menu / uninstall, checking each platform's artifacts.
Why this script exists
------------------
The installer writes to **the user's desktop and start menu**; such changes can't be shipped
just because "it looks right".
But we also can't put icons on the real desktop just for testing -- so:
  - All real writes use `--dest-root` pointing to a temp directory
  - Windows .lnk files are **really created and really read**: after creation, use PowerShell to read back TargetPath /
    IconLocation / WorkingDirectory / Description, and assert each one
  - The macOS / Linux branches are **force-switched to run** on this machine (Windows),
    really writing out the .app bundle and .desktop file, then validating content and permission bits
    (.icns generation depends on macOS's sips, and will gracefully degrade elsewhere; this is expected behavior)
  - After uninstall, assert that "every item created at install time" is really gone
  - Safety assertion: the deletion targets of --purge **must never include the novel project directory**
Output: assets/screenshots/install_report.json
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import platform_install as PI  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
ENV = dict(os.environ, PYTHONIOENCODING='utf-8')
report: dict = {'platform': PI.platform_key(), 'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"[OK]  " if ok else "[FAIL]"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return ok


def run_cli(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(APP_DIR / 'tools' / 'platform_install.py'),
                        *args],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=ENV, cwd=str(cwd or APP_DIR))
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def read_lnks(paths: list[Path]) -> tuple[dict, str]:
    """用 PowerShell 回读 .lnk 属性（Windows 专用）。返回 (信息, 诊断)。
        English:
    Read back .lnk properties using PowerShell (Windows-only). Returns (info, diagnostics).
    """
    return PI.read_shortcut_info(paths)


# ══════════════════════════════════════════════════════════════
#  ① 三个启动器（2026-10-10 起取代了原来那 9 个 shell / .bat 脚本）
# [EN] ① Three launchers (replaced the original 9 shell / .bat scripts starting 2026-10-10)
# ══════════════════════════════════════════════════════════════
def test_native_scripts() -> bool:
    """三个启动器：在不在、格式对不对、**各自认不认得自己的模式**。

    ★ 2026-10-10 改判：这一段原来查的是 `setup.bat` / `start.sh` / `*.command`
      的**编码、行尾、可执行位、bash 语法**。用户要求「删掉，只留 exe」，
      那 9 个脚本没了 —— 但**要守的事情一件都没少**，只是换成了新对象：

        旧的守                                新的守
        ─────────────────────────────────────────────────────────────
        文件在不在                            文件在不在
        GBK / CRLF / LF（shell 才有的毛病）   产物的**格式**与平台相符（PE/ELF/Mach-O）
        bash -n 语法通过                      **真的能启动**（跑一次 `--selftest`）
        "调对了子命令"                        三个 exe **各自认得自己的 mode**
                                              （同一份源码编三次，靠文件名分工）

      最后那一条是新的关键点：三个文件长得一模一样、只差一个编译期常量，
      所以"谁是谁"完全靠文件名 —— 建错一个名字，双击 setup 会变成启动程序。
    
        English:
    Three launchers: whether they exist, whether the format is right, and **whether each one
    recognizes its own mode**.
        ★ 2026-10-10 revised: this section used to check `setup.bat` / `start.sh` / `*.command`
          for their **encoding, line endings, executable bit, bash syntax**. The user asked to "delete them, keep only the exe",
          so those 9 scripts are gone -- but **nothing that needed guarding was lost**, it just switched to new objects:
            old guard                            new guard
            ─────────────────────────────────────────────────────────────
            whether the file exists              whether the file exists
            GBK / CRLF / LF (shell-only issues)  the **format** of the artifact matches the platform (PE/ELF/Mach-O)
            bash -n syntax passes                it **actually launches** (run `--selftest` once)
            "called the right subcommand"         the three exes **each recognize their own mode**
                                                  (same source compiled three times, divided by filename)
          The last one is the new key point: the three files look identical, differing only in one compile-time constant,
          so "who is who" relies entirely on the filename -- get one name wrong and double-clicking setup launches the app.
    """
    print('\n── 1. 三个启动器 ──')
    ok = True
    plat = PI.platform_key()
    sfx = '.exe' if plat == 'windows' else ''
    modes: dict[str, str] = {}
    versions: set[str] = set()

    for mode in ('setup', 'start', 'uninstall'):
        exe = APP_DIR / (mode + sfx)
        good = exe.exists()
        note = ''
        if good:
            raw = exe.read_bytes()
            head = raw[:4]
            if plat == 'windows':
                import struct
                pe = struct.unpack_from('<I', raw, 0x3c)[0]
                sub = struct.unpack_from('<H', raw, pe + 0x5c)[0]
                # 子系统 = 2（GUI）才**双击不弹控制台**；=3 是控制台程序。
                # [EN] Subsystem = 2 (GUI) is what makes **double-click not pop up a console**; =3 is a console
                # [EN] program.
                good = head.startswith(b'MZ') and sub == 2
                note = f'subsystem={sub}  {len(raw):,}B'
            elif plat == 'macos':
                good = head in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe',
                                b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce')
                note = f'{len(raw):,}B'
            else:
                good = head.startswith(b'\x7fELF')
                note = f'{len(raw):,}B'
        ok &= rec(f'{mode}{sfx} 在、格式与平台相符', good,
                  note if exe.exists() else '缺失')

        if not good:
            continue
        # 真跑一次自检：**"能启动、不崩、模式认得对"**只有真跑才知道。
        # [EN] Actually run a self-check once: **"starts, doesn't crash, mode is recognized correctly"** can
        # [EN] only be known by really running it.
        import json as _json
        import tempfile
        out = Path(tempfile.gettempdir()) / f'nws_vi_{mode}.json'
        if out.exists():
            out.unlink()
        subprocess.run([str(exe), '--selftest', str(out)],
                       capture_output=True, cwd=str(APP_DIR), timeout=180)
        got = _json.loads(out.read_text(encoding='utf-8')) if out.exists() else {}
        modes[mode] = got.get('mode', '')
        if got.get('version'):
            versions.add(got['version'])

    ok &= rec('三个启动器**各自认得自己的模式**'
              '（同一份源码编三次、靠文件名分工 —— 名字错了"装"会变成"启动"）',
              all(modes.get(m) == m for m in ('setup', 'start', 'uninstall')),
              str(modes))
    ok &= rec('三个启动器是**同一次构建**出来的（版本串一致 —— '
              '防"根目录混着新旧两版"）',
              len(versions) == 1 and bool(versions), str(sorted(versions)))
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ② --dry-run 不许写任何文件
# [EN] ② --dry-run must not write any files
# ══════════════════════════════════════════════════════════════
def test_dry_run() -> bool:
    print('\n── 2. --dry-run 不写文件 ──')
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        # ⚠ **先把项目根那份安装记录清掉**：这条判据问的是"dry-run 会不会**写**出记录"，
        #   如果**上一次跑剩下的**、或者**用户真的装过**的那份还在，
        #   这条就会红成一片，而且**下一次跑又变绿** —— 典型的"看环境脸色"的判据
        #   （2026-10-06 实测：连跑两次一红一绿）。
        #   先挪走，跑完由 `main()` 统一还原。
        # [EN] ⚠ **First clear out the install record at the project root**: this criterion asks whether
        # [EN] "dry-run will **write** a record".
        # [EN] If the one **left over from the last run** or the one the **user actually installed** is still
        # [EN] there,
        # [EN] this criterion will go all red, and **the next run will turn green again** -- a typical "moody
        # [EN] about the environment" criterion
        # [EN] (measured 2026-10-06: two consecutive runs, one red one green).
        # [EN] Move it away first, and `main()` will uniformly restore it after the run.
        stale = APP_DIR / PI.MANIFEST_NAME
        if stale.exists():
            stale.unlink()
        rc, out = run_cli(['install', '--dry-run', '--dest-root', str(dest)])
        leaked = [str(p.relative_to(dest)) for p in dest.rglob('*')]
        says = '新建快捷方式' in out or '应用菜单项' in out or '创建应用包' in out
        ok1 = rec('退出码 0 且预报了将做的改动', rc == 0 and says,
                  f'rc={rc}')
        ok2 = rec('目标目录里没有任何新文件', not leaked, f'泄漏 {leaked[:3]}')
        ok3 = rec('项目根没有留下安装记录',
                  not (APP_DIR / PI.MANIFEST_NAME).exists())
        return ok1 and ok2 and ok3


# ══════════════════════════════════════════════════════════════
#  ③ 本平台真实安装 + 回读 + 卸载（Windows 为主）
# [EN] ③ Real install + read-back + uninstall on this platform (mainly Windows)
# ══════════════════════════════════════════════════════════════
def test_real_platform() -> bool:
    plat = PI.platform_key()
    print(f'\n── 3. {plat} 真实安装 / 回读 / 卸载（临时 dest-root）──')
    manifest = APP_DIR / PI.MANIFEST_NAME
    backup = None
    if manifest.exists():                       # 别动用户已有的安装记录
    # [EN] Don't touch the user's existing install record
        backup = manifest.read_bytes()
        manifest.unlink()
    try:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            inst = PI.Installer(dest_root=dest, verbose=False)
            ok = rec('install() 返回成功', inst.install())
            created = list(inst.created)
            ok &= rec('安装记录已写入', inst.manifest_path.exists(),
                      f'{len(created)} 项')

            if plat == 'windows':
                lnks, lb_note = read_lnks([Path(p) for p in created])
                ok &= rec('快捷方式能被 PowerShell 回读', len(lnks) == len(created),
                          f'回读 {len(lnks)}/{len(created)}  {lb_note}')
                start = str(APP_DIR / ('start.exe' if PI.platform_key() == 'windows' else 'start'))
                targets = {v.get('target') for v in lnks.values()}
                ok &= rec('启动项指向 start 启动器', start in targets, start)
                roots = {v.get('workdir') for v in lnks.values()}
                ok &= rec('工作目录 = 程序目录', str(APP_DIR) in roots, str(APP_DIR))
                icons = [v.get('icon', '') for v in lnks.values()]
                # ★★ 判据**必须查到内容**，不能只看"路径里有没有 app_icon.ico"
                #   （2026-10-07 用户报「setup 跑完桌面图标还是老图标」）：
                #   旧版本这里只断言 `'app_icon.ico' in i` —— 这话在"图标是旧的"
                #   时候**照样成立**，所以整条链从来没有人守。
                #   现在两件事都要查：
                #     ① 路径是**带指纹**的副本（缓存按路径 key，换指纹才必然失效）；
                #     ② 那个文件的内容 == 当前图标代码画出来的那一份。
                # [EN] ★★ The criterion **must find the content**, not just check "whether the path contains
                # [EN] app_icon.ico"
                # [EN] (2026-10-07 user reported "after setup finishes, the desktop icon is still the old icon"):
                # [EN] The old version only asserted `'app_icon.ico' in i` here -- this statement still holds
                # [EN] when "the icon is old", so this entire chain was never guarded by anyone.
                # [EN] Now both things must be checked:
                # [EN] ① The path is a copy **with a fingerprint** (cache is keyed by path, so only a fingerprint
                # [EN] change necessarily invalidates it);
                # [EN] ② The content of that file == the one drawn by the current icon code.
                from image_gen.icon import asset_paths, icon_signature
                ico_paths = [i.split(',')[0] for i in icons if i]
                ok &= rec('快捷方式用的是**带指纹的** .ico 副本'
                          '（路径不变的话 Windows 图标缓存会一直给旧图）',
                          bool(ico_paths) and all(
                              f'app_icon.{icon_signature()[:8]}.ico' in i
                              for i in ico_paths),
                          ico_paths[0] if ico_paths else '（没有 icon）')
                want_ico = asset_paths()['app_ico']
                same_bytes = bool(ico_paths) and all(
                    Path(i).exists() and Path(i).read_bytes()
                    == want_ico.read_bytes() for i in ico_paths)
                ok &= rec('★ 图标**内容**就是当前设计画出来的那张'
                          '（逐字节比 `assets/app_icon.ico`）',
                          same_bytes,
                          f'{len(ico_paths)} 个快捷方式的 icon 都比过；'
                          f'当前 {want_ico.name} {want_ico.stat().st_size}B')

                # ── 换图标回归：把产物弄旧，看安装器认不认得出来 ──
                #   这是用户那次报障的**精确复现**：改过图标、产物却是旧的，
                #   此时跑 setup 必须**先重做产物**再建快捷方式。
                # [EN] -- Icon-change regression: make the artifact old, and see whether the installer recognizes it --
                # [EN] This is the **exact reproduction** of the user's reported failure: the icon was changed, but the
                # [EN] artifact was old,
                # [EN] at which point running setup must **remake the artifact first** before creating the shortcut.
                stale_ico = asset_paths()['app_ico']
                stamp_file = APP_DIR / 'assets' / '.icon_stamp'
                probe = None
                try:
                    from PIL import Image
                    probe = Image.new('RGB', (256, 256), (255, 0, 0))
                    probe.save(stale_ico)
                    stamp_file.write_text('stale-not-current', encoding='utf-8')
                    stale_probe = stale_ico.read_bytes()
                    dest2 = Path(td) / 'regress'
                    inst2 = PI.Installer(dest_root=dest2, verbose=False)
                    ok2 = inst2.install()
                    ok &= rec('★ 换图标回归：产物是旧的（红方块）时，'
                              '跑一次安装就**自动恢复成当前图标**',
                              ok2 and stale_ico.read_bytes() != stale_probe
                              and stale_ico.read_bytes() == want_ico.read_bytes(),
                              f'安装返回 {ok2}；{stale_ico.stat().st_size}B')
                    ok &= rec('★ 换图标回归：**新指纹**立刻反映到快捷方式上',
                              ok2 and f'app_icon.{icon_signature()[:8]}.ico'
                              in str(inst2.icon_ico()),
                              str(inst2.icon_ico()))
                except Exception as e:                           # noqa: BLE001
                    ok &= rec('★ 换图标回归：跑得起来', False, repr(e))
                finally:
                    # ⚠ **兜底还原**：这一组会**故意把真实产物弄坏**（红方块 +
                    #   脏指纹）。安装器正常时它会自己恢复；万一没恢复成
                    #   （比如安装器崩了），产物就留在红方块状态 ——
                    #   那这台机器上的图标就真的坏了。所以这里强制重做一遍，
                    #   无论如何不把现场留给下一个跑的人。
                    # [EN] ⚠ **Fallback restoration**: this group will **deliberately break the real artifact** (red square
                    # [EN] +
                    # [EN] dirty fingerprint). When the installer works normally it will recover by itself; if it doesn't
                    # [EN] recover
                    # [EN] (e.g. the installer crashed), the artifact stays in the red-square state --
                    # [EN] then the icons on this machine are really broken. So here we force a remake,
                    # [EN] and under no circumstances leave the mess for the next person who runs it.
                    try:
                        from image_gen.icon import ensure_assets
                        ensure_assets(force=True)
                        bad = stale_ico.read_bytes() != want_ico.read_bytes()
                        ok &= rec('兜底：换图标回归后产物已还原成当前图标',
                                  not bad, f'{stale_ico.stat().st_size}B')
                    except Exception as e:                       # noqa: BLE001
                        ok &= rec('兜底：换图标回归后产物已还原成当前图标',
                                  False, repr(e))
                sm = inst._sm_folder()
                un = sm / '卸载 小说世界AI模拟.lnk'
                ok &= rec('开始菜单文件夹里有「卸载」项',
                          str(un) in lnks and
                          lnks[str(un)]['target'] == str(
                              APP_DIR / ('uninstall.exe' if PI.platform_key() == 'windows' else 'uninstall')),
                          str(un))
                ok &= rec('桌面快捷方式存在',
                          (dest / 'Desktop' / '小说世界AI模拟.lnk').exists())
            elif plat == 'macos':
                bundle = dest / 'Applications' / '小说世界AI模拟.app'
                exe = bundle / 'Contents' / 'MacOS' / PI.SLUG
                plist = bundle / 'Contents' / 'Info.plist'
                ok &= rec('应用包结构完整',
                          exe.exists() and plist.exists() and
                          (bundle / 'Contents' / 'PkgInfo').exists())
                ok &= rec('可执行文件有执行位', exe.exists() and os.access(exe, os.X_OK))
                if exe.exists():
                    r = subprocess.run(['bash', '-n', str(exe)], capture_output=True)
                    ok &= rec('应用包内启动脚本语法通过', r.returncode == 0)
                txt = plist.read_text('utf-8') if plist.exists() else ''
                ok &= rec('Info.plist 关键字段齐全',
                          all(k in txt for k in ('CFBundleExecutable',
                                                 'CFBundleIdentifier', PI.SLUG)))
            else:
                apps = dest / '.local' / 'share' / 'applications'
                launcher = apps / f'{PI.SLUG}.desktop'
                uni = apps / f'{PI.SLUG}-uninstall.desktop'
                icon = (dest / '.local' / 'share' / 'icons' / 'hicolor'
                        / '256x256' / 'apps' / f'{PI.SLUG}.png')
                desk = dest / 'Desktop' / f'{PI.SLUG}.desktop'
                ok &= rec('应用菜单项 + 卸载项 + 图标 + 桌面图标齐全',
                          all(p.exists() for p in (launcher, uni, icon, desk)))
                txt = launcher.read_text('utf-8') if launcher.exists() else ''
                ok &= rec('Exec 指向 start 启动器、Path 指向程序目录、'
                          'Terminal=**false**'
                          '（启动器没有控制台：装依赖的进度由它自己的进度窗显示，'
                          '所以**不该**开终端）',
                          f'Exec={APP_DIR / "start"}' in txt
                          and f'Path={APP_DIR}' in txt and 'Terminal=false' in txt)
                ok &= rec('桌面图标双份（桌面 + 应用菜单内容一致）',
                          desk.exists() and desk.read_text('utf-8') == txt)
                ok &= rec('桌面图标有执行位', desk.exists() and os.access(desk, os.X_OK))

            # ── 卸载 ──
            # [EN] -- Uninstall --
            inst2 = PI.Installer(dest_root=dest, verbose=False)
            ok &= rec('uninstall() 返回成功', inst2.uninstall(assume_yes=True))
            left = [p for p in created if Path(p).exists()]
            ok &= rec('安装时创建的每一项都已被删除', not left,
                      f'残留 {left[:3]}' if left else '')
            ok &= rec('安装记录本身也清掉了', not inst.manifest_path.exists())
    finally:
        if backup is not None:
            manifest.write_bytes(backup)
        elif manifest.exists():
            manifest.unlink()
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ③ 命令行端到端：沙盒 install → 沙盒 uninstall（**不许碰真实记录**）
# [EN] ③ CLI end-to-end: sandbox install -> sandbox uninstall (**must not touch the real record**)
# ══════════════════════════════════════════════════════════════
def test_cli_e2e() -> bool:
    """`--dest-root` 是"把桌面/开始菜单整个挪到别处"的**测试沙盒**开关。

    ★ 2026-10-10 改判（这条原来是"install 到沙盒 → **不带** `--dest-root`
      也能靠工程根那条记录卸载"）。写新判据时先量了一遍旧行为，量出两个真问题：

        ① 沙盒 install 会把**真实**记录覆盖成 `dest_root=<临时目录>`；
        ② 于是用户下次**真卸载**会照着那条记录去临时目录里删 —— 桌面图标
           一个都没删掉，而且**返回成功**（"没有找到本程序创建的快捷方式"）。
           属于本项目最忌讳的"不报错、但给你错结果"。
        ③ 沙盒 uninstall 还会顺手把真实记录本身删掉（实测：`uninstall --yes
           --dest-root <空目录>` 报「已删除 1 项」—— 删的就是那条记录）。

      所以记录现在**跟着沙盒走**（见 `Installer.__init__`）。这一组改成守
      "**测试状态绝不可能碰到生产状态**"——比原来的断言更值钱，而且它
      守的是一个已经真实发生过的 bug，不是假想的。

    ⚠ 真实记录仍然先备份后还原：万一以后又有人在沙盒路径上写它，这一组会红，
      而不会把用户的记录吃掉。
    
        English:
    `--dest-root` is the **test sandbox** switch for "move the whole desktop/start menu somewhere
    else".
        ★ 2026-10-10 revised (this item used to be "install into the sandbox -> **without** `--dest-root`
          you can still uninstall relying on the record at the project root"). Before writing the new criteria I measured the old behavior once and found two real problems:
            ① Sandbox install overwrites the **real** record with `dest_root=<temp dir>`;
            ② so the next time the user does a **real uninstall** it follows that record and deletes inside the temp dir --
               not a single desktop icon gets deleted, and it **returns success** ("no shortcuts created by this program were found").
               This is the thing this project dreads most: "no error, but a wrong result".
            ③ Sandbox uninstall will also casually delete the real record itself (measured: `uninstall --yes
               --dest-root <empty dir>` reports "1 item deleted" -- and the thing deleted is that record).
          So the record now **follows the sandbox** (see `Installer.__init__`). This group has been changed to guard
          "**test state can never touch production state**" -- worth more than the original assertion, and it
          guards a bug that has actually happened, not a hypothetical one.
        ⚠ The real record is still backed up first then restored: if someone writes it on a sandbox path again in the future, this group goes red,
          instead of eating the user's record.
    """
    print('\n── 3. 命令行端到端（沙盒 install → 沙盒 uninstall）──')
    manifest = APP_DIR / PI.MANIFEST_NAME
    backup = manifest.read_bytes() if manifest.exists() else None
    ok = True
    try:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            rc, out = run_cli(['install', '--dest-root', str(dest)])
            ok &= rec('沙盒 install 退出码 0', rc == 0, f'rc={rc}')
            # ① 记录写在沙盒里
            # [EN] ① The record is written in the sandbox
            in_sandbox = dest / PI.MANIFEST_NAME
            ok &= rec('★ 安装记录写在**沙盒里**（`<dest-root>/.install_manifest.json`）',
                      in_sandbox.exists(), str(in_sandbox))
            data = PI.read_json(in_sandbox)
            created = data.get('created') or []
            ok &= rec('记录里存了安装根目录（供卸载时还原）',
                      data.get('dest_root') == str(dest),
                      str(data.get('dest_root')))
            stale = [p for p in created if not Path(p).exists()]
            ok &= rec('记录里的每一项都真实存在', not stale, f'{len(created)} 项')
            # ② 真实记录**一个字都没动**
            # [EN] ② The real record **was not touched at all**
            ok &= rec('★★ 工程根那条`.install_manifest.json`**没被碰过**'
                      '（否则用户下次真卸载会去沙盒里删、还报成功）',
                      manifest.read_bytes() == backup if backup is not None
                      else not manifest.exists(),
                      '存在' if manifest.exists() else '不存在')

            rc2, out2 = run_cli(['uninstall', '--yes', '--dest-root', str(dest)])
            ok &= rec('沙盒 uninstall 退出码 0', rc2 == 0, f'rc={rc2}')
            left = [p for p in created if Path(p).exists()]
            ok &= rec('沙盒里的快捷方式删干净了', not left,
                      f'残留 {left[:2]}' if left else '')
            ok &= rec('沙盒里的安装记录也清掉了', not in_sandbox.exists())
            ok &= rec('★★ 沙盒卸载**没有**顺手删掉工程根那条记录',
                      manifest.read_bytes() == backup if backup is not None
                      else not manifest.exists(),
                      '存在' if manifest.exists() else '不存在')
    finally:
        if backup is not None:
            manifest.write_bytes(backup)
        elif manifest.exists():
            manifest.unlink()
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ③b Windows 双击路径：真的跑一遍 setup.exe / uninstall.exe
# [EN] ③b Windows double-click path: actually run setup.exe / uninstall.exe once
# ══════════════════════════════════════════════════════════════
def test_wrapper_execution() -> bool:
    """用户双击的那个**可执行文件**，真跑一遍（`--dry-run`，不写任何文件）。

    ★ 2026-10-10 改：以前这里是 `cmd /c setup.bat --dry-run`，然后**断言它的
      stdout** 里有那几句话。现在启动器是**无控制台**的 GUI 程序 ——
      它**没有 stdout 可读**（写出去也没人要）。所以"输出正常"这条不能再靠
      `r.stdout` 来判。

      换成更有说服力的两层：
        ① **退出码**（老实话：这是启动器能给出的唯一"结果"）；
        ② **它自己写的任务日志** `logs/launcher_job.log` —— 那是进度窗把每一步的
           真实输出原样落下来的地方（就是用户在进度窗里看到的东西）。
           只看**这一趟新追加的那一段**（跑之前记下文件大小），不受历史影响。
      这样"它到底做了什么"仍然查得到，而且查的是**产品自己的产物**，不是我们的替身。
    
        English:
    The **executable** the user double-clicks gets run once for real (`--dry-run`, writes no files).
        ★ 2026-10-10 changed: this used to be `cmd /c setup.bat --dry-run`, then **assert on its
          stdout** containing those lines. Now the launcher is a **console-less** GUI program --
          it **has no stdout to read** (writing anything out is pointless). So "output is normal" can no longer be judged
          by `r.stdout`.
          Replaced with two more convincing layers:
            ① **exit code** (honestly: this is the only "result" a launcher can give);
            ② **the job log it writes itself** `logs/launcher_job.log` -- that is where the progress window drops the
               real output of each step verbatim (exactly what the user sees in the progress window).
               Only look at **the segment newly appended this run** (record the file size before running), unaffected by history.
          This way "what did it actually do" is still traceable, and what is inspected is **the product's own artifact**, not our stand-in.
    """
    if PI.platform_key() != 'windows':
        print('\n── 3b. 启动器实际执行（非 Windows，跳过）──')
        return True
    print('\n── 3b. 启动器实际执行（用户双击的就是这个）──')
    manifest = APP_DIR / PI.MANIFEST_NAME
    # ⚠ **要备份 + 还原**：这一支干的是"删掉安装记录，看 dry-run 会不会写回来"，
    #   以前是**无条件 unlink、不还原** —— 如果用户**真的装过**，
    #   跑一次验证就把他的安装记录**永久删掉**（以后卸载就清不干净快捷方式了）。
    #   旁边两支（`test_real_platform` / `test_cli_e2e`）一直是备份+还原的，这里跟上。
    # [EN] ⚠ **Must back up + restore**: this branch does "delete the install record, see whether dry-run
    # [EN] writes it back".
    # [EN] Previously it was **unconditional unlink, no restore** -- if the user **actually installed it**,
    # [EN] running the verification once would **permanently delete** their install record (afterwards
    # [EN] uninstall can no longer clean up the shortcuts properly).
    # [EN] The two branches next to it (`test_real_platform` / `test_cli_e2e`) have always backed up +
    # [EN] restored, so keep up here.
    backup = manifest.read_bytes() if manifest.exists() else None
    if manifest.exists():
        manifest.unlink()
    ok = True
    joblog = APP_DIR / 'logs' / 'launcher_job.log'
    # ⚠ `--skip-service`：不跳过的话启动器会先去 `novelservice.py prepare`
    #   （建 venv / 装依赖，环境没备好时要几分钟）—— 那是 `verify_mumu_service`
    #   那一支的事，这里只验"安装/卸载这条路走不走得通"。
    # [EN] ⚠ `--skip-service`: without skipping, the launcher will first go to `novelservice.py prepare`
    # [EN] (create venv / install dependencies, which takes several minutes when the environment isn't
    # [EN] ready) -- that's the business of
    # [EN] the `verify_mumu_service` branch; here we only verify "whether the install/uninstall path
    # [EN] works".
    for name, args, must in (
            ('setup.exe', ['--skip-service', '--dry-run'],
             ['小说世界AI模拟.lnk', 'uninstall', '演练']),
            # ⚠ `--yes`：2026-10-10 起卸载**先弹一个原生确认框**（那就是修
            #   "双击卸载从来卸不掉"的办法，见 `launchers/flow.go` 的 runUninstall）。
            #   不带 `--yes` 的话这一趟会**停在框上等点击** ⇒ 判据直接挂死。
            #   框本身有没有弹、点了「取消」会不会真不动手，由
            #   `verify_launchers.py` 的 F 组守（那边用对话框替身，不阻塞）。
            # [EN] ⚠ `--yes`: starting 2026-10-10, uninstall **first pops up a native confirmation dialog** (that's
            # [EN] the fix for
            # [EN] "double-click uninstall never uninstalls", see runUninstall in `launchers/flow.go`).
            # [EN] Without `--yes`, this run will **stop on the dialog waiting for a click** => the criterion just
            # [EN] hangs.
            # [EN] Whether the dialog itself pops up, and whether clicking "Cancel" really does nothing, are
            # [EN] guarded by
            # [EN] group F of `verify_launchers.py` (which uses a dialog stand-in and does not block).
            ('uninstall.exe', ['--dry-run', '--yes'],
             ['卸载', '小说世界AI模拟'])):
        before = joblog.stat().st_size if joblog.exists() else 0
        r = subprocess.run([str(APP_DIR / name), *args],
                           capture_output=True, cwd=str(APP_DIR),
                           stdin=subprocess.DEVNULL, timeout=300)
        chunk = ''
        if joblog.exists():
            chunk = joblog.read_bytes()[before:].decode('utf-8', 'replace')
        good = r.returncode == 0 and all(m in chunk for m in must)
        ok &= rec(f'{name} 跑通（退出码 0，且任务日志里有该有的内容）', good,
                  f'rc={r.returncode} 新日志 {len(chunk)}B' + ('' if good else
                                                               '  ' + chunk.strip()
                                                               .replace('\n', ' ')[-160:]))
    ok &= rec('dry-run 没有往项目里写任何东西', not manifest.exists())
    # 还原用户原有的安装记录（见上面那段注释）
    # [EN] Restore the user's original install record (see the comment block above)
    if backup is not None:
        manifest.write_bytes(backup)
    elif manifest.exists():
        manifest.unlink()
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ④ 另外两个平台：强制切平台跑真实写入
# [EN] ④ The other two platforms: force-switch platform and run real writes
# ══════════════════════════════════════════════════════════════
@contextlib.contextmanager
def _provided_launchers(plat: str):
    """强制切平台跑的时候，**临时**把该平台的启动器摆到工程根目录，跑完收走。

    ★ 为什么非要有这一手（2026-10-10 实测）：`Installer.install()` 第一件事是
      "启动器在不在"，不在就直接 `return False`。而本机（Windows）根目录只有
      `start.exe` / `uninstall.exe` / `setup.exe`；Linux / macOS 的那几个在
      `launchers/dist/<平台>/` 里 —— 交叉编译产物本来就该那么放，
      不可能三个平台的名字全摊在根目录（`start` 和 `start.exe` 还会打架）。

      于是"强制切平台"这一支必须自己把对应平台的那一套摆好，否则它测的
      根本不是"安装器的 Linux/macOS 分支对不对"，而是"这台机器上有没有
      Linux 启动器"。第一版就是这样，两条断言当场变红 —— 而且红的理由
      跟它想验的事情毫无关系。

    优先用**真产物**（`launchers/dist/`）；实在没有就放一个同名占位文件，
    因为这一支验的是**安装器的平台分支**，不是启动器本体
    （启动器本体由 `verify_launchers` 专职验）。
    
        English:
    When forcing a platform switch, **temporarily** place that platform's launcher at the project
    root, and take it away after the run.
        ★ Why this is necessary (measured 2026-10-10): the first thing `Installer.install()` does is
          "is the launcher there", and if not it directly `return False`. On this machine (Windows) the root dir only has
          `start.exe` / `uninstall.exe` / `setup.exe`; the Linux / macOS ones are in
          `launchers/dist/<platform>/` -- cross-compiled artifacts are supposed to go there anyway,
          it's impossible to spread all three platforms' names across the root dir (`start` and `start.exe` would also clash).
          So the "force platform switch" branch must set up the corresponding platform's set itself, otherwise what it tests
          is not at all "is the installer's Linux/macOS branch correct", but "does this machine have a
          Linux launcher". The first version was like this, and two assertions went red on the spot -- and the reason they went red
          had nothing to do with what it wanted to verify.
        Prefer the **real artifact** (`launchers/dist/`); if there really is none, put a same-named placeholder file,
        because this branch verifies the **installer's platform branch**, not the launcher itself
        (the launcher itself is verified by `verify_launchers` as its dedicated job).
    """
    made: list[Path] = []
    try:
        for mode in ('start', 'uninstall', 'setup'):
            dst = APP_DIR / mode
            if dst.exists():
                continue
            src = None
            for d in sorted((APP_DIR / 'launchers' / 'dist').glob(f'{plat}-*')):
                cand = d / mode
                if cand.exists():
                    src = cand
                    break
            if src is not None:
                shutil.copy2(src, dst)
            else:
                dst.write_bytes(b'')
            dst.chmod(0o755)
            made.append(dst)
        yield
    finally:
        for f in made:
            try:
                f.unlink()
            except OSError:
                pass


def test_other_platforms() -> bool:
    print('\n── 4. 其余平台分支（强制切平台，真实写文件到临时目录）──')
    ok = True
    for plat, label in (('linux', 'Linux'), ('macos', 'macOS')):
        with _provided_launchers(plat), tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            inst = PI.Installer(dest_root=dest, verbose=False,
                                manifest_path=dest / 'manifest.json')
            inst.plat = plat                     # 强制切平台
            # [EN] Force-switch platform
            good = inst.install()
            created = list(inst.created)
            names = [Path(p).name for p in created]
            ok &= rec(f'{label}: install() 成功且写出 {len(created)} 项', good,
                      ', '.join(names[:4]))
            inst.plat = plat
            inst.uninstall(assume_yes=True)
            left = [p for p in created if Path(p).exists()]
            ok &= rec(f'{label}: 卸载后无残留', not left,
                      f'残留 {left[:2]}' if left else '')
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  ⑤ 安全性：绝不删小说项目数据
# [EN] ⑤ Safety: never delete novel project data
# ══════════════════════════════════════════════════════════════


def test_safety() -> bool:
    print('\n── 5. 安全性 ──')
    inst = PI.Installer(verbose=False)
    proj = Path(inst.projects_dir).resolve()
    purge = [p.resolve() for p in inst._purge_targets()]
    targets = [Path(p) for p in inst._targets()]

    def under_project(p) -> bool:
        try:
            p.relative_to(proj)
            return True
        except ValueError:
            return False

    ok = rec('--purge 目标不含小说项目目录', not any(under_project(p) for p in purge),
             str(proj))
    ok &= rec('--purge 目标不含程序目录本身',
              all(p != APP_DIR.resolve() for p in purge))
    ok &= rec('卸载目标不含小说项目目录', not any(under_project(p) for p in targets))
    ok &= rec('卸载目标都在用户配置范围内',
              all(str(p).startswith((str(Path.home()), str(APP_DIR))) for p in targets),
              f'{len(targets)} 项')
    return bool(ok)


def main() -> int:
    print(f'  安装器验证 · 平台 {PI.platform_key()}')
    print(f'  程序目录 {APP_DIR}')
    # ★ **整趟跑之前先给安装记录存个档，跑完还原**。
    #   这套验证里有几支必须"先删掉记录看会不会被写回来"，各支自己也会备份还原；
    #   但支与支之间会互相留尾巴（`test_cli_e2e` 跑完可能留下一份），
    #   于是**同一条判据连跑两次一会红一会绿**（2026-10-06 实测）。
    #   统一在中枢做一次备份/还原，判据就不再"看环境脸色"。
    #   顺带也保住了用户**真装过**时那份记录 —— 以前跑一次验证就把它永久删了。
    # [EN] ★ **Before the whole run, archive the install record; restore after the run**.
    # [EN] Several branches in this verification set must "first delete the record to see whether it gets
    # [EN] written back", and each branch also backs up and restores itself;
    # [EN] but branches leave tails for each other (`test_cli_e2e` may leave one behind after it runs),
    # [EN] so **the same criterion run twice goes red once and green once** (measured 2026-10-06).
    # [EN] Doing the backup/restore once centrally in the hub means the criteria no longer "take the
    # [EN] environment's mood".
    # [EN] Incidentally it also preserves the record when the user **really installed it** -- previously
    # [EN] one verification run permanently deleted it.
    manifest = APP_DIR / PI.MANIFEST_NAME
    backup = manifest.read_bytes() if manifest.exists() else None
    try:
        results = [test_native_scripts(), test_dry_run(), test_real_platform(),
                   test_cli_e2e(), test_wrapper_execution(),
                   test_other_platforms(), test_safety()]
    finally:
        if backup is not None:
            manifest.write_bytes(backup)
        elif manifest.exists():
            manifest.unlink()
    report['ok'] = all(results)
    failed = [s for s in report['steps'] if not s['ok']]
    report['failed'] = failed
    (OUT / 'install_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n  共 {len(report["steps"])} 项断言，失败 {len(failed)} 项 → '
          f'{"全部通过" if report["ok"] else "有失败"}')
    if failed:
        for s in failed:
            print(f'    [FAIL] {s["name"]}  {s["detail"]}')
    print(f'  报告: {OUT / "install_report.json"}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
