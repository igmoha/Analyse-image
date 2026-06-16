#!/usr/bin/env python3
"""
ocr_easy.py
===========
Moteur OCR EasyOCR — extrait le texte visible d'une image.

PRÉREQUIS
---------
1. Installer les dépendances Python :
     pip install easyocr numpy Pillow requests

   EasyOCR télécharge automatiquement ses modèles de langue
   lors de la première utilisation (connexion internet nécessaire).
   Les modèles sont mis en cache dans : C:/Users/<Utilisateur>/.EasyOCR/

2. GPU (optionnel) :
   Par défaut EasyOCR tourne sur CPU (gpu=False).
   Pour activer le GPU : installer PyTorch avec CUDA depuis https://pytorch.org/
   puis passer gpu=True dans Reader(...).

USAGE
-----
  python ocr_easy.py <chemin_ou_url>

  Exemples :
    python ocr_easy.py facture.png
    python ocr_easy.py https://example.com/image.jpg
"""

import sys
import numpy as np
from image_utils import charger_image, ameliorer_visibilite

try:
    import easyocr
except ImportError:
    easyocr = None


def extraire_texte_easyocr(source: str, langues: tuple[str, ...] = ("fr", "en")) -> str:
    """
    Extrait le texte d'une image via EasyOCR.
    Tente des rotations (90°, 180°, 270°) si aucun texte n'est détecté.

    Args:
        source:  chemin local ou URL de l'image
        langues: tuple de codes langue EasyOCR (défaut : français + anglais)

    Returns:
        Texte extrait (chaîne vide si rien détecté ou si EasyOCR absent)
    """
    if easyocr is None:
        raise ModuleNotFoundError("easyocr n'est pas installé. Lancez : pip install easyocr")

    image = charger_image(source)
    image = ameliorer_visibilite(image)

    reader = easyocr.Reader(list(langues), gpu=False)
    resultats = reader.readtext(np.array(image), detail=0, paragraph=True)

    # Essai de rotations si aucun texte n'est détecté
    if not resultats:
        for angle in (90, 180, 270):
            image_tournee = image.rotate(angle, expand=True, fillcolor=255)
            resultats = reader.readtext(np.array(image_tournee), detail=0, paragraph=True)
            if resultats:
                print(f"[INFO] Texte détecté après rotation de {angle}°.")
                break

    return "\n".join(resultats).strip()


# ---------------------------------------------------------------------------
# Exécution directe (test standalone)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python ocr_easy.py <chemin_ou_url>")
        sys.exit(1)

    try:
        texte = extraire_texte_easyocr(sys.argv[1])
        if texte:
            print(texte)
        else:
            print("Aucun texte détecté dans l'image.")
    except FileNotFoundError:
        print(f"Erreur : fichier introuvable — {sys.argv[1]}")
        sys.exit(1)
    except Exception as e:
        print(f"Erreur : {e}")
        sys.exit(1)