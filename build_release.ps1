# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    构建本地开箱即用 Windows 绿色发行包（VisionMonitorDesktop.exe）。
.PARAMETER VenvPython
    用于打包的 Python 解释器路径（需已安装 requirements.txt 与 pyinstaller）。
.PARAMETER DataDir
    可选：上游感知工程目录；若传入且存在，将按只读方式复制演示数据与 yolo26n.pt 权重至发行包 bundled_data/。
#>
param(
    [string]$VenvPython = "python",
    [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildDir = Join-Path $AppDir "_pyi_build"
$DistDir = Join-Path $AppDir "release"
$OutAppDir = Join-Path $DistDir "VisionMonitorDesktop"

Write-Output "=== [0/3] Closing any running VisionMonitorDesktop.exe ==="
Get-Process -Name "VisionMonitorDesktop" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 400
if (Test-Path $OutAppDir) {
    Get-ChildItem $OutAppDir -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.IsReadOnly) { $_.IsReadOnly = $false }
    }
}

Write-Output "=== [1/3] Running PyInstaller build ==="
Set-Location $AppDir
& $VenvPython -m PyInstaller --noconfirm --workpath $BuildDir --distpath $DistDir (Join-Path $AppDir "VisionMonitorDesktop.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

if ($DataDir -and (Test-Path $DataDir)) {
    Write-Output "=== [2/3] Copying read-only bundled data & yolo26n.pt from $DataDir ==="
    $Bundled = Join-Path $OutAppDir "bundled_data"
    foreach ($sub in @("out\web", "out\compare", "out\probe", "data\raw", "weights", "runs\detect\person_bootstrap")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Bundled $sub) | Out-Null
    }
    if (Test-Path "$DataDir\out\web") { Copy-Item "$DataDir\out\web\*.json" "$Bundled\out\web\" -Force -ErrorAction SilentlyContinue }
    if (Test-Path "$DataDir\out\compare") { Copy-Item "$DataDir\out\compare\*" "$Bundled\out\compare\" -Force -ErrorAction SilentlyContinue }
    if (Test-Path "$DataDir\out\probe") { Copy-Item "$DataDir\out\probe\*" "$Bundled\out\probe\" -Force -ErrorAction SilentlyContinue }
    if (Test-Path "$DataDir\data\raw") { Copy-Item "$DataDir\data\raw\*.mp4" "$Bundled\data\raw\" -Force -ErrorAction SilentlyContinue }
    if (Test-Path "$DataDir\weights\yolo26n.pt") { Copy-Item "$DataDir\weights\yolo26n.pt" "$Bundled\weights\yolo26n.pt" -Force }

    if (Test-Path "$DataDir\runs\detect\person_bootstrap") {
        Get-ChildItem "$DataDir\runs\detect\person_bootstrap" -File | Where-Object { $_.Extension -in ".png", ".jpg", ".jpeg", ".csv" } | ForEach-Object {
            Copy-Item $_.FullName "$Bundled\runs\detect\person_bootstrap\" -Force
        }
    }
    if (Test-Path "$DataDir\runs_web") {
        Get-ChildItem "$DataDir\runs_web" -Directory | ForEach-Object {
            $targetRun = Join-Path $Bundled ("runs_web\" + $_.Name)
            New-Item -ItemType Directory -Force -Path $targetRun | Out-Null
            Get-ChildItem $_.FullName -File | Where-Object { $_.Name -in "meta.json", "timeline.json", "audio.wav" } | ForEach-Object {
                Copy-Item $_.FullName $targetRun -Force
            }
        }
    }
    Get-ChildItem $Bundled -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.IsReadOnly) { $_.IsReadOnly = $false }
    }
} else {
    Write-Output "=== [2/3] Skipping bundled_data copy (pass -DataDir to bundle local datasets/weights) ==="
}

Copy-Item (Join-Path $AppDir "README.md") (Join-Path $OutAppDir "README.md") -Force
Copy-Item (Join-Path $AppDir "LICENSE") (Join-Path $OutAppDir "LICENSE") -Force
Copy-Item (Join-Path $AppDir "THIRD_PARTY_LICENSES.md") (Join-Path $OutAppDir "THIRD_PARTY_LICENSES.md") -Force

Write-Output "=== [3/3] Build summary ==="
$exeItem = Get-Item (Join-Path $OutAppDir "VisionMonitorDesktop.exe")
$totalBytes = (Get-ChildItem $OutAppDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Output ("EXE: {0} ({1:N2} MB)" -f $exeItem.FullName, ($exeItem.Length / 1MB))
Write-Output ("Total portable folder size: {0:N2} GB" -f ($totalBytes / 1GB))
