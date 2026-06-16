#!/usr/bin/env python3
"""
ocr.py
======
Moteur OCR Tesseract — extrait le texte visible d'une image.

PRÉREQUIS
---------
1. Installer Tesseract-OCR (exécutable) :
     https://github.com/UB-Mannheim/tesseract/wiki
     → Télécharger et installer "tesseract-ocr-w64-setup-*.exe" (Windows 64 bits)
     → Cocher les langues "French" et "English" pendant l'installation


3. Installer les dépendances Python :
     pip install pytesseract Pillow requests

USAGE
-----
  python ocr.py <chemin_ou_url>

  Exemples :
    python ocr.py facture.png
    python ocr.py https://example.com/image.jpg
"""

import sys
from image_utils import charger_image, ameliorer_visibilite

# ⚠️  CHEMIN À METTRE À JOUR selon votre installation de Tesseract
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

try:
    import pytesseract as pt
    pt.pytesseract.tesseract_cmd = TESSERACT_PATH
except ImportError:
    pt = None


def extraire_texte(source: str) -> str:
    """
    Extrait le texte d'une image (fichier local ou URL) via Tesseract.

    Args:
        source: chemin local ou URL de l'image

    Returns:
        Texte extrait (chaîne vide si rien détecté ou si Tesseract absent)
    """
    if pt is None:
        raise ModuleNotFoundError("pytesseract n'est pas installé. Lancez : pip install pytesseract")

    image = charger_image(source)
    image = ameliorer_visibilite(image)
    texte = pt.image_to_string(image, lang="fra+eng")
    return texte.replace("\x0c", "").strip()


# ---------------------------------------------------------------------------
# Exécution directe (test standalone)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python ocr.py <chemin_ou_url>")
        sys.exit(1)

    try:
        texte = extraire_texte(sys.argv[1])
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
