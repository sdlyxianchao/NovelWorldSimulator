# -*- coding: utf-8 -*-
"""日志框架：统一日志管理。

功能：
- 每次运行生成 `nws_<项目名>_<年_月_日_时_分_秒>.log`
  （还没开卷时没有项目名那一段：`nws_2026_10_07_01_23_11.log`；
  开卷后**改名**补上，见 `NWSLogger.set_project()`）
- 支持多种日志类型（UI、后台、配置等）
- PII 处理（隐藏敏感信息）
- 自动清理旧日志

English:
Logging framework: unified log management.
Features:
- Each run generates `nws_<project name>_<year_month_day_hour_minute_second>.log`
  (before a project is opened there is no project name segment: `nws_2026_10_07_01_23_11.log`;
  after opening, **rename** to add it back, see `NWSLogger.set_project()`)
- Supports multiple log types (UI, background, config, etc.)
- PII handling (hide sensitive info)
- Automatically clean up old logs
"""
from __future__ import annotations

import os
import re
import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# 日志目录
# [EN] Log directory
DEFAULT_LOG_DIR = Path(__file__).resolve().parent / 'logs'

#: 文件名里**绝对不许出现**的字符（Windows 的规则最严，跨平台按它来）。
#: 项目名是用户自己起的，里头可能有 `/`、`:`、空格、表情……直接拼进文件名会
#: ① 建不出文件 ② 甚至建到别的目录去（`a/b` / `..` 是**路径**不是名字）。
# [EN] : Characters that must **absolutely not appear** in a filename (Windows has the strictest rules;
# [EN] follow them for cross-platform).
# [EN] : The project name is chosen by the user, and may contain `/`, `:`, spaces, emoji...
# [EN] Concatenating it directly into a filename will
# [EN] : ① fail to create the file ② even create it in a different directory (`a/b` / `..` are
# [EN] **paths**, not names).
_BAD_IN_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
#: 项目名在文件名里最长留几个字符（别把整个路径顶爆：Windows 全路径有 260 上限）
# [EN] : Max characters of the project name kept in the filename (don't blow up the whole path: Windows
# [EN] has a 260 full-path limit)
_MAX_NAME_CHARS = 40
#: 公开别名 —— 判据（`tools/verify_dialogue_log.py` 的 C9）要按它断言截断长度，
#: 别让判据去碰下划线开头的内部名（改内部名不该弄红判据）。
# [EN] : Public alias -- the criterion (`tools/verify_dialogue_log.py`'s C9) must assert the truncation
# [EN] length against it,
# [EN] : don't let the criterion touch internal names starting with an underscore (renaming internals
# [EN] shouldn't turn the criterion red).
MAX_NAME_CHARS = _MAX_NAME_CHARS


def safe_filename_token(name: Any) -> str:
    """把项目名净化成**能安全拼进文件名**的一小段。净化成空就返回空串。

    ⚠ 三个都是会真出事的：
      · `/` `\\` 是**路径分隔**，不净化会把日志写到别处（或有意外层目录）；
      · 结尾的空格与点：Windows 建得出文件但**再访问不了**（资源管理器会吃掉）；
      · 超长项目名会把 `logs\\` 下的绝对路径顶到 260 上限，写日志直接失败。
    
        English:
    Sanitize the project name into a short segment that is **safe to concatenate into a filename**.
    If sanitization yields empty, return an empty string.
        ⚠ All three are things that will actually break:
          · `/` `\\` are **path separators**; failing to sanitize writes the log elsewhere (or creates unexpected directory levels);
          · Trailing spaces and dots: Windows can create the file but **can no longer access it** (Explorer eats them);
          · An overly long project name pushes the absolute path under `logs\\` up to the 260 limit, and writing the log fails outright.
    """
    s = _BAD_IN_FILENAME.sub('', str(name or '').strip())
    s = s.strip(' .')                       # Windows：结尾的点/空格会"消失"
    # [EN] Windows: trailing dots/spaces will "disappear"
    return s[:_MAX_NAME_CHARS]


def log_basename(kind: str, token: str, stamp: str) -> str:
    """日志文件名（**唯一出处**：主日志与对话日志都从这儿拼）。

    形如 `nws_<书名>_2026_10_07_01_23_11.log`；
    `kind='dialogue'` → `nws_<书名>_dialogue_2026_10_07_01_23_11.log`；
    `token` 为空（还没开卷）→ `nws_2026_10_07_01_23_11.log`。
    
        English:
    Log filename (**single source of truth**: both the main log and the dialogue log are
    concatenated from here).
        Of the form `nws_<book name>_2026_10_07_01_23_11.log`;
        `kind='dialogue'` → `nws_<book name>_dialogue_2026_10_07_01_23_11.log`;
        `token` is empty (project not yet opened) → `nws_2026_10_07_01_23_11.log`.
    """
    parts = ['nws']
    if token:
        parts.append(token)
    if kind:
        parts.append(kind)
    parts.append(stamp)
    return '_'.join(parts) + '.log'


def _unique_path(path: Path, *, keep: Path | None = None) -> Path:
    """同名文件已存在时加序号（`…_2.log`）。`keep` = "本来就该在那儿的那个"。
        English:
    If a file with the same name already exists, append a sequence number (`…_2.log`). `keep` = "the
    one that was supposed to be there in the first place".
    """
    if not path.exists() or (keep is not None and path == keep):
        return path
    for i in range(2, 100):
        cand = path.with_name(f'{path.stem}_{i}.log')
        if not cand.exists():
            return cand
    return path


def log_dir() -> Path:
    """当前日志目录。优先级：

        **`.env` 里显式设的 `LOG_DIR`（非空） > `NWS_LOG_DIR` 环境变量 > 程序目录 `logs/`**

    写成函数而不是常量，是因为它现在可配（「天机 · 日志」页里能改、能浏览）。
    改这项要重启 —— 日志器在启动时一次性建好，运行中换目录没有意义。

    ★★ `NWS_LOG_DIR` 是**测试钩子**，不是给用户调的旋钮（所以**不进设置界面**）。
    它是为什么来的（2026-10-06，做"并行回归"时踩到）：
    当时日志文件名只精确到**分钟**（`nws-dialogue-%Y-%m-%d-%H-%M.log`），
    于是**同一分钟内启动的多个进程会写同一个文件**。
    串行跑没事；一并行，"往日志里数条目"的判据当场错乱 ——
    `tools/verify_dialogue_log.py` 的 B 组就是这么红的：

        [FAIL] 发生过的每一次 LLM 请求都落了盘（对数） — 日志 +16 / 实际 9

    它自己只发了 9 次请求，但另外两个同时跑的实例往**同一个文件**里也写了，
    所以数出来 +16。这不是产品坏了，是**两个测试进程在抢同一个共享资源**。
    并行回归器于是给每个脚本一个自己的日志目录
    （`logs/_parallel/<脚本名>/`），`NWS_LOG_DIR` 就是那个入口。

    ⚠⚠ **为什么 `NWS_LOG_DIR` 排在 `.env` 的 `LOG_DIR` 之后，而不是最前**
    （"环境变量覆盖配置"更符合常规直觉，但那样会**打坏一条真判据**）：

        `tools/verify_config_sweep.py` 的 C6 判据**故意**把 `LOG_DIR` 指到一个
        临时目录，再造一份 90 天前的旧日志，看启动时清不清它。
        如果环境变量压过 `LOG_DIR`，日志器就会被指到别处、
        临时目录里那份旧日志没人清 → **C6 在并行跑时必红**。

    所以这里的语义是「**替代默认值**」，不是「强制覆盖」：
    `.env` 里显式写的照样说了算（那是"我就要它写这儿"），
    环境变量只在没人指定时起作用（回归器的情形）。一行之差，但差别是
    "测试钩子"还是"抢产品的方向盘"。

    ⚠ **精度到秒之后，当初那个"同分钟撞名"的老问题已经不存在了**
    （2026-10-07 用户要求日志名带项目名时顺带改的，见 `log_basename()`）——
    但 `NWS_LOG_DIR` **仍然留着**，理由变了，写在这儿免得以后被当成废钩子删掉：
      ① 并行回归器一次拉 6~8 个进程，**同一秒**起仍有极小概率撞上；
      ② 更实际的是**可读性**：`logs/_parallel/<脚本名>/` 让"这支脚本写了什么"
         一眼翻得到，不必在一堆 `nws_*.log` 里按时间猜。

    ⚠⚠ **为什么 `NWS_LOG_DIR` 排在 `.env` 的 `LOG_DIR` 之后，而不是最前**
    （"环境变量覆盖配置"更符合常规直觉，但那样会**打坏一条真判据**）：

        `tools/verify_config_sweep.py` 的 C6 判据**故意**把 `LOG_DIR` 指到一个
        临时目录，再造一份 90 天前的旧日志，看启动时清不清它。
        如果环境变量压过 `LOG_DIR`，日志器就会被指到别处、
        临时目录里那份旧日志没人清 → **C6 在并行跑时必红**。

    所以这里的语义是「**替代默认值**」，不是「**强制覆盖**」：
    `.env` 里显式写的照样说了算（那是"我就要它写这儿"），
    环境变量只在没人指定时起作用（回归器的情形）。一行之差，但差别是
    "测试钩子"还是"抢产品的方向盘"。
    
        English:
    Current log directory. Priority:
            **Explicitly set `LOG_DIR` in `.env` (non-empty) > `NWS_LOG_DIR` environment variable > program directory `logs/`**
        Written as a function rather than a constant because it is now configurable (can be changed and browsed in the "Tianji · Logs" page).
        Changing this item requires a restart — the logger is built once at startup, and swapping directories at runtime is meaningless.
        ★★ `NWS_LOG_DIR` is a **test hook**, not a knob for users to turn (so it **does not appear in the settings UI**).
        Why it exists (2026-10-06, encountered while doing "parallel regression"):
        At the time the log filename was only precise to the **minute** (`nws-dialogue-%Y-%m-%d-%H-%M.log`),
        so **multiple processes started within the same minute would write to the same file**.
        Running serially was fine; once parallelized, the criterion "count entries in the log" went haywire on the spot —
        this is exactly how group B of `tools/verify_dialogue_log.py` turned red:
            [FAIL] Every LLM request that occurred was persisted (count check) — log +16 / actual 9
        It only issued 9 requests itself, but the other two instances running at the same time also wrote into **the same file**,
        so the count came out as +16. This is not the product breaking; it is **two test processes fighting over the same shared resource**.
        The parallel regression runner therefore gives each script its own log directory
        (`logs/_parallel/<script name>/`), and `NWS_LOG_DIR` is that entry point.
        ⚠⚠ **Why `NWS_LOG_DIR` ranks after `.env`'s `LOG_DIR` rather than first**
        ("environment variables override config" fits conventional intuition better, but that would **break a real criterion**):
            Criterion C6 of `tools/verify_config_sweep.py` **deliberately** points `LOG_DIR` at a
            temp directory, then creates an old log from 90 days ago, to see whether it gets cleaned at startup.
            If the environment variable overrode `LOG_DIR`, the logger would be pointed elsewhere,
            and that old log in the temp directory would be cleaned by nobody → **C6 goes red when run in parallel**.
        So the semantics here are "**substitute the default value**", not "forced override":
        what is explicitly written in `.env` still has the final say (that is "I want it written here"),
        and the environment variable only takes effect when nobody specified it (the regression runner's case). One line's difference, but the difference is
        "test hook" versus "grabbing the product's steering wheel".
        ⚠ **After precision went to seconds, that old "same-minute name collision" problem no longer exists**
        (changed in passing on 2026-10-07 when the user requested log names carry the project name, see `log_basename()`) —
        but `NWS_LOG_DIR` **is still kept**, for a different reason, written here so it will not be deleted as a dead hook later:
          ① The parallel regression runner launches 6~8 processes at once; there is still a tiny chance of collision **within the same second**;
          ② More practically, **readability**: `logs/_parallel/<script name>/` lets you find "what this script wrote"
             at a glance, without guessing by time among a pile of `nws_*.log`.
        ⚠⚠ **Why `NWS_LOG_DIR` comes after `.env`'s `LOG_DIR`, not first**
        ("environment variables override config" is more in line with common intuition, but that would **break a real criterion**):
            C6 in `tools/verify_config_sweep.py` **deliberately** points `LOG_DIR` at a
            temp directory, then creates an old log from 90 days ago, to see whether startup clears it.
            If the environment variable overrides `LOG_DIR`, the logger gets pointed elsewhere,
            and nobody clears that old log in the temp directory → **C6 always fails under parallel runs**.
        So the semantics here are "**substitute the default**", not "**force override**":
        What is explicitly written in `.env` still wins (that is "I want it written here"),
        and the environment variable only takes effect when nobody specifies it (the regression case). One line's difference, but the difference is
        "test hook" versus "grabbing the product's steering wheel".
    """
    try:
        from config import CFG
        p = (CFG.s('LOG_DIR') or '').strip()
        if p:
            return Path(p).expanduser()
    except Exception:                                       # noqa: BLE001
        pass
    _env = (os.environ.get('NWS_LOG_DIR') or '').strip()
    if _env:
        return Path(_env).expanduser()
    return DEFAULT_LOG_DIR


# 兼容旧引用：拿到的永远是**默认**目录。要拿"当前生效的"，请调 `log_dir()`。
# [EN] Compat for old references: what you get is always the **default** directory. To get the
# [EN] "currently effective" one, call `log_dir()`.
LOG_DIR = DEFAULT_LOG_DIR

# PII 模式（需要隐藏的敏感信息）
# [EN] PII patterns (sensitive info to hide)
PII_PATTERNS = [
    # API Key
    (r'(sk-[a-zA-Z0-9]{8})[a-zA-Z0-9]{32,}', r'\1***'),
    (r'(api[_-]?key[=:]\s*)([^\s]+)', r'\1***'),
    # 密码
    # [EN] Password
    (r'(password[=:]\s*)([^\s]+)', r'\1***'),
    (r'(passwd[=:]\s*)([^\s]+)', r'\1***'),
    # Token
    (r'(token[=:]\s*)([^\s]+)', r'\1***'),
    # 邮箱
    # [EN] Email
    (r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r'***@\2'),
    # IP 地址（保留网段）
    # [EN] IP address (keep subnet)
    (r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.)\d{1,3}', r'\1***'),
    # 文件路径中的用户名
    # [EN] Username in file paths
    (r'(C:\\Users\\)([^\\]+)', r'\1***'),
    (r'(/home/)([^/]+)', r'\1***'),
]


class PIIFilter:
    """PII 信息过滤器。
        English:
    PII information filter.
    """

    @staticmethod
    def sanitize(text: str) -> str:
        """隐藏敏感信息。
                English:
        Hide sensitive information.
        """
        for pattern, replacement in PII_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


class NWSFormatter(logging.Formatter):
    """自定义日志格式器。
        English:
    Custom log formatter.
    """

    def __init__(self):
        super().__init__(
            fmt='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录。
                English:
        Format log records.
        """
        # 基础格式
        # [EN] Base format
        msg = super().format(record)

        # 添加额外信息
        # [EN] Add extra info
        extras = []

        # 添加类型标签
        # [EN] Add type tag
        if hasattr(record, 'category'):
            extras.append(f"[{record.category}]")

        # 添加函数名和行号（调试模式）
        # [EN] Add function name and line number (debug mode)
        if hasattr(record, 'show_location') and record.show_location:
            extras.append(f"({record.funcName}:{record.lineno})")

        # 组合
        # [EN] Combined
        if extras:
            msg = f"{msg} {' '.join(extras)}"

        # PII 处理
        # [EN] PII handling
        msg = PIIFilter.sanitize(msg)

        return msg


class DialogueLogger:
    """对话日志：**每一次 LLM 交换的全文** ＋ 界面里的「作者 ↔ AI」对话。

    为什么要和主日志分开（而不是都塞进同一个 `nws_*.log`）
    -------------------------------------------------------
    · 主日志是**程序流水**：阶段、配置、错误，一行一件事，几百行看完；
    · 对话日志一条动辄几千字（提示词里带着整份设定集），塞进主日志会把流水**淹掉**；
    · 但对话恰恰是作者最想复盘的东西 ——「AI 到底收到了什么、回了什么」。
    两个文件都在 `log_dir()` 下，主日志启动时会写一行指向它，不会找不到。

    ⚠ 与 `DEBUG_MODE` / `SAVE_RAW_LOGS` **无关**：那两项是排障开关
    （`llm_calls.jsonl` 默认只存前 200 字），而「对话要留档全文」是**默认行为**
    —— 2026-10-05 用户明确要求：「所有的对话也需要放到日志里」。

    ⚠ 正文**不做 PII 脱敏**：那是作者自己的小说文本，脱敏会把内容改花
    （`PIIFilter` 仍照常作用于主日志）。
    
        English:
    Conversation log: **the full text of every LLM exchange** + the "author ↔ AI" conversation in
    the UI.
        Why separate it from the main log (instead of cramming both into the same `nws_*.log`)
        -------------------------------------------------------
        · The main log is the **program flow**: stages, config, errors, one thing per line, readable in a few hundred lines;
        · A single conversation log entry is often thousands of characters (the prompt carries the entire setting bible), and cramming it into the main log would **drown out** the flow;
        · But the conversation is exactly what the author most wants to review — "what exactly did the AI receive, and what did it reply".
        Both files are under `log_dir()`; the main log writes a line pointing to it at startup, so it won't be lost.
        ⚠ Unrelated to `DEBUG_MODE` / `SAVE_RAW_LOGS`: those two are troubleshooting switches
        (`llm_calls.jsonl` only stores the first 200 characters by default), whereas "conversations must be archived in full" is **default behavior**
        —— On 2026-10-05 the user explicitly requested: "all conversations also need to go into the log".
        ⚠ The body text is **not PII-redacted**: that is the author's own novel text, and redaction would mangle the content
        (`PIIFilter` still applies to the main log as usual).
    """

    MAX_BYTES = 16 * 1024 * 1024      # 超过就轮转一份 `.1`：长跑别把磁盘写满
    # [EN] Rotate a `.1` once exceeded: don't fill the disk on long runs
    BAR = '─' * 78

    def __init__(self, directory: Path, stamp: str):
        self.dir = directory
        self.stamp = stamp
        # 文件名与主日志**同一套拼法**（`log_basename()`）：
        #   ① 同前缀 → `cleanup_old_logs()` 按 `nws*.log` 清理时能被一起轮掉；
        #   ② 同时间戳 → 一眼看出"这两个文件是同一次运行"。
        # [EN] Filename uses the **same scheme** as the main log (`log_basename()`):
        # [EN] ① Same prefix -> gets rotated together when `cleanup_old_logs()` cleans by `nws*.log`;
        # [EN] ② Same timestamp -> at a glance you can see "these two files are from the same run".
        self.token = ''
        self.path = directory / log_basename('dialogue', '', stamp)
        self._opened = False
        self._warned = False        # 写失败只抱怨一次，别刷屏
        # [EN] Complain only once on write failure, don't spam

    def set_project(self, token: str) -> None:
        """开卷后把对话日志**改名**带上项目名（与主日志同一时刻、同一个名字段）。

        还没有内容（懒创建没触发）时只改路径；已经有内容就连文件一起搬。
        **搬不动就留着原名**并如实说一声 —— 不假装改了。
        
                English:
        After opening a project, **rename** the conversation log to include the project name (same
        moment and same name field as the main log).
                When there is no content yet (lazy creation not triggered), only change the path; if there is already content, move the file too.
                **If it cannot be moved, keep the original name** and say so truthfully —— do not pretend it was renamed.
        """
        if token == self.token:
            return
        new = self.dir / log_basename('dialogue', token, self.stamp)
        if self.path.exists() and self.path != new:
            try:
                new = _unique_path(new, keep=self.path)
                self.path.rename(new)
            except OSError as e:
                logging.getLogger('nws').warning(
                    '对话日志改名失败（继续用原名 %s）：%s', self.path.name, e)
                return
        self.path = new
        self.token = token

    def _ensure(self) -> bool:
        """懒创建：本次运行一句话都没说，就别留个空文件。
                English:
        Lazy creation: if not a single word was said during this run, do not leave an empty file.
        """
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            if not self._opened:
                fresh = not self.path.exists()
                with open(self.path, 'a', encoding='utf-8') as f:
                    if fresh:
                        f.write(f'小说世界AI模拟 · 对话日志\n'
                                f'开始时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
                                f'说明：这里记**每一次 LLM 交换的全文**（请求的每条消息、'
                                f'响应的完整文本）以及界面里「作者 ↔ AI」的每一句话。\n'
                                f'主日志（程序流水）是同目录、同时间戳的那个文件'
                                f'（`nws_*.log`），两者互不覆盖。\n')
                self._opened = True
            return True
        except OSError as e:
            # **别静默失败**：写不进去（磁盘满 / 目录只读）要吭一声，
            # 否则"所有对话都留档"这个承诺会悄悄地不成立。
            # [EN] **Don't fail silently**: if it can't be written (disk full / directory read-only), say
            # [EN] something,
            # [EN] otherwise the promise "all conversations are archived" will quietly become false.
            if not self._warned:
                self._warned = True
                logging.getLogger('nws').warning(
                    '对话日志写入失败（%s），本次运行的对话不会留档：%s', self.path, e)
            return False

    def _roll(self) -> None:
        try:
            if self.path.exists() and self.path.stat().st_size > self.MAX_BYTES:
                bak = self.path.with_name(self.path.stem + '.1.log')
                if bak.exists():
                    bak.unlink()
                self.path.rename(bak)
                self._opened = False
                self._ensure()
        except OSError:
            pass

    def write(self, title: str, body: str = '', meta: str = '') -> None:
        """写一段。`title` 一行、`body` 原样全文。
                English:
        Write a segment. `title` on one line, `body` as-is in full.
        """
        if not self._ensure():
            return
        try:
            self._roll()
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            head = f'[{ts}] {title}' + (f' · {meta}' if meta else '')
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(f'\n{self.BAR}\n{head}\n{self.BAR}\n')
                if body:
                    f.write(str(body).rstrip() + '\n')
        except OSError:
            pass

    def line(self, text: str) -> None:
        """写一行流水（界面上那几行日志的镜像）。

        和 `write()` 的区别：**不套小节框**。界面的日志本来就是"一行一件事"，
        每行再套三条横线（框 + 标题 + 框）会把文件撑成三倍长、还难读。
        顺带把界面自己带的时间戳（`[23:16:06] `）掐掉 —— 这里由日志统一盖全时间。
        
                English:
        Write a line of flow (mirror of those log lines in the UI).
                Difference from `write()`: **no section box is wrapped around it**. The UI log is inherently "one thing per line",
                and wrapping each line in three horizontal rules (box + title + box) would triple the file length and make it harder to read.
                Also strip the timestamp the UI carries itself (`[23:16:06] `) —— here the log stamps the full time uniformly.
        """
        if not self._ensure():
            return
        try:
            self._roll()
            txt = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', str(text))
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(f'[{ts}] {txt}\n')
        except OSError:
            pass

    def turn(self, role: str, text: str) -> None:
        """界面里的一句对话（作者打的 / AI 回的）。
                English:
        A conversation line in the UI (typed by the author / replied by the AI).
        """
        label = {'user': '作者 → AI', 'ai': 'AI → 作者',
                 'assistant': 'AI → 作者'}.get(role, role)
        self.write(f'对话 · {label}', text)


class NWSLogger:
    """NWS 日志管理器。
        English:
    NWS log manager.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if NWSLogger._initialized:
            return
        NWSLogger._initialized = True

        # 创建日志目录（`.env` 的 LOG_DIR 优先，见 `log_dir()`）
        # [EN] Create the log directory (`.env`'s LOG_DIR takes priority, see `log_dir()`)
        _dir = log_dir()
        _dir.mkdir(parents=True, exist_ok=True)
        self.log_dir = _dir

        # 生成日志文件名。
        #   ⚠ **精确到秒**（2026-10-07 起）：用户要求日志名带项目名，例子给的是
        #     `nws_<书名>_2026_10_07_01_23_11.log`（六段）。顺带把当初那个
        #     "同分钟两个实例写同一个文件"的老问题也解决了（见 `log_dir()`）。
        #   这时**还不知道项目名**（要等用户开卷），所以先按无名建，
        #   知道名字之后再 `set_project()` 改名 —— 一个文件从头到尾，不分裂成两份。
        # [EN] Generate the log filename.
        # [EN] ⚠ **Down to the second** (as of 2026-10-07): the user asked for the log name to include the
        # [EN] project name, and the example given was
        # [EN] `nws_<book title>_2026_10_07_01_23_11.log` (six segments). Incidentally this also solved the old
        # [EN] problem of
        # [EN] "two instances in the same minute writing to the same file" (see `log_dir()`).
        # [EN] At this point the **project name isn't known yet** (it waits for the user to open a book), so
        # [EN] create it unnamed first,
        # [EN] and after the name is known call `set_project()` to rename -- one file from start to finish, not
        # [EN] split into two.
        timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
        self.stamp = timestamp
        self.project_token = ''
        self.log_file = _dir / log_basename('', '', timestamp)
        # 对话日志（同目录、同时间戳；**懒创建**，没对话就不产生空文件）
        # [EN] Dialogue log (same directory, same timestamp; **lazily created**, no empty file if there's no
        # [EN] dialogue)
        self.dialogue = DialogueLogger(_dir, timestamp)

        # ★ `LOG_ROTATE_DAYS`（以前零读取）：**启动时**清一次太旧的日志。
        #   以前这个清理函数只有测试会调，长跑的人日志目录会一直涨。
        #   `0` = 不限（默认），所以默认行为跟以前一模一样。
        # [EN] ★ `LOG_ROTATE_DAYS` (previously never read): clean out too-old logs once **at startup**.
        # [EN] Previously this cleanup function was only called by tests, and long-running users' log
        # [EN] directories kept growing.
        # [EN] `0` = unlimited (default), so the default behavior is exactly as before.
        try:
            from config import CFG as _CFG
            _days = _CFG.i("LOG_ROTATE_DAYS")
            if _days > 0:
                self.cleanup_old_logs(_days)
        except Exception as e:                                  # noqa: BLE001
            self.warning(f"日志轮转失败: {e}", category="system")

        # 配置根日志器
        # [EN] Configure the root logger
        self.root_logger = logging.getLogger('nws')
        self.root_logger.setLevel(logging.DEBUG)

        # 清除现有处理器
        # [EN] Clear existing handlers
        self.root_logger.handlers.clear()

        # ⚠ **已知事实**（2026-10-08 写《使用说明》的「日志」一章时查出来的）：
        #   `LOG_LEVEL` 这一项在「天机 · 输出与日志」页上摆着、也会被写回 `.env`，
        #   但**这里从来没读过它** —— 主日志固定记 DEBUG 及以上。
        #   所以那一项目前是个**哑旋钮**：按它调完，日志一行不会变。
        # [EN] ⚠ **Known fact** (found on 2026-10-08 while writing the "Logging" section of the Usage Guide):
        # [EN] The `LOG_LEVEL` item is displayed on the "Tianji · Output & Logging" page and also written back
        # [EN] to `.env`,
        # [EN] but **it has never been read here** -- the main log records DEBUG and above, fixed.
        # [EN] So that item is currently a **dead knob**: adjust it and not a single log line changes.
        #
        #   没有顺手接上，是因为**接上就是一次行为变更**：`.env` 里现写着
        #   `LOG_LEVEL=INFO`，一接线主日志会立刻少掉约八成行数
        #   （实测一份真实日志：1592 行里 1351 行是 DEBUG），
        #   而排障与不少判据都靠那些行。要接就得当成一件事来做（改默认值 + 跑回归），
        #   不该混在"写文档"这一趟里。**文档里如实写着它不生效**（见使用说明 §12.7）。
        # [EN] It wasn't hooked up on the side because **hooking it up is a behavior change**: `.env` currently
        # [EN] says
        # [EN] `LOG_LEVEL=INFO`, and wiring it up would immediately cut roughly 80% of the main log's lines
        # [EN] (measured on a real log: of 1592 lines, 1351 are DEBUG),
        # [EN] and troubleshooting and quite a few criteria rely on those lines. Hooking it up must be treated
        # [EN] as its own task (change default + run regression),
        # [EN] and shouldn't be mixed into this "writing docs" pass. **The docs truthfully state it doesn't
        # [EN] take effect** (see Usage Guide §12.7).
        #
        # 文件处理器（详细日志）
        # [EN] File handler (detailed log)
        file_handler = logging.FileHandler(
            self.log_file,
            encoding='utf-8',
            mode='a'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(NWSFormatter())
        self.root_logger.addHandler(file_handler)
        # ★ 存一份引用：`set_project()` 要**先关掉它**才改得动文件名
        #   （Windows 上被打开的文件既不能改名也不能移动）。
        # [EN] ★ Keep a reference: `set_project()` must **close it first** before it can change the filename
        # [EN] (on Windows an open file can neither be renamed nor moved).
        self._file_handler = file_handler

        # 控制台处理器（简化日志）
        # [EN] Console handler (simplified log)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(NWSFormatter())
        self.root_logger.addHandler(console_handler)

        # ★ 控制台横幅（**只打控制台，不写日志文件**）：
        #   双击图标后先弹出一个黑窗口，很多用户会以为出错了、顺手把它关掉 ——
        #   而关掉这个窗口就等于结束程序（窗口和进程同生共死）。
        #   所以在这里明说一句：这窗口是正常的、别关。
        #   用 `print` 而不是 `logger.info`，正是为了**只出现在屏幕上**、
        #   不进日志文件（它是给看屏幕的人看的，不是诊断信息）。
        # [EN] ★ Console banner (**console only, not written to the log file**):
        # [EN] After double-clicking the icon, a black window pops up first, and many users will think
        # [EN] something went wrong and close it --
        # [EN] and closing that window is equivalent to ending the program (window and process live and die
        # [EN] together).
        # [EN] So say it clearly here: this window is normal, don't close it.
        # [EN] Using `print` instead of `logger.info` is precisely to make it **appear only on screen** and
        # [EN] not enter the log file (it's for people looking at the screen, not diagnostic info).
        if sys.stdout is not None:
            try:
                print()
                print("  本窗口是程序的运行日志窗口，属正常现象。  /  This console "
                      "window is the program's log window; it is normal.")
                print("  运行期间请保持它打开（关闭窗口会直接结束程序）。  /  Keep it "
                      "open while running (closing it ends the program).")
                print()
                sys.stdout.flush()
            except Exception:                               # noqa: BLE001
                pass

        # 记录启动信息（中英双语：英文**附在中文后面**，见下面「对话日志」那条的说明）
        # [EN] Record startup info (bilingual Chinese-English: English **appended after the Chinese**, see the
        # [EN] note on the "dialogue log" item below)
        self.info("NWS 日志系统启动  /  Logging system started", category="system")
        self.info(f"日志文件（Log file）: {self.log_file}", category="system")
        # 对话日志是**懒创建**的，但路径现在就能说清楚 —— 找不到文件不代表没这回事
        # [EN] The dialogue log is **lazily created**, but the path can be stated clearly right now -- not
        # [EN] finding the file doesn't mean it doesn't exist
        #
        # ⚠ 消息里**必须保留「对话日志」这四个字**：`tools/verify_dialogue_log.py`
        #   用 `'对话日志' in 主日志内容` 断言「启动时写明了对话日志路径」。
        #   所以英文是**追加**，不是替换 —— 下面几条同理。
        # [EN] ⚠ The message **must retain the four characters "对话日志"**: `tools/verify_dialogue_log.py`
        # [EN] asserts "the dialogue log path is written at startup" using `'对话日志' in main log content`.
        # [EN] So the English is **appended**, not a replacement -- same for the items below.
        self.info(f"对话日志（LLM 请求/响应全文 + 界面对话）/ Dialogue log "
                  f"(full LLM requests/responses + UI chat): {self.dialogue.path}",
                  category="system")
        self.info(f"Python 版本（Python version）: {sys.version}", category="system")
        self.info(f"工作目录（Working dir）: {os.getcwd()}", category="system")

    def set_project(self, name: Any) -> Path:
        """开卷之后，把日志文件名**补上项目名**。

        改前：`nws_2026_10_07_01_23_11.log`
        改后：`nws_<书名>_2026_10_07_01_23_11.log`

        用户原话（2026-10-07）：「在 nws 后面加 `_` 然后项目名然后 `_` 接原来的
        日志名字 比如 `nws_<书名>_2026_10_07_01_23_11.log`」。
        一本小说跑很多轮，日志目录里堆满 `nws_*.log` 时，
        **光看文件名认不出哪份是哪本书的** —— 这就是要改名的理由。

        ★ 为什么是**改名**而不是"一开始就叫对"：日志器在**程序启动**时就建好了
          （而且启动日志本身就要写进文件），那时用户还没开卷、项目名未知。
          所以先按无名建，知道名字之后再搬 —— 一个文件从头到尾，
          **不会分裂成"无名前半截 + 有名后半截"两份**（那才是真的难查）。

        ★ 顺序很讲究：**先关掉文件处理器 → 改名 → 再重开**。
          Windows 上被打开的文件既不能改名也不能移动；直接 `Path.rename()`
          会抛 `PermissionError`，而"日志静悄悄停在旧文件里"这种事没人会发现。
          所以这里失败要**大声说**（`warning` + 继续用旧名）。

        ★ 改名是**幂等**的：同名项目重复开卷直接返回（不白搬一次）。
        
                English:
        After opening a project, **append the project name** to the log filename.
                Before: `nws_2026_10_07_01_23_11.log`
                After: `nws_<book title>_2026_10_07_01_23_11.log`
                User's original words (2026-10-07): "add `_` after nws, then the project name, then `_` followed by the original
                log name, e.g. `nws_<book title>_2026_10_07_01_23_11.log`".
                One novel runs many rounds, and when the log directory is stuffed with `nws_*.log`,
                **you can't tell which file belongs to which book just from the filename** - that is the reason for renaming.
                ★ Why **rename** instead of "just name it right from the start": the logger is created at **program startup**
                  (and the startup log itself must be written to the file), at which point the user hasn't opened the book yet and the project name is unknown.
                  So create it unnamed first, and move it once the name is known - one file from start to finish,
                  **it won't split into an "unnamed first half + named second half"** (that would be truly hard to trace).
                ★ The order matters a lot: **close the file handler first -> rename -> then reopen**.
                  On Windows, an open file can neither be renamed nor moved; calling `Path.rename()` directly
                  throws `PermissionError`, and "the log quietly stops in the old file" is something nobody would notice.
                  So on failure here, **say it loudly** (`warning` + keep using the old name).
                ★ Renaming is **idempotent**: opening the same-named project again just returns (no wasted move).
        """
        token = safe_filename_token(name)
        if token == self.project_token:
            return self.log_file

        old = self.log_file
        new = _unique_path(old.with_name(log_basename('', token, self.stamp)),
                           keep=old)

        # ── ① 关掉当前的 file handler（不关就搬不动）──
        # [EN] ── ① Close the current file handler (can't move it without closing) ──
        h = getattr(self, '_file_handler', None)
        closed = False
        if h is not None:
            try:
                h.flush()
                h.close()
                closed = True
            except Exception:                                   # noqa: BLE001
                closed = False

        # ── ② 搬文件（搬不动就留在原名，别假装改过）──
        # [EN] ── ② Move the file (if it can't be moved, leave it under the original name, don't pretend it was
        # [EN] changed) ──
        moved = old
        if closed and old.exists() and old != new:
            try:
                old.rename(new)
                moved = new
            except OSError as e:
                self.warning(f"日志改名失败（继续用原名 {old.name}）：{e}",
                             category="system")

        # ── ③ 处理器重新指到（改名后的）文件上 ──
        # [EN] ── ③ Repoint the handler at the (renamed) file ──
        try:
            nh = logging.FileHandler(moved, encoding='utf-8', mode='a')
            nh.setLevel(logging.DEBUG)
            nh.setFormatter(NWSFormatter())
            handlers = self.root_logger.handlers
            if h is not None and h in handlers:
                # **就地替换**，保持 handlers 顺序（文件处理器应在控制台之前）
                # [EN] **Replace in place**, keeping the handlers order (the file handler should come before the
                # [EN] console)
                handlers[handlers.index(h)] = nh
            else:
                self.root_logger.addHandler(nh)
            self._file_handler = nh
        except OSError as e:
            self.warning(f"日志处理器改写失败：{e}", category="system")

        self.log_file = moved
        self.project_token = token
        # 对话日志跟着改（两个文件同一套命名段，一眼看得出是同一次运行）
        # [EN] Rename the dialogue log along with it (both files share one naming scheme, so at a glance you
        # [EN] can tell it's the same run)
        try:
            self.dialogue.set_project(token)
        except Exception as e:                                  # noqa: BLE001
            self.warning(f"对话日志改名失败：{e}", category="system")

        if moved != old:
            # 这条**写进新文件**（处理器已经切过去了），所以"打开日志看到的第一行
            # 就说明了这份文件是谁的" —— 不用回翻去猜。
            # [EN] This item **is written to the new file** (the handler has already switched over), so "the first
            # [EN] line you see when opening the log
            # [EN] This makes clear whose file this is" — no need to scroll back and guess.
            self.info(f"日志已改名（本次运行属于《{token}》）  /  Log renamed: "
                      f"{moved.name}", category="system")
            self.info(f"日志文件（Log file）: {self.log_file}", category="system")
            self.info(f"对话日志（LLM 请求/响应全文 + 界面对话）/ Dialogue log "
                      f"(full LLM requests/responses + UI chat): {self.dialogue.path}",
                      category="system")
        return moved

    def get_logger(self, name: str) -> logging.Logger:
        """获取子日志器。
                English:
        Get the child logger.
        """
        return self.root_logger.getChild(name)

    def _log(self, level: int, msg: str, category: str = "general",
             exc_info: bool = False, **kwargs):
        """内部日志方法。

        ★★★ 2026-10-10 修：`exc_info=True` 必须**在这里**换成真的 `sys.exc_info()`。
        标准库是在 `logging.Logger._log()` 里做这一步的：

            if exc_info:
                if isinstance(exc_info, BaseException):
                    exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
                elif not isinstance(exc_info, tuple):
                    exc_info = sys.exc_info()

        而本方法是**自己造 `LogRecord`** 然后 `root_logger.handle(record)` —— 绕过了
        那一步，于是 `record.exc_info` 一直是布尔 `True`，格式化器一取
        `record.exc_info[0]` 就 `TypeError: 'bool' object is not subscriptable`；
        logging 内部只打一行 `--- Logging error ---` 到 stderr，**整条记录被丢掉**。

        实测（`developers/_probe_log_exception.py`）：调一次 `log_exception`，
        **日志文件里找不到那一行**。
        ⇒ 后果比"少一行日志"严重：全项目约 100 处 `log_exception(...)` 记的都是
          **真错误**（生成失败、写盘失败、界面崩了…），它们**一条都没落盘** ——
          而日志正是这个项目"出事时全靠它"的东西。
        ⚠ 这条与"`log.warning` 正常"不冲突：`warning` 不带 `exc_info`，所以能落盘。
        
                English:
        Internal logging method.
                ★★★ 2026-10-10 fix: `exc_info=True` must be converted to real `sys.exc_info()` **here**.
                The standard library does this step in `logging.Logger._log()`:
                    if exc_info:
                        if isinstance(exc_info, BaseException):
                            exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
                        elif not isinstance(exc_info, tuple):
                            exc_info = sys.exc_info()
                But this method **builds the `LogRecord` itself** and then calls `root_logger.handle(record)` - bypassing
                that step, so `record.exc_info` stays boolean `True`, and as soon as the formatter accesses
                `record.exc_info[0]` it's `TypeError: 'bool' object is not subscriptable`;
                logging internally just prints one `--- Logging error ---` line to stderr, and **the whole record is dropped**.
                Measured (`developers/_probe_log_exception.py`): call `log_exception` once,
                **that line cannot be found in the log file**.
                => The consequence is worse than "one missing log line": roughly 100 `log_exception(...)` calls across the project all record
                  **real errors** (generation failure, disk write failure, UI crash...), and **not a single one of them reaches disk** -
                  yet logging is exactly what this project "relies on entirely when things go wrong".
                ⚠ This doesn't conflict with "`log.warning` works fine": `warning` doesn't carry `exc_info`, so it reaches disk.
        """
        # ⚠ 换掉 `exc_info` 之后要用换过的值造 record（下面 makeRecord 用它）
        # [EN] ⚠ After replacing `exc_info`, use the replaced value to build the record (makeRecord below uses
        # [EN] it)
        if exc_info:
            if isinstance(exc_info, BaseException):
                exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
            elif not isinstance(exc_info, tuple):
                exc_info = sys.exc_info()
        # 创建日志记录
        # [EN] Create log record
        record = self.root_logger.makeRecord(
            name='nws',
            level=level,
            fn='',
            lno=0,
            msg=msg,
            args=(),
            exc_info=exc_info,
        )

        # 添加额外字段
        # [EN] Add extra fields
        record.category = category
        record.show_location = kwargs.get('show_location', False)

        # 处理
        # [EN] Process
        self.root_logger.handle(record)

    def debug(self, msg: str, category: str = "general", **kwargs):
        """调试日志。
                English:
        Debug log.
        """
        self._log(logging.DEBUG, msg, category, **kwargs)

    def info(self, msg: str, category: str = "general", **kwargs):
        """信息日志。
                English:
        Info log.
        """
        self._log(logging.INFO, msg, category, **kwargs)

    def warning(self, msg: str, category: str = "general", **kwargs):
        """警告日志。
                English:
        Warning log.
        """
        self._log(logging.WARNING, msg, category, **kwargs)

    def error(self, msg: str, category: str = "general", exc_info: bool = True, **kwargs):
        """错误日志。
                English:
        Error log.
        """
        self._log(logging.ERROR, msg, category, exc_info=exc_info, **kwargs)

    def critical(self, msg: str, category: str = "general", exc_info: bool = True, **kwargs):
        """严重错误日志。
                English:
        Critical log.
        """
        self._log(logging.CRITICAL, msg, category, exc_info=exc_info, **kwargs)

    def exception(self, msg: str, category: str = "general", **kwargs):
        """异常日志（自动捕获当前异常）。
                English:
        Exception log (automatically captures the current exception).
        """
        self._log(logging.ERROR, msg, category, exc_info=True, **kwargs)

    def ui_action(self, action: str, details: str = ""):
        """UI 操作日志。
                English:
        UI operation log.
        """
        msg = f"UI 操作: {action}"
        if details:
            msg += f" - {details}"
        self.info(msg, category="ui")

    def config_change(self, key: str, old_value: str, new_value: str):
        """配置变更日志。
                English:
        Config change log.
        """
        # PII 处理
        # [EN] PII handling
        old_sanitized = PIIFilter.sanitize(old_value)
        new_sanitized = PIIFilter.sanitize(new_value)
        self.info(
            f"配置变更: {key} = {old_sanitized} -> {new_sanitized}",
            category="config"
        )

    def function_call(self, func_name: str, args: str = ""):
        """函数调用日志。
                English:
        Function call log.
        """
        msg = f"函数调用: {func_name}"
        if args:
            msg += f"({args})"
        self.debug(msg, category="function", show_location=True)

    def cleanup_old_logs(self, max_age_days: int = 30):
        """清理旧日志文件。

        ★ 模式是 **`nws*.log`**，不是 `nws-*.log` —— 刻意同时覆盖两种名字：
        2026-10-07 起新名是 `nws_<书名>_2026_10_07_01_23_11.log`（下划线），
        而用户 `logs/` 里还躺着改名之前那一批 `nws-<旧式日期>.log`（连字符）。
        只匹配新式的写法会让**老日志永远清不掉**（长跑的人目录一直涨），
        而这恰恰是这个函数存在的原因。
        
                English:
        Clean up old log files.
                ★ The pattern is **`nws*.log`**, not `nws-*.log` - deliberately covering both names at once:
                from 2026-10-07 the new name is `nws_<book title>_2026_10_07_01_23_11.log` (underscore),
                while the user's `logs/` still contains the batch from before renaming, `nws-<old-style date>.log` (hyphen).
                Matching only the new style would make **old logs impossible to ever clean up** (the directory keeps growing for long runners),
                and that is precisely why this function exists.
        """
        try:
            cutoff = datetime.now().timestamp() - (max_age_days * 86400)
            for log_file in log_dir().glob('nws*.log'):
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
                    self.info(f"删除旧日志: {log_file.name}", category="system")
        except Exception as e:
            self.warning(f"清理旧日志失败: {e}", category="system")


# 全局日志实例
# [EN] Global logger instance
nws_logger = NWSLogger()


def get_logger(name: str) -> logging.Logger:
    """获取日志器。
        English:
    Get a logger.
    """
    return nws_logger.get_logger(name)


def log_ui_action(action: str, details: str = ""):
    """记录 UI 操作。
        English:
    Record UI operations.
    """
    nws_logger.ui_action(action, details)


def log_config_change(key: str, old_value: str, new_value: str):
    """记录配置变更。
        English:
    Record config changes.
    """
    nws_logger.config_change(key, old_value, new_value)


def log_function_call(func_name: str, args: str = ""):
    """记录函数调用。
        English:
    Record function calls.
    """
    nws_logger.function_call(func_name, args)


def dialogue_logger():
    """对话日志句柄（`.path` 是文件路径）。
        English:
    Conversation log handle (`.path` is the file path).
    """
    return nws_logger.dialogue


def set_project_log(name: str) -> Path:
    """把当前日志文件名补上项目名（**开卷时调一次**）。

    `nws_2026_10_07_01_23_11.log` → `nws_<书名>_2026_10_07_01_23_11.log`

    调用点只有一个：`gui/app_flet.py::_activate_project()`（开卷完成 / 拾卷打开
    都走它）—— 那正是"项目名第一次确定"的时刻。改名失败不影响使用
    （日志继续写在原名里，`warning` 里有据可查）。
    
        English:
    Append the project name to the current log filename (**call once when opening a project**).
        `nws_2026_10_07_01_23_11.log` → `nws_<book title>_2026_10_07_01_23_11.log`
        There is only one call site: `gui/app_flet.py::_activate_project()` (project opening complete / resuming
        both go through it) —— that is exactly "the moment the project name is first determined". Rename failure does not affect usage
        (the log keeps writing under the original name, and there is a record in `warning`).
    """
    return nws_logger.set_project(name)


def log_dialogue(title: str, body: str = "", meta: str = "") -> None:
    """往对话日志里写一段（全文，不截断）。
        English:
    Write a segment to the conversation log (full text, no truncation).
    """
    nws_logger.dialogue.write(title, body, meta)


def log_dialogue_line(text: str) -> None:
    """往对话日志里写一行流水（界面日志的镜像）。
        English:
    Write a line of flow to the conversation log (mirror of the UI log).
    """
    nws_logger.dialogue.line(text)


def log_dialogue_turn(role: str, text: str) -> None:
    """记一句界面里的对话（role = user / ai）。
        English:
    Log a conversation line from the UI (role = user / ai).
    """
    nws_logger.dialogue.turn(role, text)


def log_exception(msg: str, category: str = "general"):
    """记录异常。
        English:
    Record exceptions.
    """
    nws_logger.exception(msg, category)


# 清理旧日志
# [EN] Clean up old logs
nws_logger.cleanup_old_logs()