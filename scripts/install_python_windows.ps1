# Install Python 3.12+ for the current Windows user when missing.
# Avoids winget msstore (common public-PC / cert failure).
# Methods:
#   winget     - winget --source winget only
#   pythonorg  - silent per-user installer from python.org (no admin)
#   auto       - winget, then python.org (best for locked-down / public PCs)
param(
    [ValidateSet('auto', 'winget', 'pythonorg')]
    [string]$Method = 'auto'
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

function Write-Step([string]$Msg) {
    Write-Host $Msg
}

function Install-ViaWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Step 'winget is not available on this PC.'
        return $false
    }
    Write-Step 'Installing Python 3.12 via winget (community source only; skips Microsoft Store)...'
    $wingetArgs = @(
        'install', '-e', '--id', 'Python.Python.3.12',
        '--source', 'winget',
        '--accept-package-agreements', '--accept-source-agreements',
        '--disable-interactivity'
    )
    if ($env:PROCESSOR_ARCHITECTURE -match 'ARM') {
        $wingetArgs += @('--architecture', 'x64')
    }
    try {
        & winget @wingetArgs
        return $true
    } catch {
        Write-Step ("winget failed: " + $_.Exception.Message)
        return $false
    }
}

function Install-ViaPythonOrg {
    Write-Step 'Downloading Python 3.12 for this Windows user from python.org (no admin needed)...'
    $ver = '3.12.10'
    $url = "https://www.python.org/ftp/python/$ver/python-$ver-amd64.exe"
    $installer = Join-Path $env:TEMP 'herbie-python-3.12-amd64.exe'
    try {
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Write-Step ("Download failed: " + $_.Exception.Message)
        return $false
    }
    if (-not (Test-Path -LiteralPath $installer)) {
        Write-Step 'Download did not produce an installer file.'
        return $false
    }
    Write-Step 'Running silent per-user install. This can take a minute...'
    $argList = @(
        '/quiet',
        'InstallAllUsers=0',
        'PrependPath=1',
        'Include_launcher=1',
        'InstallLauncherAllUsers=0',
        'Include_test=0',
        'SimpleInstall=1'
    )
    try {
        $p = Start-Process -FilePath $installer -ArgumentList $argList -Wait -PassThru
        if ($null -ne $p.ExitCode -and $p.ExitCode -ne 0) {
            Write-Step ("python.org installer exit code: " + $p.ExitCode)
        }
        return $true
    } catch {
        Write-Step ("Installer failed: " + $_.Exception.Message)
        return $false
    } finally {
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    }
}

$okWinget = $false
$okOrg = $false
if ($Method -eq 'winget' -or $Method -eq 'auto') {
    $okWinget = Install-ViaWinget
}
if ($Method -eq 'pythonorg' -or $Method -eq 'auto') {
    # Always try python.org in auto mode: winget often "succeeds" or errors
    # (msstore) on public PCs without leaving a usable python.exe.
    if ($Method -eq 'pythonorg' -or -not $okWinget) {
        $okOrg = Install-ViaPythonOrg
    } elseif ($Method -eq 'auto') {
        # winget reported OK; still offer python.org only if caller re-invokes.
        $okOrg = $false
    }
}

if (-not $okWinget -and -not $okOrg) {
    Write-Step 'Could not install Python automatically on this machine.'
    exit 1
}
exit 0
