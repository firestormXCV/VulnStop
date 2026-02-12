from urllib.parse import urlparse
import os
import subprocess
import shutil
import tempfile
import stat

NON_REPO_SEGMENTS = {
    "issues", "pull", "pulls", "merge_requests", "mr",
    "tree", "blob", "commit", "commits",
    "releases", "tags", "branches", "wiki",
}

IGNORED_DIRS = {
    "doc", "docs", "documentation",
    "test", "tests", "testing", "__tests__",
    "vendor", "node_modules", "bower_components",
    "build", "dist", "bin", "obj",
    "cmake", ".idea", ".vscode", ".git"
}

IGNORED_FILES = {
    "jquery", "bootstrap", "min.js","package-lock.json", "yarn.lock"
}
KNOWN_GIT_PROVIDERS = {
    "github.com", 
    "gitlab.com", 
    "bitbucket.org", 
    "dev.azure.com", 
    "visualstudio.com", 
    "sourceforge.net"
}
class RepoFile:
    def __init__(self, name, path):
        self.name = name 
        self.path = path 

def is_git_repo_web_url(url: str) -> bool:
    """
    Détermine intelligemment si une URL pointe vers un dépôt Git.
    Empêche le clonage de sites web classiques (ex: deepl.com).
    """
    u = (url or "").strip().lower()
    
    # 1. Règle d'Or : Si l'utilisateur a mis '.git' à la fin, c'est forcément un repo
    if u.endswith(".git"):
        return True

    try:
        p = urlparse(u)
    except Exception:
        return False

    if p.scheme not in ("http", "https") or not p.netloc: 
        return False
    
    # Pas de paramètres de requête (?q=...) ou d'ancres (#...)
    if p.query or p.fragment: 
        return False

    # 2. Vérification du Fournisseur (La protection Anti-DeepL)
    # Si le domaine n'est pas une forge connue (Github, Gitlab...), on rejette
    # SAUF si l'URL finissait par .git (géré au point 1)
    is_known_provider = False
    for provider in KNOWN_GIT_PROVIDERS:
        if provider in p.netloc:
            is_known_provider = True
            break
    
    if not is_known_provider:
        # C'est un site inconnu (ex: google.com, deepl.com). 
        # On ne prend pas le risque de cloner.
        return False

    # 3. Analyse structurelle (Vos filtres existants)
    parts = [seg for seg in p.path.strip("/").split("/") if seg]
    
    # Un repo sur Github/Gitlab a généralement au moins 2 segments : /user/repo
    if len(parts) < 2: 
        return False

    # On vérifie si un segment de l'URL est interdit (ex: /issues, /wiki)
    for seg in parts:
        if seg in NON_REPO_SEGMENTS or seg == "-": 
            return False

    return True

def clone_git_repo(repo_url):
    try:
        parsed_path = urlparse(repo_url).path
        repo_name = parsed_path.strip('/').split('/')[-1]
        if repo_name.endswith('.git'): repo_name = repo_name[:-4]  
        if not repo_name: repo_name = "unknown_repo"

        base_temp = tempfile.gettempdir()
        target_dir = os.path.join(base_temp, "cyber_supervisor_repos", repo_name)

        if os.path.exists(target_dir): shutil.rmtree(target_dir)

        os.makedirs(os.path.dirname(target_dir), exist_ok=True)
        cmd = ["git", "clone", "--depth", "1", repo_url, target_dir]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return target_dir, None

    except subprocess.CalledProcessError:
        return None, "Erreur 'git clone'. Vérifiez l'URL ou que le dépôt est public."
    except Exception as e:
        return None, f"Erreur système : {str(e)}"

def get_files_from_repo(repo_path):
    repo_files = []
    
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS]
            
        for filename in files:
            if any(banned in filename.lower() for banned in IGNORED_FILES): continue
            if filename.endswith((".min.js", ".min.css", ".map")): continue

            full_path = os.path.join(root, filename)
            
            # Calcul du chemin relatif
            rel_path = os.path.relpath(full_path, repo_path)
            
            safe_name = rel_path.replace("\\", "__SEP__").replace("/", "__SEP__")
            
            obj = RepoFile(name=safe_name, path=full_path)
            repo_files.append(obj)
            
    return repo_files

def remove_readonly(func, path, _):
    """
    Gestionnaire d'erreur pour shutil.rmtree sur Windows.
    Si un fichier (comme .git) est en lecture seule, on force l'écriture avant de supprimer.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        print(f"⚠️ Impossible de forcer la suppression de {path}: {e}")
        
def cleanup_repo(path):
    if path and os.path.exists(path):
        try: shutil.rmtree(path,onerror=remove_readonly)
        except Exception as e: print(f"⚠️ Erreur nettoyage {path}: {e}")