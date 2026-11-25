# Windows : éclairage nocturne à reprendre

**État (25 novembre 2026)** : la commande « Basculer l'éclairage nocturne » existe sous Windows, mais l'écran
ne change pas de couleur. Testé sur Windows 11 (version 26300).

## Ce que fait le code aujourd'hui

`coeur/declic/plateforme/windows.py`, `basculer_eclairage_nocturne()` :

- lit l'enregistrement binaire `Data` du magasin de réglages de Windows (« CloudStore »), dans
  `HKCU\Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount\Current\` :
  - `default$windows.data.bluelightreduction.bluelightreductionstate\…` (clé générale) ;
  - `{…}$windows.data.bluelightreduction.bluelightreductionstateperdevice\…` (une clé par écran, sur les
    Windows 11 récents) ;
- pour activer, insère `10 00` après le second en-tête `43 42 01 00` (octet 23), ajoute 2 à l'octet 18
  (longueur de la suite) et met la date (octets 10 à 14) à maintenant ; l'inverse pour désactiver ;
- écrit les deux clés.

Le registre change bien : on le voit dans l'enregistrement, et l'historique de Déclic montre la commande
lancée. Mais Windows ne l'applique pas à l'écran. Cette méthode, très répandue, marchait sous Windows 10 et les
premiers Windows 11. Les versions récentes (clé « perdevice ») ont visiblement changé quelque chose.

Exemple d'enregistrement « désactivé » (clé générale) :

```
43 42 01 00 0A 02 01 00 2A 06 95 A1 C2 D6 06 2A 2B 0E 13 43 42 01 00 D0 0A 02 C6 14 D7 80 B9 D6 84 90 D7 EE 01 00 00 00 00
```

La clé « perdevice » est presque identique, avec `0E 14` et `… EE 01 01 00 …` (un octet de plus).

## Pistes pour la suite

1. **Comparer avec Windows lui-même** : relever les deux enregistrements, activer l'éclairage nocturne à la main
   (Paramètres → Affichage → Éclairage nocturne), les relever à nouveau, puis comparer octet par octet.
   C'est le plus sûr pour connaître le format de cette version.
   Script de lecture : `python -c` avec `winreg`, voir `_cles_eclairage_nocturne()`.
2. Vérifier si Windows attend un **horodatage** dans un autre champ que les octets 10 à 14, ou un compteur.
3. Regarder s'il existe une API ou un objet COM pour l'éclairage nocturne, comme pour Ne pas déranger
   (`QuietHoursSettings`) et le mode avion (`IRadioManager`) : chercher du côté de
   `Windows.Internal.Graphics.Display.DisplayColorManagement` et de `BlueLightReduction`.
4. En dernier recours, envoyer à Windows le même message que l'application Paramètres après l'écriture.

## À faire une fois réparé

- Tester l'activation puis la désactivation en vrai : l'écran doit devenir orangé, puis revenir.
- Retirer la mention « pas encore fonctionnel » du README (section « Installer sous Windows ») et du journal des
  versions.
- Garder le test `test_eclairage_nocturne` de `coeur/tests/test_windows.py` à jour avec le nouveau format.
