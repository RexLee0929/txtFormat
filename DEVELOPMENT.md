# txtFormat 开发说明

给要改代码、重新打包的人看。用户怎么用写在 [README.md](README.md) 里，这里只讲工程本身。

## 环境

| 项目 | 要求 |
| --- | --- |
| 系统 | 64 位 Windows 10 1903+ / Windows 11 |
| Python | 3.11 以上（虚拟环境放 `.venv\`） |
| 运行依赖 | `PySide6-Essentials>=6.6`（见 `requirements.txt`） |
| 打包主程序 | PyInstaller（`build.cmd` 会自动装） |
| 打包安装器 | .NET SDK 6.0 及以上（编译 WinForms 向导，目标框架 .NET Framework 4.8） |

## 编译

### 脚本

```bat
setup.cmd             :: 首次：建 .venv 并装依赖
run.cmd               :: 启动（pythonw，无控制台窗口）
build.cmd             :: 生成程序本体 → artifacts\txtFormat\txtFormat.exe
build-installer.cmd   :: 生成安装包   → artifacts\txtFormat-<版本>-setup.exe
```

`build-installer.cmd` 依赖 `artifacts\txtFormat\` 已存在，必须先跑 `build.cmd`。它做三件事：
`tools\make_payload.py` 把产物压成 `installer\winforms\payload.zip`；`dotnet build -c Release` 编译向导；
把 `installer\winforms\bin\Release\net48\txtFormat-Setup.exe` 复制成带版本号的安装包名。

### 手工分步

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py

:: 程序本体
.venv\Scripts\python.exe tools\make_icon.py
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath artifacts txtFormat.spec

:: 安装包：先把 VER 设为 installer\version.props 中的版本
set /p VER=请输入版本号：
.venv\Scripts\python.exe tools\make_payload.py
cd installer\winforms && dotnet build -c Release && cd ..\..
copy installer\winforms\bin\Release\net48\txtFormat-Setup.exe artifacts\txtFormat-%VER%-setup.exe
```

`.cmd` 文件是 GBK 编码的，由 `tools\write_cmd.py` 生成 —— 用 UTF-8 编辑器直接改会在 cmd 窗口里出乱码。
改脚本内容就改 `write_cmd.py` 里的模板，再跑一次它。

### 版本号

版本唯一来源是 `installer\version.props`：运行时由 `app\core\version.py` 读取，`txtFormat.spec` 在打包时生成 PE 版本资源，安装器项目和 `build-installer.cmd` 也读取同一份配置。改版本只改 props；批处理标题由 `tools\write_cmd.py` 生成，修改后运行该脚本更新它。

构建后读取主程序与安装包的 PE 版本资源，人工与 props 对照（先将环境变量 `VER` 设为实际版本；脚本只打印结果，不自动断言版本一致）：

```bat
.venv\Scripts\python.exe tools\check_version.py artifacts\txtFormat\txtFormat.exe artifacts\txtFormat-%VER%-setup.exe
```

## 改动范围

按「要加什么」找要动的地方，别按文件名翻。

| 想加的东西 | 要改哪里 |
| --- | --- |
| 格式整理的新开关 | 三处：`core/settings.py` 的 `Settings` 字段与默认值、`ui/dialogs.py` 的 `OptionsDialog`（单选组或 `options` 列表）、`core/formatter.py` 里读取它的那一步。改了已有默认值还要加 `settings_version` 迁移，否则老配置读进来仍是旧值 |
| 新的一类审核 | `core/checkers.py` 注册检查函数、`ui/dialogs.py` 的 `REVIEW_ITEMS` 加一项、决定默认是否勾选 |
| 新的内置正则 | `core/regexlib_data.py` 追加条目（说明 / 表达式 / 替换），打包自检会验证每一条都能编译 |
| 自动化的新步骤 | `core/automation.py` 的 `STEP_TYPES` 注册 `StepSpec`（`run` + `summarize`）；带选项的步骤在 `ui/automation.py` 加一个配置小对话框 |
| 新的转换格式 | `core/convert.py` 的 `CONVERTERS` 加一项（键、扩展名、界面文案、实现），命令栏的「转换」下拉按这张表自动填充，不用改界面 |
| 命令栏按钮或菜单项 | 命令栏改 `ui/main_window.py` 的 `_build_command_bar`；菜单项在 `ui/menu_def.py` 增加数据，并在 `MainWindow._command_table` 登记对应命令。图标名须在 `ui/icons.py` 中存在 |
| 安装/卸载流程 | `installer/winforms/` 下的 `InstallForm.cs`（8 页向导）、`UninstallForm.cs`、`Program.cs`（注册表、快捷方式、解包、清理） |
| 安装包里的文件 | 主程序文件由 `tools/make_payload.py` 的过滤规则决定；`README.md` / `LICENSE` / `custreg.txt` 由 csproj 的 `EmbeddedResource` 内嵌 |
| 文档 | README 改完必须重建安装器（它被内嵌进 setup.exe，还写到安装目录）；新增根目录 md 或目录要加进同步白名单 |

## 代码结构

```
app/
  main.py            入口：QApplication、DWM 标题栏、命令行打开文件、单实例互斥
  selftest.py        打包自检（--selftest / --menutest / --popuptest），按参数懒加载
  core/              纯逻辑，无 Qt 依赖，可单独测试
    version.py       版本与作者信息
    encoding.py      编码与行尾识别、按原样回写；decode_first / read_text_any 统一编码探测
    formatter.py     格式整理 11 步
    punct.py         标点全半角、非法组合（PUNCT_RULES 规则表，审核与整理共用）、引号规范化
    numcn.py         中文数字 ↔ 阿拉伯数字
    chapter.py       章节解析、标题规范化、重排、分割
    splitter.py      按大小/章节分割、合并、批量更名
    adfilter.py      广告扫描、remove.txt 的应用
    checkers.py      八类检查
    regexlib.py      正则库封装；regexlib_data.py 是内置表达式数据
    convert.py       各格式转 TXT
    zhconv.py        简繁转换（LCMapStringEx）
    automation.py    自动化任务引擎：六种步骤、逐步执行、每步独立配置
    settings.py      选项持久化（程序目录 config.json，读入时逐项校验）
    errlog.py        未捕获异常记录与错误提示
    aboutmd.py       关于页面 Markdown 内容解析
    paths.py         源码/打包两种环境下的路径解析
  data/              typos.txt / screened.txt / pinyin.txt，可直接编辑扩充
  ui/
    theme.py         设计令牌、全局 QSS、系统强调色
    icons.py         内置 SVG 图标
    widgets.py       Card / Menu（不透明窗口 + setMask 圆角）/ CommandButton / SearchBox / Toast / CopyChip
    editor.py        行号、水线、当前行高亮、自动卷屏、阅读模式
    panels.py        文件列表面板、替换规则面板、自动化面板
    dialogs.py       选项 / 章节分割 / 合并 / 快速审核 / 转到 / 重编码 / 关于
    fontdialog.py    字体搜索、参数选择与预览
    errdialog.py     自绘错误提示
    menu_def.py      菜单数据与命令标识
    automation.py    自动化任务的编辑对话框（AutomationDialog 与各步骤配置小框）
    task.py          后台 QThread 任务封装（同一时间只允许一个后台任务）
    main_window.py   菜单、命令栏、三栏布局、业务编排
installer/
  version.props      版本与作者信息的唯一来源
  winforms/          自绘安装与卸载向导（C#，.NET Framework 4.8）
tests/               核心、界面、图标、禁用系统弹窗检查与截图脚本
tools/               图标、载荷、截图、同步、版本校验、端到端验证
```

## 图标与配色

- 图标全部是 `ui/icons.py` 里的内联 SVG，按 16px 与 20px 两档取用，换色靠传参，不依赖图片文件。
  `app/assets/app.ico` 由 `tools/make_icon.py` 现场生成（多尺寸），别手工替换。
- 配色集中在 `ui/theme.py` 的 `Color` 与 `ACCENT`：窗口底色、卡片、描边、三级文字色。
  **强调色由程序图标派生**（`core/accent.py` 读 `app.ico` 主色的 H/S，按规范 §三 的公式算四个用途色），
  所以换图标整套界面跟着换；截图里的主按钮颜色会随图标变，写文档时别把某个具体颜色写死。
- 标题栏走 DWM：圆角 33、边框 34、标题底色 35、标题文字 36、纯色背景 38，取值都来自 `Color`。
  DWM 用的是 `COLORREF`（`0x00BBGGRR`），不是 RGB，顺序写反会得到互补色。

## 界面怎么验证

```bat
.venv\Scripts\python.exe tests\test_core.py          :: 核心逻辑
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python.exe tests\test_ui.py            :: 界面交互与字体选择器
.venv\Scripts\python.exe tests\test_icons.py         :: 图标
.venv\Scripts\python.exe tests\test_no_system_popup.py :: 扫描系统弹窗与提示音等禁用模式
```

`test_ui.py` 会创建主窗口，而主窗口会读取和写入程序目录的 `config.json`；测试前应在隔离副本中运行，避免影响个人设置。后台任务测试会等待事件循环处理结果；离屏检查不能替代真实 Windows 桌面的弹层验证。

截图按需生成，产物只留在本机 `docs\`（不进发布区）：

```bat
.venv\Scripts\python.exe tools\make_shots.py          :: 主界面与各对话框，逐张独立进程
.venv\Scripts\python.exe tools\shot_installer.py      :: 安装向导逐页截图（需已编译安装器）
.venv\Scripts\python.exe tests\shot.py out.png 1440 900
```

打包产物自带自检，用来检查资源和界面（结果写 JSON）。下列菜单与弹层检查使用真实窗口；如果前面设置过离屏模式，先清除该变量：

```bat
set QT_QPA_PLATFORM=
artifacts\txtFormat\txtFormat.exe --selftest %TEMP%\tfself
artifacts\txtFormat\txtFormat.exe --menutest %TEMP%\tfmenu
artifacts\txtFormat\txtFormat.exe --popuptest %TEMP%\tfpopup
```

分别检查核心资源与界面、菜单结构与圆角裁切、字体下拉弹层几何；查看各目录下对应的 JSON 和退出码。`--popuptest` 需要真实窗口环境，另保存弹层截图；可用 `tools\check_popup_edge.py <输出目录> <size|line|weight>` 按报告坐标检查边缘。

安装包做端到端验证：静默安装 → 检查文件、快捷方式、注册表 → 从安装目录跑自检 → 静默卸载 →
确认目录、开始菜单项、`App Paths` 与卸载登记键都已清理。脚本不写死版本号：
期望版本从 `app\core\version.py` 动态读（`expect_version()`），升版本不用改它。

```bat
.venv\Scripts\python.exe tools\e2e_installer.py artifacts\txtFormat-%VER%-setup.exe
```

## 坑

一条 = 现象 + 根因 + 对策，都是实际踩过的。

- **窗口标题出现「文件名 — txtFormat - txtFormat」**：Qt 会把 `applicationDisplayName` 追加到窗口标题后面，
  而标题里已经带了程序名。对策：`app.setApplicationDisplayName("")`，标题自己拼。
- **`--selftest` 在无人值守时挂住**：自检里若调 `window.close()`，`closeEvent` 会弹出「文档已修改」的模态确认框，
  没人点就永远等。对策：自检只 `hide()`，不 `close()`。
- **缩放字号后只有部分文字变了**：QSS 里的 `font-size` 优先级高于 `setFont`。对策：改字号时重设整窗样式表
  （`stylesheet() + editor_font_qss(...)`），只调 `setFont` 不生效。
- **安装包把开发机的设置带给用户**：payload 里混进 `config.json` / `custreg.txt` / `settings.json` 就会出现。
  对策：`make_payload.py` 按文件名黑名单跳过这些，`config.json` 永远不打包。
- **安装后 `custreg.txt` 中文乱码**：这个文件是 GB18030 编码，写成 UTF-8 再读就乱。对策：安装器从内嵌资源
  按原始字节写出（`ResourceBytes`），不做任何转码。
- **许可协议页文字糊成一片**：内嵌的 `LICENSE` 是 LF 行尾，WinForms 的 `TextBox` 只认 CRLF。对策：读进来先
  `ToCrlf` 再显示。
- **安装向导侧栏图标发虚**：`Icon.ExtractAssociatedIcon` 固定返回 32×32（ico 里有大帧也拿不到），
  再 `new Icon(ico, 256, 256)` 等于 32→256→64 两次重采样，细线条 logo 被拉糊。对策：`PrivateExtractIconsW`
  按请求尺寸直接挑真帧（要 256 就拿真 256），取不到再退回老 API（`WizardShell.FrameIcon`）。
- **长文案的按钮折成两行**：向导按钮宽度默认按两字算，「结束进程并继续卸载」放不下。对策：切页时调
  `LayoutButtons(宽度)` 按该页最长文案加宽。
- **卸载最后一步删不掉 `uninstall.exe`**：卸载程序自己就是那个文件，父进程还占着句柄。对策：先把自身复制到
  临时目录再启动，由副本删原目录。
- **整篇替换后 Ctrl+Z 撤不回去、光标跳走**：`setPlainText` 会清空撤消栈。对策：全文替换统一走
  `_replace_document_text()`，用 QTextCursor 编辑块整篇替换，撤销栈与光标位置都保留。
- **旧字体对话框的 `QFontDialog.getFont()` 解包曾崩溃**：PySide6 的静态方法返回值与部分 PyQt 教程的顺序不同，
  选点阵字体时字号也可能为 -1。现在改用 `ui/fontdialog.py` 的自绘字体选择器，读取 `selected()` 并校验字号；不要把旧的静态方法直接搬回来。
- **菜单弹层四角发黑、底部一条暗线**：`WA_TranslucentBackground` 的半透明像素在 DPR 除不尽时被 DWM
  混成暗色。对策：弹层窗口完全不透明（palette 底色 = 卡片白）+ `setMask` 圆角裁切 + paintEvent 先整面
  `fillRect` 画实，别用半透明背景方案。
- **换图标后被 `build.cmd` 覆盖回旧图标**：`tools/make_icon.py` 原来在构建期用 Qt 现画图标，
  手工换上去的新 logo 一跑构建就被覆盖。对策：图标唯一来源改为品牌管线（`brand/export/<程序>/`），
  `make_icon.py` 只做搬运（命令行参数 > 环境变量 `BRAND_EXPORT_DIR` > 相对仓库探测），
  不再在构建期画图。
- **端到端脚本里写死版本号**：换版本必漏 —— 1.0.2 时代 `e2e_installer.py` 里两处 `== "1.0.2"` 断言都是
  靠人肉改的。对策：`expect_version()` 按文件路径加载 `app\core\version.py` 拿 `APP_VERSION`，
  断言全部写成 `== ver_expect`。
- **`.cmd` 里中文变问号**：用 UTF-8 存批处理，cmd 按 GBK 读就乱。对策：`tools\write_cmd.py` 以 GBK + CRLF 写出。
- **同步过去的东西少了几个文件，且不报错**：`sync_to_code.py` 的白名单是硬编码的，新文件没进列表永远同步不过去。
  对策：加完先跑一次预演，确认目标文件出现在计划里。

## 同步到发布区

编辑区（本地构建工程目录）改代码与文档，发布区是另一个目录下的 git 仓库，两侧靠脚本单向同步：

```bat
.venv\Scripts\python.exe tools\sync_to_code.py                 :: 预演，只打印计划
.venv\Scripts\python.exe tools\sync_to_code.py --apply         :: 落盘（覆盖前自动备份到 .sync-backup）
.venv\Scripts\python.exe tools\sync_to_code.py --apply --prune :: 同时删掉发布区里多余的文件
```

- 白名单是三组常量：`SOURCE_FILES`（根文件）、`SOURCE_DIRS`（目录）、跳过规则（`SKIP_PARTS` / `SKIP_NAMES` /
  `SKIP_SUFFIX` / `_` 前缀）。**新增根 md 或新目录必须加进去**，漏加的表现是永远同步不过去且不报错。
- `docs\` 与 `artifacts\` 不进发布区：截图、遗留资料、构建产物只留本机，安装包直接传 GitHub Releases。
- 脚本**不做冲突判断**：编辑区比发布区新就直接覆盖，被覆盖的旧文件会先复制到发布区 `.sync-backup\<时间戳>\`。
  所以发布区若被人手改过，先 diff 自己那份，把改动搬回编辑区，再同步；别指望脚本拦你。
- 同步只搬文件，不做任何 git 操作；提交、打 tag、发 Release 另做。
