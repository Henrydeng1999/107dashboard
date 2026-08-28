using System.IO;
using System.Text.Json;
using Dashboard107.Client.Models;

namespace Dashboard107.Client.Services;

public sealed class SettingsStore
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private readonly string _settingsPath;

    public SettingsStore(string? applicationDirectory = null, string? legacySettingsPath = null)
    {
        var directory = Path.Combine(applicationDirectory ?? AppContext.BaseDirectory, "data");
        Directory.CreateDirectory(directory);
        _settingsPath = Path.Combine(directory, "client-settings.json");
        ImportLegacySettings(legacySettingsPath ?? GetLegacySettingsPath());
    }

    public ClientSettings Load()
    {
        if (!File.Exists(_settingsPath))
        {
            return new ClientSettings();
        }

        try
        {
            return JsonSerializer.Deserialize<ClientSettings>(File.ReadAllText(_settingsPath))
                ?? new ClientSettings();
        }
        catch (JsonException)
        {
            return new ClientSettings();
        }
    }

    public void Save(ClientSettings settings)
    {
        var temporaryPath = _settingsPath + ".tmp";
        File.WriteAllText(temporaryPath, JsonSerializer.Serialize(settings, JsonOptions));
        File.Move(temporaryPath, _settingsPath, true);
    }

    private void ImportLegacySettings(string legacySettingsPath)
    {
        if (File.Exists(_settingsPath) || !File.Exists(legacySettingsPath))
        {
            return;
        }

        try
        {
            var settings = JsonSerializer.Deserialize<ClientSettings>(
                File.ReadAllText(legacySettingsPath));
            if (settings is not null)
            {
                Save(settings);
            }
        }
        catch (JsonException)
        {
            // Ignore malformed legacy settings and use the defaults.
        }
        catch (IOException)
        {
            // A portable copy must still be able to start if the old file is unavailable.
        }
        catch (UnauthorizedAccessException)
        {
            // A portable copy must still be able to start if the old file is inaccessible.
        }
    }

    private static string GetLegacySettingsPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "107Dashboard",
        "client-settings.json");
}
