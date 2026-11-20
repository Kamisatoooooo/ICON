#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const VENV = path.join(ROOT, 'script', '.venv');

function pythonPath(root = ROOT, platform = process.platform) {
  return path.join(root, 'script', '.venv', ...(platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python']));
}

function plan(command, args = [], root = ROOT, platform = process.platform) {
  const python = pythonPath(root, platform);
  const entry = path.join(root, 'script', 'normalize_icons.py');
  switch (command) {
    case 'tui':
      return { executable: python, args: ['-X', 'utf8', entry, '--tui', ...args] };
    case 'normalize':
      return { executable: python, args: ['-X', 'utf8', entry, ...args] };
    default:
      throw new Error(`未知启动模式: ${command}`);
  }
}

function execute(executable, args) {
  // Direct process invocation: paths/arguments are never interpolated into a shell.
  const result = spawnSync(executable, args, {
    cwd: ROOT,
    stdio: 'inherit',
    shell: false,
    env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
  });
  if (result.error) {
    console.error(`无法启动 ${executable}: ${result.error.message}`);
    return 2;
  }
  if (result.signal) return result.signal === 'SIGINT' ? 130 : 1;
  return result.status ?? 1;
}

function findBootstrapPython() {
  const candidates = process.env.ICON_PYTHON
    ? [[process.env.ICON_PYTHON, []]]
    : process.platform === 'win32'
      ? [['py', ['-3']], ['python', []], ['python3', []]]
      : [['python3', []], ['python', []]];
  for (const [executable, args] of candidates) {
    const result = spawnSync(executable, [...args, '-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'], {
      stdio: 'ignore', shell: false, timeout: 15000,
    });
    if (!result.error && result.status === 0) return { executable, args };
  }
  throw new Error('未找到 Python 3.10+。请先安装 Python，或用 ICON_PYTHON 指定 Python 可执行文件的完整路径。');
}

function setup(args) {
  if (args.length !== 0) {
    console.error('用法: npm run setup');
    return 2;
  }
  const python = pythonPath();
  if (!fs.existsSync(python)) {
    const bootstrap = findBootstrapPython();
    const status = execute(bootstrap.executable, [...bootstrap.args, '-m', 'venv', VENV]);
    if (status !== 0) return status;
  }
  const requirements = path.join(ROOT, 'script', 'requirements.txt');
  const status = execute(python, ['-X', 'utf8', '-m', 'pip', 'install', '-r', requirements]);
  if (status === 0) {
    console.log('\nPython 环境已准备好。运行 npm start 打开 TUI。');
    console.log('注意：setup 不安装 waifu2x。默认 auto 遇到长边 <128px 的小位图会需要该程序。');
    console.log('需要 AI 时运行 npm run setup:ai，安装后自动识别，无需填写路径（目前自动安装支持 Windows x64）。');
    console.log('TUI 没有 /setup 安装命令；暂不使用 AI 可输入 /method lanczos。');
  }
  return status;
}

function main(argv = process.argv.slice(2)) {
  const [command = 'tui', ...args] = argv;
  try {
    if (command === 'setup') return setup(args);
    if (command === 'setup-ai') {
      const python = pythonPath();
      const bootstrap = fs.existsSync(python) ? { executable: python, args: [] } : findBootstrapPython();
      return execute(bootstrap.executable, [...bootstrap.args, '-X', 'utf8', path.join(ROOT, 'script', 'install_waifu2x.py'), ...args]);
    }
    const launch = plan(command, args);
    if (!fs.existsSync(launch.executable)) {
      console.error('尚未创建项目 Python 环境。请先运行 npm run setup，再运行 npm start。');
      return 2;
    }
    return execute(launch.executable, launch.args);
  } catch (error) {
    console.error(error.message);
    return 2;
  }
}

process.exitCode = main();
