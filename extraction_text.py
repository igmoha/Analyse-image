#!/usr/bin/env python3
"""
extraction_text.py
==================
Extrait le type de document et son numéro depuis un texte OCR.

Types supportés :
  - Facture d'avoir  → numéro : FAC + 7 chiffres  (ex: FAC1234567)
  - Facture          → numéro : 7 chiffres          (ex: 1234567)
  - Bon de livraison → numéro : 7 chiffres          (ex: 1234567)

Stratégie de recherche du numéro :
  1. On localise le mot "numéro" (ou variantes : "numero", "n°", "no.") dans le texte
     qui suit le type de document.
  2. On prend le premier numéro valide dans les 50 caractères après ce mot-clé.
  3. Si "numéro" est absent, on cherche directement le numéro dans les 150 caractères
     après le type (fallback).

⚠️  L'ordre dans DOCUMENT_TYPES est important :
    "Facture d'avoir" doit être listé AVANT "Facture"
    pour éviter qu'une facture d'avoir soit détectée comme simple facture.

PRÉREQUIS
---------
  Aucune dépendance externe — uniquement la bibliothèque standard Python (re, sys, pathlib).

USAGE (standalone)
------------------
  python extraction_text.py <fichier.txt>
"""

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration des types de documents
# ---------------------------------------------------------------------------

DOCUMENT_TYPES = [
    {
        "label":       "Facture d'avoir",
        # Détecte "facture d'avoir" ou "facture d'avoir" (apostrophe typographique '\u2019')
        "pattern":     r"facture\s+d['\u2019]avoir",
        # Format du numéro : FAC suivi de 7 chiffres (ex: FAC1234567)
        "num_pattern": r"FAC\d{7}",
    },
    {
        "label":       "Facture",
        # Détecte "facture" mais PAS suivi de "d'avoir" (lookahead négatif)
        "pattern":     r"facture(?!\s+d['\u2019]avoir)",
        # Format du numéro : exactement 7 chiffres ISOLÉS
        # (?<!\d) = pas de chiffre avant  |  (?!\d) = pas de chiffre après
        "num_pattern": r"(?<!\d)\d{7}(?!\d)",
    },
    {
        "label":       "Bon de livraison",
        "pattern":     r"bon\s+de\s+livraison",
        # Format du numéro : exactement 7 chiffres ISOLÉS
        "num_pattern": r"(?<!\d)\d{7}(?!\d)",
    },
]

# Mot-clé exact tel qu'il apparaît sur les documents
PATTERN_MOT_NUMERO = r"numéro"


# ---------------------------------------------------------------------------
# Fonction principale d'extraction
# ---------------------------------------------------------------------------

def extract_info(text: str) -> dict:
    """
    Identifie le premier type de document trouvé dans le texte,
    localise le mot "numéro" qui le suit, puis extrait le numéro
    dans les caractères qui suivent immédiatement ce mot-clé.

    Stratégie :
      1. Chercher le type de document dans le texte.
      2. Dans le texte après le type, chercher le mot "numéro" (ou variante).
      3. Chercher le numéro dans les 50 caractères après "numéro".
      4. Si "numéro" est absent → fallback : chercher dans les 150 car. après le type.

    Args:
        text: texte brut issu de l'OCR

    Returns:
        Dictionnaire avec :
          - "type"     (str | None) : label du type de document détecté
          - "numero"   (str | None) : numéro de document extrait
          - "position" (int | None) : index de début du type dans le texte
    """
    text_lower = text.lower()
    best_match = None  # (start_index, end_index, doc_type_dict)

    # Trouver la première occurrence de chaque type de document
    for doc in DOCUMENT_TYPES:
        for m in re.finditer(doc["pattern"], text_lower):
            if best_match is None or m.start() < best_match[0]:
                best_match = (m.start(), m.end(), doc)

    if best_match is None:
        return {"type": None, "numero": None, "position": None}

    start_idx, end_idx, doc_type = best_match

    # Texte situé après le type de document
    text_after = text[end_idx:]
    text_after_lower = text_after.lower()

    # --- Étape 1 : chercher le mot "numéro" après le type ---
    mot_numero = re.search(PATTERN_MOT_NUMERO, text_after_lower)

    if mot_numero:
        # --- Étape 2 : chercher le numéro juste après le mot "numéro" ---
        # On limite à 100 caractères après le mot-clé (espace, ":", séparateurs possibles)
        zone = text_after[mot_numero.end(): mot_numero.end() + 100]
        num_match = re.search(doc_type["num_pattern"], zone)
    else:
        # --- Fallback : pas de mot "numéro" trouvé, chercher dans les 100 car. suivants ---
        zone = text_after[:100]
        num_match = re.search(doc_type["num_pattern"], zone)

    return {
        "type":     doc_type["label"],
        "numero":   num_match.group(0) if num_match else None,
        "position": start_idx,
    }


# ---------------------------------------------------------------------------
# Exécution directe (test standalone)
# ---------------------------------------------------------------------------

def process_file(filepath: str) -> None:
    path = Path(filepath)

    if not path.exists():
        print(f"[ERREUR] Fichier introuvable : {filepath}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8", errors="replace")
    result = extract_info(text)

    print("=" * 50)
    print(f"  Fichier  : {path.name}")
    print("-" * 50)

    if result["type"] is None:
        print("  ❌ Aucun type de document reconnu.")
    else:
        print(f"  Type     : {result['type']}")
        print(f"  Numéro   : {result['numero'] if result['numero'] else '❌ Non trouvé'}")

    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python extraction_text.py <fichier.txt>")
        sys.exit(1)

    process_file(sys.argv[1])