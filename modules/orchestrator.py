import re
import chainlit as cl
import json
import asyncio
from crewai import Crew, Process
import os
import shutil
import tempfile
import glob
import datetime
from typing import List

# IMPORTS MODULES
from modules.scanner import run_zap_scan
from modules.utils import get_latest_report_data, keep_only_latest_report, process_raw_alerts, split_list_into_chunks
from modules.agents import pdf_writer_agent, sme_risk_advisor, audit_analyst, chat_assistant
from modules.tasks import (
    create_analysis_task, create_intro_task, create_remediation_task, create_chat_task,       
    create_sme_intro_task, create_sme_body_task, create_semgrep_remediation_task
)
from modules.reporting.technical_report import generate_technical_pdf
from modules.reporting.managerial_report import generate_managerial_pdf
from modules.semgrep import run_semgrep_scan

# Pré-compilation regex
THOUGHT_PATTERN = re.compile(r'(Thought|Plan|Action|Observation):.*?(?=\n\n|\Z)', re.DOTALL)


# --- PIPELINE A : SCAN LIVE (ZAP) ---
async def Zap_pipeline(target_url, threads, active_scan):
    cl.user_session.set("stop_requested", False)
    msg = cl.Message(content=f"🚀 **Démarrage du scan sur** `{target_url}`...")
    await msg.send()
    
    def progress_handler(percent, phase):
        if cl.user_session.get("stop_requested"): return False
        
        bar_length = 10
        filled_length = int(bar_length * percent // 100)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        
        msg.content = f"🚀 **Scan en cours sur** `{target_url}`\n⚙️ **Phase :** {phase}\n📊 `{bar}` {percent}%"
        cl.run_sync(msg.update())
        return True

    # Lancement ZAP
    scan_result_raw = await cl.make_async(lambda: run_zap_scan(target_url, threads, active_scan, progress_callback=progress_handler))()

    # --- 1. GESTION DU STOP MANUEL ---
    if cl.user_session.get("stop_requested"):
        msg.content = "🛑 **Arrêt demandé par l'utilisateur.**"
        await msg.update()
        return None

    # --- 2. GESTION DES ERREURS ZAP (CRITIQUE) ---
    if not scan_result_raw:
        msg.content = "❌ **Erreur Critique :** Le scan ZAP n'a rien renvoyé (Crash ou Timeout)."
        await msg.update()
        return None

    try:
        if isinstance(scan_result_raw, str):
            parsed_result = json.loads(scan_result_raw)
            if "error" in parsed_result:
                error_msg = parsed_result["error"]
                details = parsed_result.get("details", "")
                msg.content = f"❌ **Échec du Scan ZAP**\n\n**Raison :** {error_msg}\n\n`{details}`"
                await msg.update()
                return None
    except:
        pass

    # --- 3. SUITE DU TRAITEMENT ---
    msg.content = f"✅ **Scan terminé** \n🧠 **Analyse de l'expert IA en cours...**"
    await msg.update()
    
    keep_only_latest_report("zap_FULL_") # Nettoyage des anciens rapports 
    data, _, _ = get_latest_report_data()
    
    if not data:
        msg.content = "❌ **Erreur :** Impossible de lire le rapport ZAP sur le disque."
        await msg.update()
        return None
    
    # Analyse IA Rapide (Intro) - On inclut Critical/High/Medium
    final_obj = process_raw_alerts(data, target_url, ["Critical", "High", "Medium"])
    final_json = json.dumps(final_obj, indent=2)
    
    task = create_analysis_task(audit_analyst, target_url, final_json)
    crew = Crew(agents=[audit_analyst], tasks=[task])
    
    res = await cl.make_async(crew.kickoff)()
    
    full_text = clean_crew_output(str(res))
   
    actions = [
        cl.Action(name="start_pdf_choice", value="go", label="📚 Générer le Rapport PDF Complet", id="pdf_btn", payload={"action": "start_pdf_choice"})
    ]
    
    return full_text, actions


# --- PIPELINE B : SCAN SEMGREP (EXECUTION) ---
async def run_semgrep_pipeline(files=None, raw_code=None, config_name="p/default"):
    """Gère l'analyse Semgrep et prépare le bouton PDF."""
    
    with tempfile.TemporaryDirectory() as scan_dir:
        # Gestion Fichiers / Code Brut
        if files:
            for file in files:
                dest_path = os.path.join(scan_dir, file.name)
                shutil.copy(file.path, dest_path)
        elif raw_code:
            match = re.match(r'^```(\w+)', raw_code.strip())
            language = match.group(1).lower() if match else "python"
            extensions = {"python": ".py", "javascript": ".js", "js": ".js", "ts": ".ts", "java": ".java", "php": ".php"}
            file_ext = extensions.get(language, ".py")
            filename = f"snippet{file_ext}"
            
            clean_code = re.sub(r'^```[a-zA-Z]*\n', '', raw_code.strip())
            clean_code = re.sub(r'\n```$', '', clean_code)
            snippet_path = os.path.join(scan_dir, filename)
            with open(snippet_path, "w", encoding="utf-8") as f:
                f.write(clean_code)

        # Exécution du scan
        scan_results = run_semgrep_scan(scan_dir, config_name=config_name)
      
        if "vulnerabilities" in scan_results:
            for issue in scan_results["vulnerabilities"]:
                if "file" in issue:
                    issue["file"] = clean_file_path(issue["file"])
        if "error" in scan_results:
            return f"❌ Erreur Semgrep : {scan_results['error']}", []

        if scan_results["scan_summary"]["total_issues"] == 0:
            return "✅ **Semgrep Clean :** Aucune vulnérabilité critique détectée.", []
        scan_results = process_raw_alerts(scan_results, "Code Source Uploadé",["Critical", "High", "Medium", "Low", "Error", "Warning", "Info"])
        print(scan_results["vulnerabilities"])
        # Sauvegarde pour le PDF
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        formatted_report_path = os.path.join("reports", f"semgrep_FULL_{timestamp}.json")
        
        with open(formatted_report_path, "w", encoding="utf-8") as f:
            json.dump(scan_results, f, indent=4)

        cl.user_session.set("last_semgrep_report", formatted_report_path)
        keep_only_latest_report("semgrep_FULL_") # Nettoyage ancien rapports Semgrep
        # Analyse IA "Chat"
        scan_json = json.dumps(scan_results, indent=2)
        task = create_analysis_task(audit_analyst, "Code Source Uploadé", scan_json)
        crew = Crew(agents=[audit_analyst], tasks=[task])
        res = await cl.make_async(crew.kickoff)()
        
        actions = [
            cl.Action(
                name="semgrep_pdf_gen", 
                value="go", 
                label="📄 Générer le rapport Technique (Pour les Développeurs)",
                payload={"type": "semgrep"}
            )
        ]

        return clean_crew_output(str(res)), actions


# --- PIPELINE C : PDF GENERATION (OPTIMIZED & UNIFIED) ---

async def run_semgrep_pdf_pipeline(report_type="technical"):
    """
    Génère un PDF basé sur le dernier scan Semgrep.
    Utilise process_raw_alerts pour normaliser les sévérités (ERROR -> High).
    """
    # 1. Récupération
    report_path = cl.user_session.get("last_semgrep_report")
    if not report_path or not os.path.exists(report_path):
        list_of_files = glob.glob('reports/semgrep_FULL_*.json')
        if not list_of_files:
            return "❌ Aucun rapport Semgrep trouvé.", []
        report_path = max(list_of_files, key=os.path.getctime)

    # 2. Lecture
    with open(report_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        

    # 🔥 OPTIMISATION: Utilisation de votre fonction de filtre centralisée
    target_source = "Code Source (Semgrep)"
    # On demande tout le spectre, process_raw_alerts triera Critical > High/Error > Medium/Warning
    allowed_risks = ["Critical", "High", "Medium", "Low", "Error", "Warning", "Info"]
    
    processed_data = process_raw_alerts(raw_data, target_source, allowed_risks)
    vulns = processed_data.get("vulnerabilities", [])

    if not vulns:
        return "✅ Aucune faille pertinente trouvée pour le rapport PDF.", []

    await cl.Message(content=f"📝 **L'IA rédige le rapport Semgrep pour {len(vulns)} faille(s)...**").send()

    # 3. Exécution via la logique partagée
    return await _execute_pdf_generation_logic(
        vulns=vulns,
        target_name=target_source,
        report_type="Technique (Code)",
        current_agent=sme_risk_advisor, 
        intro_task_func=create_intro_task,
        body_task_func=create_semgrep_remediation_task,
        pdf_gen_func=generate_technical_pdf,
        pdf_filename="Rapport_Technique_Semgrep.pdf",
        batch_size=8,
        is_semgrep=True
    )


async def run_batch_pdf_pipeline(selected_risks, report_type="technical"):
    """
    Pipeline principal pour les rapports ZAP (Managerial ou Technique).
    """
    # 1. Récupération
    raw_data, _, target_url = get_latest_report_data()
    if not raw_data: 
        return "❌ Aucune donnée. Veuillez effectuer un scan ZAP d'abord.", []
    
    # 🔥 OPTIMISATION: Filtrage et Tri
    full_data_obj = process_raw_alerts(raw_data, target_url, selected_risks)
    vulnerabilities_list = full_data_obj.get("vulnerabilities", [])
    
    if not vulnerabilities_list:
        return f"✅ Aucune faille trouvée pour les niveaux : {selected_risks}", []

    # 2. Config Switch
    if report_type == "managerial":
        print("💼 Config: Mode PME/Direction")
        current_agent = sme_risk_advisor
        intro_task_func = create_sme_intro_task
        body_task_func = create_sme_body_task
        pdf_gen_func = generate_managerial_pdf
        pdf_filename = "Rapport_Audit_PME.pdf"
        BATCH_SIZE = 10 
        pretty_type = "Managérial"
    else:
        print("🛠️ Config: Mode Technique")
        current_agent = pdf_writer_agent
        intro_task_func = create_intro_task
        body_task_func = create_remediation_task
        pdf_gen_func = generate_technical_pdf
        pdf_filename = "Rapport_Technique_ZAP.pdf"
        BATCH_SIZE = 8
        pretty_type = "Technique"

    # 3. Exécution via la logique partagée
    return await _execute_pdf_generation_logic(
        vulns=vulnerabilities_list,
        target_name=target_url,
        report_type=pretty_type,
        current_agent=current_agent,
        intro_task_func=intro_task_func,
        body_task_func=body_task_func,
        pdf_gen_func=pdf_gen_func,
        pdf_filename=pdf_filename,
        batch_size=BATCH_SIZE,
        is_semgrep=False
    )


async def _execute_pdf_generation_logic(
    vulns, target_name, report_type, current_agent, 
    intro_task_func, body_task_func, pdf_gen_func, 
    pdf_filename, batch_size, is_semgrep=False
):
    """
    LOGIQUE UNIFIÉE POUR GÉNÉRER LE CONTENU DU PDF (DRY Principle)
    """
    parts = []
    
    # A. Génération de l'Intro
    await cl.Message(content=f"📝 **Rédaction de l'Introduction ({report_type})...**").send()
    try:
        # Adaptation des arguments selon si c'est Semgrep ou ZAP
        if is_semgrep:
             task_intro = intro_task_func(
                 current_agent, target_name, len(vulns), 
                 auditeur="Semgrep SAST", nomredacteur="Cyber-Supervisor AI"
             )
        else:
             # Gestion des signatures différentes pour ZAP (Managerial vs Technical)
             try:
                task_intro = intro_task_func(current_agent, target_name, len(vulns))
             except TypeError:
                task_intro = intro_task_func(current_agent, target_name, len(vulns), auditeur="ZAP Scanner", nomredacteur="Cyber-Supervisor AI")

        crew_intro = Crew(agents=[current_agent], tasks=[task_intro], process=Process.sequential)
        res_intro = await cl.make_async(crew_intro.kickoff)()
        parts.append(clean_crew_output(res_intro))
        
    except Exception as e:
        error_msg = f"# ERREUR INTRO\nL'IA n'a pas pu générer l'intro : {str(e)}"
        print(error_msg)
        parts.append(error_msg)

    # B. Boucle sur les vulnérabilités (Batches)
    chunks = list(split_list_into_chunks(vulns, batch_size))
    
    global_counter = 1
    
    for i, chunk in enumerate(chunks):
        msg = cl.Message(content=f"⚙️ **Analyse lot {i+1}/{len(chunks)} ({len(chunk)} failles)...**")
        await msg.send()
        
        chunk_str = json.dumps(chunk, indent=2)
        
        # Adaptation des signatures de tâches
        if is_semgrep:
             # Semgrep task
             task_rem = body_task_func(current_agent, chunk_str, len(chunk),start_index=global_counter)
        elif report_type == "Managérial":
             # Managerial ZAP task
             task_rem = body_task_func(current_agent, target_name, chunk_str)
        else:
             # Technical ZAP task
             task_rem = body_task_func(current_agent, target_name, chunk_str, len(chunk), start_index=global_counter)
        
        try:
            crew_batch = Crew(agents=[current_agent], tasks=[task_rem], process=Process.sequential)
            res = await cl.make_async(crew_batch.kickoff)()
            
            global_counter += len(chunk)
            parts.append(clean_crew_output(res))
            
            await msg.remove()
            await asyncio.sleep(1.5) # Anti Rate-Limit
            
        except Exception as e:
            error_msg = f"⚠️ Erreur lot {i+1}: {str(e)}"
            parts.append(f"\n\n### [ERREUR GÉNÉRATION LOT {i+1}]\nL'IA a échoué sur ce segment.\n")
            await cl.Message(content=error_msg).send()
        
    
    # C. Assemblage Final
    if parts:
        await cl.Message(content="🏁 **Assemblage et mise en page du PDF...**").send()
        
        parts.append("\n\n---\n*Rapport généré automatiquement par Cyber-Supervisor (PFE-T-480).*")

        try:
            temp_path = pdf_gen_func(parts, target_name)
            
            if os.path.exists(temp_path):
                
                timestamp = datetime.datetime.now().strftime('%H%M%S')
                clean_type = report_type.replace(" ", "_").replace("(", "").replace(")", "")
                
                # On construit le nom final : "Rapport_Managerial_183012.pdf"
                pretty_filename = f"Rapport_{clean_type}_{timestamp}.pdf"

                files = [
                    cl.File(
                        name=pretty_filename,  # <--- C'est ici que le nom change
                        path=temp_path, 
                        display="inline"
                    )
                ]
                
                return f"✅ **{pretty_filename}** généré avec succès.", files
                
            else:
                return "❌ Le fichier PDF n'a pas été créé sur le disque.", []
                
        except Exception as e:
            return f"❌ Erreur critique assemblage PDF: {str(e)}", []
    
    return "❌ Échec génération : Aucun contenu produit par l'IA.", []



async def run_chat_pipeline(msg):
    task = create_chat_task(chat_assistant, msg)
    crew = Crew(agents=[chat_assistant], tasks=[task], process=Process.sequential)
    result = await cl.make_async(crew.kickoff)()
    final_answer = clean_crew_output(str(result))
    return final_answer

# --- HELPER FUNCTIONS ---
def clean_file_path(path_str):
    """
    Transforme: C:\\Users\\...\\Temp\\tmpxyz123\\mon_projet\\fichier.py
    En: mon_projet/fichier.py
    """
    # 1. Uniformiser les slashs (Windows \ vers /)
    path_str = path_str.replace("\\", "/")
    
    # 2. Regex pour trouver le pattern du dossier temporaire aléatoire
    # Cherche "/tmp<quelquechose>/" ou "/Temp/<quelquechose>/"
    # La regex capture tout ce qui est APRES le dossier temp
    
    # Pattern explicatif : 
    # (?: ... ) = groupe non capturant pour trouver le dossier temp
    # [\\/] = slash ou backslash
    # (?:tmp|Temp) = nom du dossier temp
    # [a-zA-Z0-9_]+ = le nom aléatoire (ex: tmpj4nkop3q)
    # [\\/] = le slash suivant
    # (.*) = LE GROUPE CAPTURÉ (le reste du chemin)
    
    match = re.search(r'(?:tmp|Temp)[\\/][a-zA-Z0-9_]+[\\/](.*)', path_str, re.IGNORECASE)
    
    if match:
        return match.group(1) # Retourne uniquement la partie après le dossier temp
    
    # Fallback : Si on ne trouve pas le pattern, on retourne juste le nom du fichier
    return path_str.split('/')[-1]

def clean_crew_output(output_text: str) -> str:
    if hasattr(output_text, 'raw'):
        output_text = output_text.raw
        
    if not isinstance(output_text, str):
        output_text = str(output_text)
    
    if not output_text:
        return ""

    final_marker = "### REPONSE_FINALE"

    if final_marker in output_text:
        return output_text.split(final_marker, 1)[1].strip()

    fallback_markers = ["## 🛡️", "🚨 ", "## "]
    for marker in fallback_markers:
        index = output_text.find(marker)
        if index != -1:
            clean_text = output_text[index:].strip()
            return clean_text.replace(final_marker, '').strip()

    clean_text = THOUGHT_PATTERN.sub('', output_text)
    return clean_text.replace(final_marker, '').strip()