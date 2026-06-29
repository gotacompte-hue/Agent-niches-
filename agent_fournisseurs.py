"""
Agent de recherche de fournisseurs CJ Dropshipping
---------------------------------------------------
Version 6 : ajoute un diagnostic decisif. Sur le rapport precedent, "unicorn"
+ n'importe quel second mot donnait 0 resultat partout (stickers, papier
peint, coussin, linge de lit, tapis, lampe) alors que d'autres mots generiques
fonctionnaient bien -> on teste maintenant "unicorn" SEUL, sans filtre, pour
savoir si CJ a vraiment quasi rien sous ce terme ou si un second mot
quelconque casse la recherche. Renomme aussi la categorie "Stickers
personnalises" pour clarifier qu'elle n'a rien a voir avec les licornes
(generique personnalisation/prenom uniquement).

Auteur: genere par Claude pour Romain
"""

import os
import time
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TON_CHAT_ID_ICI")
CJ_API_KEY = os.environ.get("CJ_API_KEY", "METS_TA_CLE_CJ_ICI")

CONCEPTS = [
    {
        "label": "Stickers muraux licorne",
        "requetes": ["unicorn wall sticker", "unicorn decal", "rainbow unicorn sticker"],
        "mots_validation": ["unicorn"],
    },
    {
        "label": "Papier peint licorne",
        "requetes": ["unicorn wallpaper", "unicorn wall mural", "rainbow mural"],
        "mots_validation": ["unicorn", "mural"],
    },
    {
        "label": "Stickers personnalises - generique (PAS specifique licorne)",
        "requetes": ["custom name sticker", "personalized name decal", "name sticker kids"],
        "mots_validation": ["sticker", "decal", "label"],
    },
    {
        "label": "Coussin licorne",
        "requetes": ["unicorn pillow", "unicorn cushion"],
        "mots_validation": ["unicorn"],
    },
    {
        "label": "Linge de lit licorne",
        "requetes": ["unicorn bedding", "unicorn duvet", "unicorn blanket"],
        "mots_validation": ["unicorn"],
    },
    {
        "label": "Tapis licorne",
        "requetes": ["unicorn rug", "unicorn carpet"],
        "mots_validation": ["unicorn"],
    },
    {
        "label": "Lampe licorne",
        "requetes": ["unicorn night light", "unicorn led lamp", "unicorn lamp"],
        "mots_validation": ["unicorn"],
    },
]

NB_PRODUITS_BRUTS = 20
NB_PRODUITS_AFFICHES = 5
BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"

LABELS_LOGISTIQUE = {
    "0": "Gere et expedie par CJ directement (automatique)",
    "1": "Produit de service (stockage CJ)",
    "3": "Produit d'emballage (non vendable seul)",
    "4": "Gere par un fournisseur partenaire CJ (automatise via CJ)",
    "5": "Expedie directement par le fournisseur (a verifier, moins garanti)",
}


def get_access_token():
    url = f"{BASE_URL}/authentication/getAccessToken"
    payload = {"apiKey": CJ_API_KEY}
    r = requests.post(url, json=payload, timeout=10)
    data = r.json()
    if not data.get("result"):
        raise Exception(f"Echec authentification CJ : {data.get('message')}")
    return data["data"]["accessToken"]


def rechercher_produits(token, mot_cle, taille=NB_PRODUITS_BRUTS):
    url = f"{BASE_URL}/product/listV2"
    headers = {"CJ-Access-Token": token}
    params = {"keyWord": mot_cle, "page": 1, "size": taille}
    r = requests.get(url, headers=headers, params=params, timeout=10)
    data = r.json()
    if not data.get("result"):
        print(f"Erreur recherche '{mot_cle}' : {data.get('message')}")
        return []
    contenu = data.get("data", {}).get("content", [])
    if not contenu:
        return []
    return contenu[0].get("productList", [])


def diagnostic_unicorn_seul(token):
    """Test decisif : 'unicorn' tout seul, sans filtre. Si ca renvoie plein
    de resultats, le probleme vient du second mot associe. Si ca renvoie
    quasi rien, CJ n'a simplement pas ce theme en profondeur."""
    print("DIAGNOSTIC : recherche 'unicorn' seul, sans filtre...")
    bruts = rechercher_produits(token, "unicorn", taille=20)
    print(f"  -> {len(bruts)} resultats bruts pour 'unicorn' seul")
    exemples = [p.get("nameEn", "?") for p in bruts[:5]]
    for ex in exemples:
        print(f"     - {ex}")
    return bruts


def filtrer_pertinents(produits, mots_validation, n=NB_PRODUITS_AFFICHES):
    pertinents = [
        p for p in produits
        if any(mot.lower() in p.get("nameEn", "").lower() for mot in mots_validation)
    ]
    return pertinents[:n]


def chercher_concept(token, concept):
    for requete in concept["requetes"]:
        print(f"  Essai requete : {requete}")
        bruts = rechercher_produits(token, requete)
        print(f"    -> {len(bruts)} resultats bruts avant filtrage")
        pertinents = filtrer_pertinents(bruts, concept["mots_validation"])
        time.sleep(1)
        if pertinents:
            return pertinents, requete
    return [], None


def verifier_pays_stock(token, pid):
    url = f"{BASE_URL}/product/stock/getInventoryByPid"
    headers = {"CJ-Access-Token": token}
    params = {"pid": pid}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        inventaires = data.get("data", {}).get("inventories", [])
        pays = [
            inv.get("countryCode")
            for inv in inventaires
            if inv.get("totalInventoryNum", 0) > 0 and inv.get("countryCode")
        ]
        return list(dict.fromkeys(pays))
    except Exception as e:
        print(f"Erreur verification stock pour {pid} : {e}")
        return []


def formater_produit(p, pays_stock):
    nom = p.get("nameEn", "Produit sans nom")
    prix = p.get("sellPrice", "?")
    prix_promo = p.get("discountPrice")
    nb_listings = p.get("listedNum", 0)
    personnalisable = "Oui" if p.get("isPersonalized") == 1 else "Non"
    certif_ce = "Oui" if p.get("hasCECertification") == 1 else "Non"
    logistique = LABELS_LOGISTIQUE.get(str(p.get("productType")), "Type non precise")

    ligne_prix = f"{prix}$"
    if prix_promo and str(prix_promo) != str(prix):
        ligne_prix += f" (promo: {prix_promo}$)"

    ligne_stock = ", ".join(pays_stock) if pays_stock else "non precise"

    return (
        f"*{nom}*\n"
        f"   Prix : {ligne_prix}\n"
        f"   Stock dispo : {ligne_stock} | Personnalisable : {personnalisable} | CE : {certif_ce}\n"
        f"   Deja liste par {nb_listings} boutique(s)\n"
        f"   Expedition : {logistique}"
    )


def construire_rapport():
    token = get_access_token()
    date_str = datetime.now().strftime("%d/%m/%Y")
    lignes = [f"*Rapport fournisseurs CJ du {date_str}*\n"]

    diag = diagnostic_unicorn_seul(token)
    lignes.append(f"_Diagnostic : 'unicorn' seul (sans filtre) = {len(diag)} resultat(s) bruts chez CJ._\n")

    for concept in CONCEPTS:
        print(f"Concept : {concept['label']}")
        produits, requete_gagnante = chercher_concept(token, concept)
        lignes.append(f"\n— *{concept['label']}* —")

        if not produits:
            essais = ", ".join(concept["requetes"])
            lignes.append(f"Rien trouve malgre {len(concept['requetes'])} formulations testees ({essais}).")
            continue

        lignes.append(f"_(trouve via : \"{requete_gagnante}\")_")
        for p in produits:
            pid = p.get("id")
            pays_stock = verifier_pays_stock(token, pid) if pid else []
            lignes.append(formater_produit(p, pays_stock))
            time.sleep(1)

    return "\n".join(lignes)


def envoyer_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    morceaux = [message[i:i + 3500] for i in range(0, len(message), 3500)]
    for morceau in morceaux:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": morceau, "parse_mode": "Markdown"}
        r = requests.post(url, data=payload)
        if r.status_code != 200:
            print(f"Erreur envoi Telegram : {r.text}")
        time.sleep(1)


def main():
    rapport = construire_rapport()
    print("\n--- Rapport ---\n" + rapport)
    envoyer_telegram(rapport)


if __name__ == "__main__":
    main()
