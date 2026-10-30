using System;
using System.Drawing;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace TxtFormatSetup
{
    /// <summary>卸载向导：确认 → [正在运行] → 卸载中 → 完成。外观与安装向导同一套。</summary>
    public class UninstallForm : WizardShell
    {
        readonly string _dir;
        bool _busy, _removed, _failed;
        bool _keepConfig;
        bool _onRunningPage;      // 当前显示的是「正在运行」条件页（§三.1-6 / §五-1b）

        CheckBox _cbKeep;
        ProgressStrip _bar;
        Label _status;

        public UninstallForm(string dir)
            : base("卸载 " + Program.AppName, 640, 400, "从计算机中移除程序")
        {
            _dir = string.IsNullOrEmpty(dir) ? Program.DefaultDir() : dir;
            // 卸载完成后：临时副本与安装目录里的 uninstall.exe 都删掉，空目录一并收走
            FormClosing += delegate { if (_removed) Program.ScheduleCleanup(_dir); };
        }

        protected override void BuildPages()
        {
            NextBtn.Click += delegate { OnNext(); };
            Back.Click += delegate
            {
                if (_busy || _removed) return;
                if (_onRunningPage) { ShowConfirm(); return; }   // 上一步 → 回确认页
                Close();
            };
            CancelBtn.Click += delegate { if (!_busy) Close(); };
        }

        protected override void ShowPage(int index)
        {
            if (index == 0) ShowConfirm();
        }

        void ShowConfirm()
        {
            _onRunningPage = false;
            BuildConfirm();

            // 规范 §五-1b：确认页出现时**不**检测占用。
            // 程序开着时点开卸载向导若直接落到「正在运行」页，用户连卸载内容和
            // 「保留配置文件」选项都没看见（ComicConverter 1.0.3 实测踩过）。
            // 占用检测只放在点「卸载」那一刻 —— 见 OnNext()。
        }

        void BuildConfirm()
        {
            Body.Controls.Clear();
            TitleLabel.Text = "卸载 " + Program.AppName;

            Back.Visible = false;
            CancelBtn.Visible = true;
            CancelBtn.Enabled = true;
            NextBtn.Visible = true;
            NextBtn.Text = "卸载";
            NextBtn.Enabled = true;
            LayoutButtons(86);           // 从「正在运行」页回来时复位默认宽度

            bool allUsers = Program.InstalledForAllUsers() || Program.IsUnderProgramFiles(_dir);

            L("安装程序将把 " + Program.AppName + " " + Program.Version
              + " 从您的计算机中移除（"
              + (allUsers ? "为所有用户安装" : "为当前用户安装") + "）。", 0, 0, 428, 24);

            Strong("安装位置：", 0, 34, 428, 22);
            L(_dir, 0, 56, 428, 20);

            Strong("将一并清理：", 0, 88, 428, 22);
            L("· 程序文件与运行库\n"
              + "· 桌面与开始菜单快捷方式\n"
              + "· 「设置 → 应用」里的卸载登记项", 0, 110, 428, 70);

            _cbKeep = Check("保留个人设置与自定义词表（安装目录内的 config.json 等）", 0, 190, 396, true);

            L("作者：" + Program.Author + "　　联系邮箱：" + Program.Email, 0, 224, 428, 20);
        }

        void OnNext()
        {
            if (_removed) { Close(); return; }
            if (_failed) { Close(); return; }
            if (_busy) return;

            if (_onRunningPage)
            {
                EndRunningAndUninstall();
                return;
            }

            // 规范 §五-1b / §三.1-6：点「卸载」时才检测占用（程序可能在确认页停留期间被打开）；
            // 命中就切「正在运行」页，绝不弹 MessageBox。
            if (Program.RunningInstances(_dir).Length > 0)
            {
                ShowRunning();
                return;
            }

            _keepConfig = _cbKeep != null && _cbKeep.Checked;
            StartUninstall();
        }

        /// <summary>「X 正在运行」条件页（§五-1b）：与安装侧同款，不弹 MessageBox。</summary>
        void ShowRunning()
        {
            _onRunningPage = true;
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
            NextBtn.Text = "结束进程并继续卸载";
            LayoutButtons(126);          // 按钮文字长，需要更宽，否则被折成两行（§三.1）

            Strong("需要删除的文件正被占用：", 0, 0, 428, 22);
            L(_dir, 0, 24, 428, 20);
            L(Path.Combine(_dir, Program.AppExe), 0, 46, 428, 20);

            Strong("请选择一种处理方式：", 0, 80, 428, 22);
            L("· 点「结束进程并继续卸载」—— 自动关闭正在运行的 " + Program.AppName
              + "（未保存的操作会丢失），随后立即继续卸载；\n"
              + "· 点「上一步」—— 回到确认页；\n"
              + "· 若结束失败，请手动关闭 " + Program.AppName
              + "，再点「结束进程并继续卸载」重试。", 0, 104, 428, 80);
        }

        /// <summary>结束占用进程后继续卸载；仍被占用则停在这一页，让用户手动处理。</summary>
        void EndRunningAndUninstall()
        {
            NextBtn.Enabled = false;
            int n = Program.KillRunning(_dir);

            if (Program.RunningInstances(_dir).Length > 0)
            {
                NextBtn.Enabled = true;
                MessageBox.Show(this,
                    "没能结束正在运行的 " + Program.AppName + "（权限不足或进程未响应）。\n\n"
                    + "请用任务管理器手动结束它，或重启计算机后再运行卸载程序。",
                    Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            if (n > 0) Thread.Sleep(300);   // 等文件句柄真正释放
            _keepConfig = _cbKeep != null && _cbKeep.Checked;
            StartUninstall();
        }

        void StartUninstall()
        {
            _busy = true;
            Body.Controls.Clear();
            TitleLabel.Text = "正在卸载";

            Back.Visible = false;
            NextBtn.Enabled = false;
            CancelBtn.Enabled = false;

            L("正在从 " + _dir + " 移除 " + Program.AppName + "…", 0, 0, 428, 40);

            _bar = new ProgressStrip(K, 0, 60, 428, 10);
            Body.Controls.Add(_bar);

            _status = L("准备中…", 0, 78, 428, 150);

            var dir = _dir;
            var keep = _keepConfig;
            var th = new Thread(delegate()
            {
                try
                {
                    int n = Program.RemoveAll(dir, keep, delegate(int pct, string msg)
                    {
                        Ui(delegate
                        {
                            if (_bar == null) return;
                            _bar.Value = Math.Min(100, pct);
                            _status.Text = msg + "…";
                        });
                    });
                    Ui(delegate { ShowFinish(n, keep); });
                }
                catch (Exception ex)
                {
                    Ui(delegate { ShowFailure(ex.Message); });
                }
            });
            th.IsBackground = true;
            th.Start();
        }

        void ShowFinish(int removed, bool keep)
        {
            _busy = false;
            _removed = true;
            Body.Controls.Clear();
            TitleLabel.Text = "正在完成 " + Program.AppName + " 卸载向导";

            Back.Visible = false;
            CancelBtn.Visible = false;
            NextBtn.Text = "关闭";
            NextBtn.Enabled = true;

            L(Program.AppName + " 已从您的计算机中移除。", 0, 0, 428, 24);
            L("共删除 " + removed + " 个文件。", 0, 32, 428, 20);

            if (keep)
            {
                // 规范 §五-3：说明与路径**分开两行**，路径过长用省略号截断。
                // 拼成一行会折行，而标签只有 20px 高，第二行看不见。
                L("配置文件已保留：", 0, 62, 428, 20);
                var pathLbl = L(_dir, 0, 84, 428, 20);
                pathLbl.AutoEllipsis = true;
                pathLbl.Tag = _dir;                     // 完整路径，供悬停提示查看
                var tip = new ToolTip();
                tip.SetToolTip(pathLbl, _dir);
                L("包含：" + Program.KeptConfigFiles(_dir), 0, 106, 428, 20);
            }
            else
            {
                L("配置文件已一并删除。", 0, 62, 428, 20);
            }

            L("如果以后还要用，重新运行安装包即可。", 0, 140, 428, 20);
            L("作者：" + Program.Author + "　　联系邮箱：" + Program.Email, 0, 170, 428, 20);
        }

        void ShowFailure(string msg)
        {
            _busy = false;
            _failed = true;
            Body.Controls.Clear();
            TitleLabel.Text = "卸载未完全成功";

            Back.Visible = false;
            CancelBtn.Visible = false;
            NextBtn.Text = "关闭";
            NextBtn.Enabled = true;

            L("有些文件没能删除：\n\n" + msg
              + "\n\n可以稍后手动删除安装目录：\n" + _dir, 0, 0, 428, 140);
        }

        void Ui(Action a)
        {
            try { if (IsHandleCreated) BeginInvoke(a); } catch { }
        }
    }
}