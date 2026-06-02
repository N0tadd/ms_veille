"""
Veille marches-securises — Notifications Discord
By N0tad
"""

import requests
import re
import sys
import json
import os
import gc
import schedule
import time

# ─── CONFIG ───────────────────────────────────────────────────────────────────

LOG_FILE         = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms_log.txt")
DISCORD_WEBHOOK  = "https://discord.com/api/webhooks/1496848388006875246/BqTBCA7nBDJPXh59Lq6gjvn_H057YoKkJl22M_hp1KmcTgbiwvfipKdGPFIqcARVeY2p"   # ← à remplir
FICHIER_VUS      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms_vus.json")

URL = (
    "https://www.marches-securises.fr/entreprise/"
    "?module=liste_consultations"
    "&presta=%3Btravaux%3Bautres" # A personnaliser
    "&r=cloison%2C+plafond%2C+doublage%2C+isolation%2C+menuiserie" # A personnaliser
    "&date_cloture_type=0" # A personnaliser
    "&liste_dept=44%3B49%3B85%3B79%3B56%3B35%3B53%3B86%3B37%3B72" # A personnaliser
)

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ─── LOGS ─────────────────────────────────────────────────────────────────────

class Logger:
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

sys.stdout = Logger(LOG_FILE)

# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def recuperer_avis():
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get("https://www.marches-securises.fr/entreprise/", timeout=15)
        r = session.get(URL, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[ERREUR] Requête : {e}")
        return []

    blocs = re.split(r'(?=class="tr_pa tr_icone")', r.text)

    def nettoyer(m):
        if not m:
            return "—"
        return re.sub(r'\s+', ' ', m.group(1)).strip()

    avis = []
    for bloc in blocs:
        cle = re.search(r'cle_dce=([a-z0-9]+)&(?:amp;)?version=QR', bloc)
        if not cle:
            continue
        acheteur  = re.search(r'tr_icone">\s*<td[^>]*>(.*?)<!--', bloc, re.DOTALL)
        objet     = re.search(r'class="objet">.*?<div[^>]*>(.*?)</div>', bloc, re.DOTALL)
        dept      = re.search(r'tr_dept[\s\S]*?<td colspan="4">(.*?)</td>', bloc)
        date_clot = re.search(r'class="td_clot_date">(.*?)</td>', bloc, re.DOTALL)
        reference = re.search(r'tr_identifiant[\s\S]*?<th colspan="4">(.*?)</th>', bloc)

        avis.append({
            "cle_dce":   cle.group(1),
            "acheteur":  nettoyer(acheteur),
            "objet":     nettoyer(objet),
            "dept":      nettoyer(dept),
            "date_clot": nettoyer(date_clot),
            "reference": nettoyer(reference),
        })

    return avis

# ─── STOCKAGE ─────────────────────────────────────────────────────────────────

def charger_vus() -> set:
    if not os.path.exists(FICHIER_VUS):
        return set()
    try:
        with open(FICHIER_VUS, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, ValueError):
        print("[WARN] ms_vus.json corrompu, réinitialisation")
        return set()

def sauvegarder_vus(vus: set):
    with open(FICHIER_VUS, "w", encoding="utf-8") as f:
        json.dump(list(vus), f, indent=2)

# ─── DISCORD ──────────────────────────────────────────────────────────────────

def envoyer_discord(a: dict):
    lien = f"https://www.marches-securises.fr/entreprise/?module=consultation|details&cle_dce={a['cle_dce']}&version=QR"
    message = {
        "embeds": [{
            "title":       f"📢 Nouvel AO — {a['dept']}",
            "description": f"**{a['objet']}**",
            "color":       0xCCCC00,
            "url":         lien,
            "fields": [
                {"name": "🏢 Acheteur",    "value": a["acheteur"],  "inline": True},
                {"name": "🔖 Référence",   "value": a["reference"], "inline": True},
                {"name": "⏳ Clôture",     "value": a["date_clot"], "inline": True},
            ],
            "footer": {"text": f"marches-securises.fr — cle_dce : {a['cle_dce']}"},
        }]
    }
    try:
        r = requests.post(DISCORD_WEBHOOK, json=message, timeout=10)
        r.raise_for_status()
        print(f"[DISCORD] Envoyé : {a['cle_dce']} — {a['objet'][:60]}")
    except Exception as e:
        print(f"[ERREUR] Discord ({a['cle_dce']}) : {e}")

# ─── BOUCLE PRINCIPALE ────────────────────────────────────────────────────────

def verifier():
    try:
        print(f"[CHECK] {time.strftime('%H:%M:%S')} — Vérification en cours...")

        vus      = charger_vus()
        avis     = recuperer_avis()
        nouveaux = [a for a in avis if a["cle_dce"] not in vus]

        if not nouveaux:
            print("[CHECK] Aucun nouvel avis.")
            return

        print(f"[CHECK] {len(nouveaux)} nouvel(s) avis trouvé(s) !")
        for a in nouveaux:
            envoyer_discord(a)
            vus.add(a["cle_dce"])
            time.sleep(1)

        sauvegarder_vus(vus)

    except Exception as e:
        print(f"[ERREUR CRITIQUE] verifier() : {e}")
        import traceback; traceback.print_exc()
    finally:
        gc.collect()

# ─── LANCEMENT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Veille marches-securises.fr démarrée — vérification toutes les 15 minutes")
    print(f"   Webhook : {DISCORD_WEBHOOK[:50]}...")
    print()

    verifier()

    schedule.every(15).minutes.do(verifier)

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print(f"[ERREUR] Boucle principale : {e}")
        time.sleep(30)
