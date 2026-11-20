# 图片标准化工具

[返回项目首页](../README.md)

将单张图片或文件夹中的图片转换为 **144×144、RGBA PNG、96 DPI**。提供命令行和 Textual TUI，共用同一处理引擎。原图不会被覆盖，默认使用 auto 自适应选择 Lanczos / waifu2x NCNN/Vulkan，也可手动指定。

## 1. 安装与启动

要求 **Node.js 18+、npm 和 Python 3.10+**。以下命令在仓库根目录执行，可以直接使用 Windows CMD，不依赖 PowerShell，也不需要激活虚拟环境。

```sh
# 首次安装 / 重建 Python 环境时执行
npm run setup

# 可选：安装 AI 超分程序和模型（Windows x64）
npm run setup:ai

# 打开 TUI
npm start
```

如果已完成初始化且 `script/.venv` 可用，后续可直接运行 `npm start`；更换设备或重新克隆仓库后，需要重新执行 `npm run setup`。

- `npm run setup` 自动查找 Python 3.10+、创建项目内的 `script/.venv`，并安装运行依赖；不会修改全局 Python 环境。
- 已有虚拟环境时，setup 复用它。首次安装依赖需要联网；平时 `npm start` 不会下载依赖或模型。
- 如需指定用于创建环境的 Python，在 CMD 中先执行 `set "ICON_PYTHON=C:\Path To\Python\python.exe"`，再运行 `npm run setup`。值应仅包含程序路径，不带命令行参数。
- 不需要执行 `npm install`，启动器没有第三方 npm 依赖；图片处理仍由 Python 引擎完成。
- `npm run tui` 与 `npm start` 等效。向命令追加参数时使用 `--`。
- 原 PowerShell 启动文件已移除。所有 npm 入口通过 Node 直接启动 Python，不调用 PowerShell。

虚拟环境已被 Git 忽略，不随仓库分发。SVG 使用 `resvg-py` 渲染，不走 CairoSVG 的转换路线。

### TUI 操作

界面采用简洁的终端交互布局：上方为操作记录，底部只有一个输入框；不再显示大表单、按钮面板或目录选择弹窗。输入 `/` 查看命令，`Tab` 补全命令以及文件 / 文件夹路径，`↑` / `↓` 回看输入历史。80×24 的终端也能显示主要操作区。

```text
ICON  /  图片标准化
144×144 · PNG · 96 DPI · auto · 递归 关 · ...

› group
  扫描到 45 张 · 输出 .../group/normalized

› /run
  [1/45] OK Adobe.png · lanczos
  ...

就绪 / 当前进度
────────────────────────────────────────────────────
› 输入文件或文件夹，或输入 / 查看命令
────────────────────────────────────────────────────
/ 命令   Tab 补全   ↑↓ 历史   Esc 停止   Ctrl+C 退出
```

- 直接输入文件 / 文件夹路径并回车：选择输入并扫描预览，**不会立即处理**。中文、空格、Windows 反斜杠可直接使用，路径两侧可加引号。
- 路径补全支持 `gro`、`./gro`、Windows 的 `.\gro`、`../`、绝对路径、中文和带空格路径；相对路径以启动目录为基准（通过 npm 启动时为仓库根目录），不是相对于当前选择的图片文件夹。
- 支持在 `/run 路径`、`/scan 路径`、`/output 路径`、`/set waifu2x 路径` 和 `/set model-dir 路径` 中按 Tab 补全；输出和模型目录只补全文件夹。
- 多项匹配时先补齐公共前缀，再连续按 Tab 循环选择候选；修改输入会重新查找。唯一文件夹补全后带目录分隔符，再按 Tab 可继续补全子项。空格路径会自动加引号，文件夹的光标保持在引号内便于继续输入。
- `/scan [路径]`：扫描预览，不写入文件。
- `/install-ai`：后台安装官方 AI 程序和配套模型，日志实时显示；安装后直接 `/run`，不用重启。安装与图片处理不能同时进行；Esc 安全停止并清理，Ctrl+C 清理后退出。停止可能等待当前网络请求（60 秒超时）或解压完成。
- `/run [路径]`：开始处理当前输入，或指定新路径并处理。
- `/method auto`（默认）、`/method lanczos`、`/method waifu2x`：选择放大方式。
- `/output 路径`：设置输出目录；`/output default` 恢复默认 `normalized`。
- `/recursive on`、`/recursive off`：控制递归；只输入 `/recursive` 则切换。
- `/status`：查看全部配置；`/help` 查看命令；`/clear` 清空记录。
- 高级设置按需使用，例如 `/set waifu2x "D:\Tools\waifu2x.exe"`、`/set device cpu`、`/set model-dir "D:\Tools\models-cunet"`、`/set timeout 180`、`/set fallback on`。
- AI 回退默认关闭，仅 `/set fallback on` 才允许失败后改用 Lanczos，且会记录原因。
- `Ctrl+R` 开始；`Esc` 或 `/stop` 只停止任务，不退出。
- `Ctrl+C` 或 `/quit` 退出，输入框有未提交内容时也可退出；任务运行期间先安全停止，处理报告写入或安装临时文件清理后自动退出，无需再次按键。
- 停止需等待当前解码 / waifu2x 单轮调用完成；默认单轮超时 180 秒。已生成的成品保留，并写入报告。

## 2. 命令行示例

```sh
# 单个文件，默认 auto 自适应
npm run normalize -- ".\airport\TAG.png"

# 文件夹：默认不扫描子文件夹
npm run normalize -- ".\group"

# 递归扫描，保留输入下的相对目录结构
npm run normalize -- ".\area" --recursive --output ".\normalized\area"

# 只扫描，不写入
npm run normalize -- ".\group" --dry-run

# 用已有路径初始化 TUI
npm start -- ".\group"

# 所有参数
npm run normalize -- --help
```

npm 入口以仓库根目录为工作目录；相对输入、输出路径均以仓库根目录为基准。文件夹扫描按常见图片扩展名筛选；解码时识别实际格式，例如扩展名为 `.png` 的 JPEG。单文件输入不限制扩展名。

## 3. 自适应模式与 waifu2x 配置

默认 `auto`（CLI：`--upscale auto`；TUI：`/method auto`）：

- 解码后位图的**长边小于 128px**，且需要放大到目标尺寸时使用 waifu2x。
- 长边恰好为 128px 不走 AI；例如 100×100、48×48 使用 AI，128×128 使用 Lanczos。
- 非正方形按长边判断：128×64 使用 Lanczos 并透明补边，不因短边不足而调用 AI。
- 缩小使用 Lanczos，无需缩放则保持像素；SVG 直接按目标尺寸渲染。
- `--upscale lanczos` 强制所有位图缩放使用 Lanczos；`--upscale waifu2x` 对所有需要放大的位图使用 AI。
- auto 处理图片时不会自动安装 waifu2x。可预先运行 `npm run setup:ai`；需要 AI 但程序缺失或失败时，该文件会报错并提示安装命令，只有明确启用回退才改用 Lanczos。

```sh
# 默认 auto，指定 AI 程序（仅命中小图时调用）
npm run normalize -- ".\group" --waifu2x "D:\Tools\waifu2x\waifu2x-ncnn-vulkan.exe"

# 不使用 AI，也不需要安装 waifu2x
npm run normalize -- ".\group" --upscale lanczos
```

**不要求 CUDA/N 卡，图片处理过程中不会自动下载。** Windows x64 可显式运行 `npm run setup:ai` 安装官方 `nihui/waifu2x-ncnn-vulkan` 最新稳定发行包及模型到 `script/tools/waifu2x/`；后续自动识别，无需指定路径。重复运行会复用完整安装，不自动升级或覆盖。其他系统仍可手动安装，解压时保留程序与自带模型文件夹的相对位置。不同版本的设备支持可能不同；CPU 模式需使用支持 `-g -1` 的版本，GPU 模式依赖适用的 Vulkan 设备与驱动。

```sh
# 指定程序；自动选择设备
npm run normalize -- ".\group" --upscale waifu2x --waifu2x "D:\Tools\waifu2x\waifu2x-ncnn-vulkan.exe"

# 使用 CPU
npm run normalize -- ".\group" --upscale waifu2x --waifu2x "D:\Tools\waifu2x\waifu2x-ncnn-vulkan.exe" --device cpu

# 指定 GPU 0 / 模型目录 / 单轮超时
npm run normalize -- ".\group" --upscale waifu2x --waifu2x "D:\Tools\waifu2x\waifu2x-ncnn-vulkan.exe" --device 0 --model-dir "D:\Tools\waifu2x\models-cunet" --timeout 180
```

程序查找优先级：`--waifu2x` → 环境变量 `WAIFU2X_BIN` → 项目内 `script/tools/waifu2x/` → 系统 `PATH`。

- 仅需要放大的位图调用 waifu2x；大图缩小仍用 Lanczos，SVG 直接渲染，不需要 waifu2x。
- 默认不降噪，使用 `-n -1 -s 2`；必要时多轮 2 倍放大，最后缩放到内容目标尺寸。
- RGB 使用 AI，alpha 单独使用 Lanczos 缩放。半透明像素保留原始 RGB，仅完全透明处填充白色供模型推理；边缘观感仍应人工检查。
- AI 并不保证忠实恢复 Logo 的细字或线条，建议与 Lanczos 成品比较。
- 默认 AI 失败会记录该文件失败并继续其他图片，不会悄悄换算法。只有指定 `--fallback-lanczos` 或在 TUI 执行 `/set fallback on`，才允许回退，并记录具体原因。
- 如果所有文件都只需缩小 / 直接渲染，即使选择 waifu2x，也不会要求安装可执行程序。

## 4. 处理规则与保护措施

| 内容 | 行为 |
|---|---|
| 目标画布 | 固定 144×144，RGBA PNG，96×96 DPI |
| 长宽比 | 等比缩放，居中透明补边，不拉伸、不裁切 |
| 既有边距 / 白底 | 不自动去除 |
| SVG | 按目标边界直接渲染，再居中；报告中的原始尺寸字段表示渲染后的像素尺寸 |
| ICO | 选择最大可用图层 |
| GIF / 动态 WebP / APNG / 多页 TIFF | 取第 0 帧；APNG 有默认静态图时取默认图；报告注明 |
| EXIF 方向 | 应用方向后再缩放，不重复保留方向标签 |
| ICC | 尝试转换为 sRGB；失败会注明，按原始颜色转换 |
| 同名输出 | 自动添加 `__2`、`__3` 等后缀；重复运行也不覆盖已有成品 |
| 输入输出隔离 | 拒绝把输出目录设为输入目录本身；递归扫描排除所选输出子树 |
| 隐藏目录 / 链接 | 文件夹扫描跳过点开头目录、符号链接及 Windows junction，不跟随链接递归 |
| 输出校验 | 每张成品重新打开，校验 PNG、RGBA、144×144、DPI；失败不保留该次未验证成品 |
| 原图 | 不修改、不重命名、不删除；不同输入不做内容合并 |

PNG 以整数“每米像素数”保存密度，因此读回可能是 **96.012 DPI**，属于正常舍入，校验允许 0.02 DPI 误差。DPI 只是元数据，不会增加像素细节。

每批生成独立 `report-时间戳.json`，包含配置、输入数、成功 / 失败数、输入输出映射、实际算法、提示与错误。失败项不会阻止其余图片处理。正常完成 / TUI 停止会生成报告；强制终止进程或命令行 Ctrl+C 不保证产生批次报告。

命令行退出码：`0` 成功，`1` 存在图片失败 / 扫描无匹配图片，`2` 配置或运行错误，`130` 用户中断。

## 5. 文件结构

- `normalize_icons.py`：命令行入口，无输入参数时打开 TUI。
- `image_core.py`：格式解码、缩放、waifu2x 调用、安全保存和报告。
- `image_tui.py`：简洁输入式终端界面、斜杠命令、输入历史、后台任务和操作记录。
- `tui_completion.py`：命令与文件系统路径补全，不经过 shell 解析。
- `launcher.cjs`：无第三方 npm 依赖的启动器，负责基础环境、AI 安装入口和 TUI / CLI 启动。
- `install_waifu2x.py`：通过官方 GitHub Releases 安装 AI 程序和模型，验证下载大小、可用的官方 SHA256 及 ZIP 路径安全性；版本与摘要记录在安装目录。
- 根目录 `package.json`：npm 命令定义。
- `requirements.txt`：运行依赖。

> **安装提示**：在系统终端运行 `npm run setup` 准备 Python 环境；需要 AI 再执行 `npm run setup:ai`（目前自动安装支持 Windows x64）。安装位置为 `script/tools/waifu2x/`，已被 Git 忽略，安装后自动识别。TUI 可直接输入 `/install-ai` 后台安装，日志实时显示，完成后无需重启即可 `/run`；缺失时会提示该命令。所有安装入口都不调用 PowerShell。
