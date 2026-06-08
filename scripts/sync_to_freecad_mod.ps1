param(
    [string]$Destination = "C:\Program Files\FreeCAD 1.1\Mod\FreeCADAI"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Destination)) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
}

$resolvedDestination = (Resolve-Path -LiteralPath $Destination).Path
if ((Split-Path -Leaf $resolvedDestination) -ne "FreeCADAI") {
    throw "Refusing to sync because destination does not end with FreeCADAI: $resolvedDestination"
}

$resolvedRoot = (Resolve-Path -LiteralPath $repoRoot).Path
if ($resolvedDestination -eq $resolvedRoot) {
    throw "Refusing to sync onto the source directory."
}

$excludeDirs = @("__pycache__", ".git", ".pytest_cache")
$excludeFiles = @("*.pyc", "*.pyo")

Get-ChildItem -LiteralPath $resolvedDestination -Force | Remove-Item -Recurse -Force

Get-ChildItem -LiteralPath $repoRoot -Force | Where-Object {
    $excludeDirs -notcontains $_.Name
} | ForEach-Object {
    $target = Join-Path $resolvedDestination $_.Name
    if ($_.PSIsContainer) {
        Copy-Item -LiteralPath $_.FullName -Destination $resolvedDestination -Recurse -Force -Exclude $excludeFiles
    } else {
        $skip = $false
        foreach ($pattern in $excludeFiles) {
            if ($_.Name -like $pattern) {
                $skip = $true
                break
            }
        }
        if (-not $skip) {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

Get-ChildItem -Recurse -Force -Directory -LiteralPath $resolvedDestination -Filter "__pycache__" |
    Remove-Item -Recurse -Force

Write-Host "Synced FreeCADAI to $resolvedDestination"
