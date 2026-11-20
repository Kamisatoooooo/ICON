# ICON

用于 mihomo 的个人图标仓库，按机场、地区和策略组分类整理；同时提供图片标准化工具，方便导入和维护图标。

- **图标分类**：机场品牌、国家 / 地区、应用服务与策略组。
- **统一处理**：将图片转换为 144×144、RGBA PNG、96 DPI。
- **两种操作方式**：简洁的终端交互界面（TUI）和命令行（CLI）。
- **两种放大方式**：默认 auto 自适应选择 Lanczos / waifu2x，也可手动指定；SVG 直接渲染。
- **保留原图**：独立目录输出，不覆盖已有图片。

> 只引用仓库中的图标，不需要安装 Node.js、Python 或运行脚本。以下环境要求仅针对图片处理工具。

## 目录结构

```text
ICON/
├── airport/              # 机场图标，例如 Nexitally、TAG、YTOO
├── area/                 # 国家 / 地区图标，例如 HK、JP、SG、USA
├── group/                # 应用、服务和策略组图标，例如 AI、Steam、Telegram
├── script/               # 图片处理工具及详细说明
│   ├── normalize_icons.py
│   ├── image_core.py
│   ├── image_tui.py
│   ├── tui_completion.py
│   ├── launcher.cjs
│   ├── requirements.txt
│   └── README.md
├── package.json          # npm 启动命令
└── README.md
```

## 引用图标

本仓库为 `Kamisatoooooo/ICON`，引用分支为 `main`。按分类找到图片后，使用对应文件的原始内容地址，而不是 GitHub 文件预览页面地址。以下链接可直接使用：

```text
https://raw.githubusercontent.com/Kamisatoooooo/ICON/main/group/AI.png
https://raw.githubusercontent.com/Kamisatoooooo/ICON/main/area/HK.png
https://raw.githubusercontent.com/Kamisatoooooo/ICON/main/airport/TAG.png
```

文件名的大小写以仓库中的实际名称为准，例如地区图标为 `USA.png`。调整分类、重命名或删除图片时，也需要检查已有配置中的引用。

## 图片处理工具

### 环境要求与启动

- Node.js 18+ 和 npm。
- Python 3.10+。
- 默认 auto 在遇到长边小于 128px、需要放大的位图时使用 waifu2x，可通过 `npm run setup:ai` 安装；手动选择 Lanczos 则无需安装 AI 工具。

在仓库根目录运行；Windows CMD 可直接使用，无需 PowerShell，也无需手动激活 Python 虚拟环境：

```sh
# 首次使用：创建 script/.venv 并安装 Python 运行依赖
npm run setup

# 可选：安装 AI 超分程序和模型（Windows x64）
npm run setup:ai

# 启动终端交互界面
npm start
```

环境准备好后，日常只需执行 `npm start`。启动器没有第三方 npm 依赖，**不需要先运行 `npm install`**。首次安装 Python 依赖需要联网，正常启动不会自动下载模型。

### TUI：输入路径即可操作

界面上方显示操作记录，底部是输入框。以下内容是在 TUI 中逐行输入，不是系统终端命令：

```text
group
/scan
/run
```

输入 `group` 会选择该文件夹并扫描预览，**不会立即转换**；输入 `/run` 才开始处理。也可以直接输入 `/run group`。

| 操作 | 命令 / 快捷键 |
|---|---|
| 扫描预览，不写入文件 | `/scan` 或 `/scan 路径` |
| 安装 AI，无需退出 | `/install-ai` |
| 开始处理 | `/run` 或 `/run 路径` |
| 切换放大方式 | `/method auto`（默认）、`/method lanczos`、`/method waifu2x` |
| 指定输出目录 | `/output normalized` |
| 恢复默认输出目录 | `/output default` |
| 开启 / 关闭递归 | `/recursive on`、`/recursive off` |
| 查看配置 / 帮助 | `/status`、`/help` |
| 命令与路径补全 | `Tab`；多个候选时继续按 Tab 切换 |
| 查看输入历史 | `↑` / `↓` |
| 停止任务但不退出 | `Esc` 或 `/stop` |
| 退出 | `Ctrl+C` 或 `/quit` |

相对路径以**仓库根目录**为基准，而不是相对于当前选择的图片目录。支持 `group`、`./group`、Windows 的 `.\group` 以及带空格的路径。任务运行中按 Ctrl+C 会先请求安全停止，报告写入后自动退出。

### CLI：直接处理文件或文件夹

```sh
# 单张图片
npm run normalize -- "airport/TAG.png"

# 扫描预览，不生成文件
npm run normalize -- group --dry-run

# 处理文件夹，默认不递归
npm run normalize -- group

# 递归处理，并指定输出目录
npm run normalize -- group --recursive --output normalized

# 查看完整参数
npm run normalize -- --help
```

默认情况下，`group` 的处理结果写入 `group/normalized/`；单文件的结果写入其所在目录下的 `normalized/`。递归处理会保留相对目录结构。输出目录不能与输入目录相同。

## 处理规则

以下是工具的默认输出规则，不代表每个新加入仓库的文件都会自动完成处理：

| 项目 | 规则 |
|---|---|
| 格式与画布 | RGBA PNG，144×144 像素 |
| 图片密度 | 96×96 DPI；读回约 96.012 属于正常舍入 |
| 长宽比 | 保持比例、居中透明补边，不拉伸、不裁切 |
| 原有背景和边距 | 不自动去白底、不自动裁透明边 |
| SVG / ICO | SVG 直接渲染；ICO 选择最大可用图层 |
| 多帧图片 | 取第 0 帧，成品不保留动画 |
| 放大与缩小 | 默认 auto：长边 <128px 且需要放大的位图用 waifu2x，其他缩放用 Lanczos；可手动指定模式 |
| 同名文件 | 自动增加 `__2`、`__3` 等后缀，不覆盖已有成品 |
| 处理报告 | 每批输出 `report-时间戳.json`，记录结果、实际算法与错误 |

### 关于 waifu2x

可选后端为 **waifu2x NCNN/Vulkan**，不以 CUDA / N 卡作为前提。Windows x64 可运行 `npm run setup:ai` 下载官方程序和配套模型；其他系统可手动配置。处理图片时不会自动联网安装；实际 CPU / GPU 支持取决于版本、设备及驱动。

AI 超分不保证忠实还原 Logo 的小字和细线，建议先用 Lanczos 建立对照，再对明显偏小的图片尝试 waifu2x。默认 AI 失败不会静默切换算法，只有显式允许后才回退。

完整的 waifu2x 配置、设备选择、超时和回退说明见 [工具使用说明](script/README.md)。

## 日常维护建议

1. 将新图标放入相应分类目录，文件名尽量简洁、易于辨认。
2. 使用扫描预览确认输入，再输出到独立目录检查效果。
3. 重点查看透明边缘、细小文字和非正方形图片的留白。
4. 确认结果后，再手动整理到正式图标目录；工具不会自动替换原图或修改 mihomo 配置。
5. 更新文件名或路径时，同步维护引用。避免将 Python 虚拟环境、批次报告等本地文件混入图标目录提交。

本仓库用于个人图标整理，不表示与相关品牌存在关联，也不对第三方图标作统一的授权声明。

> **安装提示**：在系统终端运行 `npm run setup` 准备 Python 环境；需要 AI 再执行 `npm run setup:ai`（目前自动安装支持 Windows x64）。安装位置为 `script/tools/waifu2x/`，已被 Git 忽略，安装后自动识别。TUI 可直接输入 `/install-ai` 后台安装，日志实时显示，完成后无需重启即可 `/run`；缺失时会提示该命令。所有安装入口都不调用 PowerShell。
