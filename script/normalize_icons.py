#!/usr/bin/env python3
"""CLI entry point. With no arguments, launch the optional Textual TUI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description='图片标准化：144×144、RGBA PNG、96 DPI；默认不覆盖原图。')
    cli.add_argument('source', nargs='?', type=Path, help='单个文件或文件夹；不填则启动 TUI')
    cli.add_argument('--tui', action='store_true', help='打开交互式终端界面')
    cli.add_argument('-o', '--output', type=Path, help='独立输出目录（默认：输入目录/normalized）')
    cli.add_argument('-r', '--recursive', action='store_true', help='递归扫描子目录，保留目录结构')
    cli.add_argument('--upscale', choices=['auto', 'lanczos', 'waifu2x'], default='auto',
                     help='默认 auto：长边小于 128px 且需要放大的位图使用 waifu2x，其余使用 Lanczos')
    cli.add_argument('--waifu2x', help='waifu2x-ncnn-vulkan 可执行文件路径，也可设置 WAIFU2X_BIN')
    cli.add_argument('--device', default='auto', help='waifu2x 设备：auto、cpu 或 GPU 编号，例如 0')
    cli.add_argument('--model-dir', type=Path, help='可选的 waifu2x 模型文件夹；默认使用程序自带模型')
    cli.add_argument('--fallback-lanczos', action='store_true', help='明确允许 AI 失败时回退 Lanczos，并在报告中记录')
    cli.add_argument('--timeout', type=float, default=180, help='waifu2x 每轮超时秒数（默认 180）')
    cli.add_argument('--dry-run', action='store_true', help='只列出待处理文件，不创建目录或写入图片')
    return cli


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        from image_core import Config, discover, run_batch
        config = Config(source=args.source or Path.cwd(), output=args.output,
                        recursive=args.recursive, upscale=args.upscale, waifu2x=args.waifu2x,
                        device=args.device, model_dir=args.model_dir,
                        fallback_lanczos=args.fallback_lanczos, timeout=args.timeout)
        if args.tui or (args.source is None and not args.dry_run):
            from image_tui import NormalizeApp
            NormalizeApp(config).run()
            return 0
        config.validate()
        if args.dry_run:
            files = discover(config)
            print(f'输入: {config.source}\n输出: {config.output}\n待处理: {len(files)} 张')
            for path in files:
                print(path)
            return 0 if files else 1
        def progress(index, total, result):
            print(f'[{index}/{total}] {result.status.upper()} {Path(result.source).name}', flush=True)
            if result.output:
                print(f'  -> {result.output} ({result.method})', flush=True)
            for note in result.notes:
                print(f'  提示: {note}', flush=True)
            if result.error:
                print(f'  错误: {result.error}', file=sys.stderr, flush=True)
        batch = run_batch(config, progress)
        successes = sum(r.status == 'ok' for r in batch.results)
        failures = sum(r.status == 'failed' for r in batch.results)
        print(f'\n完成：成功 {successes}，失败 {failures}；报告: {batch.report}')
        return 1 if failures else 0
    except ImportError as exc:
        print(f'缺少依赖: {exc}\n请运行: python -m pip install -r script/requirements.txt', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('\n操作已中断；已生成的文件保留。', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'错误: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    # UTF-8 also when redirected to files/pipes on Windows.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
