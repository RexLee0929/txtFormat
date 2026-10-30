using System;
using System.IO;
using System.Text;
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

        [STAThread]
        static int Main(string[] args)
        {
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