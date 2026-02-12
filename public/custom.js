console.log("🚀 [AUTO-SCROLL V11] Radar de Navigation Actif.");

let isInitPhase = false;
let initTimer = null;
let isUserAtBottom = true;
let lastUrl = window.location.href; // On mémorise l'URL actuelle

// --- 1. FONCTIONS DE SCROLL (Les Muscles) ---
const getScrollCandidates = () => {
    // On cible large puis on filtre
    const candidates = document.querySelectorAll('.flex-grow.overflow-y-auto');
    return Array.from(candidates).filter(el => el.clientWidth > 300);
};

const performScroll = (force = false) => {
    const targets = getScrollCandidates();
    if (targets.length === 0) return;

    targets.forEach((container) => {
        // Est-ce qu'il y a de la matière à scroller ?
        const canScroll = container.scrollHeight > container.clientHeight;
        
        if (canScroll || force) {
            // Méthode 1 : Direct
            container.scrollTop = container.scrollHeight;
            
            // Méthode 2 : Vise le dernier élément (pour les boutons)
            const lastChild = container.lastElementChild;
            if (lastChild) {
                lastChild.scrollIntoView({ block: "end", behavior: "auto" });
            }
        }
    });
};

// --- 2. LA PHASE INIT (Le Rouleau Compresseur - 2 secondes) ---
const triggerInitPhase = () => {
    // console.log("🔄 INIT : Force Scroll activé pour 2 secondes...");
    isInitPhase = true;
    isUserAtBottom = true; // On part du principe qu'on veut voir le bas
    
    if (initTimer) clearInterval(initTimer);

    let ticks = 0;
    initTimer = setInterval(() => {
        performScroll(true); // On force
        ticks++;
        if (ticks > 2) { 
            clearInterval(initTimer);
            isInitPhase = false;
            // console.log("🔓 INIT : Terminé.");
        }
    }, 100);
};

// --- 3. LE RADAR D'URL (Pour l'historique) ---
// C'est ce qui manquait : on vérifie l'URL 5 fois par seconde
setInterval(() => {
    const currentUrl = window.location.href;
    if (currentUrl !== lastUrl) {
        lastUrl = currentUrl;
        console.log("🌍 Changement de Chat détecté via URL -> Lancement Init");
        triggerInitPhase();
    }
}, 200);


// --- 4. OBSERVATEUR (Pour les nouveaux messages en direct) ---
const observer = new MutationObserver((mutations) => {
    const hasNewContent = mutations.some(record => record.addedNodes.length > 0);

    if (hasNewContent) {
        // Si on est en phase init OU que l'utilisateur suivait la conversation
        if (isInitPhase || isUserAtBottom) {
             performScroll();
        }
    }
});

// --- 5. SMART LOCK (Gestion du scroll manuel) ---
const attachScrollListeners = () => {
    const targets = getScrollCandidates();
    targets.forEach(container => {
        if (container.dataset.hasScrollListener === "true") return;
        
        container.dataset.hasScrollListener = "true";
        container.addEventListener('scroll', () => {
            if (isInitPhase) return; // On ignore pendant l'init

            const distance = container.scrollHeight - container.scrollTop - container.clientHeight;
            // Si l'utilisateur remonte de plus de 100px
            if (distance > 100) {
                isUserAtBottom = false;
            } else {
                isUserAtBottom = true;
            }
        });
    });
};

// --- DÉMARRAGE ---
window.addEventListener('load', () => {
    setTimeout(() => {
        const body = document.body;
        observer.observe(body, { childList: true, subtree: true });
        
        // 1. Init au chargement F5
        triggerInitPhase();
        
        // 2. Vérification continue des listeners (car React recrée les divs)
        setInterval(attachScrollListeners, 1000);
        
    }, 500);
});