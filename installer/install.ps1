# FieldScribe one-click installer for Windows 10/11.
# Installs everything FieldScribe needs to run with NO internet afterwards:
#   Python 3.11 (if missing), the app and its packages, Ollama + a local AI model sized to this laptop,
#   the Whisper speech model, the offline street map, and Desktop / Start-menu shortcuts.
# Safe to run again: it upgrades the app and skips anything already done. Your records and keys are kept.
param(
    [switch]$NoAI,          # skip Ollama and the local AI model
    [switch]$NoMap,         # skip the offline street map
    [string]$Speech = "",   # Whisper model: large-v3-turbo | small | base (default: picked from memory)
    [string]$AIModel = ""   # qwen2.5:7b | qwen2.5:3b | qwen2.5:1.5b (default: picked from memory)
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Src = Split-Path -Parent $PSScriptRoot

# Edition: "full" (offline AI, best speech model) or "lite" (essentials only). Set by edition.txt in the download.
$Edition = "full"
$edFile = Join-Path $Src "edition.txt"
if (Test-Path $edFile) { $Edition = (Get-Content $edFile -Raw).Trim().ToLower() }
if ($Edition -eq "lite") {
    if (-not $PSBoundParameters.ContainsKey("NoAI")) { $NoAI = $true }
    if (-not $Speech) { $Speech = "base" }
}
$Dest = Join-Path $env:LOCALAPPDATA "Programs\FieldScribe"
$Log = Join-Path $env:TEMP "fieldscribe-install.log"
Start-Transcript -Path $Log -Force | Out-Null

function Step($n, $total, $text) { Write-Host ""; Write-Host ("[{0}/{1}] {2}" -f $n, $total, $text) -ForegroundColor Cyan }
function Ok($text) { Write-Host ("      OK  " + $text) -ForegroundColor Green }
function Note($text) { Write-Host ("      " + $text) -ForegroundColor Gray }
function Warn($text) { Write-Host ("      !   " + $text) -ForegroundColor Yellow }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function RefreshPath {
    $m = [Environment]::GetEnvironmentVariable("Path", "Machine"); $u = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$m;$u"
}

$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$freeGB = [math]::Round((Get-PSDrive -Name ($env:LOCALAPPDATA.Substring(0, 1))).Free / 1GB, 1)
$StepTotal = 8

Write-Host ""
Write-Host ("  FieldScribe installer ({0} edition)" -f $Edition) -ForegroundColor White
Write-Host "  Offline voice-to-record for 108 ambulance crews" -ForegroundColor Gray
Write-Host ("  This laptop: {0} GB memory, {1} GB free disk. Installing to {2}" -f $ramGB, $freeGB, $Dest) -ForegroundColor Gray
if ($Edition -eq "lite") { Note "Lite: essentials only, about 0.6 GB installed. Copilot uses Gemini online and the built-in protocol engine offline." }
elseif ($freeGB -lt 8) { Warn "Less than 8 GB free disk. The AI and speech models need about 3-7 GB." }

# ------------------------------------------------------------------ 1. copy the app
Step 1 $StepTotal "Copying FieldScribe"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
if ((Resolve-Path $Src).Path.TrimEnd('\') -ne (Resolve-Path $Dest).Path.TrimEnd('\')) {
    $null = robocopy $Src $Dest /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 `
        /XD .venv node_modules __pycache__ .pytest_cache .git (Join-Path $Src "backend\data") (Join-Path $Src "backend\models") (Join-Path $Src "backend\maps") `
        /XF .env *.zip
    if ($LASTEXITCODE -ge 8) { throw "Copying files failed (robocopy $LASTEXITCODE)" }
    # bring an existing setup's records, keys and downloaded models across, without overwriting the installed copy
    $srcEnv = Join-Path $Src "backend\.env"; $dstEnv = Join-Path $Dest "backend\.env"
    if ((Test-Path $srcEnv) -and -not (Test-Path $dstEnv)) { Copy-Item $srcEnv $dstEnv; Ok "Kept your settings and keys (backend\.env)" }
    foreach ($d in @("data", "models", "maps")) {
        $fromDir = Join-Path $Src "backend\$d"; $toDir = Join-Path $Dest "backend\$d"
        if (Test-Path $fromDir) {
            $null = robocopy $fromDir $toDir /E /XC /XN /XO /NFL /NDL /NJH /NJS /NP /R:1 /W:1
            Ok "Kept backend\$d"
        }
    }
}
$dstEnv = Join-Path $Dest "backend\.env"
if (-not (Test-Path $dstEnv)) { Copy-Item (Join-Path $Dest "backend\.env.example") $dstEnv }
Ok "App files in place"

# ------------------------------------------------------------------ 2. Python
Step 2 $StepTotal "Python"
$py = $null
foreach ($v in @("3.11", "3.12", "3.13")) {
    if (Have "py") { try { $p = & py "-$v" -c "import sys; print(sys.executable)" 2>$null; if ($LASTEXITCODE -eq 0 -and $p) { $py = $p.Trim(); break } } catch {} }
}
if (-not $py) {
    Note "Python 3.11 not found. Installing it for this user (no admin needed)..."
    if (Have "winget") {
        winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    } else {
        $exe = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
        Invoke-WebRequest "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $exe
        Start-Process $exe -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_tcltk=1" -Wait
    }
    RefreshPath
    $cand = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $cand) { $py = $cand } elseif (Have "py") { $py = (& py -3.11 -c "import sys; print(sys.executable)").Trim() }
}
if (-not $py) { throw "Python could not be installed. Install Python 3.11 from python.org (tick 'Add to PATH'), then run this again." }
Ok ("Python: " + (& $py --version))

# ------------------------------------------------------------------ 3. packages
Step 3 $StepTotal "FieldScribe packages (encryption, speech recognition)"
$venvPy = Join-Path $Dest ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { & $py -m venv (Join-Path $Dest ".venv"); Note "Created a private Python environment" }
& $venvPy -m pip install --upgrade pip --quiet --disable-pip-version-check
$reqs = @("-r", (Join-Path $Dest "backend\requirements.txt"), "-r", (Join-Path $Dest "backend\requirements-asr.txt"))
if ($Edition -ne "lite") { $reqs += @("-r", (Join-Path $Dest "backend\requirements-hub.txt")) }     # PostgreSQL hub driver
& $venvPy -m pip install --disable-pip-version-check -q @reqs
if ($LASTEXITCODE -ne 0) { throw "Installing Python packages failed. Check your internet connection and run this again." }
Ok "Packages installed"

# ------------------------------------------------------------------ 4. Ollama + local AI model
Step 4 $StepTotal "Offline AI for Copilot (Ollama + local model)"
if ($NoAI) { Note "Skipped (-NoAI). Copilot will use Gemini online and the built-in protocol engine offline." }
else {
    $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if (-not $ollama) { $c = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"; if (Test-Path $c) { $ollama = $c } }
    if (-not $ollama) {
        Note "Installing Ollama (free, runs AI models on this laptop)..."
        try {
            if (Have "winget") { winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements | Out-Host }
            else {
                $exe = Join-Path $env:TEMP "OllamaSetup.exe"
                Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $exe
                Start-Process $exe -ArgumentList "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES" -Wait
            }
        } catch { Warn ("Ollama install failed: " + $_.Exception.Message) }
        RefreshPath
        $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
        if (-not $ollama) { $c = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"; if (Test-Path $c) { $ollama = $c } }
    }
    if ($ollama) {
        Ok "Ollama ready"
        $upOk = $false
        try { $null = Invoke-WebRequest "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2; $upOk = $true } catch {}
        if (-not $upOk) { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep -Seconds 4 }
        if (-not $AIModel) { if ($ramGB -ge 14) { $AIModel = "qwen2.5:7b" } elseif ($ramGB -ge 7) { $AIModel = "qwen2.5:3b" } else { $AIModel = "qwen2.5:1.5b" } }
        $have = ""
        try { $have = (& $ollama list 2>&1 | Out-String) } catch {}
        if ($have -match [regex]::Escape($AIModel)) { Ok "$AIModel already downloaded" }
        else {
            Note "Downloading $AIModel (one time; 1-5 GB depending on the model)..."
            & $ollama pull $AIModel
            if ($LASTEXITCODE -eq 0) { Ok "$AIModel downloaded" } else { Warn "Model download failed. You can retry later in Settings -> Offline AI." }
        }
        $envText = Get-Content $dstEnv -Raw
        if ($envText -notmatch "(?m)^OLLAMA_MODEL=") { Add-Content $dstEnv "`r`nOLLAMA_MODEL=$AIModel" }
    } else { Warn "Ollama isn't available. Install it later from ollama.com, then use Settings -> Offline AI." }
}

# ------------------------------------------------------------------ 5. Whisper
Step 5 $StepTotal "Speech recognition model (Whisper, runs offline)"
if (-not $Speech) { if ($ramGB -ge 8) { $Speech = "large-v3-turbo" } else { $Speech = "small" } }
$mdir = Join-Path $Dest "backend\models\$Speech"
if ((Test-Path $mdir) -and (Get-ChildItem $mdir -ErrorAction SilentlyContinue)) { Ok "$Speech already downloaded" }
else {
    Note "Downloading Whisper $Speech (about 0.5-1.6 GB)..."
    Push-Location (Join-Path $Dest "backend")
    & $venvPy fetch_model.py $Speech
    $rc = $LASTEXITCODE
    Pop-Location
    if ($rc -eq 0) { Ok "Whisper $Speech ready" } else { Warn "Whisper download failed. Run again later; typing still works." }
}

# ------------------------------------------------------------------ 6. map
Step 6 $StepTotal "Offline street map (Bengaluru)"
$map = Test-Path (Join-Path $Dest "backend\maps\bengaluru.json")
if ($NoMap) { Note "Skipped (-NoMap). The live map is used when online." }
elseif ($map) { Ok "Map already on this laptop" }
else {
    Push-Location (Join-Path $Dest "backend")
    & $venvPy fetch_map.py
    $rc = $LASTEXITCODE
    Pop-Location
    if ($rc -eq 0) { Ok "Map downloaded" } else { Warn "Map servers were busy. Run again later; the live map works when online." }
}

# ------------------------------------------------------------------ 7. shortcuts
Step 7 $StepTotal "Shortcuts"
$pyw = Join-Path $Dest ".venv\Scripts\pythonw.exe"
$icon = Join-Path $Dest "installer\fieldscribe.ico"
$ws = New-Object -ComObject WScript.Shell
$startDir = Join-Path ([Environment]::GetFolderPath("Programs")) "FieldScribe"
New-Item -ItemType Directory -Force -Path $startDir | Out-Null
function Link($path, $target, $arguments, $desc) {
    $l = $ws.CreateShortcut($path); $l.TargetPath = $target; $l.Arguments = $arguments; $l.WorkingDirectory = $Dest
    $l.IconLocation = $icon; $l.Description = $desc; $l.Save()
}
Link (Join-Path ([Environment]::GetFolderPath("Desktop")) "FieldScribe.lnk") $pyw "`"$Dest\FieldScribe.pyw`"" "FieldScribe EMS clinical record"
Link (Join-Path $startDir "FieldScribe.lnk") $pyw "`"$Dest\FieldScribe.pyw`"" "FieldScribe EMS clinical record"
Link (Join-Path $startDir "FieldScribe (tablet mode).lnk") (Join-Path $Dest "start_tablet_mode.bat") "" "Serve FieldScribe to tablets on this Wi-Fi"
Link (Join-Path $startDir "Uninstall FieldScribe.lnk") (Join-Path $Dest "Uninstall FieldScribe.bat") "" "Remove FieldScribe"
Ok "Desktop and Start-menu shortcuts created"

# ------------------------------------------------------------------ 8. check + launch
Step 8 $StepTotal "Checking the install"
& $venvPy -c "import sys; sys.path.insert(0, r'$Dest\backend'); import app.main; print('      OK  Backend loads')"
if ($LASTEXITCODE -ne 0) { throw "The backend failed to load. See $Log" }
Stop-Transcript | Out-Null
Write-Host ""
Write-Host ("  FieldScribe ({0}) is installed." -f $Edition) -ForegroundColor Green
if ($Edition -eq "lite") { Write-Host "  To add the offline AI and the best speech model later, run the Full installer over it: records are kept." -ForegroundColor Gray }
Write-Host "  Open it any time from the FieldScribe icon on your Desktop or Start menu." -ForegroundColor Gray
Write-Host "  Demo PINs: crew 1080, ED 2020, supervisor 9090 (change them in Settings)." -ForegroundColor Gray
Write-Host ""
Start-Process $pyw -ArgumentList "`"$Dest\FieldScribe.pyw`"" -WorkingDirectory $Dest
