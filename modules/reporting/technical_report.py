from datetime import datetime
import os
import re
import tempfile
from fpdf import FPDF

def clean_text_for_pdf(text):
    """Nettoyage des caractères pour FPDF (Latin-1)."""
    replacements = {
        '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', 
        '\u2013': '-', '\u2014': '-', '…': '...',
        '[CRITIQUE]': '🔴', '[IMPORTANT]': '🟠', '[MODÉRÉ]': '🟡', '[ROBUSTE]': '🟢',
        '🛡️': '', '🚨': '', '🎯': '', '🛠️': '', '●': '-'
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    try:
        return text.encode('latin-1', 'replace').decode('latin-1')
    except:
        return text

class ModernPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
    
    def header(self):
        self.set_fill_color(13, 26, 71)
        self.rect(0, 0, 210, 20, 'F')
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(255, 255, 255)
        self.set_y(5)
        self.cell(0, 10, 'Audit de sécurité et remédiation technique', 0, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()} - [Confidentiel] Rapport de sécurité généré par l\'IA, Veuillez vérifier les informations importantes.', 0, 0, 'C')

    def chapter_heading(self, title):
        """Titres : I. , 1. , # """
        self.ln(5)
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(24, 49, 136)
        #clean = title.replace("#", "").strip().upper()
        clean = title.replace("#", "").strip()
        self.multi_cell(0, 8, clean_text_for_pdf(clean), 0, 'L')
        self.ln(3)

    def sub_heading(self, title):
        """Sous-titres : A. , B. """
        self.ln(4)
        self.set_font('Helvetica', 'B', 14)
        self.set_text_color(32, 65, 181)
        clean = title.strip()
        self.cell(0, 8, clean_text_for_pdf(clean), 0, 1, 'L')
        self.set_draw_color(41, 128, 185)
        self.line(self.get_x(), self.get_y(), self.get_x() + 50, self.get_y())
        self.ln(4)

    def sub_sub_heading(self, label, text):
    #"""Style pour les titres type a. b. c. (Indice Bleu/Gras, Texte Noir/Normal)"""
        self.set_x(15)  # Indentation
        # --- L'INDICE (ex: a.) ---
        self.set_font('Helvetica', 'I', 13)

        self.set_text_color(41, 128, 185)  # Bleu

        self.write(8, f"{label} ") # On utilise write pour rester sur la même ligne
        # --- LE TEXTE DE LA LISTE ---
        self.set_font('Helvetica', 'I', 13) # On enlève le gras
        self.set_text_color(41, 128, 185)  # Bleu
        self.multi_cell(0, 8, text)        # multi_cell gère les longs paragraphes
        self.ln(2) # Petit espace après le paragraphe

    # Vérifiez aussi que vous avez bien cette méthode pour le Gras Markdown 
    
    
    def triple_hash_heading(self, title):
        """Sous-sous-titres : ### """
        self.ln(2)
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(52, 73, 94)
        clean = title.replace("###", "").strip()
        self.cell(0, 8, clean_text_for_pdf(clean), 0, 1, 'L')
        self.ln(1)

    def smart_write_bold(self, text, size=12, indent=0):
        """Détecte les ** à l'intérieur d'une ligne et applique le gras."""
        if indent > 0: self.set_x(indent)
        
        # On découpe la ligne par les balises **
        parts = re.split(r'(\*\*.*?\*\*)', text)
        
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                self.set_font('Helvetica', 'B', size)
                clean_part = part.replace('**', '')
                self.write(5, clean_text_for_pdf(clean_part))
            else:
                self.set_font('Helvetica', '', size)
                self.write(5, clean_text_for_pdf(part))
        self.ln(6)

    def code_block(self, code):
        self.ln(2)
        self.set_font('Courier', '', 12) 
        self.set_fill_color(245, 245, 245)
        self.set_draw_color(180, 180, 180)
        self.multi_cell(0, 4, clean_text_for_pdf(code), border=1, fill=True)
        self.ln(3)
def parse_and_write_pdf(pdf, full_text):
    # Séparation par blocs de code
    parts = re.split(r'(```.*?```)', full_text, flags=re.DOTALL)
    for part in parts:
        if part.startswith('```'):
            # 1. Nettoyage initial : on retire les ``` et les espaces autour
            content = part.replace('```', '').strip()
            # 2. Gestion de la balise de langage (ex: ```python)
            # On regarde la première ligne. Si elle est très courte (ex: "python"), 
            # c'est probablement l'identifiant du langage, donc on le retire.
            if '\n' in content:
                first_line = content.split('\n', 1)[0].strip()
                # Si la première ligne fait moins de 15 caractères et ne contient pas d'espace
                if len(first_line) < 15 and ' ' not in first_line:
                    # On ne garde que ce qu'il y a après le premier saut de ligne
                    content = content.split('\n', 1)[1]
            # 3. Appel de ta méthode personnalisée
            # .strip() final pour éviter d'avoir des sauts de ligne vides en haut/bas du cadre gris
            pdf.code_block(content.strip())
        else:
            lines = part.split('\n')
            for line in lines:
                line = line.strip()
                if "synthèse exécutive" in line.lower() and len(line) < 30:
                # On force le formatage exact attendu par la Regex (AVEC L'ESPACE après le point)
                    line = "I. Synthèse exécutive"
                if not line: continue
                
                # 1. SAUT DE PAGE (Séparateur ---)
                if "---" in line:
                    if pdf.get_y() > 40:
                        pdf.add_page()
                
                elif " ### REPONSE_FINALE" in line:
                    print("REPONSE FINALE FILTREE !")
                    line = ""
                    
                
                # 2. GRANDS TITRES (I. , 1. , # ) - Regex robuste pour les chiffres romains et arabes
                elif re.match(r'^([IVX]+\.|[\d]+\.)\s', line) or (line.startswith("# ")) and not (line.startswith("###")) or (line.startswith("##")) :
                    pdf.chapter_heading(line)
                
                # 3. SOUS-SOUS-TITRES ( ### )
                elif line.startswith("###")  and not (line.startswith("##")) :
                    pdf.triple_hash_heading(line)

                # 4. SOUS-TITRES MAJUSCULES (A., B., C.)
                elif re.match(r'^[A-Z]\.\s', line):
                    pdf.sub_heading(line)

                # 5. LISTES ET TEXTES AVEC GRAS (Détecte si la ligne contient **)
                elif "**" in line:
                    pdf.set_text_color(50, 50, 50)
                    # Si c'est une liste à puces
                    if line.startswith(('-', '*', '•')):
                        pdf.smart_write_bold(line, indent=15)
                    else:
                        pdf.smart_write_bold(line, indent=10)
                
                # 3. SOUS-TITRES MINUSCULES (a., b., c.) -> Ressources & Liens
                elif match := re.match(r'^([a-z]\.)\s+(.*)', line):
                    pdf.sub_sub_heading(match.group(1), match.group(2))
                
                # 6. CAS PARTICULIER : URL
                elif line.upper().startswith("URL:"):
                    pdf.set_text_color(50, 50, 50)
                    pdf.set_font('Helvetica', 'I', 12)
                    pdf.set_x(15)
                    pdf.cell(0, 5, clean_text_for_pdf(f"- {line.split(':', 1)[1].strip()}"), 0, 1)
                
                # 7. TEXTE STANDARD (Sans gras)
                else: 
                    pdf.set_text_color(50, 50, 50)
                    pdf.set_font('Helvetica', '', 12)
                    pdf.multi_cell(0, 5, clean_text_for_pdf(line))
                    pdf.ln(1)

def generate_technical_pdf(sections_list, target_url):
    pdf = ModernPDF()
    pdf.add_page()
    
    # Page de garde
    pdf.set_font('Helvetica', 'B', 22)
    pdf.ln(60)
    pdf.cell(0, 10, clean_text_for_pdf("Audit de sécurité et remédiation technique"), 0, 1, 'C')
    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(41, 128, 185)
    pdf.cell(0, 10, clean_text_for_pdf(f"CIBLE : {target_url}"), 0, 1, 'C')
    pdf.ln(5)
    pdf.set_font('Helvetica', 'I', 13)
    pdf.set_text_color(122, 0, 19)
    pdf.cell(0, 10, clean_text_for_pdf("Rapport généré par l'IA. Veuillez vérifiez les informations importantes"), 0, 1, 'C')
    pdf.set_font('Helvetica', 'B', 22)
    # Petite dédicace aux membres du projet
    pdf.ln(60)
    pdf.set_font('Arial', 'B', 22)
    pdf.set_text_color(32, 132, 140)
    # pdf.cell(0, 10, clean_text_for_pdf("[PFE-T-480] (Le meilleur groupe du PFE)"), 0, 1, 'C')
    #
    
    for section in sections_list:
        pdf.add_page()
        parse_and_write_pdf(pdf, section)
            
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        # FPDF écrit directement dans le chemin du fichier temporaire
        pdf.output(tmp_file.name)
        
        # On retourne le chemin absolu du fichier temporaire (ex: C:\Users\...\AppData\Local\Temp\tmp8x7s.pdf)
        return tmp_file.name