using System;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace TxtFormatSetup
{
    /// <summary>
    /// 安装向导：欢迎 → 安装模式 → 许可协议 → 安装位置 → 附加任务 → 准备 → 安装 → 完成。
    /// </summary>
    public class InstallForm : WizardShell
    {
        const int PageWelcome = 0, PageMode = 1, PageLicense = 2,
                  PageDir = 3, PageTasks = 4, PageReady = 5;

        int _page;
        bool _busy, _done, _failed, _blocked, _dirTouched;
        string _blockedPath;      // 被占用的那个文件，用于在页面上指名道姓

        string _dir;
        InstallMode _mode = Program.Mode;
        bool _desktop = true, _start = true, _run = true;
        bool _overwriteConfig;    // 勾了「覆盖现有配置」才为 true；默认不动本地配置

        ModeCard _cardUser, _cardAll;
        Label _modeHint;
        TextBox _dirBox;
        CheckBox _cbDesktop, _cbStart, _cbRun;
        ProgressStrip _bar;
        Label _status;
        CheckBox _cbRunNow, _cbReadme;
        Label _localExe, _localCfg;   // 「选择安装位置」页的本地状态行，没有就整块不出现
        CheckBox _cbOverwrite;

        public InstallForm()
            : base(Program.AppName + " 安装", 640, 400, Program.Tagline)
        {
            _mode = Program.Mode;
            var installed = Program.InstalledDir();
            if (!string.IsNullOrEmpty(installed))
            {
                _dir = installed;
                _dirTouched = true;
            }
            else
            {
                _dir = Program.DefaultDir(_mode);
            }
        }

        /// <summary>按钮在外壳构建完成后才存在，事件必须绑在这里而不是构造函数。</summary>
        protected override void BuildPages()
        {
            NextBtn.Click += delegate { OnNext(); };
            Back.Click += delegate { OnBack(); };
            CancelBtn.Click += delegate
            {
                if (_failed) { RetryInstall(); return; }   // 失败页这一格是「重试」
                if (!_busy) Close();
            };
        }

        // ------------------------------------------------------------ 页签
        protected override void ShowPage(int index)
        {
            _page = index;
            _blocked = false;
            Body.Controls.Clear();
            Back.Visible = true;
            Back.Text = "上一步";
            CancelBtn.Visible = true;
            CancelBtn.Text = "取消";
            Back.Enabled = index > PageWelcome;
            NextBtn.Enabled = true;
            NextBtn.Text = index == PageReady ? "安装" : "下一步";
            LayoutButtons(86);          // 复位默认宽度，长文字页会自己再调宽

            switch (index)
            {
                case PageWelcome: BuildWelcome(); break;
                case PageMode: BuildMode(); break;
                case PageLicense: BuildLicense(); break;
                case PageDir: BuildDir(); break;
                case PageTasks: BuildTasks(); break;
                default: BuildReady(); break;
            }
        }

        void BuildWelcome()
        {
            TitleLabel.Text = "欢迎使用 " + Program.AppName + " 安装向导";

            L("安装程序将把 " + Program.AppName + " " + Program.Version
              + " 安装到您的计算机。\n\n"
              + "作者：" + Program.Author + "　　联系邮箱：" + Program.Email + "\n\n"
              + "继续之前，建议关闭其它正在运行的程序。", 0, 0, 428, 110);

            Strong("这个程序做什么", 0, 120, 428, 22);
            L("面向中文长文本（小说、讲稿、转录稿）的整理工具：格式整理、正则查找替换、"
              + "章节整理、快速审核，以及 HTML / EPUB / DOCX / MOBI 等格式转 TXT。"
              + "全部功能在本机完成，不联网、不上传任何内容。", 0, 144, 428, 70);
        }

        void BuildMode()
        {
            TitleLabel.Text = "选择安装模式";

            L(Program.AppName + " 可以仅为您自己安装，也可以为这台计算机上的所有用户安装。",
              0, 0, 428, 44);

            _cardUser = new ModeCard("仅为我安装（推荐）",
                "只有当前用户能使用；不需要管理员权限", false, K, 0, 50, 428, 62);
            _cardUser.Picked += delegate { PickMode(InstallMode.PerUser); };
            Body.Controls.Add(_cardUser);

            _cardAll = new ModeCard("为所有用户安装",
                "本机所有用户都能使用；需要管理员权限", true, K, 0, 122, 428, 62);
            _cardAll.Picked += delegate { PickMode(InstallMode.AllUsers); };
            Body.Controls.Add(_cardAll);

            _modeHint = L("", 0, 196, 428, 40);
            PickMode(_mode);
        }

        void PickMode(InstallMode m)
        {
            _mode = m;

            if (_cardUser != null) { _cardUser.Selected = m == InstallMode.PerUser; _cardUser.Invalidate(); }
            if (_cardAll != null) { _cardAll.Selected = m == InstallMode.AllUsers; _cardAll.Invalidate(); }

            if (!_dirTouched) _dir = Program.DefaultDir(m);

            if (_modeHint != null)
            {
                _modeHint.Text = _dirTouched
                    ? "安装位置已在后面单独设置。"
                    : "将安装到：" + Program.DefaultDir(m);
            }
        }

        void BuildLicense()
        {
            TitleLabel.Text = "许可协议";

            L("请阅读以下许可协议。安装前必须接受本协议的条款。", 0, 0, 428, 20);

            var tb = new TextBox
            {
                Text = Program.License,
                Location = P(0, 26),
                Size = Z(428, 210),
                Multiline = true,
                ReadOnly = true,
                ScrollBars = ScrollBars.Vertical,
                BorderStyle = BorderStyle.FixedSingle,
                BackColor = Theme.CardIdle,
                Font = new Font("Consolas", 8.5f),
                WordWrap = true
            };
            Body.Controls.Add(tb);
        }

        void BuildDir()
        {
            TitleLabel.Text = "选择安装位置";

            L("安装程序将把 " + Program.AppName + " 安装到下面的文件夹。\n"
              + "若要装到其它文件夹，点「浏览」选择目标文件夹。", 0, 0, 428, 40);

            _dirBox = Box(_dir, 0, 48, 328, 24);

            var browse = SmallButton("浏览…", 338, 46, 90, 27);
            browse.Click += delegate
            {
                var picked = FolderPicker.Pick(this, "选择 " + Program.AppName + " 的安装位置");
                if (string.IsNullOrEmpty(picked)) return;

                // 选完自动补一层程序名
                var trimmed = picked.TrimEnd('\\');
                var name = Path.GetFileName(trimmed);
                var full = string.Equals(name, Program.AppId, StringComparison.OrdinalIgnoreCase)
                    ? trimmed
                    : Path.Combine(trimmed, Program.AppId);

                _dirTouched = true;
                _dirBox.Text = full;
                RefreshLocalState();       // 换了目录要重新判定
            };

            L(SizeText(), 0, 84, 428, 20);

            // ---- 本地状态：没有就整块不出现（规范 §三.2）
            _localExe = L("", 0, 118, 428, 20);
            _localCfg = L("", 0, 142, 428, 20);
            _cbOverwrite = Check("覆盖现有配置（恢复为默认设置）", 0, 166, 380, false);
            _cbOverwrite.CheckedChanged += delegate { _overwriteConfig = _cbOverwrite.Checked; };

            // 手动输入、粘路径、浏览选完都要跟着刷新
            _dirBox.TextChanged += delegate { RefreshLocalState(); };
            RefreshLocalState();
        }

        /// <summary>已装版本 → 一行结论文案。降级必须说清楚，别让用户默默退回旧版。</summary>
        static string UpgradeText(Program.UpgradeKind kind, string installed)
        {
            var have = string.IsNullOrEmpty(installed) ? "未知版本" : "v" + installed;
            var now = "v" + Program.Version;

            switch (kind)
            {
                case Program.UpgradeKind.Update:
                    return "该位置已安装 " + have + "，将更新到 " + now + "。";
                case Program.UpgradeKind.Same:
                    return "该位置已安装 " + have + "（与安装包相同），将重新安装覆盖。";
                case Program.UpgradeKind.Downgrade:
                    return "该位置已安装 " + have + "，比本安装包 " + now + " 新。继续将降级到 " + now + "。";
                case Program.UpgradeKind.Unknown:
                    return "该位置已安装 " + Program.AppName + "（" + have + "），将覆盖程序文件。";
                default:
                    return "";
            }
        }

        /// <summary>
        /// 按当前路径刷新「本地状态」区：有已装程序 / 有配置才显示，都没有就整块隐藏。
        /// 切到没有配置的目录时，复选框要连勾选状态一起复位，不能把上一个目录的选择带过去。
        /// </summary>
        void RefreshLocalState()
        {
            if (_localExe == null || _localCfg == null || _cbOverwrite == null) return;

            var dir = _dirBox == null ? _dir : _dirBox.Text.Trim();
            bool hasExe = false, hasCfg = false;
            Program.UpgradeKind kind = Program.UpgradeKind.Fresh;
            string installed = null;
            try
            {
                if (!string.IsNullOrEmpty(dir) && Path.IsPathRooted(dir))
                {
                    hasExe = File.Exists(Program.ExePathIn(dir));
                    hasCfg = Program.HasConfig(dir);
                    if (hasExe) kind = Program.DetectUpgrade(dir, out installed);
                }
            }
            catch { }

            _localExe.Visible = hasExe;
            _localExe.Text = hasExe ? UpgradeText(kind, installed) : "";
            // 降级用警示色，其它用普通灰
            _localExe.ForeColor = kind == Program.UpgradeKind.Downgrade ? Theme.Warn : Theme.Muted;

            _localCfg.Visible = hasCfg;
            _localCfg.Text = hasCfg ? "检测到本地已有配置，将保留你现有的设置。" : "";

            _cbOverwrite.Visible = hasCfg;
            _cbOverwrite.Enabled = hasCfg;
            if (!hasCfg) _cbOverwrite.Checked = false;   // 没配置就不可能覆盖
            _overwriteConfig = _cbOverwrite.Checked;

            // 依次紧凑排布，没有的那块不占位
            int y = 118;
            if (hasExe) { _localExe.Location = P(0, y); y += 24; }
            if (hasCfg)
            {
                _localCfg.Location = P(0, y);
                _cbOverwrite.Location = P(0, y + 24);
            }
        }

        static string SizeText()
        {
            try
            {
                using (var s = typeof(Program).Assembly.GetManifestResourceStream("payload.zip"))
                {
                    if (s != null)
                    {
                        // 按解压后的体积算，压缩包大小会明显偏小
                        using (var zip = new System.IO.Compression.ZipArchive(
                                   s, System.IO.Compression.ZipArchiveMode.Read))
                        {
                            long total = 0;
                            foreach (var e in zip.Entries) total += e.Length;
                            var mb = total / 1048576.0;
                            return "所需磁盘空间：约 " + mb.ToString("0.0") + " MB";
                        }
                    }
                }
            }
            catch { }
            return "所需磁盘空间：约 65 MB";
        }

        void BuildTasks()
        {
            TitleLabel.Text = "选择附加任务";

            L("选择安装程序要执行的附加任务，然后点「下一步」。", 0, 0, 428, 20);

            Strong("附加图标：", 0, 34, 428, 22);
            _cbDesktop = Check("创建桌面快捷方式", 16, 60, 320, _desktop);
            _cbStart = Check("创建开始菜单快捷方式", 16, 86, 320, _start);

            Strong("完成后：", 0, 124, 428, 22);
            _cbRun = Check("立即运行 " + Program.AppName, 16, 150, 320, _run);
        }

        void BuildReady()
        {
            TitleLabel.Text = "准备安装";

            // Body 区只有 264px 高，最多要放 5 段（模式/位置/操作类型/本地配置/附加任务），
            // 所以导语压成一行、每段步进 42px，别用宽松行距，否则最后一段会被分隔线裁掉。
            L("点「安装」开始安装，或点「上一步」复查或更改设置。", 0, 0, 428, 20);

            int y = 26;
            const int Step = 42;

            Strong("安装模式：", 0, y, 428, 20);
            L(_mode == InstallMode.AllUsers
                ? "为所有用户安装（写入 Program Files，需要管理员权限）"
                : "仅为我安装（写入当前用户目录）", 0, y + 18, 428, 18);
            y += Step;

            Strong("安装位置：", 0, y, 428, 20);
            L(_dir, 0, y + 18, 428, 18);
            y += Step;

            // 已装过就说明这次是更新 / 重装 / 降级（规范 §三.3）
            string installed;
            var kind = Program.DetectUpgrade(_dir, out installed);
            if (kind != Program.UpgradeKind.Fresh)
            {
                Strong("操作类型：", 0, y, 428, 20);
                var lbl = L(ActionText(kind, installed), 0, y + 18, 428, 18);
                if (kind == Program.UpgradeKind.Downgrade) lbl.ForeColor = Theme.Warn;
                y += Step;
            }

            // 只在目标目录确实有配置时才出现（规范 §三.2：没有就不占位）
            if (Program.HasConfig(_dir))
            {
                Strong("本地配置：", 0, y, 428, 20);
                L(_overwriteConfig
                    ? "覆盖（恢复为默认设置）"
                    : "保留现有配置", 0, y + 18, 428, 18);
                y += Step;
            }

            Strong("附加任务：", 0, y, 428, 20);
            L(TaskSummary(), 0, y + 18, 428, 44);
        }

        /// <summary>「准备安装」页的操作类型文案，比页面提示更短。</summary>
        static string ActionText(Program.UpgradeKind kind, string installed)
        {
            var have = string.IsNullOrEmpty(installed) ? "未知版本" : "v" + installed;
            switch (kind)
            {
                case Program.UpgradeKind.Update:
                    return "更新 " + have + " → v" + Program.Version;
                case Program.UpgradeKind.Same:
                    return "重新安装（已装 " + have + "，版本相同）";
                case Program.UpgradeKind.Downgrade:
                    return "降级 " + have + " → v" + Program.Version + "（已装版本更新）";
                case Program.UpgradeKind.Unknown:
                    return "覆盖安装（已装版本无法识别）";
                default:
                    return "全新安装";
            }
        }

        string TaskSummary()
        {
            var s = "无";
            if (_desktop && _start) s = "桌面快捷方式、开始菜单快捷方式";
            else if (_desktop) s = "桌面快捷方式";
            else if (_start) s = "开始菜单快捷方式";
            if (_run) s += "；安装完成后运行程序";
            return s;
        }

        // ------------------------------------------------------------ 交互
        void OnBack()
        {
            if (_busy || _done || _failed) return;

            // 从「文件被占用」页返回，退回「准备安装」让用户改设置
            if (_blocked)
            {
                _blocked = false;
                _blockedPath = null;
                ShowPage(PageReady);
                return;
            }
            if (_page > PageWelcome) ShowPage(_page - 1);
        }

        void OnNext()
        {
            if (_done)
            {
                if (_cbRunNow != null && _cbRunNow.Checked) Program.Launch(_dir);
                if (_cbReadme != null && _cbReadme.Checked) Program.OpenReadme(_dir);
                Close();
                return;
            }

            if (_blocked) { EndRunningAndRetry(); return; }
            if (_failed) { Close(); return; }
            if (_busy) return;

            switch (_page)
            {
                case PageMode:
                    {
                        if (_mode == InstallMode.AllUsers && !Program.IsElevated)
                        {
                            var r = MessageBox.Show(this,
                                "「为所有用户安装」需要管理员权限。\n\n"
                                + "接下来会请求提升权限并重新启动安装程序，你的选择会被保留。",
                                Program.AppName, MessageBoxButtons.OKCancel, MessageBoxIcon.Information);
                            if (r != DialogResult.OK) return;

                            if (Program.RelaunchAsAdmin("--all-users")) { Close(); return; }

                            MessageBox.Show(this,
                                "没有获得管理员权限，已取消。\n可以改选「仅为我安装」，不需要提权。",
                                Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                            return;
                        }
                        ShowPage(PageLicense);
                        return;
                    }
                case PageDir:
                    {
                        var err = CheckDir(_dirBox.Text.Trim());
                        if (err != null)
                        {
                            MessageBox.Show(this, err, Program.AppName,
                                MessageBoxButtons.OK, MessageBoxIcon.Warning);
                            return;
                        }
                        _dir = _dirBox.Text.Trim();
                        _dirTouched = true;
                        // 「该位置已存在、是否覆盖」的弹窗已移除（规范 §一 / §三.2）：
                        // 版本结论与配置保留与否都做在页面上，下一页汇总再确认一次。
                        ShowPage(PageTasks);
                        return;
                    }
                case PageTasks:
                    {
                        if (_cbDesktop != null) _desktop = _cbDesktop.Checked;
                        if (_cbStart != null) _start = _cbStart.Checked;
                        if (_cbRun != null) _run = _cbRun.Checked;
                        ShowPage(PageReady);
                        return;
                    }
                case PageReady:
                    {
                        // 点「安装」前先探一次：目标程序正开着就别等写文件时才炸
                        if (File.Exists(Program.ExePathIn(_dir))
                            && Program.RunningInstances(_dir).Length > 0)
                        {
                            NextBtn.Text = "结束进程并继续";
                            ShowBlocked(Program.ExePathIn(_dir));
                            return;
                        }
                        StartInstall();
                        return;
                    }
                default:
                    ShowPage(_page + 1);
                    return;
            }
        }

        static string CheckDir(string dir)
        {
            if (string.IsNullOrEmpty(dir)) return "请填写安装位置。";
            if (!Path.IsPathRooted(dir))
                return "安装位置要写完整路径，例如：\nD:\\Apps\\txtFormat";

            bool created = !Directory.Exists(dir);
            try
            {
                Directory.CreateDirectory(dir);
                var probe = Path.Combine(dir, ".tf-write-test");
                File.WriteAllText(probe, "ok");
                File.Delete(probe);
            }
            catch (Exception ex)
            {
                return "无法写入该目录：\n" + ex.Message
                     + "\n\nProgram Files 这类系统目录需要管理员权限，建议改选「为所有用户安装」或装到用户目录。";
            }
            finally
            {
                // 只是试探可写性，别在用户取消时留下一个空目录
                try
                {
                    if (created && Directory.Exists(dir)
                        && Directory.GetFileSystemEntries(dir).Length == 0)
                        Directory.Delete(dir);
                }
                catch { }
            }
            return null;
        }

        // ------------------------------------------------------------ 安装
        void StartInstall()
        {
            _busy = true;
            _blocked = false;
            _blockedPath = null;
            Body.Controls.Clear();
            TitleLabel.Text = "正在安装";
            Back.Visible = false;
            NextBtn.Text = "安装";
            NextBtn.Enabled = false;
            CancelBtn.Text = "取消";
            CancelBtn.Enabled = false;

            L(Program.AppName + " 正在安装到：" + _dir, 0, 0, 428, 40);

            _bar = new ProgressStrip(K, 0, 60, 428, 10);
            Body.Controls.Add(_bar);

            _status = L("准备中…", 0, 78, 428, 160);

            var dir = _dir;
            var mode = _mode;
            var th = new Thread(delegate()
            {
                try
                {
                    Program.DoInstall(dir, mode, _desktop, _start, _overwriteConfig,
                        delegate(int pct, string name)
                    {
                        Ui(delegate
                        {
                            if (_bar == null) return;
                            _bar.Value = Math.Min(100, pct);
                            _status.Text = pct + "%　" + name;
                        });
                    });
                    Ui(ShowFinish);
                }
                catch (Exception ex)
                {
                    // 文件被占用 → 转成可操作的「正在运行」页，而不是一句错误把用户晾在那
                    var msg = ex.Message;
                    var path = Program.QuotedPath(msg);
                    Ui(delegate
                    {
                        if (Program.LooksLikeFileInUse(msg)
                            || (File.Exists(Program.ExePathIn(_dir))
                                && Program.RunningInstances(_dir).Length > 0))
                        {
                            NextBtn.Text = "结束进程并继续";
                            ShowBlocked(path ?? Program.ExePathIn(_dir));
                        }
                        else
                        {
                            ShowFailure(msg);
                        }
                    });
                }
            });
            th.IsBackground = true;
            th.Start();
        }

        void ShowFailure(string msg)
        {
            _busy = false;
            _failed = true;
            Body.Controls.Clear();
            TitleLabel.Text = "安装未完成";
            Back.Visible = false;
            NextBtn.Text = "关闭";
            NextBtn.Enabled = true;

            L("安装过程中出错：\n\n" + msg + "\n\n"
              + "可以点「重试」再装一次（比如先关掉占用文件的程序），"
              + "或点「关闭」退出后重新运行安装程序。",
              0, 0, 428, 140);

            // 失败页给一个「重试」：把上一步/取消的位置复用成一个重试按钮
            CancelBtn.Visible = true;
            CancelBtn.Enabled = true;
            CancelBtn.Text = "重试";
        }

        /// <summary>失败页的「重试」：关掉可能还在运行的实例，重新走一遍安装。</summary>
        void RetryInstall()
        {
            _failed = false;
            CancelBtn.Text = "取消";
            Program.KillRunning(_dir);
            StartInstall();
        }

        void ShowFinish()
        {
            _busy = false;
            _done = true;
            Body.Controls.Clear();

            TitleLabel.Text = "正在完成 " + Program.AppName + " 安装向导";
            Back.Visible = false;
            CancelBtn.Visible = false;
            NextBtn.Text = "完成";
            NextBtn.Enabled = true;

            L(Program.AppName + " 已安装在您的计算机上。\n\n"
              + "作者：" + Program.Author + "　　联系邮箱：" + Program.Email
              + "\n\n桌面与开始菜单都有快捷方式，卸载可从「设置 → 应用」里操作。", 0, 0, 428, 106);

            Strong("安装位置：", 0, 112, 428, 22);
            L(_dir, 0, 134, 428, 20);

            _cbRunNow = Check("立即运行 " + Program.AppName, 0, 170, 380, _run);
            _cbReadme = Check("查看使用说明（" + Program.ReadmeName + "）", 0, 196, 380, false);
        }

        void Ui(Action a)
        {
            try { if (IsHandleCreated) BeginInvoke(a); } catch { }
        }

        void ShowBlocked(string path)
        {
            _busy = false;
            _failed = false;
            _blocked = true;
            _blockedPath = path;
            Body.Controls.Clear();

            TitleLabel.Text = Program.AppName + " 正在运行";
            Back.Visible = true;
            Back.Text = "上一步";
            Back.Enabled = true;
            CancelBtn.Visible = true;
            CancelBtn.Enabled = true;
            CancelBtn.Text = "取消";
            NextBtn.Visible = true;
            NextBtn.Enabled = true;
            NextBtn.Text = "结束进程并继续";
            LayoutButtons(126);          // 这个按钮文字长，需要更宽，否则被折成两行

            Strong("需要写入的文件正被占用：", 0, 0, 428, 22);
            L(_dir, 0, 24, 428, 20);
            if (!string.IsNullOrEmpty(path)) L(path, 0, 46, 428, 20);

            Strong("请选择一种处理方式：", 0, 80, 428, 22);
            L("· 点「结束进程并继续」—— 自动关闭正在运行的 " + Program.AppName
              + "（未保存的操作会丢失），随后立即继续安装；\n"
              + "· 点「上一步」—— 回到上一页更改设置；\n"
              + "· 若上一步无效，请手动关闭 " + Program.AppName
              + "，再点「结束进程并继续」重试。", 0, 104, 428, 80);
        }

        /// <summary>结束占用进程后重试安装；仍被占用则停在这一页，让用户手动处理。</summary>
        void EndRunningAndRetry()
        {
            NextBtn.Enabled = false;
            int n = Program.KillRunning(_dir);

            if (Program.RunningInstances(_dir).Length > 0)
            {
                NextBtn.Enabled = true;
                MessageBox.Show(this,
                    "没能结束正在运行的 " + Program.AppName + "（权限不足或进程未响应）。\n\n"
                    + "请用任务管理器手动结束它，或重启计算机后再运行安装程序。",
                    Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            if (n > 0) Thread.Sleep(300);   // 等文件句柄真正释放
            StartInstall();
        }
    }
}