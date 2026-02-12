import subprocess
import json
import os
from datetime import datetime

def run_semgrep_scan(target_path, config_name="p/default"):
    """
    Exécute Semgrep sur un chemin donné.
    FORCE L'UTF-8 pour éviter les crashs Unicode sur Windows.
    Exécute Semgrep avec une configuration dynamique.
    config_name: 'p/default', 'p/owasp-top-ten', 'p/security-audit', etc.
    """
    
    target_path = target_path.replace('\u202a', '').replace('\u202c', '')

    
    command = [
        "semgrep",
        "scan",
        "--config", config_name,  #Usage de la variable demandee par utilisateur
        "--json",
        target_path
    ]

    # --- CORRECTION CRITIQUE ICI ---
    # On copie l'environnement actuel (pour garder le PATH)
    # Et on force Python à utiliser l'UTF-8 pour le sous-processus
    env_vars = os.environ.copy()
    env_vars["PYTHONUTF8"] = "1"
    # -------------------------------

    try:
        print(f"🔍 Lancement Semgrep sur : {target_path}")
        
        # On passe 'env=env_vars' et on force l'encodage de la capture en utf-8
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            env=env_vars,          # Injecte la variable PYTHONUTF8=1
            encoding='utf-8'       # Force la lecture des logs en UTF-8
        )

        if result.returncode != 0:
            print("❌ Erreur critique Semgrep :")
            print(f"Code de retour : {result.returncode}")
            print(f"STDERR (Erreur) : {result.stderr}")
            return {"error": f"Semgrep a échoué (Code {result.returncode})."}
        
        # Au lieu de lire un fichier, on parse directement la sortie console (stdout)
        try:
            raw_results = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"error": "Semgrep n'a pas renvoyé un JSON valide."}

        # On passe à la fonction de formatage (sans chemin de fichier)
        return format_semgrep_results(raw_results, target_path)

    except FileNotFoundError:
        return {"error": "La commande 'semgrep' est introuvable."}
    except Exception as e:
        return {"error": str(e)}

def format_semgrep_results(raw_json,target):
    """Nettoie les résultats Semgrep pour les rendre digestes par l'IA."""
    findings = []
    
    for result in raw_json.get("results", []):
        findings.append({
            "title": result.get("check_id"),
            "risk": result.get("extra", {}).get("severity", "Medium"),
            "file": result.get("path").replace("__SEP__", "/"),
            "line": result.get("start", {}).get("line"),
            "description": result.get("extra", {}).get("message"),
            "code_snippet": result.get("extra", {}).get("lines"),
            "remediation": result.get("extra", {}).get("metadata", {}).get("fix_instructions", "")
        })

    return {
        "scan_summary": {
            "total_issues": len(findings),
            "scan_type": "SAST (Semgrep)",
            "target": target
        },
        "vulnerabilities": findings
    }
    