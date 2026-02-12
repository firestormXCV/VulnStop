import time
import json
import os
import requests
from zapv2 import ZAPv2
from datetime import datetime
from modules.utils import get_clean_filename_from_url
from dotenv import load_dotenv

load_dotenv() # This pulls the variables from your .env file into os.environ

ZAP_API_KEY = os.getenv("ZAP_API_KEY")
#ZAP_PROXY_URL = os.getenv("ZAP_PROXY") # This is "http://localhost:8080"
ZAP_PROXY_URL = os.getenv("ZAP_PROXY")
# ZAPv2 expects a dictionary for the proxies parameter
proxies = {
    'http': ZAP_PROXY_URL,
    'https': ZAP_PROXY_URL
}

# Récupération des variables d'env ici ou via config
ZAP_API_KEY = os.getenv("ZAP_API_KEY")
ZAP_PORT = '8080'
zap_url_env = os.getenv("ZAP_PROXY")

ZAP_PROXY = {
    "http": zap_url_env,
    "https": zap_url_env
}

def clean_alert_data(alert):
    """Fonction helper pour nettoyer une alerte brute ZAP et extraire les liens"""
    
    # 1. Extraction des liens depuis les TAGS
    tags = alert.get("tags", {})
    extracted_links = []
    
    # On parcourt les tags (ex: "OWASP_2021_A01": "https://...")
    for key, value in tags.items():
        if isinstance(value, str) and value.startswith("http"):
            extracted_links.append(value)
            
    # 2. Extraction depuis le champ REFERENCE (souvent présent aussi)
    refs = alert.get("reference", "")
    if refs.startswith("http") and refs not in extracted_links:
        extracted_links.append(refs)

    return {
        "title": alert.get("alert", "Inconnu"),
        "risk": alert.get("risk", "Inconnu"),
        "description": alert.get("description", "")[:500],
        "solution": alert.get("solution", ""),
        "urls": [], # Sera rempli par la boucle principale
        "reference_links": extracted_links # Liens utiles extraits
    }
# --- FONCTION PRINCIPALE ---
def run_zap_scan(target_url, max_threads, active_scan, progress_callback=None):
    if "#" in target_url:
        print(f"⚠️ URL avec fragment (#) détectée. Nettoyage : {target_url} -> {target_url.split('#')[0]}")
        target_url = target_url.split("#")[0]
    
    # On retire le slash final pour éviter les problèmes de matching strict
    target_url = target_url.rstrip('/')
    
    RISK_WEIGHT = {"High": 0, "Medium": 1, "Low": 2, "Informational": 3}
    print(f"🔌 Tentative de connexion à ZAP sur le port {ZAP_PORT}...")
    zap = ZAPv2(apikey=ZAP_API_KEY, proxies=ZAP_PROXY)    
    # 1. Vérification connexion
    
    try:
        zap.core.version
        print("✅ Connecté à ZAP !")
        print(f"Connected to ZAP version: {zap.core.version}")
    except Exception as e:
        print(f"Failed to connect to ZAP. Check if ZAP is running on {ZAP_PROXY_URL}")
        print(f"Error: {e}")
        error_msg = f"ERREUR CRITIQUE: ZAP n'est pas accessible sur {ZAP_PORT}. Lancez ZAP d'abord."
        print(error_msg,e)
        return json.dumps({"error": error_msg})

    # Réinitialisation
    zap.core.new_session(name=f"Session_{int(time.time())}", overwrite=True)
    
    # --- CONFIGURATION DYNAMIQUE ---

    zap.ascan.set_option_thread_per_host(max_threads)
    zap.spider.set_option_thread_count(max_threads)
    
    # Si très lent, on augmente le timeout réseau de ZAP
    if max_threads <= 3:
        zap.core.set_option_timeout_in_secs(20)
    # On définit une regex pour exclure les fichiers statiques lourds
    regex_exclusion = ".*\\.(gif|jpg|jpeg|png|ico|css|woff|woff2)$"
    zap.spider.exclude_from_scan(regex_exclusion)
    zap.ascan.exclude_from_scan(regex_exclusion)
    # --- 1. SPIDER ---
    print(f"🕷️ Spider sur {target_url}...")
    scan_id = zap.spider.scan(target_url)
    while int(zap.spider.status(scan_id)) < 100:
        if progress_callback:
            if not progress_callback(int(zap.spider.status(scan_id)), "🕷️ Exploration (Spider)"):
                zap.spider.stop(scan_id); return json.dumps({"error": "Stop user"})
        time.sleep(1)
    
    # --- 2. ACTIVE SCAN ---
    if active_scan:
        print(f"⚡ Active Scan (Récursif)...")
        scan_id = zap.ascan.scan(target_url, recurse=True)
        time.sleep(2)
        
        consecutive_errors = 0
        max_retries = 10 # On autorise 10 échecs de connexion avant d'abandonner

        while True:
            try:
                # TENTATIVE DE CONNEXION
                status = zap.ascan.status(scan_id)
                
                # Si on arrive ici, la connexion a réussi : on reset le compteur d'erreurs
                consecutive_errors = 0
                
                # PROTECTION ANTI-CRASH (Données invalides renvoyées par ZAP)
                if not str(status).isdigit():
                    if status == "does_not_exist":
                        print("✅ Active Scan terminé (ID plus actif).")
                    else:
                        print(f"⚠️ Statut Active Scan inconnu : {status}")
                    break
                    
                # Si c'est un nombre, on continue normalement
                status_int = int(status)
                
                if progress_callback:
                    if not progress_callback(status_int, "⚡ Attaque (Active Scan)"):
                        zap.ascan.stop(scan_id)
                        return json.dumps({"error": "Scan stoppé par l'utilisateur."})
                
                if status_int >= 100:
                    break
                
                # Pause normale entre deux vérifications
                time.sleep(2)

            # GESTION DES ERREURS DE CONNEXION (WinError 10048 / ProxyError)
            except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError) as e:
                consecutive_errors += 1
                print(f"⚠️ ZAP ne répond pas (Tentative {consecutive_errors}/{max_retries}). Le réseau est saturé.")
                
                # PAUSE D'URGENCE : On attend 5 secondes pour laisser Windows libérer les sockets
                time.sleep(5)
                
                if consecutive_errors >= max_retries:
                    print("❌ ERREUR CRITIQUE : ZAP est injoignable après plusieurs tentatives.")
                    break
                    
            except Exception as e:
                print(f"⚠️ Erreur inattendue dans la boucle Active Scan : {e}")
                break
    else:
        print("ℹ️ Active Scan SKIPPÉ (Mode Passif).")

    # --- 3. RÉCUPÉRATION DES ALERTES (AVEC RETRIES) ---
    print("📝 Récupération des alertes...")
    
    all_alerts_raw = []
    start_index = 0
    batch_size = 5000  # On récupère 5000 alertes par appel (taille raisonnable)
    
    # Optimisation cruciale : On demande à ZAP de filtrer l'URL lui-même !
    # Cela évite de récupérer les alertes d'autres sites polluants.
    target_base = target_url.rstrip('/')
    
    while True:
        try:
            # Appel API avec pagination (start/count) et filtre (baseurl)
            # baseurl : ZAP ne renvoie que les alertes concernant cette cible
            batch = zap.core.alerts(
                baseurl=target_url, 
                start=start_index, 
                count=batch_size
            )
            
            # Gestion des formats bizarres (au cas où ZAP renvoie une string ou un dict vide)
            if not batch:
                break # Fin des données
                
            if isinstance(batch, str):
                # Parfois ZAP renvoie une string vide "" au lieu d'une liste
                break
                
            if isinstance(batch, dict) and "alerts" in batch:
                batch = batch["alerts"]
                
            if not isinstance(batch, list):
                print(f"⚠️ Format de lot inattendu (Type: {type(batch)}). Arrêt.")
                break
                
            # Si le lot est vide, on a fini
            if len(batch) == 0:
                break
                
            # Ajout au total
            all_alerts_raw.extend(batch)
            print(f"   📥 Reçu lot de {len(batch)} alertes (Total: {len(all_alerts_raw)})...")
            
            # On avance l'index pour le prochain tour
            start_index += batch_size
            
            # Si on a reçu moins que demandé, c'est que c'était le dernier lot
            if len(batch) < batch_size:
                break
                
        except Exception as e:
            print(f"❌ Erreur lors de la récupération du lot {start_index}: {e}")
            # En cas d'erreur réseau, on peut choisir d'arrêter ou de réessayer
            # Ici on arrête pour éviter une boucle infinie d'erreurs
            break

    # --- NETTOYAGE FINAL ---
    # Le filtrage 'startswith' est théoriquement inutile grâce à l'argument baseurl,
    # mais on le garde en double sécurité (ceinture et bretelles).
    raw_alerts = []
    
    for alert in all_alerts_raw:
        if isinstance(alert, dict):
            # Parfois l'URL dans l'alerte diffère légèrement du baseurl demandé
            if alert.get('url', '').startswith(target_base):
                raw_alerts.append(alert)
    
    # Si le filtre baseurl de ZAP a bien marché, raw_alerts == all_alerts_raw
    # Sinon, on garde juste celles validées.
    if not raw_alerts:
        raw_alerts = all_alerts_raw 

    print(f"✅ Récupération terminée : {len(raw_alerts)} alertes uniques récupérées.")
    # ... (Suite : Sauvegarde...)

    # --- 4. SAUVEGARDE DU JSON BRUT ( ---
   
    # 1. On génère un nom propre basé sur la racine (ex: demo_owasp_juice_shop)
    safe_root_name = get_clean_filename_from_url(target_url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  
    # --- 5. REGROUPEMENT POUR L'IA ---
    grouped_alerts = {}
    for alert in raw_alerts:
        title = alert.get("alert")
        risk = alert.get("risk")
        url = alert.get("url")
        key = f"{title}|{risk}"
        
        if key not in grouped_alerts:
            cleaned = clean_alert_data(alert)
            cleaned["urls"] = [url]
            cleaned["method"] = alert.get("method", "")
            cleaned["param"] = alert.get("param", "")
            grouped_alerts[key] = cleaned
        else:
            if url not in grouped_alerts[key]["urls"]:
                grouped_alerts[key]["urls"].append(url)

    # --- 6. FILTRAGE FINAL ---
    final_vulnerabilities_list = []
    
    # LISTE DES RISQUES ACCEPTÉS (Anglais + Français)
    VALID_RISKS = ["High", "Medium", "Low", "Informational", "Elevée", "Moyenne", "Faible", "Informative"]

    for key, data in grouped_alerts.items():
        # On vérifie si le risque est dans notre liste autorisée
        if data["risk"] not in VALID_RISKS: 
             continue 
            
        data["urls"] = sorted(data["urls"])[:15] 
        final_vulnerabilities_list.append(data)

    final_vulnerabilities_list.sort(key=lambda x: RISK_WEIGHT.get(x['risk'], 4))

    # --- 7. SORTIE JSON TRAITÉ ---
    final_output = {
        "scan_summary": {
            "target_url": target_url,
            "timestamp": timestamp,
            "total_alerts_found": len(raw_alerts),
            "unique_vulnerabilities": len(final_vulnerabilities_list),
            
        },
        "vulnerabilities": final_vulnerabilities_list
    }
    
    # On réutilise le même nom propre safe_root_name
    full_filename = f"zap_FULL_{safe_root_name}_{timestamp}.json"
    full_path = os.path.join("reports", full_filename)
    
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4, ensure_ascii=False)
        print(f"💾 Rapport FINAL sauvegardé : {full_path}")
    except Exception as e:
        print(f"❌ Erreur sauvegarde FINAL : {e}")

    return json.dumps(final_output, indent=2)
