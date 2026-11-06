# -*- coding: utf-8 -*-
"""Flet 运行时跨平台检查模块。

功能：
- 检测 Flet 运行时是否已安装
- 自动识别当前操作系统和架构
- 从本地 packages 文件夹查找对应平台的安装包
- 自动解压安装
- 缺少安装包时自动下载

支持平台：
- Windows (x86_64)
- macOS (Universal: Intel + Apple Silicon)
- Ubuntu 20.04/22.04/24.04 (x86_64 / ARM64)
- Debian 10/12 (x86_64 / ARM64)

用法：
    from flet_setup import ensure_flet_ready
    ensure_flet_ready()  # 确保 Flet 运行时就绪

English:
Flet runtime cross-platform check module.
Features:
- Detect whether Flet runtime is installed
- Automatically identify current OS and architecture
- Find the corresponding platform installation package from the local packages folder
- Automatically extract and install
- Automatically download when installation package is missing
Supported platforms:
- Windows (x86_64)
- macOS (Universal: Intel + Apple Silicon)
- Ubuntu 20.04/22.04/24.04 (x86_64 / ARM64)
- Debian 10/12 (x86_64 / ARM64)
Usage:
    from flet_setup import ensure_flet_ready
    ensure_flet_ready()  # Ensure Flet runtime is ready
"""
from __future__ import annotations

import os
import sys
import platform
import zipfile
import tarfile
import urllib.request
from pathlib import Path

# Flet 版本
# [EN] Flet version
FLET_VERSION = "1.0.3"

# 本地 packages 目录
# [EN] Local packages directory
PACKAGES_DIR = Path(__file__).resolve().parent / 'packages'

# Flet 运行时安装目录
# [EN] Flet runtime installation directory
FLET_CLIENT_DIR = Path.home() / '.flet' / 'client'

# GitHub 下载地址
# [EN] GitHub download URL
FLET_DOWNLOAD_URL = f"https://github.com/flet-dev/flet/releases/download/v{FLET_VERSION}"


def get_platform_info() -> tuple[str, str]:
    """获取当前平台信息。

    Returns:
        (os_name, arch) 例如 ('windows', 'amd64'), ('macos', 'arm64'), ('ubuntu24.04', 'amd64')
    
        English:
    Get current platform info.
        Returns:
            (os_name, arch) e.g. ('windows', 'amd64'), ('macos', 'arm64'), ('ubuntu24.04', 'amd64')
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    # 规范化架构名称
    # [EN] Normalize architecture name
    if machine in ('x86_64', 'amd64'):
        arch = 'amd64'
    elif machine in ('aarch64', 'arm64'):
        arch = 'arm64'
    else:
        arch = machine

    if system == 'windows':
        return 'windows', arch
    elif system == 'darwin':
        return 'macos', arch
    elif system == 'linux':
        # 检测 Linux 发行版
        # [EN] Detect Linux distribution
        try:
            # 读取 os-release 文件
            # [EN] Read os-release file
            os_release = {}
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        os_release[key] = value.strip('"')

            distro_id = os_release.get('ID', '').lower()
            version = os_release.get('VERSION_ID', '')

            if distro_id == 'ubuntu':
                return f'ubuntu{version}', arch
            elif distro_id == 'debian':
                return f'debian{version}', arch
            else:
                # 回退到通用 Linux
                # [EN] Fall back to generic Linux
                return f'linux-{distro_id}', arch
        except:
            return 'linux', arch
    else:
        return system, arch


def get_package_filename() -> str | None:
    """获取当前平台对应的安装包文件名。
        English:
    Get the installation package filename for the current platform.
    """
    os_name, arch = get_platform_info()

    # 平台到文件名的映射
    # [EN] Platform to filename mapping
    platform_map = {
        ('windows', 'amd64'): 'flet-windows.zip',
        ('macos', 'arm64'): 'flet-macos.tar.gz',
        ('macos', 'amd64'): 'flet-macos.tar.gz',  # macOS 通用二进制
        # [EN] macOS universal binary
        ('ubuntu24.04', 'amd64'): 'flet-linux-ubuntu24.04-amd64.tar.gz',
        ('ubuntu24.04', 'arm64'): 'flet-linux-ubuntu24.04-arm64.tar.gz',
        ('ubuntu22.04', 'amd64'): 'flet-linux-ubuntu22.04-amd64.tar.gz',
        ('ubuntu22.04', 'arm64'): 'flet-linux-ubuntu22.04-arm64.tar.gz',
        ('ubuntu20.04', 'amd64'): 'flet-linux-ubuntu20.04-amd64.tar.gz',
        ('ubuntu20.04', 'arm64'): 'flet-linux-ubuntu20.04-arm64.tar.gz',
        ('debian12', 'amd64'): 'flet-linux-debian12-amd64.tar.gz',
        ('debian12', 'arm64'): 'flet-linux-debian12-arm64.tar.gz',
        ('debian10', 'amd64'): 'flet-linux-debian10-amd64.tar.gz',
        ('debian10', 'arm64'): 'flet-linux-debian10-arm64.tar.gz',
    }

    return platform_map.get((os_name, arch))


def get_flet_client_path() -> Path:
    """获取 Flet 客户端目录路径。
        English:
    Get the Flet client directory path.
    """
    # Flet 1.0 的目录命名规则
    # [EN] Flet 1.0 directory naming rules
    if platform.system() == 'Windows':
        return FLET_CLIENT_DIR / f'flet-desktop-full-{FLET_VERSION}'
    elif platform.system() == 'Darwin':
        return FLET_CLIENT_DIR / f'flet-desktop-full-{FLET_VERSION}'
    else:
        return FLET_CLIENT_DIR / f'flet-desktop-full-{FLET_VERSION}'


def is_flet_installed() -> bool:
    """检查 Flet 运行时是否已安装。
        English:
    Check whether Flet runtime is installed.
    """
    client_path = get_flet_client_path()
    return client_path.exists()


def find_local_package() -> Path | None:
    """从本地 packages 文件夹查找当前平台的安装包。
        English:
    Find the current platform's installation package from the local packages folder.
    """
    if not PACKAGES_DIR.exists():
        return None

    filename = get_package_filename()
    if not filename:
        return None

    package_path = PACKAGES_DIR / filename
    if package_path.exists():
        return package_path

    return None


def download_current_platform() -> Path | None:
    """下载当前平台的安装包到 packages 目录。

    Returns:
        下载成功返回文件路径，失败返回 None
    
        English:
    Download the current platform's installation package to the packages directory.
        Returns:
            Returns file path on download success, None on failure
    """
    filename = get_package_filename()
    if not filename:
        return None

    # 确保 packages 目录存在
    # [EN] Ensure packages directory exists
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    dest = PACKAGES_DIR / filename
    url = f"https://github.com/flet-dev/flet/releases/download/v{FLET_VERSION}/{filename}"

    print(f"下载 / Downloading {filename}...")
    print(f"  URL: {url[:80]}...")

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=300) as response:
            total = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            with open(dest, 'wb') as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        mb = downloaded / (1024 * 1024)
                        total_mb = total / (1024 * 1024)
                        print(f"\r  进度 / progress: {pct}% ({mb:.1f}MB/{total_mb:.1f}MB)",
                      end='', flush=True)
            print()
            print(f"[OK] 下载完成 / Download finished: {dest}")
            return dest
    except Exception as e:
        print(f"\n[X] 下载失败 / Download failed: {e}")
        # 清理失败的文件
        # [EN] Clean up failed files
        if dest.exists():
            dest.unlink()
        return None


def install_from_package(package_path: Path) -> bool:
    """从本地安装包安装 Flet 运行时。
        English:
    Install Flet runtime from local installation package.
    """
    print(f"\n{'='*50}")
    print(f"安装 Flet v{FLET_VERSION} 桌面运行时  /  Installing the Flet desktop runtime")
    print(f"{'='*50}")
    print(f"安装包 / Package: {package_path.name}")

    # 创建目标目录
    # [EN] Create target directory
    FLET_CLIENT_DIR.mkdir(parents=True, exist_ok=True)

    # 解压
    # [EN] Extract
    print(f"解压到 / Extracting to: {FLET_CLIENT_DIR}")
    try:
        if package_path.suffix == '.zip':
            with zipfile.ZipFile(package_path, 'r') as zip_ref:
                zip_ref.extractall(FLET_CLIENT_DIR)
        elif package_path.suffix == '.gz':
            with tarfile.open(package_path, 'r:gz') as tar_ref:
                tar_ref.extractall(FLET_CLIENT_DIR)
        else:
            print(f"[!] 不支持的压缩格式 / Unsupported archive type: {package_path.suffix}")
            return False

        print("[OK] 解压完成  /  Extraction complete")
        return True
    except Exception as e:
        print(f"[!] 解压失败 / Extraction failed: {e}")
        return False


def ensure_flet_ready() -> bool:
    """确保 Flet 运行时已就绪。

    Returns:
        True 如果就绪，False 如果失败
    
        English:
    Ensure Flet runtime is ready.
        Returns:
            True if ready, False if failed
    """
    # 检查是否已安装
    # [EN] Check if already installed
    if is_flet_installed():
        print("[OK] Flet 运行时已就绪  /  Flet runtime is ready")
        return True

    # 获取平台信息
    # [EN] Get platform info
    os_name, arch = get_platform_info()
    print(f"首次运行，需要安装 Flet 桌面运行时...  /  First run: the Flet desktop runtime must be installed...")
    print(f"当前平台 / Current platform: {os_name} ({arch})")

    # 查找本地安装包
    # [EN] Find local installation package
    package = find_local_package()

    if package:
        print(f"[OK] 找到本地安装包 / Found local package: {package.name}")
        return install_from_package(package)

    # 本地没有，尝试自动下载
    # [EN] Not found locally, try auto-download
    print(f"本地未找到安装包，尝试自动下载...  /  No local package found; trying to download it...")
    package = download_current_platform()

    if package:
        return install_from_package(package)

    # 下载也失败
    # [EN] Download also failed
    filename = get_package_filename()
    print(f"\n[!] 自动下载失败  /  Automatic download failed")
    if filename:
        print(f"需要 / Need: {filename}")
        print(f"请手动下载并放到以下目录  /  Download it manually and put it in:")
    else:
        print(f"不支持的平台 / Unsupported platform: {os_name} ({arch})")
        print(f"请手动下载 Flet 桌面运行时  /  Please download the Flet desktop runtime manually")
    print(f"  {PACKAGES_DIR}")
    return False


def setup_flet_env():
    """设置 Flet 环境变量（如果需要）。
        English:
    Set Flet environment variables (if needed).
    """
    return ensure_flet_ready()


if __name__ == '__main__':
    # 测试
    # [EN] Test
    print("测试 Flet 运行时检查...")
    print(f"平台: {platform.system()} {platform.machine()}")
    print(f"平台信息: {get_platform_info()}")
    print(f"安装包文件名: {get_package_filename()}")
    print(f"已安装: {is_flet_installed()}")
    print(f"客户端路径: {get_flet_client_path()}")

    print(f"\n检查本地安装包...")
    print(f"packages 目录: {PACKAGES_DIR}")
    package = find_local_package()
    if package:
        print(f"[OK] 找到安装包: {package}")
    else:
        print(f"[X] 未找到安装包")