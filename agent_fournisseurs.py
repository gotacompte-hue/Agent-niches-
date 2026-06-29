"""
Agent de recherche de fournisseurs CJ Dropshipping
---------------------------------------------------
Version 4 : integre les criteres precises par Romain.
1. Pas de filtre prix dur (budget = peu importe), mais ajout d'une verification
   du pays de stock par produit (pour juger soi-meme la rapidite de livraison,
   sans risquer de vider les resultats avec un filtre trop strict).
2. Mots-cles etendus pour couvrir toute la structure de page prevue (stickers,
   papier peint, personnalisation, coussins, linge de lit, tapis, lampe) et
   plus de produits affiches par mot-cle, pour avoir de la variete.
3. Ajout du type de gestion logistique (productType) traduit en clair : qui
   gere reellement l'expedition quand il y a une vente (CJ directement, un
   fournisseur partenaire, ou le fournisseur en direct - a verifier).
4. Ajout de la certification CE si CJ la fournit (utile pour produits enfant).

Auteur: genere par Claude pour Romain
"""

import os
import time
import requests
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "METS_TON_TOKEN_ICI")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "METS_TON_CHAT_ID_ICI")
CJ_API_KEY = os.environ.get("CJ_API_KEY", "METS_TA_CLE_CJ_ICI")

# Mots-cles courts (2 mots max), le terme le plus distinctif en premier.
# Couvre toute la structure de page prevue : stickers, papier peint,
# personnalisation, coussins, linge de lit, tapis, lampe.
MOTS_CLES_PRODUITS = [
    "unicorn sticker",
    "unicorn wallpaper",
    "personalized sticker",
    "custom decal",
    "unicorn pillow",
    "unicorn bedding",
    "unicorn rug",
    "unicorn lamp",
]

NB_PRODUITS_BRUTS = 30        # nombre recupere depuis l'API avant filtrage
NB_PRODUITS_AFFICHES = 6      # nombre garde apres filtrage, par mot-cle
BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"

# Traduction du type logistique CJ en explication claire pour Romain
LABELS_LOGISTIQUE = {
    "ORDINARY_PRODUCT": "Gere et expedie par CJ directement (automatique)",
    "SUPPLIER_PRODUCT": "Gere par un fournisseur partenaire CJ (automatise via CJ)",
    "SUPPLIER_SHIPPED_PRODUCT": "Expedie directement par le fournisseur (a verifier, moins garanti)",
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


def filtrer_pertinents(produits, mot_cle, n=NB_PRODUITS_AFFICHES):
    mot_principal = mot_cle.split()[0].lower()
    pertinents = [p for p in produits if mot_principal in p.get("nameEn", "").lower()]
    return pertinents[:n]


def verifier_pays_stock(token, pid):
    """Renvoie la liste des pays ou le produit a vraiment du stock (>0),
    pour juger la rapidite de livraison potentielle."""
    url = f"{BASE_URL}/product/stock/getInventoryByPid"
    headers = {"CJ-Access-Token": token}
    params = {"pid": pid}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        if not data.get("success") and not data.get("result"):
            return []
        inventaires = data.get("data", {}).get("inventories", [])
        pays = [
            inv.get("countryCode")
            for inv in inventaires
            if inv.get("totalInventoryNum", 0) > 0 and inv.get("countryCode")
        ]
        return list(dict.fromkeys(pays))  # supprime les doublons, garde l'ordre
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
    logistique = LABELS_LOGISTIQUE.get(p.get("productType"), "Type non precise")

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

    for mot_cle in MOTS_CLES_PRODUITS:
        print(f"Recherche : {mot_cle}")
        produits_bruts = rechercher_produits(token, mot_cle)
        produits = filtrer_pertinents(produits_bruts, mot_cle)
        lignes.append(f"\n— *{mot_cle}* —")

        if not produits:
            lignes.append("Aucun produit pertinent trouve (a verifier a la main sur AliExpress).")
        else:
            for p in produits:
                pid = p.get("id")
                pays_stock = verifier_pays_stock(token, pid) if pid else []
                lignes.append(formater_produit(p, pays_stock))
                time.sleep(1)

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
