# -*- coding: utf-8 -*-
"""下载 Flet 全平台桌面运行时（并行下载，实时进度）。

用法：
    python download_flet_all.py           # 下载所有平台（5线程并行）
    python download_flet_all.py --win     # 只下载 Windows
    python download_flet_all.py --mac     # 只下载 macOS
    python download_flet_all.py --linux   # 只下载 Linux
    python download_flet_all.py --threads 3  # 指定线程数

English:
Download Flet desktop runtimes for all platforms (parallel download, real-time progress).
Usage:
    python download_flet_all.py           # Download all platforms (5 threads in parallel)
    python download_flet_all.py --win     # Only download Windows
    python download_flet_all.py --mac     # Only download macOS
    python download_flet_all.py --linux   # Only download Linux
    python download_flet_all.py --threads 3  # Specify thread count
"""
import os
import sys
import time
from pathlib import Path
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

FLET_VERSION = "1.0.3"
BASE_URL = f"https://github.com/flet-dev/flet/releases/download/v{FLET_VERSION}"
DEFAULT_THREADS = 5

# 平台配置
# [EN] Platform config
PLATFORMS = {
    'windows': {'file': 'flet-windows.zip', 'desc': 'Windows', 'group': 'win'},
    'macos': {'file': 'flet-macos.tar.gz', 'desc': 'macOS', 'group': 'mac'},
    'ubuntu24.04-amd64': {'file': 'flet-linux-ubuntu24.04-amd64.tar.gz', 'desc': 'Ubuntu24.04-x64', 'group': 'linux'},
    'ubuntu24.04-arm64': {'file': 'flet-linux-ubuntu24.04-arm64.tar.gz', 'desc': 'Ubuntu24.04-ARM', 'group': 'linux'},
    'ubuntu22.04-amd64': {'file': 'flet-linux-ubuntu22.04-amd64.tar.gz', 'desc': 'Ubuntu22.04-x64', 'group': 'linux'},
    'ubuntu22.04-arm64': {'file': 'flet-linux-ubuntu22.04-arm64.tar.gz', 'desc': 'Ubuntu22.04-ARM', 'group': 'linux'},
    'ubuntu20.04-amd64': {'file': 'flet-linux-ubuntu20.04-amd64.tar.gz', 'desc': 'Ubuntu20.04-x64', 'group': 'linux'},
    'ubuntu20.04-arm64': {'file': 'flet-linux-ubuntu20.04-arm64.tar.gz', 'desc': 'Ubuntu20.04-ARM', 'group': 'linux'},
    'debian12-amd64': {'file': 'flet-linux-debian12-amd64.tar.gz', 'desc': 'Debian12-x64', 'group': 'linux'},
    'debian12-arm64': {'file': 'flet-linux-debian12-arm64.tar.gz', 'desc': 'Debian12-ARM', 'group': 'linux'},
}


class DownloadTask:
    """单个下载任务的状态。
        English:
    Status of a single download task.
    """
    def __init__(self, task_id: int, desc: str, url: str, dest: Path):
        self.task_id = task_id
        self.desc = desc
        self.url = url
        self.dest = dest
        self.status = 'pending'  # pending, downloading, done, error
        self.percent = 0.0
        self.speed = 0.0
        self.downloaded = 0
        self.total = 0
        self.error = None
        self.start_time = None
        self.lock = threading.Lock()

    def update(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def get_status(self):
        with self.lock:
            return {
                'desc': self.desc,
                'status': self.status,
                'percent': self.percent,
                'speed': self.speed,
                'downloaded': self.downloaded,
                'total': self.total,
            }


def download_task(task: DownloadTask) -> DownloadTask:
    """执行下载任务。
        English:
    Execute download task.
    """
    task.update(status='downloading', start_time=time.time())

    try:
        req = urllib.request.Request(task.url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=300) as response:
            total = int(response.headers.get('Content-Length', 0))
            task.update(total=total)
            downloaded = 0
            last_update = time.time()

            with open(task.dest, 'wb') as f:
                while True:
                    chunk = response.read(32768)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_update >= 0.3:
                        elapsed = now - task.start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        percent = (downloaded * 100 / total) if total > 0 else 0
                        task.update(percent=percent, speed=speed, downloaded=downloaded)
                        last_update = now

        elapsed = time.time() - task.start_time
        speed = downloaded / elapsed if elapsed > 0 else 0
        task.update(status='done', percent=100, speed=speed, downloaded=downloaded)

    except Exception as e:
        task.update(status='error', error=str(e))
        if task.dest.exists():
            task.dest.unlink()

    return task


def format_size(bytes_size):
    """格式化文件大小。
        English:
    Format file size.
    """
    if bytes_size < 1024:
        return f"{bytes_size}B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size/1024:.1f}KB"
    else:
        return f"{bytes_size/(1024*1024):.1f}MB"


def format_speed(bytes_per_sec):
    """格式化速度。
        English:
    Format speed.
    """
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f}B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec/1024:.1f}KB/s"
    else:
        return f"{bytes_per_sec/(1024*1024):.1f}MB/s"


def print_status(tasks: list[DownloadTask]):
    """打印所有任务状态。
        English:
    Print status of all tasks.
    """
    lines = []
    for task in tasks:
        status = task.get_status()
        desc = status['desc'].ljust(18)

        if status['status'] == 'done':
            speed = format_speed(status['speed'])
            size = format_size(status['downloaded'])
            lines.append(f"  ✓ {desc} 完成  {size} @ {speed}")
        elif status['status'] == 'error':
            lines.append(f"  ✗ {desc} 失败")
        elif status['status'] == 'downloading':
            pct = status['percent']
            speed = format_speed(status['speed'])
            downloaded = format_size(status['downloaded'])
            total = format_size(status['total']) if status['total'] > 0 else '?'

            bar_len = 20
            filled = int(bar_len * pct / 100)
            bar = '█' * filled + '░' * (bar_len - filled)

            lines.append(f"  ↓ {desc} {bar} {pct:5.1f}%  {downloaded}/{total}  {speed}")
        else:
            lines.append(f"  · {desc} 等待中...")

    print("\n".join(lines))


def main():
    packages_dir = Path(__file__).resolve().parent / 'packages'
    packages_dir.mkdir(exist_ok=True)

    # 解析参数
    # [EN] Parse arguments
    args = sys.argv[1:]
    download_all = '--win' not in args and '--mac' not in args and '--linux' not in args
    download_win = '--win' in args or download_all
    download_mac = '--mac' in args or download_all
    download_linux = '--linux' in args or download_all

    # 解析线程数
    # [EN] Parse thread count
    threads = DEFAULT_THREADS
    if '--threads' in args:
        try:
            idx = args.index('--threads')
            threads = int(args[idx + 1])
        except (IndexError, ValueError):
            pass

    print(f"{'='*60}")
    print(f"Flet v{FLET_VERSION} 全平台桌面运行时下载")
    print(f"{'='*60}")
    print(f"下载目录: {packages_dir}")
    print(f"并行线程: {threads}")
    print()

    # 筛选要下载的平台
    # [EN] Filter platforms to download
    tasks = []
    skipped = 0
    for key, info in PLATFORMS.items():
        group = info['group']
        if (group == 'win' and download_win) or \
           (group == 'mac' and download_mac) or \
           (group == 'linux' and download_linux):
            file_name = info['file']
            dest = packages_dir / file_name
            if dest.exists():
                print(f"  ✓ {info['desc']}: 已存在，跳过")
                skipped += 1
            else:
                url = f"{BASE_URL}/{file_name}"
                task = DownloadTask(len(tasks), info['desc'], url, dest)
                tasks.append(task)

    if not tasks:
        print(f"\n所有文件已存在或无需下载")
        return 0

    print(f"\n开始下载 {len(tasks)} 个平台...")
    print()

    # 并行下载
    # [EN] Parallel download
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        # 提交所有任务
        # [EN] Submit all tasks
        futures = [executor.submit(download_task, task) for task in tasks]

        # 定期打印状态
        # [EN] Periodically print status
        while not all(f.done() for f in futures):
            # 移动光标到开始位置
            # [EN] Move cursor to start position
            if tasks:
                print(f"\033[{len(tasks)}A", end='')
            print_status(tasks)
            time.sleep(0.5)

        # 最终状态
        # [EN] Final status
        if tasks:
            print(f"\033[{len(tasks)}A", end='')
        print_status(tasks)

        # 等待所有完成
        # [EN] Wait for all to complete
        for future in as_completed(futures):
            future.result()

    # 统计结果
    # [EN] Aggregate results
    total_time = time.time() - start_time
    success = sum(1 for t in tasks if t.get_status()['status'] == 'done')
    failed = sum(1 for t in tasks if t.get_status()['status'] == 'error')

    print(f"\n{'='*60}")
    print(f"下载完成:")
    print(f"  成功: {success}")
    print(f"  失败: {failed}")
    print(f"  跳过: {skipped}")
    print(f"  耗时: {total_time:.1f}秒")
    print(f"文件位置: {packages_dir}")
    print(f"{'='*60}")

    if failed > 0:
        print("\n失败的下载:")
        for task in tasks:
            if task.get_status()['status'] == 'error':
                print(f"  - {task.desc}: {task.error}")

    return 1 if failed > 0 else 0


if __name__ == '__main__':
    sys.exit(main())