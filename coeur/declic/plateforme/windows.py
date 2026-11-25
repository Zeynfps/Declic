"""Plateforme Windows (10 et 11).

Uniquement des outils fournis avec Windows et Python, aucun module à installer :
  applis       : liste du menu Démarrer (Get-StartApps : programmes et applications du Store)
  ouverture    : os.startfile, explorer.exe
  presse-pap.  : API du presse-papiers (user32)
  notifications: notifications Windows (WinRT, via PowerShell)
  session      : LockWorkStation, SetSuspendState, shutdown
  énergie      : mode d'alimentation de Windows 11 (PowerSetActiveOverlayScheme), sinon powercfg
  fichiers     : index des dossiers personnels tenu par Déclic (Bureau, Documents, Téléchargements…)
  réglages     : registre (thème sombre, fichiers cachés)
  radios       : Wi-Fi et Bluetooth (Windows.Devices.Radios, via PowerShell)
  réseau       : netsh wlan (Wi-Fi enregistrés, Wi-Fi connecté)
  coffre       : Gestionnaire d'identifiants de Windows (CredWrite / CredRead / CredEnumerate)
  son          : API audio de Windows (Core Audio, IAudioEndpointVolume)
  musique      : touches multimédia (lecture/pause, suivant, précédent)
  Ne pas dér.  : profil « heures calmes » de Windows (objet COM QuietHoursSettings, celui de Windows 11)
  mode avion   : gestionnaire des radios de Windows (objet COM RadioManagement, celui des réglages rapides)
  écl. nocturne: état de l'éclairage nocturne dans le magasin de réglages de Windows (registre)
  navigateur   : adresse de l'onglet affiché lue par UI Automation (via PowerShell), frappe par SendInput :
                 remplissage des identifiants et envoi des questions aux IA, seulement sur la bonne page
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import threading
import time
import unicodedata
import uuid
import winreg
from ctypes import wintypes as wt
from pathlib import Path

from declic.plateforme.base import Application, Fichier, NonPrisEnCharge, Plateforme

log = logging.getLogger("declic")

_SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DUREE_CACHE_APPLIS = 120  # secondes
_INTERVALLE_INDEX = 15 * 60  # l'index des fichiers est refait toutes les 15 minutes
_MAX_FICHIERS = 400_000
_INTERVALLE_EVENEMENTS = 3  # secondes entre deux relevés (verrouillage, alimentation, Wi-Fi)
PREFIXE_COFFRE = "Declic:"
ATTRIBUTS_COFFRE = ("nom", "adresse", "identifiant", "titre")

# Mode d'alimentation de Windows 11 (« Efficacité énergétique », « Équilibré », « Performances optimales »)
_MODES_ENERGIE = {
    "economie": "961cc777-2547-4f9d-8174-7d86181b8a7a",
    "equilibre": "00000000-0000-0000-0000-000000000000",
    "performance": "ded574b5-45a0-4f42-8737-46345c09c238",
}
# Modes classiques de powercfg, si le mode d'alimentation de Windows 11 n'est pas disponible
_SCHEMAS_ENERGIE = {
    "economie": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "equilibre": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
}

# Dossiers exclus de l'index des fichiers (en plus des dossiers cachés et de ceux qui commencent par « . »)
_EXCLUS = {"node_modules", "__pycache__", "appdata", "$recycle.bin", "site-packages", ".git", "venv", ".venv"}


# --------------------------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------------------------

def _decoder(octets: bytes) -> str:
    """Sortie d'un outil de Windows : UTF-8 si possible, sinon l'encodage de la console (OEM)."""
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return octets.decode("oem", errors="replace")


def _executer(args: list[str], timeout: float = 15) -> subprocess.CompletedProcess:
    """Lance une commande sans ouvrir de fenêtre de console ; stdout et stderr sont décodés."""
    fini = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=_SANS_FENETRE)
    fini.stdout, fini.stderr = _decoder(fini.stdout or b""), _decoder(fini.stderr or b"")
    return fini


def _powershell(script: str, timeout: float = 20, env: dict[str, str] | None = None) -> str:
    """Exécute un script PowerShell (Windows PowerShell 5.1, toujours présent) et renvoie sa sortie."""
    prefixe = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; $ErrorActionPreference = 'Stop'; "
    environnement = {**os.environ, **(env or {})}
    fini = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", prefixe + script],
        capture_output=True, timeout=timeout, creationflags=_SANS_FENETRE, env=environnement,
        text=True, encoding="utf-8", errors="replace")
    if fini.returncode != 0:
        detail = (fini.stderr or fini.stdout).strip()
        raise NonPrisEnCharge(detail.splitlines()[0] if detail else f"PowerShell a échoué (code {fini.returncode})")
    return fini.stdout.strip()


def _sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").casefold()


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def depuis(cls, texte: str) -> "_GUID":
        u = uuid.UUID(texte)
        g = cls()
        g.Data1, g.Data2, g.Data3 = u.time_low, u.time_mid, u.time_hi_version
        g.Data4[:] = u.bytes[8:]
        return g


def _diffuser_changement(zone: str) -> None:
    """Prévient les fenêtres ouvertes qu'un réglage a changé (thème…)."""
    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
    resultat = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(wt.HWND(HWND_BROADCAST), WM_SETTINGCHANGE, 0, zone,
                                             SMTO_ABORTIFHUNG, 1000, ctypes.byref(resultat))


def _lire_registre(chemin: str, nom: str, defaut=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin) as cle:
            return winreg.QueryValueEx(cle, nom)[0]
    except OSError:
        return defaut


def _ecrire_registre(chemin: str, nom: str, valeur: int) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, chemin, 0, winreg.KEY_SET_VALUE) as cle:
        winreg.SetValueEx(cle, nom, 0, winreg.REG_DWORD, int(valeur))


# --- Gestionnaire d'identifiants (advapi32) ---------------------------------------------------

class _CREDENTIAL_ATTRIBUTE(ctypes.Structure):
    _fields_ = [("Keyword", wt.LPWSTR), ("Flags", wt.DWORD), ("ValueSize", wt.DWORD),
                ("Value", ctypes.POINTER(ctypes.c_ubyte))]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wt.DWORD),
                ("AttributeCount", wt.DWORD), ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTE)),
                ("TargetAlias", wt.LPWSTR), ("UserName", wt.LPWSTR)]


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_TAILLE_MAX_ATTRIBUT = 256  # octets, limite de Windows


def _advapi32():
    a = ctypes.WinDLL("advapi32", use_last_error=True)
    a.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wt.DWORD]
    a.CredWriteW.restype = wt.BOOL
    a.CredEnumerateW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD),
                                 ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)))]
    a.CredEnumerateW.restype = wt.BOOL
    a.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
    a.CredDeleteW.restype = wt.BOOL
    a.CredFree.argtypes = [ctypes.c_void_p]
    a.CredFree.restype = None
    return a


# --- Son (Core Audio, objets COM appelés par leur table de méthodes) --------------------------

_CLSID_MMDeviceEnumerator = "bcde0395-e52f-467c-8e3d-c4579291692e"
_IID_IMMDeviceEnumerator = "a95664d2-9614-4f35-a746-de8db63617e6"
_IID_IAudioEndpointVolume = "5cdf2c82-841e-4546-9722-0cf74078229a"
_SORTIE, _ENTREE = 0, 1  # eRender, eCapture


def _methode(objet: ctypes.c_void_p, index: int, *argtypes):
    """Méthode n° index de la table d'un objet COM (le 1er argument est l'objet lui-même)."""
    table = ctypes.cast(objet, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])


def _verifier(hr: int, quoi: str) -> None:
    if hr < 0:
        raise NonPrisEnCharge(f"{quoi} : erreur Windows 0x{hr & 0xFFFFFFFF:08x}")


class _Volume:
    """Volume du périphérique audio par défaut (sortie ou entrée)."""

    def __init__(self, flux: int):
        self.flux = flux
        self.objets: list[ctypes.c_void_p] = []

    def __enter__(self):
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0)  # déjà initialisé dans ce fil : sans effet
        enumerateur = ctypes.c_void_p()
        _verifier(ole32.CoCreateInstance(ctypes.byref(_GUID.depuis(_CLSID_MMDeviceEnumerator)), None, 0x17,
                                         ctypes.byref(_GUID.depuis(_IID_IMMDeviceEnumerator)),
                                         ctypes.byref(enumerateur)), "Son")
        self.objets.append(enumerateur)
        peripherique = ctypes.c_void_p()
        hr = _methode(enumerateur, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
            enumerateur, self.flux, 0, ctypes.byref(peripherique))
        if hr < 0:
            raise NonPrisEnCharge("Aucun micro trouvé." if self.flux == _ENTREE else "Aucune sortie audio trouvée.")
        self.objets.append(peripherique)
        volume = ctypes.c_void_p()
        _verifier(_methode(peripherique, 3, ctypes.POINTER(_GUID), wt.DWORD, ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_void_p))(
            peripherique, ctypes.byref(_GUID.depuis(_IID_IAudioEndpointVolume)), 0x17, None, ctypes.byref(volume)),
            "Son")
        self.objets.append(volume)
        return self

    def __exit__(self, *_):
        for objet in reversed(self.objets):
            _methode(objet, 2)(objet)  # Release

    @property
    def _point(self):
        return self.objets[-1]

    def lire(self) -> float:
        valeur = ctypes.c_float()
        _verifier(_methode(self._point, 9, ctypes.POINTER(ctypes.c_float))(self._point, ctypes.byref(valeur)), "Son")
        return valeur.value

    def regler(self, niveau: float) -> None:
        _verifier(_methode(self._point, 7, ctypes.c_float, ctypes.c_void_p)(
            self._point, ctypes.c_float(max(0.0, min(1.0, niveau))), None), "Son")

    def muet(self) -> bool:
        valeur = wt.BOOL()
        _verifier(_methode(self._point, 15, ctypes.POINTER(wt.BOOL))(self._point, ctypes.byref(valeur)), "Son")
        return bool(valeur.value)

    def couper(self, muet: bool) -> None:
        _verifier(_methode(self._point, 14, wt.BOOL, ctypes.c_void_p)(self._point, bool(muet), None), "Son")


# --- Réglages sans API publique : objets COM de Windows et magasin de réglages ----------------

def _objet_com(clsid: str, iid: str, quoi: str) -> ctypes.c_void_p:
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 0)  # déjà initialisé dans ce fil : sans effet
    objet = ctypes.c_void_p()
    _verifier(ole32.CoCreateInstance(ctypes.byref(_GUID.depuis(clsid)), None, 4,  # CLSCTX_LOCAL_SERVER
                                     ctypes.byref(_GUID.depuis(iid)), ctypes.byref(objet)), quoi)
    return objet


def _liberer(objet: ctypes.c_void_p) -> None:
    _methode(objet, 2)(objet)  # Release


# « Ne pas déranger » de Windows 11 = profil « Priorité uniquement » des heures calmes
_CLSID_HEURES_CALMES = "f53321fa-34f8-4b7f-b9a3-361877cb94cf"
_IID_HEURES_CALMES = "6bff4732-81ec-4ffb-ae67-b6c1bc29631f"  # IQuietHoursSettings
PROFIL_LIBRE = "Microsoft.QuietHoursProfile.Unrestricted"
PROFIL_NE_PAS_DERANGER = "Microsoft.QuietHoursProfile.PriorityOnly"

# Mode avion : état global des radios (vrai = radios allumées, donc mode avion coupé)
_CLSID_RADIOS = "581333f6-28db-41be-bc7a-ff201f12f3f6"
_IID_RADIOS = "db3afbfb-08e6-46c6-aa70-bf9a34c30ab7"  # IRadioManager

# Éclairage nocturne : enregistrement binaire du magasin de réglages (« CloudStore »). Windows le relit dès
# qu'il change. Octet 18 : longueur de la suite ; « 10 00 » juste après le second en-tête « CB 01 00 » = activé.
_MAGASIN = r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current"
_ETAT_NOCTURNE = "windows.data.bluelightreduction.bluelightreductionstate"


def _varint(n: int) -> bytes:
    sortie = bytearray()
    while True:
        octet, n = n & 0x7F, n >> 7
        if n:
            sortie.append(octet | 0x80)
        else:
            sortie.append(octet)
            return bytes(sortie)


def eclairage_nocturne_actif(donnees: bytes) -> bool:
    return donnees[23:25] == b"\x10\x00"


def eclairage_nocturne_change(donnees: bytes, actif: bool, horodatage: int) -> bytes:
    """Le même enregistrement, éclairage nocturne activé ou non, daté de maintenant (sinon ignoré)."""
    d = bytearray(donnees)
    date = _varint(horodatage)
    if (d[:4] != b"CB\x01\x00" or len(d) < 25 or d[9] != 0x06 or d[15] != 0x2A or d[19:23] != b"CB\x01\x00"
            or len(date) != 5):
        raise NonPrisEnCharge("Éclairage nocturne : format inconnu dans cette version de Windows.")
    d[10:15] = date
    if actif and not eclairage_nocturne_actif(d):
        d[23:23] = b"\x10\x00"
        d[18] += 2
    elif not actif and eclairage_nocturne_actif(d):
        del d[23:25]
        d[18] -= 2
    return bytes(d)


def _cles_eclairage_nocturne() -> list[str]:
    """La clé générale et, sur les Windows 11 récents, une clé par écran (« …perdevice »)."""
    cles = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _MAGASIN) as magasin:
            i = 0
            while True:
                try:
                    nom = winreg.EnumKey(magasin, i)
                except OSError:
                    break
                i += 1
                if nom.endswith("$" + _ETAT_NOCTURNE) or nom.endswith("$" + _ETAT_NOCTURNE + "perdevice"):
                    sous_cle = nom.split("$", 1)[1]
                    cles.append(f"{_MAGASIN}\\{nom}\\{sous_cle}")
    except OSError:
        pass
    return sorted(cles, key=lambda c: c.endswith("perdevice"))  # la générale d'abord


# --- Navigateur : adresse de l'onglet affiché (UI Automation) et frappe au clavier ------------

NAVIGATEURS = re.compile(r"firefox|librewolf|waterfox|floorp|zen|chrome|chromium|brave|vivaldi|opera|msedge|thorium",
                         re.IGNORECASE)

# Le document web visible (les onglets cachés sont « hors écran ») donne l'adresse complète de la page
_SCRIPT_ADRESSE = r"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$A = [Windows.Automation.AutomationElement]
$fenetre = $A::FromHandle([IntPtr][int64]$env:DECLIC_FENETRE)
$condition = New-Object Windows.Automation.PropertyCondition($A::ControlTypeProperty, [Windows.Automation.ControlType]::Document)
foreach ($document in $fenetre.FindAll([Windows.Automation.TreeScope]::Descendants, $condition)) {
  if ($document.Current.IsOffscreen) { continue }
  try { $document.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern).Current.Value } catch { }
  break
}
"""


def sans_requete(adresse: str | None) -> str | None:
    """« https://claude.ai/new?q=… » → « https://claude.ai/new » : la requête peut être retirée par le site."""
    import urllib.parse

    if not adresse:
        return None
    m = urllib.parse.urlsplit(adresse.strip())
    if not m.scheme or not m.hostname:
        return None
    return f"{m.scheme}://{m.hostname}{m.path or '/'}".lower()


def _user32():
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.GetForegroundWindow.restype = wt.HWND
    u.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    u.GetWindowThreadProcessId.restype = wt.DWORD
    u.SendInput.argtypes = [wt.UINT, ctypes.c_void_p, ctypes.c_int]
    u.SendInput.restype = wt.UINT
    u.GetTopWindow.argtypes = [wt.HWND]
    u.GetTopWindow.restype = wt.HWND
    u.GetWindow.argtypes = [wt.HWND, wt.UINT]
    u.GetWindow.restype = wt.HWND
    u.IsWindowVisible.argtypes = [wt.HWND]
    u.GetWindowTextLengthW.argtypes = [wt.HWND]
    return u


def _premier_plan() -> tuple[int, int]:
    """(fenêtre principale, processus) au premier plan. Un navigateur donne parfois la main à une petite
    fenêtre à lui (menu, liste déroulante, fenêtre cachée) : on remonte alors à sa fenêtre principale."""
    u = _user32()
    u.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    u.GetAncestor.restype = wt.HWND
    fenetre = u.GetForegroundWindow() or 0
    pid = wt.DWORD()
    if not fenetre:
        return 0, 0
    u.GetWindowThreadProcessId(fenetre, ctypes.byref(pid))
    fenetre = u.GetAncestor(fenetre, 3) or fenetre  # GA_ROOTOWNER
    if not u.IsWindowVisible(fenetre) or u.GetWindowTextLengthW(fenetre) == 0:
        fenetre = _fenetre_du_processus(pid.value) or fenetre
    return int(fenetre), pid.value


def _nom_processus(pid: int) -> str:
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    k.OpenProcess.restype = wt.HANDLE
    k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    k.CloseHandle.argtypes = [wt.HANDLE]
    poignee = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not poignee:
        return ""
    try:
        tampon = ctypes.create_unicode_buffer(1024)
        taille = wt.DWORD(len(tampon))
        if not k.QueryFullProcessImageNameW(poignee, 0, tampon, ctypes.byref(taille)):
            return ""
        return os.path.basename(tampon.value)
    finally:
        k.CloseHandle(poignee)


def _fenetre_du_processus(pid: int) -> int:
    """La fenêtre principale de ce processus la plus haute à l'écran (la dernière utilisée)."""
    u = _user32()
    GW_HWNDNEXT, GW_OWNER = 2, 4
    fenetre = u.GetTopWindow(None)
    while fenetre:
        p = wt.DWORD()
        u.GetWindowThreadProcessId(fenetre, ctypes.byref(p))
        if (p.value == pid and u.IsWindowVisible(fenetre) and not u.GetWindow(fenetre, GW_OWNER)
                and u.GetWindowTextLengthW(fenetre) > 0):
            return int(fenetre)
        fenetre = u.GetWindow(fenetre, GW_HWNDNEXT)
    return 0


def _adresse_fenetre(fenetre: int) -> str | None:
    if not fenetre:
        return None
    try:
        sortie = _powershell(_SCRIPT_ADRESSE, timeout=10, env={"DECLIC_FENETRE": str(fenetre)})
    except (NonPrisEnCharge, subprocess.TimeoutExpired):
        return None
    lignes = [ligne.strip() for ligne in sortie.splitlines() if ligne.strip()]
    return lignes[0] if lignes else None


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _ENTREE_U(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _ENTREE_U)]


_VK_TAB, _VK_ENTREE = 0x09, 0x0D
_PAUSE_TOUCHE_S = 0.012


class _Clavier:
    """Frappe dans une fenêtre précise : s'arrête net si une autre fenêtre passe au premier plan."""

    def __init__(self, fenetre: int):
        self.fenetre = fenetre
        self.u = _user32()

    def _envoyer(self, entrees: list[_KEYBDINPUT]) -> None:
        if _premier_plan()[0] != self.fenetre:
            raise NonPrisEnCharge("la fenêtre a changé pendant la saisie : arrêt immédiat")
        tableau = (_INPUT * len(entrees))()
        for i, ki in enumerate(entrees):
            tableau[i].type = 1  # INPUT_KEYBOARD
            tableau[i].ki = ki
        self.u.SendInput(len(entrees), tableau, ctypes.sizeof(_INPUT))
        time.sleep(_PAUSE_TOUCHE_S)

    def touche(self, vk: int) -> None:
        self._envoyer([_KEYBDINPUT(vk, 0, 0, 0, 0), _KEYBDINPUT(vk, 0, 0x0002, 0, 0)])

    def taper(self, texte: str) -> None:
        unites = texte.encode("utf-16-le")
        for i in range(0, len(unites), 2):
            code = int.from_bytes(unites[i:i + 2], "little")
            # KEYEVENTF_UNICODE : le caractère lui-même, quelle que soit la disposition du clavier
            self._envoyer([_KEYBDINPUT(0, code, 0x0004, 0, 0), _KEYBDINPUT(0, code, 0x0004 | 0x0002, 0, 0)])


# --- Radios (Wi-Fi, Bluetooth) via l'API WinRT, depuis PowerShell ---------------------------

_SCRIPT_RADIO = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Attendre($operation, $type) {
  $tache = $asTask.MakeGenericMethod($type).Invoke($null, @($operation)); $tache.Wait(-1) | Out-Null; $tache.Result }
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
Attendre ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Attendre ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$radio = $radios | Where-Object { $_.Kind -eq $env:DECLIC_RADIO } | Select-Object -First 1
if (-not $radio) { throw "absent" }
if ($env:DECLIC_LIRE -eq '1') { $radio.State; return }
$nouveau = if ($radio.State -eq 'On') { 'Off' } else { 'On' }
$statut = Attendre ($radio.SetStateAsync($nouveau)) ([Windows.Devices.Radios.RadioAccessStatus])
if ($statut -ne 'Allowed') { throw "refuse:$statut" }
$nouveau
"""

# Notification Windows au nom de PowerShell (identifiant d'application connu de Windows)
_SCRIPT_NOTIFICATION = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$modele = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textes = $modele.GetElementsByTagName('text')
$textes.Item(0).AppendChild($modele.CreateTextNode($env:DECLIC_TITRE)) | Out-Null
$textes.Item(1).AppendChild($modele.CreateTextNode($env:DECLIC_MESSAGE)) | Out-Null
$notification = [Windows.UI.Notifications.ToastNotification]::new($modele)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show($notification)
"""

_SCRIPT_APPLIS = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"

# Logos des applications du Microsoft Store, lus dans leur manifeste (AppxManifest.xml)
_SCRIPT_LOGOS_STORE = r"""
$liste = foreach ($p in Get-AppxPackage) {
  $manifeste = Join-Path $p.InstallLocation 'AppxManifest.xml'
  if (-not (Test-Path -LiteralPath $manifeste)) { continue }
  try { [xml]$x = Get-Content -LiteralPath $manifeste -Raw } catch { continue }
  foreach ($a in @($x.Package.Applications.Application)) {
    if (-not $a) { continue }
    $ve = $a.VisualElements
    $logo = if ($ve.Square44x44Logo) { $ve.Square44x44Logo } elseif ($ve.Square150x150Logo) { $ve.Square150x150Logo } else { $x.Package.Properties.Logo }
    if ($logo) { [pscustomobject]@{ aumid = "$($p.PackageFamilyName)!$($a.Id)"; dossier = $p.InstallLocation; logo = $logo } }
  }
}
@($liste) | ConvertTo-Json -Compress
"""

# Dossiers connus de Windows, tels qu'ils apparaissent dans les identifiants du menu Démarrer
_DOSSIERS_CONNUS = {
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}": r"%WINDIR%\System32",
    "{F38BF404-1D43-42F2-9305-67DE0B28FC23}": r"%WINDIR%",
    "{6D809377-6AF0-444B-8957-A3773F02200E}": r"%ProgramFiles%",
    "{7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E}": r"%ProgramFiles(x86)%",
    "{D65231B0-B2F1-4857-A4CE-A8E7C6EA7D27}": r"%WINDIR%\SysWOW64",
}

# Variantes d'un logo du Store, de la plus adaptée à la barre (fond sombre, petite taille) à la moins adaptée
_VARIANTES_LOGO = ("targetsize-48_altform-unplated", "targetsize-48", "targetsize-32_altform-unplated", "targetsize-32",
                   "targetsize-64_altform-unplated", "targetsize-64", "targetsize-256_altform-unplated", "scale-200",
                   "scale-150", "scale-125", "scale-100", "scale-400")


def meilleur_logo(dossier: str, logo: str) -> str:
    """Fichier réel d'un logo du Store : « Assets\\Logo.png » existe sous forme « Logo.targetsize-48.png »…"""
    relatif = Path(logo.replace("\\", "/"))
    base = Path(dossier) / relatif.parent
    if not base.is_dir():
        return ""
    candidats = {p.name.casefold(): p for p in base.glob(f"{relatif.stem}*{relatif.suffix}")}
    for variante in _VARIANTES_LOGO:
        p = candidats.get(f"{relatif.stem}.{variante}{relatif.suffix}".casefold())
        if p:
            return str(p)
    exact = base / relatif.name
    if exact.is_file():
        return str(exact)
    propres = [p for nom, p in sorted(candidats.items()) if "contrast" not in nom and "lightunplated" not in nom]
    return str(propres[0]) if propres else ""


def chemin_connu(app_id: str) -> str:
    """« {1AC14E77-…}\\osk.exe » → « C:\\Windows\\System32\\osk.exe » ; chemin absolu inchangé ; sinon vide."""
    for guid, dossier in _DOSSIERS_CONNUS.items():
        if app_id.upper().startswith(guid):
            return os.path.expandvars(dossier) + app_id[len(guid):]
    return app_id if re.match(r"^[a-zA-Z]:\\", app_id) else ""


def profils_wifi(sortie_netsh: str) -> list[str]:
    """Noms des Wi-Fi enregistrés, lus dans la sortie de « netsh wlan show profiles ».
    « Profil Tous les utilisateurs : Maison » : la langue des libellés dépend de Windows,
    et le français met une espace insécable avant les deux-points."""
    noms = []
    dans_liste = False
    for ligne in sortie_netsh.splitlines():
        if ligne.strip().startswith("---"):
            dans_liste = True
            continue
        m = re.match(r"^\s{2,}\S.*?\s*:\s*(.+)$", ligne)
        if dans_liste and m:
            noms.append(m.group(1).strip())
    return sorted(set(noms), key=str.casefold)


# --------------------------------------------------------------------------------------------
# Index des fichiers personnels
# --------------------------------------------------------------------------------------------

class _IndexFichiers:
    """Noms des fichiers des dossiers personnels, gardés en mémoire et rafraîchis en arrière-plan.
    Une recherche ne touche pas au disque ; le premier remplissage prend quelques secondes."""

    def __init__(self, racines: list[Path]):
        self.racines = racines
        self.entrees: list[tuple[str, str, bool, float]] = []  # (nom sans accents, chemin, dossier, modifié)
        self.date = 0.0
        self.verrou = threading.Lock()
        self.en_cours = threading.Event()
        self.fil: threading.Thread | None = None

    def _parcourir(self) -> list[tuple[str, str, bool, float]]:
        entrees = []
        pile = [r for r in self.racines if r.is_dir()]
        vus = set()
        while pile and len(entrees) < _MAX_FICHIERS:
            dossier = pile.pop()
            try:
                reel = os.path.realpath(dossier).casefold()
                if reel in vus:
                    continue
                vus.add(reel)
                with os.scandir(dossier) as contenu:
                    for e in contenu:
                        nom = e.name
                        if nom.startswith((".", "~$")) or nom.casefold() in _EXCLUS:
                            continue
                        try:
                            attributs = e.stat(follow_symlinks=False)
                        except OSError:
                            continue
                        if getattr(attributs, "st_file_attributes", 0) & 0x2:  # caché
                            continue
                        est_dossier = e.is_dir(follow_symlinks=False)
                        entrees.append((_sans_accents(nom), e.path, est_dossier, attributs.st_mtime))
                        if est_dossier:
                            pile.append(Path(e.path))
            except OSError:
                continue
        return entrees

    def _remplir(self) -> None:
        try:
            debut = time.monotonic()
            entrees = self._parcourir()
            with self.verrou:
                self.entrees, self.date = entrees, time.monotonic()
            log.info("Index des fichiers : %d éléments en %.1f s", len(entrees), time.monotonic() - debut)
        finally:
            self.en_cours.clear()

    def rafraichir(self, attendre: bool) -> None:
        if not self.en_cours.is_set():
            self.en_cours.set()
            self.fil = threading.Thread(target=self._remplir, daemon=True, name="index des fichiers")
            self.fil.start()
        if attendre and self.fil is not None:
            self.fil.join(20)

    def chercher(self, mots: list[str], limite: int) -> list[tuple[str, str, bool, float]]:
        if not self.date:
            self.rafraichir(attendre=True)
        elif time.monotonic() - self.date > _INTERVALLE_INDEX:
            self.rafraichir(attendre=False)
        with self.verrou:
            trouves = [e for e in self.entrees if all(m in e[0] for m in mots)]
        trouves.sort(key=lambda e: e[3], reverse=True)
        return trouves[:limite]


def _dossiers_personnels() -> list[Path]:
    maison = Path.home()
    racines = [maison / nom for nom in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")]
    # Dossiers réels (redirigés vers OneDrive par exemple), lus dans le registre de l'explorateur
    cle = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    for nom in ("Desktop", "Personal", "{374DE290-123F-4565-9164-39C4925E467B}", "My Pictures", "My Music", "My Video"):
        valeur = _lire_registre(cle, nom)
        if valeur:
            racines.append(Path(os.path.expandvars(valeur)))
    racines += [p for p in maison.glob("OneDrive*") if p.is_dir()]
    uniques, vus = [], set()
    for r in racines:
        cle_r = str(r).casefold()
        if cle_r not in vus:
            vus.add(cle_r)
            uniques.append(r)
    return uniques


# --------------------------------------------------------------------------------------------
# Plateforme
# --------------------------------------------------------------------------------------------

class PlateformeWindows(Plateforme):
    nom = "Windows"

    def __init__(self):
        self._applis: list[Application] = []
        self._date_applis = 0.0
        self._index = _IndexFichiers(_dossiers_personnels())
        # Les logos du Store se lisent en 1 à 2 secondes : en arrière-plan dès le démarrage
        self._logos_store: dict[str, str] = {}
        self._logos_prets = threading.Event()
        threading.Thread(target=self._lire_logos_store, daemon=True, name="logos du Store").start()

    def _lire_logos_store(self) -> None:
        try:
            donnees = json.loads(_powershell(_SCRIPT_LOGOS_STORE, timeout=60) or "[]")
            logos = {}
            for d in donnees if isinstance(donnees, list) else [donnees]:
                chemin = meilleur_logo(d.get("dossier") or "", d.get("logo") or "")
                if chemin:
                    logos[(d.get("aumid") or "").casefold()] = chemin
            self._logos_store = logos
        except (NonPrisEnCharge, ValueError, subprocess.TimeoutExpired, OSError):
            log.warning("Logos des applications du Store indisponibles")
        finally:
            self._logos_prets.set()

    # --- Applications et ouverture -------------------------------------------------
    @staticmethod
    def _dossiers_menu() -> list[Path]:
        return [
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]

    @classmethod
    def _raccourcis(cls) -> dict[str, Path]:
        """Raccourcis du menu Démarrer, par nom (pour retrouver l'icône d'une application).
        La barre suit le raccourci jusqu'au programme pour afficher son vrai logo."""
        raccourcis = {}
        for dossier in cls._dossiers_menu():
            if dossier.is_dir():
                for lnk in dossier.rglob("*.lnk"):
                    raccourcis.setdefault(lnk.stem.casefold(), lnk)
        return raccourcis

    @classmethod
    def _icones_internet(cls) -> dict[str, str]:
        """Icônes des raccourcis Internet du menu Démarrer (jeux Steam, Epic…) : ligne « IconFile= »."""
        icones = {}
        for dossier in cls._dossiers_menu():
            if not dossier.is_dir():
                continue
            for url in dossier.rglob("*.url"):
                try:
                    for ligne in url.read_text(encoding="utf-8", errors="replace").splitlines():
                        if ligne.casefold().startswith("iconfile="):
                            chemin = os.path.expandvars(ligne.split("=", 1)[1].strip())
                            if os.path.isfile(chemin):
                                icones.setdefault(url.stem.casefold(), chemin)
                            break
                except OSError:
                    continue
        return icones

    def _icone(self, nom: str, app_id: str, raccourcis: dict[str, Path], internet: dict[str, str]) -> str:
        """Fichier d'où tirer le logo : raccourci, programme, icône d'un jeu, logo du Store."""
        cle = nom.casefold()
        if cle in raccourcis:
            return str(raccourcis[cle])
        if cle in internet:
            return internet[cle]
        if "!" in app_id:  # application du Store : « Famille!Appli »
            return self._logos_store.get(app_id.casefold(), "")
        chemin = chemin_connu(app_id)
        return chemin if chemin and os.path.isfile(chemin) else ""

    def lister_applications(self) -> list[Application]:
        if self._applis and time.monotonic() - self._date_applis < _DUREE_CACHE_APPLIS:
            return self._applis
        raccourcis = self._raccourcis()
        internet = self._icones_internet()
        self._logos_prets.wait(5)  # la première liste attend les logos du Store, au plus 5 secondes
        applis: dict[str, Application] = {}
        try:
            donnees = json.loads(_powershell(_SCRIPT_APPLIS) or "[]")
            for a in donnees if isinstance(donnees, list) else [donnees]:
                nom, app_id = a.get("Name") or "", a.get("AppID") or ""
                if not nom or not app_id:
                    continue
                applis.setdefault(nom.casefold(), Application(
                    id=f"shell:AppsFolder\\{app_id}", nom=nom, icone=self._icone(nom, app_id, raccourcis, internet)))
        except (NonPrisEnCharge, ValueError, subprocess.TimeoutExpired):
            log.warning("Get-StartApps indisponible : seuls les raccourcis du menu Démarrer sont listés")
        for nom, lnk in raccourcis.items():
            applis.setdefault(nom, Application(id=str(lnk), nom=lnk.stem, icone=str(lnk)))
        self._applis = sorted(applis.values(), key=lambda a: a.nom.casefold())
        self._date_applis = time.monotonic()
        return self._applis

    def lancer_application(self, app_id: str) -> None:
        if app_id.startswith("shell:AppsFolder\\"):
            subprocess.Popen(["explorer.exe", app_id], creationflags=_SANS_FENETRE)
        else:
            os.startfile(app_id)  # type: ignore[attr-defined]

    def ouvrir(self, cible: str) -> None:
        os.startfile(os.path.expanduser(cible) if "://" not in cible else cible)  # type: ignore[attr-defined]

    # --- Presse-papiers et notifications -------------------------------------------
    def copier_texte(self, texte: str) -> None:
        CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        k32.GlobalAlloc.restype = ctypes.c_void_p
        k32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        k32.GlobalFree.argtypes = [ctypes.c_void_p]
        u32.SetClipboardData.restype = ctypes.c_void_p
        u32.SetClipboardData.argtypes = [wt.UINT, ctypes.c_void_p]
        donnees = texte.encode("utf-16-le") + b"\x00\x00"
        for _ in range(20):  # le presse-papiers peut être occupé un instant par une autre application
            if u32.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            raise NonPrisEnCharge("Le presse-papiers est occupé par une autre application.")
        try:
            u32.EmptyClipboard()
            memoire = k32.GlobalAlloc(GMEM_MOVEABLE, len(donnees))
            pointeur = k32.GlobalLock(memoire)
            ctypes.memmove(pointeur, donnees, len(donnees))
            k32.GlobalUnlock(memoire)
            if not u32.SetClipboardData(CF_UNICODETEXT, memoire):
                k32.GlobalFree(memoire)
                raise NonPrisEnCharge("Impossible d'écrire dans le presse-papiers.")
        finally:
            u32.CloseClipboard()

    # --- Historique du presse-papiers ----------------------------------------------
    @staticmethod
    def _lire_presse_papiers() -> str | None:
        """Texte du presse-papiers, ou None s'il n'y en a pas ou s'il ne faut pas le garder : les gestionnaires
        de mots de passe (KeePass, Bitwarden, 1Password…) le signalent par des formats convenus."""
        CF_UNICODETEXT = 13
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        u32.GetClipboardData.restype = ctypes.c_void_p
        u32.RegisterClipboardFormatW.restype = wt.UINT
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        exclure = [u32.RegisterClipboardFormatW(n) for n in ("ExcludeClipboardContentFromMonitorProcessing",
                                                               "Clipboard Viewer Ignore")]
        historique = u32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
        if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        for _ in range(10):
            if u32.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            return None
        try:
            if any(u32.IsClipboardFormatAvailable(f) for f in exclure):
                return None
            if u32.IsClipboardFormatAvailable(historique):
                valeur = u32.GetClipboardData(historique)
                pointeur = k32.GlobalLock(valeur) if valeur else None
                if pointeur:
                    refuse = ctypes.c_uint32.from_address(pointeur).value == 0
                    k32.GlobalUnlock(valeur)
                    if refuse:
                        return None
            donnees = u32.GetClipboardData(CF_UNICODETEXT)
            pointeur = k32.GlobalLock(donnees) if donnees else None
            if not pointeur:
                return None
            try:
                return ctypes.wstring_at(pointeur)
            finally:
                k32.GlobalUnlock(donnees)
        finally:
            u32.CloseClipboard()

    def surveiller_presse_papiers(self, rappel) -> None:
        """Relève le presse-papiers à chaque changement (numéro de séquence de Windows, vérifié 2 fois par seconde)."""
        sequence = ctypes.windll.user32.GetClipboardSequenceNumber

        def boucle():
            dernier = sequence()
            while True:
                time.sleep(0.5)
                actuel = sequence()
                if actuel == dernier:
                    continue
                dernier = actuel
                try:
                    contenu = self._lire_presse_papiers()
                    if contenu:
                        rappel(contenu)
                except Exception:
                    log.exception("Lecture du presse-papiers impossible")

        threading.Thread(target=boucle, daemon=True, name="presse-papiers").start()

    def coller_texte(self, texte: str) -> None:
        """Copie, puis Ctrl+V dans l'application qui reprend la main quand la barre se ferme."""
        self.copier_texte(texte)

        def coller():
            limite = time.monotonic() + 2
            while time.monotonic() < limite:  # attendre que la barre de Déclic ait rendu la main
                fenetre, pid = _premier_plan()
                if fenetre and not re.match(r"declic|electron", _nom_processus(pid), re.IGNORECASE):
                    break
                time.sleep(0.05)
            else:
                return
            time.sleep(0.12)
            VK_CONTROL, VK_V, HAUT = 0x11, 0x56, 0x0002
            entrees = [_KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0), _KEYBDINPUT(VK_V, 0, 0, 0, 0),
                       _KEYBDINPUT(VK_V, 0, HAUT, 0, 0), _KEYBDINPUT(VK_CONTROL, 0, HAUT, 0, 0)]
            tableau = (_INPUT * len(entrees))()
            for i, ki in enumerate(entrees):
                tableau[i].type = 1
                tableau[i].ki = ki
            _user32().SendInput(len(entrees), tableau, ctypes.sizeof(_INPUT))

        threading.Thread(target=coller, daemon=True, name="coller").start()

    def notifier(self, titre: str, message: str = "") -> None:
        # Texte passé par l'environnement : jamais interprété comme du code PowerShell
        _powershell(_SCRIPT_NOTIFICATION, env={"DECLIC_TITRE": f"Déclic — {titre}", "DECLIC_MESSAGE": message or " "})

    # --- Session et alimentation ---------------------------------------------------
    def verrouiller(self) -> None:
        if not ctypes.windll.user32.LockWorkStation():
            raise NonPrisEnCharge("Windows a refusé de verrouiller la session.")

    def veille(self) -> None:
        # SetSuspendState(hibernation, forcer, désactiver le réveil) : veille simple
        if not ctypes.windll.powrprof.SetSuspendState(False, False, False):
            raise NonPrisEnCharge("Windows a refusé la mise en veille.")

    def redemarrer(self) -> None:
        _executer(["shutdown", "/r", "/t", "0"])

    def eteindre(self) -> None:
        _executer(["shutdown", "/s", "/t", "0"])

    def deconnecter(self) -> None:
        _executer(["shutdown", "/l"])

    def definir_profil_energie(self, profil: str) -> None:
        if profil not in _MODES_ENERGIE:
            raise ValueError(f"Profil inconnu : {profil}")
        try:
            fonction = ctypes.windll.powrprof.PowerSetActiveOverlayScheme
            if fonction(ctypes.byref(_GUID.depuis(_MODES_ENERGIE[profil]))) == 0:
                return
        except AttributeError:
            pass  # Windows 10 ancien : pas de mode d'alimentation
        fini = _executer(["powercfg", "/setactive", _SCHEMAS_ENERGIE[profil]])
        if fini.returncode != 0:
            raise NonPrisEnCharge("Ce mode d'alimentation n'existe pas sur ce PC.")

    def profil_energie_actuel(self) -> str | None:
        """Mode d'alimentation actif (pour les tests et l'affichage)."""
        try:
            guid = _GUID()
            if ctypes.windll.powrprof.PowerGetEffectiveOverlayScheme(ctypes.byref(guid)) != 0:
                return None
        except AttributeError:
            return None
        texte = str(uuid.UUID(bytes_le=bytes(guid)))
        return next((p for p, g in _MODES_ENERGIE.items() if g == texte), texte)

    # --- Fichiers ------------------------------------------------------------------
    def vider_corbeille(self) -> None:
        SHERB = 0x1 | 0x2 | 0x4  # sans confirmation, sans barre de progression, sans son
        hr = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, SHERB)
        if hr < 0 and (hr & 0xFFFFFFFF) != 0x8000FFFF:  # 0x8000FFFF : corbeille déjà vide
            raise NonPrisEnCharge(f"Impossible de vider la corbeille (0x{hr & 0xFFFFFFFF:08x}).")

    def ouvrir_corbeille(self) -> None:
        subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"], creationflags=_SANS_FENETRE)

    def chercher_fichiers(self, mots: list[str], limite: int = 60) -> list[Fichier]:
        mots = [m for m in mots if m][:6]
        if not mots:
            return []
        fichiers = []
        for _nom, chemin, dossier, modifie in self._index.chercher(mots, limite * 2):
            if not os.path.lexists(chemin):
                continue  # supprimé depuis le dernier passage de l'index
            fichiers.append(Fichier(chemin=chemin, nom=os.path.basename(chemin), dossier=dossier, modifie=modifie,
                                    icone="folder-symbolic" if dossier else "text-x-generic-symbolic"))
            if len(fichiers) >= limite:
                break
        return fichiers

    def afficher_dans_dossier(self, chemin: str) -> None:
        subprocess.Popen(["explorer.exe", f"/select,{os.path.normpath(chemin)}"], creationflags=_SANS_FENETRE)

    # --- Bascules ------------------------------------------------------------------
    _THEME = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    _EXPLORATEUR = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"

    def basculer_theme_sombre(self) -> bool:
        sombre = _lire_registre(self._THEME, "AppsUseLightTheme", 1) != 0
        for nom in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            _ecrire_registre(self._THEME, nom, 0 if sombre else 1)
        _diffuser_changement("ImmersiveColorSet")
        return sombre

    def basculer_fichiers_caches(self) -> bool:
        visibles = _lire_registre(self._EXPLORATEUR, "Hidden", 2) != 1
        _ecrire_registre(self._EXPLORATEUR, "Hidden", 1 if visibles else 2)
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED : l'explorateur se rafraîchit
        return visibles

    def etat_radio(self, genre: str) -> bool:
        """État d'une radio (« WiFi » ou « Bluetooth ») sans la changer."""
        return _powershell(_SCRIPT_RADIO, env={"DECLIC_RADIO": genre, "DECLIC_LIRE": "1"}, timeout=30).splitlines()[-1] == "On"

    def _basculer_radio(self, genre: str) -> bool:
        try:
            etat = _powershell(_SCRIPT_RADIO, env={"DECLIC_RADIO": genre, "DECLIC_LIRE": "0"}, timeout=30)
        except NonPrisEnCharge as exc:
            if "absent" in str(exc):
                raise NonPrisEnCharge(f"Aucun {'Wi-Fi' if genre == 'WiFi' else 'Bluetooth'} sur ce PC.") from exc
            raise
        return etat.strip().splitlines()[-1] == "On"

    def basculer_wifi(self) -> bool:
        return self._basculer_radio("WiFi")

    def basculer_bluetooth(self) -> bool:
        return self._basculer_radio("Bluetooth")

    @staticmethod
    def _mode_avion(nouveau: bool | None = None) -> bool:
        """Mode avion actuel ; avec « nouveau », le change d'abord. Renvoie l'état final."""
        radios = _objet_com(_CLSID_RADIOS, _IID_RADIOS, "Mode avion")
        try:
            if nouveau is not None:  # SetSystemRadioState : 1 = radios allumées, donc mode avion coupé
                _verifier(_methode(radios, 6, ctypes.c_int)(radios, 0 if nouveau else 1), "Mode avion")
                return nouveau
            allumees, inutile, raison = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
            P = ctypes.POINTER(ctypes.c_int)
            _verifier(_methode(radios, 5, P, P, P)(radios, ctypes.byref(allumees), ctypes.byref(inutile),
                                                   ctypes.byref(raison)), "Mode avion")
            return not allumees.value
        finally:
            _liberer(radios)

    def basculer_mode_avion(self) -> bool:
        return self._mode_avion(not self._mode_avion())

    @staticmethod
    def _ne_pas_deranger(nouveau: bool | None = None) -> bool:
        """« Ne pas déranger » actuel ; avec « nouveau », le change d'abord. Renvoie l'état final."""
        heures = _objet_com(_CLSID_HEURES_CALMES, _IID_HEURES_CALMES, "Ne pas déranger")
        try:
            if nouveau is not None:
                _verifier(_methode(heures, 4, wt.LPCWSTR)(heures, PROFIL_NE_PAS_DERANGER if nouveau else PROFIL_LIBRE),
                          "Ne pas déranger")
                return nouveau
            profil = ctypes.c_void_p()
            _verifier(_methode(heures, 3, ctypes.POINTER(ctypes.c_void_p))(heures, ctypes.byref(profil)),
                      "Ne pas déranger")
            actuel = ctypes.wstring_at(profil.value) if profil.value else PROFIL_LIBRE
            ctypes.windll.ole32.CoTaskMemFree(profil)
            return actuel != PROFIL_LIBRE
        finally:
            _liberer(heures)

    def basculer_ne_pas_deranger(self) -> bool:
        return self._ne_pas_deranger(not self._ne_pas_deranger())

    def etat_bascule(self, nom: str) -> bool:
        if nom == "ne_pas_deranger":
            return self._ne_pas_deranger()
        if nom == "mode_avion":
            return self._mode_avion()
        if nom == "theme_sombre":
            return _lire_registre(self._THEME, "AppsUseLightTheme", 1) == 0
        if nom == "fichiers_caches":
            return _lire_registre(self._EXPLORATEUR, "Hidden", 2) == 1
        if nom in ("wifi", "bluetooth"):
            return self.etat_radio("WiFi" if nom == "wifi" else "Bluetooth")
        if nom == "eclairage_nocturne":
            cles = _cles_eclairage_nocturne()
            if not cles:
                return False
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cles[0]) as k:
                return eclairage_nocturne_actif(bytes(winreg.QueryValueEx(k, "Data")[0]))
        raise NonPrisEnCharge(f"État inconnu : {nom}")

    # --- Programmes ouverts ----------------------------------------------------------
    def processus(self) -> dict[str, str]:
        """Programmes de la session de l'utilisateur (les services de Windows sont ignorés)."""
        psapi, k = ctypes.WinDLL("psapi"), ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k.OpenProcess.restype = wt.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        k.CloseHandle.argtypes = [wt.HANDLE]
        k.ProcessIdToSessionId.argtypes = [wt.DWORD, ctypes.POINTER(wt.DWORD)]
        ids = (wt.DWORD * 4096)()
        taille = wt.DWORD()
        if not psapi.EnumProcesses(ids, ctypes.sizeof(ids), ctypes.byref(taille)):
            return {}
        ma_session, session = wt.DWORD(), wt.DWORD()
        k.ProcessIdToSessionId(os.getpid(), ctypes.byref(ma_session))
        tampon = ctypes.create_unicode_buffer(1024)
        trouves: dict[str, str] = {}
        for pid in ids[:taille.value // ctypes.sizeof(wt.DWORD)]:
            if not pid or not k.ProcessIdToSessionId(pid, ctypes.byref(session)) or session.value != ma_session.value:
                continue
            poignee = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not poignee:
                continue
            try:
                longueur = wt.DWORD(len(tampon))
                if k.QueryFullProcessImageNameW(poignee, 0, tampon, ctypes.byref(longueur)):
                    chemin = tampon.value
                    trouves.setdefault(os.path.splitext(os.path.basename(chemin))[0], chemin)
            finally:
                k.CloseHandle(poignee)
        return trouves

    def fermer_application(self, nom: str) -> int:
        """Comme la croix de la fenêtre ; si le programme est encore là après 5 secondes (beaucoup se rangent
        dans la zone de notification), il est arrêté."""
        nom = os.path.splitext(nom.strip())[0]
        ouverts = [n for n in self.processus() if n.casefold() == nom.casefold()]
        if not ouverts:
            return 0
        image = f"{ouverts[0]}.exe"
        _executer(["taskkill", "/IM", image], timeout=10)
        for _ in range(10):
            time.sleep(0.5)
            if not any(n.casefold() == nom.casefold() for n in self.processus()):
                return len(ouverts)
        _executer(["taskkill", "/IM", image, "/T", "/F"], timeout=10)
        return len(ouverts)

    def basculer_eclairage_nocturne(self) -> bool:
        cles = _cles_eclairage_nocturne()
        if not cles:
            raise NonPrisEnCharge("Éclairage nocturne introuvable : ouvrez-le une fois dans Paramètres → Affichage.")
        lus = []
        for cle in cles:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cle) as k:
                lus.append((cle, bytes(winreg.QueryValueEx(k, "Data")[0])))
        actif = not eclairage_nocturne_actif(lus[0][1])
        maintenant = int(time.time())
        nouveaux = [(cle, eclairage_nocturne_change(d, actif, maintenant)) for cle, d in lus]  # tout vérifier d'abord
        for cle, d in nouveaux:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cle, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "Data", 0, winreg.REG_BINARY, d)
        return actif

    # --- Réseau --------------------------------------------------------------------
    @staticmethod
    def _netsh_wlan(*args: str) -> str:
        try:
            fini = _executer(["netsh", "wlan", *args], timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return fini.stdout if fini.returncode == 0 else ""

    def reseaux_wifi_connus(self) -> list[str]:
        return profils_wifi(self._netsh_wlan("show", "profiles"))

    def wifi_connecte(self) -> str | None:
        """Nom du Wi-Fi auquel le PC est connecté, ou None."""
        for ligne in self._netsh_wlan("show", "interfaces").splitlines():
            m = re.match(r"^\s*SSID\s*:\s*(.+)$", ligne)  # pas « BSSID »
            if m:
                return m.group(1).strip() or None
        return None

    # --- Coffre à identifiants : Gestionnaire d'identifiants de Windows --------------
    def coffre_enregistrer(self, site, attributs, mot_de_passe):
        a = _advapi32()
        valeurs = [(k, str(attributs.get(k, "")).encode("utf-8")) for k in ATTRIBUTS_COFFRE]
        trop_long = [k for k, v in valeurs if len(v) > _TAILLE_MAX_ATTRIBUT]
        if trop_long:
            raise ValueError(f"Trop long pour Windows (256 octets au plus) : {', '.join(trop_long)}")
        tampons = [(ctypes.create_unicode_buffer(f"declic-{k}"),
                    (ctypes.c_ubyte * max(1, len(v))).from_buffer_copy(v or b"\0"), len(v)) for k, v in valeurs]
        tableau = (_CREDENTIAL_ATTRIBUTE * len(tampons))()
        for i, (cle, valeur, taille) in enumerate(tampons):
            tableau[i].Keyword = ctypes.cast(cle, wt.LPWSTR)
            tableau[i].Flags = 0
            tableau[i].ValueSize = taille
            tableau[i].Value = ctypes.cast(valeur, ctypes.POINTER(ctypes.c_ubyte))
        secret = mot_de_passe.encode("utf-16-le")
        blob = (ctypes.c_ubyte * max(1, len(secret))).from_buffer_copy(secret or b"\0")
        cred = _CREDENTIAL()
        cred.Type = _CRED_TYPE_GENERIC
        cred.TargetName = f"{PREFIXE_COFFRE}{site}"
        cred.Comment = f"Déclic : {attributs.get('nom', site)}"[:255]
        cred.CredentialBlobSize = len(secret)
        cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
        cred.AttributeCount = len(tampons)
        cred.Attributes = ctypes.cast(tableau, ctypes.POINTER(_CREDENTIAL_ATTRIBUTE))
        cred.UserName = str(attributs.get("identifiant", ""))
        if not a.CredWriteW(ctypes.byref(cred), 0):
            raise NonPrisEnCharge(f"Gestionnaire d'identifiants : erreur {ctypes.get_last_error()}")

    def coffre_lister(self):
        a = _advapi32()
        nombre = wt.DWORD()
        liste = ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))()
        if not a.CredEnumerateW(f"{PREFIXE_COFFRE}*", 0, ctypes.byref(nombre), ctypes.byref(liste)):
            return []  # aucun identifiant Déclic
        try:
            sites = []
            for i in range(nombre.value):
                c = liste[i].contents
                # On ne lit que les attributs publics, jamais le mot de passe (CredentialBlob)
                infos = {"site": (c.TargetName or "")[len(PREFIXE_COFFRE):]}
                for k in range(c.AttributeCount):
                    attr = c.Attributes[k]
                    cle = (attr.Keyword or "").removeprefix("declic-")
                    if cle in ATTRIBUTS_COFFRE:
                        infos[cle] = bytes(attr.Value[:attr.ValueSize]).decode("utf-8", "replace")
                sites.append({k: infos.get(k, "") for k in ("site", *ATTRIBUTS_COFFRE)})
            return [s for s in sites if s["site"]]
        finally:
            a.CredFree(liste)

    def coffre_supprimer(self, site):
        return bool(_advapi32().CredDeleteW(f"{PREFIXE_COFFRE}{site}", _CRED_TYPE_GENERIC, 0))

    # --- Clés d'API des IA : Gestionnaire d'identifiants (« DeclicIA:… », à part des sites) ---
    def secret_enregistrer(self, nom, valeur):
        a = _advapi32()
        secret = valeur.encode("utf-16-le")
        blob = (ctypes.c_ubyte * max(1, len(secret))).from_buffer_copy(secret or b"\0")
        cred = _CREDENTIAL()
        cred.Type = _CRED_TYPE_GENERIC
        cred.TargetName = f"DeclicIA:{nom}"
        cred.Comment = "Déclic : clé d'API"
        cred.CredentialBlobSize = len(secret)
        cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        cred.Persist = _CRED_PERSIST_LOCAL_MACHINE
        cred.UserName = nom
        if not a.CredWriteW(ctypes.byref(cred), 0):
            raise NonPrisEnCharge(f"Gestionnaire d'identifiants : erreur {ctypes.get_last_error()}")

    def secret_lire(self, nom):
        a = _advapi32()
        a.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
        a.CredReadW.restype = wt.BOOL
        cred = ctypes.POINTER(_CREDENTIAL)()
        if not a.CredReadW(f"DeclicIA:{nom}", _CRED_TYPE_GENERIC, 0, ctypes.byref(cred)):
            return None
        try:
            c = cred.contents
            return bytes(c.CredentialBlob[:c.CredentialBlobSize]).decode("utf-16-le")
        finally:
            a.CredFree(cred)

    def secret_supprimer(self, nom):
        _advapi32().CredDeleteW(f"DeclicIA:{nom}", _CRED_TYPE_GENERIC, 0)

    @staticmethod
    def _coffre_lire(site: str) -> tuple[str, str]:
        """(identifiant, mot de passe) : lu seulement juste avant de le taper."""
        a = _advapi32()
        a.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
        a.CredReadW.restype = wt.BOOL
        cred = ctypes.POINTER(_CREDENTIAL)()
        if not a.CredReadW(f"{PREFIXE_COFFRE}{site}", _CRED_TYPE_GENERIC, 0, ctypes.byref(cred)):
            raise NonPrisEnCharge(f"identifiant « {site} » absent du Gestionnaire d'identifiants")
        try:
            c = cred.contents
            mot_de_passe = bytes(c.CredentialBlob[:c.CredentialBlobSize]).decode("utf-16-le")
            return c.UserName or "", mot_de_passe
        finally:
            a.CredFree(cred)

    # --- Navigateur : remplir une page de connexion, envoyer une question à une IA ---
    def adresse_page(self, pid):
        """Adresse de l'onglet affiché dans la dernière fenêtre utilisée de ce navigateur (UI Automation)."""
        pid = int(pid)
        if not NAVIGATEURS.search(_nom_processus(pid)):
            return None
        fenetre, pid_actif = _premier_plan()
        if pid_actif != pid:
            fenetre = _fenetre_du_processus(pid)  # la barre de Déclic est par-dessus
        return _adresse_fenetre(fenetre)

    @staticmethod
    def _navigateur_actif() -> int:
        fenetre, pid = _premier_plan()
        return fenetre if fenetre and NAVIGATEURS.search(_nom_processus(pid)) else 0

    def saisir_identifiant(self, site, delai_s):
        from declic.modules.identifiants import page_autorisee

        if getattr(self, "_saisie_en_cours", False):
            raise NonPrisEnCharge("une autre connexion est déjà en cours")
        enregistre = next((s for s in self.coffre_lister() if s["site"] == site), None)
        if enregistre is None:
            raise NonPrisEnCharge(f"identifiant « {site} » absent du Gestionnaire d'identifiants")
        delai = max(1, min(60, int(delai_s)))

        def verifier(fenetre: int) -> tuple[bool, str]:
            if self._navigateur_actif() != fenetre:
                return False, "aucun navigateur au premier plan"
            return page_autorisee(_adresse_fenetre(fenetre), enregistre["adresse"])

        def saisir():
            # Attendre qu'un navigateur soit au premier plan ET sur le bon site (chargement, redirections…)
            limite, raison, fenetre = time.monotonic() + delai, "aucun navigateur au premier plan", 0
            while not fenetre:
                if time.monotonic() > limite:
                    raise NonPrisEnCharge(f"{raison} : rien n'a été tapé")
                candidate = self._navigateur_actif()
                if candidate:
                    ok, raison = verifier(candidate)
                    if ok:
                        fenetre = candidate
                        break
                time.sleep(0.4)
            identifiant, mot_de_passe = self._coffre_lire(site)
            try:
                time.sleep(0.7)  # la page finit de se charger et place le curseur
                clavier = _Clavier(fenetre)
                clavier.taper(identifiant)
                clavier.touche(_VK_TAB)
                ok, raison = verifier(fenetre)
                if not ok:
                    raise NonPrisEnCharge(f"{raison} : mot de passe non tapé")
                clavier.taper(mot_de_passe)
                clavier.touche(_VK_ENTREE)
            finally:
                mot_de_passe = None

        def lancer():
            try:
                saisir()
            except Exception as exc:  # la barre est déjà fermée : on prévient par une notification
                log.warning("Connexion abandonnée : %s", exc)
                try:
                    self.notifier("Connexion abandonnée", str(exc))
                except Exception:
                    pass
            finally:
                self._saisie_en_cours = False

        self._saisie_en_cours = True
        threading.Thread(target=lancer, daemon=True, name="saisie d'un identifiant").start()

    def valider_page(self, adresse, delai_s):
        attendu = sans_requete(adresse)
        if not attendu:
            raise NonPrisEnCharge("adresse illisible")
        self._jeton_page = getattr(self, "_jeton_page", 0) + 1  # une nouvelle question remplace la précédente
        jeton = self._jeton_page
        delai = max(1, min(60, int(delai_s)))

        def sur_la_page() -> int:
            fenetre = self._navigateur_actif()
            if fenetre and sans_requete(_adresse_fenetre(fenetre)) == attendu and self._navigateur_actif() == fenetre:
                return fenetre
            return 0

        def envoyer():
            limite, fenetre = time.monotonic() + delai, 0
            while not fenetre:
                if jeton != self._jeton_page:
                    return
                if time.monotonic() > limite:
                    log.info("Question non envoyée : la page de l'IA n'est pas apparue au premier plan")
                    return
                fenetre = sur_la_page()
                if not fenetre:
                    time.sleep(0.3)
            # Laisse la zone de saisie apparaître, puis Entrée, au plus 3 fois tant que la page n'a pas changé
            # (une fois la question partie, le site change d'adresse : on s'arrête)
            for _ in range(3):
                time.sleep(1.5)
                if jeton != self._jeton_page or sur_la_page() != fenetre:
                    return
                try:
                    _Clavier(fenetre).touche(_VK_ENTREE)
                except NonPrisEnCharge:
                    return

        threading.Thread(target=envoyer, daemon=True, name="envoi d'une question").start()

    # --- Événements (déclencheurs des automatisations) -------------------------------
    @staticmethod
    def session_verrouillee() -> bool | None:
        """Vrai si la session est verrouillée (WTSSessionInfoEx), None si inconnu."""
        wtsapi = ctypes.windll.wtsapi32
        wtsapi.WTSQuerySessionInformationW.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_int,
                                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD)]
        wtsapi.WTSFreeMemory.argtypes = [ctypes.c_void_p]
        tampon = ctypes.c_void_p()
        taille = wt.DWORD()
        WTS_CURRENT_SESSION, WTSSessionInfoEx = 0xFFFFFFFF, 25
        if not wtsapi.WTSQuerySessionInformationW(None, WTS_CURRENT_SESSION, WTSSessionInfoEx,
                                                  ctypes.byref(tampon), ctypes.byref(taille)):
            return None
        try:
            # WTSINFOEXW : Level (4 octets), puis la structure alignée sur 8 octets (elle contient des
            # LARGE_INTEGER) : SessionId, SessionState, SessionFlags (0 = verrouillée, 1 = ouverte)
            drapeaux = ctypes.cast(tampon, ctypes.POINTER(ctypes.c_long))[4]
            return {0: True, 1: False}.get(drapeaux)
        finally:
            wtsapi.WTSFreeMemory(tampon)

    @staticmethod
    def sur_secteur() -> bool | None:
        class _SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", wt.DWORD), ("BatteryFullLifeTime", wt.DWORD)]

        etat = _SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(etat)):
            return None
        return {0: False, 1: True}.get(etat.ACLineStatus)

    def surveiller(self, rappel) -> None:
        """Relève toutes les 3 secondes le verrouillage, l'alimentation et le Wi-Fi ;
        seuls les changements d'état sont transmis."""

        def emettre(evenement, valeur=None):
            try:
                rappel(evenement, valeur)
            except Exception:
                log.exception("Déclenchement %s impossible", evenement)

        def boucle():
            verrou, secteur, wifi = self.session_verrouillee(), self.sur_secteur(), self.wifi_connecte()
            log.info("Écoute des événements : session %s, %s, Wi-Fi %s",
                     "verrouillée" if verrou else "ouverte", "secteur" if secteur else "batterie", wifi or "aucun")
            while True:
                time.sleep(_INTERVALLE_EVENEMENTS)
                try:
                    v = self.session_verrouillee()
                    if v is not None and verrou is not None and v != verrou:
                        emettre("session.verrouillee" if v else "session.deverrouillee")
                    verrou = v if v is not None else verrou
                    s = self.sur_secteur()
                    if s is not None and secteur is not None and s != secteur:
                        emettre("alimentation.secteur" if s else "alimentation.batterie")
                    secteur = s if s is not None else secteur
                    w = self.wifi_connecte()
                    if w != wifi:
                        if wifi:
                            emettre("wifi.deconnecte", wifi)
                        if w:
                            emettre("reseau.connecte", w)
                            emettre("wifi.connecte", w)
                        wifi = w
                except Exception:
                    log.exception("Relevé des événements impossible")

        threading.Thread(target=boucle, daemon=True, name="événements système").start()

    # --- Son -------------------------------------------------------------------------
    def lire_volume(self) -> tuple[int, bool]:
        with _Volume(_SORTIE) as v:
            return round(v.lire() * 100), v.muet()

    def definir_volume(self, pourcent: int) -> None:
        pourcent = max(0, min(100, int(pourcent)))
        with _Volume(_SORTIE) as v:
            v.regler(pourcent / 100)
            if pourcent > 0:
                v.couper(False)

    def changer_volume(self, delta: int) -> None:
        with _Volume(_SORTIE) as v:
            v.regler(v.lire() + int(delta) / 100)

    def basculer_muet(self) -> bool:
        with _Volume(_SORTIE) as v:
            v.couper(not v.muet())
            return v.muet()

    def basculer_micro_muet(self) -> bool:
        with _Volume(_ENTREE) as v:
            v.couper(not v.muet())
            return v.muet()

    # --- Musique : touches multimédia, comprises par le lecteur actif ---------------
    def media(self, commande: str) -> str:
        touche = {"lecture-pause": 0xB3, "suivant": 0xB0, "precedent": 0xB1}[commande]
        KEYEVENTF_KEYUP = 0x2
        ctypes.windll.user32.keybd_event(touche, 0, 0, 0)
        ctypes.windll.user32.keybd_event(touche, 0, KEYEVENTF_KEYUP, 0)
        return "lecteur actif"
