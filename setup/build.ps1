# KobiCAM VMS — Windows kurulum paketini üretir.
# PyInstaller ile dist\KobiCAM üretir; Inno Setup varsa Setup.exe derler.

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $PSScriptRoot
Set-Location $Kok

$Python = $null
foreach ($aday in @("py", "python")) {
    $cmd = Get-Command $aday -ErrorAction SilentlyContinue
    if ($cmd) { $Python = $cmd.Source; break }
}
if (-not $Python) { throw "Python 3.10+ bulunamadı. python.org adresinden kurun." }

Write-Host "==> Bağımlılıklar"
$Onceki = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -m pip uninstall -y opencv-python opencv-contrib-python 2>$null | Out-Null
$ErrorActionPreference = $Onceki
& $Python -m pip install -r "$Kok\requirements.txt" pyinstaller -q
if ($LASTEXITCODE -ne 0) { throw "pip install başarısız." }

Write-Host "==> PyInstaller (onedir)"
& $Python -m PyInstaller "$Kok\kobicam.spec" --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller başarısız." }

$Exe = Join-Path $Kok "dist\KobiCAM\KobiCAM.exe"
if (-not (Test-Path $Exe)) { throw "Beklenen exe yok: $Exe" }
Write-Host "Uygulama: $Exe"

$Iscc = $null
$adaylar = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
foreach ($yol in $adaylar) {
    if (Test-Path $yol) { $Iscc = $yol; break }
}
if (-not $Iscc) {
    $found = Get-Command iscc -ErrorAction SilentlyContinue
    if ($found) { $Iscc = $found.Source }
}

if ($Iscc) {
    Write-Host "==> Inno Setup"
    & $Iscc "$Kok\setup\KobiCAM.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup derlemesi başarısız." }
    $Kurulum = Get-ChildItem "$Kok\setup\Output\KobiCAM-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($Kurulum) {
        Write-Host "Kurulum: $($Kurulum.FullName)"
    }
} else {
    Write-Host "Inno Setup 6 bulunamadı. dist\KobiCAM klasörü hazır."
    Write-Host "Setup.exe için: winget install JRSoftware.InnoSetup  sonra bu betiği tekrar çalıştırın."
}
