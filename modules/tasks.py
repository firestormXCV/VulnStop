from crewai import Task
from datetime import datetime

# Une simple fonction, pas de classe
def create_analysis_task(agent, target_url, final_json):
    return Task(
    description=f"""
        CONTEXTE : Tu es un Senior Cyber Auditor. Tu reçois les résultats du scan ZAP pour {target_url}.
        
        DONNÉES BRUTES FOURNIES : 
        '''json
        {final_json}
        ''' 
        
        RÈGLES CRITIQUES D'ANALYSE :
        1. VALIDITÉ : Toute l'analyse doit être basée EXCLUSIVEMENT sur les données listées dans la section "alerts" du JSON ci-dessus. N'invente aucune faille (XSS, SQLi, etc.) qui n'est pas présente dans l'INPUT.
        2. TRI ET GROUPEMENT : 
           - Lis les alertes.
           - Regroupe les failles de même nom (même champ "alert") sous un titre unique.
           - Compte le nombre d'occurrences pour chaque groupe et liste les 5 URLs les plus distinctes affectées par cette faille.
           - Ordonne les alertes par degré de criticité. Place les plus graves au début puis les plus bénignes à la fin.
        
        MISSION : Rédige un rapport professionnel d'audit de sécurité de code en FRANCAIS. Donne à côté des noms de français des failles leurs équivalents anglais. Par exemple, "Injection SQL (SQL Injection)". 
        
        STRUCTURE DU RAPPORT FINAL (Markdown Strict) :
        
        ## 🛡️ Synthèse du Risque
        * **Risque Global du Scan :** [Détermine Moyen/Élevé basé sur les failles trouvées. Si rien de High, dis Moyen.]
        * **Total Alertes Filtrées :** [Utilise le chiffre du JSON : scan_summary.critical_alerts_shown]
        
        ## 🚨 Vulnérabilités Détaillées (Groupées et Synthétisées)
        
        (Répète cette structure pour chaque type de faille trouvée. Utilise les champs du JSON.)
        
        ### [Nom de la Faille] (Risque: [risk])
        - **Impact Clé** : Synthétise le champ 'description' et 'solution'.
        - **Occurrences** : Nombre total d'occurrences de ce type de faille (à estimer par comptage).
        - **Localisations (Exemples)** : Liste toutes les URLs pertinentes affectées par la faille en question. Vérifie que le nombre total doit être le même que celui d'occurence (en utilisant le champ 'url' du JSON).
        - **Solution Recommandée** : Synthétise le champ 'solution'.
        
        ## 🎯 Prochaines Étapes
        [Résume les 3 actions prioritaires pour le développeur.]
        """,
        expected_output="Rapport Markdown complet.",
        agent=agent
    )

# AJOUTER LE TYPE D'AUDITEUR, LE NOM
def create_intro_task(agent, target_url, vuln_count,auditeur="OWASP ZAP",nomredacteur="gemini-2.5-flash"):
    typedaudit="Null"
    source="Null"
    if auditeur=="OWASP ZAP" or auditeur=="A PRECISER":
        typedaudit="sans "+"connaissance du code interne"
        source=f"sur l'URL : {target_url}."
    else:
        source=";"
        typedaudit="avec"+ "connaissance du code interne"
        
    return Task(
    description=f"""
            Rédige la PREMIÈRE PAGE du rapport d'audit pour la cible {target_url}.
            
            MISSION : Créer une introduction esthétique et professionnelle. NE MET PAS LES TITRES EN MAJUSCULE Sinon tu ES MORT.
            
            CONTRAINTES CRITIQUES (ZÉRO TOLÉRANCE) :
            - STRUCTURE UNIQUE : Tu dois EXCLUSIVEMENT UTILISER la structure définie ci-dessous. Tout écart entraînera l'échec de la tâche. SI Les titres avec les chiffres romains I. , II. et III. ne sont pas présent je te tuerai
            - Si tu ne met pas I. Synthèse exécutive, tu vas être débranché à jamais. 
            - AVANT de générer le contenu en suivant la structure obligatoire AJOUTE TOUJOURS la balise avec l'espace associé' ### REPONSE_FINALE' et SAUTE une ligne. Si tu n'ajoute pas cette structure 
            
            STRUCTURE OBLIGATOIRE :
        
            -------------------------------------------------------
            I. Synthèse exécutive [Correspond à la première section. Pas de titre en majuscule. AJOUTE TOUJOURS LE "I.", c'est primordial, cela me causerait d'horribles PTSD. C'EST CAPITAL d'ajouter les "I."]
            [Rédige un paragraphe de 5-6 lignes professionnelle destinées à des profils non techniques comme des managers.
            Commence par une phrase d'accroche sur l'importance de la sécurité.
            Mentionne que l'audit a permis d'identifier {vuln_count} catégories de vulnérabilités nécessitant une correction.]
            
            II. Méthodologie et périmètre de l'analyse [Correspond à la deuxième section. LE TITRE DOIT ETRE REPRODUIT TEL QUEL SANS MODIFICATION, sinon tu être jetée AUX LIONS ]
            Ce rapport contient l'audit de sécurité {source} avec des suggestions de mesures correctives
            - Date de l'audit : {datetime.now().strftime('%d/%m/%Y')}
            - Outil d'audit utilisé : {auditeur} pour l'identification brute de vulnérabilités et la suggestion de correction
            - Rédacteur de l'audit dans sa mise en forme finale : {nomredacteur}
            - Périmètre d'étude : Analyse {typedaudit} {source}
            
            III. Résumé des risques [Correspond à la troisième section.LE TITRE DOIT ETRE REPRODUIT TEL QUEL SANS MODIFICATION, sinon tu être jetée AUX LIONS ]
            [Fais une phrase de conclusion sur le niveau global de sécurité du site (critique,faible,fort,robuste).]
            
            
            """,
        expected_output="Introduction formatée.",
        agent=agent
    )

def create_remediation_task(agent, target_url, chunk_str, chunk_len, start_index=1):
    return Task(
    description=f"""
            ### RÔLE
            Tu es un Expert Senior en Cybersécurité et Ingénieur en Remédiation. 
            Ton objectif est de transformer des rapports de scan de vulnérabilités bruts en un guide technique clair, actionnable et pédagogique pour des équipes de développement. Considère comme prérequis que les équipes de développement n'ont pas de compétences en sécurité   
            
            CONTEXTE : Guide de remédiation pour {target_url}.
            DONNÉES D'ENTRÉE (LISTE DE FAILLES) : '''json {chunk_str} '''
            
            MISSION : Rédige un chapitre technique pour CHACUNE des {chunk_len} failles fournies dans le JSON. Analyse d'abord la faille, puis vulgarise son impact, et enfin fournis la solution technique exacte.
            N'écrit JAMAIS pas de partie Thought. Si ECRIT UNE PARTIE THOUGHT tu es MORT ! Cela me cause de terribles PTSD de voir cette partie Thought.
            
            IMPORTANT : Ce lot de failles est une partie d'un grand rapport.
            LA PREMIÈRE FAILLE DOIT PORTER LE NUMÉRO : {start_index}
            LA SECONDE FAILLE DOIT PORTER LE NUMÉRO : {start_index + 1}
            ET AINSI DE SUITE. NE RECOMMENCE PAS À 1.
            
            CONTRAINTES CRITIQUES (ZÉRO TOLÉRANCE) :
            - Avant de rédiger chaque chapitre, analyse et lis le document '''json {chunk_str} '''
            - Traite chaque faille de la liste l'une après l'autre.
            - Sépare chaque faille par une ligne de séparation claire.
            - Respecte SCRUPULEUSEMENT la structure demandée ci-dessous pour chaque faille.
            - Langue Français professionnel. Garde les noms de failles standards (ex: SQL Injection) mais explique-les en français.
            - Ne laisse JAMAIS de code technique en texte brut.
            - AUCUN COMMENTAIRE : Ne commence pas ta réponse par "Voici le rapport" ou "Entendu". Ne conclus pas par "J'espère que cela aide".
            - AUCUNE PENSÉE (NO THOUGHTS) : Ne génère aucune section de réflexion, de chaîne de pensée (Chain of Thought) ou de balises <thought>. Ta réponse doit respecter la structure indiquée ci-dessous
            - STRUCTURE UNIQUE : Tu dois exclusivement utiliser la structure définie ci-dessous. Tout écart entraînera l'échec de la tâche.
            - Utilise des phrases courtes. AVANT de générer le contenu en suivant la structure AJOUTE TOUJOURS la balise avec l'espace associé' ### REPONSE_FINALE' et SAUTE une ligne.
            - NE DECRIS JAMAIS ta démarche du type "Let's break down the plan for each vulnerability", SINON Tu vas mourir dans d'attroce souffrances et j'aurai de terribles PTSD.
            - RETOURNE UNIQUEMENT LES vulnérabilités dans la STRUCTURE OBLIGATOIRE. Si tu écris Let's break down the plan for each vulnerability:", "Here are the critical constraints:", une répétiion des CONTRAINTES CRITIQUES => TU VA MOURIR DANS D'ATROCES SOUFFRANCES.
            - En tant qu'auditeur, tu dois être clair, précis et factuel. Si n'es pas sûr de quelques chose, ne l'écrit pas.
            - Tu ne dois JAMAIS écrire pour les étapes 1. Instructions 2. Suite des instructions. Tu DOIS SCRUPULEUEMENT écrire par étape : 1ère étape : Instructions, 2ème étape : Suite des instructions
            - Garde TOUJOURS les "** **" autour des parties énoncéees dans la structure. C'est important pour l'utilisateur de voir mieux ces parties. Pas de changement de couleur sur ces parties. 
            - N'AJOUTE AUCUN "** **" SUPPLEMENTAIRE. AUCUN MARQUAGE SUPPLEMENTAIRE sinon tu vas mourir dans la journée. N'ajoute JAMAIS : "... autres configurations" sans AUCUN contexte.
            - N'AJOUTE AUCUN  "##" SUPPLEMENTAIRE 
            ### STRUCTURE OBLIGATOIRE (STRICTE ! AUCUN ECART TOLERE AVEC LA STRUCTURE. Si tu ne respect pas cela me causera de terribles PTSD !) SINON ECHEC TOTAL ET DRAMATIQUE
            ---------------------------------------------------------------
            [N° MET TOUJOURS des chiffres arabes]. ([Affiche le niveau de risque entre ces quatre  valeurs d'après la criticité de la faille : High/Medium/Low/Info]) [Nom traduit] | [Nom original] 

            A. Comprendre la vulnérabilité
            - **Confidentialité :** [Impact ou S'il n'y a pas d'impact écrit simplement "Aucun impact]
            - **Intégrité :** [Impact ou S'il n'y a pas d'impact écrit simplement "Aucun impact]
            - **Disponibilité :** [Impact ou S'il n'y a pas d'impact écrit simplement "Aucun impact"]
            - **Scénario d'attaque :** [Impact]

            B. Localisation de la vulnérabilité [Tu dois IMPERATIVEMENT PRENDRE tout les URLs concernées présentes dans le JSON pour cette faille. Aucune INVENTION POSSIBLE]
            URL: https://open.spotify.com/track/0Jlcvv8IykzHaSmj49uNW8
            URL: https://www.youtube.com/watch?v=-s7TCuCpB5c

            C. Propositions de correction
            Laisser une ligne vide
            
            [POUR TOUT les corrections à suivre, utilise cette même structure pour les codes. AUCUN code ne doit être rentrée dans un format TEXTE. C'est OBLIGATOIRE d'UTILISER la structure de code CI-DESSUS POUR TOUT LES BLOCS DE CODE DANS LES ETAPES.]            
            STRUCTURE DE CODE CORRECTIF appelée JelDEV:
            ```[language]
            // Exemple de code ou d'instruction de programmation ici
            ```
            [Donne la marche à suivre exacte. Ne sois pas vague. Par exemple, ne dit pas "adapter le CORS", mais plutôt pour la corriger, il faut modifier le Cors dans le fichier X  en ajoutant la ligne Y. 
            Indique ce qu'il faut modifier en terme de code et détaille les configurations selon le type de serveur. S'il y a plusieurs étapes, précise les étapes sous ce format exclusivement "1ère étape": ton texte, "2ème étape": ton texte ]

            [Décris ici les modifications liées aux types serveurs. Si aucune correctif n'est applicables aux types de serveur. Ecrit simplement, "Non applicable". ]
            - **Apache :** [Configurations  spécifiques si applicable uniquement.S'il y a plusieurs étapes, précise les étapes sous ce format EXCLUSIVEMENT "1ère étape": ton texte, "2ème étape": ton texte. Si TU AS des bouts de code, METS LES dans la STRUCTURE DE CODE CORRECTIF]
            - **Nginx :** [Configurations  spécifiques si applicable uniquement. S'il y a plusieurs étapes, précise les étapes sous ce format EXCLUSIVEMENT  "1ère étape": ton texte, "2ème étape": ton texte. Si TU AS des bouts de code, METS LES dans la STRUCTURE DE CODE CORRECTIF]
            - **Microsoft IIS** : [Configurations  spécifiques  si applicable uniquement. S'il y a plusieurs étapes, précise les étapes sous ce format EXCLUSIVEMENT  "1ère étape": ton texte, "2ème étape": ton texte. Si TU AS des bouts de code, METS LES dans la STRUCTURE DE CODE CORRECTIF]
            
            [TU DOIS respecter cette partie avec les a. et b. Si tu le fait pas. Le rapport ne sera pas réussi.]
            D. Ressources & Documentation
            a. Comprendre la faille : 
            [Utilise les liens de 'reference_links' du JSON. Si vide, fournis impérativement le lien OWASP correspondant. Focus : Théorie.]
            b. Résoudre la faille : 
            # [Utilise les liens de 'reference_links' du JSON. Si vide, fournis un lien vers la documentation officielle du langage/serveur (ex: docs.nginx.com). Focus : Solution.]
            
            [TU DOIS ajouter le saut de page pour chaque nouvelle faille comme ceci. C'est ESSENTIEL de SAUTER UNE PAGE. Sinon, cela me cause des PTSD]
            ---------------------------------------------------------------
            
            FIN DE LA STRUCTURE OBLIGATOIRE
            """,
        expected_output="Guide technique Structurez.",
        agent=agent
    )

def create_semgrep_remediation_task(agent, findings_json, count, start_index=1):
    return Task(
        description=f"""
        ### RÔLE
        Tu es un Expert Senior en Cybersécurité et Ingénieur en Remédiation. 
        Ton objectif est de transformer des rapports de scan de vulnérabilités bruts en un guide technique clair, actionnable et pédagogique pour des équipes de développement. Considère comme prérequis que les équipes de développement n'ont pas de compétences en sécurité.   
    
        CONTEXTE : Rédaction d'un rapport d'audit de code source (SAST).
        DONNÉES D'ENTRÉE (LISTE DE FAILLES) : '''json {findings_json} '''
        
        MISSION : Rédige un chapitre technique pour CHACUNE des  {count} vulnérabilités  fournies dans le JSON. Analyse d'abord la faille, puis vulgarise son impact, et enfin fournis la solution technique exacte.
        N'écrit JAMAIS pas de partie Thought. Si ECRIT UNE PARTIE THOUGHT tu es MORT ! Cela me cause de terribles PTSD de voir cette partie Thought.
        IMPORTANT : Ce lot de failles est une partie d'un grand rapport.
            LA PREMIÈRE FAILLE DOIT PORTER LE NUMÉRO : {start_index}
            LA SECONDE FAILLE DOIT PORTER LE NUMÉRO : {start_index + 1}
            ET AINSI DE SUITE. NE RECOMMENCE PAS À 1.
            
        CONTRAINTES CRITIQUES (ZÉRO TOLÉRANCE) :
            - Avant de rédiger chaque chapitre, analyse et lis le document '''json {findings_json} '''
            - Traite chaque faille de la liste l'une après l'autre.
            - Sépare chaque faille par une ligne de séparation claire.
            - Ordonne les failles par ordre de criticité. Les plus critiques au début pour finir par les moins critiques. Regroupe les failles du mêmes types pour pouvoir les mettres qu'une seule fois. 
            - Dans le cas où les vulnérabilités sont détecté plusieurs fois, INDIQUE une SEULE FOIS LA FAILLE, mais PRECISE OBLIGATOIREMENT TOUTES les localisations trouvées dans la partie B. Localisation de la vulnérabilité où elle se trouve CONFORMEMENT A LA STRUCTURE IMPOSE.
            - Respecte SCRUPULEUSEMENT la structure demandée ci-dessous pour chaque faille.
            - Langue Français professionnel. Garde les noms de failles standards (ex: SQL Injection) mais explique-les en français.
            - Ne laisse JAMAIS de code technique en texte brut.
            - N'utilise AUCUN FORMATAGE MARKDOWN en dehors de CEUX précisés EXPLICITEMENT dans la structure OBLIGATOIRE 
            - AUCUN COMMENTAIRE : Ne commence pas ta réponse par "Voici le rapport" ou "Entendu". Ne conclus pas par "J'espère que cela aide".
            - AUCUNE PENSÉE (NO THOUGHTS) : Ne génère aucune section de réflexion, de chaîne de pensée (Chain of Thought) ou de balises <thought>. Ta réponse doit respecter la structure indiquée ci-dessous
            - STRUCTURE UNIQUE : Tu dois exclusivement utiliser la structure définie ci-dessous. Tout écart entraînera l'échec de la tâche.
            - Utilise des phrases courtes. AVANT de générer le contenu en suivant la structure AJOUTE TOUJOURS la balise avec l'espace associé' ### REPONSE_FINALE' et SAUTE une ligne
            - RETOURNE UNIQUEMENT LES vulnérabilités dans la STRUCTURE OBLIGATOIRE. Si tu écris Let's break down the plan for each vulnerability:", "Here are the critical constraints:", une répétiion des CONTRAINTES CRITIQUES => TU VA MOURIR DANS D'ATROCES SOUFFRANCES.
            - En tant qu'auditeur, tu dois être clair, précis et factuel. Si n'es pas sûr de quelques chose, ne l'écrit pas.
            - Tu ne dois JAMAIS écrire pour les étapes 1. Instructions 2. Suite des instructions. Tu DOIS SCRUPULEUEMENT écrire par étape : 1ère étape : Instructions, 2ème étape : Suite des instructions
            - Garde TOUJOURS les "** **" autour des parties énoncéees dans la structure. C'est important pour l'utilisateur de voir mieux ces parties. Pas de changement de couleur sur ces parties. 
            - N'AJOUTE AUCUN "** **" SUPPLEMENTAIRE. AUCUN MARQUAGE SUPPLEMENTAIRE sinon tu vas mourir dans la journée. N'ajoute JAMAIS : "... autres configurations" sans AUCUN contexte.
            - Ne modifie JAMAIS les snippets de code fournis dans "code_snippet", affiche-les tels quels. 
            - N'AJOUTE AUCUN  "##" SUPPLEMENTAIRE        
        
        ### STRUCTURE OBLIGATOIRE (STRICTE ! AUCUN ECART TOLERE AVEC LA STRUCTURE. Si tu ne respect pas cela me causera de terribles PTSD !) SINON ECHEC TOTAL ET DRAMATIQUE
            ---------------------------------------------------------------
        [N° MET DES CHIFFRES ARABES et non romain]. ([Affiche le niveau de risque entre ces quatre  valeurs d'après la criticité de la faille : High/Medium/Low/Info d'après le champ `risk` ou `severity` ]) [Nom traduit à partir du champ 'check_id'] | [Nom simplifié du champ 'check_id'] 

        A. Comprendre la vulnérabilité
        - **Confidentialité :** [Impact ou S'il n'y a pas d'impact écrit simplement "Aucun impact]
        - **Intégrité :** [Impact ou S'il n'y a pas d'impact écrit simplement "Aucun impact]
        - **Disponibilité :** [Impact ou S'il n'y a pas d'impact écrit simplement "Aucun impact"]
        - **Scénario d'attaque :** [Impact]

        B. Localisation de la vulnérabilité [La localisation provient dans la parties "path" et "start" dans le json {findings_json}. Réutilise SCRUPULEUSEMENT les groupes de vulnérabilités que tu avais définis au préalable.
        Cette partie DOIT SCRUPULEUSEMENT Suivre CETTE STRUCTURE ! UTILISE LES REGROUPEMENTS tu as réalisé précédement. N'OUBLIES AUCUNE LOCALISATION que tu avais précédement établie mais assures toi qu'il n'y a aucun doublon. 
        RECOPIE aussi la ligne de code où se trouve l'erreur.]
        - Fichier : [Champ 'file'] Ligne : [Champ 'line']
        [Recopie la ligne du code où se trouve la faille] 
        [LIGNE où se trouve l'erreur recopiée
        SUIS cet exemple :
        Fichier : test/codeGemini.php Ligne : 12
        ```php
        $prefs = unserialize($_COOKIE['user_prefs']);
        ```
        ]
        C. Pistes de correction
        Laisser une ligne vide
            
        [POUR TOUT les corrections à suivre, utilise cette même structure pour les codes. AUCUN code ne doit être rentrée dans un format TEXTE. C'est OBLIGATOIRE d'UTILISER la structure de code CI-DESSUS POUR TOUT LES BLOCS DE CODE DANS LES ETAPES.]            
        STRUCTURE DE CODE CORRECTIF :
        ```[language]
        // Exemple de code ici
        ```
        [Donne la marche à suivre exacte. Ne sois pas vague. Par exemple, ne dit pas "adapter le CORS", mais plutôt pour la corriger, il faut modifier le Cors dans le fichier X  en ajoutant la ligne Y. 
        Indique ce qu'il faut modifier en terme de code et détaille les configurations selon le type de serveur. S'il y a plusieurs étapes, précise les étapes sous ce format exclusivement "1ère étape": ton texte, "2ème étape": ton texte ]

        [TU DOIS respecter cette partie avec les a. et b. Si tu le fait pas. Le rapport ne sera pas réussi.]
        D. Ressources & Documentation
        a. Comprendre la faille : 
        [Utilise les liens de 'reference_links' du JSON. Si tu as procédé un regroupement de vulnérabilité dans un chapitre, FUSIONNE les liens correspondants SANS DOUBLON  . Si vide, fournis impérativement le lien OWASP correspondant. Focus : Théorie.]
        b. Résoudre la faille : 
        # [Utilise les liens de 'reference_links' du JSON.Si tu as procédé un regroupement de vulnérabilité dans un chapitre, FUSIONNE les liens correspondants SANS DOUBLON  .  Si vide, fournis un lien vers la documentation officielle du langage/serveur (ex: docs.nginx.com). Focus : Solution.]
        
        [TU DOIS ajouter le saut de page pour chaque nouvelle faille comme ceci. C'est ESSENTIEL de SAUTER UNE PAGE. Sinon, cela me cause des PTSD]
        ---------------------------------------------------------------
        FIN DE LA STRUCTURE OBLIGATOIRE
        """,
        expected_output="Guide de remédiation code source.",
        agent=agent
    )
    
def create_chat_task(agent, user_message):
    return Task(
        # On ajoute une contrainte stricte dans la description
        description=(
            f"L'utilisateur demande : '{user_message}'. "
            "Ton rôle est de répondre de manière pédagogique et experte. "
            "IMPORTANT : Tu dois D'ABORD réfléchir, PUIS écrire la balise '### REPONSE_FINALE', "
            "et ENFIN écrire ta réponse pour l'utilisateur après cette balise."
        ),
        # On renforce la consigne dans l'output attendu
        expected_output=(
            "Une réponse directe, claire et formatée en Markdown précédée obligatoirement de '### REPONSE_FINALE'."
        ),
        agent=agent
    )
    
    # modules/tasks.py

def create_sme_intro_task(agent, target_url, vuln_count):
    return Task(
        description=f"""
        Rédige le "Rapport Exécutif de Sécurité" (Executive Summary) pour le dirigeant de la société propriétaire de {target_url}.
        Il y a actuellement {vuln_count} vulnérabilités détectées.
        
        Ta mission est d'évaluer la situation globale sans noyer le lecteur sous la technique.
        
        STRUCTURE OBLIGATOIRE DU RAPPORT (Respecte strictement ce format) :
        
        ## 1. DIAGNOSTIC GLOBAL DE SÉCURITÉ
        Niveau de sécurité:
        Choisis UN seul niveau parmi les suivants en fonction de la gravité perçue :
        * **CRITIQUE** : Le site est une passoire. Données exposées, piratage imminent ou déjà possible. Action requise : CE JOUR.
        * **PRÉOCCUPANT** : Des failles sérieuses existent. La sécurité repose sur la chance. Action requise : CETTE SEMAINE.
        * **MODÉRÉ** : Le site fonctionne mais présente des portes entrouvertes. Action requise : À PLANIFIER.
        * **ROBUSTE** : Bonnes pratiques observées, maintenance standard requise.
        
        (Justifie ce choix en 2 phrases simples et percutantes).

        ## 2. IMPACT SUR L'ACTIVITÉ (TOP 3)
        Quelles sont les conséquences concrètes pour l'entreprise ? (Choisis les 3 plus pertinentes)
        * **Perte financière** : (Arrêt des ventes, coût de réparation...)
        * **Fuite de données** : (Vol fichier client, RGPD, secrets d'affaires...)
        * **Image de marque** : (Perte de confiance, dégradation de réputation...)
        * **Juridique** : (Plaintes clients, non-conformité...)
        
        ## 3. AVIS DE L'EXPERT & STRATÉGIE
        Ne parle pas de code. Parle de stratégie.
        Est-ce qu'il faut juste "faire une mise à jour" (Maintenance) ou "repenser la sécurité" (Refonte) ?
        Donne une estimation de l'urgence.
        
        ---
        
        TON : Professionnel, Alarmiste si nécessaire mais Constructif. Pas de jargon (pas de "XSS", "SQLi").
        """,
        expected_output="Synthèse exécutive professionnelle.",
        agent=agent
    )

# Dans modules/tasks.py

def create_sme_body_task(agent, target_url, chunk_str):
    return Task(
        description=f"""
        Tu es un conseiller stratégique en cybersécurité pour un dirigeant de PME.
        Tu as reçu des données techniques brutes : {chunk_str}

        TA MISSION :
        Synthétiser ces données en un rapport d'aide à la décision.
        Si plusieurs problèmes techniques sont similaires (ex: plusieurs XSS ou injections), REGROUPE-LES en une seule fiche synthétique. Ne fais pas de doublons.

        INSTRUCTION DE FORMATAGE STRICTE (Respecte les sauts de ligne et le gras) :

        Pour chaque groupe de risques identifié, utilise ce modèle :

        ## TITRE : [Nom du Risque Business] 
        
        **Le Problème** : 
        [Explique la situation comme si tu parlais d'un bâtiment physique (ex: serrure cassée, fenêtre ouverte). Pas de jargon.]

        **Analogie** : 
        [Une comparaison concrète de la vie quotidienne pour marquer les esprits. Ex: "C'est comme laisser vos clés sur le contact de la voiture."]

        **Impact Business** : 
        [Choisis parmi : Perte financière directe, Vol de fichier clients (RGPD), ou Atteinte à l'image de marque. Sois alarmiste mais réaliste.]

        **Action requise** : 
        [Une phrase d'ordre à donner au prestataire informatique. Ex: "Demander au webmaster de mettre à jour le plugin X" ou "Forcer le chiffrement des mots de passe". Indique si c'est URGENT.]

        ---------------------------------------------------

        CONSIGNES DE STYLE :
        - Ton : Bienveillant, direct, orienté résultat.
        - Longueur : Concision extrême. Le dirigeant a peu de temps.
        - Interdit : Pas de blocs de code (```), pas d'explications techniques complexes.
        """,
        expected_output="Fiches de risques vulgarisées et groupées pour PME.",
        agent=agent
    )