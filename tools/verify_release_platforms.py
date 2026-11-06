# -*- coding: utf-8 -*-
"""验证：**一个包，四个平台**（2026-10-22 改判：发布不再区分平台）。

背景（要证明的就是这件事）
--------------------------
旧流程 `make_release.py <目标> --packages windows|macos|macos-intel|linux` 一个版本打**四个包**，
差别只有两样：根目录那三个启动器、`packages/` 里留哪个平台的 flet 运行时。
用户 2026-10-22 改判：**不再区分平台** —— 发布目录里新建「版本号」文件夹，整棵复制，四个平台全带。

于是要守的东西也变了，但**两条老教训一个字都不许丢**：
  ① **文件名证不了平台**（Windows 叫 `setup.exe`，Linux 与 macOS 都叫 `setup`）⇒ 只认魔数；
  ② **"取不到就静默跳过"是假绿**（旧 `swap_launchers` 就栽在这）⇒ 缺一套必须报问题。

判据分组
--------
A 组（纯逻辑，不打包）
  A1 `launcher_platform()` 认得出 `launchers/dist/` 下 12 个文件的平台（逐个点名）
  A2 `LAUNCHER_SETS` 四个取值的目录**都存在**（缺一套 = 那个平台进不了包）
  A3 ★★ 源码里**没有** `--packages` 参数 —— "不再区分平台"的唯一客观证据
     （反例：有人把平台参数加回来，这条必须当场红）
  A4 `PACKAGE_FILES` 的并集 == `packages/` 里的运行时（不多不少）
  A5 ★★ `ALLOWED_LAUNCHER_PLATFORM` 与 `LAUNCHER_SETS` 自洽（两张表打架就是假绿）
  A6 `required_launchers()` 只给 Windows 加 `.exe`
  A7 ★ 默认落点 = `<发布根>/<config.VERSION>`（版本号一个来源，落点不手抄）
  A8 ★ 清空口径：`LLM_KEY_PREFIXES` 覆盖 `SPEC` 里所有 `LLM_`/`MODEL_`/`EMBEDDING_` 键；
     且**行为**上真的清空了值、留住了注释与其它键
  A9 ★ 同步口径：本机 `.env` 里 `SPEC` 未登记的键**补进样例**；
     值带本机路径 / 键名像凭据的**留空**，普通值照抄
  A10 八步流程的**实现**都在册（防止某一步被删而判据还绿着）
B 组（行为：真打**一个**包，逐个读魔数量）
  B1 根目录启动器 = 打包机平台
  B2 ★ `启动器/其他平台/<平台>/` 三套各 3 个文件，魔数各对各的
  B3 ★ `packages/` 里四平台运行时全在（不裁剪）
  B4 `平台说明.md` 写到三套落点 + `PLATFORM.txt` + README 顶部横幅
  B5 清单：`checks == 'clean'`、`version == config.VERSION`、`launcher_sets` 四套
  B6 ★★ 造真错：删掉 Linux 那套 → 自检**当场报缺**
  B7 ★★ 造真错：把 `.env.example` 的 `LLM_BASE_URL` 改成非空 → 自检报"仍有非空的密钥 / LLM 配置"
  B8 ★★ 造真错：往 `.env` 塞一个样例里没有的键 → 自检报"`.env` 里有 `.env.example` 没有的键"

产出：assets/screenshots/release_platforms_report.json

English:
Verification: **one package, four platforms** (reclassified 2026-10-22: no more per-platform splits).
The old flow built **four packages per version**, differing only in the root launchers and which flet
runtime stayed in `packages/`. The user changed it: create a version folder in the release directory,
copy the whole tree, carry all four platforms.
Two old lessons must survive the change: ① **a filename proves no platform** (Windows `setup.exe`,
Linux/macOS `setup`) => magic only; ② **"missing -> skip silently" is a false green** (the old
`swap_launchers` was burned there) => a missing set must be reported.
Group A (logic): A1 magic on all 12 dist files; A2 all four dist dirs exist; A3 ★★ **no `--packages`
flag in the source** (the only objective proof of "no platform split"); A4 `PACKAGE_FILES` union ==
runtimes on disk; A5 tables self-consistent; A6 `.exe` only for Windows; A7 default target is
`<release root>/<version>`; A8 ★ LLM keys really blanked (comments and other keys intact); A9 ★
unregistered keys synced into the example, local-path/credential values blanked; A10 all eight steps
still implemented.
Group B (behaviour, one real build): B1 root = host; B2 ★ three other sets present with right magic;
B3 ★ all four runtimes present; B4 note + banner; B5 manifest clean/version/sets; B6-B8 ★★ three
manufactured errors that the self-check must report.
Output: assets/screenshots/release_platforms_report.json
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import make_release as M                                  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
PYTHON = str(APP_DIR / '.venv' / 'Scripts' / 'python.exe')
if not Path(PYTHON).exists():
    PYTHON = sys.executable
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:300]})
    return bool(cond)


def group_a() -> None:
    dist = APP_DIR / 'launchers' / 'dist'
    src = (APP_DIR / 'tools' / 'make_release.py').read_text(encoding='utf-8')

    # A1
    rows = [(d.name, f.name, M.launcher_platform(f))
            for d in sorted(dist.iterdir()) if d.is_dir() for f in sorted(d.iterdir())]
    unknown = [r for r in rows if r[2] in ('?',) or r[2].startswith('other')]
    ok('A1 认得出 launchers/dist 下 12 个启动器各自的平台（读魔数）',
       len(rows) == 12 and not unknown, f'{len(rows)} 个 · 认不出={unknown}')

    # A2
    missing = [c for c, d in M.LAUNCHER_SETS.items() if not (dist / d).is_dir()]
    ok('A2 LAUNCHER_SETS 四个取值的产物目录都存在（缺一套 = 那个平台进不了包）',
       not missing and len(M.LAUNCHER_SETS) == 4, f'缺={missing}')

    # A3 ★★ 不区分平台的**唯一客观证据**：参数层没有 `--packages`
    #    ⚠ 只查 `add_argument('--packages'` 这一种形态：文档里提到
    #      `--packages windows|...` 是**记录历史**，不该判红。
    # [EN] ★★ The only objective proof of "no platform split": no `--packages` in the argument layer.
    # [EN] ⚠ Only `add_argument('--packages'` counts: mentioning it in docs is history, not a regression.
    has_flag = bool(re.search(r"add_argument\(\s*['\"]--packages", src))
    ok('A3 ★★ 源码里没有 --packages 参数（"不再区分平台"的客观证据）',
       not has_flag and 'PACKAGE_CHOICES' not in src, f'has_flag={has_flag}')

    # A4 运行时清单 == 磁盘（不多不少）
    have = {p.name for p in (APP_DIR / 'packages').iterdir() if p.is_file()}
    want = {n for names in M.PACKAGE_FILES.values() for n in names}
    ok('A4 PACKAGE_FILES 的并集 == packages/ 里的运行时（不多不少；不裁剪就必须全在册）',
       have == want, f'磁盘 {len(have)} · 清单 {len(want)} · 漏={sorted(have - want)[:3]} '
                     f'多={sorted(want - have)[:3]}')

    # A5 两张表自洽
    bad_pair = []
    for choice, d in M.LAUNCHER_SETS.items():
        allowed = M.ALLOWED_LAUNCHER_PLATFORM.get(choice)
        if allowed is None:
            bad_pair.append(f'{choice}: ALLOWED 缺失')
            continue
        for f in (dist / d).iterdir():
            got = M.launcher_platform(f)
            if got not in allowed:
                bad_pair.append(f'{choice}({d}/{f.name})={got} ∉ {sorted(allowed)}')
    ok('A5 ★★ ALLOWED_LAUNCHER_PLATFORM 与 LAUNCHER_SETS 自洽（两张表打架就是假绿）',
       not bad_pair, bad_pair[:4])

    # A6
    names = {c: M.required_launchers(c) for c in M.LAUNCHER_SETS}
    ok('A6 required_launchers() 只给 Windows 加 .exe',
       all(n.endswith('.exe') for n in names['windows'])
       and all(not n.endswith('.exe') for c in names if c != 'windows' for n in names[c]),
       names)

    # A7 ★ 默认落点：发布根/<版本号>
    ok('A7 ★ 默认落点 = <发布根>/<config.VERSION>（版本号一个来源，落点不手抄）',
       'release_root / version' in src and M.RELEASE_ROOT.name == '发布版本'
       and src.count('_source_version()') >= 1,
       f'RELEASE_ROOT={M.RELEASE_ROOT.name}')

    # A8 ★ 清空口径：SPEC 里所有 LLM 类键都在前缀表覆盖范围内，且真的清空
    spec = M._load_spec()
    llm_keys = [k for k in spec if k.upper().startswith(M.LLM_KEY_PREFIXES)]
    not_covered = [k for k in llm_keys if not k.upper().startswith(M.LLM_KEY_PREFIXES)]
    tmp = Path(tempfile.mkdtemp(prefix='nws_envchk_'))
    try:
        p = tmp / '.env.example'
        p.write_text('# 注释要留着\nLLM_BASE_URL=https://relay.example/v1\n'
                     'MODEL_FRONT=my-model\nEMBEDDING_PROVIDER=ollama\n'
                     'SPEC_KEEP_ME=keep\n', encoding='utf-8')
        done = M.scrub_llm_env(p)
        text = p.read_text(encoding='utf-8')
        kept = 'SPEC_KEEP_ME=keep' in text and '注释要留着' in text
        blank = all(f'{k}=' in text for k in ('LLM_BASE_URL', 'MODEL_FRONT', 'EMBEDDING_PROVIDER'))
        ok('A8 ★ 清空值但留住键名 / 注释 / 其它键（SPEC 里每个 LLM 类键都被前缀表覆盖）',
           not not_covered and len(done) == 3 and kept and blank,
           f'清了={done} 覆盖漏={not_covered} 保留={kept} 空={blank}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # A9 ★ 同步口径
    tmp = Path(tempfile.mkdtemp(prefix='nws_syncchk_'))
    try:
        live = tmp / 'source.env'
        live.write_text('LLM_API_KEY=sk-abcd1234efgh5678\n'
                        'MY_PRIVATE_DIR=C:\\Users\\chao\\Desktop\\proj\n'
                        'MY_THIRD_TOKEN=tok_abcdef\n'
                        'MY_PLAIN_KNOB=42\n', encoding='utf-8')
        # ⚠ 样例与 `.env` 必须是**两个文件**：同一个文件传两遍时，
        #   第二次写会把同一段块追加两次（第一版就这么写，于是"补了什么"里混着重复项）。
        # [EN] ⚠ Example and `.env` must be **two files**: passing the same file twice appends the
        # [EN] block twice (the first version did exactly that, duplicating entries).
        ex = tmp / '.env.example'
        ex.write_text('LLM_API_KEY=\n', encoding='utf-8')
        env = tmp / '.env'
        env.write_text('LLM_API_KEY=\n', encoding='utf-8')
        added, blanked = M.sync_env_keys(live, ex, env)
        text = ex.read_text(encoding='utf-8')
        env_text = env.read_text(encoding='utf-8')
        ok('A9 ★ 未登记的键补进样例：带本机路径 / 像凭据的值留空，普通值照抄',
           set(added) == {'MY_PRIVATE_DIR', 'MY_THIRD_TOKEN', 'MY_PLAIN_KNOB'}
           and 'MY_PLAIN_KNOB=42' in text
           and 'MY_PRIVATE_DIR=\n' in text + '\n' and 'MY_THIRD_TOKEN=\n' in text + '\n'
           and set(blanked) == {'MY_PRIVATE_DIR', 'MY_THIRD_TOKEN'}
           and env_text == text,          # 两项文件内容必须一致（否则 2c 会报键集合不一致）
           f'补={added} 留空={blanked} 两份一致={env_text == text}')

        # A9b ★★★ 同步的**唯一通路**上不许把真密钥带过去（用户 2026-10-22：
        #   「环境文件里 APIKey 需要清理掉」）。两种"键名筛不住"的写法各来一条：
        #   ① 密钥藏在 URL 查询串里；② JWT 挂在没有任何收尾词的名字下。
        # [EN] A9b ★★★ The **only channel** that can carry a real value must not carry a secret (user,
        # [EN] 2026-10-22: "the API key in the env file must be cleaned out"). Two shapes that a
        # [EN] name-based filter cannot catch: ① a key inside a URL query; ② a JWT under a name with no
        # [EN] credential suffix.
        live2 = tmp / 'source2.env'
        live2.write_text('MY_RELAY=https://relay.example.com/v1?key=sk-abcdef1234567890abcd\n'
                         'SOMETHING_CRED=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdefghijkl\n'
                         'CREW_STORY_TOKENS=12000\n', encoding='utf-8')
        ex2 = tmp / 'ex2/.env.example'
        ex2.parent.mkdir(parents=True, exist_ok=True)
        ex2.write_text('LLM_API_KEY=\n', encoding='utf-8')
        env2 = ex2.with_name('.env')
        env2.write_text('LLM_API_KEY=\n', encoding='utf-8')
        _a2, _b2 = M.sync_env_keys(live2, ex2, env2)
        t2 = ex2.read_text(encoding='utf-8')
        ok('A9b ★★★ 同步时"密钥藏在 URL 里 / JWT 挂在无收尾词的名字下"也会被留空',
           set(_b2) == {'MY_RELAY', 'SOMETHING_CRED'}
           and 'MY_RELAY=\n' in t2 + '\n' and 'SOMETHING_CRED=\n' in t2 + '\n'
           and 'CREW_STORY_TOKENS=12000' in t2,
           f'留空={_b2} 补={_a2}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # A10 八步流程的实现都在册
    need = ['def write_clean_env', 'def sync_env_keys', 'def scrub_llm_env', 'def clean_junk',
            'def stage_launcher_sets', 'def write_release_note', 'def scan_release',
            'shutil.copytree(src, dst']
    lack = [n for n in need if n not in src]
    ok('A10 八步流程的实现都在册（某一步被删掉时这条先红）', not lack, f'缺={lack}')


def build(target: Path) -> str:
    r = subprocess.run([PYTHON, str(APP_DIR / 'tools' / 'make_release.py'), str(target), '--yes'],
                       cwd=str(APP_DIR), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=3600)
    return (r.stdout or '') + (r.stderr or '')


def group_b() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_relchk_'))
    tgt = tmp / (M._source_version() or 'X')
    try:
        log = build(tgt)
        report['build_log'] = log[-1500:]
        # B1
        got = M.launcher_platforms_in_dir(tgt)
        allowed = M.ALLOWED_LAUNCHER_PLATFORM.get(M.host_platform()) or set()
        ok('B1 根目录启动器实测平台 = 打包机平台',
           bool(got) and (not allowed or set(got) <= allowed),
           f'实测={got} 允许={sorted(allowed)}')
        # B2 ★ 三套其他平台启动器
        bad = []
        for key in M.LAUNCHER_SETS:
            if key == M.host_platform():
                continue
            sub = tgt / M.LAUNCHER_STAGE_DIR / M.OTHER_PLATFORM_DIR / key
            names = M.required_launchers(key)
            lack = [n for n in names if not (sub / n).is_file()]
            got2 = set(M.launcher_platforms_in_dir(sub))
            allow2 = M.ALLOWED_LAUNCHER_PLATFORM.get(key) or set()
            if lack:
                bad.append(f'{key} 缺 {lack}')
            elif allow2 and got2 - allow2:
                bad.append(f'{key} 魔数 {sorted(got2)}')
        ok(f'B2 ★ {M.LAUNCHER_STAGE_DIR}/{M.OTHER_PLATFORM_DIR}/ 里三套各 3 个文件、魔数各对',
           not bad, bad[:3])
        # B3 ★ 四平台运行时全在
        want = {n for names in M.PACKAGE_FILES.values() for n in names}
        have = {p.name for p in (tgt / 'packages').iterdir()} if (tgt / 'packages').is_dir() else set()
        ok('B3 ★ packages/ 里四平台 flet 运行时全在（不裁剪）',
           not (want - have), sorted(want - have)[:4])
        # B4 说明书
        note = tgt / M.NOTE_NAME
        txt = note.read_text(encoding='utf-8') if note.is_file() else ''
        staged_ok = all(f'{M.LAUNCHER_STAGE_DIR}/{M.OTHER_PLATFORM_DIR}/{k}' in txt
                        for k in M.LAUNCHER_SETS if k != M.host_platform())
        rzh = (tgt / 'README.md').read_text(encoding='utf-8').split('\n')[:8]
        ok('B4 平台说明.md 写到三套落点 + PLATFORM.txt + README 顶部横幅',
           note.is_file() and (tgt / M.NOTE_NAME_EN).is_file() and staged_ok
           and any(M.NOTE_NAME in x for x in rzh),
           f'落点齐={staged_ok} 横幅={rzh[2][:50] if len(rzh) > 2 else ""}')
        # B5 清单
        man = json.loads((tgt / '.release_manifest.json').read_text(encoding='utf-8'))
        ok('B5 清单 checks=clean、version 跟源码、launcher_sets 四套都在',
           man.get('checks') == 'clean' and man.get('version') == M._source_version()
           and len(man.get('launcher_sets', {})) == 4 and man.get('platform') == 'single',
           f"checks={man.get('checks')} v={man.get('version')} "
           f"sets={list(man.get('launcher_sets', {}))}")

        # B9 ★★★ `.env` 与 `.env.example` 的**分工**（2026-10-22 实测出来的真回归）：
        #   `coerce()` 对 str/path/enum **不回落默认值**，所以 `.env` 里 `LLM_BASE_URL=` 一空，
        #   发布版就指向空地址；而样例那份要清空给人看。两者键集合还必须一致。
        # [EN] B9 ★★★ The **split** between `.env` and `.env.example` (a real regression measured on
        # [EN] 2026-10-22): `coerce()` does not fall back for str/path/enum, so an empty
        # [EN] `LLM_BASE_URL` in `.env` leaves the release pointing nowhere; the example is the one to
        # [EN] blank. Both must share the same key set.
        def _pairs(name):
            return dict(M.parse_env_pairs((tgt / name).read_text(encoding='utf-8')))
        e_env, e_ex = _pairs('.env'), _pairs('.env.example')
        ok('B9 ★★★ `.env` 保留官方默认（能跑）、`.env.example` 的 LLM 值全空、两份键集合一致',
           bool(e_env.get('LLM_BASE_URL', '').strip())
           and bool(e_env.get('MODEL_FRONT', '').strip())
           and not e_ex.get('LLM_BASE_URL', '').strip()
           and not e_ex.get('MODEL_FRONT', '').strip()
           and set(e_env) == set(e_ex),
           f"env base={'有' if e_env.get('LLM_BASE_URL', '').strip() else '空!'} "
           f"样例 base={'空' if not e_ex.get('LLM_BASE_URL', '').strip() else '有!'} "
           f"键集合一致={set(e_env) == set(e_ex)}")

        # B10 ★★★ 包里**任何一个** env 文件都不许有非空凭据（用户 2026-10-22：
        #   「环境文件里 APIKey 需要清理掉」）。这一条不看位置 —— 旧写法只扫
        #   `novelservices/` 下面，服务挪个位置就漏过去，而漏过去的样子是"自检 ✓"。
        #
        # ★★★ 第一版是**假绿**（反例 M12 当场揭穿）：判据自己 `rglob('.env*')` 又数了一遍，
        #   产品扫描缩回 `novelservices/` 时它照样绿 —— 因为包本身是干净的。
        #   这正是"判据与产品各有一套口径"的病：**判据在考自己，不在考产品**。
        #   ⇒ 改成：① 干净包上，产品**不报**任何凭据问题；② 在**根目录之外**
        #     （`novelservices/` 以外）造一张脏 env，产品**必须报**。
        #     覆盖率完全由产品决定，判据只问"报没报"。
        #   ⚠ 探针必须放在 **`novelservices/` 以外**：放在里面的话，产品缩回旧覆盖面也照样报。
        # [EN] B10 ★★★ No env file anywhere may hold a non-empty credential. The old scan only looked
        # [EN] under `novelservices/`, so moving a service let it through -- and "through" looks like ✓.
        # [EN] ★★★ The first version was a **false green** (reverse experiment M12 exposed it): the
        # [EN] criterion re-counted with its own `rglob('.env*')`, so shrinking the product's scan back
        # [EN] to `novelservices/` still showed green -- the package itself is clean. That is the
        # [EN] "criterion measures itself, not the product" disease.
        # [EN] => Now: ① on a clean package the product reports **no** credential problem; ② a dirty env
        # [EN] planted **outside** `novelservices/` **must** be reported. Coverage belongs to the
        # [EN] product; the criterion only asks "did it report".
        # [EN] ⚠ The probe must sit **outside** `novelservices/`; inside it, the shrunken scan would
        # [EN] still report.
        _clean_probs = [x for x in M.scan_release(tgt, '') if '凭据' in x]
        _probe = tgt / '_probe_env_root'
        _probe.mkdir(parents=True, exist_ok=True)
        (_probe / '.env').write_text('PROBE_SESSION_SECRET_KEY=deadbeef\n', encoding='utf-8')
        _probe_hit = [x for x in M.scan_release(tgt, '') if 'PROBE_SESSION_SECRET_KEY' in x]
        shutil.rmtree(_probe, ignore_errors=True)
        ok('B10 ★★★ 干净包不报凭据 / 在 novelservices 之外造一张脏 env 必须报（覆盖由产品决定）',
           not _clean_probs and bool(_probe_hit),
           f'干净包误报={_clean_probs[:2]} 造错被抓住={bool(_probe_hit)}')

        # B6 ★★ 造真错：删掉 Linux 那套
        sub = tgt / M.LAUNCHER_STAGE_DIR / M.OTHER_PLATFORM_DIR / 'linux'
        if sub.is_dir():
            shutil.rmtree(sub)
        probs = M.scan_release(tgt, '')
        hit = [p for p in probs if 'linux' in p.lower() or 'Linux' in p]
        ok('B6 ★★ 删掉 Linux 那套 → 自检**当场报缺**', bool(hit), probs[:3])
        report['b6_problems'] = probs[:6]

        # B7 ★★ 造真错：`.env.example` 里留一个非空的 LLM 配置
        ex = tgt / '.env.example'
        ex.write_text(ex.read_text(encoding='utf-8').replace(
            'LLM_BASE_URL=', 'LLM_BASE_URL=https://my-relay.example/v1', 1), encoding='utf-8')
        probs = M.scan_release(tgt, '')
        ok('B7 ★★ .env.example 里留着 LLM 配置 → 自检报"仍有非空的密钥 / LLM 配置"',
           any('LLM_BASE_URL' in p for p in probs), probs[:3])

        # B8 ★★ 造真错：`.env` 里多一个样例没有的键
        envp = tgt / '.env'
        envp.write_text(envp.read_text(encoding='utf-8') + '\nNEW_SECRET_KNOB=1\n',
                        encoding='utf-8')
        probs = M.scan_release(tgt, '')
        ok('B8 ★★ `.env` 多出样例没有的键 → 自检报键集合不一致',
           any('NEW_SECRET_KNOB' in p for p in probs), probs[:3])
    except BaseException:                                    # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        ok('B 组未抛异常（整轮跑完）', False, report['fatal'][-300:])
    finally:
        # ★ 清理：包里有只读文件时 `rmtree` 会失败，先改权限再删
        # [EN] ★ Cleanup: `rmtree` fails on read-only files; chmod first, then delete
        for p in tmp.rglob('*'):
            if p.is_file():
                os.chmod(p, 0o666)
        shutil.rmtree(tmp, ignore_errors=True)


#: `--a-only`：只跑 A 组（纯逻辑）—— 给反例法用：改坏了 A 组能抓的东西时，
#: 没必要真打一个包（一遍要拷贝 1GB 以上）。
# [EN] : `--a-only`: run group A only (pure logic) -- for reverse experiments: when the mutation breaks
# [EN] something group A catches, there's no need to really build a package (each round copies >1GB).
A_ONLY = '--a-only' in sys.argv


def main() -> int:
    try:
        group_a()
        if not A_ONLY:
            group_b()
    except BaseException:                                    # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        ok('未抛异常（整轮跑完）', False, report['fatal'][-200:])
    passed = sum(1 for c in report['checks'] if c['ok'])
    total = len(report['checks'])
    report.update({'passed': passed, 'total': total,
                   'ok': passed == total and not report.get('fatal')})
    (OUT / 'release_platforms_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for c in report['checks']:
        print(('  ✓ ' if c['ok'] else '  ✗ ') + c['name'] +
              (f"   [{c['detail']}]" if not c['ok'] else ''))
    print(f'\n四平台发布包验证：{passed}/{total}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
