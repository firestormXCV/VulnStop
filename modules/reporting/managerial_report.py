import tempfile
from fpdf import FPDF
import os
import re
from datetime import datetime
from modules.utils import get_clean_filename_from_url

class ModernManagerialPDF(FPDF):
    def __init__(self, target_url):
        super().__init__()
        self.target_url = target_url
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_fill_color(44, 62, 80)
        self.rect(0, 0, 210, 20, 'F')
        
        self.set_font('Arial', 'B', 10)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 5)
        
        clean_url = self.target_url.replace('http://', '').replace('https://', '')[:40]
        self.cell(0, 10, f"AUDIT PME - {clean_url}", 0, 0, 'L')
        self.cell(0, 10, datetime.now().strftime("%d/%m/%Y"), 0, 0, 'R')
        self.ln(25)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def create_cover_page(self):
        self.add_page()
        self.set_fill_color(245, 247, 250)
        self.rect(0, 0, 210, 297, 'F')
        
        self.ln(60)
        self.set_font('Arial', 'B', 26)
        self.set_text_color(44, 62, 80)
        self.multi_cell(0, 12, "RAPPORT D'AUDIT\nCYBERSÉCURITÉ", 0, 'C')
        
        self.ln(20)
        self.set_draw_color(231, 76, 60)
        self.set_line_width(1)
        self.line(50, self.get_y(), 160, self.get_y())
        self.ln(20)
        
        self.set_font('Arial', '', 14)
        self.set_text_color(60, 60, 60)
        self.cell(0, 10, f"Cible analysée : {self.target_url}", 0, 1, 'C')
        
        self.set_y(-60)
        self.set_font('Arial', 'B', 10)
        self.set_text_color(200, 50, 50)
        self.cell(0, 10, "DOCUMENT CONFIDENTIEL - DIRECTION GÉNÉRALE", 0, 1, 'C')

    def add_section_title(self, title):
        """Ajoute un titre de section avec fond coloré et gestion multiligne propre."""
        self.ln(8) 
        self.set_font('Arial', 'B', 13)
        self.set_text_color(44, 62, 80)
        self.set_fill_color(230, 236, 240) # Gris bleuté
        
        clean_title = title.replace("#", "").strip().upper()
        
        # 1. Calcul de la hauteur nécessaire
        # On simule l'écriture pour savoir combien de lignes ça va prendre
        w_page = self.w - self.l_margin - self.r_margin
        # On garde une petite marge interne de 2mm à gauche et à droite pour le texte
        w_text = w_page - 4 
        
        # Astuce : on compte les lignes
        nb_lines = len(self.multi_cell(w_text, 8, clean_title, split_only=True))
        h_total = nb_lines * 8 + 4 # 8mm par ligne + 4mm de marge (padding haut/bas)
        
        # 2. Dessin du fond coloré (Rectangle)
        x_start = self.get_x()
        y_start = self.get_y()
        self.rect(x_start, y_start, w_page, h_total, 'F')
        
        # 3. Écriture du texte par dessus
        # On se décale un peu pour ne pas coller au bord gauche (Padding Left)
        self.set_xy(x_start + 2, y_start + 2) # +2mm X, +2mm Y
        self.multi_cell(w_text, 8, clean_title, 0, 'L')
        
        # 4. On replace le curseur après le bloc
        self.set_xy(self.l_margin, y_start + h_total)
        self.ln(2)

    def clean_text_for_pdf(self, text):
        """Nettoyage des caractères et Emojis pour FPDF (Latin-1)"""
        text = str(text)
        replacements = {
            '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"', 
            '\u2013': '-', '\u2014': '-', '…': '...',
            '●': '-', '•': '-'
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        
        return text.encode('latin-1', 'replace').decode('latin-1').strip()

    def add_colored_label(self, text):
        """Affiche toute la ligne avec la couleur détectée."""
        text_upper = text.upper()
        
        # Définition des couleurs (R, G, B)
        # Rouge = (231, 76, 60), Orange = (230, 126, 34), Jaune = (241, 196, 15), Vert = (39, 174, 96)
        
        if any(x in text_upper for x in ["CRITIQUE", "DANGER", "URGENT", "CE JOUR"]):
            self.set_text_color(231, 76, 60) # Rouge
        elif any(x in text_upper for x in ["PRÉOCCUPANT", "IMPORTANT", "ALERTE"]):
            self.set_text_color(230, 126, 34) # Orange
        elif "MODÉRÉ" in text_upper:
            self.set_text_color(241, 196, 15) # Jaune/Moutarde (lisible)
        elif any(x in text_upper for x in ["ROBUSTE", "SATISFAISANT", "OK"]):
            self.set_text_color(39, 174, 96) # Vert
        else:
            self.set_text_color(44, 62, 80) # Bleu par défaut

        # On écrit la ligne
        self.set_font('Arial', 'B', 12)
        
        # On nettoie les ** ou [] pour l'affichage final
        clean_display = text.replace("**", "").replace("[", "").replace("]", "").strip()
        
        self.multi_cell(0, 6, clean_display)
        
        # Reset couleur noir
        self.set_text_color(0, 0, 0)
        self.set_font('Arial', '', 11)

    def add_bullet_point(self, text, bold_part=None):
        self.set_font('Arial', '', 11)
        self.set_text_color(20, 20, 20)
        self.set_x(self.l_margin + 5)
        self.cell(5, 6, chr(149), 0, 0) 
        
        x = self.get_x()
        w_text = (self.w - self.r_margin) - x
        if w_text < 20: 
            self.ln()
            self.set_x(self.l_margin + 10)
            w_text = 0

        if bold_part:
            self.set_font('Arial', 'B', 11)
            self.set_text_color(44, 62, 80)
            clean_bold = bold_part.replace(":", "").strip()
            self.write(6, clean_bold + " :")
            
            self.ln(5) 
            self.set_x(self.l_margin + 10)
            
            self.set_font('Arial', '', 11)
            self.set_text_color(0, 0, 0)
            if ":" in text:
                remaining = text.split(":", 1)[1].strip()
            else:
                remaining = text.replace(bold_part, "").strip()
            self.multi_cell(0, 6, remaining)
        else:
            self.multi_cell(w_text, 6, text)

def parse_and_add_content(pdf, text_block):
    lines = text_block.split('\n')
    buffer_text = ""
    
    # Mots clés qui doivent déclencher la couleur
    RISK_KEYWORDS = ["CRITIQUE", "PRÉOCCUPANT", "IMPORTANT", "MODÉRÉ", "ROBUSTE", "URGENT", "CE JOUR"]
    
    for line in lines:
        clean_line = pdf.clean_text_for_pdf(line.strip())
        
        if not clean_line or re.match(r'^[-_*]{3,}$', clean_line):
            if buffer_text:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, buffer_text)
                pdf.ln(2)
                buffer_text = ""
            continue

        # 1. DÉTECTION PRIORITAIRE : LABELS COLORÉS
        # On vérifie si la ligne contient un mot clé de risque
        # ET si la ligne est courte (pour éviter de colorer tout un paragraphe qui contient le mot "important")
        upper_line = clean_line.upper()
        if any(k in upper_line for k in RISK_KEYWORDS) and len(clean_line) < 80:
            if buffer_text:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, buffer_text)
                buffer_text = ""
            
            # C'est un label, on l'affiche en couleur
            pdf.add_colored_label(clean_line)
            pdf.ln(2)
            continue

        # 2. TITRES
        if clean_line.startswith("##") or re.match(r'^TITRE\s*:', clean_line, re.IGNORECASE):
            if buffer_text:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, buffer_text)
                buffer_text = ""
            title = re.sub(r'^(##|TITRE\s*:)\s*', '', clean_line, flags=re.IGNORECASE).replace("**", "").strip()
            pdf.add_section_title(title)

        # 3. LISTES À PUCES
        elif clean_line.startswith("- ") or clean_line.startswith("* "):
            if buffer_text:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, buffer_text)
                buffer_text = ""
            
            content = clean_line[1:].strip()
            match_bold = re.match(r'\*\*(.*?)\*\*(.*)', content)
            if match_bold:
                bold_txt = match_bold.group(1)
                full_text = content.replace("**", "")
                pdf.add_bullet_point(full_text, bold_part=bold_txt)
            else:
                pdf.add_bullet_point(content)

        # 4. GRAS HORS LISTE ("**Clé** : Valeur")
        elif "**" in clean_line:
             if buffer_text:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, buffer_text)
                buffer_text = ""
             
             if ":" in clean_line:
                 parts = clean_line.split(":", 1)
                 key_part = parts[0].replace("**", "").strip()
                 val_part = parts[1].strip()
                 
                 pdf.ln(2)
                 pdf.set_x(pdf.l_margin)
                 pdf.set_font('Arial', 'B', 11)
                 pdf.set_text_color(44, 62, 80)
                 pdf.write(6, key_part + " :")
                 
                 pdf.ln(5)
                 pdf.set_x(pdf.l_margin + 5)
                 
                 pdf.set_font('Arial', '', 11)
                 pdf.set_text_color(0, 0, 0)
                 pdf.multi_cell(0, 6, val_part)
             else:
                 # Cas **PRÉOCCUPANT** (si non attrapé par l'étape 1, ex: ligne longue)
                 content = clean_line.replace("**", "").strip()
                 pdf.ln(2)
                 pdf.set_x(pdf.l_margin)
                 pdf.set_font('Arial', 'B', 11)
                 pdf.set_text_color(44, 62, 80)
                 pdf.multi_cell(0, 6, content)
                 pdf.set_text_color(0, 0, 0)

        else:
            buffer_text += clean_line + " "

    if buffer_text:
        pdf.set_x(pdf.l_margin)
        pdf.set_font('Arial', '', 11)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 6, buffer_text)

def generate_managerial_pdf(content_parts, target_url):
    pdf = ModernManagerialPDF(target_url)
    pdf.create_cover_page()
    
    for i, part in enumerate(content_parts):
        if "ERREUR" in part: continue
        
        if i == 0: 
            pdf.add_page()
            pdf.add_section_title("SYNTHÈSE DU DIAGNOSTIC")
        elif i == 1:
            pdf.add_page()
            pdf.add_section_title("DÉTAIL DES RISQUES PRIORITAIRES")
        else:
            pdf.ln(5)
            pdf.set_draw_color(220, 220, 220)
            pdf.line(20, pdf.get_y(), 190, pdf.get_y())
            pdf.ln(5)
            
        parse_and_add_content(pdf, part)
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
        pdf.output(tmp_file.name)
        return tmp_file.name