using System;
using System.IO;
using System.IO.Compression;
using System.Diagnostics;
using System.Reflection;
using System.Windows.Forms;

// Installs into a fresh directory. Updating never overwrites the personal database.
internal static class Setup {
    [STAThread]
    static int Main(string[] args) {
        bool testInstall = args.Length == 2 && args[0] == "--test-install";
        bool isolated = testInstall || (args.Length == 2 && args[0] == "--extract");
        try {
            string parent = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "F1rti AI Coach");
            string root = isolated ? Path.GetFullPath(args[1]) : Path.Combine(parent, "App-" + Guid.NewGuid().ToString("N").Substring(0,10));
            if (!isolated && MessageBox.Show("Установить F1rti AI Coach для текущего пользователя?", "F1rti AI Coach", MessageBoxButtons.OKCancel) != DialogResult.OK) return 0;
            if (Directory.Exists(root)) throw new IOException("Выберите новую папку установки.");
            Directory.CreateDirectory(root);
            using (Stream data = Assembly.GetExecutingAssembly().GetManifestResourceStream("coach.payload"))
            using (ZipArchive archive = new ZipArchive(data)) {
                foreach (var entry in archive.Entries) {
                    string file = Path.GetFullPath(Path.Combine(root,entry.FullName));
                    if (!file.StartsWith(root + Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new IOException("Недопустимое имя файла.");
                    Directory.CreateDirectory(Path.GetDirectoryName(file));
                    entry.ExtractToFile(file);
                }
            }
            if (isolated && !testInstall) return 0;
            string exe = Path.Combine(root,"pythonw.exe");
            string script = "\"" + Path.Combine(root,"desktop.py") + "\"";
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            object shell = Activator.CreateInstance(shellType);
            foreach (var folder in new[]{Environment.SpecialFolder.Programs,Environment.SpecialFolder.DesktopDirectory}) {
                string links = testInstall ? Path.Combine(root,"shortcut-test",folder.ToString()) : Environment.GetFolderPath(folder);
                Directory.CreateDirectory(links);
                string name = Path.Combine(links,"F1rti AI Coach.lnk");
                object shortcut = shellType.InvokeMember("CreateShortcut",BindingFlags.InvokeMethod,null,shell,new object[]{name});
                Type t = shortcut.GetType();
                t.InvokeMember("TargetPath",BindingFlags.SetProperty,null,shortcut,new object[]{exe});
                t.InvokeMember("Arguments",BindingFlags.SetProperty,null,shortcut,new object[]{script});
                t.InvokeMember("WorkingDirectory",BindingFlags.SetProperty,null,shortcut,new object[]{root});
                t.InvokeMember("Save",BindingFlags.InvokeMethod,null,shortcut,null);
            }
            if (!testInstall) Process.Start(exe,script);
            return 0;
        } catch(Exception exc) {
            if (!isolated) MessageBox.Show(exc.Message,"Установка F1rti AI Coach",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        }
    }
}

