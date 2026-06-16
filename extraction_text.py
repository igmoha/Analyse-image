"""
extract_document_info.py
Extrait le type de document et son numéro depuis un fichier texte.

Types supportés :
  - Bon de livraison  → numéro : 7 chiffres
  - Facture           → numéro : 7 chiffres
  - Facture d'avoir   → numéro : FAC + 7 chiffres

Usage :
  python extract_document_info.py <fichier.txt>
"""

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Patterns de détection
# ---------------------------------------------------------------------------

# Types de documents (ordre important : "facture d'avoir" avant "facture")
DOCUMENT_TYPES = [
    {
        "label":   "Facture d'avoir",
        "pattern": r"facture\s+d['\u2019]avoir",          # facture d'avoir / facture d'avoir
        "num_pattern": r"FAC\d{7}",                        # FAC + 7 chiffres
    },
    {
        "label":   "Facture",
        "pattern": r"facture(?!\s+d['\u2019]avoir)",       # facture (pas suivi de d'avoir)
        "num_pattern": r"\d{7}",                           # 7 chiffres
    },
    {
        "label":   "Bon de livraison",
        "pattern": r"bon\s+de\s+livraison",
        "num_pattern": r"\d{7}",                           # 7 chiffres
    },
]


def extract_info(text: str) -> dict:
    """
    Parcourt le texte à la recherche du premier type de document connu,
    puis cherche le numéro correspondant dans le texte qui suit.

    Retourne un dict :
      {
        "type":   str | None,
        "numero": str | None,
        "position": int | None   # index de début du type dans le texte
      }
    """
    text_lower = text.lower()

    best_match = None  # (start_index, doc_type_dict)

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

    # Chercher le numéro dans la partie qui suit
    num_match = re.search(doc_type["num_pattern"], text_after)

    numero = num_match.group(0) if num_match else None

    return {
        "type":     doc_type["label"],
        "numero":   numero,
        "position": start_idx,
    }


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
        print("  ❌ Aucun type de document reconnu dans ce fichier.")
    else:
        print(f"  Type     : {result['type']}")
        print(f"  Numéro   : {result['numero'] if result['numero'] else '❌ Non trouvé'}")

    print("=" * 50)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python extract_document_info.py <fichier.txt>")
        sys.exit(1)

    process_file(sys.argv[1])