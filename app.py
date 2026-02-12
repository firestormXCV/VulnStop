
import asyncio
from email.mime import message
import os
import chainlit as cl
import chainlit.data as cl_data
from dotenv import load_dotenv
import chainlit.data as cl_data
from chainlit.types import ThreadDict
from litellm import uuid
from litellm import uuid
# Import des modules locaux
from modules.utils import check_and_calibrate_target, extract_url_from_text, extract_code_and_text, is_valid_code_block # Si extract est dans utils
from modules.git_utils import is_git_repo_web_url, clone_git_repo, cleanup_repo, get_files_from_repo
from modules.orchestrator import Zap_pipeline, run_batch_pdf_pipeline, run_chat_pipeline, run_semgrep_pipeline, run_semgrep_pdf_pipeline #, run_audit_pipeline
from modules.db_manager import SQLiteDataLayer 
load_dotenv()

data_layer = SQLiteDataLayer()
cl_data._data_layer = data_layer

def serialize_actions(actions_list):
    """
    Transforme une liste d'objets cl.Action en une liste de dictionnaires propres
    pour la sauvegarde en métadonnées.
    """
    clean_list = []
    for a in actions_list:
        clean_list.append({
            "name": a.name,
            "value": getattr(a, "value", ""),
            "label": a.label,
            "payload": a.payload or {}
        })
    return clean_list
async def test_action():
    pass

@cl.password_auth_callback
def auth(username, password):
    if username == "admin" and password == "admin":
        # AJOUT CRITIQUE : on force id="admin"
        return cl.User(identifier="admin", id="admin", metadata={"role": "admin"})
    return None

@cl.on_chat_start
async def start():
    actions = [cl.Action(name="start_pdf_choice", value="go", label="📄 Analyser à nouveau le dernier rapport", id="scan_exist", payload={"action": "start_pdf_choice"})]

    # --- CORRECTION ICI ---
    await cl.Message(
        content="👋 **L'Agent IA Cyber est prêt !**\n\n _Voici les options possibles pour la détection des vulnérabilités :_ \n\n- **Copier** l'**URL** de **votre site web**.\n - **Copier** ou **téléverser** votre **propre code** sur l'interface.\n- **Copier** l'**URL** de votre **répertoire GitHub (public)**.\n\n _Vous pouvez également :_  \n- **Poser** **toutes vos questions** sur la **sécurité informatique**. \n- **Analyser** à nouveau le **précédent rapport** (si existant).\n\n", 
        actions=actions,
        metadata={"actions": serialize_actions(actions)} # Utilisation de la fonction propre
    ).send()

@cl.action_callback("semgrep_pdf_gen")
async def on_semgrep_pdf_click(action):
    await action.remove() # On enlève le bouton pour ne pas cliquer 2 fois
    
    # Appel de la nouvelle fonction orchestrator
    res_text, files = await run_semgrep_pdf_pipeline()
    
    if files:
        await cl.Message(content=res_text, elements=files).send()
    else:
        await cl.Message(content=f"⚠️ {res_text}").send()

@cl.on_stop
def on_stop(): 
    cl.user_session.set("stop_requested", True)

# --- 1. ETAPE 1 : CHOIX DU TYPE DE RAPPORT ---
@cl.action_callback("start_pdf_choice")
async def on_click_pdf_choice(action):
    await action.remove()
    
    # On propose d'abord le style du rapport
    actions_type = [
        cl.Action(name="report_type_select", value="technical", label="🛠️ Technique (Pour les Développeurs)", payload={"type": "technical"}),
        cl.Action(name="report_type_select", value="managerial", label="💼 Managérial (Pour la Direction)", payload={"type": "managerial"}),
    ]
    actions_data = [vars(a) for a in actions_type]
    await cl.Message(content="📑 **Quel type de rapport souhaitez-vous générer ?**", actions=actions_type,metadata={"actions": actions_data}).send()

# --- 2. ETAPE 2 : CHOIX DU NIVEAU DE RISQUE ---
@cl.action_callback("report_type_select")
async def on_report_type_selected(action):
    await action.remove()
    
    # On sauvegarde le choix du type en session
    report_type = action.payload.get("type", "technical")
    cl.user_session.set("report_type", report_type)
    
    # --- BRANCHE 1 : MANAGÉRIAL (AUTOMATIQUE) ---
    if report_type == "managerial":
        # Pour le management, on ne filtre pas, on donne tout le contexte.
        await cl.Message(content=f"✅ Mode **Managérial 💼** sélectionné.\n🚀 **Génération du rapport global (High/Medium/Low) lancée...**").send()
        
        # On définit les risques par défaut (Tout)
        all_risks = ["High", "Medium", "Low"]
        
        try:
            # On lance le pipeline directement ici
            res_text, files = await run_batch_pdf_pipeline(all_risks, report_type="managerial")
            
            if files:
                await cl.Message(content=f"✅ **Terminé !**\n{res_text}", elements=files).send()
            else:
                await cl.Message(content=f"⚠️ **Info :**\n{res_text}").send()
                
        except Exception as e:
            await cl.Message(content=f"❌ **Erreur :** {str(e)}").send()

    # --- BRANCHE 2 : TECHNIQUE (MANUEL) ---
    else:
        # Pour les devs, on laisse le choix du filtrage pour prioriser les tickets
        await cl.Message(content=f"✅ Mode **Technique 🛠️** sélectionné.").send()
        
        actions_risk = [
            cl.Action(name="risk_select", value="High", label="🔴 High Uniquement", payload={"risk": "High"}),
            cl.Action(name="risk_select", value="High,Medium", label="🟠 High & Medium", payload={"risk": "High,Medium"}),
            cl.Action(name="risk_select", value="High,Medium,Low", label="🟡 Tout (H/M/L)", payload={"risk": "High,Medium,Low"}),
        ]
        actions_data = [vars(a) for a in actions_risk]
        await cl.Message(content="📊 **Quels niveaux de failles voulez-vous inclure ?**", actions=actions_risk, metadata={"actions": actions_data}).send()

# --- 3. LANCEMENT GENERATION ---
@cl.action_callback("risk_select")
async def on_risk_selected(action):
    await action.remove()
    
    risk_value = action.payload.get("risk", "High,Medium,Low")
    selected = risk_value.split(",")
    
    # On récupère le type stocké à l'étape précédente
    report_type = cl.user_session.get("report_type", "technical")
    
    await cl.Message(content=f"🚀 **Génération Rapport {report_type.capitalize()}** (Filtre : {selected})...").send()
    
    try:
        # IMPORTANT : On passe report_type à la fonction pipeline
        res_text, files = await run_batch_pdf_pipeline(selected, report_type=report_type)
        
        if files:
            await cl.Message(content=f"✅ **Terminé !**\n{res_text}", elements=files).send()
        else:
            await cl.Message(content=f"⚠️ **Info :**\n{res_text}").send()
            
    except Exception as e:
        await cl.Message(content=f"❌ **Erreur :** {str(e)}").send()

# --- GESTION SCAN MODE (Actif/Passif) ---
@cl.action_callback("scan_mode_select")
async def on_scan_mode_selected(action):
    # 1. On nettoie l'interface
    await action.remove()
    
    # 2. Récupération des données stockées en session
    url = cl.user_session.get("target_url")
    threads = cl.user_session.get("scan_threads")
    mode = action.payload.get("mode")
    
    if not url:
        await cl.Message(content="❌ Erreur de session : URL perdue. Veuillez recommencer.").send()
        return

    # 3. Définition du booléen pour l'orchestrateur
    is_active_scan = (mode == "active")
    
    mode_text = "⚡ ACTIF (Attaque réelle)" if is_active_scan else "🔍 PASSIF (Écoute silencieuse)"
    await cl.Message(content=f"🚀 **Lancement du Scan {mode_text}** sur `{url}`...").send()

    # 4. Lancement du Pipeline avec l'argument active_scan
    # NOTE: Vous devez mettre à jour Zap_pipeline pour accepter active_scan=True/False
    res = await Zap_pipeline(url, threads, active_scan=is_active_scan)
    
    if res:
        txt, acts = res
        acts_data = [vars(a) for a in acts]
        await cl.Message(content=f"### 🛡️ Résumé Scan\n\n{txt}", actions=acts, metadata={"actions": acts_data}).send()
        
@cl.action_callback("test_action")
async def on_test_action(action: cl.Action):
    await cl.Message(content="✅ Le bouton fonctionne !").send()

#Fonction non régie par comportement, donc pas de @cl.on_message pour celui-ci
async def ask_semgrep_config():
    """Affiche les boutons de choix de règles pour Semgrep."""
    actions = [
        cl.Action(name="semgrep_scan_launch", value="p/default", label="⚙️ Standard (Complet)", payload={"config": "p/default"}),
        cl.Action(name="semgrep_scan_launch", value="p/owasp-top-ten", label="🛡️ OWASP Top 10 (Partiel)", payload={"config": "p/owasp-top-ten"}),
        cl.Action(name="semgrep_scan_launch", value="p/security-audit", label="🕵️ Security Audit (Minimum)", payload={"config": "p/security-audit"}),
        #Autres options de règles plus tard ici si besoin
    ]
    await cl.Message(content="🧐 **Quelle configuration Semgrep souhaitez-vous utiliser ?**", actions=actions).send()

@cl.action_callback("semgrep_scan_launch")
async def on_semgrep_config_selected(action):
    await action.remove() # Retire les boutons
    
    config_chosen = action.payload.get("config", "p/default")
    mode = cl.user_session.get("semgrep_mode") # 'files', 'snippet' ou 'git'
    
    msg = cl.Message(content=f"🚀 **Lancement Semgrep** (Pack: `{config_chosen}`)...\n⏳ Analyse en cours...")
    await msg.send()
    
    res_text, actions = "", []
    
    # Récupération des données selon le mode
    if mode == "files":
        files = cl.user_session.get("semgrep_data")
        res_text, actions = await run_semgrep_pipeline(files=files, config_name=config_chosen)
        
    elif mode == "snippet":
        raw_code = cl.user_session.get("semgrep_data")
        res_text, actions = await run_semgrep_pipeline(raw_code=raw_code, config_name=config_chosen)
        
    elif mode == "git":
        # Pour Git, c'est un peu spécial car run_semgrep_pipeline attend une liste de fichiers
        repo_files = cl.user_session.get("semgrep_data")
        res_text, actions = await run_semgrep_pipeline(files=repo_files, config_name=config_chosen)

    msg.content = f"### 🔍 Résultats Semgrep ({config_chosen})\n\n{res_text}"
    msg.actions = actions
    await msg.update()

async def show_menu_delayed(thread_id):
    # On attend que l'historique (resume_thread) soit passé
    # Comme cette tâche est détachée, ce sleep ne bloque PAS le chargement de la page
    
    # --- A. FICHIERS (Mode Fantôme) ---
    elements_to_display = []
    
    if data_layer and thread_id:
        try:
            files = await data_layer.get_thread_files(thread_id)
            for f in files:
                path = f.get("path")
                if path and os.path.exists(path):
                    elements_to_display.append(
                        cl.File(name=f.get("name"), path=path, display="inline")
                    )
        except: pass

    if elements_to_display:
        await cl.Message(
            content=f"📂 **Archives :** {len(elements_to_display)} document(s) retrouvé(s).",
            elements=elements_to_display,
            metadata={"disable_persistence": True}
        ).send()

    # --- B. BOUTONS (Mode Fantôme) ---
    actions = [
        cl.Action(
            name="start_pdf_choice", 
            value="go", 
            label="📄 Analyser le dernier rapport existant", 
            payload={"action": "start_pdf_choice"},
            id=str(uuid.uuid4())
        )
    ]

    await cl.Message(
        content="👇 **Action requise :**\nEntrez une URL ou utilisez l'option ci-dessous.",
        actions=actions,
        metadata={"disable_persistence": True}
    ).send()
@cl.on_chat_resume
async def on_chat_resume(thread):
    thread_id = thread["id"]
    
    # ⚡ MAGIE ICI : On lance la tâche en parallèle et on s'en va.

    asyncio.create_task(show_menu_delayed(thread_id))
    
    return
    
# --- GESTION DES MESSAGES (MAIN) ---
@cl.on_message
async def main(message: cl.Message):
    
    print(f"🕵️ LIVE DEBUG: Le Data Layer actif est -> {cl_data._data_layer}")
    # ---------------------------------------------------------
    # 1. GESTION DES FICHIERS (Priorité Absolue)
    # ---------------------------------------------------------
    if message.elements:
        files = [el for el in message.elements if el.type == "file"]
        if files:
            #await cl.Message(
            #    content=f"📂 **{len(files)} fichier(s) reçu(s).**\n"
            #            f"Lancement de l'analyse SAST (Semgrep)..."
            #).send()
            cl.user_session.set("semgrep_data", files)
            cl.user_session.set("semgrep_mode", "files")
            
            # On passe directement les objets fichiers
            #res, action = await run_semgrep_pipeline(files=files)
            #await cl.Message(content=f"### 🔍 Rapport Semgrep (Fichiers)\n\n{res}",actions=action).send()
            #return 
            await cl.Message(content=f"📂 **{len(files)} fichier(s) reçu(s).**").send()
            await ask_semgrep_config() # Appel des boutons
            return

    # ---------------------------------------------------------
    # 2. GESTION DES SNIPPETS DE CODE (Priorité Haute)
    # ---------------------------------------------------------
    # On utilise votre extracteur robuste
    extraction = extract_code_and_text(message.content)

    if extraction['has_code']:
        # On filtre la liste pour ne garder que les blocs valides
        valid_blocks = [b for b in extraction['code_blocks'] if is_valid_code_block(b)]
        clean_code = "\n\n".join(valid_blocks)
    
        # On concatène les blocs propres. 
        # extract_code_and_text renvoie déjà du code pur, cela ne gênera pas.
        #clean_code_for_analysis = "\n\n".join(valid_blocks)
        
        #print("Code extrait pour analyse Semgrep :", clean_code_for_analysis)
        #print("Texte associé :", extraction['text_content'])
        # Appel Pipeline
        #res, action = await run_semgrep_pipeline(raw_code=clean_code_for_analysis)

        #await cl.Message(content=f"### 🔍 Rapport Semgrep (Snippet)\n\n{res}",actions=action).send()

        cl.user_session.set("semgrep_data", clean_code)
        cl.user_session.set("semgrep_mode", "snippet")
        await cl.Message(content="📝 **Snippet de code détecté.**").send()
        await ask_semgrep_config() # Appel des boutons
        return 

    # ---------------------------------------------------------
    # 3. GESTION DES URLS / DAST (Priorité Moyenne)
    # ---------------------------------------------------------
    url = extract_url_from_text(message.content)
    
    urlLoi = f"https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000047052655"
    
    if url:
        msg_check = await cl.Message(content=f"🔎 **Vérification de la cible** `{url}`...").send()
        
        # Vérification de l'accessibilité
        diagnostic = await cl.make_async(check_and_calibrate_target)(url)
        
        if not diagnostic["valid"]:
            msg_check.content = f"⛔ **Erreur cible :** {diagnostic['message']}"
            await msg_check.update()
            return # STOP (On ne lance pas le chat sur une URL invalide)
        
        if diagnostic["valid"]:
            # --- MODIFICATION ICI : ON NE LANCE PLUS DIRECTEMENT ---
            
            # 1. On stocke les infos pour plus tard
            cl.user_session.set("target_url", url)
            cl.user_session.set("scan_threads", diagnostic["threads"])
            
            msg_check.content = f"✅ **Cible valide.** ({diagnostic['message']})"
            await msg_check.update()
            
            #Vérifie si on est face à un repo git ou non

            if is_git_repo_web_url(url):
                msg_git = cl.Message(content=f"📦 **Dépôt Git détecté.**\nClonage de `{url}` en cours...")
                await msg_git.send()

                # 1. CLONAGE
                repo_path, error = await cl.make_async(clone_git_repo)(url)

                if error:
                    msg_git.content = f"❌ **Échec du clonage :**\n{error}"
                    await msg_git.update()
                else:
                    try:
                        # 2. LISTING DES FICHIERS (Via utils, sans Chainlit)
                        msg_git.content = f"✅ **Clonage réussi.**\nLecture des fichiers..."
                        await msg_git.update()
                        
                        # On récupère une liste d'objets RepoFile
                        repo_files = await cl.make_async(get_files_from_repo)(repo_path)
                        
                        if not repo_files:
                            msg_git.content = "⚠️ **Dépôt vide ou illisible.**"
                            await msg_git.update()
                        else:
                            # 3. ANALYSE (On donne la liste au pipeline existant)
                            #cl.user_session.set("semgrep_data", repo_files)
                            #cl.user_session.set("semgrep_mode", "git")

                            msg_git.content = f"🚀 **Analyse en cours** de {len(repo_files)} fichiers..."
                            #await msg_git.update()

                            #await ask_semgrep_config()
                            #return

                            # 3. ANALYSE (On donne la liste au pipeline existant)
                            # run_semgrep_pipeline va lire .path et .name sur nos objets RepoFile
                            res, action = await run_semgrep_pipeline(files=repo_files)
                            
                            await cl.Message(content=f"### 🔍 Résultats Semgrep (Git)\n\n{res}",actions=action).send()

                    except Exception as e:
                         await cl.Message(content=f"❌ **Erreur durant l'analyse :** {str(e)}").send()
                    
                    finally:
                        # 4. NETTOYAGE
                        await cl.make_async(cleanup_repo)(repo_path)

            # --- BLOC WEB CLASSIQUE (ZAP) ---
            else :
            # Disclaimer & Actions
                disclaimer_text = (
                    f"⚠️ **Avertissement de sécurité** ⚠️\n\n"
                    f"Cible : `{url}`\n\n"
                    "Veuillez choisir votre mode d'engagement :\n"
                    "**1. 🔍 Scan Passif (Safe)** : Exploration sans attaques.\n"
                    "**2. ⚡ Scan Actif (Risqué)** : Simulation d'attaques réelles.\n\n"
                    f"🕵️ L'utilisation du mode actif sur un site dont vous n'êtes pas propriétaire pourrait être interprété comme une forme d'attaque informatique. Une attaque informatique **est punissable par [le Code Pénal]({urlLoi})**."
                    " L'outil est destiné à un usage de sécurité défensive et de connaissances des vulnérabilités axés sur la protection.\n\n"
                    "⚖️ **Si vous utilisez le mode actif,  l'autorisation écrite du propriétaire du site web est obligatoire.** \n\n"
                    "_\"Un grand pouvoir implique de grandes responsabilités...\"_"
                )
                actions_mode = [
                    cl.Action(name="scan_mode_select", value="passive", label="🔍 Scan Passif", payload={"mode": "passive"}),
                    cl.Action(name="scan_mode_select", value="active", label="⚡ Scan Actif", payload={"mode": "active"}),
                ]
                await cl.Message(content=disclaimer_text, actions=actions_mode).send()
                return # STOP
    else:
        # ---------------------------------------------------------
        # 4. CHAT GÉNÉRAL (Fallback)
        # ---------------------------------------------------------
        # Si rien de ce qui précède n'a matché, c'est une discussion normale
        res = await run_chat_pipeline(message.content)
        await cl.Message(content=str(res)).send()
