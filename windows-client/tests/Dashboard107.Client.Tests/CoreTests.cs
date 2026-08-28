using System.Formats.Tar;
using System.IO.Compression;
using System.Text;
using Dashboard107.Client.Models;
using Dashboard107.Client.Services;

namespace Dashboard107.Client.Tests;

public sealed class CoreTests
{
    [Fact]
    public void ShellQuote_ProtectsSingleQuotes()
    {
        Assert.Equal("'alpha'\"'\"'beta'", ShellQuote.Posix("alpha'beta"));
    }

    [Fact]
    public void InputValidator_RejectsUppercaseUsername()
    {
        var key = Path.GetTempFileName();
        try
        {
            var options = new ConnectionOptions("107.ustc.edu.cn", 22, "PB123", key, "", "");
            Assert.Throws<ArgumentException>(() => InputValidator.Validate(options));
        }
        finally
        {
            File.Delete(key);
        }
    }

    [Fact]
    public void ReleasePackage_ReadsManifestAndChecksum()
    {
        var path = Path.GetTempFileName();
        try
        {
            using (var file = File.Create(path))
            using (var gzip = new GZipStream(file, CompressionLevel.SmallestSize))
            using (var writer = new TarWriter(gzip, leaveOpen: false))
            {
                var manifest = """
                    {"version":"0.1.0","source_commit":"0123456789abcdef"}
                    """;
                var entry = new PaxTarEntry(
                    TarEntryType.RegularFile,
                    "107dashboard-0.1.0/release-manifest.json")
                {
                    DataStream = new MemoryStream(Encoding.UTF8.GetBytes(manifest)),
                };
                writer.WriteEntry(entry);
            }

            var package = ReleasePackage.LoadFile(path);

            Assert.Matches("^0\\.1\\.0-01234567-[0-9a-f]{8}$", package.Info.ReleaseId);
            Assert.Equal(64, package.Info.Sha256.Length);
            Assert.Equal(new FileInfo(path).Length, package.OpenRead().Length);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public void SettingsStoreImportsLegacySettingsIntoPortableDataDirectory()
    {
        var applicationDirectory = Path.Combine(Path.GetTempPath(), $"107dashboard-{Guid.NewGuid():N}");
        var legacyPath = Path.Combine(applicationDirectory, "legacy", "client-settings.json");
        Directory.CreateDirectory(Path.GetDirectoryName(legacyPath)!);
        File.WriteAllText(
            legacyPath,
            """
            {
              "Host": "107.ustc.edu.cn",
              "Port": 2222,
              "Username": "pb24030760",
              "PrivateKeyPath": "C:\\Users\\tester\\.ssh\\id_ed25519",
              "TrustedHostFingerprint": "SHA256:test"
            }
            """);

        try
        {
            var store = new SettingsStore(applicationDirectory, legacyPath);

            var settings = store.Load();

            Assert.Equal("107.ustc.edu.cn", settings.Host);
            Assert.Equal(2222, settings.Port);
            Assert.Equal("pb24030760", settings.Username);
            Assert.Equal(
                "C:\\Users\\tester\\.ssh\\id_ed25519",
                settings.PrivateKeyPath);
            Assert.True(File.Exists(Path.Combine(applicationDirectory, "data", "client-settings.json")));
            Assert.True(File.Exists(legacyPath));
        }
        finally
        {
            Directory.Delete(applicationDirectory, recursive: true);
        }
    }

    [Fact]
    public void DeploymentScriptSerializesLockedRollbackAndCleanupFlow()
    {
        var script = RemoteDeploymentService.BuildDeploymentScript(
            new ReleaseInfo(
                "0.1.0",
                new string('a', 40),
                "0.1.0-aaaaaaaa-11111111",
                "107dashboard-0.1.0-aaaaaaaa-local",
                new string('b', 64)),
            ".upload-token");

        Assert.Contains("exec 9>\"$ROOT/update.lock\"", script);
        Assert.Contains("flock -n 9", script);
        Assert.Contains("mv -f -- \"$UPLOADED_ARCHIVE\" \"$ARCHIVE\"", script);
        Assert.Contains("ln -sfnT \"$PREVIOUS\" \"$ROOT/previous\"", script);
        Assert.Contains("cleanup_old_versions()", script);
        Assert.Contains("\"$path\" != \"$TARGET\"", script);
        Assert.Contains("\"$path\" != \"$PREVIOUS\"", script);
        Assert.DoesNotContain("rm -rf -- \"$ROOT/runtime\"", script);
    }
}
