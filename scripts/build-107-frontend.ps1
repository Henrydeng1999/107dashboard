[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$StagingDirectory = Join-Path $FrontendRoot "dist.107-staging"
$DistDirectory = Join-Path $FrontendRoot "dist"
$NpxCommand = Get-Command npx.cmd -ErrorAction SilentlyContinue
if ($null -eq $NpxCommand) {
    $NpxCommand = Get-Command npx -ErrorAction SilentlyContinue
}
if ($null -eq $NpxCommand) {
    throw "npx is required to build the frontend release."
}

function Remove-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Invoke-Npx {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & $NpxCommand.Source @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "npx command failed with exit code $($LASTEXITCODE): $($Arguments -join ' ')"
    }
}

$BuildInstalled = $false
try {
    Remove-Directory $StagingDirectory

    Push-Location $FrontendRoot
    try {
        Invoke-Npx @("tsc", "-b")
        Invoke-Npx @(
            "vite", "build", "--mode", "navigation", "--base=/107-dashboard/",
            "--outDir", $StagingDirectory, "--emptyOutDir"
        )
    }
    finally {
        Pop-Location
    }

    $IndexPath = Join-Path $StagingDirectory "index.html"
    if (-not (Test-Path -LiteralPath $IndexPath -PathType Leaf)) {
        throw "frontend build did not produce dist.107-staging/index.html"
    }

    $IndexContent = Get-Content -LiteralPath $IndexPath -Raw
    if ($IndexContent -notmatch "/107-dashboard/assets/") {
        throw "107 frontend build is missing the /107-dashboard/assets/ prefix."
    }

    $AssetDirectory = Join-Path $StagingDirectory "assets"
    $AssetFiles = @(Get-ChildItem -LiteralPath $AssetDirectory -File -Recurse -ErrorAction Stop)
    if ($AssetFiles.Count -eq 0) {
        throw "107 frontend build did not produce asset files."
    }
    if (-not (Select-String -Path $AssetFiles.FullName -Pattern "/107-dashboard/api" -SimpleMatch -Quiet)) {
        throw "107 frontend build is missing the /107-dashboard/api prefix."
    }

    $BuildFiles = @((Get-Item -LiteralPath $IndexPath)) + $AssetFiles
    if (Select-String -Path $BuildFiles.FullName -Pattern "https?://(localhost|127\.0\.0\.1):[0-9]+/api" -Quiet) {
        throw "107 frontend build contains a development API address."
    }

    $PreviousIndexPath = Join-Path $DistDirectory "index.html"
    if (Test-Path -LiteralPath $PreviousIndexPath -PathType Leaf) {
        $PreviousIndexContent = Get-Content -LiteralPath $PreviousIndexPath -Raw
        $PreviousAssetPaths = [regex]::Matches(
            $PreviousIndexContent,
            '/107-dashboard/assets/[^"'' ]+'
        ) | ForEach-Object { $_.Value } | Sort-Object -Unique

        foreach ($AssetPath in $PreviousAssetPaths) {
            $RelativePath = $AssetPath.Substring("/107-dashboard/".Length).Replace(
                "/", [IO.Path]::DirectorySeparatorChar
            )
            $SourcePath = Join-Path $DistDirectory $RelativePath
            $TargetPath = Join-Path $StagingDirectory $RelativePath
            if ((Test-Path -LiteralPath $SourcePath -PathType Leaf) -and
                -not (Test-Path -LiteralPath $TargetPath)) {
                $TargetParent = Split-Path -Parent $TargetPath
                New-Item -ItemType Directory -Path $TargetParent -Force | Out-Null
                Copy-Item -LiteralPath $SourcePath -Destination $TargetPath
            }
        }
    }

    Remove-Directory $DistDirectory
    Move-Item -LiteralPath $StagingDirectory -Destination $DistDirectory
    $BuildInstalled = $true
    Write-Output "107 frontend release build validated and installed in $DistDirectory."
}
finally {
    if (-not $BuildInstalled) {
        Remove-Directory $StagingDirectory
    }
}
