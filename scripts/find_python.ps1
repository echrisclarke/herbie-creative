# Find a usable Python 3.12+ executable on Windows.
# Prints one absolute path to stdout, or exits 1 if none found.
# Does not require Python to be on PATH: searches launchers, registry,
# winget/python.org folders, Scoop, Conda, and common Program Files layouts.
# Skips the Windows Store stub under WindowsApps.
$ErrorActionPreference = 'SilentlyContinue'
$minMajor = 3
$minMinor = 12

function Refresh-ProcessPath {
    try {
        $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $user = [Environment]::GetEnvironmentVariable('Path', 'User')
        if ($machine -or $user) {
            $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
        }
    } catch {}
}

function Test-PythonVersion([string]$Exe) {
    if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) { return $false }
    if ($Exe -match 'WindowsApps') { return $false }
    try {
        $ver = & $Exe -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
        if (-not $ver) { return $false }
        $parts = $ver.ToString().Trim().Split('.')
        $maj = [int]$parts[0]
        $min = [int]$parts[1]
        return ($maj -gt $minMajor) -or ($maj -eq $minMajor -and $min -ge $minMinor)
    } catch {
        return $false
    }
}

function Get-PythonMachine([string]$Exe) {
    try {
        $m = & $Exe -c "import platform; print(platform.machine())" 2>$null
        return ($m | Out-String).Trim()
    } catch {
        return ''
    }
}

function Add-Candidate(
    [System.Collections.Generic.List[string]]$List,
    [string]$Path
) {
    if (-not $Path) { return }
    $trimmed = $Path.Trim().Trim('"')
    if (-not $trimmed) { return }
    if ($trimmed -match 'WindowsApps') { return }
    if (-not (Test-Path -LiteralPath $trimmed)) { return }
    [void]$List.Add($trimmed)
}

function Add-PythonTree(
    [System.Collections.Generic.List[string]]$List,
    [string]$Root,
    [int]$Depth = 3
) {
    if (-not $Root -or -not (Test-Path -LiteralPath $Root)) { return }
    # Prefer shallow known layouts first (fast), then a bounded recurse.
    foreach ($rel in @(
            'python.exe',
            'Python312\python.exe',
            'Python313\python.exe',
            'Python314\python.exe',
            'Python311\python.exe',
            'current\python.exe'
        )) {
        Add-Candidate $List (Join-Path $Root $rel)
    }
    Get-ChildItem -LiteralPath $Root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        Add-Candidate $List (Join-Path $_.FullName 'python.exe')
        Add-Candidate $List (Join-Path $_.FullName 'python\python.exe')
    }
    if ($Depth -gt 0) {
        Get-ChildItem -LiteralPath $Root -Recurse -Depth $Depth -Filter python.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch 'WindowsApps|Lib\\venv|\\Tests\\' } |
            ForEach-Object { Add-Candidate $List $_.FullName }
    }
}

Refresh-ProcessPath

$candidates = New-Object System.Collections.Generic.List[string]

# Official / winget / Microsoft Store (real) installs
Add-PythonTree $candidates (Join-Path $env:LOCALAPPDATA 'Programs\Python') 4
Add-PythonTree $candidates (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher') 2
Add-PythonTree $candidates (Join-Path $env:ProgramFiles 'Python') 3
Add-PythonTree $candidates (Join-Path ${env:ProgramFiles(x86)} 'Python') 3

# Versioned Program Files roots used by some installers
foreach ($ver in @('Python314', 'Python313', 'Python312', 'Python311', 'Python310')) {
    Add-Candidate $candidates (Join-Path (Join-Path $env:ProgramFiles $ver) 'python.exe')
    Add-Candidate $candidates (Join-Path (Join-Path ${env:ProgramFiles(x86)} $ver) 'python.exe')
    Add-Candidate $candidates (Join-Path $env:LOCALAPPDATA "Programs\Python\$ver\python.exe")
}

# Classic python.org layout (C:\Python3x)
foreach ($drive in @($env:SystemDrive, 'C:', 'D:')) {
    if (-not $drive) { continue }
    $root = Join-Path $drive '\'
    Get-ChildItem -LiteralPath $root -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
        ForEach-Object { Add-Candidate $candidates (Join-Path $_.FullName 'python.exe') }
}

# Scoop / Chocolatey / Conda / pyenv-win / winget package cache
Add-PythonTree $candidates (Join-Path $env:USERPROFILE 'scoop\apps\python') 3
Add-PythonTree $candidates (Join-Path $env:USERPROFILE 'scoop\apps\python312') 2
Add-PythonTree $candidates (Join-Path $env:USERPROFILE 'scoop\apps\python313') 2
Add-Candidate $candidates (Join-Path $env:ChocolateyInstall 'bin\python.exe')
Add-PythonTree $candidates 'C:\tools\python' 2
Add-PythonTree $candidates (Join-Path $env:USERPROFILE 'anaconda3') 2
Add-PythonTree $candidates (Join-Path $env:USERPROFILE 'miniconda3') 2
Add-PythonTree $candidates (Join-Path $env:USERPROFILE 'AppData\Local\miniconda3') 2
Add-PythonTree $candidates (Join-Path $env:USERPROFILE 'AppData\Local\anaconda3') 2
Add-PythonTree $candidates (Join-Path $env:USERPROFILE '.pyenv\pyenv-win\versions') 3
Add-PythonTree $candidates (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') 5
Add-PythonTree $candidates (Join-Path $env:ProgramData 'chocolatey\lib') 4

# Public / lab PCs: any Program Files* folder whose name contains Python
foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if (-not $pf -or -not (Test-Path -LiteralPath $pf)) { continue }
    Get-ChildItem -LiteralPath $pf -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)python' } |
        ForEach-Object { Add-PythonTree $candidates $_.FullName 2 }
}

# Registry InstallPath (most reliable when not on PATH)
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
            $p = $props.$name
            if (-not $p) { continue }
            if ($p -match '\.exe$') {
                Add-Candidate $candidates $p
            } else {
                Add-Candidate $candidates (Join-Path $p 'python.exe')
            }
        }
    }
}

# py.exe launcher (can resolve installs that are off PATH)
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    foreach ($launch in @(
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe'),
            (Join-Path $env:SystemRoot 'py.exe'),
            (Join-Path $env:ProgramFiles 'Python\Launcher\py.exe')
        )) {
        if (Test-Path -LiteralPath $launch) {
            $py = Get-Item -LiteralPath $launch
            break
        }
    }
}
if ($py) {
    $pyExe = if ($py.Source) { $py.Source } else { $py.FullName }
    foreach ($args in @(
            @('-3'),
            @('-3-64'),
            @('-3.14'),
            @('-3.13'),
            @('-3.12')
        )) {
        try {
            $exe = (& $pyExe @args -c 'import sys; print(sys.executable)' 2>$null)
            if ($exe) { Add-Candidate $candidates ($exe.ToString().Trim()) }
        } catch {}
    }
}

# PATH / where.exe (after Refresh-ProcessPath)
foreach ($name in @('python', 'python3')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch 'WindowsApps') {
        Add-Candidate $candidates $cmd.Source
    }
}
try {
    $whereOut = & where.exe python 2>$null
    foreach ($line in @($whereOut)) {
        Add-Candidate $candidates $line
    }
} catch {}

$hostArch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
$unique = @($candidates | Where-Object { $_ } | Select-Object -Unique)
$ranked = New-Object System.Collections.Generic.List[object]
foreach ($exe in $unique) {
    if (-not (Test-PythonVersion $exe)) { continue }
    $machine = Get-PythonMachine $exe
    $isArmPy = ($machine -match 'ARM|aarch64') -or ($exe -match '(?i)arm64')
    # Lower score = better. Prefer non-ARM Python on ARM Windows hosts.
    $score = 1
    if ($hostArch -match 'Arm' -and -not $isArmPy) { $score = 0 }
    if ($hostArch -match 'Arm' -and $isArmPy) { $score = 2 }
    [void]$ranked.Add([pscustomobject]@{ Exe = $exe; Score = $score })
}

$best = $ranked | Sort-Object Score, Exe | Select-Object -First 1
if ($best) {
    Write-Output $best.Exe
    exit 0
}

exit 1
