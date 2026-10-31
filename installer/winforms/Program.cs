using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace TxtFormatSetup
{
    /// <summary>安装范围。</summary>
    public enum InstallMode { PerUser, AllUsers }

    static class Program
    {
        /// <summary>程序名只用英文。</summary>
        public const string AppName = "txtFormat";
        public const string AppId = "txtFormat";
        public const string Tagline = "长文本整理工具";
        public const string Author = "Rex Lee";
        public const string Email = "rexlee@rexleepro.com";

        public const string AppExe = "txtFormat.exe";
        public const string ReadmeName = "README.md";
        /// <summary>自定义正则示例，随程序一起装（首次安装才放，升级不覆盖）。</summary>
        public const string CustRegName = "custreg.txt";
        /// <summary>程序本体的设置文件，按规范 §十 与 exe 同目录；payload 里没有它，
        /// 不勾「覆盖现有配置」就天然不会碰（规范 §三.2）。</summary>
        public const string SettingsName = "config.json";

        const string UninstallSubKey =
            @"Software\Microsoft\Windows\CurrentVersion\Uninstall\txtFormat";

        const string AppPathsSubKey =
            @"Software\Microsoft\Windows\CurrentVersion\App Paths\txtFormat.exe";

        // ------------------------------------------------------------ 基本信息
        static string _version;

        public static string Version
        {
            get
            {
                if (_version == null)
                {
                    var asm = typeof(Program).Assembly;
                    var info = (AssemblyInformationalVersionAttribute)Attribute.GetCustomAttribute(
                        asm, typeof(AssemblyInformationalVersionAttribute));
                    if (info != null && !string.IsNullOrEmpty(info.InformationalVersion))
                    {
                        var v = info.InformationalVersion;
                        int plus = v.IndexOf('+');
                        if (plus > 0) v = v.Substring(0, plus);
                        _version = v.Trim();
                    }
                    if (string.IsNullOrEmpty(_version))
                    {
                        var nv = asm.GetName().Version;
                        _version = nv == null ? "0.0.0" : nv.Major + "." + nv.Minor + "." + nv.Build;
                    }
                }
                return _version;
            }
        }

        // ------------------------------------------------------------ 安装范围

        /// <summary>
        /// 目标目录里已装版本的对比结论。决定「选择安装位置」页的文案和「准备安装」页的操作类型。
        /// </summary>
        public enum UpgradeKind
        {
            /// <summary>目录是空的，没装过。</summary>
            Fresh,
            /// <summary>已装版本比安装包旧 —— 正常升级。</summary>
            Update,
            /// <summary>版本相同 —— 重装 / 修复。</summary>
            Same,
            /// <summary>已装版本比安装包新 —— 降级，要提醒用户。</summary>
            Downgrade,
            /// <summary>exe 在但版本读不出来（手工拷的 / 文件损坏）。</summary>
            Unknown
        }

        /// <summary>读目标目录里已安装程序的版本号，读不到返回 null。</summary>
        public static string InstalledVersion(string dir)
        {
            try
            {
                var exe = ExePathIn(dir);
                if (!File.Exists(exe)) return null;

                var vi = FileVersionInfo.GetVersionInfo(exe);
                if (!string.IsNullOrEmpty(vi.ProductVersion)) return vi.ProductVersion.Trim();
                if (!string.IsNullOrEmpty(vi.FileVersion)) return vi.FileVersion.Trim();
            }
            catch { }
            return null;
        }

        /// <summary>把 "1.2.3" / "1.2.3.0" 这类字符串解析成可比较的版本；解析失败返回 null。</summary>
        static Version ParseVersion(string s)
        {
            if (string.IsNullOrEmpty(s)) return null;

            // 只取开头的数字和点，丢掉 "1.2.3-beta" 这类后缀
            var sb = new StringBuilder();
            foreach (var c in s.Trim())
            {
                if (char.IsDigit(c) || c == '.') sb.Append(c);
                else break;
            }

            var text = sb.ToString().Trim('.');
            if (text.Length == 0) return null;

            // 一律补齐到四段再比较。不全补齐的话，"1.2.3" 与 "1.2.3.0" 会因分量个数不同
            // 被判成不相等（Version 把缺失分量当 -1），同版本被误报成更新或降级。
            var parts = text.Split('.');
            int keep = Math.Min(parts.Length, 4);
            var padded = new StringBuilder();
            for (int i = 0; i < 4; i++)
            {
                if (i > 0) padded.Append('.');
                padded.Append(i < keep ? parts[i].PadLeft(1, '0') : "0");
            }

            try { return new Version(padded.ToString()); }
            catch { return null; }
        }

        /// <summary>
        /// 纯比较：已装版本 vs 本安装包版本 → 五态之一。不碰文件系统，便于单独测试。
        /// </summary>
        public static UpgradeKind ClassifyVersions(string installed, string package)
        {
            var oldV = ParseVersion(installed);
            var newV = ParseVersion(package);
            if (oldV == null || newV == null) return UpgradeKind.Unknown;

            int cmp = oldV.CompareTo(newV);
            if (cmp < 0) return UpgradeKind.Update;
            if (cmp == 0) return UpgradeKind.Same;
            return UpgradeKind.Downgrade;
        }

        /// <summary>判定本次安装属于全新安装 / 更新 / 重装 / 降级。</summary>
        public static UpgradeKind DetectUpgrade(string dir, out string installed)
        {
            installed = null;
            try
            {
                if (!File.Exists(ExePathIn(dir))) return UpgradeKind.Fresh;
            }
            catch { return UpgradeKind.Fresh; }

            installed = InstalledVersion(dir);
            return ClassifyVersions(installed, Version);
        }

        /// <summary>仅供校验工程调用，暴露版本解析以便单独测试容错规则（规范 §三.3）。</summary>
        public static Version ParseVersionForTest(string s) { return ParseVersion(s); }

        // ------------------------------------------------------------ 安装范围
        public static InstallMode Mode = InstallMode.PerUser;

        /// <summary>提权重启后从第几页接着走（--resume=N，0 或未给表示正常从头开始）。</summary>
        public static int ResumePage;

        static bool? _elevated;

        /// <summary>当前进程是否已提权（管理员）。</summary>
        public static bool IsElevated
        {
            get
            {
                if (_elevated == null)
                {
                    try
                    {
                        using (var id = WindowsIdentity.GetCurrent())
                            _elevated = new WindowsPrincipal(id).IsInRole(WindowsBuiltInRole.Administrator);
                    }
                    catch { _elevated = false; }
                }
                return _elevated.Value;
            }
        }

        /// <summary>64 位 Program Files。</summary>
        public static string ProgramFilesDir
        {
            get
            {
                var pf = Environment.GetEnvironmentVariable("ProgramW6432");
                if (string.IsNullOrEmpty(pf))
                    pf = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
                return pf;
            }
        }

        /// <summary>按安装范围给不同的默认目录。</summary>
        public static string DefaultDir(InstallMode mode)
        {
            if (mode == InstallMode.AllUsers)
                return Path.Combine(ProgramFilesDir, AppId);

            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Programs", AppId);
        }

        public static string DefaultDir() { return DefaultDir(Mode); }

        public static string ExePathIn(string dir) { return Path.Combine(dir, AppExe); }
        public static string ReadmePathIn(string dir) { return Path.Combine(dir, ReadmeName); }

        // ------------------------------------------------------------ 本地配置
        /// <summary>
        /// 安装目录里用户可改的自定义正则文件。txtFormat 用它装自定义正则示例，
        /// 用户通常会自己往里加条目 —— 升级时默认不动它（规范 §三.2）。
        /// </summary>
        /// <summary>自定义正则 / 词表文件（custreg.txt）的完整路径 —— **不是**设置文件，
        /// 设置文件走 <see cref="SettingsPathIn"/>。</summary>
        public static string ConfigPathIn(string dir) { return Path.Combine(dir, CustRegName); }

        /// <summary>安装目录里的设置文件（程序本体按规范 §十 写在 exe 同目录）。</summary>
        public static string SettingsPathIn(string dir) { return Path.Combine(dir, SettingsName); }

        /// <summary>目标目录里是否已经有用户配置（设置或自定义正则，任一即算）。</summary>
        public static bool HasConfig(string dir)
        {
            try
            {
                return File.Exists(SettingsPathIn(dir)) || File.Exists(ConfigPathIn(dir));
            }
            catch { return false; }
        }

        public static bool IsUnderProgramFiles(string dir)
        {
            try
            {
                var pf = ProgramFilesDir;
                return !string.IsNullOrEmpty(pf)
                       && dir.StartsWith(pf, StringComparison.OrdinalIgnoreCase);
            }
            catch { return false; }
        }

        /// <summary>
        /// 本机装在**别处**的那一份：已装位置与 <paramref name="dir"/> 不同才返回路径。
        /// 给「选择安装位置」页用 —— 已装过、这次又换了安装模式时，不能让页面看着像首次安装。
        /// </summary>
        public static string OtherInstalledDir(string dir)
        {
            try
            {
                var installed = InstalledDir();
                if (string.IsNullOrEmpty(installed)) return null;
                if (!string.IsNullOrEmpty(dir) && Path.IsPathRooted(dir)
                    && string.Equals(Path.GetFullPath(installed).TrimEnd('\\'),
                                     Path.GetFullPath(dir).TrimEnd('\\'),
                                     StringComparison.OrdinalIgnoreCase))
                    return null;
                return Directory.Exists(installed) ? installed : null;
            }
            catch { return null; }
        }

        // ------------------------------------------------------------ 用户数据目录
        /// <summary>个人设置与自定义文件的存放处（与 app/core/settings.py 一致）。</summary>
        public static string DataDir
        {
            get
            {
                var baseDir = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
                if (string.IsNullOrEmpty(baseDir)) baseDir = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                return Path.Combine(baseDir, AppId);
            }
        }

        // ------------------------------------------------------------ 目录位置
        /// <summary>桌面可能被 OneDrive 重定向，必须读注册表拿真实路径。</summary>
        public static string DesktopDir(bool allUsers)
        {
            if (allUsers)
            {
                var common = Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory);
                if (!string.IsNullOrEmpty(common)) return common;
            }

            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(
                    @"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"))
                {
                    var v = k == null ? null : k.GetValue("Desktop") as string;
                    if (!string.IsNullOrEmpty(v))
                    {
                        var p = Environment.ExpandEnvironmentVariables(v);
                        if (Directory.Exists(p)) return p;
                    }
                }
            }
            catch { }

            var d = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            if (!Directory.Exists(d))
            {
                try { Directory.CreateDirectory(d); } catch { }
            }
            return d;
        }

        public static string StartMenuDir(bool allUsers)
        {
            var f = allUsers
                ? Environment.SpecialFolder.CommonPrograms
                : Environment.SpecialFolder.Programs;
            return Environment.GetFolderPath(f);
        }

        // ------------------------------------------------------------ 注册表
        static RegistryKey OpenUninstallKey(bool allUsers, bool writable)
        {
            var hive = allUsers ? RegistryHive.LocalMachine : RegistryHive.CurrentUser;
            var view = (allUsers && Environment.Is64BitOperatingSystem)
                ? RegistryView.Registry64
                : RegistryView.Default;

            var root = RegistryKey.OpenBaseKey(hive, view);
            return writable ? root.CreateSubKey(UninstallSubKey) : root.OpenSubKey(UninstallSubKey);
        }

        /// <summary>已安装的目录：先找「所有用户」，再找「当前用户」。</summary>
        public static string InstalledDir()
        {
            foreach (var all in new[] { true, false })
            {
                try
                {
                    using (var k = OpenUninstallKey(all, false))
                    {
                        var v = k == null ? null : k.GetValue("InstallLocation") as string;
                        if (!string.IsNullOrEmpty(v)) return v;
                    }
                }
                catch { }
            }
            return null;
        }

        public static bool InstalledForAllUsers()
        {
            try
            {
                using (var k = OpenUninstallKey(true, false)) return k != null;
            }
            catch { return false; }
        }

        static void WriteUninstallEntry(string dir, InstallMode mode)
        {
            try
            {
                using (var k = OpenUninstallKey(mode == InstallMode.AllUsers, true))
                {
                    if (k == null) return;
                    k.SetValue("DisplayName", AppName);
                    k.SetValue("DisplayVersion", Version);
                    k.SetValue("Publisher", Author);
                    k.SetValue("Contact", Email);
                    k.SetValue("InstallLocation", dir);
                    k.SetValue("DisplayIcon", ExePathIn(dir));
                    k.SetValue("UninstallString", "\"" + Path.Combine(dir, "uninstall.exe") + "\"");
                    k.SetValue("QuietUninstallString",
                        "\"" + Path.Combine(dir, "uninstall.exe") + "\" --uninstall");
                    k.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
                    k.SetValue("EstimatedSize", DirSizeKb(dir), RegistryValueKind.DWord);
                    k.SetValue("NoModify", 1, RegistryValueKind.DWord);
                    k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                }
            }
            catch { }
        }

        /// <summary>支持 Win+R 直接输入 txtFormat 启动。</summary>
        static void WriteAppPath(string dir, InstallMode mode)
        {
            try
            {
                var hive = mode == InstallMode.AllUsers ? RegistryHive.LocalMachine : RegistryHive.CurrentUser;
                var view = (mode == InstallMode.AllUsers && Environment.Is64BitOperatingSystem)
                    ? RegistryView.Registry64
                    : RegistryView.Default;

                using (var root = RegistryKey.OpenBaseKey(hive, view))
                using (var k = root.CreateSubKey(AppPathsSubKey))
                {
                    if (k == null) return;
                    k.SetValue("", ExePathIn(dir));
                    k.SetValue("Path", dir);
                }
            }
            catch { }
        }

        /// <summary>
        /// 注册表要扫的两个视图（规范 §五：旧版本可能写在 32 位视图里，
        /// 只清 64 位会在「设置 → 应用」里留一条删不掉的登记项）。
        /// </summary>
        static readonly RegistryView[] Views =
        {
            RegistryView.Registry64,
            RegistryView.Registry32,
        };

        static void RemoveAppPaths()
        {
            foreach (var all in new[] { true, false })
            {
                foreach (var view in Views)
                {
                    try
                    {
                        var hive = all ? RegistryHive.LocalMachine : RegistryHive.CurrentUser;
                        using (var root = RegistryKey.OpenBaseKey(hive, view))
                        {
                            if (root.OpenSubKey(AppPathsSubKey) != null)
                                root.DeleteSubKeyTree(AppPathsSubKey, false);
                        }
                    }
                    catch { }
                }
            }
        }

        static void RemoveUninstallEntries()
        {
            foreach (var all in new[] { true, false })
            {
                foreach (var view in Views)
                {
                    try
                    {
                        var hive = all ? RegistryHive.LocalMachine : RegistryHive.CurrentUser;
                        using (var root = RegistryKey.OpenBaseKey(hive, view))
                        {
                            if (root.OpenSubKey(UninstallSubKey) != null)
                                root.DeleteSubKeyTree(UninstallSubKey, false);
                        }
                    }
                    catch { }
                }
            }
        }

        static int DirSizeKb(string dir)
        {
            try
            {
                long sum = 0;
                foreach (var f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                {
                    try { sum += new FileInfo(f).Length; } catch { }
                }
                return (int)Math.Min(int.MaxValue, sum / 1024);
            }
            catch { return 4096; }
        }

        // ------------------------------------------------------------ 入口
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern bool SetProcessDPIAware();

        [STAThread]
        static void Main(string[] args)
        {
            // 必须在建任何窗口前声明 DPI 感知，否则 150% 缩放下窗口会被系统按比例缩小
            try { SetProcessDPIAware(); } catch { }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            // 未捕获异常：自绘对话框兜住（规范 §二.1 —— 只能弹的场景用自绘，
            // 且一律不响提示音）。挂上以后任何界面异常都不会静默闪退。
            Application.ThreadException += delegate (object s, ThreadExceptionEventArgs e)
            {
                ShowFatal(e.Exception);
            };
            AppDomain.CurrentDomain.UnhandledException += delegate (object s, UnhandledExceptionEventArgs e)
            {
                ShowFatal(e.ExceptionObject as Exception);
            };

            // 卸载：先复制到临时目录，再从临时目录执行，才能真正删掉安装目录
            int runIdx = Array.IndexOf(args, "--uninstall-run");
            if (runIdx >= 0 && args.Length > runIdx + 1)
            {
                var targetDir = args[runIdx + 1];
                // 静默卸载：/S、--silent 或 --quiet 都认，用于「设置 → 应用」的静默卸载与自动化验证
                if (HasFlag(args, "--silent") || HasFlag(args, "/S") || HasFlag(args, "--quiet"))
                {
                    int code = 0;
                    try
                    {
                        RemoveAll(targetDir, true, null);   // 静默卸载保留个人设置
                    }
                    catch { code = 1; }                     // 仍被占用 / 有残留：退出码照实报
                    // 成功才连安装目录里的 uninstall.exe 一起清；失败必须保住它，
                    // 否则用户卸不掉、也没有卸不载入口了（e2e 实测踩过）。
                    ScheduleCleanup(targetDir, code == 0);
                    Environment.Exit(code);
                    return;
                }
                Application.Run(new UninstallForm(targetDir));
                return;
            }

            var self = Path.GetFileNameWithoutExtension(Application.ExecutablePath);
            bool isUninstall = self.Equals("uninstall", StringComparison.OrdinalIgnoreCase)
                               || (args.Length > 0 && args[0] == "--uninstall");

            if (isUninstall)
            {
                RelaunchForUninstall(HasFlag(args, "--silent") || HasFlag(args, "/S") || HasFlag(args, "--quiet"));
                return;
            }

            // 提权重启后的实例：安装范围已经确定
            if (Array.IndexOf(args, "--all-users") >= 0) Mode = InstallMode.AllUsers;

            // 提权重启后接着走（--resume=N）：用户刚选完模式，不该再从欢迎页点一遍
            foreach (var a in args)
                if (a.StartsWith("--resume=", StringComparison.Ordinal))
                {
                    int page;
                    if (int.TryParse(a.Substring("--resume=".Length), out page)) ResumePage = page;
                }

            if (args.Length > 0 && args[0] == "--silent")
            {
                try
                {
                    DoInstall(DefaultDir(), Mode, true, true, null);
                    Environment.Exit(0);
                }
                catch { Environment.Exit(1); }
                return;
            }

            Application.Run(new InstallForm());
        }

        /// <summary>未捕获异常的统一出口：写临时日志 + 自绘错误框（带「打开日志」），不发声（规范 §二.1）。</summary>
        static void ShowFatal(Exception ex)
        {
            // 1) 日志：%TEMP%\<AppId>-setup-error.log，带版本号和时间戳，用户可整份反馈
            string log = null;
            try
            {
                log = Path.Combine(Path.GetTempPath(), AppId + "-setup-error.log");
                File.AppendAllText(log,
                    "---- " + DateTime.Now + "  v" + Version + Environment.NewLine
                    + (ex == null ? "(未知异常)" : ex.ToString())
                    + Environment.NewLine + Environment.NewLine);
            }
            catch { log = null; }   // 写失败要改口（正文不能再承诺有日志）

            // 2) owner：有向导就挂在它上面，居中在向导而不是屏幕
            Form owner = null;
            try { if (Application.OpenForms.Count > 0) owner = Application.OpenForms[0]; } catch { }

            // 3) UnhandledException 跟着崩溃线程走，工作线程上直接建窗不可靠；
            //    同步切回 UI 线程再弹 —— BeginInvoke 异步排队在 CLR 终止进程时
            //    可能来不及跑，错误框就永远不出现（规范 §二.1）。
            if (owner != null && owner.InvokeRequired)
            {
                try
                {
                    owner.Invoke(new Action(delegate { ShowFatalOnUi(owner, log); }));
                    return;
                }
                catch { }    // 窗口正在销毁等竞态：退回直接弹
            }
            ShowFatalOnUi(owner, log);
        }

        static void ShowFatalOnUi(IWin32Window owner, string log)
        {
            try
            {
                MsgDialog.Error(owner,
                    log == null
                        ? "安装程序遇到没有预料到的问题，可能无法继续。\r\n\r\n"
                          + "详细信息未能写入日志文件，请把上述情况反馈给作者。"
                        : "安装程序遇到没有预料到的问题，可能无法继续。\r\n\r\n"
                          + "详细信息已写入日志文件，可以点「打开日志」查看。",
                    log);
            }
            catch { }
        }

        // ------------------------------------------------------------ 提权
        /// <summary>命令行里有没有这个开关（大小写不敏感）。</summary>
        static bool HasFlag(string[] args, string flag)
        {
            foreach (var a in args)
                if (string.Equals(a, flag, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        /// <summary>以管理员身份重新启动自己。用户取消 UAC 时返回 false。</summary>
        public static bool RelaunchAsAdmin(string arguments)
        {
            try
            {
                Process.Start(new ProcessStartInfo(Application.ExecutablePath, arguments)
                {
                    UseShellExecute = true,
                    Verb = "runas"
                });
                return true;
            }
            catch { return false; }
        }

        static void RelaunchForUninstall(bool silent)
        {
            var dir = InstalledDir();
            if (string.IsNullOrEmpty(dir))
                dir = Path.GetDirectoryName(Application.ExecutablePath);

            bool needAdmin = (InstalledForAllUsers() || IsUnderProgramFiles(dir)) && !IsElevated;

            try
            {
                var tmp = Path.Combine(Path.GetTempPath(),
                    "txtFormat-uninstall-" + Process.GetCurrentProcess().Id + ".exe");
                File.Copy(Application.ExecutablePath, tmp, true);

                var psi = new ProcessStartInfo(tmp,
                    "--uninstall-run \"" + dir + "\"" + (silent ? " --silent" : ""))
                {
                    UseShellExecute = true
                };
                if (needAdmin) psi.Verb = "runas";   // 删 Program Files / HKLM 需要提权

                var child = Process.Start(psi);
                // 静默卸载要等子进程删完再退出，否则父进程先走会让子进程被杀掉
                if (silent && child != null) child.WaitForExit();
            }
            catch (Exception ex)
            {
                // 规范 §二.1：自绘对话框（无系统图标、不发声）。
                // 这里没有 owner —— 卸载器是独立进程，弹在屏幕中间。
                MsgDialog.Info(null,
                    "无法启动卸载程序：\n" + ex.Message
                    + "\n\n可以手动到安装目录里运行 uninstall.exe。");
            }
        }

        // ------------------------------------------------------------ 安装
        public static void DoInstall(string dir, InstallMode mode, bool desktopShortcut,
                                     bool startMenuShortcut, Action<int, string> progress)
        {
            DoInstall(dir, mode, desktopShortcut, startMenuShortcut, false, progress);
        }

        /// <param name="resetConfig">
        /// true = 用户勾了「覆盖现有配置」，装完删掉旧配置让程序重建默认；
        /// false（默认）= 完全不动配置文件，不读不写不改时间戳（规范 §三.2）。
        /// </param>
        public static void DoInstall(string dir, InstallMode mode, bool desktopShortcut,
                                     bool startMenuShortcut, bool resetConfig,
                                     Action<int, string> progress)
        {
            // 点「安装」时的预检到这里之间有时间差（解压、弹进度页都要几秒），
            // 用户完全可能在这期间又把程序打开。页面层已经按「先问再杀」征得同意，
            // 这里**只复查、绝不静默杀**：非空抛出去让向导切回「正在运行」页，
            // 由用户再决定一次（规范 §三.1 第 7 点，与卸载侧 RemoveAll 同款）。
            if (RunningInstances(dir).Length > 0)
                throw new StillRunningException();

            Directory.CreateDirectory(dir);

            var asm = Assembly.GetExecutingAssembly();
            using (var s = asm.GetManifestResourceStream("payload.zip"))
            {
                if (s == null) throw new Exception("安装包数据缺失（payload.zip 未嵌入）");

                using (var zip = new ZipArchive(s, ZipArchiveMode.Read))
                {
                    int total = 0;
                    foreach (var e in zip.Entries)
                        if (!e.FullName.EndsWith("/")) total++;

                    int i = 0;
                    foreach (var e in zip.Entries)
                    {
                        if (e.FullName.EndsWith("/")) continue;

                        var target = Path.Combine(dir, e.FullName.Replace('/', '\\'));
                        var d = Path.GetDirectoryName(target);
                        if (!string.IsNullOrEmpty(d)) Directory.CreateDirectory(d);

                        e.ExtractToFile(target, true);

                        i++;
                        if (progress != null)
                            progress(total == 0 ? 100 : i * 100 / total, e.Name);
                    }
                }
            }

            // 使用说明随程序一起装进去（用户可自己在安装目录打开；完成页不再放对应复选框）
            try
            {
                File.WriteAllText(ReadmePathIn(dir), Readme, new UTF8Encoding(false));
            }
            catch { }

            // 自定义正则示例：只在首次安装时放，升级不覆盖用户改过的版本。
            // 注意必须按原始字节写：custreg.txt 是 GB18030 编码的，
            // 当 UTF-8 读一遍会把每个汉字变成 U+FFFD（程序里 _read_triples 能认 gb18030）。
            // 勾了「覆盖现有配置」时：删掉设置文件 config.json（程序下次启动重建默认配置，
            // 规范 §三.2），自定义正则也先删后写，恢复为随包附带的默认内容。
            // 不勾选则一个都不碰：config.json 本就不在 payload 里，天然不会动。
            if (resetConfig)
            {
                try
                {
                    var settings = SettingsPathIn(dir);
                    if (File.Exists(settings)) File.Delete(settings);
                }
                catch { }
            }
            try
            {
                var custReg = ConfigPathIn(dir);
                if (resetConfig && File.Exists(custReg)) File.Delete(custReg);
                if (!File.Exists(custReg))
                {
                    var raw = CustRegBytes;
                    if (raw != null && raw.Length > 0) File.WriteAllBytes(custReg, raw);
                }
            }
            catch { }

            // 卸载入口：把安装器自身复制成 uninstall.exe
            try
            {
                var self = Application.ExecutablePath;
                var dst = Path.Combine(dir, "uninstall.exe");
                if (!string.Equals(self, dst, StringComparison.OrdinalIgnoreCase))
                    File.Copy(self, dst, true);
            }
            catch { }

            bool allUsers = mode == InstallMode.AllUsers;
            if (desktopShortcut)
                CreateShortcut(Path.Combine(DesktopDir(allUsers), AppName + ".lnk"), dir);
            if (startMenuShortcut)
                CreateShortcut(Path.Combine(StartMenuDir(allUsers), AppName + ".lnk"), dir);

            WriteUninstallEntry(dir, mode);
            WriteAppPath(dir, mode);
        }

        static void CreateShortcut(string lnkPath, string targetDir)
        {
            try
            {
                var d = Path.GetDirectoryName(lnkPath);
                if (!string.IsNullOrEmpty(d) && !Directory.Exists(d)) Directory.CreateDirectory(d);

                var t = Type.GetTypeFromProgID("WScript.Shell");
                if (t == null) return;
                var shell = Activator.CreateInstance(t);
                var lnk = t.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell,
                    new object[] { lnkPath });
                var lt = lnk.GetType();
                var exe = ExePathIn(targetDir);
                lt.InvokeMember("TargetPath", BindingFlags.SetProperty, null, lnk, new object[] { exe });
                lt.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, lnk, new object[] { targetDir });
                lt.InvokeMember("IconLocation", BindingFlags.SetProperty, null, lnk, new object[] { exe + ",0" });
                lt.InvokeMember("Description", BindingFlags.SetProperty, null, lnk, new object[] { AppName });
                lt.InvokeMember("Save", BindingFlags.InvokeMethod, null, lnk, null);
            }
            catch { }
        }

        // ------------------------------------------------------------ 卸载
        /// <summary>卸载开始时发现目标程序又在运行 —— 向导据此切回占用页，而不是当失败处理。</summary>
        public class StillRunningException : Exception { }

        /// <summary>
        /// 卸载后复查：安装目录里还剩多少文件（keepConfig 时不算保留下来的用户设置）。
        /// 逐文件 TryDelete 会吞掉占用/权限导致的失败，不能凭它报「已移除」——
        /// 完成页必须先核实目录（规范 §五 3b）。
        /// </summary>
        public static int RemainingFiles(string dir, bool keepConfig)
        {
            try
            {
                if (!Directory.Exists(dir)) return 0;
                int n = 0;
                foreach (var f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                {
                    if (keepConfig && IsUserConfigFile(Path.GetFileName(f))) continue;
                    // 卸载器自己的 exe 不算残留：它可能正被父进程占用，
                    // 由 Program.ScheduleCleanup 在进程退出后删。
                    if (Path.GetFileName(f).Equals("uninstall.exe", StringComparison.OrdinalIgnoreCase))
                        continue;
                    n++;
                }
                return n;
            }
            catch { return 1; }   // 读不了也算「有残留」，宁可不报成功
        }

        /// <summary>清理安装痕迹，返回删除的文件数。keepConfig 为 true 时保留个人设置。</summary>
        public static int RemoveAll(string dir, bool keepConfig, Action<int, string> progress)
        {
            // 占用进程不在这里杀：页面层已经按规范「先问再杀」（点卸载时检测 → 占用页
            // 由用户决定）。走到这里还活着，只能是检查之后到动手之前新启动的 ——
            // 静默杀等于替用户做了决定（规范 §三.1 第 7 点 / §五）。
            // 抛出去让向导切回占用页，用户自己决定要不要结束它。
            if (RunningInstances(dir).Length > 0)
                throw new StillRunningException();

            const int Steps = 4;
            int step = 0;
            Action<string> tick = delegate(string msg)
            {
                step++;
                if (progress != null) progress(step * 100 / Steps, msg);
            };

            // 1. 注册表（两边都试，能删的删）
            RemoveUninstallEntries();
            RemoveAppPaths();
            tick("清理注册表");

            // 2. 快捷方式：当前用户与所有用户的位置都清一遍
            foreach (var all in new[] { false, true })
            {
                TryDelete(Path.Combine(DesktopDir(all), AppName + ".lnk"));
                TryDelete(Path.Combine(StartMenuDir(all), AppName + ".lnk"));
            }
            tick("删除快捷方式");

            // 3. 安装目录（勾了保留就跳过用户配置：设置与自定义词表现在都在这里）
            int removed = 0;
            if (Directory.Exists(dir))
            {
                foreach (var f in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                {
                    if (keepConfig && IsUserConfigFile(Path.GetFileName(f))) continue;
                    if (TryDelete(f)) removed++;
                }

                // 卸载器自己的 exe 常常正被父进程占用：多试几次，仍不行就交给
                // ScheduleCleanup 在进程退出后删（不算残留）。
                var selfExe = Path.Combine(dir, "uninstall.exe");
                for (int i = 0; i < 5 && File.Exists(selfExe); i++)
                {
                    TryDelete(selfExe);
                    if (!File.Exists(selfExe)) break;
                    Thread.Sleep(120);
                }

                var dirs = Directory.GetDirectories(dir, "*", SearchOption.AllDirectories);
                Array.Sort(dirs, delegate(string a, string b) { return b.Length.CompareTo(a.Length); });
                foreach (var d in dirs)
                {
                    try { if (Directory.GetFileSystemEntries(d).Length == 0) Directory.Delete(d); }
                    catch { }
                }

                try
                {
                    if (Directory.GetFileSystemEntries(dir).Length == 0) Directory.Delete(dir);
                }
                catch { }
            }
            tick("删除程序文件");

            // 4. 个人设置目录（勾了保留就不动它）
            if (!keepConfig)
            {
                try
                {
                    if (Directory.Exists(DataDir)) Directory.Delete(DataDir, true);
                }
                catch { }
            }
            tick("清理缓存");

            return removed;
        }

        /// <summary>安装目录里属于用户个人数据的文件（设置 + 自定义正则/错别字词表）。</summary>
        static readonly string[] UserConfigNames = { SettingsName, CustRegName, "custerr.txt" };

        /// <summary>判断卸载时要按「保留个人设置」跳过的文件名。</summary>
        public static bool IsUserConfigFile(string name)
        {
            foreach (var n in UserConfigNames)
                if (string.Equals(n, name, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        /// <summary>卸载勾了保留后仍在的用户配置清单（安装目录内的 + 旧版 %APPDATA% 里没清的）。</summary>
        public static string KeptConfigFiles(string dir)
        {
            try
            {
                var names = new List<string>();
                if (Directory.Exists(dir))
                    foreach (var f in Directory.GetFiles(dir, "*", SearchOption.TopDirectoryOnly))
                        if (IsUserConfigFile(Path.GetFileName(f))) names.Add(Path.GetFileName(f));
                if (Directory.Exists(DataDir))
                    foreach (var f in Directory.GetFiles(DataDir, "*", SearchOption.TopDirectoryOnly))
                        names.Add(Path.GetFileName(f) + "（旧版%APPDATA%）");
                return names.Count == 0 ? "（未发现个人设置）" : string.Join("、", names.ToArray());
            }
            catch { return "（无法读取）"; }
        }

        /// <summary>
        /// 保留的配置文件的**完整地址**（完成页单独一行显示，过长用省略号截断）。
        /// 与 KeptConfigFiles 的清单一一对应，只是换成完整路径，别让用户自己拼目录。
        /// </summary>
        public static string KeptConfigPaths(string dir)
        {
            try
            {
                var paths = new List<string>();
                var settings = SettingsPathIn(dir);
                if (File.Exists(settings)) paths.Add(settings);
                var custReg = ConfigPathIn(dir);
                if (File.Exists(custReg)) paths.Add(custReg);
                var custErr = Path.Combine(dir, "custerr.txt");
                if (File.Exists(custErr)) paths.Add(custErr);

                // 旧版把设置放在 %APPDATA%\txtFormat，卸载时不动它，这里也如实列出来
                if (Directory.Exists(DataDir))
                    foreach (var f in Directory.GetFiles(DataDir, "*", SearchOption.TopDirectoryOnly))
                        if (IsUserConfigFile(Path.GetFileName(f))) paths.Add(f);

                return string.Join("、", paths.ToArray());
            }
            catch { return ""; }
        }

        static bool TryDelete(string path)
        {
            try
            {
                if (File.Exists(path)) { File.Delete(path); return true; }
            }
            catch { }
            return false;
        }

        /// <summary>在指定目录下运行的实例。拿不到模块路径的也一并算上，宁可多提示，也不能等写文件时才炸。</summary>
        public static Process[] RunningInstances(string dir)
        {
            var list = new List<Process>();
            try
            {
                var root = string.IsNullOrEmpty(dir) ? null : dir.TrimEnd('\\') + "\\";
                foreach (var p in Process.GetProcessesByName(AppId))
                {
                    string exe = null;
                    try { exe = p.MainModule == null ? null : p.MainModule.FileName; } catch { }

                    // 权限不足或跨位数时 MainModule 会抛，此时按「在运行」处理
                    if (root == null || string.IsNullOrEmpty(exe)
                        || exe.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        list.Add(p);
                }
            }
            catch { }
            return list.ToArray();
        }

        /// <summary>结束安装目录下运行的实例，返回结束掉的个数。安装/卸载共用。</summary>
        public static int KillRunning(string dir)
        {
            int n = 0;
            foreach (var p in RunningInstances(dir))
            {
                try
                {
                    p.Kill();
                    p.WaitForExit(3000);
                    n++;
                }
                catch { }
            }
            return n;
        }

        /// <summary>异常消息是不是「文件被其它进程占用」。中英文 Windows 的措辞都认。</summary>
        public static bool LooksLikeFileInUse(string msg)
        {
            if (string.IsNullOrEmpty(msg)) return false;
            return msg.IndexOf("正由另一进程使用", StringComparison.Ordinal) >= 0
                || msg.IndexOf("另一个程序正在使用", StringComparison.Ordinal) >= 0
                || msg.IndexOf("being used by another process", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        /// <summary>从异常消息里抠出被占用的文件路径，取不到就返回 null。</summary>
        public static string QuotedPath(string msg)
        {
            if (string.IsNullOrEmpty(msg)) return null;
            int a = msg.IndexOf('"');
            if (a < 0) return null;
            int b = msg.IndexOf('"', a + 1);
            if (b < 0) return null;
            return msg.Substring(a + 1, b - a - 1);
        }

        /// <summary>临时副本用完把自己删掉。</summary>
        public static void ScheduleSelfDelete()
        {
            try
            {
                var self = Application.ExecutablePath;
                var tmp = Path.GetTempPath();
                if (!self.StartsWith(tmp, StringComparison.OrdinalIgnoreCase)) return;

                Process.Start(new ProcessStartInfo("cmd.exe",
                    "/c timeout /t 2 >nul & del /f /q \"" + self + "\"")
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden
                });
            }
            catch { }
        }

        /// <summary>
        /// 静默卸载收尾：本进程占着临时副本，无法自删；交给一个稍后启动的 cmd
        /// 在父进程退出后清掉临时副本、安装目录里残留的 uninstall.exe 与空目录。
        /// </summary>
        /// <param name="removeInstall">
        /// true（默认）= 卸载成功：临时副本、安装目录里的 uninstall.exe 与空目录都删掉；
        /// false = 卸载失败（程序还在运行 / 有残留）：**必须保住安装目录里的 uninstall.exe**，
        /// 否则用户既卸不掉也找不到卸载入口了，只能重装一次。临时副本照旧删。
        /// </param>
        public static void ScheduleCleanup(string dir, bool removeInstall = true)
        {
            try
            {
                var self = Application.ExecutablePath;              // 临时目录里的副本
                var localExe = Path.Combine(dir, "uninstall.exe");  // 安装目录里的本体
                var cmd = "/c timeout /t 3 >nul"
                          + " & del /f /q \"" + self + "\"";
                if (removeInstall)
                    cmd += " & del /f /q \"" + localExe + "\""
                           + " & rmdir \"" + dir + "\"";

                Process.Start(new ProcessStartInfo("cmd.exe", cmd)
                {
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden
                });
            }
            catch { }
        }

        public static void Launch(string dir)
        {
            try { Process.Start(ExePathIn(dir)); } catch { }
        }

        // ------------------------------------------------------------ 内嵌文本
        static string _license;

        /// <summary>许可协议，安装时展示。</summary>
        public static string License
        {
            get
            {
                // 内嵌的 LICENSE 是 LF 行尾；WinForms 的 TextBox 只认 \r\n，
                // 不归一化的话整篇文字会挤成一段。这里统一成 CRLF 再交给界面。
                if (_license == null)
                    _license = ToCrlf(Resource("LICENSE", DefaultLicense));
                return _license;
            }
        }

        /// <summary>把任意行尾（LF / CRLF / CR）统一成 CRLF。</summary>
        static string ToCrlf(string text)
        {
            if (string.IsNullOrEmpty(text)) return text;
            return text.Replace("\r\n", "\n").Replace("\r", "\n").Replace("\n", "\r\n");
        }

        static string _readme;

        /// <summary>使用说明，安装时写进安装目录。</summary>
        public static string Readme
        {
            get
            {
                if (_readme == null) _readme = Resource("README", "# " + AppName);
                return _readme;
            }
        }

        /// <summary>自定义正则示例（GB18030 原文），首次安装时按原始字节写入安装目录。</summary>
        public static byte[] CustRegBytes
        {
            get
            {
                var raw = ResourceBytes("CUSTREG");
                if (raw != null && raw.Length > 0) return raw;
                return Encoding.GetEncoding("GB18030").GetBytes(DefaultCustReg);
            }
        }

        /// <summary>读取内嵌资源的原始字节（供非 UTF-8 文本使用）。</summary>
        static byte[] ResourceBytes(string name)
        {
            try
            {
                using (var s = typeof(Program).Assembly.GetManifestResourceStream(name))
                {
                    if (s == null) return null;
                    var buf = new byte[s.Length];
                    int read = 0;
                    while (read < buf.Length)
                    {
                        int n = s.Read(buf, read, buf.Length - read);
                        if (n <= 0) break;
                        read += n;
                    }
                    if (read == buf.Length) return buf;
                    var trimmed = new byte[read];
                    Array.Copy(buf, trimmed, read);
                    return trimmed;
                }
            }
            catch { return null; }
        }

        static string Resource(string name, string fallback)
        {
            try
            {
                using (var s = typeof(Program).Assembly.GetManifestResourceStream(name))
                {
                    if (s == null) return fallback + "\r\n";
                    using (var r = new StreamReader(s, Encoding.UTF8))
                        return r.ReadToEnd();
                }
            }
            catch { return fallback + "\r\n"; }
        }

        /// <summary>LICENSE 未嵌入时的兜底文案（正常构建不会走到这里）。</summary>
        const string DefaultLicense = "MIT License";

        const string DefaultCustReg =
            "; txtFormat 自定义正则（每行一条：名称 | 表达式 | 说明）\r\n"
            + "; 放在安装目录或 %APPDATA%\\txtFormat\\ 下，重启程序即可生效。\r\n";
    }
}