import re
import time
import requests
from urllib.parse import urlparse
import os
import glob
import json
from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
from typing import List
from modules.agents import pdf_writer_agent, sme_risk_advisor ,audit_analyst,chat_assistant

def keep_only_latest_report(report_prefix):
    """
    Ne garde que le fichier le plus récent pour un préfixe donné (ex: 'zap_FULL_' ou 'semgrep_FULL_').
    """
    report_dir = "reports"
    if not os.path.exists(report_dir):
        return

    # On cherche tous les fichiers correspondant au pattern
    pattern = os.path.join(report_dir, f"{report_prefix}*.json")
    files = glob.glob(pattern)

    if len(files) < 2:
        return

    # On trie par date (le plus récent à la fin)
    files.sort(key=os.path.getmtime)

    # On garde le dernier, on supprime le reste
    # files[:-1] prend toute la liste SAUF le dernier élément
    for f in files[:-1]:
        try:
            os.remove(f)
            print(f"🧹 Ménage rapport obsolète : {f}")
        except Exception as e:
            print(f"⚠️ Erreur suppression {f}: {e}")
            
def get_latest_report_data():
    """Récupère le dernier fichier JSON de scan généré."""
    if not os.path.isdir("reports"): return None, None, None
    files = glob.glob(os.path.join("reports", 'zap_FULL_*.json'))
    if not files: return None, None, None
    latest = max(files, key=os.path.getctime)
    
    try:
        with open(latest, 'r', encoding='utf-8') as f: data = json.load(f)
    except Exception as e:
        print(f"Erreur lecture JSON: {e}")
        return None, None, None

    # Extraction URL sécurisée
    url = "Inconnue"
    if isinstance(data, list) and data: 
        url = data[0].get('url', 'Inconnue')
    elif isinstance(data, dict): 
        url = data.get('scan_summary', {}).get('target_url', 'Inconnue')
        
    return data, latest, url

def process_raw_alerts(raw_data, target_url, allowed_risks=["Critical", "High", "Medium", "Low", "Error", "Warning", "Info"]):
    """Filtre les vulnérabilités selon le risque choisi (High, Medium, etc.)."""
    if isinstance(raw_data, dict):
        vulnerabilities = raw_data.get('vulnerabilities', []) or raw_data.get('results') or []
    else:
        vulnerabilities = []

    if not vulnerabilities:
        return {"scan_summary": {"total_alerts_found": 0, "target_url": target_url}, "vulnerabilities": []}

    SEVERITY_TRANSLATION = {
        "CRITICAL": "Critical",
        "ERROR": "High",
        "HIGH": "High",
        "WARNING": "Medium",
        "MEDIUM": "Medium",
        "INFO": "Low",
        "LOW": "Low",
        "INFORMATIONAL": "Low"
    }
    RISK_WEIGHT = {
        "Critical": 0,
        "High": 1,
        "Medium": 2,
        "Low": 3
    }
    allowed_risks_normalized = {r.capitalize() for r in allowed_risks}
    filtered_alerts = []
    
    for alert in vulnerabilities:
        severity = (alert.get('risk') or alert.get('severity') or "Unknown").upper()
        normalized_severity = SEVERITY_TRANSLATION.get(severity, severity.capitalize())
        
        if normalized_severity in allowed_risks_normalized:
            alert['risk'] = normalized_severity
            if 'severity' in alert:
                alert['severity'] = normalized_severity
            filtered_alerts.append(alert)
    
    filtered_alerts.sort(key=lambda x: RISK_WEIGHT.get(x['risk'], 10))
        

    return {
        "scan_summary": {
            "total_raw_alerts": len(vulnerabilities),
            "critical_alerts_shown_to_ai": len(filtered_alerts),
            "target_url": target_url,
            "filter_applied": f"{allowed_risks}"
        },
        "vulnerabilities": filtered_alerts
    }

def split_list_into_chunks(lst, chunk_size):
    """Divise une liste en sous-listes."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def extract_url_from_text(text):
    """Trouve la première URL dans un message."""
    url_pattern = re.compile(r'(https?://[^\s]+)')
    match = url_pattern.search(text)
    return match.group(0) if match else None

def get_clean_filename_from_url(target_url):
    """
    Nettoie une URL pour en faire un nom de fichier sûr.
    Ex: 'https://demo.owasp-juice.shop/main.js?q=123' -> 'demo_owasp-juice_shop'
    """
    try:
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'http://' + target_url
        parsed = urlparse(target_url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        if ':' in domain: domain = domain.split(':')[0]
        clean_name = re.sub(r'[^a-zA-Z0-9\-]', '_', domain)
        return re.sub(r'_+', '_', clean_name).strip('_')
    except:
        return "unknown_target"

def check_and_calibrate_target(target_url):
    """Vérifie si le site est en ligne et calcule la vitesse."""
    print(f"🔎 Reconnaissance sur {target_url}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Calibration-Bot)'}
    response_times = []
    
    try:
        for _ in range(3):
            start = time.time()
            requests.get(target_url, headers=headers, timeout=5, verify=False)
            response_times.append(time.time() - start)
            
        avg_time = sum(response_times) / len(response_times)
        
        if avg_time < 0.4: threads = 25
        elif avg_time < 1.0: threads = 8
        else: threads = 3
        
        msg = f"Site EN LIGNE. Latence moy: {avg_time:.2f}s. Config ZAP : {threads} threads."
        return {"valid": True, "threads": threads, "message": msg}

    except requests.exceptions.ConnectionError:
        return {"valid": False, "threads": 0, "message": "❌ ÉCHEC : Impossible de se connecter au serveur."}
    except requests.exceptions.Timeout:
        return {"valid": False, "threads": 0, "message": "❌ ÉCHEC : Timeout (Serveur trop lent ou pare-feu)."}
    except Exception as e:
        # On est tolérant : si erreur bizarre, on renvoie True mais avec prudence (2 threads)
        return {"valid": True, "threads": 2, "message": f"⚠️ ATTENTION : Erreur technique ({str(e)}), mode prudent activé."}

def extract_code_and_text(text):
    """
    Sépare le code du texte.
    Optimisé pour Docker/YAML, Web (JS/HTML/PHP) et Code classique.
    """
    code_blocks = []
    text_content = text
    
    # --- ÉTAPE 1 : Détection Markdown explicite (```...```) ---
    markdown_pattern = r'```(?:[\w\+\-\.]+)?\s*(.*?)```'
    matches = re.findall(markdown_pattern, text, re.DOTALL)
    
    if matches:
        valid_blocks = [m.strip() for m in matches if m.strip()]
        if valid_blocks:
            code_blocks.extend(valid_blocks)
            full_block_pattern = r'```.*?```'
            text_content = re.sub(full_block_pattern, '\n[...CODE EXTRAIT...]\n', text, flags=re.DOTALL)
            return {
                "text_content": text_content.strip(),
                "code_blocks": code_blocks,
                "has_code": True
            }

    # --- ÉTAPE 2 : Heuristique "Scanner de Lignes" ---
    
    lines = text.split('\n')
    potential_code_block = []
    cleaned_text_lines = []
    
    code_indicators = [
        # --- 1. YAML / Docker Compose / Configs ---
        r'^\s*[\w\-\.\"\']+\s*:\s*(?:#.*)?$', 
        r'^\s*[\w\-\.\"\']+\s*:\s*[\w\-\.\"\'].*$',
        r'^\s*-\s+[\w\-\"\']+',

        # --- 2. Web (HTML / XML) ---
        # CORRECTION MAJEURE : Détection générique de balise <tag> ou </tag>
        # Capture <h1, <div, <table, </body, <img... sans avoir besoin de tout lister
        r'^\s*</?[a-zA-Z][\w:-]*[^>]*>', 
        r'/>\s*$', # Fin de balise auto-fermante

        # --- 3. CSS ---
        r'^\s*[.#]?[a-zA-Z0-9_-]+\s*\{\s*$',   
        r'^\s*[a-zA-Z-]+\s*:\s*[^;]+;\s*$', # Propriété CSS isolée (ex: "color: red;")
        
        # --- 4. JavaScript / TypeScript ---
        r'(function|const|let|var|import|export|class|async|await)\s+', 
        r'console\.(log|error|warn)', 
        r'\s*=>\s*',
        r'(document|window|localStorage|sessionStorage)\.',  
        r'\.get\(', # Appels génériques .get()
        
        # --- 5. PHP (Backend Web) ---
        r'<\?php',                 # Ouverture
        r'^\s*\?>;?$',             # Fermeture (NOUVEAU : gère le ?> seul)
        r'\$[a-zA-Z_]\w*',         # Variables $var
        r'\->',                    # Méthodes objets
        r'(echo|print|system|exec|shell_exec|passthru)\b', # Mots clés PHP dangereux

        # --- 6. SQL ---
        r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TABLE|FROM|WHERE)\b',

        # --- 7. Python / Général ---
        r'(def|class|return|if|for|while|try|except|else|with|from)\s+',
        r'^\s*@\w+',
        r'"""', r"'''",
        r'^\s*[\w\._]+\s*=\s*.+$', 

        # --- 8. Syntaxe Générique ---
        r'[{}];?\s*$',      
        r'\);\s*$',         
        r'^\s{4,}', r'\t',  
    ]
    
    combined_regex = '|'.join(code_indicators)
    
    in_code_mode = False
    in_multiline_string = False 
    
    for line in lines:
        is_line_code = False
        stripped = line.strip()
        
        # Gestion Docstrings
        if '"""' in line or "'''" in line:
            if (line.count('"""') + line.count("'''")) % 2 == 1:
                in_multiline_string = not in_multiline_string
            is_line_code = True
        elif in_multiline_string:
            is_line_code = True
            
        # Regex (avec tolérance pour les balises de fin)
        elif len(stripped) > 2 or stripped in ['}', '};', '];', ']', ')', '?>', ');']:
            if re.search(combined_regex, line, re.IGNORECASE):
                is_line_code = True

        # Regroupement
        if is_line_code:
            if not in_code_mode:
                in_code_mode = True
            potential_code_block.append(line)
        else:
            # On garde les lignes vides ou commentaires dans le bloc
            # On garde aussi les lignes très courtes DANS un bloc HTML (ex: "  <br>")
            if in_code_mode:
                # Si c'est vide, un commentaire, ou si ça ressemble à du contenu texte HTML court
                # (Pour éviter de couper <h1>Titre</h1> au milieu si la regex a raté le contenu)
                potential_code_block.append(line)
            else:
                if in_code_mode:
                    save_block(potential_code_block, code_blocks, cleaned_text_lines)
                    potential_code_block = []
                    in_code_mode = False
                
                cleaned_text_lines.append(line)

    if potential_code_block:
        save_block(potential_code_block, code_blocks, cleaned_text_lines)

    return {
        "text_content": "\n".join(cleaned_text_lines).strip(),
        "code_blocks": code_blocks,
        "has_code": len(code_blocks) > 0
    }

def save_block(buffer, blocks_list, text_list):
    """Fonction utilitaire pour valider et sauvegarder un bloc."""
    full_block = "\n".join(buffer).strip()
    if is_valid_code_block(full_block) or is_strong_web_match(full_block):
        blocks_list.append(full_block)
        text_list.append("\n[...CODE EXTRAIT...]\n")
    else:
        # Faux positif (ex: liste de courses), on remet dans le texte
        text_list.extend(buffer)

def is_strong_web_match(text):
    """Validation de secours pour les petits snippets Web (CSS/YAML/JSON)."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines: return False
    
    # Si > 50% des lignes ressemblent à du CSS (prop: val;) ou YAML (key: val) ou HTML (<tag>)
    matches = sum(1 for l in lines if re.search(r'(^[\w\-\"]+\s*:)|(^\s*-\s+)|(^\s*<)', l))
    return matches / len(lines) > 0.5

CODE_KEYWORDS = {
    'def', 'class', 'import', 'return', 'var', 'let', 'const', 'function', 
    'if', 'else', 'for', 'while', 'print', 'console.log', 'echo', 'sudo', 
    'docker', 'npm', 'pip', 'public', 'private', 'void', 'int', 'struct'
}

def is_valid_code_block(text):
    """
    Valide si un texte est vraiment du code pour éviter d'analyser du texte explicatif.
    """
    text = text.strip()
    
    # 1. Filtre de longueur minimale (augmenté à 10 chars)
    if len(text) < 10: 
        return False 

    # 2. Filtre "Phrase naturelle" : Commence par majuscule, finit par point, contient des espaces
    # et ne contient PAS de symboles critiques de code ({, }, ;)
    if (text[0].isupper() and text.endswith('.') and " " in text and 
        not any(c in text for c in ['{', '}', ';', '(', ')', '$', '<', '>'])):
        # Si c'est une phrase mais qu'elle ne contient aucun mot-clé technique, on rejette
        if not any(kw in text for kw in CODE_KEYWORDS):
            return False

    # 3. Validation Pygments avec Exclusion
    try:
        lexer = guess_lexer(text)
        # Ces lexers sont souvent détectés à tort sur des listes ou du texte structuré
        excluded_lexers = [
            'Text only', 'MIME', 'YAML', 'Properties', 'Ini', 'Gettext', 'Markdown'
        ]
        if lexer.name in excluded_lexers:
            # Si Pygments doute, on regarde si on trouve des mots-clés explicites
            return any(kw in text for kw in CODE_KEYWORDS)
            
        return True
    except ClassNotFound:
        return False