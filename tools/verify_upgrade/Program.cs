using System;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;
using TxtFormatSetup;

namespace VerifyUpgrade
{
    /// <summary>
    /// 安装器「更新 / 重装 / 降级」判定逻辑的单元校验（规范 §三.3）。
    ///
    /// 不驱动 GUI：判定逻辑本身是纯函数（ClassifyVersions / ParseVersion），
    /// 文件系统那层只用临时目录验证「有没有 exe」与「有没有配置」两个开关。
    /// </summary>
    static class Entry
    {
        static int _pass, _fail;

        static void Check(string name, bool ok, string extra = "")
        {
            if (ok) { _pass++; Console.WriteLine("  [OK]   " + name); }
            else { _fail++; Console.WriteLine("  [FAIL] " + name + "  " + extra); }
        }

        static string TempDir(string tag)
        {
            var dir = Path.Combine(Path.GetTempPath(),
                "tfverify-" + tag + "-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(dir);
            return dir;
        }

        /// <summary>
        /// 自绘对话框的规格断言（规范 §二.1）。直接查控件属性，
        /// 不依赖截图 —— 这台机器上 PrintWindow/DrawToBitmap 对 WinForms
        /// 窗口的字形渲染不可靠。
        /// </summary>
        static void CheckDialogSpec(Form dlg, string tag)
        {
            Console.WriteLine("自绘对话框规格（" + tag + "）：");
            Check(tag + " 无系统边框", dlg.FormBorderStyle == FormBorderStyle.None,
                  dlg.FormBorderStyle.ToString());
            Check(tag + " 白色底", dlg.BackColor == Color.White, dlg.BackColor.ToString());
            Check(tag + " 定位在 owner 上", dlg.StartPosition == FormStartPosition.CenterParent,
                  dlg.StartPosition.ToString());
            Check(tag + " 宽度 420", dlg.Width == 420, dlg.Width.ToString());
            // 高由内容算、不设上限（规范 §二.1）—— 只要按钮行下面留够了 24px 就行
            Check(tag + " 高度按内容算（>=150）", dlg.Height >= 150, dlg.Height.ToString());
            Check(tag + " 不显示在任务栏", !dlg.ShowInTaskbar);

            var labels = new System.Collections.Generic.List<Label>();
            var buttons = new System.Collections.Generic.List<Button>();
            var pics = new System.Collections.Generic.List<PictureBox>();
            var icons = new System.Collections.Generic.List<System.Windows.Forms.Control>();
            Collect(dlg, labels, buttons, pics, icons);

            Check(tag + " 有标题", labels.Count >= 1, "Label 数 " + labels.Count);
            Check(tag + " 有正文", labels.Count >= 2, "Label 数 " + labels.Count);

            bool hasTitle = false, hasBody = false;
            foreach (var l in labels)
            {
                if (l.Font.Bold && l.Font.Size >= 10f) hasTitle = true;
                else if (!l.Font.Bold && l.Font.Size <= 9.5f) hasBody = true;
            }
            Check(tag + " 标题 10.5pt 粗体", hasTitle);
            Check(tag + " 正文 9pt", hasBody);

            // **不要图标** —— 规范明确黄三角/红叉是观感割裂的主因。
            // 只查真正的图标控件（PictureBox / 带 Image 的 Label），
            // Panel 之类的布局容器不算图标。
            int iconCount = pics.Count;
            foreach (var l in labels)
                if (l.Image != null) iconCount++;
            Check(tag + " 无图标控件", iconCount == 0, "图标控件 " + iconCount);

            Check(tag + " 至少一个按钮", buttons.Count >= 1, "Button 数 " + buttons.Count);

            // ---- 按钮顺序（规范 §二.1）：「取消」最右、主按钮在左 ----
            // 主按钮 = Accent 描边；次按钮（取消）= Theme.Line 描边。
            Button primary = null, secondary = null;
            foreach (var b in buttons)
            {
                if (b.FlatAppearance.BorderColor == Theme.Accent) primary = b;
                else secondary = b;
            }
            if (primary != null && secondary != null)
            {
                Check(tag + " 取消在最右",
                      secondary.Left > primary.Left,
                      "主 " + primary.Left + " / 次 " + secondary.Left);
                Check(tag + " 按钮间距 8",
                      Math.Abs((secondary.Left - primary.Left) - primary.Width - 8) <= 2,
                      "间距 " + (secondary.Left - primary.Left - primary.Width));
            }
            else if (primary != null && secondary == null)
            {
                Check(tag + " 仅有主按钮", true);
            }

            // ---- 按钮文字颜色（规范 §二.1）----
            // 主按钮 1px Accent 描边 + Theme.Ink 文字；
            // 次按钮 1px Line 描边 + Theme.Muted 文字。
            if (primary != null)
            {
                Check(tag + " 主按钮 Accent 描边 + Ink 文字",
                      primary.BackColor == Color.White
                      && primary.ForeColor == Theme.Ink
                      && primary.FlatStyle == FlatStyle.Flat,
                      "文字 " + primary.ForeColor);
            }
            if (secondary != null)
            {
                Check(tag + " 次按钮细灰描边 + Muted 文字",
                      secondary.BackColor == Color.White
                      && secondary.ForeColor == Theme.Muted
                      && secondary.FlatAppearance.BorderColor == Theme.Line,
                      "文字 " + secondary.ForeColor);
            }

            // ---- 悬停/按下底色（规范 §二.1：悬停 Theme.HoverBg、按下 Theme.SelectBg）----
            foreach (var b in buttons)
            {
                Check(tag + " 按钮「" + b.Text + "」悬停底色",
                      b.FlatAppearance.MouseOverBackColor == Theme.HoverBg,
                      b.FlatAppearance.MouseOverBackColor.ToString());
                Check(tag + " 按钮「" + b.Text + "」按下底色",
                      b.FlatAppearance.MouseDownBackColor == Theme.SelectBg,
                      b.FlatAppearance.MouseDownBackColor.ToString());
            }

            // 按钮文字不能被折行：宽度要够放得下文字
            foreach (var b in buttons)
            {
                int need = TextRenderer.MeasureText(b.Text, b.Font).Width + 24;
                Check(tag + " 按钮「" + b.Text + "」文字不折行", b.Width >= need,
                      "宽 " + b.Width + " 需 " + need);
            }

            // 正文最多三行
            int maxLines = 0;
            foreach (var l in labels)
                if (!l.Font.Bold)
                    maxLines = Math.Max(maxLines,
                        l.Text.Replace("\r\n", "\n").Split('\n').Length);
            Check(tag + " 正文不超过三行", maxLines <= 3, "行数 " + maxLines);
        }

        static void Collect(Control c, System.Collections.Generic.List<Label> labels,
                            System.Collections.Generic.List<Button> buttons,
                            System.Collections.Generic.List<PictureBox> pics,
                            System.Collections.Generic.List<Control> others)
        {
            foreach (Control child in c.Controls)
            {
                if (child is Label lb) labels.Add(lb);
                else if (child is Button bt) buttons.Add(bt);
                else if (child is PictureBox pb) pics.Add(pb);
                else others.Add(child);
                Collect(child, labels, buttons, pics, others);
            }
        }

        /// <summary>把窗体里每个控件按各自坐标画到一张 Bitmap 上（字形正常）。</summary>
        static void SaveControls(Form f, string path)
        {
            using (var bmp = new Bitmap(f.Width, f.Height))
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.White);
                DrawTree(f, g, Point.Empty);
                bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            }
        }

        /// <summary>递归画控件树：Label/Button 走 Paint，Panel 直接画底色。</summary>
        static void DrawTree(Control c, Graphics g, Point offset)
        {
            var r = c.Bounds;
            var g2 = g;
            g2.TranslateTransform(offset.X + r.Left, offset.Y + r.Top);

            if (c is Label || c is Button || c is TextBox)
            {
                // 让控件自己画到我们的 Graphics 上
                var pe = new PaintEventArgs(g2, c.ClientRectangle);
                c.GetType().GetMethod("OnPaint",
                    System.Reflection.BindingFlags.Instance
                    | System.Reflection.BindingFlags.NonPublic
                    | System.Reflection.BindingFlags.Public,
                    null,
                    new[] { typeof(PaintEventArgs) },
                    null)
                    .Invoke(c, new object[] { pe });
            }
            else
            {
                using (var br = new SolidBrush(c.BackColor))
                    g2.FillRectangle(br, c.ClientRectangle);
            }

            g2.ResetTransform();
            foreach (Control child in c.Controls)
                DrawTree(child, g, new Point(offset.X + r.Left, offset.Y + r.Top));
        }

        [STAThread]
        static int Main(string[] args)
        {
            // ---- 0. --dialog：拉起自绘对话框供人工目检（规范 §二.1）
            if (Array.IndexOf(args, "--dialog") >= 0)
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                // 造一个假 owner 当参照物，确认弹窗居中在 owner 之上
                var owner = new Form
                {
                    Text = "参照窗口",
                    StartPosition = FormStartPosition.CenterScreen,
                    ClientSize = new Size(400, 200)
                };
                owner.Show();

                // 标题传空 → 回落到程序名（规范 §二.1，与实际调用同款）
                using (var dlg = new NoticeDialog(owner, "",
                        "「为所有用户安装」需要管理员权限。\r\n\r\n"
                        + "接下来会请求提升权限并重新启动安装程序，你的选择会被保留。",
                        "继续", "取消"))
                {
                    // 不覆盖 StartPosition：让它保持默认的 CenterParent，
                    // 这样才能断言「弹窗居中在 owner 之上」。
                    dlg.Show();
                    dlg.BringToFront();
                    Application.DoEvents();
                    System.Threading.Thread.Sleep(700);
                    Application.DoEvents();
                    Check("标题回落到程序名", dlg.Controls[0].Text == Program.AppName,
                          dlg.Controls[0].Text);

                    // 规格断言（规范 §二.1）：不靠截图，直接查控件属性
                    CheckDialogSpec(dlg, "带取消");

                    // 只有主按钮、无取消的另一种形态
                    using (var dlg2 = new NoticeDialog(owner, "没有获得管理员权限",
                            "已取消本次安装。\r\n可以改选「仅为我安装」，不需要提权。",
                            null, null, true))
                    {
                        dlg2.Show();
                        Application.DoEvents();
                        System.Threading.Thread.Sleep(400);
                        Application.DoEvents();
                        CheckDialogSpec(dlg2, "仅主按钮");
                        dlg2.Close();
                    }

                    // 错误框（未捕获异常兜底，规范 §二.1）：正文承诺有日志时，
                    // 按钮行最右必须有「打开日志」，否则用户按提示找不到文件
                    var logPath = System.IO.Path.Combine(System.IO.Path.GetTempPath(),
                        Program.AppId + "-setup-error.log");
                    using (var dlg3 = new NoticeDialog(owner, null,
                            "安装程序遇到没有预料到的问题，可能无法继续。\r\n\r\n"
                            + "详细信息已写入日志文件，可以点「打开日志」查看。",
                            "关闭", null, true, 0f, logPath))
                    {
                        dlg3.Show();
                        Application.DoEvents();
                        System.Threading.Thread.Sleep(400);
                        Application.DoEvents();
                        CheckDialogSpec(dlg3, "错误框");
                        bool hasLogBtn = false;
                        foreach (Control c in dlg3.Controls)
                            if (c is Button && ((Button)c).Text == "打开日志") hasLogBtn = true;
                        Check("错误框有「打开日志」按钮", hasLogBtn);
                        dlg3.Close();
                    }

                    // （向导按钮的自绘 flat / 禁用态改造由 build + e2e 覆盖：
                    //  校验工程里没有内嵌 payload，构造 InstallForm 会在读资源时抛空引用，
                    //  不适合作为断言宿主。）

                    Console.WriteLine("按回车关闭…");
                    Console.ReadLine();

                    dlg.Close();
                }

                owner.Close();
                return 0;
            }

            Console.WriteLine("校验：安装器版本判定（规范 §三.3）\n");

            // ---- 1. 五态判定（纯比较，不碰文件系统）
            Console.WriteLine("五态判定：");
            var classify = new[]
            {
                new object[] { "1.0.0", "1.0.1", Program.UpgradeKind.Update,    "旧 → 新 = 更新" },
                new object[] { "1.0.1", "1.0.1", Program.UpgradeKind.Same,      "同版本 = 重装" },
                new object[] { "1.1.0", "1.0.1", Program.UpgradeKind.Downgrade, "新 → 旧 = 降级" },
                new object[] { "1.2",   "1.2.0", Program.UpgradeKind.Same,      "2 段 vs 3 段同版本 = 重装" },
                new object[] { "1",     "1.0.0", Program.UpgradeKind.Same,      "1 段 vs 3 段同版本 = 重装" },
                new object[] { "1.2.3-beta", "1.2.3", Program.UpgradeKind.Same, "带后缀 = 取数字段" },
                new object[] { "abc",   "1.0.1", Program.UpgradeKind.Unknown,   "读不出 = 未知" },
                new object[] { "",      "1.0.1", Program.UpgradeKind.Unknown,   "空串 = 未知" },
            };
            foreach (var c in classify)
            {
                var got = Program.ClassifyVersions((string)c[0], (string)c[1]);
                Check((string)c[3], got == (Program.UpgradeKind)c[2],
                      $"期望 {c[2]}，得到 {got}");
            }

            // ---- 2. 版本解析容错（规范 §三.3 脏数据表）
            Console.WriteLine("\n版本解析容错：");
            var parse = new[]
            {
                new[] { "1.2.3",      "1.2.3.0" },
                new[] { "1.2.3.0",    "1.2.3.0" },
                new[] { "1.2",        "1.2.0.0" },
                new[] { "1",          "1.0.0.0" },
                new[] { "1.2.3-beta", "1.2.3.0" },
                new[] { "1.2.3.4.5",  "1.2.3.4" },
            };
            foreach (var c in parse)
            {
                var got = Program.ParseVersionForTest(c[0]);
                var want = new Version(c[1]);
                Check($"\"{c[0]}\" → {c[1]}", got != null && got.Equals(want),
                      got == null ? "null" : got.ToString());
            }
            Check("\"\" → null", Program.ParseVersionForTest("") == null);
            Check("\"abc\" → null", Program.ParseVersionForTest("abc") == null);
            Check("\"\" → null（全点）", Program.ParseVersionForTest("...") == null);

            // ---- 3. 文件系统那层的两个开关
            Console.WriteLine("\n目录探测：");
            var d1 = TempDir("fresh");
            string inst;
            Check("空目录 = Fresh",
                  Program.DetectUpgrade(d1, out inst) == Program.UpgradeKind.Fresh,
                  Program.DetectUpgrade(d1, out inst).ToString());

            var d2 = TempDir("unknown");
            File.WriteAllText(Program.ExePathIn(d2), "not a real exe", Encoding.ASCII);
            var k2 = Program.DetectUpgrade(d2, out inst);
            Check("exe 在但版本读不出 = Unknown", k2 == Program.UpgradeKind.Unknown, k2.ToString());

            var d3 = TempDir("cfg");
            Check("无配置 = HasConfig false", !Program.HasConfig(d3));
            File.WriteAllText(Program.ConfigPathIn(d3), "; test", Encoding.UTF8);
            Check("有配置 = HasConfig true", Program.HasConfig(d3));

            // 配置文件用的是随包附带的那个名字
            Check("配置文件 = custreg.txt",
                  Program.ConfigPathIn("X:\\any").EndsWith("custreg.txt", StringComparison.OrdinalIgnoreCase),
                  Program.ConfigPathIn("X:\\any"));

            foreach (var d in new[] { d1, d2, d3 })
                try { Directory.Delete(d, true); } catch { }

            Console.WriteLine($"\n通过 {_pass} 项，失败 {_fail} 项");
            Console.WriteLine(_fail == 0 ? "安装器判定逻辑校验通过 ✓" : "校验失败 ✗");
            return _fail == 0 ? 0 : 1;
        }
    }
}