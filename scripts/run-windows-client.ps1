param(
    [switch]$NoRestore
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$projectPath = Join-Path $repoRoot 'windows-client\src\Dashboard107.Client\Dashboard107.Client.csproj'

$dotnetCommand = $env:DOTNET_EXE
if ([string]::IsNullOrWhiteSpace($dotnetCommand)) {
    $dotnetLookup = Get-Command dotnet -ErrorAction SilentlyContinue
    if ($null -ne $dotnetLookup) {
        $dotnetCommand = $dotnetLookup.Source
    }
}

if ([string]::IsNullOrWhiteSpace($dotnetCommand)) {
    throw '未找到 .NET SDK。请安装 .NET 8 SDK，或先设置 DOTNET_EXE 指向 dotnet.exe。'
}

$dotnetArguments = @(
    'run'
    '--project'
    $projectPath
    '--configuration'
    'Debug'
)

if ($NoRestore) {
    $dotnetArguments += '--no-restore'
}

& $dotnetCommand @dotnetArguments
exit $LASTEXITCODE
