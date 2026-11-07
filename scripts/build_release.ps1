<#
.SYNOPSIS
    一键构建 eclipse health Windows 安装包：PyInstaller sidecar → Tauri bundle。

.DESCRIPTION
    1. 用 backend/.venv 里的 PyInstaller 打包后端（onefile），产物
       backend/packaging/dist/eclipse-health-backend.exe；
    2. 按 Tauri externalBin 命名拷贝到 src-tauri/binaries/
       eclipse-health-backend-<target-triple>.exe；
    3. 运行 npm run tauri build（前端由 beforeBuildCommand 重建）。
    任一步失败立即停止并打印原因。

.EXAMPLE
    powershell -File scripts\build_release.ps1
    powershell -File scripts\build_release.ps1 -Bundles msi
#>
[CmdletBinding()]
param(
    [ValidateSet("nsis", "msi", "all")]
    [string]$Bundles = "nsis",
    [switch]$SkipPyInstaller,
    [switch]$SkipWheelhouse,
    [switch]$WheelhouseCommunity
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Packaging = Join-Path $Backend "packaging"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$Spec = Join-Path $Packaging "eclipse-health-backend.spec"
$DistDir = Join-Path $Packaging "dist"
$WorkDir = Join-Path $Packaging "build"
$BinariesDir = Join-Path $Root "src-tauri\binaries"
$SidecarName = "eclipse-health-backend.exe"
$TotalTimer = [System.Diagnostics.Stopwatch]::StartNew()

function Fail([string]$Message) {
    Write-Host "FAIL: $Message" -ForegroundColor Red
    exit 1
}

function Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

# ---------------------------------------------------------------- 前置检查
Step "检查工具链"
if (-not (Test-Path $Python)) { Fail "找不到后端 venv: $Python" }
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { Fail "venv 里没有 PyInstaller（先装 dev 依赖）" }
if (-not (Test-Path (Join-Path $Root "node_modules"))) { Fail "缺少 node_modules，先运行 npm install" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "npm 不在 PATH 中" }
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { Fail "cargo 不在 PATH 中（需要 Rust 工具链）" }

$TargetTriple = (& rustc -vV | Select-String '^host:').ToString().Split(':')[1].Trim()
if (-not $TargetTriple) { Fail "无法从 rustc -vV 解析 host triple" }
Write-Host "    root      : $Root"
Write-Host "    toolchain : $TargetTriple"
Write-Host "    bundles   : $Bundles"

# ---------------------------------------------------------------- 0. 模块包 + 离线依赖仓库
$ModulesDist = Join-Path $Root "dist\modules"
if (-not (Test-Path $ModulesDist)) {
    Step "打包官方/社区模块（dist/modules 缺失）"
    & $Python (Join-Path $Root "scripts\pack_official_modules.py")
    if ($LASTEXITCODE -ne 0) { Fail "pack_official_modules.py 失败（exit $LASTEXITCODE）" }
}

if (-not $SkipWheelhouse) {
    Step "构建模块离线依赖仓库（wheelhouse）"
    $WheelArgs = @((Join-Path $Root "scripts\build_module_wheelhouse.py"))
    if ($WheelhouseCommunity) { $WheelArgs += "--include-community" }
    & $Python @WheelArgs
    if ($LASTEXITCODE -ne 0) { Fail "wheelhouse 构建失败（exit $LASTEXITCODE）" }
}

# ---------------------------------------------------------------- 1. sidecar
if (-not $SkipPyInstaller) {
    Step "打包后端 sidecar（PyInstaller onedir）"
    $PyTimer = [System.Diagnostics.Stopwatch]::StartNew()
    # Agg + 限制 BLAS 线程：构建期无人值守，也不需要 GUI 后端。
    $env:MPLBACKEND = "Agg"
    $env:OPENBLAS_NUM_THREADS = "2"
    $env:OMP_NUM_THREADS = "2"
    # 用 `python -m PyInstaller` 而不是 Scripts\pyinstaller.exe：复制 venv 时
    # 入口 exe 的 shebang 可能仍指向旧目录，直接用 python 可保证当前 venv 生效。
    & $Python -m PyInstaller --noconfirm --clean --distpath $DistDir --workpath $WorkDir $Spec
    if ($LASTEXITCODE -ne 0) { Fail "PyInstaller 失败（exit $LASTEXITCODE），见上方输出" }
    $PyTimer.Stop()
    Write-Host ("    sidecar built in {0:N1}s" -f $PyTimer.Elapsed.TotalSeconds)
}
else {
    Step "跳过 PyInstaller（-SkipPyInstaller）"
}

$BuiltAppDir = Join-Path $DistDir "eclipse-health-backend"
$BuiltSidecar = Join-Path $BuiltAppDir $SidecarName
$BuiltInternal = Join-Path $BuiltAppDir "_internal"
if (-not (Test-Path $BuiltSidecar)) { Fail "sidecar 产物不存在: $BuiltSidecar" }
$SidecarBytes = (Get-ChildItem -Path $BuiltAppDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("    sidecar dir: {0} ({1:N1} MB)" -f $BuiltAppDir, ($SidecarBytes / 1MB))

# ---------------------------------------------------------------- 2. externalBin + _internal
Step "拷贝 sidecar 到 src-tauri（externalBin + onedir 的 _internal）"
New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null
$TargetSidecar = Join-Path $BinariesDir "eclipse-health-backend-$TargetTriple.exe"
Copy-Item -Force $BuiltSidecar $TargetSidecar
Write-Host "    -> $TargetSidecar"

# PyInstaller onedir 的 exe 必须在 _internal 旁边运行；Tauri resources 把它放到
# <install>/_internal（Windows 的 resource_dir 就是 exe 目录），与 sidecar 同级。
$TargetInternal = Join-Path $Root "src-tauri\_internal"
if (-not (Test-Path $BuiltInternal)) { Fail "_internal 不存在: $BuiltInternal" }
robocopy $BuiltInternal $TargetInternal /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "同步 _internal 失败（robocopy exit $LASTEXITCODE）" }
Write-Host "    -> $TargetInternal"

# ---------------------------------------------------------------- 3. Tauri build
Step "Tauri build（含 npm run build）"
$TauriTimer = [System.Diagnostics.Stopwatch]::StartNew()
Push-Location $Root
try {
    npm run tauri build -- --bundles $Bundles
    if ($LASTEXITCODE -ne 0) { Fail "tauri build 失败（exit $LASTEXITCODE）" }
}
finally {
    Pop-Location
}
$TauriTimer.Stop()
Write-Host ("    tauri build in {0:N1}s" -f $TauriTimer.Elapsed.TotalSeconds)

# ---------------------------------------------------------------- 4. 产物
Step "产物"
$BundleRoot = Join-Path $Root "src-tauri\target\release\bundle"
$Artifacts = @()
if (Test-Path $BundleRoot) {
    $Artifacts = @(Get-ChildItem -Path $BundleRoot -Recurse -File |
        Where-Object { $_.Extension -in @(".exe", ".msi") })
}
if ($Artifacts.Count -eq 0) {
    Write-Host "    未找到安装包（可能只构建了可执行文件）" -ForegroundColor Yellow
}
foreach ($item in $Artifacts) {
    Write-Host ("    {0}  ({1:N1} MB)" -f $item.FullName, ($item.Length / 1MB))
}
$AppExe = Join-Path $Root "src-tauri\target\release\eclipse health.exe"
if (Test-Path $AppExe) {
    Write-Host ("    app exe : {0} ({1:N1} MB)" -f $AppExe, ((Get-Item $AppExe).Length / 1MB))
}

$TotalTimer.Stop()
Write-Host ("`nDONE in {0:N1}s" -f $TotalTimer.Elapsed.TotalSeconds) -ForegroundColor Green
