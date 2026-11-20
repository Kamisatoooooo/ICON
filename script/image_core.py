"""Image normalization engine shared by the CLI and TUI (Python 3.10+)."""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.ico', '.svg', '.tif', '.tiff', '.avif'}


@dataclass
class Config:
    source: Path
    output: Path | None = None
    recursive: bool = False
    upscale: str = 'lanczos'
    waifu2x: str | None = None
    device: str = 'auto'
    model_dir: Path | None = None
    fallback_lanczos: bool = False
    size: int = 144
    dpi: int = 96
    timeout: float = 180

    def validate(self) -> None:
        self.source = self.source.expanduser().resolve()
        if not self.source.exists():
            raise ValueError(f'输入不存在: {self.source}')
        if not (self.source.is_file() or self.source.is_dir()):
            raise ValueError('输入必须是文件或文件夹')
        base = self.source if self.source.is_dir() else self.source.parent
        self.output = (self.output or base / 'normalized').expanduser().resolve()
        if self.output == base or self.output == self.source:
            raise ValueError('输出目录不能与输入目录相同，请使用独立目录以保护原图')
        if self.output.exists() and not self.output.is_dir():
            raise ValueError('输出路径已经存在，且不是文件夹')
        if self.upscale not in {'lanczos', 'waifu2x'}:
            raise ValueError('未知放大方式')
        if self.size < 1 or self.dpi < 1 or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError('尺寸、DPI 和超时时间必须为正数')
        if self.device not in {'auto', 'cpu'}:
            try:
                if int(self.device) < 0:
                    raise ValueError()
            except ValueError:
                raise ValueError('设备必须为 auto、cpu 或非负 GPU 编号') from None
        if self.model_dir is not None:
            self.model_dir = self.model_dir.expanduser().resolve()
            if not self.model_dir.is_dir():
                raise ValueError(f'模型目录不存在: {self.model_dir}')


@dataclass
class Result:
    source: str
    status: str
    output: str | None = None
    input_format: str | None = None
    original_size: tuple[int, int] | None = None
    content_size: tuple[int, int] | None = None
    method: str | None = None
    notes: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class Batch:
    results: list[Result]
    report: Path | None
    cancelled: bool = False


class Cancelled(Exception):
    pass


def discover(config: Config) -> list[Path]:
    """Snapshot inputs before writing; do not follow links or scan the output tree."""
    if config.source.is_file():
        return [config.source]
    found = []
    for current, dirs, files in os.walk(config.source, followlinks=False):
        parent = Path(current)
        dirs[:] = sorted(d for d in dirs if not d.startswith('.')
                         and not (parent / d).is_symlink()
                         and not getattr(parent / d, 'is_junction', lambda: False)()
                         and (parent / d).resolve() != config.output)
        if parent.resolve() == config.output:
            dirs[:] = []
            continue
        for name in sorted(files):
            path = parent / name
            if path.suffix.lower() in EXTENSIONS and not path.is_symlink():
                found.append(path)
        if not config.recursive:
            break
    return sorted(found, key=lambda p: str(p).casefold())


def fit_size(width: int, height: int, target: int) -> tuple[int, int]:
    if width < 1 or height < 1:
        raise ValueError('图片宽高必须大于零')
    ratio = target / max(width, height)
    return max(1, round(width * ratio)), max(1, round(height * ratio))


def decode(path: Path, target: int) -> tuple[Image.Image, str, list[str]]:
    # Sniff actual content, including SVG files with misleading suffixes.
    with path.open('rb') as stream:
        head = stream.read(8192).lstrip(b'\xef\xbb\xbf \r\n\t')
    if b'<svg' in head.lower():
        try:
            import resvg_py
        except ImportError as exc:
            raise RuntimeError('SVG 转换需要 resvg-py，请安装 script/requirements.txt') from exc
        # Render vectors directly into a square viewport; SVG aspect ratio is preserved.
        raw = resvg_py.svg_to_bytes(svg_path=str(path), width=target, height=target)
        with Image.open(io.BytesIO(raw)) as rendered:
            return rendered.convert('RGBA'), 'SVG', ['矢量直接渲染；不经过 AI 超分']
    with Image.open(path) as image:
        kind = image.format or 'unknown'
        notes = []
        if kind == 'ICO':
            largest = max(image.ico.sizes(), key=lambda s: (s[0] * s[1], s[0], s[1]))
            return image.ico.getimage(largest).convert('RGBA'), kind, [f'选择 ICO 最大图层 {largest}']
        if getattr(image, 'n_frames', 1) > 1:
            notes.append('多帧图片仅取第 0 帧（APNG 如有默认静态图则取默认图）')
        image.seek(0)
        oriented = ImageOps.exif_transpose(image)
        # Convert tagged RGB/CMYK images to sRGB where possible, preserving alpha.
        if image.info.get('icc_profile'):
            try:
                from PIL import ImageCms
                profile = ImageCms.ImageCmsProfile(io.BytesIO(image.info['icc_profile']))
                mode = 'CMYK' if oriented.mode == 'CMYK' else 'RGB'
                rgb = ImageCms.profileToProfile(oriented.convert(mode), profile,
                                               ImageCms.createProfile('sRGB'), outputMode='RGB')
                rgb.putalpha(oriented.convert('RGBA').getchannel('A'))
                return rgb, kind, notes
            except Exception as exc:
                notes.append(f'ICC 转换失败，按原始颜色转换: {exc}')
        return oriented.convert('RGBA'), kind, notes


def executable(config: Config) -> Path:
    name = config.waifu2x or os.environ.get('WAIFU2X_BIN') or 'waifu2x-ncnn-vulkan'
    expanded = str(Path(name).expanduser())
    resolved = shutil.which(expanded)
    candidate = Path(resolved) if resolved else Path(expanded)
    if not candidate.is_file():
        raise RuntimeError('未找到 waifu2x-ncnn-vulkan。请使用 --waifu2x 指定程序路径，或设置 WAIFU2X_BIN / PATH')
    return candidate.resolve()


def waifu_upscale(image: Image.Image, target: tuple[int, int], config: Config,
                   stop: threading.Event | None) -> Image.Image:
    exe = executable(config)
    alpha = image.getchannel('A')
    # Keep straight RGB for semitransparent pixels (do not apply alpha twice).
    # Fill only fully invisible RGB with white to avoid arbitrary hidden colors.
    current = Image.new('RGB', image.size, 'white')
    visible = alpha.point(lambda value: 255 if value else 0)
    current.paste(image.convert('RGB'), (0, 0), visible)
    with tempfile.TemporaryDirectory(prefix='icon-waifu2x-') as temp:
        folder = Path(temp)
        step = 0
        while current.width < target[0] or current.height < target[1]:
            if stop and stop.is_set():
                raise Cancelled()
            src, dst = folder / f'in-{step}.png', folder / f'out-{step}.png'
            current.save(src, format='PNG')
            command = [str(exe), '-i', str(src), '-o', str(dst), '-n', '-1', '-s', '2', '-f', 'png']
            if config.device != 'auto':
                command += ['-g', '-1' if config.device == 'cpu' else config.device]
            if config.model_dir:
                command += ['-m', str(config.model_dir)]
            try:
                run = subprocess.run(command, cwd=exe.parent, capture_output=True,
                                     timeout=config.timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f'waifu2x 单轮运行超过 {config.timeout:g} 秒') from exc
            if run.returncode != 0 or not dst.is_file():
                detail = (run.stderr + run.stdout).decode('utf-8', errors='replace')[-2000:]
                raise RuntimeError(f'waifu2x 失败（退出码 {run.returncode}）: {detail}')
            with Image.open(dst) as enhanced:
                next_image = enhanced.convert('RGB')
            if next_image.width != current.width * 2 or next_image.height != current.height * 2:
                raise RuntimeError('waifu2x 未产生预期的 2 倍输出，停止处理')
            current = next_image
            step += 1
    final = current.resize(target, Image.Resampling.LANCZOS).convert('RGBA')
    final.putalpha(alpha.resize(target, Image.Resampling.LANCZOS))
    return final


def reserve_path(folder: Path, name: str) -> tuple[Path, object]:
    """Exclusive creation prevents overwrites, including case-insensitive collisions."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = Path(name).stem
    for index in range(1, 100000):
        path = folder / (f'{stem}.png' if index == 1 else f'{stem}__{index}.png')
        try:
            return path, path.open('xb')
        except FileExistsError:
            continue
    raise RuntimeError('同名文件过多，无法分配输出名称')


def verify(path: Path, config: Config) -> None:
    with Image.open(path) as image:
        if image.format != 'PNG' or image.mode != 'RGBA' or image.size != (config.size, config.size):
            raise RuntimeError('输出格式、颜色模式或尺寸校验失败')
        if any(abs(value - config.dpi) > 0.02 for value in image.info.get('dpi', (0, 0))):
            raise RuntimeError('输出 DPI 校验失败')
        image.load()


def process_one(path: Path, config: Config, stop: threading.Event | None = None) -> Result:
    result = Result(str(path), 'failed')
    saved = None
    try:
        if stop and stop.is_set():
            raise Cancelled()
        image, kind, notes = decode(path, config.size)
        result.input_format, result.original_size, result.notes = kind, image.size, notes
        target = fit_size(*image.size, config.size)
        result.content_size = target
        factor = max(target[0] / image.width, target[1] / image.height)
        if kind != 'SVG' and factor > 1 and config.upscale == 'waifu2x':
            try:
                content = waifu_upscale(image, target, config, stop)
                result.method = 'waifu2x'
                result.notes.append('仅 RGB 超分；透明通道使用 Lanczos 缩放')
            except Cancelled:
                raise
            except Exception as exc:
                if not config.fallback_lanczos:
                    raise
                content = image.resize(target, Image.Resampling.LANCZOS)
                result.method = 'lanczos-fallback'
                result.notes.append(f'用户允许回退，waifu2x 错误: {exc}')
        else:
            content = image.resize(target, Image.Resampling.LANCZOS) if image.size != target else image
            result.method = 'svg-render' if kind == 'SVG' else ('unchanged' if image.size == target else 'lanczos')
        if stop and stop.is_set():
            raise Cancelled()
        canvas = Image.new('RGBA', (config.size, config.size), (0, 0, 0, 0))
        canvas.alpha_composite(content, ((config.size - content.width) // 2, (config.size - content.height) // 2))
        relative = path.relative_to(config.source) if config.source.is_dir() else Path(path.name)
        assert config.output is not None
        saved, stream = reserve_path(config.output / relative.parent, relative.name)
        with stream:
            canvas.save(stream, format='PNG', dpi=(config.dpi, config.dpi))
        verify(saved, config)
        result.output, result.status = str(saved), 'ok'
    except Cancelled:
        result.status = 'cancelled'
    except Exception as exc:
        if saved is not None:
            saved.unlink(missing_ok=True)  # Only remove the file exclusively created by this call.
        result.error = f'{type(exc).__name__}: {exc}'
    return result


def run_batch(config: Config, progress: Callable[[int, int, Result], None] | None = None,
              stop: threading.Event | None = None) -> Batch:
    config.validate()
    sources = discover(config)
    if not sources:
        raise ValueError('没有找到支持的图片；子文件夹需要开启 --recursive')
    results = []
    for index, path in enumerate(sources, 1):
        if stop and stop.is_set():
            break
        result = process_one(path, config, stop)
        results.append(result)
        if progress:
            progress(index, len(sources), result)
    cancelled = bool(stop and stop.is_set())
    assert config.output is not None
    config.output.mkdir(parents=True, exist_ok=True)
    payload = {'created_at': datetime.now(timezone.utc).isoformat(),
               'config': {k: str(v) if isinstance(v, Path) else v for k, v in asdict(config).items()},
               'total_inputs': len(sources), 'processed': len(results), 'cancelled': cancelled,
               'success': sum(r.status == 'ok' for r in results),
               'failed': sum(r.status == 'failed' for r in results),
               'results': [asdict(r) for r in results]}
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    report = config.output / f'report-{stamp}.json'
    with report.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return Batch(results, report, cancelled)
