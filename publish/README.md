# 发布脚本（打包 / 推送，两步分开）

三个文件，各管一件事：

| 文件 | 干什么 | 会不会联网 |
|---|---|---|
| `publish\build.ps1` | **生成发布包** → `发布版本\<版本号>\` | 不联网 |
| `publish\publish.ps1` | **把仓库推到 GitHub / Gitee**、打 tag、建 Release | 联网 |
| `publish\readme_variant.py` | 给两个远端**换 README 门面**（GitHub 英文 / Gitee 中文） | 不联网 |

先跑 A，确认包没问题，再跑 B。也可以只跑其中一个 —— 打好的包可以过几天再推。

---

## 〇、两个远端的门面不一样（2026-11-06 起）

源码里是 `README.md`（中文）+ `README_EN.md`（英文），但两个仓库要的**第一眼**不同：

| 远端 | `README.md` | 另一语言 | 语言条 |
|---|---|---|---|
| GitHub | **英文**（`README_EN.md` 的内容） | `README.zh-CN.md` | `[中文](README.zh-CN.md)` |
| Gitee | **中文**（原样） | `README.en.md` | `[English](README.en.md)` |

**只改文件名会坏**：两份 README 顶上的语言条互相指着对方，点「English」会停在原地。
所以换位和改语言条是同一件事，唯一实现在 `readme_variant.py`，它还会顺带检查
「两份 README 里的相对链接是不是都落在盘上」—— 门面文档点开是 404，比没有 README 更难看。

因为内容不同，**两个远端不能共用一个 commit**：各自一个工作区、各自一份历史。

---

## 一、阶段 A：生成发布包

```powershell
cd <工程根目录>          # 就是含 config.py / gui / sim 的那一层

.\publish\build.ps1 -Version 0.3.3            # 校验版本号一致后打包
.\publish\build.ps1 -Version 0.3.3 -Zip       # 再压一个 zip（Release 附件用）
.\publish\build.ps1 -DryRun                   # 只看会做什么，不动手
.\publish\build.ps1 -Version 0.3.4 -Force     # 重建（旧包移进 _旧版本\，不删）
```

**版本号只由你定。** 脚本 **不会改** `config.py` 的 `VERSION`，也不会"顺手"升级。
`-Version` 只用来**核对** —— 和你改好的 `VERSION` 不一致就报错停下（防止"包名写着 0.3.0、代码里是 0.3.3"）。

所以正确顺序是：**先改 `config.py` 的 `VERSION` → 再跑这个脚本**。

> ⚠ `-Force` 重建时，旧包是**移到** `发布版本\_旧版本（可在资源管理器里删除）\`，不是删掉。
> 因为 `make_release.py --force` 的清空动作会被批量删除守卫**静默拦下**（退出码还是 0），
> 用它的话你会以为重建了、其实旧包还在。

---

## 二、阶段 B：推送到 GitHub / Gitee

**最常用的一条**（两边都发；Gitee 第一次会弹登录框）：

```powershell
.\publish\publish.ps1 -Gitee -Token "<你的 GitHub PAT>"
```

只发 GitHub：

```powershell
.\publish\publish.ps1 -Token "<你的 GitHub PAT>"
```

只发 Gitee：

```powershell
.\publish\publish.ps1 -GiteeOnly
```

带版本号（打 tag + 建 Release）：

```powershell
.\publish\publish.ps1 -Gitee -Token "<PAT>" -Version "v0.3.4" `
    -ReleaseNotes "本次更新说明" -CommitMessage "v0.3.4: 本次更新说明"
```

其他常用：

```powershell
.\publish\publish.ps1 -DryRun                     # 只打印计划，不碰 git、不联网
.\publish\publish.ps1 -NoPush                     # 只生成两套工作区 + 本地 commit，不推
.\publish\publish.ps1 -Gitee -NoProxy             # 代理没起时直连
.\publish\publish.ps1 -Gitee -UploadAsset         # 同时把发布包 zip 挂到 Release 附件
.\publish\publish.ps1 -Lite                       # 更瘦：不推 assets\images
```

参数一览：

| 参数 | 说明 |
|---|---|
| `-Token` | GitHub PAT（`repo` 写权限）。不传则匿名（只能推已有凭据的仓库，也不能建仓） |
| `-Gitee` | **同时**推 Gitee（GitHub 也会推） |
| `-GiteeOnly` | **只**推 Gitee |
| `-GiteeToken` / `-GiteeUser` | 直接给 Gitee 令牌（不给则用已保存凭据 / 弹框） |
| `-ResetGiteeCred` | 丢掉本机保存的 Gitee 凭据，本次重新询问（令牌输错时用） |
| `-GithubIp` | 把 `github.com` 钉到指定 IP（走 `http.curloptResolve`，优先于 hosts / DNS），不改系统文件。**通常不用给**：不给时如果连不上，脚本会按候选池（`$GithubIpCandidates`）自己试一遍并用能连的那个重推 |
| `-Proxy` | 走代理，如 `http://127.0.0.1:7890`。**默认直连**，并且会覆盖 git 全局配置里残留的代理 |
| `-Version` | tag 名，如 `v0.3.4`。**留空则不打 tag、不建 Release**（只推代码）。带不带 `v` 都行（`0.3.4` 的 tag 就是 `0.3.4`）；与 `config.VERSION` 不一致**只警告、不拦**（版本号只由你定） |
| `-ReleaseNotes` | tag 正文 + Release 说明 |
| `-CommitMessage` | 提交信息，默认 `update: sync latest source`。两边各用同一句；工作区**无变更时不提交**（不会造空 commit） |
| `-RepoUrl` / `-GiteeRepoUrl` | 换仓库地址 |
| `-UploadAsset` / `-AssetPath` | 发布包挂 Release 附件（Gitee >95MB 自动分卷） |
| `-NoCreate` | 远端不存在时**不**自动建仓，只报告 |
| `-Private` / `-Description` | 自动建仓时用（默认公开 / 内置简介） |
| `-NoProxy` | 绕过三层代理配置直连 |
| `-NoPush` | 只生成、不推 |
| `-DryRun` | 只打印计划 |
| `-Lite` / `-WithDev` | 瘦身 / 连 `developers\` 一起推 |
| `-Branch` | 默认 `main`（推完会把远端默认分支也设成它） |

---

## 三、必须先知道的四件事

### 1. 远端不存在会自动建

`Phase 0` 会先查两个仓库在不在（GitHub / Gitee 各查一次 API）：

- **在** → 直接推；
- **不在** → 用你的令牌**建一个空仓库**（`auto_init = false`，即不勾 README），再推；
- 建完推送成功后会**把默认分支设成 `main`**（空仓库建出来常是 `master`，不改的话仓库首页会 404）。

建仓需要令牌：GitHub 用 `-Token`，Gitee 用 `-GiteeToken` 或弹框。不想让它建就加 `-NoCreate`。

> 为什么坚持 `auto_init = false`：勾了 README，远端就先有一个提交，我们第一次 push 必然被拒，
> 只能 force 覆盖 —— 等于把刚生成的东西再砸掉，多此一举。

### 2. 仓库里装的是什么（实测 138 MB / 1000 文件）

发布包 **892 MB** 装不进 Git（GitHub 单文件硬上限 100 MB）。所以分两条道：

- **Git 仓库** = 源码 + 文档 + 程序必需资源 → 实测 **约 138 MB / 1000 文件**，单文件最大 23.6 MB（`assets/fonts/LXGWWenKai-Regular.ttf`）
- **发布包** = 走 Release 附件（`-UploadAsset`），GitHub 能收；Gitee 通常限 100MB/个，脚本自动切成 `.part00/.part01…`

被排除掉的（**故意的，不是漏了**）：

| 排除项 | 体积 | 为什么 |
|---|---|---|
| `logs\` | 2.2 GB | 本机运行日志 |
| `novelservices\`（本体） | GB 级 | 三座外部服务各自独立；仓库里**只放 5 个桥接薄壳 .py** |
| `packages\` | 202 MB | flet 离线安装包，随发布包走 |
| `assets\screenshots\` | 286 MB | 调试截图。**里面 `audit_screens.json` 存着真的 API Key** |
| `novel_bench\results\` | 13 MB | 跑分产物（`bench/` `dataset/` 仍保留） |
| `launchers\dist\` | — | 12 个交叉编译产物，`launchers/build.py` 可重建 |
| `Simulating.gif` | 33.8 MB | 根目录的旧演示图，README 用的是 `assets/images/demo/walkthrough.gif` |
| `developers\` | 21 MB | 一次性探查脚本（`-WithDev` 可带上） |
| `.env` / `llm_models.json` / `usage.db` | — | **含真 API Key 与你的使用数据** |
| `*.bak*` / `*.exitbak` / `*.old-*` | — | 本机备份 |

想再瘦：`-Lite` 会再排掉 `assets\images`（54 MB 生成图，`make_art.py` 可重建）。

**根目录的 `start.exe` / `setup.exe` / `uninstall.exe`（和 Linux 版 `start` / `setup` / `uninstall`）保留** ——
README 里写着"双击这个"，排掉它们等于让人双击一个不存在的文件。

### 3. 它不会把你的源码目录变成 Git 仓库

源码目录里没有 `.git`，脚本也不会加。它用 robocopy 把**过滤后的快照**镜像到：

```
<工程同级>\_publish_repo_github\
<工程同级>\_publish_repo_gitee\
```

（`<工程同级>` = 工程根目录的**上一层**。想换位置用 `-RepoDir` / `-GiteeRepoDir`。）

`.git` 只在那两个目录里。搞坏了直接整个删掉重跑即可，源码一个字都不会动。
想换位置：`-RepoDir "D:\xxx"`（**不能**放在源码目录里面）。

> ⚠ 带路径的排除项**必须给完整路径**。实测 `/XD assets\screenshots` 这种相对写法会被
> robocopy 静默忽略，286 MB 调试截图（含真 Key）原样进工作区，而清单读起来完全正确。
> 另外 `/XF` 只**阻止复制**、不会删掉目标里已有的同名文件，所以脚本每次镜像完会按清单再扫一遍。

### 4. 四道安全闸（别拆）

1. `.env` / `llm_models.json` / `usage.db` / 日志 / 用户作品 / Gitee 凭据 —— 硬排除，压根不进工作区
2. **拿 `.env` 与 `llm_models.json` 里的真实密钥值去全文搜** —— 密钥被粘进文档、示例、调试脚本时，
   只有这一条拦得住（实测就是它抓到了 `assets/screenshots/audit_screens.json` 里的真 Key）
3. 形态体检（`sk-` / `ghp_` / `github_pat_` / `glpat-` / `AKIA` / `AIza` …），带**占位符判据** ——
   `sk-xxxxxxxx` / `sk-abcd1234efgh5678` 不会被误判成真 key
4. **token 不写进 `.git/config`**：push 时直接给带凭据的 URL，工作区里不落凭据，
   中途 Ctrl+C 也不会留下（旧写法是 set-url 完再清，异常退出就清不掉）

> 第 2、3 条宁可误报停下，也不放过。Key 推上公开仓库之后，**删提交也清不掉历史**。

---

## 四、首次使用要准备

1. **GitHub PAT**：[Settings → Developer settings → Tokens](https://github.com/settings/tokens)，勾 `repo`。
   Gitee 令牌勾 `projects` 读写。
2. **仓库可以不用手建** —— 脚本会建（见上文）。要自己建的话：空仓库，**别勾"初始化 README"**。
3. Gitee 凭据第一次运行会弹两个输入框，之后加密存在本机（`.gitee-cred.enc` + `.gitee-user.txt`），换机器要重输。
   **存了之后就不再弹框** —— 输错了加 `-ResetGiteeCred` 重跑（见第五节最后一条）。

---

## 五、失败时看这里

| 现象 | 原因 / 处理 |
|---|---|
| `Failed to connect to 127.0.0.1 port xxxxx` | 代理没起。本脚本默认直连；要代理用 `-Proxy` |
| `GitHub 仓库不存在` + `自动建仓需要 GitHub PAT` | 没给 `-Token`，不能建仓。补上，或先手动建 |
| `Unsupported SSL backend 'openssl'. Supported SSL backends: schannel` | **本机 git 的配置和它的编译方式不一致**（系统级 `C:\Program Files\Git\etc\gitconfig` 写了 `openssl`，那个 git 只编了 `schannel`）⇒ 它**每一个 https 操作都废**，跟令牌/网络/代理都没关系。脚本现在会自己问 git"你支持哪些"并自动换成支持的那个；永久修：`git config --global http.sslBackend schannel` |
| `Failed to connect to github.com:443` / `Recv failure: Connection was reset` | `hosts` 里那条 `github.com` 已经失效（**同一个 IP 隔一天就会烂**）。现在**不用管**：脚本会按候选池自己试一遍并重推；想跳过这 20 秒就加 `-GithubIp <能连的 IP>`（脚本发现能连时会把这一个直接告诉你） |
| push 报 `Incorrect username or password (access token)` | Gitee 网络是通的，**令牌不对**（输错 / 用了登录密码 / 没勾 projects）。`-ResetGiteeCred` 重输 |
| 建 Gitee 仓库 403 | 令牌没勾 `projects` 读写 |
| `push 被拒（历史不一致）` | 脚本自动 `force-with-lease` 重试；仍失败说明远端有新提交，先人工看一眼 |
| Gitee 仓库建失败 `401` | **令牌本身不对**（输错 / 过期 / 已删）。脚本会**自动作废**已存的凭据并提示 → 重跑重输；想跳过弹框用 `-GiteeUser sdxianchao -GiteeToken "<新令牌>"` |
| Gitee 仓库建失败 `403` | **令牌有效，但没有建仓权限**。去勾 `projects` 读写 —— 重输令牌一百次也不会好，脚本**故意不清**凭据 |
| 已存凭据要换掉（比如换账号） | `.\\publish.ps1 -Gitee -ResetGiteeCred`（等价于手删 `.gitee-cred.enc` + `.gitee-user.txt`） |
| 扫到密钥中止 | 加进脚本的 `$XD` / `$XF` 排除清单，或把真 Key 从那个文件挪走 |
| `README 换位失败` | 语言条被改过（脚本要求 `[English](README_EN.md)` 恰好出现 1 次）。按报错行号看一眼 |
| `README 里有 N 个坏链` | 换位后链接指到不存在的文件。按列出来的路径补文件或改链接 |
| 发布包目录找不到 | 先跑阶段 A。不加 `-UploadAsset` 时不影响推源码 |
| 仓库首页 404 | 默认分支还指着 `master`。脚本会设成 `main`；失败时到网页上手动改 |

---

## 六、退出码

| 码 | 含义 |
|---|---|
| 0 | **本来要发的每一边**都成功 |
| 2 | 前置检查失败（目录冲突 / 工作区位置非法 / README 换位失败） |
| 3 | **密钥体检命中，已中止** |
| 4 | 有一次要发的没成功（建仓失败 / 没凭据 / push 失败 —— 看汇总里的 ✗） |

> 退出码看的是 `$wantGithub` / `$wantGitee`，不是 `$doGithub` / `$doGitee`：
> 中途因为"没令牌"跳过 GitHub 时，不能因为"跳过了"就报成功 —— 那等于**页面上一片空，退出码 0**。

---

**English (short)**
`build.ps1` builds `发布版本\<version>\` via `tools/make_release.py` — offline, never edits `VERSION`.
`publish.ps1` mirrors two filtered snapshots into `<sibling>\_publish_repo_github\` and
`_publish_repo_gitee\`, swaps the README front page (`readme_variant.py`: English on GitHub,
Chinese on Gitee), commits, pushes, tags, and optionally attaches the release bundle.
It also **creates the remote repo** when it does not exist (`auto_init = false`) and sets the
default branch to `main`.
The 892 MB release folder never enters Git (100 MB per-file cap); the repo carries ~138 MB of
source/docs/assets, and the bundle ships as a Release asset (`-UploadAsset`, auto-split for Gitee).
Your source tree never becomes a repo. Four safety gates: hard-exclude secrets, full-text search
for the **real** key values, shape checks with a placeholder test, and no token ever written into
`.git/config`.
