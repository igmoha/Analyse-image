#!/usr/bin/env python3
"""
watcher.py
==========
Surveille en continu un dossier "images à traiter" : dès qu'une image y est
déposée, le pipeline OCR (main.py) est exécuté automatiquement dessus, puis :

  - Traitement réussi (type ET numéro détectés)
        -> JSON écrit dans  image_traitee_json/<nom_image>.json
        -> image déplacée dans  image_traitee/

  - Doublon (un JSON existant a déjà le même type_document + numero_document)
        -> image déplacée dans  doublon/
        -> (le nouveau JSON n'est PAS écrit dans image_traitee_json, pour ne
           pas écraser/dupliquer un résultat déjà enregistré)

  - Échec du traitement (exception, ou type/numéro non détecté)
        -> image déplacée dans  image_non_traitable/

ARBORESCENCE ATTENDUE (créée automatiquement si absente)
----------------------------------------------------------
  <racine>/
    image_a_traiter/       <- dossier surveillé, déposer les images ici
    image_traitee/         <- images traitées avec succès
    image_traitee_json/    <- résultats JSON correspondants
    doublon/                <- images dont le résultat existe déjà
    image_non_traitable/    <- images en échec de traitement

USAGE
-----
  python watcher.py [--racine /chemin/vers/dossier_parent] [--verbose]

  Si --racine n'est pas fourni, le dossier courant est utilisé.

PRÉREQUIS
---------
  pip install watchdog
  (+ dépendances de main.py : pytesseract, easyocr, Pillow, requests, numpy)

Arrêt : Ctrl+C
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from threading import Lock

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# main.py doit être dans le même dossier que watcher.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import traiter_image, charger_moteurs, sauvegarder_json  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# Délai (secondes) avant de traiter un fichier après sa dernière modification.
# Permet d'éviter de lire un fichier en cours d'écriture (copie lente, upload...).
DELAI_STABILISATION = 2.0

# Intervalle (secondes) de la boucle de vérification des fichiers "en attente"
INTERVALLE_VERIFICATION = 1.0


# ---------------------------------------------------------------------------
# Utilitaires dossiers
# ---------------------------------------------------------------------------

def preparer_dossiers(racine: Path) -> dict:
    """Crée (si besoin) et retourne les chemins des dossiers du pipeline."""
    dossiers = {
        "a_traiter":      racine / "image_a_traiter",
        "traitee":        racine / "image_traitee",
        "traitee_json":   racine / "image_traitee_json",
        "doublon":        racine / "doublon",
        "non_traitable":  racine / "image_non_traitable",
    }
    for chemin in dossiers.values():
        chemin.mkdir(parents=True, exist_ok=True)
    return dossiers


def chemin_disponible(chemin: Path) -> Path:
    """
    Retourne `chemin` s'il n'existe pas encore, sinon ajoute un suffixe
    _1, _2, ... avant l'extension jusqu'à trouver un nom libre.
    """
    if not chemin.exists():
        return chemin

    stem, suffix, parent = chemin.stem, chemin.suffix, chemin.parent
    compteur = 1
    while True:
        candidat = parent / f"{stem}_{compteur}{suffix}"
        if not candidat.exists():
            return candidat
        compteur += 1


def deplacer_vers(fichier: Path, dossier_dest: Path, verbose: bool = False) -> Path:
    """Déplace `fichier` dans `dossier_dest` en gérant les collisions de nom."""
    destination = chemin_disponible(dossier_dest / fichier.name)
    shutil.move(str(fichier), str(destination))
    if verbose:
        print(f"  -> déplacé vers : {destination}")
    return destination


# ---------------------------------------------------------------------------
# Détection de doublon
# ---------------------------------------------------------------------------

def est_un_doublon(resultat: dict, dossier_json: Path) -> bool:
    """
    Vérifie si un JSON déjà présent dans `dossier_json` correspond au même
    document : même type_document ET même numero_document.

    Les documents non détectés ("Non détecté") ne sont jamais considérés
    comme des doublons entre eux (sinon toutes les images en échec partiel
    seraient signalées comme doublons les unes des autres).
    """
    type_doc   = resultat.get("type_document")
    numero_doc = resultat.get("numero_document")

    if not type_doc or not numero_doc:
        return False
    if type_doc == "Non détecté" or numero_doc == "Non détecté":
        return False

    for fichier_json in dossier_json.glob("*.json"):
        try:
            existant = json.loads(fichier_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if (
            existant.get("type_document") == type_doc
            and existant.get("numero_document") == numero_doc
        ):
            return True

    return False


def traitement_reussi(resultat: dict) -> bool:
    """
    Un traitement est considéré réussi seulement si le type ET le numéro
    de document ont bien été détectés (le but métier du pipeline).
    """
    return (
        resultat.get("type_document") not in (None, "Non détecté")
        and resultat.get("numero_document") not in (None, "Non détecté")
    )


# ---------------------------------------------------------------------------
# Traitement d'une image
# ---------------------------------------------------------------------------

def traiter_un_fichier(fichier: Path, dossiers: dict, moteurs: dict, verbose: bool = False) -> None:
    """Exécute le pipeline OCR sur `fichier` et le range selon le résultat."""
    print(f"[TRAITEMENT] {fichier.name}")

    try:
        resultat = traiter_image(str(fichier), moteurs=moteurs, verbose=verbose)
    except Exception as exc:
        print(f"  [ECHEC] Erreur pendant le traitement : {exc}")
        deplacer_vers(fichier, dossiers["non_traitable"], verbose=verbose)
        return

    if not traitement_reussi(resultat):
        print(
            f"  [ECHEC] Type/numéro non détecté "
            f"(type={resultat.get('type_document')}, numero={resultat.get('numero_document')})"
        )
        deplacer_vers(fichier, dossiers["non_traitable"], verbose=verbose)
        return

    if est_un_doublon(resultat, dossiers["traitee_json"]):
        print(
            f"  [DOUBLON] type={resultat.get('type_document')} "
            f"numero={resultat.get('numero_document')} déjà traité."
        )
        deplacer_vers(fichier, dossiers["doublon"], verbose=verbose)
        return

    # ------------------------------------------------------------------
    # Succès : écrire le JSON (nom = même nom que l'image) puis déplacer
    # l'image. On déplace l'image EN DERNIER pour ne pas perdre le fichier
    # source si l'écriture du JSON échouait.
    # ------------------------------------------------------------------
    chemin_json = chemin_disponible(dossiers["traitee_json"] / f"{fichier.stem}.json")
    sauvegarder_json(chemin_json, resultat)

    deplacer_vers(fichier, dossiers["traitee"], verbose=verbose)
    print(f"  [OK] type={resultat.get('type_document')} numero={resultat.get('numero_document')}")


# ---------------------------------------------------------------------------
# Watcher (watchdog)
# ---------------------------------------------------------------------------

class GestionnaireImages(FileSystemEventHandler):
    """
    Réagit aux événements du système de fichiers dans le dossier surveillé.

    Les fichiers détectés sont ajoutés à une file d'attente avec un
    horodatage ; un thread périodique (boucle principale) ne les traite
    qu'une fois "stables" (pas modifiés depuis DELAI_STABILISATION
    secondes), pour éviter de lire un fichier encore en cours de copie.
    """

    def __init__(self, dossiers: dict, moteurs: dict, verbose: bool = False):
        super().__init__()
        self.dossiers   = dossiers
        self.moteurs    = moteurs
        self.verbose    = verbose
        self.en_attente: dict[Path, float] = {}
        self.verrou     = Lock()

    def _est_image(self, chemin: str) -> bool:
        return Path(chemin).suffix.lower() in EXTENSIONS_IMAGE

    def _signaler(self, chemin: str) -> None:
        if not self._est_image(chemin):
            return
        fichier = Path(chemin)
        with self.verrou:
            self.en_attente[fichier] = time.time()

    def on_created(self, event):
        if not event.is_directory:
            self._signaler(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._signaler(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._signaler(event.dest_path)

    def traiter_fichiers_stables(self) -> None:
        """À appeler périodiquement : traite les fichiers stabilisés."""
        maintenant = time.time()
        a_traiter = []

        with self.verrou:
            for fichier, derniere_maj in list(self.en_attente.items()):
                if maintenant - derniere_maj >= DELAI_STABILISATION:
                    a_traiter.append(fichier)
                    del self.en_attente[fichier]

        for fichier in a_traiter:
            if not fichier.exists():
                continue  # déplacé/supprimé entre-temps
            traiter_un_fichier(fichier, self.dossiers, self.moteurs, verbose=self.verbose)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def traiter_fichiers_existants(dossiers: dict, moteurs: dict, verbose: bool = False) -> None:
    """Traite les images déjà présentes dans le dossier à traiter au démarrage."""
    fichiers = [
        f for f in dossiers["a_traiter"].iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSIONS_IMAGE
    ]
    if not fichiers:
        return
    print(f"[DEMARRAGE] {len(fichiers)} image(s) déjà présente(s), traitement...")
    for fichier in fichiers:
        traiter_un_fichier(fichier, dossiers, moteurs, verbose=verbose)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Surveille un dossier et traite automatiquement les nouvelles images via le pipeline OCR."
    )
    parser.add_argument(
        "--racine", "-r", default=".",
        help="Dossier parent contenant (ou recevant) les sous-dossiers du pipeline (défaut : dossier courant)."
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Affiche les détails de chaque traitement.")
    args = parser.parse_args()

    racine = Path(args.racine).resolve()
    dossiers = preparer_dossiers(racine)

    print("Dossiers du pipeline :")
    for nom, chemin in dossiers.items():
        print(f"  {nom:15s} -> {chemin}")

    print("\nChargement des moteurs OCR...")
    moteurs = charger_moteurs(verbose=args.verbose)
    if moteurs["extraire_texte"] is None and moteurs["extraire_texte_easyocr"] is None:
        sys.exit("[ERREUR] Aucun moteur OCR disponible (ocr.py et ocr_easy.py indisponibles).")

    # Traiter ce qui est déjà présent avant de démarrer la surveillance
    traiter_fichiers_existants(dossiers, moteurs, verbose=args.verbose)

    gestionnaire = GestionnaireImages(dossiers, moteurs, verbose=args.verbose)
    observateur = Observer()
    observateur.schedule(gestionnaire, str(dossiers["a_traiter"]), recursive=False)
    observateur.start()

    print(f"\n[SURVEILLANCE] En attente d'images dans : {dossiers['a_traiter']}")
    print("(Ctrl+C pour arrêter)\n")

    try:
        while True:
            time.sleep(INTERVALLE_VERIFICATION)
            gestionnaire.traiter_fichiers_stables()
    except KeyboardInterrupt:
        print("\n[ARRET] Arrêt demandé par l'utilisateur.")
    finally:
        observateur.stop()
        observateur.join()


if __name__ == "__main__":
    main()