using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        try
        {
            if (!TryResolveRepo(out var repo, out var script))
            {
                MessageBox.Show(
                    "Could not find scripts\\Start-NovaDaily.ps1.\n\n" +
                    "Put a one-line Nova.repo file next to Nova.exe with the repo path, e.g.\n" +
                    @"C:\Users\aalta\github\Nova",
                    "Nova",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return;
            }

            Process.Start(new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\"",
                WorkingDirectory = repo,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "Nova", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static bool TryResolveRepo(out string repo, out string script)
    {
        repo = "";
        script = "";
        var exeDir = AppContext.BaseDirectory.TrimEnd(
            Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        foreach (var root in CandidateRoots(exeDir))
        {
            var candidate = Path.Combine(root, "scripts", "Start-NovaDaily.ps1");
            if (File.Exists(candidate))
            {
                repo = root;
                script = candidate;
                return true;
            }
        }

        return false;
    }

    private static System.Collections.Generic.IEnumerable<string> CandidateRoots(string exeDir)
    {
        var seen = new System.Collections.Generic.HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var ordered = new System.Collections.Generic.List<string>();
        void Push(string? path)
        {
            if (string.IsNullOrWhiteSpace(path)) return;
            try { path = Path.GetFullPath(path.Trim().Trim('"')); }
            catch { return; }
            if (seen.Add(path)) ordered.Add(path);
        }

        // Explicit pointer next to the exe (Desktop copy, etc.)
        var repoFile = Path.Combine(exeDir, "Nova.repo");
        if (File.Exists(repoFile))
        {
            try { Push(File.ReadAllText(repoFile).Trim()); } catch { /* ignore */ }
        }

        var env = Environment.GetEnvironmentVariable("NOVA_REPO");
        Push(env);

        Push(exeDir);
        Push(Path.Combine(exeDir, ".."));
        Push(Path.Combine(exeDir, "..", ".."));
        Push(Path.Combine(exeDir, "..", "..", ".."));

        // Common local clone path for this machine
        Push(Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "github", "Nova"));

        return ordered;
    }
}
