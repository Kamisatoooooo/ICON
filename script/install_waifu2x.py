"""Explicit, project-local installer for the official Windows x64 waifu2x release."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import sys
import tempfile
import threading
import zipfile
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

REPO = 'nihui/waifu2x-ncnn-vulkan'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
TOOLS = Path(__file__).resolve().parent / 'tools'
DEST = TOOLS / 'waifu2x'
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024


def request(url: str):
    return urlopen(Request(url, headers={'User-Agent': 'ICON-local-installer',
                                        'Accept': 'application/vnd.github+json' if url == API else 'application/octet-stream'}), timeout=60)


def release_asset() -> tuple[dict, dict]:
    with request(API) as response:
        release = json.load(response)
    matches = [asset for asset in release.get('assets', [])
               if asset['name'].lower().endswith('-windows.zip')]
    if len(matches) != 1:
        raise RuntimeError('无法唯一确定官方 Windows 发行包，请手动安装并指定 --waifu2x。')
    asset = matches[0]
    if not asset['browser_download_url'].startswith(f'https://github.com/{REPO}/releases/download/'):
        raise RuntimeError('下载地址不属于预期官方仓库，已停止。')
    if asset.get('size', 0) > MAX_ARCHIVE:
        raise RuntimeError('发行包超过下载大小限制，已停止。')
    return release, asset


def extract(archive: Path, folder: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) > 10000 or sum(item.file_size for item in entries) > MAX_EXPANDED:
            raise RuntimeError('压缩包内容超过安全限制。')
        seen = set()
        for item in entries:
            path = PurePosixPath(item.filename)
            target = (folder / item.filename).resolve()
            if (path.is_absolute() or '..' in path.parts or ':' in item.filename
                    or chr(92) in item.filename or not target.is_relative_to(folder.resolve())
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise RuntimeError(f'压缩包包含不安全路径: {item.filename}')
            key = str(target).casefold()
            if key in seen:
                raise RuntimeError(f'压缩包包含重复路径: {item.filename}')
            seen.add(key)
        bundle.extractall(folder)
    programs = list(folder.rglob('waifu2x-ncnn-vulkan.exe'))
    if len(programs) != 1:
        raise RuntimeError('发行包未包含唯一的 waifu2x 程序。')
    root = programs[0].parent
    models = root / 'models-cunet'
    if not list(models.glob('*.param')) or not list(models.glob('*.bin')):
        raise RuntimeError('发行包缺少配套 models-cunet 模型，安装未完成。')
    return root


class InstallCancelled(Exception):
    pass


def check_cancel(stop: threading.Event | None) -> None:
    if stop and stop.is_set():
        raise InstallCancelled('安装已停止')


def main(argv: list[str] | None = None, log=print, stop: threading.Event | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check_cancel(stop)
    if args not in ([], ['--check']):
        raise RuntimeError('用法: npm run setup:ai（或追加 -- --check 仅检查官方发行包）')
    if sys.platform != 'win32' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise RuntimeError('自动安装目前仅支持 Windows x64；其他系统请手动安装并指定 --waifu2x。')
    if DEST.exists():
        exe = DEST / 'waifu2x-ncnn-vulkan.exe'
        if exe.is_file() and list((DEST / 'models-cunet').glob('*.param')) and list((DEST / 'models-cunet').glob('*.bin')):
            log(f'AI 工具已安装，直接复用: {exe}')
            return 0
        raise RuntimeError(f'安装目录已存在但不完整，为保护文件不会覆盖: {DEST}')
    log("正在查询官方 AI 发行包…", flush=True)
    release, asset = release_asset()
    check_cancel(stop)
    log(f'官方发行版: {release["tag_name"]} / {asset["name"]}', flush=True)
    if '--check' in args:
        log('检查完成，未下载或安装。')
        return 0
    TOOLS.mkdir(parents=True, exist_ok=True)
    lock = TOOLS / '.waifu2x-install.lock'
    with lock.open('x'):
        pass
    try:
        # Temporary cleanup is confined to a newly created directory under script/tools.
        with tempfile.TemporaryDirectory(prefix='.waifu2x-', dir=TOOLS) as temp:
            folder = Path(temp).resolve()
            if not folder.is_relative_to(TOOLS.resolve()):
                raise RuntimeError('临时安装目录越界。')
            archive = folder / 'release.zip'
            digest = hashlib.sha256()
            count = 0
            log('正在下载官方程序及模型…', flush=True)
            last_percent = -1
            check_cancel(stop)
            with request(asset['browser_download_url']) as response, archive.open('xb') as output:
                while chunk := response.read(1024 * 1024):
                    check_cancel(stop)
                    count += len(chunk)
                    if count > MAX_ARCHIVE:
                        raise RuntimeError('下载超过大小限制。')
                    digest.update(chunk)
                    output.write(chunk)
                    total = asset.get('size', 0)
                    percent = min(100, count * 100 // total) if total else 0
                    if percent // 10 > last_percent:
                        last_percent = percent // 10
                        log(f'下载进度 {percent}%（{count // 1024} KiB）', flush=True)
            if asset.get('size') and count != asset['size']:
                raise RuntimeError('下载大小不匹配，安装已停止。')
            expected = asset.get('digest')
            if expected and expected != 'sha256:' + digest.hexdigest():
                raise RuntimeError('官方 SHA256 校验失败，安装已停止。')
            if not expected:
                log('提示：此官方发行包未提供 SHA256 摘要；将验证 ZIP 完整性及程序、模型文件。', flush=True)
            check_cancel(stop)
            log('下载完成，正在校验和解压…', flush=True)
            extracted = folder / 'extracted'
            extracted.mkdir()
            root = extract(archive, extracted)
            check_cancel(stop)
            (root / 'icon-install.json').write_text(json.dumps({
                'repository': REPO, 'version': release['tag_name'],
                'asset': asset['name'], 'sha256': digest.hexdigest(),
            }, indent=2), encoding='utf-8')
            # Same-volume rename; never overwrite an existing installation.
            if DEST.exists():
                raise RuntimeError('安装目录已出现，停止以避免覆盖。')
            root.rename(DEST)
        log(f'AI 工具安装完成: {DEST}')
        log('无需配置路径。重新打开 npm start，或在现有 TUI 中直接重试 /run。')
        log('已安装不代表设备驱动可用；实际推理仍依赖对应 CPU / Vulkan 支持。')
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except InstallCancelled:
        print("安装已停止。", file=sys.stderr)
        raise SystemExit(130)
    except KeyboardInterrupt:
        print('安装已取消，可重新运行 npm run setup:ai。', file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f'AI 安装失败: {exc}。可重试 npm run setup:ai，或手动安装并指定程序路径。', file=sys.stderr)
        raise SystemExit(2)
