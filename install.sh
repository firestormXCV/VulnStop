#!/bin/bash

# --- COULEURS ---
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

clear
echo -e "${CYAN}############################################################${NC}"
echo -e "${CYAN}#        🛡️  CYBER-SUPERVISOR - INSTALLATEUR COMPLET       #${NC}"
echo -e "${CYAN}############################################################${NC}"
echo ""

# --- 1. VERIFICATION OS ---
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${YELLOW}⚠️  Attention : Script optimisé pour Linux.${NC}"
    read -p "Continuer ? (o/n) " os_choice
    if [[ "$os_choice" != "o" ]]; then exit 1; fi
fi

# --- 2. DEPENDANCES SYSTEME ---
echo -e "\n${BLUE}[1/5] 🛠️  Vérification système...${NC}"

if ! command -v sudo &> /dev/null; then
    echo -e "${RED}❌ 'sudo' n'est pas installé. Veuillez l'installer ou lancer en root.${NC}"
    exit 1
fi

dependencies=("git" "docker" "curl")
missing_deps=()

for cmd in "${dependencies[@]}"; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}❌ $cmd manquant.${NC}"
        missing_deps+=($cmd)
    else
        echo -e "${GREEN}✅ $cmd présent.${NC}"
    fi
done

if [ ${#missing_deps[@]} -ne 0 ]; then
    echo -e "${YELLOW}📦 Installation de : ${missing_deps[*]}...${NC}"
    sudo apt-get update
    sudo apt-get install -y "${missing_deps[@]}"
fi

echo -e "${YELLOW}🔍 Vérification des modules Python...${NC}"

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
VENV_PACKAGE="python${PY_VERSION}-venv"

echo -e "ℹ️  Version Python détectée : $PY_VERSION (Paquet requis: $VENV_PACKAGE)"

sudo apt-get update
sudo apt-get install -y python3-pip python3-venv "$VENV_PACKAGE"

if [ $? -ne 0 ]; then
    echo -e "${RED}⚠️  Impossible d'installer $VENV_PACKAGE automatiquement.${NC}"
    echo -e "Essai avec le paquet générique python3-venv..."
    sudo apt-get install -y python3-venv
fi

# --- 3. PYTHON ET VIRTUALENV ---
echo -e "\n${BLUE}[2/5] 🐍 Environnement Python...${NC}"

if [ -d "venv" ] && [ ! -f "venv/bin/activate" ]; then
    echo -e "${YELLOW}Nettoyage de l'ancien environnement virtuel corrompu...${NC}"
    rm -rf venv
fi

if [ ! -d "venv" ]; then 
    echo -e "Création de l'environnement virtuel..."
    python3 -m venv venv
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ ERREUR FATALE : Impossible de créer le venv.${NC}"
        echo -e "Veuillez exécuter manuellement : sudo apt install python${PY_VERSION}-venv"
        exit 1
    fi
fi

source venv/bin/activate

if ! command -v pip &> /dev/null; then
    echo -e "${RED}❌ Pip n'est pas disponible dans le venv.${NC}"
    echo -e "Tentative de réparation avec ensurepip..."
    python3 -m ensurepip --upgrade
fi

pip install --upgrade pip > /dev/null 2>&1

if [ -f "requirements.txt" ]; then
    echo -e "Installation des dépendances (cela peut prendre un moment)..."
    pip install -r requirements.txt
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Dépendances Python installées.${NC}"
    else
        echo -e "${RED}❌ Erreur lors de l'installation des dépendances.${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ requirements.txt introuvable !${NC}"
    exit 1
fi

# --- 4. CONFIGURATION .ENV ---
echo -e "\n${BLUE}[3/5] 🔑 Configuration API (.env)...${NC}"
CHAINLIT_SECRET=$(openssl rand -base64 32)
ENV_FILE=".env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "Configuration des clés :"
    select provider in "[gemini]" "[grok]"; do
        case $provider in
            "[gemini]") 
                LLM="gemini-2.5-flash"; read -p "Clé API GEMINI : " KEY; GEMINI_KEY=$KEY; GROQ_KEY=""; break;;
            "[grok]") 
                LLM="grok"; read -p "Clé API GROQ : " KEY; GROQ_KEY=$KEY; GEMINI_KEY=""; break;;
        esac
    done

    ZAP_KEY=$(date +%s | sha256sum | base64 | head -c 32)
    
    cat > $ENV_FILE <<EOL
LLM_PROVIDER=$LLM
GEMINI_API_KEY=$GEMINI_KEY
GROQ_API_KEY=$GROQ_KEY
ZAP_API_KEY=$ZAP_KEY
ZAP_PROXY=http://127.0.0.1:8080
CHAINLIT_AUTH_SECRET=$CHAINLIT_SECRET
EOL
echo -e "${GREEN}✅ .env généré avec succès (Secrets inclus).${NC}"
else
    echo -e "ℹ️  Fichier .env existant détecté."
    # Vérifie si le secret chainlit manque et l'ajoute si nécessaire
    if ! grep -q "CHAINLIT_AUTH_SECRET" "$ENV_FILE"; then
        echo -e "${YELLOW}Ajout du secret Chainlit manquant...${NC}"
        echo "CHAINLIT_AUTH_SECRET=$CHAINLIT_SECRET" >> "$ENV_FILE"
    fi
fi
# --- 5. CONFIGURATION CADDY (HTTPS) ---
echo -e "\n${BLUE}[4/5] 🔒 Configuration Web (Caddy/HTTPS)...${NC}"
CADDY_FILE="Caddyfile"

echo -e "Voulez-vous rendre l'application accessible depuis internet (HTTPS) ?"
read -p "Avez-vous un nom de domaine (ex: pfe-480.duckdns.org) ? (o/n) " has_domain

if [[ "$has_domain" == "o" ]]; then
    read -p "👉 Entrez votre nom de domaine : " DOMAIN_NAME
    
    cat > $CADDY_FILE <<EOL
$DOMAIN_NAME {
    reverse_proxy app:8000
}
EOL
    echo -e "${GREEN}✅ Caddyfile configuré pour $DOMAIN_NAME (HTTPS Auto).${NC}"

else
    echo -e "${YELLOW}Configuration en mode local uniquement.${NC}"
    cat > $CADDY_FILE <<EOL
:80 {
    reverse_proxy app:8000
}
EOL
    echo -e "${GREEN}✅ Caddyfile configuré pour localhost (:80).${NC}"
fi

# --- 6. LANCEMENT ---
echo -e "\n${BLUE}[5/5] 🚀 Lancement...${NC}"
read -p "Lancer toute l'infrastructure (App + ZAP + Caddy) via Docker maintenant ? (o/n) " launch

if [[ "$launch" == "o" ]]; then
    export ZAP_API_KEY=$(grep ZAP_API_KEY .env | cut -d '=' -f2)
    
    if command -v docker-compose &> /dev/null; then CMD="docker-compose"; else CMD="docker compose"; fi
    
    echo -e "Construction et démarrage..."
    $CMD up -d --build
    
    echo -e "\n${GREEN}✅ TOUT EST PRÊT !${NC}"
    if [[ "$has_domain" == "o" ]]; then
        echo -e "👉 Accès : https://$DOMAIN_NAME"
    else
        echo -e "👉 Accès : http://localhost"
    fi
else
    echo -e "${GREEN}Installation terminée.${NC}"
    echo -e "Pour lancer plus tard : docker-compose up -d --build"
fi

chmod +x "$0"