using System;
using System.Diagnostics;
using System.IO;
using System.Text;

class SofficeWrapper
{
    private static string RealSoffice { get { return Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, @"..\tools\LibreOffice\program\soffice.exe")); } }

    static bool HasNonAscii(string value)
    {
        foreach (char ch in value)
        {
            if (ch > 127) return true;
        }
        return false;
    }

    static string NormalizeUserInstallation(string arg)
    {
        const string prefix = "-env:UserInstallation=file://";
        if (arg.StartsWith(prefix, StringComparison.OrdinalIgnoreCase) &&
            !arg.StartsWith("-env:UserInstallation=file:///", StringComparison.OrdinalIgnoreCase))
        {
            string value = arg.Substring(prefix.Length).Replace('\\', '/');
            return "-env:UserInstallation=file:///" + value;
        }
        return arg;
    }

    static string Quote(string arg)
    {
        if (arg.Length == 0) return "\"\"";
        bool needsQuotes = arg.IndexOfAny(new[] { ' ', '\t', '\n', '\v', '"' }) >= 0;
        if (!needsQuotes) return arg;

        var sb = new StringBuilder();
        sb.Append('"');
        int backslashes = 0;
        foreach (char c in arg)
        {
            if (c == '\\')
            {
                backslashes++;
            }
            else if (c == '"')
            {
                sb.Append('\\', backslashes * 2 + 1);
                sb.Append('"');
                backslashes = 0;
            }
            else
            {
                sb.Append('\\', backslashes);
                backslashes = 0;
                sb.Append(c);
            }
        }
        sb.Append('\\', backslashes * 2);
        sb.Append('"');
        return sb.ToString();
    }

    static int Main(string[] rawArgs)
    {
        string tempDir = null;
        string[] args = new string[rawArgs.Length];
        for (int i = 0; i < rawArgs.Length; i++)
        {
            args[i] = NormalizeUserInstallation(rawArgs[i]);
        }

        if (args.Length > 0 && File.Exists(args[args.Length - 1]) && HasNonAscii(args[args.Length - 1]))
        {
            string suffix = Path.GetExtension(args[args.Length - 1]);
            if (String.IsNullOrEmpty(suffix)) suffix = ".docx";
            tempDir = Path.Combine(Path.GetTempPath(), "codex_lo_input_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempDir);
            string copied = Path.Combine(tempDir, "input" + suffix);
            File.Copy(args[args.Length - 1], copied, true);
            args[args.Length - 1] = copied;
        }

        var psi = new ProcessStartInfo();
        psi.FileName = RealSoffice;
        psi.UseShellExecute = false;
        psi.Arguments = String.Join(" ", Array.ConvertAll(args, Quote));

        try
        {
            using (var proc = Process.Start(psi))
            {
                proc.WaitForExit();
                return proc.ExitCode;
            }
        }
        finally
        {
            if (tempDir != null && Directory.Exists(tempDir)) Directory.Delete(tempDir, true);
        }
    }
}
