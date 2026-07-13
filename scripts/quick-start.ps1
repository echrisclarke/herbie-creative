# Herbie Creative Quick start (Windows)
# Downloads to Desktop, ensures Python 3.12+, starts the app.
# Finds Python via registry / common install folders / py launcher, not PATH alone.
# Installs without relying on Microsoft Store winget source (public PC friendly).
$ErrorActionPreference = 'Stop'

$desk = [Environment]::GetFolderPath('Desktop')
Set-Location $desk

function Refresh-HerbiePath {
  try {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ($machine -or $user) {
      $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
    }
  } catch {}
  foreach ($ver in @('Python314', 'Python313', 'Python312', 'Python311')) {
    $dir = Join-Path $env:LOCALAPPDATA "Programs\Python\$ver"
    if (Test-Path -LiteralPath $dir) {
      $env:Path = "$dir;$dir\Scripts;$env:Path"
    }
  }
}

function Test-HerbiePy([string]$Exe, [string[]]$Prefix = @()) {
  if (-not $Exe) { return $false }
  if ($Exe -match 'WindowsApps') { return $false }
  try {
    if ($Prefix.Count -eq 0 -and -not (Test-Path -LiteralPath $Exe)) { return $false }
    & $Exe @Prefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch {
    return $false
  }
}

function Find-HerbiePy {
  Refresh-HerbiePath

  # Prefer the shared finder from GitHub (same logic Open App.bat uses).
  $finderUrl = 'https://raw.githubusercontent.com/echrisclarke/herbie-creative/main/scripts/find_python.ps1'
  $finderLocal = Join-Path $env:TEMP 'herbie-find-python.ps1'
  try {
    Invoke-WebRequest -Uri $finderUrl -OutFile $finderLocal -UseBasicParsing
    $found = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $finderLocal 2>$null
    if ($found) {
      $path = ($found | Select-Object -Last 1).ToString().Trim()
      if ($path -and (Test-HerbiePy $path)) { return ,@($path) }
    }
  } catch {}

  # Fallback inline search if the download fails (offline / raw blocked).
  $candidates = New-Object System.Collections.Generic.List[string]
  function Add-Hit([string]$Path) {
    if (-not $Path) { return }
    $p = $Path.Trim().Trim('"')
    if (-not $p -or $p -match 'WindowsApps') { return }
    if (-not (Test-Path -LiteralPath $p)) { return }
    [void]$candidates.Add($p)
  }

  foreach ($hive in @(
      'HKCU:\Software\Python\PythonCore',
      'HKLM:\Software\Python\PythonCore',
      'HKLM:\Software\WOW6432Node\Python\PythonCore'
    )) {
    Get-ChildItem -LiteralPath $hive -ErrorAction SilentlyContinue | ForEach-Object {
      $install = Join-Path $_.PSPath 'InstallPath'
      $props = Get-ItemProperty -LiteralPath $install -ErrorAction SilentlyContinue
      if (-not $props) { return }
      foreach ($name in @('(default)', 'ExecutablePath')) {
        $v = $props.$name
        if (-not $v) { continue }
        if ($v -match '\.exe$') { Add-Hit $v } else { Add-Hit (Join-Path $v 'python.exe') }
      }
    }
  }

  foreach ($root in @(
      "$env:LocalAppData\Programs\Python",
      "$env:ProgramFiles\Python",
      "${env:ProgramFiles(x86)}\Python",
      "$env:LocalAppData\Microsoft\WinGet\Packages",
      "$env:UserProfile\scoop\apps\python",
      "$env:UserProfile\anaconda3",
      "$env:UserProfile\miniconda3",
      "$env:UserProfile\AppData\Local\miniconda3",
      "$env:UserProfile\AppData\Local\anaconda3",
      "$env:UserProfile\.pyenv\pyenv-win\versions"
    )) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    Get-ChildItem -LiteralPath $root -Recurse -Depth 4 -Filter python.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -notmatch 'WindowsApps|Lib\\venv' } |
      ForEach-Object { Add-Hit $_.FullName }
  }

  foreach ($ver in @('Python314', 'Python313', 'Python312', 'Python311')) {
    Add-Hit "$env:LocalAppData\Programs\Python\$ver\python.exe"
    Add-Hit "$env:ProgramFiles\$ver\python.exe"
    Add-Hit "${env:ProgramFiles(x86)}\$ver\python.exe"
  }

  Get-ChildItem -LiteralPath "$env:SystemDrive\" -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
    ForEach-Object { Add-Hit (Join-Path $_.FullName 'python.exe') }

  $pyLaunch = @(
    (Get-Command py -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "$env:LocalAppData\Programs\Python\Launcher\py.exe",
    "$env:SystemRoot\py.exe"
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
  if ($pyLaunch) {
    foreach ($args in @(@('-3'), @('-3-64'), @('-3.14'), @('-3.13'), @('-3.12'))) {
      try {
        $exe = (& $pyLaunch @args -c 'import sys; print(sys.executable)' 2>$null)
        if ($exe) { Add-Hit ($exe.ToString().Trim()) }
      } catch {}
    }
  }

  foreach ($name in @('python', 'python3')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { Add-Hit $cmd.Source }
  }
  try {
    foreach ($line in @(& where.exe python 2>$null)) { Add-Hit $line }
  } catch {}

  foreach ($exe in ($candidates | Select-Object -Unique)) {
    if (Test-HerbiePy $exe) { return ,@($exe) }
  }
  return $null
}

function Install-HerbiePython([string]$Method = 'auto') {
  $installUrl = 'https://raw.githubusercontent.com/echrisclarke/herbie-creative/main/scripts/install_python_windows.ps1'
  $installLocal = Join-Path $env:TEMP 'herbie-install-python.ps1'
  $prev = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    Invoke-WebRequest -Uri $installUrl -OutFile $installLocal -UseBasicParsing
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installLocal -Method $Method
  } catch {
    Write-Host ("Install helper error: " + $_.Exception.Message)
  } finally {
    $ErrorActionPreference = $prev
  }
}

Write-Host "Checking for Python 3.12+..."
$py = Find-HerbiePy
if (-not $py) {
  Write-Host "Python 3.12+ not found for this user session."
  Write-Host "On public / shared PCs, winget often fails on the Microsoft Store source."
  Write-Host "Trying winget (community source) then a per-user python.org install..."
  Install-HerbiePython -Method winget
  Refresh-HerbiePath
  Start-Sleep -Seconds 2
  $py = Find-HerbiePy
}
if (-not $py) {
  Write-Host "Still no python.exe. Installing Python 3.12 for the current user from python.org..."
  Install-HerbiePython -Method pythonorg
  Refresh-HerbiePath
  Start-Sleep -Seconds 3
  $py = Find-HerbiePy
}
if (-not $py) {
  Start-Process "https://www.python.org/downloads/"
  throw @"
Could not find or install Python 3.12+ in this session.

On a public computer this usually means:
  - winget hit a Microsoft Store (msstore) error, or needs admin you do not have
  - Python is installed for another account, or was never installed for this user

Fix: download Python from python.org, run the installer, choose "Install for current user",
check "Add python.exe to PATH", finish, close PowerShell, open a new window, and paste the Quick start line again.
"@
}
Write-Host ("Python OK: " + ($py -join ' '))

if (-not (Test-Path 'herbie-creative\run_app.py')) {
  Write-Host "Downloading Herbie Creative..."
  Invoke-WebRequest -Uri 'https://github.com/echrisclarke/herbie-creative/archive/refs/heads/main.zip' -OutFile 'herbie-creative.zip'
  Expand-Archive -Path 'herbie-creative.zip' -DestinationPath . -Force
  if (Test-Path 'herbie-creative') { Remove-Item 'herbie-creative' -Recurse -Force }
  Rename-Item 'herbie-creative-main' 'herbie-creative'
  Remove-Item 'herbie-creative.zip' -Force
}

# Prefer the repo finder once the tree is on disk.
$repoFinder = Join-Path (Get-Location) 'herbie-creative\scripts\find_python.ps1'
if (Test-Path -LiteralPath $repoFinder) {
  try {
    $found = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $repoFinder 2>$null
    if ($found) {
      $path = ($found | Select-Object -Last 1).ToString().Trim()
      if ($path -and (Test-HerbiePy $path)) { $py = ,@($path) }
    }
  } catch {}
}

Set-Location 'herbie-creative'
Write-Host "Starting app (leave this window open)..."
$runArgs = @()
if ($py.Count -gt 1) { $runArgs += $py[1..($py.Count - 1)] }
$runArgs += 'run_app.py'
& $py[0] @runArgs
