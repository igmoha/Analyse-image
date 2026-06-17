#!/usr/bin/env python3
"""
main.py
=======
Orchestrateur OCR — combine Tesseract et EasyOCR, extrait les infos document
et sauvegarde le résultat dans un fichier JSON.

Structure du JSON produit :
  {
    "fichier_source": "facture.png",
    "source_ocr":     "Tesseract",       // moteur OCR principal utilisé
    "type_document":  "Facture",
    "numero_document": "1234567",
    "texte_ocr":      "...",             // texte brut fusionné
    "stats": {
      "tesseract_caracteres": 842,
      "tesseract_lignes":     35,
      "easyocr_caracteres":   910,
      "easyocr_lignes":       37
    }
  }

PRÉREQUIS
---------
1. Tesseract-OCR installé (voir ocr.py pour les détails)
   ⚠️  Mettre à jour TESSERACT_PATH dans ocr.py

2. Dépendances Python :
     pip install pytesseract easyocr Pillow requests numpy

3. Fichiers du projet à placer dans le même dossier :
     image_utils.py, ocr.py, ocr_easy.py, extraction_text.py

USAGE
-----
  python main.py <chemin_ou_url> [--output resultat.json] [--verbose]

  Exemples :
    python main.py facture.png
    python main.py facture.png --output sorties/resultat.json --verbose
    python main.py https://example.com/image.jpg -o resultat.json -v
"""

import argparse
import importlib
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Utilitaires texte
# ---------------------------------------------------------------------------

def nettoyer_texte(texte: str) -> str:
    """Supprime les lignes vides et les espaces superflus."""
    lignes = [l.strip() for l in texte.replace("\r", "\n").splitlines() if l.strip()]
    return "\n".join(lignes)


def score_texte(texte: str) -> tuple[int, int]:
    """Retourne (nb_caractères, nb_lignes) du texte nettoyé."""
    propre = nettoyer_texte(texte)
    return len(propre), len(propre.splitlines())


def fusionner_textes(primaire: str, secondaire: str) -> str:
    """
    Fusionne deux textes OCR en gardant le primaire comme base
    et en ajoutant les lignes uniques du secondaire à la fin.
    """
    lignes_primaire   = [l.strip() for l in primaire.splitlines()   if l.strip()]
    lignes_secondaire = [l.strip() for l in secondaire.splitlines() if l.strip()]
    vues = set(lignes_primaire)
    resultat = lignes_primaire.copy()
    for ligne in lignes_secondaire:
        if ligne not in vues:
            resultat.append(ligne)
            vues.add(ligne)
    return "\n".join(resultat)


def selectionner_meilleur_resultat(texte_tesseract: str, texte_easyocr: str) -> tuple[str, str]:
    """
    Choisit le texte le plus complet comme base, fusionne l'autre dessus.

    Règle : EasyOCR est préféré s'il produit plus de 10 % de caractères
    supplémentaires par rapport à Tesseract, sinon Tesseract est retenu.

    Returns:
        (texte_fusionné, nom_source_principale)
    """
    t1 = nettoyer_texte(texte_tesseract)
    t2 = nettoyer_texte(texte_easyocr)

    if not t1:
        return t2, "EasyOCR"
    if not t2:
        return t1, "Tesseract"

    if len(t2) > len(t1) * 1.1:
        primaire, source = t2, "EasyOCR"
        secondaire = t1
    else:
        primaire, source = t1, "Tesseract"
        secondaire = t2

    return fusionner_textes(primaire, secondaire), source


# ---------------------------------------------------------------------------
# Sauvegarde JSON
# ---------------------------------------------------------------------------

def sauvegarder_json(chemin_sortie: Path, donnees: dict) -> None:
    """
    Écrit le dictionnaire de résultats dans un fichier JSON (UTF-8, indenté).

    Args:
        chemin_sortie: chemin du fichier .json à créer/écraser
        donnees:       dict contenant les résultats OCR et extraction
    """
    chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
    chemin_sortie.write_text(
        json.dumps(donnees, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"✓ Résultats sauvegardés dans : {chemin_sortie}")


# ---------------------------------------------------------------------------
# Chargement des moteurs (modules) — fait une seule fois, réutilisable
# ---------------------------------------------------------------------------

def charger_moteurs(verbose: bool = False) -> dict:
    """
    Importe dynamiquement les modules OCR / extraction.

    Returns:
        dict avec les clés 'extraire_texte', 'extraire_texte_easyocr',
        'extract_info' (valeur = None si le module est indisponible).
    """
    moteurs = {
        "extraire_texte": None,
        "extraire_texte_easyocr": None,
        "extract_info": None,
    }

    try:
        ocr_module = importlib.import_module("ocr")
        moteurs["extraire_texte"] = getattr(ocr_module, "extraire_texte")
    except Exception as exc:
        if verbose:
            print(f"[INFO] ocr.py (Tesseract) indisponible : {exc}")

    try:
        ocr_easy_module = importlib.import_module("ocr_easy")
        moteurs["extraire_texte_easyocr"] = getattr(ocr_easy_module, "extraire_texte_easyocr")
    except Exception as exc:
        if verbose:
            print(f"[INFO] ocr_easy.py (EasyOCR) indisponible : {exc}")

    try:
        extraction_module = importlib.import_module("extraction_text")
        moteurs["extract_info"] = getattr(extraction_module, "extract_info")
    except Exception as exc:
        if verbose:
            print(f"[INFO] extraction_text.py indisponible : {exc}")

    return moteurs


# ---------------------------------------------------------------------------
# Fonction principale réutilisable (sans argparse, sans sys.exit)
# ---------------------------------------------------------------------------

def traiter_image(source: str, moteurs: dict = None, verbose: bool = False) -> dict:
    """
    Exécute le pipeline OCR complet sur une image et retourne le résultat.

    Args:
        source:  chemin local ou URL de l'image
        moteurs: dict produit par charger_moteurs() ; si None, est rechargé
                 à chaque appel (plus lent — préférer le passer explicitement
                 quand on traite plusieurs images d'affilée).
        verbose: affiche un résumé détaillé dans la console.

    Returns:
        dict au même format que celui sauvegardé par sauvegarder_json().

    Raises:
        RuntimeError: si aucun moteur OCR n'est disponible ou si aucun texte
                      n'a pu être extrait de l'image.
    """
    if moteurs is None:
        moteurs = charger_moteurs(verbose=verbose)

    extraire_texte         = moteurs.get("extraire_texte")
    extraire_texte_easyocr = moteurs.get("extraire_texte_easyocr")
    extract_info           = moteurs.get("extract_info")

    if extraire_texte is None and extraire_texte_easyocr is None:
        raise RuntimeError("Aucun moteur OCR disponible. Vérifiez ocr.py et ocr_easy.py.")

    # ------------------------------------------------------------------
    # Exécution des moteurs OCR
    # ------------------------------------------------------------------
    texte_tesseract = ""
    texte_easyocr   = ""

    if extraire_texte is not None:
        try:
            texte_tesseract = extraire_texte(source)
        except Exception as exc:
            if verbose:
                print(f"[INFO] Tesseract a échoué : {exc}")

    if extraire_texte_easyocr is not None:
        try:
            texte_easyocr = extraire_texte_easyocr(source)
        except Exception as exc:
            if verbose:
                print(f"[INFO] EasyOCR a échoué : {exc}")

    if not texte_tesseract and not texte_easyocr:
        raise RuntimeError("Aucun texte extrait. Vérifiez l'image ou les moteurs OCR.")

    # ------------------------------------------------------------------
    # Fusion et sélection du meilleur résultat
    # ------------------------------------------------------------------
    texte_final, source_ocr = selectionner_meilleur_resultat(texte_tesseract, texte_easyocr)

    # ------------------------------------------------------------------
    # Extraction des informations du document
    # ------------------------------------------------------------------
    type_doc   = None
    numero_doc = None

    if extract_info is not None and texte_final:
        try:
            info       = extract_info(texte_final)
            type_doc   = info.get("type")
            numero_doc = info.get("numero")
        except Exception as exc:
            if verbose:
                print(f"[INFO] Extraction document a échoué : {exc}")

    # ------------------------------------------------------------------
    # Construction du résultat
    # ------------------------------------------------------------------
    nom_fichier = Path(source).name if not str(source).startswith("http") else source

    stats_tess    = score_texte(texte_tesseract)
    stats_easyocr = score_texte(texte_easyocr)

    resultat = {
        "fichier_source":   nom_fichier,
        "source_ocr":       source_ocr,
        "type_document":    type_doc    or "Non détecté",
        "numero_document":  numero_doc  or "Non détecté",
        "texte_ocr":        texte_final,
        "stats": {
            "tesseract_caracteres": stats_tess[0],
            "tesseract_lignes":     stats_tess[1],
            "easyocr_caracteres":   stats_easyocr[0],
            "easyocr_lignes":       stats_easyocr[1],
        }
    }

    if verbose:
        print("\n--- Résumé OCR ---")
        print(f"  Fichier         : {nom_fichier}")
        print(f"  Source OCR      : {source_ocr}")
        print(f"  Tesseract       : {stats_tess[0]} car. / {stats_tess[1]} lignes")
        print(f"  EasyOCR         : {stats_easyocr[0]} car. / {stats_easyocr[1]} lignes")
        print(f"  Type document   : {type_doc   or 'Non détecté'}")
        print(f"  Numéro document : {numero_doc or 'Non détecté'}")

    return resultat


# ---------------------------------------------------------------------------
# Point d'entrée CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline OCR — combine Tesseract + EasyOCR et exporte en JSON."
    )
    parser.add_argument("source",   help="Chemin local ou URL de l'image.")
    parser.add_argument("--output", "-o", default="resultat.json",
                        help="Chemin du fichier JSON de sortie (défaut : resultat.json).")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Affiche un résumé détaillé dans la console.")
    args = parser.parse_args()

    output_path = Path(args.output)

    try:
        resultat = traiter_image(args.source, verbose=args.verbose)
    except RuntimeError as exc:
        sys.exit(f"[ERREUR] {exc}")

    sauvegarder_json(output_path, resultat)


if __name__ == "__main__":
    main()