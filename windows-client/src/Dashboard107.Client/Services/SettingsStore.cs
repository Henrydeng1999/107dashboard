using System.IO;
using System.Text.Json;
using Dashboard107.Client.Models;

namespace Dashboard107.Client.Services;

public sealed class SettingsStore
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    private readonly string _settingsPath;

    public SettingsStore()
    {
        var directory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "107Dashboard");
        Directory.CreateDirectory(directory);
        _settingsPath = Path.Combine(directory, "client-settings.json");
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
}
