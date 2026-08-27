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
}
