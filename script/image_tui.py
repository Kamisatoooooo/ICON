"""Minimal prompt-driven terminal UI sharing the existing conversion engine."""
from __future__ import annotations

import math
import os
import threading
from dataclasses import replace
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input, RichLog, Static

from image_core import Batch, Config, Result, discover, executable, run_batch
from tui_completion import complete_prefix

COMMANDS = {
    '/run': '开始处理，可追加文件或文件夹路径',
    '/install-ai': '后台安装 AI 程序及模型，无需退出界面',
    '/scan': '扫描预览，可追加路径；不写入文件',
    '/method': 'auto（默认） | lanczos | waifu2x',
    '/output': '输出目录；default 恢复默认',
    '/recursive': 'on | off；不填则切换',
    '/set': '高级设置：waifu2x / device / model-dir / fallback / timeout',
    '/status': '查看当前配置',
    '/stop': '停止当前任务',
    '/clear': '清空操作记录',
    '/help': '查看使用说明',
    '/quit': '退出',
}


def unquote(value: str) -> str:
    """Preserve Windows backslashes and spaces, removing only paired outer quotes."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def boolean(value: str) -> bool:
    if value.lower() not in {'on', 'off'}:
        raise ValueError('请使用 on 或 off')
    return value.lower() == 'on'


class NormalizeApp(App):
    TITLE = 'ICON'
    CSS = '''
    Screen { background: #141414; color: #dedede; padding: 0 2; }
    #title { height: 2; padding-top: 1; color: #e8e8e8; }
    #context { height: 1; color: #999999; margin-bottom: 1; }
    #log { height: 1fr; background: transparent; padding: 0; border: none; }
    #status { height: 1; color: #a4b8a6; margin-top: 1; }
    #prompt { height: 3; background: #202020; border: none; border-top: solid #555555;
              border-bottom: solid #555555; padding: 0 1; }
    #prompt:focus { border-top: solid #a6b4a0; border-bottom: solid #a6b4a0; }
    #hint { height: 1; color: #8e8e8e; }
    '''
    BINDINGS = [
        Binding('ctrl+r', 'start', '开始', show=False),
        Binding('ctrl+c', 'quit', '退出', show=False, priority=True),
        Binding('escape', 'stop', '停止', show=False, priority=True),
        Binding('tab', 'complete', '补全', show=False, priority=True),
        Binding('up', 'history_previous', '上一条', show=False, priority=True),
        Binding('down', 'history_next', '下一条', show=False, priority=True),
    ]

    def __init__(self, initial: Config | None = None):
        super().__init__()
        self.config = replace(initial) if initial else Config(Path.cwd())
        self.busy = False
        self.task_kind: str | None = None
        self.stop_event = threading.Event()
        self.history: list[str] = []
        self.history_position = 0
        self.draft = ''
        self.quit_requested = False
        self.completion_matches: list[str] = []
        self.completion_index = -1
        self.completion_last: tuple[str, int] | None = None
        self.completion_suffix = ''

    def compose(self) -> ComposeResult:
        yield Static('ICON  /  图片标准化', id='title', markup=False)
        yield Static('', id='context', markup=False)
        yield RichLog(id='log', wrap=True, highlight=False, markup=False, auto_scroll=True)
        yield Static('就绪', id='status', markup=False)
        yield Input(placeholder='› 输入文件或文件夹，或输入 / 查看命令', id='prompt')
        yield Static('/ 命令   Tab 路径补全   ↑↓ 历史   Esc 停止   Ctrl+C 退出', id='hint', markup=False)

    def on_mount(self) -> None:
        self.update_context()
        self.write_log('输入路径并回车即可选择图片或文件夹。/scan 预览，/run 处理。')
        self.write_log('auto：长边 <128px 的小位图用 waifu2x，其他用 Lanczos；SVG 直接渲染。')
        if self.config.upscale != 'lanczos':
            try:
                executable(self.config)
            except RuntimeError as exc:
                self.write_log(f'提示：{exc}')
        self.write_log('原图保留 · 等比居中 · 透明补边。输入 /help 查看更多。')
        self.query_one('#prompt', Input).focus()

    def update_context(self) -> None:
        cfg = self.config
        self.query_one('#context', Static).update(
            f'144×144 · PNG · 96 DPI · {cfg.upscale} · 递归 {"开" if cfg.recursive else "关"} · {cfg.source}')

    def write_log(self, message: str) -> None:
        self.query_one('#log', RichLog).write(message)

    def read_config(self) -> Config:
        # Validation resolves paths in place. Keep the editable config independent.
        return replace(self.config)

    @on(Input.Changed, '#prompt')
    def prompt_changed(self, event: Input.Changed) -> None:
        value = event.value.strip()
        matches = [name for name in COMMANDS if name.startswith(value)] if value.startswith('/') else []
        hint = '  '.join(matches) if matches else '/ 命令   Tab 路径补全   ↑↓ 历史   Esc 停止   Ctrl+C 退出'
        if value in COMMANDS:
            hint = f'{value}  {COMMANDS[value]}'
        if self.completion_last and event.value == self.completion_last[0] and len(self.completion_matches) > 1:
            hint = self.completion_hint()
        self.query_one('#hint', Static).update(hint)

    @on(Input.Submitted, '#prompt')
    def submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        if not self.history or self.history[-1] != text:
            self.history.append(text)
        self.history_position = len(self.history)
        self.draft = ''
        event.input.value = ''
        self.write_log(f'› {text}')
        try:
            self.dispatch(text)
        except Exception as exc:
            self.write_log(f'  错误: {exc}')

    def dispatch(self, text: str) -> None:
        command, _, argument = text.partition(' ')
        command = command.lower()
        argument = unquote(argument)
        if self.busy and command not in {'/stop', '/quit', '/status', '/help', '/clear'}:
            raise ValueError('任务正在运行，Esc 或 /stop 停止后再修改配置')
        if not text.startswith('/'):
            # Absolute POSIX paths also start with /; handled below as a fallback.
            self.select_source(unquote(text))
        elif command in {'/run', '/scan'}:
            if argument:
                self.config.source = Path(argument).expanduser()
                self.update_context()
            self.action_start() if command == '/run' else self.preview()
        elif command == '/install-ai':
            if argument:
                raise ValueError('用法: /install-ai（无需参数）')
            self.start_install()
        elif command == '/setup':
            self.write_log('  没有 /setup 安装命令。请在终端运行 npm run setup 安装 Python 依赖（不含 waifu2x）。')
            self.write_log('  如需 AI，直接输入 /install-ai 后台安装；也可在系统终端运行 npm run setup:ai。')
        elif command == '/method':
            if argument not in {'auto', 'lanczos', 'waifu2x'}:
                raise ValueError('用法: /method auto、/method lanczos 或 /method waifu2x')
            self.config.upscale = argument
            self.write_log(f'  放大方式 → {argument}')
            self.update_context()
        elif command == '/output':
            if not argument:
                raise ValueError('用法: /output 路径，或 /output default')
            self.config.output = None if argument == 'default' else Path(argument).expanduser()
            self.write_log(f'  输出 → {self.config.output or "默认 normalized 目录"}')
        elif command == '/recursive':
            self.config.recursive = boolean(argument) if argument else not self.config.recursive
            self.update_context()
            self.write_log(f'  递归扫描 → {"开" if self.config.recursive else "关"}')
        elif command == '/set':
            self.setting(argument)
        elif command == '/status':
            for name, value in vars(self.config).items():
                self.write_log(f'  {name}: {value if value is not None else "默认"}')
        elif command == '/stop':
            self.action_stop()
        elif command == '/quit':
            self.action_quit()
        elif command == '/clear':
            self.query_one('#log', RichLog).clear()
        elif command == '/help' or text == '/':
            for name, help_text in COMMANDS.items():
                self.write_log(f'  {name:<12} {help_text}')
            self.write_log('  示例: /run "group"  ·  /set waifu2x "D:\\Tools\\waifu2x.exe"')
        elif Path(unquote(text)).expanduser().exists():
            if self.busy:
                raise ValueError('请先停止当前任务')
            self.select_source(unquote(text))
        else:
            raise ValueError('未知命令或路径不存在；输入 /help 查看说明')

    def select_source(self, value: str) -> None:
        source = Path(value).expanduser()
        if not source.exists():
            raise ValueError(f'路径不存在: {source}')
        self.config.source = source
        self.update_context()
        self.preview()

    def setting(self, argument: str) -> None:
        key, _, raw = argument.partition(' ')
        value = unquote(raw)
        if not value:
            raise ValueError('/set 需要设置名和值；使用 /help 查看设置名')
        cfg = replace(self.config)
        if key == 'waifu2x':
            cfg.waifu2x = None if value == 'default' else value
        elif key == 'device':
            cfg.device = value
        elif key == 'model-dir':
            cfg.model_dir = None if value == 'default' else Path(value).expanduser()
        elif key == 'fallback':
            cfg.fallback_lanczos = boolean(value)
        elif key == 'timeout':
            cfg.timeout = float(value)
            if not math.isfinite(cfg.timeout) or cfg.timeout <= 0:
                raise ValueError('超时时间必须为正数')
        else:
            raise ValueError('设置名: waifu2x、device、model-dir、fallback、timeout')
        # Validate without normalizing the stored default output path.
        replace(cfg).validate()
        self.config = cfg
        self.write_log(f'  {key} → {value}')

    def preview(self) -> None:
        config = self.read_config()
        config.validate()
        files = discover(config)
        self.write_log(f'  扫描到 {len(files)} 张 · 输出 {config.output}')
        for path in files[:8]:
            self.write_log(f'    {path.name}')
        if len(files) > 8:
            self.write_log(f'    … 其余 {len(files) - 8} 张')
        self.query_one('#status', Static).update(f'待处理 {len(files)} 张 · /run 开始处理；扫描未写入文件')

    def action_start(self) -> None:
        if self.busy:
            return
        try:
            config = self.read_config()
            config.validate()
        except Exception as exc:
            self.write_log(f'  配置错误: {exc}')
            return
        self.stop_event = threading.Event()
        self.busy = True
        self.task_kind = 'convert'
        self.query_one('#status', Static).update('正在处理…  Esc 停止')
        self.convert(config)

    def action_stop(self) -> None:
        if self.busy:
            self.stop_event.set()
            message = ('正在停止安装… 等待当前网络请求 / 解压结束后清理（网络超时 60 秒）'
                       if self.task_kind == 'install' else '正在停止… 等待当前解码 / AI 单轮结束（受超时限制）')
            self.query_one('#status', Static).update(message)

    def start_install(self) -> None:
        if self.busy:
            return
        self.stop_event = threading.Event()
        self.busy = True
        self.task_kind = 'install'
        self.write_log('  正在后台安装官方 waifu2x 程序及模型；Esc 停止，Ctrl+C 安全停止并退出。')
        self.query_one('#status', Static).update('AI 安装中… Esc 停止')
        self.install_ai()

    @work(thread=True, exclusive=True, group='install-ai')
    def install_ai(self) -> None:
        from install_waifu2x import InstallCancelled, main as install
        error = None
        cancelled = False
        try:
            def log(message, **_kwargs):
                self.call_from_thread(self.write_log, f'  {message}')
            code = install([], log=log, stop=self.stop_event)
            if code != 0:
                error = f'安装退出码 {code}'
        except InstallCancelled:
            cancelled = True
        except Exception as exc:
            error = str(exc)
        self.call_from_thread(self.install_finished, error, cancelled)

    def install_finished(self, error: str | None, cancelled: bool) -> None:
        self.busy = False
        self.task_kind = None
        if cancelled:
            message = 'AI 安装已停止，临时文件已清理；可再次 /install-ai'
        elif error:
            message = f'AI 安装失败: {error}；可再次 /install-ai 重试'
        else:
            message = 'AI 工具已准备好，无需重启；输入 /run 即可处理'
            try:
                executable(self.config)
            except RuntimeError:
                self.write_log('  提示：自定义 waifu2x 路径无效。/set waifu2x default 恢复自动查找，并检查 WAIFU2X_BIN。')
        self.write_log(f'  {message}')
        self.query_one('#status', Static).update(message)
        if self.quit_requested:
            self.exit()

    def completion_hint(self) -> str:
        preview = ' · '.join(self.completion_matches[:6])
        rest = f' …共 {len(self.completion_matches)} 项' if len(self.completion_matches) > 6 else ''
        return f'Tab 切换候选 · {preview}{rest}'

    def action_complete(self) -> None:
        prompt = self.query_one('#prompt', Input)
        state = (prompt.value, prompt.cursor_position)
        if state == self.completion_last and len(self.completion_matches) > 1:
            self.completion_index = (self.completion_index + 1) % len(self.completion_matches)
            replacement = self.completion_matches[self.completion_index]
        else:
            before, self.completion_suffix = prompt.value[:prompt.cursor_position], prompt.value[prompt.cursor_position:]
            self.completion_matches = complete_prefix(before, COMMANDS)
            self.completion_index = -1
            if not self.completion_matches:
                self.completion_last = None
                self.query_one('#hint', Static).update('没有匹配的文件、文件夹或命令（相对路径以启动目录为基准）')
                return
            common = os.path.commonprefix(self.completion_matches)
            if len(self.completion_matches) > 1 and len(common) > len(before):
                replacement = common
            else:
                self.completion_index = 0
                replacement = self.completion_matches[0]
        # Do not swallow the remainder when completing in the middle of a line.
        # A closing quote immediately after the cursor is already in replacement.
        suffix = self.completion_suffix
        if suffix[:1] in {'"', "'"} and replacement.endswith(suffix[0]):
            suffix = suffix[1:]
        prompt.value = replacement + suffix
        cursor = len(replacement)
        if replacement[-1:] in {'"', "'"} and replacement[-2:-1] in {'/', chr(92)}:
            cursor -= 1  # Continue directory paths inside the closing quote.
        prompt.cursor_position = cursor
        self.completion_last = (prompt.value, prompt.cursor_position)
        self.query_one('#hint', Static).update(self.completion_hint() if len(self.completion_matches) > 1 else '已补全 · Enter 确认；继续输入子路径后可再次按 Tab')

    def action_history_previous(self) -> None:
        prompt = self.query_one('#prompt', Input)
        if self.history_position == len(self.history):
            self.draft = prompt.value
        if self.history_position > 0:
            self.history_position -= 1
            prompt.value = self.history[self.history_position]
            prompt.cursor_position = len(prompt.value)

    def action_history_next(self) -> None:
        if self.history_position < len(self.history):
            self.history_position += 1
            prompt = self.query_one('#prompt', Input)
            prompt.value = self.draft if self.history_position == len(self.history) else self.history[self.history_position]
            prompt.cursor_position = len(prompt.value)

    @work(thread=True, exclusive=True)
    def convert(self, config: Config) -> None:
        try:
            def progress(index, total, result):
                self.call_from_thread(self.update_result, index, total, result)
            batch = run_batch(config, progress, self.stop_event)
            self.call_from_thread(self.finished, batch, None)
        except Exception as exc:
            self.call_from_thread(self.finished, None, str(exc))

    def update_result(self, index: int, total: int, result: Result) -> None:
        self.query_one('#status', Static).update(f'处理中 {index}/{total} · {Path(result.source).name} · Esc 停止')
        self.write_log(f'  [{index}/{total}] {result.status.upper()} {Path(result.source).name} · {result.method or "-"}')
        if result.error:
            self.write_log(f'    错误: {result.error}')
        for note in result.notes:
            self.write_log(f'    {note}')

    def finished(self, batch: Batch | None, error: str | None) -> None:
        self.busy = False
        self.task_kind = None
        if error:
            self.write_log(f'  处理失败: {error}')
            self.query_one('#status', Static).update('处理失败，请查看记录')
            if self.quit_requested:
                self.exit()
            return
        assert batch is not None
        ok = sum(r.status == 'ok' for r in batch.results)
        failed = sum(r.status == 'failed' for r in batch.results)
        summary = f'{"已停止" if batch.cancelled else "完成"} · 成功 {ok}，失败 {failed}'
        self.write_log(f'  {summary}\n  报告: {batch.report}')
        self.query_one('#status', Static).update(summary)
        if self.quit_requested:
            self.exit()

    def action_quit(self) -> None:
        if self.busy:
            self.quit_requested = True
            self.action_stop()
            self.write_log('  已请求安全停止，安装清理结束后自动退出' if self.task_kind == 'install' else '  已请求安全停止，报告写入后自动退出')
        else:
            self.exit()
