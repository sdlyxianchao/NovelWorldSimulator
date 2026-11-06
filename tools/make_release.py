# -*- coding: utf-8 -*-
"""把一个版本**发布出去**：在发布目录里新建「版本号」文件夹，整棵工程复制过去，再清干净。

★★★ 2026-10-22 改判（用户：「修改下发布脚本，**不再区分平台**，而是先到发布目录新建一个
目标版本文件夹，把整个文件夹的内容复制过去……」）：
  旧脚本是 `make_release.py <目标路径> --packages windows|macos|macos-intel|linux`，
  一个版本要打**四个包**（4 × ~1GB，光复制就几十分钟），而且四个包的差别只有两样：
  根目录那三个启动器、`packages/` 里留哪个平台的 flet 运行时。
  ⇒ 现在**一个版本一个文件夹**（`发布版本/<版本号>/`），四个平台的启动器**全带**，
  `packages/` 不裁。判据也跟着改了：`tools/verify_release_platforms.py` 现在守的是
  「单包里的四套启动器都在、魔数对得上、平台说明写清楚了」。

固定八步（顺序不能换）
--------------------
1. **新建版本文件夹**：`发布版本/<config.VERSION>/`。版本号**只有一个来源**
   （`config.py` 的 `VERSION`），不传参、不写死 —— 0.3.2 那次「包名写着 0.3.0」就是抄了一份。
   目标已存在时：是本脚本产出过的（有 `.release_manifest.json`）且带 `--force` 才清空重建，
   否则只接受"不存在或空目录"。这条是防路径给错时把无关数据删掉。
2. **整棵复制**：`shutil.copytree` + 排除表（`.venv` / `logs` / `Projects` / `usage.db` /
   服务里的用户数据与凭据 ……，逐条都有理由，见下面的字典）。排除表**复制前**就生效 ——
   1.85G 的 venv 拷贝一遍再删，光 IO 就几分钟，中途失败还会留下半个包。
3. **启动器（不区分平台）**：根目录是**打包机那一套**（本机双击就能用）；另外三套
   （`darwin-arm64` / `darwin-amd64` / `linux-amd64`）放进 `启动器/其他平台/<平台>/`。
   ★ 为什么必须带：`launchers/` 整目录按路径排除（构建工具链，里面写着本机 Go 路径），
     不另带一份的话，Mac / Linux 用户拿到的包**根目录三个文件双击没反应，也没有任何别的来源**。
   ★ 每套都**读魔数**核对，不认文件名 —— Windows 叫 `setup.exe`，Linux 与 macOS 都叫 `setup`，
     同名不同物，名字一个字都证明不了。
4. **`.env` / `.env.example` 重新生成**：用 `config.Config.write_example()` 按 `SPEC` 逐键写
   （全键 + 官方默认 + `secret=True` 留空），**不复制**工程里那份（它含真密钥与本机路径）。
5. **同步本机 `.env` 里多出来的键**：`.env` 里有、生成的样例里没有 ⇒ 补进样例。
   这是"新加了一个旋钮、但忘了登记进 `SPEC`"**唯一**能被发现的时机
   （`SPEC` 里有 352 个键，本机 `.env` 351 个；两边各自演化迟早会分叉）。
6. **清掉密钥与 LLM 配置（只清样例）**：`.env.example` 里 `LLM_*` / `MODEL_*` / `EMBEDDING_*`
   的值一律留空（**键名与注释保留**），`secret=True` 的键同样留空。
   ⚠ **`.env` 不清 LLM 那几项**（2026-10-22 实测修正）：`coerce()` 对 str/path/enum
   **不回落默认值**（只有 bool 与 int 回落）⇒ `.env` 里 `LLM_BASE_URL=` 一空，
   发布版就指向空地址、没有模型名，用户填了 key 也只会看到"请求失败"。
   所以分工是：`.env` = 官方默认 + 密钥空（装上就能跑，只差一个 key）；
   `.env.example` = 值全清的"旋钮清单"。两份**键集合一致**，自检同时验这两条。
7. **兜底清扫**：日志 / 缓存 / 台账 / 开发目录 / 本机状态 / 旧备份（`*.old-*`、`*.bak-*`）
   再扫一遍删干净。排除表漏一条也不会让它们进包，删了什么按类报数。
8. **自检 + 清单**：拿**真实密钥**去全文搜、查 `sk-…` 字面量、查本机绝对路径、查残留日志与
   数据库、查必带文件（含四套启动器的魔数）、查 `.env` 里密钥与 LLM 配置是否真的空着。
   有问题时退出码非 0，并写进 `.release_manifest.json` 的 `checks`。

用法
----
    python tools/make_release.py                 # 发布 发布版本/<config.VERSION>/
    python tools/make_release.py --dry-run       # 只打印计划，不复制
    python tools/make_release.py --out <目录>     # 换一个落点（默认 发布版本/<版本号>）
    python tools/make_release.py --force         # 该版本已存在（且是旧发布版）→ 清空重建
    python tools/make_release.py --zip           # 另外打一个 .zip 放在旁边
    --release-root <目录>                         # 换发布根目录（默认 工程同级 的「发布版本」）
    --keep-dev-tools                             # 保留 tools/verify_*.py（默认不带）

English:
Publish one version: create `<release root>/<version>/`, copy the whole tree into it, then clean it.
★★★ Reclassified 2026-10-22 (user: "change the release script, **stop splitting by platform**;
instead create a target-version folder in the release directory and copy the whole thing over"):
  The old script took `--packages windows|macos|macos-intel|linux` and built **four packages per
  version** (4 x ~1GB, tens of minutes each), differing in exactly two things: the three launchers in
  the root and which flet runtime stayed in `packages/`.
  => Now **one folder per version** (`发布版本/<version>/`), all four launcher sets included,
  `packages/` untrimmed. Criteria changed too: `tools/verify_release_platforms.py` now guards
  "all four sets present in the single package, magic verified, the platform note says where they are".
Eight fixed steps (order matters):
  1. Create the version folder; the version has **one source** (`config.VERSION`). Existing target is
     only wiped when it carries our manifest **and** `--force` was given.
  2. Whole-tree copy with the exclusion tables (they apply **before** the copy: copying 1.85GB of
     venv only to delete it wastes minutes and can leave half a package).
  3. Launchers, **platform-agnostic**: root = build host's set; the other three go to
     `启动器/其他平台/<platform>/`. `launchers/` itself is excluded (build toolchain, local Go paths),
     so without this a Mac/Linux user has launchers that do nothing and no other source. Every set is
     checked by **magic** (Windows is `setup.exe`, Linux and macOS are both `setup`).
  4. Regenerate `.env` / `.env.example` from `SPEC` (all keys + official defaults + secrets empty);
     never copy the project's own `.env` (real key, local paths).
  5. Sync keys that exist in the local `.env` but not in the generated example -- the only moment a
     knob added without a `SPEC` entry can be noticed.
  6. Blank `LLM_*` / `MODEL_*` / `EMBEDDING_*` and every `secret=True` key in the **example**
     (names and comments kept). ⚠ **Not** in `.env` (corrected 2026-10-22 by measurement):
     `coerce()` does not fall back for str/path/enum (only bool/int), so an empty `LLM_BASE_URL` in
     `.env` leaves the release pointing nowhere while the user only sees "request failed".
     Split: `.env` = official defaults + empty secret (runs out of the box, only a key missing);
     `.env.example` = every value blanked, i.e. a list of knobs. Same key set in both.
  7. Sweep logs / caches / ledgers / dev dirs / machine state / old backups once more and report counts.
  8. Self-check (real key full-text search, `sk-...` literals, local absolute paths, leftover logs and
     DBs, required files incl. four launcher sets' magic, empty secrets and LLM config) + manifest.
Usage:
    python tools/make_release.py [--dry-run] [--out DIR] [--force] [--zip]
                                 [--release-root DIR] [--keep-dev-tools]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
MANIFEST_NAME = '.release_manifest.json'

# ══════════════════════════════════════════════════════════════
#  排除规则（分组只为让人看得懂"为什么排除它"，报告里按组显示）
#  ★ 分两类，别混：
#    - `==_DIR_NAMES`：**任何位置**只要目录名是这个就排除（如 .venv、__pycache__）；
#    - `==_DIR_PATHS`：**指定相对路径**才排除。
#      第一版把 `assets/screenshots` 写进了"按名字"那张表 —— 拿"目录名"去比
#      "带斜杠的路径"，永远不命中，那张调试截图整批会被复制进发布包
#      （dry-run 里那组一项都没列出，是它自己暴露的）。
# [EN] Exclusion rules (grouped only so readers can see "why it's excluded"; reports display by group)
# [EN] ★ Two categories, don't mix them up:
# [EN] - `==_DIR_NAMES`: exclude if the directory name matches **anywhere** (e.g. .venv, __pycache__);
# [EN] - `==_DIR_PATHS`: exclude only at the **specified relative path**.
# [EN] The first version put `assets/screenshots` into the "by name" table -- comparing a "directory
# [EN] name" against
# [EN] a "path with slashes" never matches, and that whole batch of debug screenshots gets copied into
# [EN] the release package
# [EN] (the dry-run group listed zero entries -- it exposed itself).
# ══════════════════════════════════════════════════════════════
EXCLUDE_DIR_NAMES: dict[str, list[str]] = {
    '运行环境（用户自建）': ['.venv', 'venv', 'env'],
    'Python 字节码缓存': ['__pycache__'],
    '版本控制 / 编辑器': ['.git', '.vscode', '.idea'],
    '运行日志': ['logs'],
    '开发脚本（本机调试用）': ['developers'],
    '开发测试': ['tests'],
    '用户项目数据': ['Projects', '项目'],
    # ★ 2026-10-10 加：`.gitignore` 里写着「导出物（发给别人的诊断包等：
    #   里面是**用户自己的作品与运行日志**）」—— 可排除清单里**一直没有它**，
    #   于是诊断包（对话日志 + 主日志 + 小说正文）会**整包跟着发布包走**。
    #   原先只拦住里面的 `*.log`，`README_给外部工具.md` / 自检 json / 正文照走 ——
    #   和"把开发文档当用户文档发布"是同一类病：**判据只覆盖了它想得起来的那一半**。
    # [EN] ★ Added 2026-10-10: `.gitignore` says "exports (diagnostic bundles sent to others, etc.:
    # [EN] inside are **the user's own works and run logs**)" -- yet it was **never** in the exclusion
    # [EN] list,
    # [EN] so diagnostic bundles (conversation logs + main log + novel text) would **ride along with the
    # [EN] release package wholesale**.
    # [EN] Previously only `*.log` inside was blocked; `README_给外部工具.md` / self-check json / body text all
    # [EN] went through --
    # [EN] same class of disease as "publishing dev docs as user docs": **the criterion only covers the
    # [EN] half it remembers**.
    '导出物（用户自己的作品与运行日志）': ['exports'],
    # ★★★ 2026-10-21（理由见 `EXCLUDE_FILE_GLOBS` 顶部那一段的 ②③）：
    #   · `.workbuddy` = **AI 开发工作目录**（逐日开发日志、项目记忆）；
    #   · `.ui_state` = 运行期的界面状态（本机窗口尺寸 / 上次停在哪一页）。
    #   两者都"不影响运行、不报错"，所以只能靠排除表兜住。
    # [EN] ★★★ 2026-10-21 (reasoning in items ②③ at the top of `EXCLUDE_FILE_GLOBS`):
    # [EN] · `.workbuddy` = the **AI development workspace** (daily dev logs, project memory);
    # [EN] · `.ui_state` = runtime UI state (window size / last page).
    # [EN] Both "break nothing and error nowhere", so only an exclusion table can hold them.
    'AI 开发工作目录（开发日志／项目记忆，属开发内幕）': ['.workbuddy'],
    '运行期界面状态（本机窗口尺寸／上次停在哪一页）': ['.ui_state'],
}
EXCLUDE_DIR_PATHS: dict[str, list[str]] = {
    '调试截图（.gitignore 已列）': ['assets/screenshots'],
    # ★★★ 2026-10-21（用户：「清理掉这些历史遗留」）：
    #   这三样是**开发期留在工程根目录的垃圾**，之前每一版都原样进了发布包：
    #     · `字体设置验证` / `面板跳转验证` —— **判据造的假项目**（里面有 `.nwsproj`）。
    #       它们是 10-14 那天的残留：当时判据把 `isolate_projects_dir()` 的**返回值**
    #       当落点用，于是建到了工程根目录而不是隔离目录（那个错误写法已被
    #       `verify_projects_isolation.py` 立规矩修掉，所以清掉**不会再生**）。
    #     · `偷写` —— 一个空目录（连文件都没有，纯粹是某次手滑建出来的）。
    #   ⚠ 用**路径**排除而不是"按名字"：万一将来真有作者给项目起名叫「字体设置验证」，
    #     按名字排除会把他**真正的项目**从包里剔掉 —— 路径排除只认工程根目录这一个位置。
    # [EN] ★★★ 2026-10-21 (user: "clean up these historical leftovers"): these three were dev-time
    # [EN] junk sitting in the project root and shipping in every release.
    # [EN] · `字体设置验证` / `面板跳转验证` -- **fake projects made by criteria** (they contain a
    # [EN]   `.nwsproj`), left behind on 10-14 when a criterion used the **return value** of
    # [EN]   `isolate_projects_dir()` as a landing spot, so they were built in the project root
    # [EN]   instead of the isolated dir (that misuse is now outlawed by
    # [EN]   `verify_projects_isolation.py`, so cleaning them is permanent).
    # [EN] · `偷写` -- an empty directory (not even a file; pure finger-slip).
    # [EN] ⚠ Excluded **by path**, not by name: if an author ever names their project
    # [EN] "字体设置验证", a name rule would drop their **real project** from the package --
    # [EN] a path rule only matches this one location.
    '开发期残留在工程根目录的垃圾（判据假项目 / 空目录）': [
        '字体设置验证', '面板跳转验证', '偷写',
    ],
    # ★★★ 2026-10-21（清遗留时**顺带查出来的**，之前每一版都在包里）：
    #   `generated-images/视觉参考/` 是**产品运行时写**的目录 —— `crew/agents.py` 里
    #   `_out.mkdir(parents=True, exist_ok=True)` 之后把人物参考图落进去。
    #   而包里带的那 170 个文件是**开发期跑不同世界留下的**（人物_傩送 / 人物_克莱恩 /
    #   人物_司马懿 …… 2.7MB），跟发布产品毫无关系，用户只会觉得莫名其妙。
    #
    #   ★ 为什么可以整目录排除：代码**每次都会 mkdir**，缺目录不影响任何功能。
    #     （如果它是"只读不建"的目录，整目录排除就会埋一个运行期错误 —— 所以要查这一句。）
    # [EN] ★★★ 2026-10-21 (found **while auditing leftovers**; present in every earlier release):
    # [EN] `generated-images/视觉参考/` is a directory the **product writes at runtime** --
    # [EN] `crew/agents.py` does `_out.mkdir(parents=True, exist_ok=True)` and drops character
    # [EN] reference images in. The 170 files in the package are **left over from running different
    # [EN] worlds during development** (人物_傩送 / 人物_克莱恩 / 人物_司马懿 ... 2.7MB) -- unrelated to
    # [EN] the shipped product and baffling to users.
    # [EN] ★ Why whole-directory exclusion is safe: the code **mkdirs every time**, so a missing
    # [EN] directory breaks nothing. (If it were read-only, excluding it wholesale would plant a
    # [EN] runtime error -- hence checking that one line.)
    '开发期跑出来的图片产物（产品运行时会自建该目录）': ['generated-images'],
    # ★★★ 2026-10-21（用户：「记得**所有相关服务都复制过去**」）：
    #   `novelservices/` 从"整目录排除"改成"**带上，但按服务规则裁剪 + 脱敏**"。
    #
    #   ★ 为什么改（以前排除的理由，逐条对照）：
    #     · "不是产品的一部分" —— **这条已经不成立了**。`crew/agents.py` 里
    #       `from novelservices import mumu_bridge`，Go 启动器也按
    #       `novelservices/PenShot` / `PlotPilot` / `MuMuAINovel/backend` 三个固定相对路径
    #       去 prepare/stop 它们。不在包里 ⇒ 发布版的"外部创作服务"**整块是死的**
    #       （代码有 try/except，所以不报错 —— 那更糟：用户以为功能坏了）。
    #     · "体积 ~921MB" —— 主要是三个 `.venv`（454M + 674M + 721M = 1.85G）。
    #       **venv 必须排除**，但理由不是体积，是**它根本不能搬**：venv 里的
    #       `pyvenv.cfg` 和每个 console script 都写着打包机的绝对路径，
    #       换一台机器 100% 起不来。带上它等于给一个"看起来带了依赖、其实用不了"的包。
    #       依赖由 `service_ctl.py prepare` 在装机时现建（那正是它存在的理由）。
    #     · "含用户数据 / API Key" —— **改用脱敏解决**，不再靠"整个不发"：
    #       · `backend/.env`、`PenShot/.env`、`PlotPilot/.env` → 复制但**清空密钥字段**
    #         （见 `sanitize_service_envs`，与根目录 `.env` 同一套口径）；
    #       · `凭据.txt`、`data/ai_story.db`（35M，678 个项目 / 932 章正文）、
    #         `data/chroma_db`（123M，上述正文的向量索引）→ **仍然排除**（用户 2026-10-21 选定：
    #         不带，用空库，首次启动自动建表）。
    #     · `embedding/onnx`（458M 向量模型）→ **必须带**：那是功能依赖，不是用户数据，
    #       少了它服务的"记忆/检索"直接不可用。
    #
    #   ⚠ 三个 `.venv` / `logs` / `__pycache__` / `.git` 不需要在这里逐条写 ——
    #     `EXCLUDE_DIR_NAMES` 是**按名字**匹配的，服务目录里的同名目录自动被排除。
    #     这里只写"按路径"才能表达的那几条（用户数据、凭据）。
    #   ⚠ 必须**在复制前**排除，不能复制完再删：458M 模型 + 1.85G venv 一起拷一遍再删，
    #     光 IO 就几分钟，而且中途失败会留下半个包。
    #
    # [EN] ★★★ 2026-10-21 (user: "remember to copy **all the related services** over"):
    # [EN] `novelservices/` moves from "exclude the whole directory" to "**ship it, trimmed by service
    # [EN] rules and sanitized**".
    # [EN] ★ Why (each old reason re-examined):
    # [EN] · "not part of the product" -- **no longer true**. `crew/agents.py` does
    # [EN]   `from novelservices import mumu_bridge`, and the Go launchers locate
    # [EN]   `novelservices/PenShot`, `PlotPilot`, `MuMuAINovel/backend` by three fixed relative paths to
    # [EN]   prepare/stop them. Absent from the package => the shipped "external creation service" is
    # [EN]   **entirely dead** (the code has a try/except, so nothing errors -- which is worse: the user
    # [EN]   concludes the feature is broken).
    # [EN] · "~921MB" -- mostly the three `.venv`s (454M + 674M + 721M). **venv must be excluded**, but
    # [EN]   not for size: **it cannot be relocated**. `pyvenv.cfg` and every console script carry the
    # [EN]   build machine's absolute paths, so it fails 100% on another machine. Shipping it means "a
    # [EN]   package that looks like it has dependencies but cannot use them". Dependencies are built at
    # [EN]   install time by `service_ctl.py prepare` -- that is exactly why it exists.
    # [EN] · "contains user data / API keys" -- **solved by sanitizing** instead of not shipping:
    # [EN]   `backend/.env`, `PenShot/.env`, `PlotPilot/.env` are copied with **secret fields blanked**
    # [EN]   (see `sanitize_service_envs`, same rule as the root `.env`); `凭据.txt`,
    # [EN]   `data/ai_story.db` (35M, 678 projects / 932 chapters) and `data/chroma_db` (123M, their
    # [EN]   vector index) are **still excluded** (user's choice 2026-10-21: empty DB, tables created on
    # [EN]   first start). `embedding/onnx` (458M vector model) **must ship**: a functional dependency,
    # [EN]   not user data; without it the service's memory/retrieval is simply unavailable.
    # [EN] ⚠ The three `.venv`s / `logs` / `__pycache__` / `.git` need no entries here --
    # [EN]   `EXCLUDE_DIR_NAMES` matches **by name**, so same-named dirs inside the services are already
    # [EN]   dropped. Only the path-specific ones (user data, credentials) are written here.
    # [EN] ⚠ Must exclude **before** copying, not delete after: 458M model + 1.85G venv would be copied
    # [EN]   then deleted (minutes of IO, and a failure mid-way leaves half a package).
    # ★ 2026-10-10 加：`launchers/` 是**构建工具链**（Go 源码 + 交叉编译脚本 +
    #   四个平台的产物，产物约 42MB）。它和 `developers/` 同类：**开发期为产品服务，
    #   本身不是产品**。发布包里**根目录**已经有本平台那三个启动器了。
    #   ⚠ 而且它**必须排除** —— 发布自检当场抓到 `launchers/build.py` 里写着本机
    #     绝对路径（`C:\Users\chao\...\go\1.27.2\go`）：那是"本机路径残留"，
    #     跟 `.install_manifest.json` 同一类，不该出现在给别人的包里。
    # [EN] ★ Added 2026-10-10: `launchers/` is a **build toolchain** (Go source + cross-compile scripts +
    # [EN] artifacts for four platforms, ~42MB of artifacts). It's the same class as `developers/`:
    # [EN] **serves the product at development time,
    # [EN] is not itself the product**. The release package **root** already has the three launchers for
    # [EN] this platform.
    # [EN] ⚠ And it **must be excluded** -- the release self-check caught on the spot that
    # [EN] `launchers/build.py` contains a local
    # [EN] absolute path (`C:\Users\chao\...\go\1.27.2\go`): that's "local path residue",
    # [EN] same class as `.install_manifest.json`, and should not appear in a package given to others.
    '启动器构建工具链（Go 源码 + 交叉编译产物；根目录已有本平台那三个）': ['launchers'],
    # ★ 2026-10-18 加：`novel_bench/` 是**开发期质量基准**（数据集 + 推演实录 +
    #   评审缓存 + 它自己的 `.env`）。它和 `developers/` 同类：**开发期用来量质量，
    #   本身不是产品**。而且里面的实录是用户机器上跑出来的正文，不该随包分发。
    # [EN] ★ Added 2026-10-18: `novel_bench/` is the **development-time quality benchmark**
    # [EN] (dataset + run transcripts + review cache + its own `.env`). Same class as `developers/`:
    # [EN] **it measures quality during development, it is not the product**. Its transcripts are
    # [EN] text generated on the user's machine and must not ship either.
    '质量基准（开发期评测工具，含实录与自有 .env）': ['novel_bench'],
}
#: **服务目录里按路径排除**的东西（2026-10-21 加）。
#:
#: 为什么不并进 `EXCLUDE_DIR_PATHS`：那个字典的口径是"从工程根算起的相对路径"，
#: 而这里要表达的是"服务目录内部的某个相对位置"。混在一起写会让
#: `make_ignore` 的判断条件越来越绕（它已经在按"先名字、再路径、再文件规则"分三档了）。
#: 单独一张表，语义干净：**前缀匹配**，命中即排除。
#:
#: ⚠ 这里只放"用户数据 / 凭据"。`.venv`、`logs`、`__pycache__`、`.git` 不写 ——
#:   `EXCLUDE_DIR_NAMES` 按名字匹配，服务目录里的同名目录**已经**被排除了。
#:   重复登记不会出错，但会让人以为"少写一条就漏"，反而更难维护。
# [EN] **Path-based exclusions inside the services directory** (added 2026-10-21).
# [EN] Why not merge into `EXCLUDE_DIR_PATHS`: that dict means "relative path from the project root",
# [EN] while this expresses "a position inside a service directory". Mixing them makes `make_ignore`'s
# [EN] condition even more convoluted (it already branches name -> path -> file rules).
# [EN] A separate table is cleaner: **prefix match**, hit means exclude.
# [EN] ⚠ Only "user data / credentials" go here. `.venv`, `logs`, `__pycache__`, `.git` are omitted --
# [EN]   `EXCLUDE_DIR_NAMES` matches by name and same-named dirs inside the services are already gone.
# [EN]   Duplicating them is not wrong, but implies "miss one and it leaks", which is harder to maintain.
SERVICE_EXCLUDE_PREFIXES: dict[str, list[str]] = {
    '服务里的用户创作数据（用户 2026-10-21 选定：不带，用空库）': [
        # ★ MuMu 的 `data/` **整个**排除：里面只有两样，都是用户数据
        #   （`ai_story.db` 35M = 678 个项目 / 932 章正文 / 8886 条故事记忆，
        #    `chroma_db` 123M = 那些正文的向量索引）。首次启动由服务自己建表
        #   （alembic 迁移在 `novelservice.py` 里），所以空着不影响启动。
        #   ⚠ 排"整个目录"而不是逐个文件：索引库是**目录**，逐文件列再加一个
        #     新分片就漏了 —— 而漏一次就是把用户的正文发出去。
        # [EN] ★ MuMu's `data/` is excluded **whole**: it holds only two things, both user data
        # [EN] (`ai_story.db` 35M = 678 projects / 932 chapters / 8886 memories; `chroma_db` 123M = their
        # [EN] vector index). Tables are created on first start (alembic in `novelservice.py`), so an
        # [EN] empty dir does not break startup.
        # [EN] ⚠ Exclude the **whole directory**, not file by file: the index is a **directory**, and
        # [EN] listing files one by one misses a new shard -- and one miss ships the user's prose.
        'novelservices/MuMuAINovel/backend/data',
        # 服务自己产出的稿件/导出
        # [EN] Drafts/exports produced by the service itself
        'novelservices/MuMuAINovel/output',
        # ★ PenShot 的 data 里**混着**模型与用户数据，所以只能按子目录排：
        #   `embedding` / `models` 是功能依赖（留），`checkpoints` / `memory` / `output` 是
        #   运行期产物（24M + 500K + 609K，含用户写的内容）。
        # [EN] ★ PenShot's data **mixes** models with user data, so exclude per subdirectory:
        # [EN] `embedding` / `models` are functional dependencies (keep); `checkpoints` / `memory` /
        # [EN] `output` are runtime artifacts (24M + 500K + 609K, containing what the user wrote).
        'novelservices/PenShot/data/checkpoints',
        'novelservices/PenShot/data/memory',
        'novelservices/PenShot/data/output',
        # PlotPilot：库 + 草稿
        # [EN] PlotPilot: the DB and drafts
        'novelservices/PlotPilot/data/plotpilot.db',
        'novelservices/PlotPilot/data/plotpilot.db-journal',
        'novelservices/PlotPilot/data/drafts',
    ],
    '服务里的凭据（明文，绝不外发）': [
        # 实测存在：`novelservices/MuMuAINovel/凭据.txt`，内容是账号密码。
        # [EN] Actually present: `novelservices/MuMuAINovel/凭据.txt`, containing account credentials.
        'novelservices/MuMuAINovel/凭据.txt',
        'novelservices/PenShot/凭据.txt',
        'novelservices/PlotPilot/凭据.txt',
    ],
    '服务自己的日志与构建产物': [
        'novelservices/PenShot/logs',
        'novelservices/PenShot/build',
        'novelservices/PlotPilot/logs',
    ],
    '服务里的**开发期一次性脚本**（服务运行不读，且写着本机绝对路径）': [
        # 2026-10-21（发布 0.3.2 时自检报的本机路径残留）：
        #   `run_mowenlou.py` 里硬编码了 `C:/Users/chao/.../.env`；
        #   `verify_foreshadows.py` 里硬编码了 `C:/Users/chao/桌面/望江楼模拟项目/...`。
        #   两个都是"当初灌《望江楼》时用一次的脚本"，服务进程**不会** import 它们
        #   （`novelservice.py` 只跑 `app.main`）。留着等于把本机路径发给别人。
        # [EN] Reported by the 0.3.2 self-check as leftover local paths: `run_mowenlou.py` hardcodes
        # [EN] `C:/Users/chao/.../.env` and `verify_foreshadows.py` hardcodes a local project path.
        # [EN] Both are one-shot scripts used when seeding 《望江楼》; the service process never imports
        # [EN] them (`novelservice.py` only runs `app.main`). Keeping them ships our absolute paths.
        'novelservices/MuMuAINovel/run_mowenlou.py',
        'novelservices/MuMuAINovel/verify_foreshadows.py',
    ],
}

#: `logo_drafts/` 里**只有这一个**是产品运行时读的，其余都是设计草稿。
#:
#: ★★★ 2026-10-21（用户：「清理掉这些历史遗留」）：这个目录曾被整个打进发布包 ——
#:   22 个文件 / 17MB，包含六个 logo 方案（A~F）、标题背景草稿、各种 icon 版本。
#:   用户拿到包里会看到一堆「A_工笔仕女·半身·发间狐耳.png」这种文件名，莫名其妙。
#:
#: ★ 为什么**不能整目录排除**（这是本条的关键）：
#:   `image_gen/round_start_logo.py` 的圆角功能**运行时读** `logo_drafts/start_logo_pre-rounded.png`
#:   —— 那是"方角原图"备份。它的存在使圆角**参数可反复重设**：每次都从方角原图重新 apply
#:   当前半径。缺了它，代码会退回"把当前（已圆角的）图当原图"，于是改半径、包括关掉圆角，
#:   都**看不出变化**（旧透明被保留）。也就是说：整目录排除 = 悄悄改坏一个功能。
#:   ⇒ 只留这一个文件，其余按白名单排掉（见 `_ignore` 里的 `LOGO_DRAFT_DIR` 分支）。
#: [EN] ★★★ 2026-10-21 (user: "clean up these historical leftovers"): this directory used to ship
#: [EN] whole -- 22 files / 17MB, six logo options (A~F), title-background drafts, icon variants.
#: [EN] Users would see "A_工笔仕女·半身·发间狐耳.png" and wonder what it was.
#: [EN] ★ Why the directory **cannot be excluded wholesale** (the crux): `image_gen/round_start_logo.py`
#: [EN] **reads** `logo_drafts/start_logo_pre-rounded.png` at runtime -- the square-original backup.
#: [EN] It is what makes the corner radius re-settable: every run re-applies the current radius to the
#: [EN] square original. Without it the code falls back to treating the current (already rounded) image
#: [EN] as the original, so changing the radius -- including turning rounding off -- shows **no change**
#: [EN] (old transparency persists). Whole-directory exclusion would silently break a feature.
#: [EN] => Keep only this one file; whitelist the rest (see the `LOGO_DRAFT_DIR` branch in `_ignore`).
LOGO_DRAFT_DIR = 'logo_drafts'
LOGO_DRAFT_KEEP = {'start_logo_pre-rounded.png'}

EXCLUDE_FILE_GLOBS: dict[str, list[str]] = {
    # ★★★ 2026-10-21（发布 0.3.2 时**打包当场崩了**才发现）：
    #   工程根目录躺着一个叫 `nul` 的 0 字节文件 —— Git Bash 里写 `> nul`（本想重定向到
    #   空设备）会**真的建出一个文件**，而 `nul` 是 Windows 的**保留设备名**：
    #   `shutil.copytree` 读它会 `[WinError 87] The parameter is incorrect`，
    #   整个打包直接失败（报错指向 `nul`，但没人会想到自己根目录里有这么个东西）。
    #   ⇒ 排除掉：它 0 字节、任何 Windows 程序都打不开，本来就不是产品的一部分。
    #   ⚠ 用 `[Nn][Uu][Ll]` 而不是 `nul`：三平台 fnmatch 语义不同
    #     （Windows 大小写不敏感、Linux 敏感），写成字符组两边都对。
    #   ⚠ 保留名不止这一个：`CON` / `PRN` / `AUX` / `COM1..9` / `LPT1..9` 全都同病。
    #     这里一次列全，免得换台机器换个名字再崩一次。
    # [EN] ★★★ 2026-10-21 (found because **packaging 0.3.2 crashed on the spot**): the project root
    # [EN] had a 0-byte file named `nul` -- in Git Bash `> nul` (intending the null device) **really
    # [EN] creates a file**, and `nul` is a Windows **reserved device name**: `shutil.copytree` reading
    # [EN] it raises `[WinError 87] The parameter is incorrect` and the whole build fails (the error
    # [EN] points at `nul`, but nobody expects such a thing in their project root).
    # [EN] => Exclude it: 0 bytes, unopenable by any Windows program, never part of the product.
    # [EN] ⚠ `[Nn][Uu][Ll]` rather than `nul`: fnmatch semantics differ across platforms (Windows
    # [EN] case-insensitive, Linux sensitive); a character class is right on both.
    # [EN] ⚠ It is not the only reserved name: `CON` / `PRN` / `AUX` / `COM1..9` / `LPT1..9` all behave
    # [EN] the same. Listed in full here so a different machine does not crash on another one.
    'Windows 保留设备名（Git Bash 下 `> nul` 会建出真文件，复制时 WinError 87）': [
        '[Nn][Uu][Ll]', '[Cc][Oo][Nn]', '[Pp][Rr][Nn]', '[Aa][Uu][Xx]',
        '[Cc][Oo][Mm][1-9]', '[Ll][Pp][Tt][1-9]',
    ],
    '密钥与本地配置': ['.env', '.env.*'],
    '安装记录（含本机绝对路径）': ['.install_manifest.json'],
    # ★★★ 2026-10-21（重新发布 0.3.2 时**逐层核对包里内容**才发现的，之前每一版都带着）：
    #   ① `*.old-*` —— `launchers/build.py` 覆盖根目录 exe 时留下的备份（占用时改名再复制）。
    #      实测根目录躺着一个 3.5MB 的 `start.exe.old-1792212572`（10/17 的），
    #      四个平台的包**每包都带一份**。`.gitignore` 只写了 `*.bak`，没有这种形态。
    #   ② `.workbuddy/` —— **AI 开发工作目录**（`memory/YYYY-MM-DD.md` 是逐日开发日志：
    #      用户的原话、内部设计取舍、踩过的坑）。这是**开发内幕**，比密钥更不该外发：
    #      它不泄密密钥，但会把"这本书是怎么被一段段试错做出来的"整份给出去。
    #      ⚠ 只能按**目录名**排除：它出现在根目录、以及每个项目子目录里。
    #   ③ `.ui_state/` —— 运行期的界面状态（本机窗口尺寸、上次停在哪一页）。属于"本机状态"，
    #      与 `.install_manifest.json` 同类：带出去只会让新用户开局就落在一个陌生的界面状态上。
    #   ⚠ 这三条都**不报错、不影响运行**，所以只能靠"检查包里到底有什么"发现 ——
    #     正是本项目反复强调的那一类："缺了/多了都不报错，只有人去看才发现"。
    # [EN] ★★★ 2026-10-21 (found by **auditing what is actually inside the package** while
    # [EN] re-releasing 0.3.2; every earlier release carried these):
    # [EN] ① `*.old-*` -- the backup `launchers/build.py` leaves when overwriting the root exe
    # [EN]    (rename-then-copy when the file is locked). Measured: a 3.5MB
    # [EN]    `start.exe.old-1792212572` from 10/17 sitting in the root, copied into **all four**
    # [EN]    packages. `.gitignore` only had `*.bak`, not this shape.
    # [EN] ② `.workbuddy/` -- the **AI development workspace** (`memory/YYYY-MM-DD.md` is a daily dev
    # [EN]    log: the user's own words, internal design trade-offs, mistakes made). This is
    # [EN]    **inside information** -- worse to ship than a key: it does not leak a secret, it hands
    # [EN]    over "how this book was built by trial and error".
    # [EN]    ⚠ Must be excluded **by directory name**: it appears at the root and inside project dirs.
    # [EN] ③ `.ui_state/` -- runtime UI state (window size, last page). Same class as
    # [EN]    `.install_manifest.json`: shipping it only makes a new user start in a strange state.
    # [EN] ⚠ None of the three errors out or breaks anything, so only "look at what is in the package"
    # [EN] finds them -- exactly the category this project keeps stressing.
    #: ① 启动器替换时留下的备份（`start.exe.old-1792212572` 这种形态）
    # [EN] ① backups left by launcher replacement (`start.exe.old-1792212572`)
    '启动器替换留下的备份（`*.bak` 之外还有这种形态）': ['*.old-*'],
    # ★★★ 2026-10-21（用户：「清理掉这些历史遗留」）：**开发期的测试正文与设计草稿**。
    #   · `雪国_*.md`（12 个）+ `雪国重跑记录.md` —— 拿「雪国」那本书反复重跑出来的**正文**，
    #     是调文风时的对照样本，不是产品的一部分；
    #   · `snow_ykg1000*.md` —— 同样是调参用的文本夹具（`developers/probe_*.py` 读它们）。
    #   两者加起来约 70KB，体积不是问题，问题是**用户会把它们当成产品自带的示例**。
    # [EN] ★★★ 2026-10-21 (user: "clean up these historical leftovers"): **dev-time test prose and
    # [EN] design drafts**. `雪国_*.md` (12) + `雪国重跑记录.md` are bodies produced by re-running the
    # [EN] "Snow Country" book over and over while tuning style; `snow_ykg1000*.md` are parameter-tuning
    # [EN] fixtures read by `developers/probe_*.py`. About 70KB -- size is not the issue; the issue is
    # [EN] that **users would read them as sample content shipped with the product**.
    '开发期测试正文（调文风时反复重跑出来的稿子，不是产品内容）': [
        '雪国_*.md', '雪国重跑记录.md', 'snow_ykg1000*.md', 'snow_ykg1000b.md',
    ],
    # ★ 2026-10-14 加（发布 0.3.1 时**发布前自检当场抓到**）：`llm_models.json`
    #   是「AI 模型配置」那一页的**模型登记表**，每条都带 `api_key`。
    #   `.gitignore` 里早就写了它（L15），但**可排除清单里一直没有** ——
    #   于是 `make_release.py` 复制时把它整份搬进了发布包。
    #   发布前自检的"拿真实密钥去全文搜"那条当场报红：
    #     ✗ ★ 发布包里出现了真实 API Key：['llm_models.json']
    #     ✗ ★ 疑似密钥字面量（sk-…）：['llm_models.json']
    #   ⚠ 它和 `.env` 是**同一类**（含真实密钥的本地配置）。
    # [EN] ★ Added 2026-10-14 (the **pre-release self-check caught it on the spot** while publishing
    # [EN] 0.3.1): `llm_models.json` is the **model registry** on the "AI model config" page; every
    # [EN] entry carries an `api_key`. `.gitignore` already listed it (L15), but the **exclusion list
    # [EN] never had it** -- so `make_release.py` copied the whole thing into the release. The
    # [EN] pre-release self-check's "search the full text with the real secret" rule went red:
    #   ✗ ★ real API key found in package: ['llm_models.json']
    #   ✗ ★ suspected secret literal (sk-...): ['llm_models.json']
    # [EN] ⚠ It's the **same class** as `.env` (local config containing real secrets).
    '模型登记表（含 API Key）': ['llm_models.json'],
    '全局消息（运行期状态）': ['.nws_messages.jsonl'],
    # ★ 2026-10-11 加（用户原话：「使用脚本清理掉所有不需要和不允许发布出去的
    #   **脚本和配置以及日志**等文件」）—— 这三类都是**本机过程产物**，
    #   `.gitignore` 里已经写明「不该提交」，但发布脚本的可排除清单里一直没有它们：
    #     · `usage.db`：LLM 用量台账（这位用户自己的调用与花费，14MB 级）；
    #     · `*.bak-bilingual`：注释双语化的**写前备份**，与源码同名同目录，
    #       会被当成"源码"一起放进发布包（全项目 260 多份）；
    #     · `.bilingual_done.json`：双语化的续跑记录（46KB）。
    #   它们**不是产品**，而且 bak 文件会让"发布包里的源码"看起来重了一份。
    # [EN] ★ Added 2026-10-11 (user's words: "use the script to clean out all scripts, configs and
    # [EN] logs etc. that are not needed and must not be published") -- these three are **local process
    # [EN] artifacts**; `.gitignore` already says "never commit", yet the release script's exclusion list
    # [EN] never had them:
    # [EN] · `usage.db`: the LLM usage ledger (this user's own calls and spend, ~14MB);
    # [EN] · `*.bak-bilingual`: the pre-write backups of the comment-bilingualization pass, sitting next
    # [EN] to the sources under the same names (260+ across the project);
    # [EN] · `.bilingual_done.json`: the resume record of that pass (46KB).
    # [EN] They are **not the product**, and the bak files make "the sources in the release package" look
    # [EN] duplicated.
    'LLM 用量台账（本机运行期数据）': ['usage.db', 'usage.db-journal'],
    # ★ 2026-10-21 加（发布 0.3.2 时自检报的 `残留数据库文件：['llm_cache.db']`）：
    #   `llm_cache.db` 是 **LLM 响应缓存**，表里存着用户的 prompt 与模型返回的正文。
    #   它和 `usage.db` 同类（运行期数据、含用户内容），但**可排除清单里一直没有它**。
    # [EN] ★ Added 2026-10-21 (the 0.3.2 self-check reported
    # [EN] `leftover database files: ['llm_cache.db']`): it is the **LLM response cache**;
    # [EN] its rows hold the user's prompts and the model's prose. Same class as `usage.db`
    # [EN] (runtime data with user content) but **never in the exclusion list**.
    'LLM 响应缓存（含用户 prompt 与正文）': ['llm_cache.db', 'llm_cache.db-journal'],
    '注释双语化的本机备份与续跑记录': ['*.bak-bilingual', '.bilingual_done.json'],
    '日志文件': ['*.log'],
    'Python 字节码': ['*.py[cod]'],
    '系统垃圾文件': ['.DS_Store', 'Thumbs.db', 'desktop.ini'],
    # ★★★ 2026-10-22（重新发布 0.3.2 时**自检当场抓到**）：
    #   这里原来写的是 `'*.bak'` —— 只认"以 `.bak` 结尾"。
    #   而实测包里有五个 `*.bak-<后缀>` 形态的历史备份：
    #     `llm_models.json.bak-before-临时指向`（★ 里面有**真 API Key**）、
    #     `sim/loop.py.bak-20261015_234115`、`assets/app_icon.*.bak-20261012` …
    #   `*.bak` 一个都不命中 ⇒ 排除表、兜底清扫、自检三处**同时漏掉**，
    #   而自检靠"拿真 key 全文搜"才把它抓出来（报了两条红）。
    #   ⚠ 形态判据要覆盖**前缀**而不是结尾：备份文件名几乎都是"原名 + 标记 + 时间/原因"。
    # [EN] ★★★ 2026-10-22 (the self-check **caught this on the spot** while re-releasing 0.3.2):
    # [EN] this used to be `'*.bak'` -- "ends with `.bak`". Measured: five `*.bak-<suffix>` backups were
    # [EN] in the package (`llm_models.json.bak-before-临时指向` -- holding a **real API key** --
    # [EN] `sim/loop.py.bak-20261015_234115`, `assets/app_icon.*.bak-20261012` ...). `*.bak` matched
    # [EN] none of them, so the exclusion table, the fallback sweep and the leftover check all missed
    # [EN] them at once, and only "search the full text with the real key" reported it (two reds).
    # [EN] ⚠ Backup names are "original + marker + time/reason", so the pattern must match a **prefix**.
    '开发期产物（含 `*.bak-<时间/原因>` 这类历史备份）': [
        '*.orig', '*.rej', '*.bak*', '*.old*',
    ],
    # ★★★ 2026-10-26（重新发布 0.3.3 时**逐文件核对抓到的**）：
    #   SQLite 开 WAL 模式后，一个库会带**两个伴生文件**：
    #     `xxx.db-wal`（预写日志，**可能含未提交的用户数据**）
    #     `xxx.db-shm`（共享内存索引，**换台机器毫无意义**，且每次运行都变）
    #   排除表里只写了 `.db` 和 `.db-journal`，两者都漏 ⇒ 实测包里出现了
    #   `novelservices/PlotPilot/data/plotpilot.db-shm`(32KB) + `.db-wal`(0B)，
    #   而 `plotpilot.db` 本体是被排除的 —— 于是包里躺着**两个没有主库的孤儿文件**。
    #   危害有两层：① `-wal` 里的未提交数据跟着发出去；② 孤儿文件让 SQLite 打开时
    #   行为不确定（它按文件名找主库，主库不在就是垃圾）。
    #   ⚠ 用**通配**而不是补两条具体路径：任何库都可能开 WAL，补具体路径等于等着下次再漏。
    #   （与 `*.bak` 那条同一个教训：排除项要覆盖**形态**，不要穷举文件名。）
    # [EN] ★★★ 2026-10-26 (caught while re-releasing 0.3.3, by checking file by file): SQLite in
    # [EN] WAL mode has **two companion files**: `xxx.db-wal` (the write-ahead log, **possibly
    # [EN] holding uncommitted user data**) and `xxx.db-shm` (a shared-memory index that is
    # [EN] **meaningless on another machine** and changes every run). The table listed only `.db` and
    # [EN] `.db-journal`, so both slipped through -- measured: `plotpilot.db-shm` (32KB) and
    # [EN] `.db-wal` (0B) were in the package while `plotpilot.db` itself was excluded, leaving **two
    # [EN] orphans without their database**. Two harms: (1) uncommitted `-wal` data ships; (2)
    # [EN] orphan files make SQLite's behaviour undefined. ⚠ Use a **pattern**, not two more paths:
    # [EN] any database may enable WAL, and adding exact paths just waits for the next miss. (Same
    # [EN] lesson as `*.bak`: exclude by **shape**, do not enumerate filenames.)
    'SQLite 的 WAL 伴生文件（含未提交数据 / 换机无意义）': [
        '*.db-wal', '*.db-shm',
    ],
}
# `tools/` 只留装机脚本要用到的那一个（其余是 verify_* 开发验证）
#: `tools/` 里随包发布的**装机链路**用到的脚本。
#: ★ 2026-10-10 加 `launcher_progress.py`：三个启动器要装依赖时会拉起它弹进度窗。
#:   缺了**不会崩**（启动器会退回"静默执行 + 原生弹框"，这条降级本身也有判据守），
#:   但用户在那几分钟里就什么都看不见了 —— 正是"缺了只是难看、不报错"的那一种，
#:   得由这里兜住。
# [EN] `tools/` keeps only the one used by the installer script (the rest are verify_* dev validation)
# [EN] : scripts under `tools/` used by the **install chain** shipped with the package.
# [EN] : ★ Added 2026-10-10 `launcher_progress.py`: the three launchers pull it up to show a progress
# [EN] window when installing dependencies.
# [EN] : Missing it **won't crash** (the launcher falls back to "silent execution + native dialog", and
# [EN] that fallback itself is guarded by a criterion),
# [EN] : but the user sees nothing for those few minutes -- exactly the kind of "missing is only ugly,
# [EN] not an error" case,
# [EN] :   which must be caught here.
TOOLS_KEEP = {'platform_install.py', 'launcher_progress.py', 'launcher_splash.py'}
# ★★★ 2026-10-21 补进 `launcher_splash.py` —— 这是**真缺陷**，不是"顺手加一个文件"：
#   启动器（`launchers/flow.go`，`splashRel = "tools/launcher_splash.py"`）在启动时拉起它画那块
#   "书封"窗口；文件不在就 `lg.printf("没有 … ⇒ 不显示启动窗口")` 然后**静默降级**。
#   而它一直没在这张表里 ⇒ **发布版用户从来没见过启动画面**（开发机根目录里有这个脚本，
#   所以本地跑 `start.exe` 一切正常，发布包里却什么都没有 —— 正是"缺了不报错"那一类）。
#   ⚠ 判据也补了：`developers/check_release.py` 的 `NEED` 里有它，再漏就会当场报红。
#   ⚠ 依赖：`tkinter`（stdlib）+ `Pillow`（`requirements.txt` 里有；且 splash 里是**局部
#     import + try**，缺了只退回系统字体，窗口照样出）。
# [EN] ★★★ 2026-10-21 added `launcher_splash.py` -- a **real defect**, not a casual addition:
# [EN] the launcher (`launchers/flow.go`, `splashRel = "tools/launcher_splash.py"`) starts it to draw
# [EN] the "book cover" window; when the file is missing it prints "no ... => no splash window" and
# [EN] **silently degrades**. It was never in this table => **release users never saw the splash**
# [EN] (the dev machine's root dir has the script, so `start.exe` works locally while the release
# [EN] package has nothing -- exactly the "missing is silent" category).
# [EN] ⚠ A criterion was added too: it is in `NEED` of `developers/check_release.py`.
# [EN] ⚠ Dependencies: `tkinter` (stdlib) + `Pillow` (in `requirements.txt`; and the splash imports it
# [EN] **locally inside try**, so a missing Pillow only falls back to a system font -- the window still
# [EN] appears).
# 开发向文档 —— **只按"根目录文件名"排除**。
# ★ 2026-10-10 改判：这里原来写的是 `{'Configuration_Classification.md', '配置分类.md'}`，
#   理由"描述哪些配置项已从程序里删除、引用 config.py 与 tools/，不适合终端用户"——**判断错了**。
#   那两份《配置分类》讲的是"配置放在哪一层、作用范围、优先级"，是**用户文档**：
#   README.md / README_EN.md / 使用说明.md / User_Manual.md / 配置指南.md /
#   Configuration_Guide.md **六处**都把链接指向它。按旧清单排除，发布包里这些链接**全是断的**
#   （实测：0.1.0 发布包的 README 就链到了不存在的 `配置分类.md`）。
#   已改判为用户文档 → 随包发布，并加进下面的 `REQUIRED` 由自检兜住。
#   真正开发向的文档已统一搬进 `developers/docs/`，而 `developers/` **整目录被排除**，
#   所以不再需要用"点名"的方式排除文档。留一个空集合只为保住 `--keep-dev-docs` 这个开关。
# [EN] Development-oriented docs -- **excluded only by "root directory filename"**.
# [EN] ★ 2026-10-10 reclassified: this used to say `{'Configuration_Classification.md', '配置分类.md'}`,
# [EN] with the rationale "describes which config items were removed from the program, references
# [EN] config.py and tools/, not suitable for end users" -- **wrong call**.
# [EN] Those two 《配置分类》 documents explain "which layer config lives in, scope, priority" -- they are
# [EN] **user docs**:
# [EN] Configuration_Guide.md -- **six places** link to them. Excluded per the old list, those links in
# [EN] the release package are **all broken**
# [EN] (measured: the 0.1.0 release package's README linked to a nonexistent `配置分类.md`).
# [EN] Reclassified as user docs → shipped with the package, and added to the `REQUIRED` below so
# [EN] self-check guards it.
# [EN] The truly dev-oriented docs have been uniformly moved into `developers/docs/`, and `developers/`
# [EN] **is excluded wholesale**,
# [EN] so there's no longer any need to exclude docs by "naming them". An empty set is kept only to
# [EN] preserve the `--keep-dev-docs` switch.
DEV_DOCS: set[str] = set()

# 发布版**必须**有的东西 —— 缺任何一项都算发布包不完整
#: 三个启动器的**模式名**（`launchers/build.py` 编出来的就是这三个）。
# [EN] Things the release build **must** have -- missing any one means the release package is
# [EN] incomplete
# [EN] : the three launchers' **mode names** (what `launchers/build.py` produces is exactly these
# [EN] three).
LAUNCHER_MODES = ('setup', 'start', 'uninstall')
#: 平台取值 → `launchers/dist/` 下的**目录名**（一一对应）。
#:
#: ★★ 2026-10-22：这张表**不再决定"打哪个平台的包"**（一个包带全部四套），只决定
#:   「`启动器/其他平台/` 下放哪几个目录」以及「自检时每个平台该读到什么魔数」。
#:   取值名保持不变 —— 四个名字本来就是**平台**的名字，不是"包"的名字。
# [EN] : platform value -> the **directory name** under `launchers/dist/` (one-to-one).
# [EN] ★★ 2026-10-22: this table **no longer decides which platform's package to build** (one package
# [EN] carries all four sets); it only decides which directories go into `启动器/其他平台/` and which
# [EN] magic each platform should read in the self-check. The value names stay -- the four names are
# [EN] **platforms**, not packages.
LAUNCHER_SETS = {
    'windows': 'windows-amd64',
    'macos': 'darwin-arm64',          # Apple Silicon
    'macos-intel': 'darwin-amd64',    # Intel Mac
    'linux': 'linux-amd64',
}
#: 取值 → 给人看的平台名（写进 `平台说明.md` 与自检报告）。
# [EN] : value -> human-readable platform name (written into `平台说明.md` and self-check reports).
PLATFORM_LABEL = {
    'windows': 'Windows（64 位）',
    'macos': 'macOS · Apple Silicon（M 系列芯片）',
    'macos-intel': 'macOS · Intel（x86_64）',
    'linux': 'Linux（64 位，amd64）',
}
#: 包里放"别的平台启动器"的目录（相对包根）。四个平台里**打包机那一套在根目录**，
#: 其余三套在这里各占一个子目录。
# [EN] : where the "other platforms' launchers" live inside the package (relative to the package
# [EN] root). Of the four sets, **the build host's is in the root**; the other three get a subdir here.
LAUNCHER_STAGE_DIR = '启动器'
OTHER_PLATFORM_DIR = '其他平台'
#: 发布根目录：**工程目录的同级**（`小说世界AI模拟/发布版本`）。
#: ★ 与工程同级而不是工程内部：发布物一旦落在工程里，下次"整棵复制"就会把它自己拷进去
#:   （`make_ignore` 也会多一条要维护的排除项）。
# [EN] : the release root: **sibling of the project directory** (`小说世界AI模拟/发布版本`).
# [EN] ★ Sibling rather than inside the project: a release living inside the tree would be copied into
# [EN] the next release (and `make_ignore` would need another exclusion to maintain).
RELEASE_ROOT = APP_DIR.parent / '发布版本'


def host_platform() -> str:
    """本机是哪个平台 —— 决定工程根目录现在放的是哪一套启动器。
        English:
    Which platform is the local machine —— determines which set of launchers is currently in the
    project root.
    """
    import platform as _p
    if sys.platform.startswith('win'):
        return 'windows'
    if sys.platform == 'darwin':
        return 'macos'
    return 'linux'


def required_launchers(plat: str) -> list[str]:
    """该平台的三个启动器**文件名**（发布包里必须有）。
        English:
    The three launcher **filenames** for that platform (must be present in the release package).
    """
    return [m + ('.exe' if plat == 'windows' else '') for m in LAUNCHER_MODES]


#: 各平台启动器应该是什么魔数（`developers/probe_launcher_magic.py` 的判据口径）。
#: 格式：`(类型, 期望值)`；`elf_machine` / `macho_cpu` 是**进一步**判架构的那一位。
# [EN] : the magic each platform's launcher should have (same criteria as
# [EN] `developers/probe_launcher_magic.py`). Format: `(kind, expected)`; `elf_machine` /
# [EN] `macho_cpu` further pin down the architecture.
#: 「提示」类条目的前缀 —— 带它的条目**不算失败**（见 `main()` 里那段说明）。
# [EN] : prefix for "note" entries -- anything carrying it **does not count as a failure** (see the
# [EN] explanation in `main()`).
NOTE_PREFIX = 'ℹ'
_MACHO_MAGIC = (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe')
_CPU_X86_64 = 0x01000007
_CPU_ARM64 = 0x0100000C


def launcher_platform(path: Path) -> str:
    """读启动器的头部字节，判它是哪个平台/架构（读不出回 `?`）。

    ★★ 为什么非要读魔数：**文件名判不出来** —— Windows 叫 `setup.exe`，
      而 Linux 与 macOS 都叫 `setup`（同名、内容不同）。发布包里"给的是哪一套"
      只有魔数证得了。补上这条之后，"把 Windows 包发给了 Mac 用户"这类错
      **当场量得出来**，不靠人记得。
    
        English:
    Read a launcher's header bytes and determine its platform/architecture (`?` when unreadable).
        ★★ Why the magic must be read: **the filename cannot tell you** -- Windows is `setup.exe`
        while Linux and macOS are both `setup` (same name, different content). Only the magic can
        prove "which set this is" in a release package. With this in place, errors like "a Windows
        package sent to a Mac user" become **measurable on the spot**, not dependent on someone
        remembering.
    """
    try:
        head = path.read_bytes()[:20]
    except OSError:
        return '?'
    if len(head) < 8:
        return '?'
    if head[:2] == b'MZ':
        return 'windows'
    if head[:4] == b'\x7fELF':
        machine = int.from_bytes(head[18:20], 'little') if len(head) >= 20 else 0
        return {0x3E: 'linux-amd64', 0xB7: 'linux-arm64'}.get(machine, 'linux-?')
    if head[:4] in _MACHO_MAGIC:
        cpu = int.from_bytes(head[4:8], 'little')
        if cpu == _CPU_ARM64:
            return 'macos-arm64'
        if cpu == _CPU_X86_64:
            return 'macos-amd64'
        return f'macos-0x{cpu:08x}'
    if head[:4] == b'\xca\xfe\xba\xbe':
        return 'macos-universal'
    return 'other:' + head[:4].hex()


#: 取值 → 该包**唯一允许**出现的启动器平台（`None` = 不检查，即 `all` / `none`）。
# [EN] : value → the **only** launcher platform allowed in that package (`None` = skip the check, i.e.
# [EN] `all` / `none`).
ALLOWED_LAUNCHER_PLATFORM = {
    'windows': {'windows'},
    'linux': {'linux-amd64', 'linux-arm64'},
    'macos': {'macos-arm64', 'macos-universal'},
    'macos-intel': {'macos-amd64', 'macos-universal'},
}


def launcher_platforms_in_dir(path: Path) -> dict:
    """某目录里那三个启动器**各自**被判成什么平台 → `{平台: [文件名]}`。
        English:
    What platform each of the three launchers in a directory is judged to be -> `{platform: [names]}`.
    """
    out: dict[str, list[str]] = {}
    for name in [m + '.exe' for m in LAUNCHER_MODES] + list(LAUNCHER_MODES):
        p = path / name
        if p.is_file():
            out.setdefault(launcher_platform(p), []).append(name)
    return out


def stage_launcher_sets(dst: Path, src: Path, log: list[str]) -> tuple[list[str], dict[str, str]]:
    """四套启动器各有落点：**打包机那套在根目录，其余三套进 `启动器/其他平台/<平台>/`**。

    ★★★ 为什么是"全带"而不是"只带本机那套"（2026-10-22 改判的核心）：
      旧流程一个版本打四个包，每个包只放自己那平台的一套。改成"一个版本一个文件夹"后，
      如果只留打包机那套，Mac / Linux 用户拿到的包**根目录三个文件双击没有任何反应，
      而且包里再也找不到别的东西** —— 因为 `launchers/` 整个目录是按路径排除的
      （构建工具链，`build.py` 里写着本机 Go 路径）。这不是"少个便利"，是"那个平台用不了"。
      ⇒ 其余三套（各 3 个文件、共约 30MB）单独放一层，`平台说明.md` 写明怎么取用。

    ★ 每套都**读魔数核对**再算数：`launcher_platform()` 认的是二进制头，不是文件名。
      实测过文件名完全证不了 —— Windows 是 `setup.exe`，Linux 与 macOS 都叫 `setup`。

    ★ 取不到某套时**返回问题**、不静默跳过：旧脚本的 `swap_launchers` 就在这里栽过
      （"目录不存在 → return"，于是安静地产出一个缺平台文件的包）。
      `--force` 打不出真错就会变成"每次都绿"的假判据。

    返回 `(问题列表, {平台: 包内落点})`。
        English:
    Give each of the four launcher sets a home: **the build host's in the root, the other three under
    `启动器/其他平台/<platform>/`**.
    ★★★ Why include all instead of only the host's (the core of the 2026-10-22 reclassification): the
      old flow built four packages per version, each with its own set. With "one folder per version",
      keeping only the host's set leaves a Mac/Linux user with three root files that do nothing **and
      no other source** -- `launchers/` is excluded by path (build toolchain, local Go paths). That is
      not "a missing convenience", it is "unusable on that platform".
      => The other three sets (~30MB total) ship in their own layer, with `平台说明.md` explaining use.
    ★ Every set is **verified by magic** first: `launcher_platform()` reads the binary header, not the
      name (measured: the name proves nothing -- Windows is `setup.exe`, Linux and macOS are `setup`).
    ★ A missing set **returns a problem** instead of being skipped silently: the old `swap_launchers`
      was burned exactly there ("dir missing -> return", quietly producing a package without that
      platform's files), which would make a criterion that always passes.
    Returns `(problems, {platform: path inside the package})`.
    """
    problems: list[str] = []
    staged: dict[str, str] = {}
    host = host_platform()
    dist = src / 'launchers' / 'dist'
    for key, dirname in LAUNCHER_SETS.items():
        setdir = dist / dirname
        names = required_launchers(key)
        allowed = ALLOWED_LAUNCHER_PLATFORM.get(key) or set()
        if key == host:
            # 根目录这一套本来就是工程根目录里的（`copytree` 已经复制过来了）；
            # 缺哪个就从 `launchers/dist/` 补哪个，一个都不缺就什么都不做。
            # [EN] The root set came with `copytree`; fill in whatever is missing from `launchers/dist/`.
            missing = [n for n in names if not (dst / n).is_file()]
            if missing:
                if not setdir.is_dir():
                    problems.append(f'★ 根目录缺启动器 {missing}，且 launchers/dist/{dirname} 不存在')
                    continue
                for n in missing:
                    shutil.copy2(setdir / n, dst / n)
                    log.append(f'根目录启动器 {n}（补自 launchers/dist/{dirname}）')
            got = set(launcher_platforms_in_dir(dst))
            stray = sorted(got - allowed) if allowed else []
            if stray:
                problems.append(f'★ 根目录启动器不是本机平台（{host}）：实测 {sorted(got)}')
            staged[key] = '（根目录）'
            continue
        if not setdir.is_dir():
            problems.append(f'★ 缺 {PLATFORM_LABEL.get(key, key)} 那一套启动器：'
                            f'launchers/dist/{dirname} 不存在'
                            f'（先跑 python launchers/build.py）')
            continue
        out = dst / LAUNCHER_STAGE_DIR / OTHER_PLATFORM_DIR / key
        out.mkdir(parents=True, exist_ok=True)
        copied = 0
        for n in names:
            s = setdir / n
            if not s.is_file():
                problems.append(f'★ {PLATFORM_LABEL.get(key, key)} 那套少了 {n}'
                                f'（launchers/dist/{dirname}）')
                continue
            shutil.copy2(s, out / n)
            copied += 1
        got = set(launcher_platforms_in_dir(out))
        stray = sorted(got - allowed) if allowed else []
        if stray:
            problems.append(f'★ {PLATFORM_LABEL.get(key, key)} 那套启动器魔数不对：实测 {sorted(got)}')
        if copied:
            staged[key] = f'{LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/{key}'
            log.append(f"启动器 {PLATFORM_LABEL.get(key, key)} → {staged[key]}（{copied} 个文件）")
    return problems, staged


def launcher_platforms_in_root(dst: Path) -> dict:
    """根目录里三个启动器**各自**被判成什么平台 → `{平台: [文件名]}`。
        English:
    What platform each of the three root launchers is judged to be -> `{platform: [filenames]}`.
    """
    out: dict[str, list[str]] = {}
    for name in [m + '.exe' for m in LAUNCHER_MODES] + list(LAUNCHER_MODES):
        p = dst / name
        if p.is_file():
            out.setdefault(launcher_platform(p), []).append(name)
    return out


REQUIRED = [
    'main_gui.py', 'main.py', 'config.py', 'i18n.py', 'logger.py', 'requirements.txt',
    # ★ 2026-10-10：这里原来是 9 个启动脚本（`.bat` / `.sh` / `.command` 各三个）。
    #   用户要求「删掉，只留 exe」，换成了 `launchers/` 编出来的三个启动器。
    #   ⚠ 文件名**随平台变**（Windows 是 `.exe`，Linux / macOS 无后缀），所以不能
    #     在这里写死一个平台的写法 —— 那会让另一个平台的发布包永远"缺文件"。
    #     这里只列**本机**那一套；换了平台之后的完整性由 `required_launchers()` 兜。
    # [EN] ★ 2026-10-10: this used to be 9 launch scripts (three each of `.bat` / `.sh` / `.command`).
    # [EN] The user requested "delete them, keep only the exe", replaced by the three launchers produced by
    # [EN] `launchers/`.
    # [EN] ⚠ Filenames **vary by platform** (Windows has `.exe`, Linux / macOS have no suffix), so you
    # [EN] cannot
    # [EN] hardcode one platform's naming here -- that would make the other platform's release package
    # [EN] forever "missing files".
    # [EN] Only **this machine's** set is listed here; completeness after switching platforms is guarded by
    # [EN] `required_launchers()`.
    *required_launchers(host_platform()),
    'flet_setup.py', 'make_art.py', 'mcp_servers.yaml',
    'tools/platform_install.py',
    '.env', '.env.example',
    'image_gen/icon.py', 'assets/app_icon.ico', 'assets/app_icon.png',
    'assets/images/icon.ico', 'assets/images/icon.png', 'assets/fonts',
    'assets/images/manual/zh', 'assets/images/manual/en',
    # ★ 2026-10-25 加：README 顶部那段「看它跑一遍」的 GIF（`assets/images/demo/walkthrough.gif`）。
    #   README 是**随包发布**的用户文档，它引用的图缺了就是一张破图 ——
    #   而"破图"不报错、不崩，只是难看出问题，正是这份清单要挡的那一类。
    #   清单里写**目录**而不是单个文件：以后再加演示图不用改这里。
    # [EN] ★ Added 2026-10-25: the "Watch One Run" GIF at the top of the README
    # [EN] (`assets/images/demo/walkthrough.gif`). The README **ships with the package**, so a missing
    # [EN] image is a broken image -- which neither errors nor crashes, exactly what this list is for.
    # [EN] The **directory** is listed rather than the file, so adding more demo images needs no edit.
    'assets/images/demo',
    # ★ 2026-10-10 加：开始菜单八项用的**彩色图标**（8 张 + 8 张褪色版 + 出处说明）。
    #   缺了不会崩（`mk_menu_icon` 会降级成"破图"图标），所以**自检必须兜住** ——
    #   这正是"发布包里必须有的东西"要挡的那种：缺了只是"难看"，不报错。
    # [EN] ★ Added 2026-10-10: the **color icons** used by the eight Start Menu items (8 + 8 faded versions
    # [EN] + provenance note).
    # [EN] Missing them won't crash (`mk_menu_icon` degrades to a "broken image" icon), so **self-check
    # [EN] must guard it** --
    # [EN] this is exactly the kind of thing "things that must be in the release package" is meant to
    # [EN] block: missing is just "ugly", not an error.
    'assets/images/menu_icons',
    'packages', 'skills', 'prompts', 'craft', 'refs', 'samples',
    # ── 随包发布的**用户文档**（README 与说明书互相链接，缺一份就是断链）──
    # [EN] ── **User docs** shipped with the package (README and manuals link to each other; missing one is
    # [EN] a broken link) ──
    'README.md', 'README_EN.md', '使用说明.md', 'User_Manual.md',
    'Configuration_Guide.md', '配置指南.md',
    'Configuration_Classification.md', '配置分类.md',
    '剧本输出格式.md', '设定写作指导.md',
]

#: 每个平台包里该留哪几个 flet 离线运行时（`packages/` 的裁剪口径）。
#: ★★ 2026-10-11 补两条：
#:   ① `macos` 与 `macos-intel` **共用同一个** `flet-macos.tar.gz` ——
#:      它本身是**通用二进制**（`flet_setup.py` 里 `('macos','arm64')` 与
#:      `('macos','amd64')` 都映射到它），所以 Intel 那份不用另找运行时；
#:   ② `linux` 原来只列了 **amd64** 三个，把 `*-arm64` 全漏了 ——
#:      Linux ARM 用户拿到包也装不上（`flet_setup.py` 会退回联网下载，
#:      而离线包的意义正在于不联网）。现在四个发行版 × 两种架构**全带**。
# [EN] : which flet offline runtimes to keep in each platform package (the trimming rule for
# [EN] `packages/`).
# [EN] ★★ Two additions on 2026-10-11:
# [EN] ① `macos` and `macos-intel` **share** `flet-macos.tar.gz` -- it is itself a **universal
# [EN] binary** (`flet_setup.py` maps both `('macos','arm64')` and `('macos','amd64')` to it), so the
# [EN] Intel set needs no separate runtime;
# [EN] ② `linux` listed only the **amd64** ones, omitting every `*-arm64` -- Linux ARM users would be
# [EN] unable to install from the package (`flet_setup.py` would fall back to downloading over the
# [EN] network, and the whole point of an offline package is not needing the network). Now **all
# [EN] four distros × both architectures** are included.
PACKAGE_FILES = {
    'windows': ['flet-windows.zip'],
    'macos': ['flet-macos.tar.gz'],
    'macos-intel': ['flet-macos.tar.gz'],
    'linux': ['flet-linux-ubuntu20.04-amd64.tar.gz', 'flet-linux-ubuntu20.04-arm64.tar.gz',
              'flet-linux-ubuntu22.04-amd64.tar.gz', 'flet-linux-ubuntu22.04-arm64.tar.gz',
              'flet-linux-ubuntu24.04-amd64.tar.gz', 'flet-linux-ubuntu24.04-arm64.tar.gz',
              'flet-linux-debian12-amd64.tar.gz', 'flet-linux-debian12-arm64.tar.gz'],
}


class Plan:
    """记录"会跳过什么"，用于复制前预览与复制后报告。
        English:
    Record "what will be skipped", used for pre-copy preview and post-copy report.
    """

    def __init__(self) -> None:
        self.skipped: dict[str, list[str]] = {}

    def skip(self, group: str, path: str) -> None:
        self.skipped.setdefault(group, []).append(path)

    def total(self) -> int:
        return sum(len(v) for v in self.skipped.values())


def make_ignore(args, plan: Plan, src: Path):
    """构造 shutil.copytree 的 ignore 回调。
        English:
    Build the ignore callback for shutil.copytree.
    """
    dir_names: dict[str, str] = {}
    for group, names in EXCLUDE_DIR_NAMES.items():
        for n in names:
            dir_names[n] = group
    dir_paths: dict[str, str] = {}
    for group, paths in EXCLUDE_DIR_PATHS.items():
        for p in paths:
            dir_paths[p] = group
    file_globs: dict[str, str] = {}
    for group, pats in EXCLUDE_FILE_GLOBS.items():
        for p in pats:
            file_globs[p] = group

    # 服务目录内按**路径前缀**排除（2026-10-21）
    # [EN] Path-prefix exclusions inside the services directory (2026-10-21)
    svc_prefix: dict[str, str] = {}
    for group, paths in SERVICE_EXCLUDE_PREFIXES.items():
        for pp in paths:
            svc_prefix[pp] = group

    def _ignore(current: str, names: list[str]) -> set[str]:
        rel = Path(current).relative_to(src)
        drop: set[str] = set()
        for name in names:
            child = rel / name
            full = Path(current) / name
            child_posix0 = child.as_posix()
            # ★ 服务专用排除：**前缀匹配**（命中即整棵丢掉）
            #   `_ignore` 是逐层调用的，所以这里只要判"本层这一项是否以某个排除前缀开头"，
            #   子树自然不会再被遍历（等于整目录剪掉，不花 IO）。
            # [EN] ★ Service-specific exclusion: **prefix match** (a hit drops the whole subtree).
            # [EN] `_ignore` is called level by level, so testing "does this entry start with an
            # [EN] excluded prefix" is enough -- the subtree is never walked (no IO spent).
            hit_grp = None
            for pp, grp in svc_prefix.items():
                if child_posix0 == pp or child_posix0.startswith(pp + '/'):
                    hit_grp = grp
                    break
            if hit_grp:
                plan.skip(hit_grp, child_posix0)
                drop.add(name)
                continue
            # ★★★ 2026-10-21：`logo_drafts/` **只留产品运行时读的那一个**，其余是设计草稿。
            #   ⚠ 这条必须排在"按名字排除的目录"**之前**：那个分支是"整目录丢掉"，
            #     而这里要"丢掉大部分、留一个"（`_ignore` 只能整体丢目录，
            #     要留东西就必须逐个文件判断）。
            #   ⚠ 也不能靠"文件通配"：`_match()` 只比**文件名**，写 `logo_drafts/*`
            #     永远不命中（本项目已经栽过一次：拿目录名去比带斜杠的路径）。
            # [EN] ★★★ 2026-10-21: in `logo_drafts/` keep **only the file the product reads at
            # [EN] runtime**; the rest are design drafts. ⚠ This must come **before** the "exclude
            # [EN] by directory name" branch -- that branch drops the whole dir, while here we drop
            # [EN] most and keep one (`_ignore` can only drop a directory wholesale, so keeping
            # [EN] anything requires per-file decisions). ⚠ It also cannot be a file glob:
            # [EN] `_match()` compares **names only**, so `logo_drafts/*` never hits (this project
            # [EN] has already been burned once comparing a directory name against a slashed path).
            #   ⚠ **目录本身必须放行**（`startswith(LOGO_DRAFT_DIR + '/')`，不含 `==`）：
            #     第一版把 `== LOGO_DRAFT_DIR` 也写进了条件，于是目录那一层就被整棵丢掉，
            #     连要保留的 `start_logo_pre-rounded.png` 都没了 —— dry-run 只报
            #     "1 项：logo_drafts"，看着像"排除生效"，实际是**把整个目录排掉了**。
            #     这正是"数量对不上却没人细看"的典型：1 项看起来合理，实际是错的。
            # [EN] ⚠ **The directory itself must pass** (`startswith(LOGO_DRAFT_DIR + '/')`, no
            # [EN] `==`): the first version included `== LOGO_DRAFT_DIR`, so the directory level got
            # [EN] dropped wholesale, taking `start_logo_pre-rounded.png` with it -- the dry-run only
            # [EN] reported "1 item: logo_drafts", which *looks* like the exclusion working while it
            # [EN] actually removed the whole directory. A textbook "number looks plausible but is
            # [EN] wrong".
            if child_posix0.startswith(LOGO_DRAFT_DIR + '/'):
                if name in LOGO_DRAFT_KEEP:
                    continue
                plan.skip('设计草稿（产品只读 start_logo_pre-rounded.png）', child_posix0)
                drop.add(name)
                continue
            # 按名字排除的目录
            # [EN] Directories excluded by name
            if name in dir_names:
                # ⚠ **例外：服务自己的 `.env` 要留下**（复制完再脱敏，见
                #   `sanitize_service_envs`）。服务的 `.env` 里除了密钥还有端口、
                #   数据库路径、模型名 —— 整份丢掉会让服务起不来，而"清掉密钥"
                #   与"根目录 .env 重新生成"是同一套口径。
                #   `.env.env.bak` 这类备份**仍然排除**（`_match` 会命中 `.env.*`，
                #   它们是历史垃圾，没有清空的必要）。
                # [EN] ⚠ **Exception: the services' own `.env` stays** (copied, then sanitized in
                # [EN] `sanitize_service_envs`). A service `.env` carries ports, DB paths and model
                # [EN] names besides the key -- dropping it wholesale would break startup, and
                # [EN] "blank the key" is the same rule as "regenerate the root `.env`".
                # [EN] `.env.env.bak` backups are **still** excluded (`_match` hits `.env.*`; they are
                # [EN] historical junk with nothing worth sanitizing).
                if name == '.env' and child_posix0.startswith('novelservices/'):
                    continue
                plan.skip(dir_names[name], str(child))
                drop.add(name)
                continue
            # 按相对路径排除的目录
            # [EN] Directories excluded by relative path
            child_posix = child.as_posix()
            if full.is_dir() and child_posix in dir_paths:
                plan.skip(dir_paths[child_posix], str(child))
                drop.add(name)
                continue
            # 文件规则（支持简单通配）
            # [EN] File rules (supports simple globbing)
            for pat, group in file_globs.items():
                if _match(name, pat):
                    # ⚠ 同一条例外：服务自己的 `.env` 放行（复制后脱敏）
                    # [EN] ⚠ Same exception: the services' own `.env` passes (sanitized after copying)
                    if name == '.env' and child_posix0.startswith('novelservices/'):
                        break
                    plan.skip(group, str(child))
                    drop.add(name)
                    break
            else:
                if name in DEV_DOCS and not args.keep_dev_docs:
                    plan.skip('开发向文档', str(child))
                    drop.add(name)
                elif child.parent.as_posix() == 'tools':
                    if not args.keep_dev_tools and name not in TOOLS_KEEP:
                        plan.skip('开发期验证脚本', str(child))
                        drop.add(name)
                elif full.is_file() and name.endswith(('.pyc', '.pyo')):
                    plan.skip('Python 字节码缓存', str(child))
                    drop.add(name)
        return drop

    return _ignore


def _match(name: str, pattern: str) -> bool:
    """极简 glob：支持 `*` 与 `[...]`，够用即可（不想为此引 fnmatch 之外的行为差异）。
        English:
    Minimal glob: supports `*` and `[...]`, sufficient as-is (don't want to introduce behavior
    differences beyond fnmatch for this).
    """
    import fnmatch
    return fnmatch.fnmatch(name, pattern)


#: LLM 相关的键前缀 —— 发布包里这些键的**值一律留空**（键名与注释保留）。
#:
#: ★★★ 2026-10-22（用户：「把 `.env.example` 里的 API Key 以及 **LLM 配置信息**清理掉」）：
#:   要清的**不只是密钥**。本机 `.env` 里还有"我在用哪个模型、走哪个中转站、
#:   上次从句服务拉到了哪些模型名"（`MODEL_LIST_CACHE`）—— 那些不是秘密，
#:   但都是**我这一台的配置**，发给别人既没用又暴露我的用法。
#:   ⇒ 按**前缀闭集**清（`LLM_` / `MODEL_` / `EMBEDDING_`），而不是逐个点名：
#:     将来加一个新旋钮 `LLM_XXX` 时，这里自动就管住了 —— 点名型清单必然漏。
#:   ⚠ 只清**值**，不清行、不清注释：`.env` 是给人读的，删行会让用户对照官方模板时对不上。
#:   ⚠ 清空 ≠ 坏掉：`Config` 读到空值会回落到 `SPEC` 默认值（`coerce()` 那条路径），
#:     所以包里的程序照样能起来，用户填自己的 key 就能用。
# [EN] LLM-related key prefixes -- in the release package these keys' **values are always blanked**
# [EN] (names and comments kept).
# [EN] ★★★ 2026-10-22 (user: "clean the API Key **and the LLM configuration info** out of
# [EN] `.env.example`"): it is not only the secret. The local `.env` also says which model I use,
# [EN] which relay I go through, and which model names I last fetched. Not secrets, but **my machine's
# [EN] configuration** -- useless to anyone else and it exposes how I work.
# [EN] => Blank by **prefix set** (`LLM_` / `MODEL_` / `EMBEDDING_`) rather than by name: a future
# [EN] `LLM_XXX` knob is covered automatically, while a name list is guaranteed to miss.
# [EN] ⚠ Only **values** are blanked, never lines or comments (`.env` is read by humans; removing lines
# [EN] breaks comparison with the official template).
# [EN] ⚠ Blank is not broken: `Config` falls back to the `SPEC` default on an empty value, so the
# [EN] packaged program still starts and the user just fills in their own key.
LLM_KEY_PREFIXES = ('LLM_', 'MODEL_', 'EMBEDDING_')

#: 看起来像"本机路径"的片段 —— 同步过来的**值**里带这些就留空（只留键名）。
# [EN] Fragments that look like "a local path" -- a synced **value** containing one is blanked
# [EN] (the key name is kept).
_LOCAL_PATH_MARKS = ('C:\\', 'C:/', '/Users/', '/home/', '\\\\', '~/')


def _looks_secret_value(v: str) -> bool:
    """这个值**长得像不像密钥**（不靠键名判断）。

    ★ 为什么需要"看值"而不是"看键名"（用户 2026-10-22：「环境文件里 APIKey 需要清理掉」）：
      同步那一步会把本机 `.env` 里**没登记进 `SPEC` 的键连同值**抄进发布包。
      只按键名筛（`*_KEY` / `*_TOKEN` …）会漏掉两种常见写法：
        · `MY_RELAY=https://xxx/v1?key=sk-…`（密钥藏在 URL 里）
        · `SOMETHING_CRED=eyJhbGciOi…`（JWT，名字里没有任何收尾词）
      这两种一旦抄进去，就是**把用户自己的 key 发给别人**，而自检的 `sk-…` 形态判据
      对第二种也无效（它不是 `sk-` 开头）。
    ★ 判据是"形态"，不看它在哪个键下 —— 与 `_looks_placeholder` 同一套思路：
      够长（≥20）+ 高熵（含大小写/数字/符号多样）⇒ 当成密钥，宁可多清一个。
    ⚠ 误报代价是"某个键的值被留空"（用户自己填一遍），漏报代价是"真密钥外发"。
      两者不对称，所以这里**故意偏保守**。
    [EN] Does this value **look like a secret**, regardless of its key name?
    [EN] ★ Why look at the value (user, 2026-10-22: "the API key in the env file must be cleaned
    [EN] out"): the sync step copies **unregistered** keys **with their values** from the local `.env`
    [EN] into the release. Filtering by key name misses two common shapes: a key hidden inside a URL
    [EN] (`MY_RELAY=https://...?key=sk-...`) and a JWT under a name with no credential suffix
    [EN] (`SOMETHING_CRED=eyJhbGciOi...`). Either one means **sending the user's own key to a
    [EN] stranger**, and the `sk-...` shape check misses the second entirely.
    [EN] ★ The test is about **shape**, not the key it sits under -- same idea as
    [EN] `_looks_placeholder`: long (>=20) + high entropy => treat as a secret. Over-blanking costs the
    [EN] user one re-entry; under-blanking costs a leaked key. The two are not symmetric, so this
    [EN] deliberately errs on the safe side.
    """
    s = v.strip().strip('"\'')
    if len(s) < 20:
        return False
    classes = sum(bool(re.search(p, s)) for p in
                  (r'[a-z]', r'[A-Z]', r'[0-9]', r'[^A-Za-z0-9]'))
    # 纯路径 / 纯 URL 没有密钥嫌疑（但带 `key=` / `token=` 查询串的会被下面的类判断抓住）
    return classes >= 3 and len(set(s)) >= 10

#: 兜底清扫：**按目录名**整棵删（出现在任意深度都删）。
#: ★ 与 `EXCLUDE_DIR_NAMES` 是**两套**，别合并：那张表管"复制前不拷"，
#:   这张表管"复制后兜底"。两边故意重叠一部分 —— 排除表漏一条时，这里还能兜住。
#: ⚠ `.workbuddy`（开发内幕）、`.ui_state`（本机界面状态）必须在这张表里：
#:   它们不报错、不影响运行，只有"看包里到底有什么"才发现得了。
# [EN] Fallback sweep: remove **by directory name** wholesale (at any depth).
# [EN] ★ Deliberately a **second** list, not merged with `EXCLUDE_DIR_NAMES`: that one governs "don't
# [EN] copy", this one "clean up afterwards". The overlap is intentional -- if the exclusion table
# [EN] misses an entry, this still catches it.
# [EN] ⚠ `.workbuddy` (inside information) and `.ui_state` (machine UI state) must be here: they raise
# [EN] nothing and break nothing, so only "look at what is actually in the package" finds them.
JUNK_DIR_NAMES = (
    'logs', '__pycache__', '.venv', 'venv', '.git', '.idea', '.vscode',
    '.ui_state', '.workbuddy', 'exports',
)
#: 兜底清扫：**按文件名通配**删。
#: ⚠ `*.bak*` / `*.old*` 用**前缀**而不是结尾：备份名几乎都是"原名 + 标记 + 时间/原因"
#:   （`llm_models.json.bak-before-临时指向` 就是这么漏过 `*.bak` 的，里面还有真 API Key）。
# [EN] Fallback sweep: remove by **filename glob**.
# [EN] ⚠ `*.bak*` / `*.old*` are **prefixes**, not suffixes: backup names are "original + marker +
# [EN] time/reason" (`llm_models.json.bak-before-...` slipped past `*.bak` and held a real API key).
JUNK_FILE_GLOBS = (
    '*.log', '*.pyc', '*.pyo', '*.old*', '*.bak*', '*.orig', '*.rej',
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
    'usage.db', 'usage.db-journal', 'llm_cache.db', 'llm_cache.db-journal',
    'llm_models.json', '.nws_messages.jsonl', '.bilingual_done.json',
    '.install_manifest.json',
)


def write_clean_env(dst: Path) -> tuple[Path, Path]:
    """在发布目录里**重新生成** `.env` 与 `.env.example`（全键 + 默认值 + 密钥留空）。

    直接用工程的 `config.Config.write_example()`，不自己拼模板 ——
    这样键名、默认值、密钥留空规则都跟程序保持一致，加新配置项时也不用改本脚本。
    `write_example()` 已把 `secret=True` 的键写成空值（当前只有 `LLM_API_KEY`）。

        English:
    **Regenerate** `.env` and `.env.example` in the release directory (all keys + default values +
    secrets left empty).
        Directly use the project's `config.Config.write_example()`, don't hand-roll the template --
        this way key names, default values, and the empty-secret rule all stay consistent with the
        program, and adding new config items won't require changing this script.
        `write_example()` already writes keys with `secret=True` as empty values (currently only
        `LLM_API_KEY`).
    """
    sys.path.insert(0, str(APP_DIR))
    import config  # noqa: E402  （顶层只用标准库，所以任意 python 都能跑）
    # [EN] noqa: E402 (top level uses only stdlib, so any python can run it)

    example = dst / '.env.example'
    cfg = config.Config({})
    cfg.write_example(example)
    text = example.read_text(encoding='utf-8')
    # `.env` 用同一份内容：全键都在，用户一上手就能看到可调的旋钮
    # [EN] `.env` uses the same content: all keys present, so users can immediately see the tunable knobs
    (dst / '.env').write_text(text, encoding='utf-8')
    return example, dst / '.env'


def parse_env_pairs(text: str) -> list[tuple[str, str]]:
    """把 `.env` 文本解析成 `[(键, 值)]`（注释与空行丢掉，顺序保留）。
        English:
    Parse `.env` text into `[(key, value)]` (comments and blank lines dropped, order preserved).
    """
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$', s)
        if m:
            out.append((m.group(1), m.group(2).strip().strip('"\'')))
    return out


def sync_env_keys(src_env: Path, example: Path, env: Path) -> tuple[list[str], list[str]]:
    """把**本机 `.env` 里有、生成的样例里没有**的键补进包里的 `.env` 与 `.env.example`。

    ★ 这一步要抓的是什么（用户原话：「看下 `.env` 里是不是有 `.env.example` 里没有的东西，
      如果是则同步过去」）：`SPEC` 是配置项的**登记处**，样例由它生成。
      所以"本机 `.env` 有、样例没有"只有一种成因 —— **有人手工加了一个键，没登记进 `SPEC`**
      （实测：当前 `SPEC` 352 项、本机 `.env` 351 项、样例 262 项；样例那份已经落后了一大截，
      正是因为它是很久以前生成的）。
      这种键在程序里多半是"没人读的死配置"，但**不能假装它不存在**：它可能被某个服务读、
      也可能下一版就接进程序。让它出现在样例里，下一个人才看得见。
    ★ 值怎么处理：**带本机路径的值留空**（`C:\\Users\\chao`、`/home/…` 这类），
      看起来像凭据的键（`*_KEY` / `*_TOKEN` / `*_SECRET` / `*_PASSWORD` …）也留空。
      其余照抄 —— 一个"值被清空"的键在样例里等于没写，用户仍然不知道该填什么。

    返回 `(补上的键, 值被留空的键)`。
        English:
    Copy keys that exist in **the local `.env` but not in the generated example** into the packaged
    `.env` / `.env.example`.
    ★ What this catches (user's words: "check whether `.env` has something `.env.example` does not; if
      so, sync it over"): `SPEC` is the **registry** of config keys and the example is generated from
      it, so "local `.env` has it, example does not" has exactly one cause -- **someone added a key by
      hand without registering it in `SPEC`** (measured today: `SPEC` 352, local `.env` 351, example
      262 -- the checked-in example had fallen far behind).
      Such a key is usually dead config, but **it must not be pretended away**: a service may read it,
      or the next version may wire it in. Making it visible in the example is what lets the next person
      see it.
    ★ Values: **a value carrying a local path is blanked** (`C:\\Users\\chao`, `/home/...`), as is a
      credential-looking key (`*_KEY` / `*_TOKEN` / `*_SECRET` / `*_PASSWORD` ...). Everything else is
      copied -- a key with an emptied value tells the user nothing about what to put there.
    Returns `(keys added, keys whose value was blanked)`.
    """
    added: list[str] = []
    blanked: list[str] = []
    if not src_env.is_file():
        return added, blanked
    have = {k for k, _ in parse_env_pairs(example.read_text(encoding='utf-8'))}
    src_pairs = parse_env_pairs(src_env.read_text(encoding='utf-8'))
    missing = [(k, v) for k, v in src_pairs if k not in have]
    if not missing:
        return added, blanked
    tails = ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'PASSWD', 'CREDENTIAL')
    header = ['', '# ── 本机 .env 里有、SPEC 未登记的键（发布时同步过来，请自行确认含义）──']
    lines: list[str] = []
    for k, v in missing:
        # ★ 三个留空条件（任一命中）：键名像凭据 / 值带本机路径 / **值长得像密钥**。
        #   第三条是 2026-10-22 补的（用户：「环境文件里 APIKey 需要清理掉」）：
        #   同步是**唯一**能把本机真值带进发布包的通路，只看键名会漏掉
        #   "密钥藏在 URL 里"与"JWT 挂在没有收尾词的名字下"这两种。
        # [EN] ★ Three blanking conditions (any hit): credential-looking name / value carrying a local
        # [EN] path / **value shaped like a secret**. The third was added 2026-10-22 (user: "the API key
        # [EN] in the env file must be cleaned out"): sync is the **only** channel that can carry a real
        # [EN] local value into the release, and name-only filtering misses "key hidden in a URL" and
        # [EN] "JWT under a name with no credential suffix".
        if (any(k.upper().endswith(t) for t in tails)
                or any(m in v for m in _LOCAL_PATH_MARKS)
                or _looks_secret_value(v)):
            v = ''
            blanked.append(k)
        lines.append(f'{k}={v}')
        added.append(k)
    block = '\n'.join(header + lines) + '\n'
    for p in (example, env):
        text = p.read_text(encoding='utf-8')
        p.write_text(text.rstrip('\n') + '\n' + block, encoding='utf-8')
    return added, blanked


def scrub_llm_env(path: Path) -> list[str]:
    """把 <path> 里 `LLM_*` / `MODEL_*` / `EMBEDDING_*` 的**值**清空（键名与注释保留）。

    返回被清空的键名（供报告里说"清了几个"，不打印值）。
        English:
    Blank the **values** of `LLM_*` / `MODEL_*` / `EMBEDDING_*` in <path> (keys and comments kept).
    Returns the blanked key names (so the report can say "blanked N", without printing values).
    """
    done: list[str] = []
    if not path.is_file():
        return done
    out: list[str] = []
    for line in path.read_text(encoding='utf-8').split('\n'):
        s = line.strip()
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$', s)
        if m and m.group(1).upper().startswith(LLM_KEY_PREFIXES):
            if m.group(2).strip():
                done.append(m.group(1))
            out.append(f'{m.group(1)}=')
            continue
        out.append(line)
    if done:
        path.write_text('\n'.join(out), encoding='utf-8')
    return done


def clean_junk(dst: Path) -> dict[str, list[str]]:
    """兜底清扫：日志 / 缓存 / 台账 / 开发目录 / 本机状态 / 旧备份，**再扫一遍删干净**。

    ★ 为什么排除表之外还要有这一道：排除表是"按名字/路径/通配"三张闭集，
      只能拦住它**想得起来**的东西。而"多了什么从不报错"是本项目反复栽的坑
      （`*.old-*`、`.workbuddy`、`generated-images` 三次都是**每一版都在包里**，
      靠人去看才发现）。这一道不看名字表，**把整棵树扫一遍**，按类删、按类报数。
    ★ 顺序：先删文件再删目录（`os.walk(topdown=False)` 从深到浅），
      否则删掉目录后里面的文件就统计不到、也删不了。
    ★ 绝不碰 `packages/`、`assets/`、`skills/` 这些**功能目录**：这里只认
      上面两张表里的名字，不按"看着像垃圾"判断。

    返回 `{类别: [删掉的相对路径…]}`（报告里按类计数）。
        English:
    Fallback sweep: logs / caches / ledgers / dev dirs / machine state / old backups -- scan once more
    and delete.
    ★ Why this exists on top of the exclusion tables: those are three closed sets (name / path / glob)
      and only stop what they **remember**. "Something extra never errors" is this project's recurring
      trap (`*.old-*`, `.workbuddy`, `generated-images` were each present in **every** release and were
      found only by a human looking). This pass ignores the name tables, **walks the whole tree**, and
      deletes by class while reporting counts.
    ★ Order: files first, then directories (`os.walk(topdown=False)`, deepest first), otherwise files
      inside a removed directory are neither counted nor deleted.
    ★ Never touches functional dirs (`packages/`, `assets/`, `skills/`): only the two tables above are
      consulted, never "this looks like junk".
    Returns `{category: [deleted relative paths ...]}`.
    """
    import fnmatch
    import os

    done: dict[str, list[str]] = {}

    def _mark(cat: str, p: Path) -> None:
        done.setdefault(cat, []).append(str(p.relative_to(dst)))

    for cur, dirs, files in os.walk(dst, topdown=False):
        base = Path(cur)
        for name in files:
            p = base / name
            for pat in JUNK_FILE_GLOBS:
                if fnmatch.fnmatch(name, pat):
                    cat = ('残留日志' if name.endswith('.log') else
                           '残留数据库' if name.endswith(('.db', '.db-journal')) else
                           '旧备份 / 开发期产物')
                    try:
                        p.unlink()
                        _mark(cat, p)
                    except OSError:
                        pass
                    break
            else:
                # `.env.*` 备份（`env.example` 之外的）
                if name.startswith('.env.') and name != '.env.example':
                    try:
                        p.unlink()
                        _mark('残留配置备份', p)
                    except OSError:
                        pass
        for name in dirs:
            if name in JUNK_DIR_NAMES:
                p = base / name
                try:
                    shutil.rmtree(p)
                    _mark('运行期目录 / 开发目录', p)
                except OSError:
                    pass
    return done


#: 服务 `.env` 里哪些键算"密钥"，复制发布包时**必须清空**。
#:
#: ★ 为什么是一张**闭集**而不是"名字里带 KEY 就算"：
#:   `*_KEY` 这种猜测在别处吃过亏 —— `KEY` 也可能是普通字段
#:   （比如某个 `SORT_KEY`），而真密钥不一定带 KEY 字样（`TOKEN` / `SECRET` / `PASSWORD`）。
#:   宁可逐条列，也不要一个看起来聪明、实际漏报的规则。
#:   ⚠ 新加服务/新加密钥字段时**必须回来补一条** —— 这里的漏项会被
#:     `scan_release` 的"疑似密钥字面量 `sk-…`"兜住（那是最硬的一道）。
# [EN] Which keys in a service `.env` count as secrets and **must be blanked** in the release.
# [EN] ★ Why a **closed list** instead of "anything with KEY in the name": that guess has burned
# [EN]   us -- `KEY` can be an ordinary field (e.g. `SORT_KEY`), and a real secret need not contain
# [EN]   KEY at all (`TOKEN`, `SECRET`, `PASSWORD`). Better an explicit list than a clever rule that
# [EN]   misses hits. ⚠ When adding a service or a secret field, **add a line here** -- misses are
# [EN]   caught by `scan_release`'s "suspected secret literal `sk-...`" (the hardest gate).
SERVICE_SECRET_KEYS = (
    'OPENAI_API_KEY', 'LLM_API_KEY', 'API_KEY', 'DEEPSEEK_API_KEY',
    'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'QWEN_API_KEY', 'MOONSHOT_API_KEY',
    'AZURE_OPENAI_API_KEY', 'SILICONFLOW_API_KEY', 'ZHIPU_API_KEY',
    'OPENAI_TOKEN', 'HF_TOKEN', 'ACCESS_TOKEN', 'AUTH_TOKEN', 'BEARER_TOKEN',
    'SECRET_KEY', 'JWT_SECRET', 'CLIENT_SECRET', 'PASSWORD', 'DB_PASSWORD',
)


def sanitize_service_envs(dst: Path, log: list[str]) -> list[str]:
    """把**服务目录里**每个 `.env` 的密钥字段清空（其余配置原样保留）。

    ★ 为什么是"清空"而不是"整份不发"（2026-10-21 用户点名改的）：
      服务的 `.env` 除了密钥，还有端口、数据库路径、模型名、超时 ——
      整份丢掉会让服务起不来（而用户看到的是"外部服务坏了"，不是"没配置"）。
      "清空密钥、保留旋钮"与根目录 `.env` 的做法是**同一套口径**：
      那边是重新生成（全键 + 默认值 + `secret` 留空），这边是原地清空。
      两处都表达同一句话：**发出去的包里没有任何真密钥**。

    ★ 怎么清：只改**值**，不动键名、不动注释、不动行序。
      `.env` 是给人读的、也会被程序按行解析；重排或删行会让用户下次对照
      官方模板时对不上，也会让 `service_ctl` 的读取逻辑遇到缺键。

    ⚠ 三个必须守住的细节：
      ① **只认行首的 `KEY=`**（允许前置空格），不碰注释里提到的键名；
      ② 值外面可能带引号（`KEY="sk-..."`），整段替换成空，不留残渣；
      ③ 清完**不许抛**：某个 `.env` 是只读/被占用时只记一条问题，
        不能让整个打包失败（失败一次要重跑几分钟的复制）。

    返回问题列表（空 = 全部干净）。

        English:
    Blank the secret fields in **every service `.env`** (all other settings preserved).
    ★ Why "blank" rather than "don't ship the file" (changed on the user's request 2026-10-21): a
      service `.env` carries ports, DB paths, model names and timeouts besides the key -- dropping it
      wholesale breaks startup (and the user sees "the external service is broken", not "it is
      unconfigured"). "Blank the secret, keep the knobs" is the **same rule** as the root `.env`
      (that one is regenerated: all keys + defaults + `secret` empty). Both say one thing: **no real
      secret leaves in the package**.
    ★ How: change only the **values**; leave key names, comments and line order alone. `.env` is read
      by both humans and the program; reordering or dropping lines breaks later comparison with the
      official template and leaves `service_ctl`'s reader with missing keys.
    ⚠ Three details that must hold: ① only match **`KEY=` at line start** (leading spaces allowed),
      never a key name mentioned in a comment; ② values may be quoted (`KEY="sk-..."`), replace the
      whole value so no residue remains; ③ **must not raise** -- a read-only/locked `.env` produces
      one problem entry, never a failed packaging run.
    Returns a problem list (empty = all clean).
    """
    problems: list[str] = []
    root = dst / 'novelservices'
    if not root.is_dir():
        return problems
    secrets = {k.upper() for k in SERVICE_SECRET_KEYS}

    def _is_secret_key(name: str) -> bool:
        """这个键名要不要清空 = **精确命中闭集** 或 **以某个密钥后缀结尾**。

        ★★★ 为什么必须加"后缀"这一半（发布 0.3.2 时自检当场抓到）：
          PenShot 用的是**自己那套带前缀的命名**：
              PENSHOT_LLM__DEFAULT__API_KEY=sk-tp-<你的key>
              PENSHOT_EMBED__DEFAULT__API_KEY=sk-tp-...
          闭集里只有 `API_KEY`，**精确匹配一个都不中** ⇒ 两个真 key 原封不动
          进了发布包，而脱敏函数还乐呵呵地报"没问题"。
          这不是"少列了一条"，是**判据的形态错了**：不同服务有各自的命名前缀，
          而**后缀是稳定的**（都以 `API_KEY` / `TOKEN` / `SECRET` / `PASSWORD` 收尾）。

        ★ 为什么后缀写这么具体、而不是"名字里含 KEY"：
          `SORT_KEY` / `CACHE_KEY` / `PRIMARY_KEY` 都含 KEY 但**不是密钥**。
          只认那四个**收尾词** —— 它们本身就是"这是个凭据"的约定，
          而不含 KEY 的真密钥（`..._TOKEN` / `..._SECRET`）也一并覆盖到。

        ⚠ 后缀匹配一律**大写化后**比较：`.env` 的键名大小写不敏感。
        [EN] Whether to blank this key = **exact hit in the closed list** or **ends with a secret
        [EN] suffix**.
        [EN] ★★★ Why the suffix half is mandatory (the 0.3.2 self-check caught it immediately):
        [EN] PenShot uses its **own prefixed naming** (`PENSHOT_LLM__DEFAULT__API_KEY=sk-tp-...`), the
        [EN] closed list only had `API_KEY`, and **exact matching hit nothing** => two real keys went
        [EN] into the package untouched while the scrubber happily reported "clean".
        [EN] That is not "one entry missing", it is **the wrong shape of criterion**: services have
        [EN] their own prefixes, while the **suffix is stable** (`API_KEY` / `TOKEN` / `SECRET` /
        [EN] `PASSWORD`).
        [EN] ★ Why the suffixes are this specific rather than "contains KEY": `SORT_KEY` /
        [EN] `CACHE_KEY` / `PRIMARY_KEY` contain KEY but are **not secrets**. Only those four endings,
        [EN] which are themselves the convention "this is a credential" -- and real secrets without KEY
        [EN] (`..._TOKEN` / `..._SECRET`) are covered too.
        [EN] ⚠ Compare **upper-cased**: `.env` key names are case-insensitive.
        """
        up = str(name or '').upper()
        if up in secrets:
            return True
        # ★ 2026-10-21：`SECRET_KEY` 必须在列表里（发布 0.3.2 时**漏了**）。
        #   MuMu 的 `backend/.env` 里有 `SESSION_SECRET_KEY=b76df0ef93…`（64 位十六进制）——
        #   那是会话签名密钥，泄漏就等于"别人能伪造登录状态"。
        #   它**不以 `SECRET` 结尾**（以 `KEY` 结尾），所以老的后缀表一个都不中，
        #   而自检也没报（它不是 `sk-` 开头、也不是打包机那个 `LLM_API_KEY`）。
        #   ⇒ 顺序很重要：**长的写在前面**（`SECRET_KEY` 先于 `SECRET`），
        #     否则 `endswith('SECRET')` 永远轮不到 `..._SECRET_KEY`（它确实轮不到，
        #     但把长的放前面能让"这条为什么在这"一眼看懂）。
        # [EN] ★ 2026-10-21: `SECRET_KEY` must be in the list (it was **missed** when publishing
        # [EN] 0.3.2). MuMu's `backend/.env` has `SESSION_SECRET_KEY=b76df0ef93...` (64 hex chars) --
        # [EN] a session signing key; leaking it means "someone can forge a logged-in state".
        # [EN] It does **not** end with `SECRET` (it ends with `KEY`), so the old suffix table missed
        # [EN] it entirely, and the self-check stayed quiet (not `sk-`-prefixed, not the build
        # [EN] machine's `LLM_API_KEY`). => Order matters: **longer first** (`SECRET_KEY` before
        # [EN] `SECRET`) so a reader can see why each entry is there.
        return any(up.endswith(s) for s in (
            'SECRET_KEY', 'PRIVATE_KEY', 'API_KEY', 'TOKEN', 'SECRET', 'PASSWORD'))


    touched: list[str] = []
    for env in sorted(root.rglob('.env')):
        if not env.is_file():
            continue
        rel = env.relative_to(dst).as_posix()
        try:
            text = env.read_text(encoding='utf-8')
        except Exception as e:                                   # noqa: BLE001
            problems.append(f'{rel} 读不出来，无法确认里面有没有密钥：{e!r}')
            continue
        out: list[str] = []
        blanked: list[str] = []
        for line in text.splitlines():
            m = re.match(r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$', line)
            if m and _is_secret_key(m.group(2)):
                val = m.group(3).strip()
                if val:                        # 本来就是空的就不算"清掉了一条"
                    blanked.append(m.group(2))
                out.append(f'{m.group(1)}{m.group(2)}=')
            else:
                out.append(line)
        if blanked:
            try:
                # ⚠ 用 `chr(10)` 而不是某个 `NL` 常量：本脚本里**没有** `NL`。
                #   第一版就是在补丁脚本里借用了那个变量名，于是脱敏每次都抛
                #   `NameError: name 'NL' is not defined` —— 而它被 try 吞掉、
                #   只报成"写不回去"，看起来像文件被占用。
                # [EN] Use `chr(10)`, not some `NL` constant: this script **has no `NL`**.
                # [EN] The first version borrowed that name from the patch script, so scrubbing
                # [EN] always raised `NameError`, and the `try` swallowed it into a
                # [EN] "cannot write back" message that looks like a locked file.
                env.write_text(chr(10).join(out) + chr(10), encoding='utf-8')
                touched.append(f'{rel}（清空 {len(blanked)} 项：{"、".join(blanked)}）')
            except Exception as e:                               # noqa: BLE001
                problems.append(f'{rel} 写不回去，密钥仍在包里：{e!r}')
    if touched:
        log.append(f'服务配置脱敏 {len(touched)} 份：')
        log.extend(f'    · {x}' for x in touched)
    return problems


#: 包内平台说明的文件名（中英各一份，README 顶上也会插一行横幅指向它）。
# [EN] : filename of the in-package platform note (one Chinese, one English; a banner at the top of
# [EN] the README also points to it).
NOTE_NAME = '平台说明.md'
NOTE_NAME_EN = 'PLATFORM.txt'
#: README 顶部横幅的锚点 —— 插在**第一行大标题之后**，别插到正文中间。
# [EN] : anchor for the README top banner -- inserted **after the first-level heading**, not into the
# [EN] middle of the body.
_BANNER_ANCHOR = '\n\n'


def _source_version() -> str:
    """源码工程当前的 `config.VERSION`（读不到返回 `''`）。

    ★ 只**读那一段文本**，不 `import config`：`config` 会连带 import 一堆东西、
      还可能建目录；打包脚本不该被产品的副作用拖住。
    ★ 返回 `''` 而不是编一个默认版本：调用方据此**整句省掉版本号**，
      宁可少一句指引，也不写一个不存在的包名（2026-10-22 的 `0.3.0-macos-intel` 就是这么坑人的）。
    [EN] The source tree's current `config.VERSION` (`''` when unreadable). Read just that text --
    [EN] never `import config` (side effects). Returning `''` (not a made-up default) lets callers
    [EN] drop the version from the sentence entirely, which beats naming a package that doesn't exist.
    """
    try:
        for line in (APP_DIR / 'config.py').read_text(encoding='utf-8').split('\n')[:40]:
            if line.startswith('VERSION'):
                return line.split('=', 1)[1].strip().strip('\'"')
    except OSError:
        pass
    return ''


def write_release_note(dst: Path, version: str, host: str, staged: dict[str, str]) -> Path:
    """在包根目录写 `平台说明.md`（+ `PLATFORM.txt`），并往 README 顶上插一行横幅。

    ★★ 为什么还要这份说明（"不再区分平台"之后它变了用途，但**更需要**了）：
      包是**一个**了，可根目录那三个启动器只能是**一个平台**的二进制 ——
      换到别的系统上双击**不会有任何反应**。不讲清楚，Mac 用户会以为包坏了；
      讲了，他知道去 `启动器/其他平台/macos/` 把三个文件拷过来。
      旧版是"四个包各写各的平台"，新版是"一个包写清楚四个平台各自的落点"。

    ★ 说到的路径必须真实存在：`staged` 是**实际复制成功**的落点（`stage_launcher_sets` 的返回值），
      不是"按理应该有"的清单。漏一套时这里就不会写它
      —— 说明书里出现一个空目录，比不写更糟。

        English:
    Write `平台说明.md` (+ `PLATFORM.txt`) at the package root, and inject a banner at the top of the
    README.
    ★★ Why the note is still needed (its purpose changed with "stop splitting by platform" -- and it
      became **more** important): the package is **one**, but the three root launchers can only be
      **one platform's** binaries -- double-clicking them on another OS does **nothing**. Without the
      note a Mac user thinks the package is broken; with it, they know to copy the three files from
      `启动器/其他平台/macos/`.
      The old flow wrote one platform per package; the new one writes all four platforms' homes.
    ★ Every path named here must really exist: `staged` is what was **actually copied**
      (`stage_launcher_sets`' return value), not a wish list. A missing set is simply not mentioned --
      naming an empty directory in the manual is worse than omitting it.
    """
    ver = version or _source_version()
    rows = []
    for key in LAUNCHER_SETS:
        where = staged.get(key)
        if not where:
            continue
        rows.append(f'| {PLATFORM_LABEL.get(key, key)} | `{where}` | '
                    f'`{"` / `".join(required_launchers(key))}` |')
    table = '\n'.join(rows)
    host_label = PLATFORM_LABEL.get(host, host)
    host_names = ' / '.join(f'`{n}`' for n in required_launchers(host))
    other = [k for k in LAUNCHER_SETS if k != host and staged.get(k)]

    note_zh = f"""# 平台说明 · 小说世界AI模拟 {ver}

**这一个包**里带了**四个平台**的启动器 —— 不用再挑平台包，也不用再找"另一个架构的那个包"。

| 平台 | 启动器在包里的位置 | 文件名 |
|---|---|---|
{table}

## 怎么用

**{host_label}**（就是根目录那三个）：{host_names}

- 安装：双击 `setup`；启动：双击 `start`；卸载：双击 `uninstall`。
- 首次启动会自动建 venv 并装依赖（离线运行时就在 `packages/` 里，不联网也能起来）。

"""
    if other:
        note_zh += (
            '**其他平台**（根目录那三个在你们系统上双击**不会有任何反应** —— 不是坏了，是二进制不对）：\n\n'
            + '\n'.join(
                f'{i}. `{PLATFORM_LABEL.get(k, k)}`：把 '
                f'`{LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/{k}/` 里的三个文件'
                f'（`{"` / `".join(required_launchers(k))}`）**拷到包根目录**，'
                f'然后再按上面的"怎么用"操作。'
                for i, k in enumerate(other, 1))
            + '\n\n> ⚠ macOS 首次运行若被 Gatekeeper 拦下：**右键 → 打开**，'
              '或执行 `xattr -dr com.apple.quarantine "<解压出来的目录>"`。\n\n')
    note_zh += f"""## 这个包里有什么

| 项 | 说明 |
|---|---|
| 启动器 | 根目录是 **{host_label}** 那一套；其余平台在 `{LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/` |
| `packages/` | 四个平台的 flet 离线运行时**都在** —— 首次启动不联网也能跑 |
| `.env` / `.env.example` | 已生成好，**模型与密钥都是空的**；要接模型就填 `LLM_API_KEY`（见 `配置指南.md` 第 1 节） |
| `README.md` / `使用说明.md` | 通用说明（讲的是三个系统各自怎么启动，可与本文件对照看） |

## 发布是怎么做的（给维护者）

```bash
python tools/make_release.py            # → 发布版本/{ver or 'X.Y.Z'}/
python tools/make_release.py --dry-run  # 只看计划
```

版本号只有 `config.py` 的 `VERSION` 一个来源；一个版本**一个文件夹**，四个平台全带。

English:
# Platform note · Novel World AI Simulator {ver}

**This single package** carries launchers for all **four platforms** -- no per-platform package to pick.

| Platform | Where the launchers are | Filenames |
|---|---|---|
{table}

## How to use

**{host_label}** (the three in the root): {host_names}

- Install: double-click `setup`; start: `start`; uninstall: `uninstall`.
- The first launch creates a venv and installs dependencies (offline runtimes are in `packages/`).

"""
    if other:
        note_zh += (
            '**Other platforms** (the root three do **nothing** on your system -- wrong binary, not a '
            'fault):\n\n'
            + '\n'.join(f'{i}. {PLATFORM_LABEL.get(k, k)}: copy the three files in '
                        f'`{LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/{k}/` **into the package root**, '
                        f'then follow the steps above.'
                        for i, k in enumerate(other, 1))
            + '\n\n> ⚠ macOS Gatekeeper blocking the first launch: **right-click -> Open**, or run '
              '`xattr -dr com.apple.quarantine "<extracted folder>"`.\n\n')
    note_zh += """## What's inside

| Item | Notes |
|---|---|
| Launchers | root = the build host's set; other platforms under `启动器/其他平台/` |
| `packages/` | flet offline runtimes for **all four** platforms |
| `.env` / `.env.example` | pre-generated, **models and keys empty**; fill `LLM_API_KEY` to connect a model |
| `README.md` / `User_Manual.md` | general docs (per-OS launch steps; read alongside this file) |
"""
    note = dst / NOTE_NAME
    note.write_text(note_zh, encoding='utf-8')
    (dst / NOTE_NAME_EN).write_text(
        f'Novel World AI Simulator {ver} -- one package, four platforms.\n'
        f'Root launchers: {host_label}.\n'
        f'Other platforms: see {LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/ and read {NOTE_NAME}.\n',
        encoding='utf-8')

    # ── 往 README 顶上插一行横幅（中英各一份）──
    #   ⚠ 只插一次：判据是"头几行里有没有已经出现过本文件名"，避免重复打包时越插越多。
    # [EN] ── Inject a banner at the top of the README (one Chinese, one English) ──
    # [EN] ⚠ Insert only once: the check is "has this filename already appeared within the first few
    # [EN] lines", so repeated packaging doesn't stack banners.
    banner_zh = (f'> ⚠ **一个包，四个平台** —— 根目录那三个启动器是 **{host_label}** 的；'
                 f'其他平台怎么用见 [`{NOTE_NAME}`]({NOTE_NAME})。\n\n')
    banner_en = (f'> ⚠ **One package, four platforms** -- the three root launchers are for '
                 f'{host_label}; see [`{NOTE_NAME_EN}`]({NOTE_NAME_EN}).\n\n')
    for fname, banner, probe in (('README.md', banner_zh, NOTE_NAME),
                                 ('README_EN.md', banner_en, NOTE_NAME_EN)):
        p = dst / fname
        if not p.is_file():
            continue
        text = p.read_text(encoding='utf-8')
        if probe in '\n'.join(text.split('\n')[:6]):
            continue
        lines = text.split('\n')
        # 插在**第一个标题行之后**
        # [EN] Insert after the **first heading line**
        at = 0
        for i, ln in enumerate(lines):
            if ln.startswith('#'):
                at = i
                break
        lines.insert(at + 1, '\n' + banner.rstrip('\n'))
        p.write_text('\n'.join(lines), encoding='utf-8')
    return note


def scan_release(dst: Path, secret_value: str) -> list[str]:
    """发布前自检。返回问题列表（空 = 干净）。

    ★ 最硬的一条是**拿真实密钥去全文搜** —— 不是只看 `.env` 里那行。
      密钥可能被粘到别处（文档、示例、某个调试脚本），只有全文搜才拦得住。

        English:
    Pre-release self-check. Returns a list of issues (empty = clean).
        ★ The strictest one is **searching the full text with the real secret** -- not just looking at
        the line in `.env`. The secret may have been pasted elsewhere (docs, examples, some debug
        script); only a full-text search can catch that.
    """
    problems: list[str] = []

    # 1) 真实密钥不得出现在发布包任何文本文件里
    # [EN] 1) Real secrets must not appear in any text file in the release package
    if secret_value:
        hits = _grep_text_files(dst, secret_value)
        if hits:
            problems.append(f'★ 发布包里出现了真实 API Key：{hits[:3]}')

    # 2) 常见的密钥字面量形态
    # [EN] 2) Common secret literal patterns
    #
    # ★★★ 2026-10-21 修（发布 0.3.2 时这条**误报**了）：原来的正则
    #   `\bsk-[A-Za-z0-9_\-]{16,}` 会把**占位符**也算成密钥 ——
    #   `novelservices/PenShot/README.md` 里写着 `sk-xxxxxxxxxxxxxxxxxxxxxxxx`（示例），
    #   于是每次打包都报"疑似密钥"，而那是文档里教用户"把这里换成你的 key"。
    #   ⇒ 加一条**占位符判据**：`sk-` 后面**全是同一个字符**（x / * / 0 / 9 …），
    #     或长度不足、或含 `your`/`xxx` 之类的字样，就不算密钥。
    #   ⚠ 这个放宽**必须是"形态判据"而不是"文件名白名单"**：
    #     白名单（"README 不查"）会让真 key 被粘进 README 时**直接漏过去**。
    # [EN] ★★★ Fixed 2026-10-21 (this **false-positived** while publishing 0.3.2): the old regex
    # [EN] counted **placeholders** as secrets -- `novelservices/PenShot/README.md` contains
    # [EN] `sk-xxxxxxxxxxxxxxxxxxxxxxxx` (an example) and every build reported "suspected secret",
    # [EN] when that line teaches users "put your key here".
    # [EN] => Add a **placeholder test** (one repeated character / too few distinct chars / contains
    # [EN] `your`/`xxx`). ⚠ It must be a **shape test, not a filename allowlist**: an allowlist ("do not
    # [EN] scan READMEs") would let a real key pasted into a README slip through.
    pattern = re.compile(r'\bsk-[A-Za-z0-9_\-]{16,}')

    def _looks_placeholder(tok: str) -> bool:
        """这串 `sk-…` 是不是**占位符**（不是真密钥）。
        [EN] Is this `sk-...` a **placeholder** (not a real key)? The test is about the string itself.
        """
        body = tok[3:] if tok.lower().startswith('sk-') else tok
        low = body.lower()
        if any(w in low for w in ('your', 'xxx', 'placeholder', 'example', 'here')):
            return True
        if len(set(low)) <= 2:
            return True
        if len(set(low)) < 6:
            return True
        return False

    cand = _grep_text_files(dst, pattern)
    hits: list[str] = []
    if cand:
        real_hits: list[str] = []
        for rel in cand:
            fp = dst / rel
            try:
                text = fp.read_text(encoding='utf-8', errors='ignore')
            except Exception:                                # noqa: BLE001
                real_hits.append(rel)
                continue
            if any(not _looks_placeholder(m.group(0)) for m in pattern.finditer(text)):
                real_hits.append(rel)
        hits = real_hits
        skipped = len(cand) - len(real_hits)
        if skipped and not hits:
            # 放行是有意的，但**要说出来** —— 不说的话，哪天真的有人把真 key
            # 写成"看起来像占位符"的形态，这里会静默放过且没有任何痕迹。
            # [EN] The pass is intentional but **must be stated**: otherwise a real key written in a
            # [EN] placeholder-like shape is let through silently with no trace.
            problems.append(f'{NOTE_PREFIX} 放行了 {skipped} 个文件里的 `sk-…`（判定为占位符）：'
                            f'{cand[:3]}')
    if hits:
        problems.append(f'★ 疑似密钥字面量（sk-…）：{hits[:3]}')

    # 2b) ★★★ **兜底判据**：包里**任何** `.env` 里"敏感键名 + 非空值"一律算问题。
    #
    # 为什么需要它（发布 0.3.2 时被抓到的教训）：
    #   上面那条 `sk-…` 只管一种**形态**，`SERVICE_SECRET_KEYS` 管一张**名单** ——
    #   两者都可能漏：`SESSION_SECRET_KEY` 既不是 `sk-` 开头、也不在名单里，
    #   于是 64 位十六进制的会话密钥**原样进了发布包**，自检一声不响。
    #   ⇒ 这条不猜形态、不靠名单：**只看"键名像凭据"且"值不是空的"**。
    #
    # ★★★ 2026-10-22（用户：「**环境文件里 APIKey 需要清理掉**」）：扫描范围从
    #   "只扫 novelservices/ 下面"扩大到 **包里每一个 `.env` / `.env.example`
    #   / `.env.*` 文件**。原因是旧写法的覆盖面取决于**目录位置**：
    #   服务挪个位置、或者哪天产品在根目录之外多出一个 `.env`，同一个错误就漏过去，
    #   而"漏过去"的样子是**自检说 ✓**。位置不该是判据的一部分 —— 只要文件名是 env，
    #   就要按同一把尺子量。
    # ⚠ 误报控制：只认那几个**收尾词**（`*_TOKEN` 复数、`SORT_KEY`、`BASE_URL` 都不误伤），
    #   再加一个 `APIKEY`（无下划线的写法，实测别家配置里很常见）。
    # [EN] ★★★ **Fallback criterion**: a "credential-looking key + non-empty value" in **any** `.env`
    # [EN] in the package is always a problem. The `sk-...` rule covers one **shape** and
    # [EN] `SERVICE_SECRET_KEYS` one **list** -- both can miss (a 64-char hex `SESSION_SECRET_KEY`
    # [EN] went into the package with the self-check silent). This rule guesses no shape, trusts no list.
    # [EN] ★★★ 2026-10-22 (user: "**the API key in the env file must be cleaned out**"): the scan was
    # [EN] widened from "only under novelservices/" to **every `.env` / `.env.example` / `.env.*` file in
    # [EN] the package**. The old coverage depended on **location**: move a service, or let the product
    # [EN] grow a `.env` outside the root, and the same mistake sails through -- and "sails through"
    # [EN] looks exactly like a self-check saying ✓. Location must not be part of the criterion.
    # [EN] ⚠ False-positive control: only those **tail words** (`*_TOKENS` plural, `SORT_KEY`,
    # [EN] `BASE_URL` are untouched), plus `APIKEY` (the no-underscore spelling, common in other
    # [EN] projects' configs).
    _tails = ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'PASSWD', 'CREDENTIAL')
    _suspect: list[str] = []
    for _env in sorted(dst.rglob('.env*')):
        if not _env.is_file() or not _env.name.startswith('.env'):
            continue
        try:
            _txt = _env.read_text(encoding='utf-8', errors='ignore')
        except Exception:                                    # noqa: BLE001
            continue
        _rel = _env.relative_to(dst).as_posix()
        for _k, _v in parse_env_pairs(_txt):
            _ku = _k.upper()
            if _v and (any(_ku.endswith(_t) for _t in _tails) or _ku.endswith('APIKEY')):
                _suspect.append(f'{_rel}:{_k}')
    if _suspect:
        problems.append(f'★ 环境文件里仍有非空的凭据字段（脱敏没清干净）：{_suspect[:5]}')

    # 2c) ★★★ 根目录 `.env` / `.env.example`：**密钥必须空；样例的 LLM 配置也要空**。
    #
    # ★★★ 2026-10-22 改口径（构建完当场验配置才发现，是一处**真回归**）：
    #   第一版把 `.env` 和 `.env.example` **一起**清空 `LLM_*` / `MODEL_*` / `EMBEDDING_*`。
    #   跑起来一验：`Config.s('LLM_BASE_URL')` 返回 `''` —— 因为 `coerce()` 对
    #   **str / path / enum 不做空值回落**（只有 bool 与 int 会回落到 `SPEC` 默认值）。
    #   ⇒ 发布版里 `.env` 一清空，程序就**指向空地址、没有模型名**，用户填了 key 也用不了，
    #     而界面上只会看到"请求失败"，没人会想到是打包时清空的。
    #   ⇒ 正确分工（也正是用户原话的口径 ——「把 **`.env.example`** 里的 API Key 以及
    #     LLM 配置信息清理掉」）：
    #       · `.env` —— **程序读的那份**：官方默认值 + `secret` 留空 ⇒ 装上就能跑，只差一个 key；
    #       · `.env.example` —— **给人看的那份**：密钥与 LLM 配置的值全空，只留键名与说明。
    #   两者的**键集合必须一致**，这样样例仍然是完整的"旋钮清单"。
    # [EN] ★★★ Re-specified 2026-10-22 (found by actually loading the config from the built package
    # [EN] -- a real regression): the first version blanked `LLM_*` / `MODEL_*` / `EMBEDDING_*` in
    # [EN] **both** files. Verified: `Config.s('LLM_BASE_URL')` returned `''`, because `coerce()` does
    # [EN] **not** fall back to the SPEC default for str/path/enum (only bool and int do).
    # [EN] => Blanking `.env` leaves the shipped program pointing at an empty URL with no model names;
    # [EN] the user fills in a key and it still fails, showing only "request failed".
    # [EN] => Correct split (also the user's own words -- clean the API key and LLM config out of
    # [EN] **`.env.example`**): `.env` is the file the program reads (official defaults + empty
    # [EN] secrets => runs out of the box, only a key missing); `.env.example` is the human-readable
    # [EN] one (secrets and LLM values blanked, key names and comments kept). Both must carry the same
    # [EN] key set, so the example stays a complete list of knobs.
    _spec = _load_spec()
    _secret_keys = {k for k, s in _spec.items() if s.get('secret')}
    for _name in ('.env', '.env.example'):
        _p = dst / _name
        if not _p.is_file():
            continue
        _pairs = parse_env_pairs(_p.read_text(encoding='utf-8'))
        _dirty = [k for k, v in _pairs
                  if v and (k in _secret_keys
                            or (_name == '.env.example'
                                and k.upper().startswith(LLM_KEY_PREFIXES)))]
        if _dirty:
            problems.append(f'★ {_name} 里仍有非空的密钥'
                            f'{" / LLM 配置" if _name == ".env.example" else ""}：{_dirty[:6]}')
        # ★ 反向兜底：`.env` 里的 `LLM_BASE_URL` / `MODEL_FRONT` **必须有值**。
        #   空值不回落（见上），所以"清空过度"会让发布版直接不可用；
        #   这条判据把那种错误变成**当场红**，而不是等用户报"用不了"。
        # [EN] ★ Reverse guard: `LLM_BASE_URL` / `MODEL_FRONT` in `.env` **must have values**. Empty
        # [EN] values do not fall back (see above), so over-cleaning makes the release unusable; this
        # [EN] turns that into an immediate red instead of waiting for "it doesn't work" from a user.
        if _name == '.env':
            _must = [k for k in ('LLM_BASE_URL', 'MODEL_FRONT') if k in dict(_pairs)]
            _empty = [k for k in _must if not dict(_pairs)[k].strip()]
            if _empty:
                problems.append(f'★ `.env` 的 {_empty} 是空的 —— 字符串型配置**不会**回落默认值，'
                                f'发布版会连不上模型')
    # `.env` 与 `.env.example` 的**键集合**必须一致：样例少一个键，用户就永远不知道有那个旋钮。
    # [EN] `.env` and `.env.example` must have the same **key set**: a key missing from the example is
    # [EN] a knob the user will never learn about.
    _env_p, _ex_p = dst / '.env', dst / '.env.example'
    if _env_p.is_file() and _ex_p.is_file():
        _a = {k for k, _ in parse_env_pairs(_env_p.read_text(encoding='utf-8'))}
        _b = {k for k, _ in parse_env_pairs(_ex_p.read_text(encoding='utf-8'))}
        if _a - _b:
            problems.append(f'★ `.env` 里有 `.env.example` 没有的键：{sorted(_a - _b)[:6]}')
        if _b - _a:
            problems.append(f'★ `.env.example` 里有 `.env` 没有的键：{sorted(_b - _a)[:6]}')

    # 3) 不得残留本机绝对路径
    # [EN] 3) No leftover local absolute paths
    home_marks = ['C:\\Users\\chao', 'C:/Users/chao', 'C:\\小说世界AI模拟']
    for mark in home_marks:
        hits = _grep_text_files(dst, mark)
        if hits:
            problems.append(f'本机路径残留「{mark}」：{hits[:3]}')

    # 4) 不该存在的目录/文件
    # [EN] 4) Directories/files that should not exist
    for rel in ('.venv', '__pycache__', 'logs', 'assets/screenshots',
                'developers', 'tests', 'exports',
                '.git', '.install_manifest.json', '.workbuddy', '.ui_state',
                '.bilingual_done.json', 'usage.db', 'llm_cache.db', 'llm_models.json'):
        p = dst / rel
        if p.exists():
            problems.append(f'不该发布的路径仍在：{rel}')
    leftover_logs = list(dst.rglob('*.log'))
    if leftover_logs:
        problems.append(f'残留日志文件 {len(leftover_logs)} 个：'
                        f'{[str(p.relative_to(dst)) for p in leftover_logs[:3]]}')
    leftover_env = [p for p in dst.glob('.env.*') if p.name != '.env.example']
    if leftover_env:
        problems.append(f'残留 .env 备份：{[p.name for p in leftover_env]}')
    # ★ 2026-10-11：本机过程产物三件套 —— 以前**没有**这一条，于是它们
    #   （尤其是 260 多份 `*.bak-bilingual`）会整批跟着发布包走。
    # [EN] ★ 2026-10-11: the three local process artifacts -- this check **didn't exist** before, so
    # [EN] they (especially the 260+ `*.bak-bilingual` files) rode along wholesale.
    # ★ 2026-10-11 / ★★★ 2026-10-22：`*.bak*` 与 `*.old*` 一律不许在包里。
    #   2026-10-11 只写了 `*.bak-bilingual`，2026-10-22 又发现 `*.old-*`；
    #   重新发布 0.3.2 时自检抓到的却是**另一种**形态 `*.bak-before-临时指向`（里面是真 key）——
    #   三次都是"形态写得太窄"。这次改成**前缀通配**，一次覆盖全部变体。
    # [EN] ★ 2026-10-11 / ★★★ 2026-10-22: no `*.bak*` or `*.old*` in the package. 2026-10-11 only
    # [EN] covered `*.bak-bilingual`, 2026-10-22 found `*.old-*`, and re-releasing 0.3.2 found yet
    # [EN] another shape `*.bak-before-...` (with a real key inside) -- the pattern was too narrow all
    # [EN] three times. Now it is a **prefix** wildcard covering every variant.
    leftover_ver = [str(p.relative_to(dst)) for p in dst.rglob('*')
                    if p.is_file() and (_match(p.name, '*.bak*') or _match(p.name, '*.old*'))]
    if leftover_ver:
        problems.append(f'残留备份 / 旧产物 {len(leftover_ver)} 个：{leftover_ver[:3]}')
    leftover_dbs = [str(p.relative_to(dst)) for p in dst.rglob('*.db')]
    if leftover_dbs:
        problems.append(f'残留数据库文件：{leftover_dbs[:3]}')

    # 5) 必带文件齐全
    # [EN] 5) Required files all present
    missing = [rel for rel in REQUIRED if not (dst / rel).exists()]
    if missing:
        problems.append(f'缺少必带文件（{len(missing)} 项）：{missing[:6]}')

    # 5b) ★★ 四套启动器各有落点，且**每套都读魔数核对**。
    #   ⚠ 不能只判"文件名在"：Windows 叫 `setup.exe`，Linux 与 macOS 都叫 `setup`（**同名**），
    #     "名字对上了"根本证不了它是哪一套 —— 这正是"把 Windows 包发给 Mac 用户"那类错
    #     唯一的客观防线。
    #   ★ 2026-10-22：从"每个包只许有一套"改成"一个包里四套各有其位"：
    #     根目录那套必须是打包机的；其余三套在 `启动器/其他平台/<平台>/`，缺一套就是缺一个平台。
    # [EN] 5b) ★★ Each of the four launcher sets has a home, and **every set is verified by magic**.
    # [EN] ⚠ Not just "the filename exists": Windows is `setup.exe` while Linux and macOS are both
    # [EN] `setup` (**identical names**) -- a matching name proves nothing about which set it is. This
    # [EN] is the only objective defence against "a Windows package sent to a Mac user".
    # [EN] ★ 2026-10-22: from "one set per package" to "four sets, each in its place": the root set must
    # [EN] be the build host's; the other three live under `启动器/其他平台/<platform>/`, and a missing
    # [EN] one means a missing platform.
    host = host_platform()
    got_root = set(launcher_platforms_in_dir(dst))
    allowed_root = ALLOWED_LAUNCHER_PLATFORM.get(host) or set()
    if not got_root:
        problems.append('★ 根目录一个启动器都没量到')
    elif allowed_root and got_root - allowed_root:
        problems.append(f'★ 根目录启动器不是本机平台（{host}）：实测 {sorted(got_root)}')
    for key, dirname in LAUNCHER_SETS.items():
        if key == host:
            continue
        stage = dst / LAUNCHER_STAGE_DIR / OTHER_PLATFORM_DIR / key
        names = required_launchers(key)
        lack = [n for n in names if not (stage / n).is_file()]
        if lack:
            problems.append(f'★ 缺 {PLATFORM_LABEL.get(key, key)} 那一套启动器：'
                            f'{LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/{key} 里少了 {lack}')
            continue
        got = set(launcher_platforms_in_dir(stage))
        allowed = ALLOWED_LAUNCHER_PLATFORM.get(key) or set()
        stray = sorted(got - allowed) if allowed else []
        if stray:
            problems.append(f'★ {PLATFORM_LABEL.get(key, key)} 那套启动器魔数不对：'
                            f'实测 {sorted(got)}，应为 {sorted(allowed)}')

    # 5c) ★ `packages/` 里的 flet 离线运行时**一个都不能少**。
    #   ★ 2026-10-22：不再按平台裁剪，所以判据变成"四平台的运行时全在"
    #     （以前是"恰好等于该平台那份"，那条判据的形态随裁剪一起作废了）。
    #   ⚠ 缺了程序装不起来（会退回联网下载），而"退回联网"不报错 —— 只有这里拦得住。
    # [EN] 5c) ★ Not one flet offline runtime may be missing from `packages/`.
    # [EN] ★ 2026-10-22: no per-platform trimming any more, so the criterion becomes "all four
    # [EN] platforms' runtimes are present" (it used to be "exactly that platform's list", a shape that
    # [EN] died with the trimming). ⚠ Missing one means the installer falls back to downloading, which
    # [EN] reports nothing -- only this check stops it.
    want_pkgs = sorted({n for names in PACKAGE_FILES.values() for n in names})
    pkgs_dir = dst / 'packages'
    have = {p.name for p in pkgs_dir.iterdir()} if pkgs_dir.is_dir() else set()
    miss_pkg = [n for n in want_pkgs if n not in have]
    if miss_pkg:
        problems.append(f'缺少 flet 离线运行时：{miss_pkg[:4]}')

    # 6) `.env` 里 LLM 密钥必须为空 —— 已在 2c 里统一判过（那里还管样例与 LLM 配置），
    #    这里不再重复：**两条规则用同一个判据 = 其中一条是死的**。
    # [EN] 6) The LLM key in `.env` must be empty -- already covered by 2c (which also covers the
    # [EN] example and the LLM config). Not repeated here: two rules sharing one criterion means one of
    # [EN] them is dead.

    return problems


def _grep_text_files(root: Path, needle) -> list[str]:
    """在发布包的文本文件里找 `needle`（字符串或正则）。跳过二进制与图片。
        English:
    Find `needle` (string or regex) in the release package's text files. Skip binaries and images.
    """
    pat = needle if hasattr(needle, 'search') else re.compile(re.escape(str(needle)))
    skip_ext = {'.png', '.jpg', '.jpeg', '.webp', '.ico', '.icns', '.ttf', '.otf',
                '.woff', '.woff2', '.zip', '.gz', '.tgz', '.pdf', '.docx'}
    hits: list[str] = []
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix.lower() in skip_ext:
            continue
        if p.stat().st_size > 8 * 1024 * 1024:
            continue
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if pat.search(text):
            hits.append(str(p.relative_to(root)))
    return hits


def size_of(path: Path) -> tuple[int, int]:
    """(总字节, 文件数)
        English:
    (total bytes, file count)
    """
    total = 0
    count = 0
    for p in path.rglob('*'):
        if p.is_file():
            total += p.stat().st_size
            count += 1
    return total, count


def human(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024.0
    return f'{n:.1f} GB'


def _load_spec() -> dict:
    """工程的配置登记表 `config.SPEC`（键 → 规格）。
        English:
    The project's config registry `config.SPEC` (key -> spec).
    """
    sys.path.insert(0, str(APP_DIR))
    import config  # noqa: E402
    return config.SPEC


def main() -> int:
    ap = argparse.ArgumentParser(description='把一个版本发布到 <发布根>/<版本号>/')
    ap.add_argument('target', nargs='?', default='',
                    help='落点目录（省略 = <发布根>/<config.VERSION>）')
    ap.add_argument('--out', default='', help='落点目录（与位置参数同义，二选一）')
    ap.add_argument('--release-root', default='',
                    help='发布根目录（默认：工程同级的「发布版本」）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--yes', action='store_true')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--zip', action='store_true')
    ap.add_argument('--keep-dev-tools', action='store_true')
    ap.add_argument('--keep-dev-docs', action='store_true')
    args = ap.parse_args()

    src = APP_DIR
    release_root = (Path(args.release_root).expanduser().resolve()
                    if args.release_root else RELEASE_ROOT)
    version = _source_version()
    # ★ 落点优先级：显式给的路径 > 发布根/<版本号>。
    #   ★ 版本号从 `config.py` 读，**不设默认值**：读不到就拒绝发布 ——
    #     编一个版本号出来正是"包名与内容不符"的起点。
    # [EN] Target priority: explicit path > <release root>/<version>. The version is read from
    # [EN] `config.py` with **no default**: if unreadable, refuse -- inventing one is where "the
    # [EN] package name does not match its content" starts.
    explicit = args.target or args.out
    if explicit:
        dst = Path(explicit).expanduser().resolve()
    elif version:
        dst = (release_root / version).resolve()
    else:
        print('✗ 读不到 config.py 里的 VERSION，且没有指定落点目录；拒绝发布。')
        return 2

    print('═' * 62)
    print('  发布打包 · 小说世界AI模拟')
    print('═' * 62)
    print(f'  版本:   {version or "（读不到）"}')
    print(f'  源目录: {src}')
    print(f'  目标:   {dst}')

    # ── 路径安全检查 ──
    # [EN] ── Path safety check ──
    if dst == src:
        print('\n✗ 目标目录与源目录相同，拒绝执行。')
        return 2
    try:
        dst.relative_to(src)
        print('\n✗ 目标目录在源目录内部，会导致递归复制，拒绝执行。')
        return 2
    except ValueError:
        pass
    # ★ 反方向也必须拦：`--out` 指到**工程上一级**（`小说世界AI模拟/`）时，
    #   源目录就在目标里 —— 而 `--force` 会先 `rmtree(目标)`，那等于**把工程本身删掉**。
    #   这条以前只在文档里"想过"，没写进代码；这次改流程时被漏掉了，补回来。
    # [EN] ★ The reverse direction must be blocked too: `--out` pointing at the **parent**
    # [EN] (`小说世界AI模拟/`) puts the source inside the target -- and `--force` runs `rmtree(target)`
    # [EN] first, which would **delete the project itself**. Previously only thought about, never coded.
    try:
        src.relative_to(dst)
        print('\n✗ 源目录在目标目录内部（目标给成了工程上一级？），--force 会把工程删掉，拒绝执行。')
        return 2
    except ValueError:
        pass

    # ── 目标目录处理：只删"我们自己产出的发布版" ──
    # [EN] ── Target handling: only delete "release versions we produced ourselves" ──
    existing_release = (dst / MANIFEST_NAME).exists()
    if dst.exists():
        entries = list(dst.iterdir())
        if entries and not existing_release:
            print(f'\n✗ 目标目录非空，且不是本脚本先前产出的发布版（没有 {MANIFEST_NAME}）。')
            print('   为免误删，请换一个空目录；或确认那确实是要覆盖的旧发布版。')
            return 2
        if entries and not args.force:
            print('\n✗ 目标已存在且非空（是旧发布版）。要覆盖请加 --force。')
            return 2
        if entries:
            print(f'  （--force：清空旧的发布版 {dst}）')

    if args.dry_run:
        plan = Plan()
        ignore = make_ignore(args, plan, src)
        for _cur, _dirs, _files in _walk(src, ignore):
            pass
        print('\n── 计划排除 ──')
        for group, items in plan.skipped.items():
            print(f'  {group}: {len(items)} 项  例：{", ".join(items[:3])}')
        print(f'\n  共排除 {plan.total()} 项。')
        # 第 5 步会补哪些键（不改盘、只看差异）
        # [EN] Which keys step 5 would add (read-only preview)
        spec = _load_spec()
        live = parse_env_pairs((src / '.env').read_text(encoding='utf-8')) \
            if (src / '.env').is_file() else []
        extra = [k for k, _ in live if k not in spec]
        print(f'\n── .env 同步 ──\n  样例将由 SPEC（{len(spec)} 项）生成；'
              f'本机 .env 里 SPEC 未登记的键：{extra or "无"}')
        print(f'  随后清空 {len([k for k in spec if k.upper().startswith(LLM_KEY_PREFIXES)])} 个'
              f' LLM 相关键的值')
        print(f'\n  启动器：根目录 = {host_platform()} 那套；'
              f'其余三套 → {LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/<平台>/')
        print('\n  --dry-run 到此为止，未复制任何文件。')
        return 0

    if not args.yes:
        print('\n  即将开始复制。回车继续，Ctrl+C 取消...')
        try:
            input()
        except EOFError:
            pass

    # ── [1/8] 清空目标（仅旧发布版）+ 建目录 ──
    print(f'\n[1/8] 目标版本文件夹：{dst}')
    # [EN] ── [1/8] Clear the target (old releases only) + create it ──
    if dst.exists() and any(dst.iterdir()) and args.force:
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    # ── [2/8] 复制 ──
    # [EN] ── [2/8] Copy ──
    print('\n[2/8] 复制整棵工程（排除表在复制**前**生效）…')
    plan = Plan()
    t0 = time.time()
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=make_ignore(args, plan, src))
    print(f'      完成（{time.time() - t0:.1f}s）')

    # ── [3/8] 四套启动器各就各位 ──
    # [EN] ── [3/8] Put the four launcher sets in place ──
    print('[3/8] 启动器：根目录本机那套 + 其余三套进 '
          f'{LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/ …')
    staged_log: list[str] = []
    swap_problems, staged = stage_launcher_sets(dst, src, staged_log)
    for line in staged_log:
        print(f'      {line}')

    # ── [4/8][5/8][6/8] `.env` / `.env.example` ──
    # [EN] ── [4/8][5/8][6/8] `.env` / `.env.example` ──
    print('[4/8] 重新生成 .env / .env.example（全键 + 默认值 + 密钥留空）…')
    example, env = write_clean_env(dst)
    print('[5/8] 同步本机 .env 里多出来的键 …')
    added, blanked = sync_env_keys(src / '.env', example, env)
    if added:
        print(f'      补进样例 {len(added)} 个：{added[:8]}'
              + (f'（其中值留空 {len(blanked)} 个）' if blanked else ''))
    else:
        print('      没有多出来的键（样例已覆盖本机 .env 的全部键）')
    print('[6/8] 清空 `.env.example` 里的密钥与 LLM 配置（`.env` 保留官方默认，装上就能跑）…')
    # ★★★ 只清**样例**（2026-10-22 实测修正）：`coerce()` 对 str/path/enum **不回落默认值**
    #   （只有 bool 与 int 回落），所以把 `.env` 里的 `LLM_BASE_URL` 清空 = 发布版连不上模型，
    #   而用户只看得到"请求失败"。`.env` 是程序读的那份（官方默认 + 密钥空，装上就能跑），
    #   `.env.example` 是给人看的那份（值全清、键名与注释保留）。
    # [EN] ★★★ Blank the **example only** (corrected after measurement on 2026-10-22): `coerce()`
    # [EN] does **not** fall back to the default for str/path/enum (only bool and int), so emptying
    # [EN] `LLM_BASE_URL` in `.env` means the release cannot reach a model while the user only sees
    # [EN] "request failed". `.env` is the file the program reads (official defaults + empty secret),
    # [EN] `.env.example` is the human-readable one (values blanked, names and comments kept).
    scrubbed = sorted(scrub_llm_env(example))
    print(f'      {len(scrubbed)} 个键的值在样例里已清空（键名与注释保留）')

    # ── [7/8] 兜底清扫 ──
    # [EN] ── [7/8] Fallback sweep ──
    # ★ 顺序要紧：清扫排在 `sanitize_service_envs` **之前**也行，但必须排在
    #   `scan_release` 之前 —— 自检要查的是"清完的包"。
    # [EN] ★ Order matters: the sweep may run before `sanitize_service_envs`, but must run before
    # [EN] `scan_release` -- the check must inspect the cleaned package.
    print('[7/8] 兜底清扫日志 / 缓存 / 台账 / 开发目录 / 旧备份 …')
    junk = clean_junk(dst)
    for cat, items in junk.items():
        print(f'      {cat}: {len(items)} 项  例：{items[:2]}')
    if not junk:
        print('      没有发现需要清扫的东西')

    # ★★★ 2026-10-21（用户：「**发布的时候要清理掉各个服务配置文件中的 API Key**」）：
    #   根目录的 `.env` 是**重新生成**的（本来就没有密钥），但**服务自己的** `.env`
    #   是复制过来的原文件 —— 里面有打包机的真密钥。这里原地清空。
    #   ⚠ 必须排在 `scan_release` **之前**：自检要拿"清完之后"的包去搜密钥，
    #     排后面等于"自检搜的是干净包、发出去的是脏包"。
    # [EN] ★★★ 2026-10-21 (user: "**when publishing, scrub the API keys from every service config
    # [EN] file**"): the root `.env` is **regenerated**, but each **service's own** `.env` is a copied
    # [EN] original holding the build machine's real key. Blanked in place here, **before**
    # [EN] `scan_release` -- otherwise the check searches a clean copy while shipping a dirty one.
    svc_env_problems = sanitize_service_envs(dst, [])

    # [7/8] 说明书写进包里
    # [EN] [7/8] The platform note goes into the package
    note = write_release_note(dst, version, host_platform(), staged)
    print(f'      已写入 {note.name} + {NOTE_NAME_EN}，并在 README 顶部插了横幅')

    total, count = size_of(dst)
    print('\n── 已排除（复制前）──')
    for group, items in plan.skipped.items():
        print(f'  {group}: {len(items)} 项')
    print('\n── 结果 ──')
    print(f'  文件 {count} 个 / {human(total)}   耗时 {time.time() - t0:.1f}s')
    print(f'  版本 {version or "（读不到）"} · 平台：**不区分**（一个包四个平台全带）')

    # ── [8/8] 自检 ──
    # [EN] ── [8/8] Self-check ──
    real_key = ''
    live_env = src / '.env'
    if live_env.exists():
        for line in live_env.read_text(encoding='utf-8').splitlines():
            if line.startswith('LLM_API_KEY='):
                real_key = line.split('=', 1)[1].strip()
    # ★ 把"提示"与"问题"分开：`ℹ` 开头的条目不算失败
    #   （退出码非 0 会让回归器/CI 误报）。
    # ⚠ `svc_env_problems` / `swap_problems` 必须一起汇进自检结果：它们是"服务 `.env` 清不干净"
    #   与"启动器放不对"的唯一上报口 —— 不并入就等于"失败了也照样说发布成功"。
    # [EN] ★ Separate "notes" from "problems": entries starting with `ℹ` are not failures (a non-zero
    # [EN] exit code would make the regressor/CI report falsely). ⚠ `svc_env_problems` /
    # [EN] `swap_problems` must join the result: they are the only channels reporting "a service `.env`
    # [EN] could not be scrubbed" and "launchers misplaced"; leaving them out means "failed but we still
    # [EN] call it a success".
    _all_items = svc_env_problems + swap_problems + scan_release(dst, real_key)
    notes = [x for x in _all_items if x.startswith(NOTE_PREFIX)]
    problems = [x for x in _all_items if not x.startswith(NOTE_PREFIX)]
    print('\n── 发布前自检 ──')
    for n in notes:
        print(f'  {n}')
    if problems:
        for p in problems:
            print(f'  ✗ {p}')
    else:
        print('  ✓ 未发现密钥 / 本机路径 / 残留日志 / 缺件；四套启动器魔数与落点一致')

    manifest = {
        'name': '小说世界AI模拟',
        'version': version,
        'built_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'source': str(src),
        'files': count,
        'bytes': total,
        'excluded_groups': {k: len(v) for k, v in plan.skipped.items()},
        # ★ 2026-10-22：不再有"这个包是哪个平台的"这一说 —— 一个包四个平台。
        #   记的是"四套启动器各自的落点"，而不只是一个平台名。
        # [EN] ★ 2026-10-22: there is no "which platform is this package" any more -- one package,
        # [EN] four platforms. We record where each of the four sets lives, not just a platform name.
        'platform': 'single',
        'launcher_sets': staged,
        'launchers_actual': launcher_platforms_in_dir(dst),
        'env': {
            'generated': ['.env', '.env.example'],
            'synced_keys': added,
            'synced_values_blanked': blanked,
            'llm_keys_blanked': scrubbed,
        },
        'swept': {k: len(v) for k, v in junk.items()},
        'notes': notes,
        'checks': problems or 'clean',
        # ★ 只记"扫过什么、结果怎样"，**不要记密钥的任何派生值**（哪怕是哈希）。
        #   第一版写了 `env_key_sha1`，等于把开发者真实密钥的指纹一起发出去 ——
        #   不可逆不代表应该发。
        # [EN] ★ Only record "what was scanned and the result", **no derived value of secrets** (not
        # [EN] even hashes): the first version wrote `env_key_sha1`, i.e. the fingerprint of the real
        # [EN] key. Irreversible does not mean it should be sent.
        'secret_scan': {
            'compared_against_source_key': bool(real_key),
            'targets': ['真实 LLM_API_KEY', 'sk-… 字面量', '本机绝对路径',
                        '残留日志/.env 备份/开发目录', '必带文件清单',
                        '四套启动器魔数', '`.env` 密钥与 LLM 配置为空'],
        },
    }
    (dst / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    if args.zip:
        base = str(dst)
        zpath = shutil.make_archive(base, 'zip', root_dir=dst)
        zsize = Path(zpath).stat().st_size
        print(f'\n  已打包: {zpath}  ({human(zsize)})')

    print(f'\n[8/8] 发布目录: {dst}')
    # ★ 收尾只讲**这个包**怎么用：一个包四个平台，根目录是本机那套。
    # [EN] ★ Closing lines describe **this package**: one package, four platforms, host set in the root.
    print(f'  用户拿到后：直接双击 `start`（首次会建 venv 并装依赖）；'
          f'要安装到开始菜单/应用列表就跑 `setup`。')
    if len(staged) > 1:
        print(f'  换平台：把 {LAUNCHER_STAGE_DIR}/{OTHER_PLATFORM_DIR}/<平台>/ 里那三个文件'
              f'拷到包根目录（详见 {note.name}）。')
    return 1 if problems else 0


def _walk(root: Path, ignore):
    """按 copytree 的 ignore 语义走一遍树（供 --dry-run 收集跳过项）。
        English:
    Walk the tree following copytree's ignore semantics (for --dry-run to collect skipped items).
    """
    for cur, dirs, files in __import__('os').walk(root):
        rel = Path(cur).relative_to(root)
        drop = ignore(str(Path(cur)), dirs + files)
        dirs[:] = [d for d in dirs if d not in drop]
        yield cur, dirs, [f for f in files if f not in drop]


if __name__ == '__main__':
    sys.exit(main())
