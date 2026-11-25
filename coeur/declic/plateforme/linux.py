"""Plateforme Linux (GNOME, Wayland ou X11).

Services utilisés (vérifiés sur Fedora / GNOME 51, voir docs/equivalences-macos-linux.md) :
  applis       : Gio.AppInfo (fichiers .desktop)
  session      : org.freedesktop.login1, org.gnome.SessionManager, org.gnome.ScreenSaver
  réglages     : GSettings (thème, éclairage nocturne, notifications, fichiers cachés)
  réseau       : NetworkManager (Wi-Fi), org.gnome.SettingsDaemon.Rfkill (Bluetooth, mode avion)
  énergie      : net.hadess.PowerProfiles
  son          : PipeWire via `wpctl`
  musique      : MPRIS (org.mpris.MediaPlayer2.*)
  presse-pap.  : `wl-copy` (Wayland) ou `xclip` (X11)
  coffre       : trousseau GNOME (Secret Service, libsecret)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from declic.plateforme.base import Application, Fichier, NonPrisEnCharge, Plateforme  # noqa: E402

_TIMEOUT_MS = 5000
DUREE_ACCESSIBILITE_S = 60  # l'accessibilité allumée par Déclic est recoupée après une minute sans usage
ATTENTE_ACCESSIBILITE_S = 4.0

# Coffre : schéma partagé avec l'extension GNOME (qui lit le mot de passe au moment de le taper)
SCHEMA_COFFRE = "app.declic.Identifiant"
ATTRIBUTS_COFFRE = ("declic-site", "declic-nom", "declic-adresse", "declic-identifiant", "declic-titre")
_PROFILS = {"economie": "power-saver", "equilibre": "balanced", "performance": "performance"}


class PlateformeLinux(Plateforme):
    nom = "Linux"

    def __init__(self):
        import threading

        self._session = None
        self._systeme = None
        self._verrou_a11y = threading.Lock()
        self._a11y_par_declic = False
        self._minuteur_a11y = None
        self._index_fichiers = None
        self._verrou_fichiers = threading.Lock()

    # --- outils D-Bus ----------------------------------------------------------------
    @property
    def bus_session(self) -> Gio.DBusConnection:
        if self._session is None:
            self._session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return self._session

    @property
    def bus_systeme(self) -> Gio.DBusConnection:
        if self._systeme is None:
            self._systeme = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        return self._systeme

    @staticmethod
    def _appel(bus, dest, chemin, interface, methode, parametres=None, retour=None):
        resultat = bus.call_sync(
            dest, chemin, interface, methode, parametres,
            GLib.VariantType(retour) if retour else None,
            Gio.DBusCallFlags.NONE, _TIMEOUT_MS, None,
        )
        return resultat.unpack() if resultat is not None else None

    def _lire_propriete(self, bus, dest, chemin, interface, nom):
        (valeur,) = self._appel(
            bus, dest, chemin, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (interface, nom)), "(v)",
        )
        return valeur

    def _ecrire_propriete(self, bus, dest, chemin, interface, nom, variant: GLib.Variant):
        self._appel(
            bus, dest, chemin, "org.freedesktop.DBus.Properties", "Set",
            GLib.Variant("(ssv)", (interface, nom, variant)),
        )

    @staticmethod
    def _reglages(schema: str) -> Gio.Settings:
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup(schema, True) is None:
            raise NonPrisEnCharge(f"Réglage GNOME introuvable : {schema}")
        return Gio.Settings.new(schema)

    def _basculer_booleen(self, schema: str, cle: str) -> bool:
        reglages = self._reglages(schema)
        nouveau = not reglages.get_boolean(cle)
        reglages.set_boolean(cle, nouveau)
        Gio.Settings.sync()
        return nouveau

    # --- Applications et ouverture -------------------------------------------------
    def lister_applications(self) -> list[Application]:
        applis = []
        for app in Gio.AppInfo.get_all():
            if not app.should_show():
                continue
            icone = app.get_icon()
            mots_cles = ()
            if isinstance(app, Gio.DesktopAppInfo):
                mots_cles = tuple(app.get_keywords() or ())
            applis.append(Application(
                id=app.get_id() or "",
                nom=app.get_display_name() or app.get_name() or "",
                description=app.get_description() or "",
                icone=icone.to_string() if icone else "",
                mots_cles=mots_cles,
            ))
        return applis

    def lancer_application(self, app_id: str) -> None:
        app = Gio.DesktopAppInfo.new(app_id)
        if app is None:
            raise NonPrisEnCharge(f"Application introuvable : {app_id}")
        app.launch([], None)

    def ouvrir(self, cible: str) -> None:
        if "://" not in cible:
            cible = Gio.File.new_for_path(os.path.expanduser(cible)).get_uri()
        Gio.AppInfo.launch_default_for_uri(cible, None)

    # --- Presse-papiers et notifications -------------------------------------------
    def copier_texte(self, texte: str) -> None:
        if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
            commande = ["wl-copy"]
        elif shutil.which("xclip"):
            commande = ["xclip", "-selection", "clipboard"]
        else:
            raise NonPrisEnCharge("Installez wl-clipboard (wl-copy) ou xclip pour copier.")
        subprocess.run(commande, input=texte.encode(), check=True, timeout=5)

    def notifier(self, titre: str, message: str = "") -> None:
        self._appel(
            self.bus_session, "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications", "Notify",
            GLib.Variant("(susssasa{sv}i)", ("Déclic", 0, "system-run-symbolic", titre, message, [], {}, -1)),
        )

    # --- Session et alimentation ---------------------------------------------------
    def verrouiller(self) -> None:
        self._appel(self.bus_session, "org.gnome.ScreenSaver", "/org/gnome/ScreenSaver",
                    "org.gnome.ScreenSaver", "Lock")

    def _login1(self, methode: str) -> None:
        self._appel(self.bus_systeme, "org.freedesktop.login1", "/org/freedesktop/login1",
                    "org.freedesktop.login1.Manager", methode, GLib.Variant("(b)", (True,)))

    def veille(self) -> None:
        self._login1("Suspend")

    def redemarrer(self) -> None:
        self._login1("Reboot")

    def eteindre(self) -> None:
        self._login1("PowerOff")

    def deconnecter(self) -> None:
        # 1 = sans boîte de confirmation (Déclic a déjà demandé confirmation)
        self._appel(self.bus_session, "org.gnome.SessionManager", "/org/gnome/SessionManager",
                    "org.gnome.SessionManager", "Logout", GLib.Variant("(u)", (1,)))

    def definir_profil_energie(self, profil: str) -> None:
        if profil not in _PROFILS:
            raise ValueError(f"Profil inconnu : {profil}")
        self._ecrire_propriete(self.bus_systeme, "net.hadess.PowerProfiles", "/net/hadess/PowerProfiles",
                               "net.hadess.PowerProfiles", "ActiveProfile", GLib.Variant("s", _PROFILS[profil]))

    # --- Fichiers ------------------------------------------------------------------
    def vider_corbeille(self) -> None:
        subprocess.run(["gio", "trash", "--empty"], check=True, timeout=60)

    def ouvrir_corbeille(self) -> None:
        self.ouvrir("trash:///")

    # Index de GNOME (LocalSearch, anciennement Tracker) : le nom de chaque fichier y est déjà,
    # une recherche prend quelques millisecondes et ne touche pas au disque.
    _SERVICES_INDEX = ("org.freedesktop.LocalSearch3", "org.freedesktop.Tracker3.Miner.Files")

    def _requete_fichiers(self, nb_mots: int):
        if self._index_fichiers is None:
            try:
                gi.require_version("Tsparql", "3.0")
                from gi.repository import Tsparql
            except (ImportError, ValueError) as exc:
                raise NonPrisEnCharge("L'index de fichiers de GNOME (TinySPARQL) est absent.") from exc
            connexion = None
            for service in self._SERVICES_INDEX:
                try:
                    connexion = Tsparql.SparqlConnection.bus_new(service, None, None)
                    break
                except GLib.Error:
                    continue
            if connexion is None:
                raise NonPrisEnCharge("L'index de fichiers de GNOME (LocalSearch) ne répond pas.")
            self._index_fichiers = {"connexion": connexion, "requetes": {}}
        requetes = self._index_fichiers["requetes"]
        if nb_mots not in requetes:
            filtres = " ".join(f"FILTER(CONTAINS(tracker:unaccent(LCASE(?nom)), ~m{i}))" for i in range(nb_mots))
            sparql = (
                "SELECT ?url ?nom ?modif ?mime WHERE { "
                "GRAPH tracker:FileSystem { ?f a nfo:FileDataObject ; nfo:fileName ?nom ; nie:url ?url . "
                "OPTIONAL { ?f nfo:fileLastModified ?modif } "
                f"{filtres} }} "
                "OPTIONAL { ?f nie:interpretedAs/nie:mimeType ?mime } "
                "} ORDER BY DESC(?modif) LIMIT ~limite"
            )
            requetes[nb_mots] = self._index_fichiers["connexion"].query_statement(sparql, None)
        return requetes[nb_mots]

    def chercher_fichiers(self, mots: list[str], limite: int = 60) -> list[Fichier]:
        mots = [m for m in mots if m][:6]
        if not mots:
            return []
        with self._verrou_fichiers:
            requete = self._requete_fichiers(len(mots))
            for i, mot in enumerate(mots):
                requete.bind_string(f"m{i}", mot)
            requete.bind_int("limite", limite)
            curseur = requete.execute(None)
            fichiers = []
            while curseur.next(None):
                chemin = Gio.File.new_for_uri(curseur.get_string(0)[0]).get_path()
                if not chemin:
                    continue
                if not os.path.lexists(chemin):
                    continue  # supprimé depuis la dernière indexation
                modif = curseur.get_datetime(2)
                fichiers.append(Fichier(
                    chemin=chemin, nom=curseur.get_string(1)[0] or os.path.basename(chemin),
                    dossier=os.path.isdir(chemin), modifie=modif.to_unix() if modif else 0.0,
                    type_mime=curseur.get_string(3)[0] or ""))
                fichiers[-1].icone = self._icone_fichier(fichiers[-1])
            curseur.close()
        return fichiers

    @staticmethod
    def _icone_fichier(fichier: Fichier) -> str:
        if fichier.dossier:
            return "folder-symbolic"
        type_ = fichier.type_mime or Gio.content_type_guess(fichier.nom, None)[0]
        nom = Gio.content_type_get_generic_icon_name(type_) or "text-x-generic"
        return f"{nom}-symbolic"

    def afficher_dans_dossier(self, chemin: str) -> None:
        uri = Gio.File.new_for_path(chemin).get_uri()
        try:
            self.bus_session.call_sync(
                "org.freedesktop.FileManager1", "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1",
                "ShowItems", GLib.Variant("(ass)", ([uri], "")), None, Gio.DBusCallFlags.NONE, 5000, None)
        except GLib.Error:
            self.ouvrir(os.path.dirname(chemin))

    # --- Bascules ------------------------------------------------------------------
    def basculer_theme_sombre(self) -> bool:
        reglages = self._reglages("org.gnome.desktop.interface")
        sombre = reglages.get_string("color-scheme") != "prefer-dark"
        reglages.set_string("color-scheme", "prefer-dark" if sombre else "default")
        Gio.Settings.sync()
        return sombre

    def basculer_eclairage_nocturne(self) -> bool:
        return self._basculer_booleen("org.gnome.settings-daemon.plugins.color", "night-light-enabled")

    def basculer_ne_pas_deranger(self) -> bool:
        # « show-banners » vrai = notifications affichées ; « Ne pas déranger » = l'inverse
        return not self._basculer_booleen("org.gnome.desktop.notifications", "show-banners")

    def basculer_fichiers_caches(self) -> bool:
        etat = self._basculer_booleen("org.gnome.nautilus.preferences", "show-hidden-files")
        try:
            self._reglages("org.gtk.gtk4.Settings.FileChooser").set_boolean("show-hidden", etat)
            Gio.Settings.sync()
        except NonPrisEnCharge:
            pass
        return etat

    def basculer_wifi(self) -> bool:
        args = (self.bus_systeme, "org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager",
                "org.freedesktop.NetworkManager", "WirelessEnabled")
        nouveau = not self._lire_propriete(*args)
        self._ecrire_propriete(*args, GLib.Variant("b", nouveau))
        return nouveau

    def _rfkill(self, propriete: str) -> bool:
        args = (self.bus_session, "org.gnome.SettingsDaemon.Rfkill", "/org/gnome/SettingsDaemon/Rfkill",
                "org.gnome.SettingsDaemon.Rfkill", propriete)
        coupe = not self._lire_propriete(*args)
        self._ecrire_propriete(*args, GLib.Variant("b", coupe))
        return coupe

    def basculer_bluetooth(self) -> bool:
        # BluetoothAirplaneMode vrai = Bluetooth coupé
        return not self._rfkill("BluetoothAirplaneMode")

    def basculer_mode_avion(self) -> bool:
        return self._rfkill("AirplaneMode")

    def etat_bascule(self, nom: str) -> bool:
        def booleen(schema, cle):
            return self._reglages(schema).get_boolean(cle)

        def rfkill(propriete):
            return bool(self._lire_propriete(self.bus_session, "org.gnome.SettingsDaemon.Rfkill",
                                             "/org/gnome/SettingsDaemon/Rfkill", "org.gnome.SettingsDaemon.Rfkill",
                                             propriete))

        lecteurs = {
            "theme_sombre": lambda: self._reglages("org.gnome.desktop.interface").get_string("color-scheme")
            == "prefer-dark",
            "eclairage_nocturne": lambda: booleen("org.gnome.settings-daemon.plugins.color", "night-light-enabled"),
            "ne_pas_deranger": lambda: not booleen("org.gnome.desktop.notifications", "show-banners"),
            "fichiers_caches": lambda: booleen("org.gnome.nautilus.preferences", "show-hidden-files"),
            "wifi": lambda: bool(self._lire_propriete(
                self.bus_systeme, "org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager",
                "org.freedesktop.NetworkManager", "WirelessEnabled")),
            "bluetooth": lambda: not rfkill("BluetoothAirplaneMode"),
            "mode_avion": lambda: rfkill("AirplaneMode"),
        }
        if nom not in lecteurs:
            raise NonPrisEnCharge(f"État inconnu : {nom}")
        return lecteurs[nom]()

    # --- Programmes ouverts ----------------------------------------------------------
    def processus(self) -> dict[str, str]:
        """Programmes de l'utilisateur, lus dans /proc. Pour un jeu Windows lancé par Proton ou Wine, c'est le
        .exe (et son chemin dans steamapps/common…) qui compte, pas wine."""
        moi = os.getuid()
        trouves: dict[str, str] = {}
        for entree in os.scandir("/proc"):
            if not entree.name.isdigit():
                continue
            try:
                if entree.stat().st_uid != moi:
                    continue
                with open(f"/proc/{entree.name}/cmdline", "rb") as f:
                    arguments = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
                chemin = next((a for a in arguments if a.lower().endswith(".exe")), "") \
                    or os.readlink(f"/proc/{entree.name}/exe")
            except OSError:
                continue
            nom = re.split(r"[\\/]", chemin)[-1]
            if nom.lower().endswith(".exe"):
                nom = nom[:-4]
            if nom:
                trouves.setdefault(nom, chemin.replace("\\", "/"))
        return trouves

    def fermer_application(self, nom: str) -> int:
        import signal

        nom = nom.strip().removesuffix(".exe")
        moi, cibles = os.getuid(), []
        for entree in os.scandir("/proc"):
            if not entree.name.isdigit():
                continue
            try:
                if entree.stat().st_uid != moi:
                    continue
                with open(f"/proc/{entree.name}/comm", encoding="utf-8", errors="replace") as f:
                    commande = f.read().strip()
                exe = os.path.basename(os.readlink(f"/proc/{entree.name}/exe"))
            except OSError:
                continue
            if nom.casefold() in (commande.casefold(), exe.casefold()):
                cibles.append(int(entree.name))
        for pid in cibles:
            try:
                os.kill(pid, signal.SIGTERM)  # comme la croix de la fenêtre : l'application peut enregistrer
            except OSError:
                pass
        return len(cibles)

    # --- Son (PipeWire) --------------------------------------------------------------
    # --- Réseau --------------------------------------------------------------------
    def reseaux_wifi_connus(self) -> list[str]:
        nm = "org.freedesktop.NetworkManager"
        chemins = self._appel(self.bus_systeme, nm, "/org/freedesktop/NetworkManager/Settings",
                              f"{nm}.Settings", "ListConnections", None, "(ao)")[0]
        noms = []
        for chemin in chemins:
            try:
                (reglages,) = self._appel(self.bus_systeme, nm, chemin, f"{nm}.Settings.Connection",
                                          "GetSettings", None, "(a{sa{sv}})")
            except GLib.Error:
                continue
            connexion = reglages.get("connection", {})
            if connexion.get("type") == "802-11-wireless" and connexion.get("id"):
                noms.append(str(connexion["id"]))
        return sorted(set(noms), key=str.casefold)

    # --- Coffre à identifiants : trousseau GNOME (Secret Service) --------------------
    @staticmethod
    def _secret():
        gi.require_version("Secret", "1")
        from gi.repository import Secret

        return Secret, Secret.Schema.new(SCHEMA_COFFRE, Secret.SchemaFlags.NONE, {
            cle: Secret.SchemaAttributeType.STRING for cle in ATTRIBUTS_COFFRE})

    def coffre_enregistrer(self, site, attributs, mot_de_passe):
        Secret, schema = self._secret()
        valeurs = {f"declic-{k}": str(attributs.get(k, "")) for k in ("nom", "adresse", "identifiant", "titre")}
        valeurs["declic-site"] = site
        Secret.password_store_sync(schema, valeurs, Secret.COLLECTION_DEFAULT,
                                   f"Déclic : {attributs.get('nom', site)}", mot_de_passe, None)

    def coffre_lister(self):
        Secret, schema = self._secret()
        # sans LOAD_SECRETS : on ne lit que les attributs publics, jamais les mots de passe
        elements = Secret.password_search_sync(schema, {}, Secret.SearchFlags.ALL, None) or []
        liste = []
        for element in elements:
            a = element.get_attributes()
            liste.append({"site": a.get("declic-site", ""), "nom": a.get("declic-nom", ""),
                          "adresse": a.get("declic-adresse", ""), "identifiant": a.get("declic-identifiant", ""),
                          "titre": a.get("declic-titre", "")})
        return [e for e in liste if e["site"]]

    def coffre_supprimer(self, site):
        Secret, schema = self._secret()
        return bool(Secret.password_clear_sync(schema, {"declic-site": site}, None))

    # --- Clés d'API des IA : trousseau GNOME, schéma à part des identifiants de sites ---
    @staticmethod
    def _secret_ia():
        gi.require_version("Secret", "1")
        from gi.repository import Secret

        return Secret, Secret.Schema.new("app.declic.CleIA", Secret.SchemaFlags.NONE,
                                         {"declic-ia": Secret.SchemaAttributeType.STRING})

    def secret_enregistrer(self, nom, valeur):
        Secret, schema = self._secret_ia()
        Secret.password_store_sync(schema, {"declic-ia": nom}, Secret.COLLECTION_DEFAULT,
                                   f"Déclic : clé d'API {nom}", valeur, None)

    def secret_lire(self, nom):
        Secret, schema = self._secret_ia()
        return Secret.password_lookup_sync(schema, {"declic-ia": nom}, None)

    def secret_supprimer(self, nom):
        Secret, schema = self._secret_ia()
        Secret.password_clear_sync(schema, {"declic-ia": nom}, None)

    def saisir_identifiant(self, site, delai_s):
        try:
            self._appel(self.bus_session, "org.gnome.Shell", "/app/declic/Shell", "app.declic.Shell",
                        "SaisirIdentifiant", GLib.Variant("(si)", (site, int(delai_s))))
        except GLib.Error as exc:
            raise NonPrisEnCharge("La barre Déclic (extension GNOME) n'est pas active : "
                                  "reconnectez-vous pour la charger.") from exc

    def valider_page(self, adresse, delai_s):
        try:
            self._appel(self.bus_session, "org.gnome.Shell", "/app/declic/Shell", "app.declic.Shell",
                        "ValiderPage", GLib.Variant("(si)", (adresse, int(delai_s))))
        except GLib.Error as exc:
            raise NonPrisEnCharge("La barre Déclic (extension GNOME) n'est pas active : "
                                  "reconnectez-vous pour la charger.") from exc

    # L'accessibilité (AT-SPI) n'est allumée qu'au besoin : Firefox n'expose l'adresse de ses pages que
    # lorsqu'elle est active, et il la prend en compte en cours de route (testé avec Firefox 160).
    # Déclic l'allume juste avant de lire une adresse et la recoupe après une minute sans usage,
    # seulement si c'est lui qui l'avait allumée.
    def _accessibilite(self, actif: bool | None = None) -> bool:
        bus, chemin, interface = "org.a11y.Bus", "/org/a11y/bus", "org.a11y.Status"
        if actif is not None:
            self._ecrire_propriete(self.bus_session, bus, chemin, interface, "IsEnabled", GLib.Variant("b", actif))
            return actif
        return bool(self._lire_propriete(self.bus_session, bus, chemin, interface, "IsEnabled"))

    def _accessibilite_au_besoin(self) -> bool:
        """Allume l'accessibilité si elle est coupée ; renvoie True si on vient de l'allumer."""
        import threading

        with self._verrou_a11y:
            allumee_ici = False
            if not self._accessibilite():
                self._accessibilite(True)
                self._a11y_par_declic = True
                allumee_ici = True
            if self._a11y_par_declic:
                if self._minuteur_a11y is not None:
                    self._minuteur_a11y.cancel()
                self._minuteur_a11y = threading.Timer(DUREE_ACCESSIBILITE_S, self._couper_accessibilite)
                self._minuteur_a11y.daemon = True
                self._minuteur_a11y.start()
            return allumee_ici

    def _couper_accessibilite(self) -> None:
        with self._verrou_a11y:
            self._minuteur_a11y = None
            if self._a11y_par_declic:
                self._a11y_par_declic = False
                try:
                    if self._accessibilite():
                        self._accessibilite(False)
                except GLib.Error:
                    pass

    def adresse_page(self, pid):
        """Lit l'adresse de l'onglet affiché via l'accessibilité (AT-SPI), allumée seulement pour l'occasion."""
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
        import time

        try:
            vient_d_allumer = self._accessibilite_au_besoin()
        except GLib.Error:
            vient_d_allumer = False
        # le navigateur met un instant à rejoindre l'accessibilité après son allumage
        limite = time.monotonic() + (ATTENTE_ACCESSIBILITE_S if vient_d_allumer else 1.0)
        appli = None
        while appli is None:
            bureau = Atspi.get_desktop(0)
            for i in range(bureau.get_child_count()):
                candidate = bureau.get_child_at_index(i)
                if candidate is not None and candidate.get_process_id() == pid:
                    appli = candidate
                    break
            if appli is None:
                if time.monotonic() > limite:
                    return None
                time.sleep(0.2)

        def etat(acteur, quoi):
            try:
                return acteur.get_state_set().contains(quoi)
            except GLib.Error:
                return False

        # la fenêtre active du navigateur, puis le document web affiché (les onglets cachés ne sont pas « SHOWING »)
        fenetres = [appli.get_child_at_index(k) for k in range(appli.get_child_count())]
        fenetres = [f for f in fenetres if f is not None and etat(f, Atspi.StateType.ACTIVE)]
        if len(fenetres) != 1:
            return None

        def document(acteur, profondeur=0):
            if acteur is None or profondeur > 20:
                return None
            try:
                role = acteur.get_role()
                if role == Atspi.Role.DOCUMENT_WEB:
                    return acteur if etat(acteur, Atspi.StateType.SHOWING) else None
                for k in range(min(acteur.get_child_count(), 80)):
                    trouve = document(acteur.get_child_at_index(k), profondeur + 1)
                    if trouve is not None:
                        return trouve
            except GLib.Error:
                return None
            return None

        doc = document(fenetres[0])
        if doc is None:
            return None
        try:
            return doc.get_document_attribute_value("DocURL") or None
        except GLib.Error:
            return None

    # --- Événements (déclencheurs des automatisations) -------------------------------
    def surveiller(self, rappel) -> None:
        """Écoute ScreenSaver (verrouillage), UPower (secteur/batterie) et NetworkManager (réseau)
        dans une boucle GLib à part. Seuls les changements d'état sont transmis."""
        import threading

        pret = threading.Event()

        def boucle():
            contexte = GLib.MainContext.new()
            contexte.push_thread_default()
            try:
                self._abonner_evenements(rappel)
            except Exception:
                import logging
                logging.getLogger("declic").exception("Abonnement aux événements impossible")
            finally:
                pret.set()
            GLib.MainLoop.new(contexte, False).run()

        threading.Thread(target=boucle, daemon=True, name="événements système").start()
        pret.wait(5)

    def _abonner_evenements(self, rappel) -> None:
        import logging
        log = logging.getLogger("declic")

        def emettre(evenement, valeur=None):
            try:
                rappel(evenement, valeur)
            except Exception:
                log.exception("Déclenchement %s impossible", evenement)

        # Verrouillage de l'écran (GNOME)
        def ecran(_c, _e, _p, _i, _s, parametres, *_):
            (verrouille,) = parametres.unpack()
            emettre("session.verrouillee" if verrouille else "session.deverrouillee")

        self.bus_session.signal_subscribe(
            "org.gnome.ScreenSaver", "org.gnome.ScreenSaver", "ActiveChanged", "/org/gnome/ScreenSaver",
            None, Gio.DBusSignalFlags.NONE, ecran)

        # Secteur / batterie
        etat = {"batterie": None, "connexion": None}
        try:
            etat["batterie"] = bool(self._lire_propriete(self.bus_systeme, "org.freedesktop.UPower",
                                                         "/org/freedesktop/UPower", "org.freedesktop.UPower", "OnBattery"))
        except GLib.Error:
            pass

        def upower(_c, _e, _p, _i, _s, parametres, *_):
            interface, changes, _invalides = parametres.unpack()
            if interface == "org.freedesktop.UPower" and "OnBattery" in changes:
                batterie = bool(changes["OnBattery"])
                if batterie != etat["batterie"]:
                    etat["batterie"] = batterie
                    emettre("alimentation.batterie" if batterie else "alimentation.secteur")

        self.bus_systeme.signal_subscribe(
            "org.freedesktop.UPower", "org.freedesktop.DBus.Properties", "PropertiesChanged",
            "/org/freedesktop/UPower", None, Gio.DBusSignalFlags.NONE, upower)

        # Réseau : la connexion principale de NetworkManager
        def connexion_principale():
            nm = "org.freedesktop.NetworkManager"
            try:
                chemin = self._lire_propriete(self.bus_systeme, nm, "/org/freedesktop/NetworkManager", nm,
                                              "PrimaryConnection")
                if not chemin or chemin == "/":
                    return None
                active = f"{nm}.Connection.Active"
                return (str(self._lire_propriete(self.bus_systeme, nm, chemin, active, "Id")),
                        str(self._lire_propriete(self.bus_systeme, nm, chemin, active, "Type")))
            except GLib.Error:
                return None

        etat["connexion"] = connexion_principale()

        def reseau(_c, _e, _p, _i, _s, parametres, *_):
            interface, changes, _invalides = parametres.unpack()
            if interface != "org.freedesktop.NetworkManager" or "PrimaryConnection" not in changes:
                return
            nouvelle, ancienne = connexion_principale(), etat["connexion"]
            if nouvelle == ancienne:
                return
            etat["connexion"] = nouvelle
            if ancienne and ancienne[1] == "802-11-wireless":
                emettre("wifi.deconnecte", ancienne[0])
            if nouvelle:
                emettre("reseau.connecte", nouvelle[0])
                if nouvelle[1] == "802-11-wireless":
                    emettre("wifi.connecte", nouvelle[0])

        self.bus_systeme.signal_subscribe(
            "org.freedesktop.NetworkManager", "org.freedesktop.DBus.Properties", "PropertiesChanged",
            "/org/freedesktop/NetworkManager", None, Gio.DBusSignalFlags.NONE, reseau)
        log.info("Écoute des événements : écran, alimentation (%s), réseau (%s)",
                 "batterie" if etat["batterie"] else "secteur", etat["connexion"][0] if etat["connexion"] else "aucun")

    @staticmethod
    def _wpctl(*args: str) -> str:
        if not shutil.which("wpctl"):
            raise NonPrisEnCharge("wpctl (PipeWire/WirePlumber) est introuvable.")
        sortie = subprocess.run(["wpctl", *args], capture_output=True, text=True, timeout=5, check=True)
        return sortie.stdout

    def _lire(self, cible: str) -> tuple[int, bool]:
        texte = self._wpctl("get-volume", cible)
        m = re.search(r"Volume:\s*([0-9.]+)", texte)
        if not m:
            raise NonPrisEnCharge(f"Réponse inattendue de wpctl : {texte.strip()}")
        return round(float(m.group(1)) * 100), "[MUTED]" in texte

    def lire_volume(self) -> tuple[int, bool]:
        return self._lire("@DEFAULT_AUDIO_SINK@")

    def definir_volume(self, pourcent: int) -> None:
        pourcent = max(0, min(100, int(pourcent)))
        self._wpctl("set-volume", "@DEFAULT_AUDIO_SINK@", f"{pourcent / 100:.2f}")
        if pourcent > 0:
            self._wpctl("set-mute", "@DEFAULT_AUDIO_SINK@", "0")

    def changer_volume(self, delta: int) -> None:
        signe = "+" if delta >= 0 else "-"
        self._wpctl("set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{abs(int(delta))}%{signe}")

    def basculer_muet(self) -> bool:
        self._wpctl("set-mute", "@DEFAULT_AUDIO_SINK@", "toggle")
        return self._lire("@DEFAULT_AUDIO_SINK@")[1]

    def basculer_micro_muet(self) -> bool:
        self._wpctl("set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle")
        return self._lire("@DEFAULT_AUDIO_SOURCE@")[1]

    # --- Musique (MPRIS) -------------------------------------------------------------
    def lecteurs_mpris(self) -> list[tuple[str, str]]:
        """[(nom de bus, état de lecture)] ; les lecteurs en cours de lecture d'abord."""
        (noms,) = self._appel(self.bus_session, "org.freedesktop.DBus", "/org/freedesktop/DBus",
                              "org.freedesktop.DBus", "ListNames", None, "(as)")
        lecteurs = []
        for nom in noms:
            if not nom.startswith("org.mpris.MediaPlayer2."):
                continue
            try:
                etat = self._lire_propriete(self.bus_session, nom, "/org/mpris/MediaPlayer2",
                                            "org.mpris.MediaPlayer2.Player", "PlaybackStatus")
            except GLib.Error:
                etat = "Unknown"
            lecteurs.append((nom, etat))
        lecteurs.sort(key=lambda l: {"Playing": 0, "Paused": 1}.get(l[1], 2))
        return lecteurs

    def media(self, commande: str) -> str:
        methode = {"lecture-pause": "PlayPause", "suivant": "Next", "precedent": "Previous"}[commande]
        lecteurs = self.lecteurs_mpris()
        if not lecteurs:
            raise NonPrisEnCharge("Aucun lecteur de musique ou de vidéo n'est ouvert.")
        nom = lecteurs[0][0]
        self._appel(self.bus_session, nom, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", methode)
        return nom.removeprefix("org.mpris.MediaPlayer2.").split(".")[0]
