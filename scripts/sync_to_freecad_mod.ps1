param(
    [string]$Destination = "C:\Program Files\FreeCAD 1.1\Mod\FreeCADAI",
    [bool]$CleanExtraneous = $true
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedRoot = (Resolve-Path -LiteralPath $repoRoot).Path

if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
}

$resolvedDestination = (Resolve-Path -LiteralPath $Destination).Path
if ((Split-Path -Leaf $resolvedDestination) -ne "FreeCADAI") {
    throw "Refusing to sync because destination does not end with FreeCADAI: $resolvedDestination"
}
if ($resolvedDestination -eq $resolvedRoot) {
    throw "Refusing to sync onto the source directory."
}

$sourcePluginDir = Join-Path $resolvedRoot "freecad_ai"
if (-not (Test-Path -LiteralPath $sourcePluginDir)) {
    throw "Plugin source directory not found: $sourcePluginDir"
}

function Assert-ChildPath {
    param(
        [string]$Parent,
        [string]$Child
    )
    $parentFull = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\')
    $childFull = [System.IO.Path]::GetFullPath($Child).TrimEnd('\')
    if (-not ($childFull.StartsWith($parentFull + "\", [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "Refusing to operate outside destination: $childFull"
    }
}

function Invoke-Robocopy {
    param(
        [string]$Source,
        [string]$Target
    )
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    $args = @(
        $Source,
        $Target,
        "/MIR",
        "/XD", "__pycache__", ".pytest_cache",
        "/XF", "*.pyc", "*.pyo",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP"
    )
    & robocopy @args | Out-Null
    $code = $LASTEXITCODE
    if ($code -gt 7) {
        throw "robocopy failed with exit code $code while syncing $Source"
    }
}

$rootFiles = @("Init.py", "InitGui.py", "package.xml", "README.md")
foreach ($fileName in $rootFiles) {
    $source = Join-Path $resolvedRoot $fileName
    if (Test-Path -LiteralPath $source) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $resolvedDestination $fileName) -Force
    }
}

Invoke-Robocopy -Source $sourcePluginDir -Target (Join-Path $resolvedDestination "freecad_ai")

if ($CleanExtraneous) {
    $oldWholeRepoItems = @(
        "server",
        "web",
        "docs",
        "deploy",
        "dist",
        "scripts",
        ".git",
        ".pytest_cache",
        ".dockerignore",
        ".gitignore",
        "dev_deploy.cmd",
        "docker-compose.prod.yml"
    )
    foreach ($item in $oldWholeRepoItems) {
        $target = Join-Path $resolvedDestination $item
        if (Test-Path -LiteralPath $target) {
            Assert-ChildPath -Parent $resolvedDestination -Child $target
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }
}

Get-ChildItem -Recurse -Force -Directory -LiteralPath $resolvedDestination -Filter "__pycache__" |
    ForEach-Object {
        Assert-ChildPath -Parent $resolvedDestination -Child $_.FullName
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }

Write-Host "Synced FreeCADAI plugin files to $resolvedDestination"
