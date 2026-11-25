# Installe Déclic pour Windows depuis les sources, pour l'utilisateur courant (sans droits administrateur).
#
#   powershell -ExecutionPolicy Bypass -File windows\installer.ps1                  installer
#   powershell -ExecutionPolicy Bypass -File windows\installer.ps1 -Desinstaller    désinstaller
#
# Étapes : vérifie Python (3.11 ou plus) et Node.js, lance les tests du service, installe la barre
# (Electron), crée le raccourci « Déclic » du menu Démarrer, puis lance Déclic (Alt+Espace).
# Vos réglages (%APPDATA%\Declic) sont conservés à la désinstallation.

param([switch]$Desinstaller)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Racine = Split-Path -Parent $PSScriptRoot
$Barre = Join-Path $Racine 'windows'
$Coeur = Join-Path $Racine 'coeur'
$Raccourci = Join-Path ([Environment]::GetFolderPath('Programs')) 'Déclic.lnk'
$Electron = Join-Path $Barre 'node_modules\electron\dist\electron.exe'

function Etape($texte) { Write-Host "`n» $texte" -ForegroundColor Cyan }

# Lance un programme et renvoie son code de retour. Windows PowerShell 5.1 prend pour une erreur fatale
# tout texte écrit sur la sortie d'erreur (comptes rendus des tests, avertissements de npm) :
# on le laisse passer, et seul le code de retour compte.
function Lancer([string]$programme, [string[]]$arguments, [int]$dernieres = 0) {
    $precedent = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Les lignes vides de la sortie d'erreur deviennent « RemoteException » : on les retire
        $sortie = & $programme @arguments 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -ne 'System.Management.Automation.RemoteException' }
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $precedent }
    if ($dernieres -gt 0) { $sortie | Select-Object -Last $dernieres | ForEach-Object { Write-Host "  $_" } }
    return $code
}

if ($Desinstaller) {
    Etape 'Arrêt de Déclic'
    Get-CimInstance Win32_Process -Filter "Name='electron.exe'" |
        Where-Object { $_.CommandLine -like "*$Barre*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Etape 'Suppression du raccourci et du démarrage automatique'
    Remove-Item $Raccourci -ErrorAction SilentlyContinue
    $Run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    (Get-Item $Run).Property | Where-Object {
        (Get-ItemPropertyValue $Run $_) -like "*$Barre*"
    } | ForEach-Object { Remove-ItemProperty $Run $_ }
    Write-Host "`nDéclic est désinstallé. Vos réglages restent dans $env:APPDATA\Declic." -ForegroundColor Green
    return
}

# --- Python ---------------------------------------------------------------------------
Etape 'Recherche de Python 3.11 ou plus récent'
function TrouverPython {
    $racinePy = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path $racinePy) {
        $exe = Get-ChildItem $racinePy -Directory -Filter 'Python3*' |
            Sort-Object { [int]($_.Name -replace '\D', '') } -Descending |
            ForEach-Object { Join-Path $_.FullName 'python.exe' } | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($exe) { return $exe }
    }
    foreach ($commande in 'py', 'python') {
        $chemin = (Get-Command $commande -ErrorAction SilentlyContinue).Source
        if ($chemin -and $chemin -notlike '*WindowsApps*') { return $chemin }
    }
    return $null
}
$Python = TrouverPython
if (-not $Python) {
    Write-Host 'Python est introuvable.' -ForegroundColor Yellow
    $reponse = Read-Host 'Installer Python 3.13 pour votre compte avec winget ? (o/n)'
    if ($reponse -notmatch '^[oOyY]') { throw "Installez Python 3.11 ou plus récent, puis relancez l'installateur." }
    $null = Lancer 'winget' @('install', '--id', 'Python.Python.3.13', '--scope', 'user', '--silent', '--accept-package-agreements', '--accept-source-agreements') 3
    $Python = TrouverPython
    if (-not $Python) { throw "Python n'a pas pu être installé." }
}
$version = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$version -lt [version]'3.11') { throw "Python $version est trop ancien : il faut la version 3.11 ou plus récente." }
Write-Host "Python $version : $Python"

# --- Tests du service --------------------------------------------------------------------
Etape 'Tests du service Déclic'
Push-Location $Coeur
try {
    if ((Lancer $Python @('-m', 'unittest') 3) -ne 0) { throw 'Les tests du service ont échoué : installation interrompue.' }
} finally { Pop-Location }

# --- Barre (Electron) -------------------------------------------------------------------
Etape 'Installation de la barre (Electron)'
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js est introuvable. Installez-le (winget install OpenJS.NodeJS.LTS), puis relancez l'installateur."
}
Push-Location $Barre
try {
    if ((Lancer 'npm.cmd' @('install', '--no-fund', '--no-audit') 2) -ne 0) { throw "L'installation de la barre a échoué." }
} finally { Pop-Location }

# --- Raccourci du menu Démarrer -----------------------------------------------------------
Etape 'Création du raccourci « Déclic » dans le menu Démarrer'
$shell = New-Object -ComObject WScript.Shell
$lien = $shell.CreateShortcut($Raccourci)
$lien.TargetPath = $Electron
$lien.Arguments = "`"$Barre`""
$lien.WorkingDirectory = $Barre
$lien.IconLocation = (Join-Path $Barre 'icones\declic.ico')
$lien.Description = 'Déclic : barre de commande (Alt+Espace)'
$lien.Save()

# --- Lancement ----------------------------------------------------------------------------
Etape 'Lancement de Déclic'
Start-Process -FilePath $Electron -ArgumentList "`"$Barre`"", '--ouvrir' -WorkingDirectory $Barre
Write-Host "`nDéclic est installé. Appuyez sur Alt+Espace pour ouvrir la barre." -ForegroundColor Green
Write-Host "Clic droit sur l'icône de Déclic (zone de notification) pour « Démarrer avec Windows »."
