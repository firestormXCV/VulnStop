# modules/llm.py
import os
from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

def get_llm_instance():
    """
    Configure et retourne l'objet LLM de CrewAI selon le provider choisi (.env).
    """
    provider = os.getenv("LLM_PROVIDER", "").lower()
    
    # --- OPTION 1 : GROQ ---
    if provider == "grok":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("❌ Erreur : GROQ_API_KEY manquant dans .env")
            
        print("✅ Chargement LLM : Groq (Llama 3.3)")
        return LLM(
            model="groq/llama-3.3-70b-versatile",
            api_key=api_key,
            temperature=0.1
        )

    # --- OPTION 2 : GEMINI (Défaut) ---
    else:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ Erreur : GEMINI_API_KEY manquant dans .env")

        # Note: gemini-2.5 n'existe pas encore publiquement, on sécurise sur 1.5-flash
        model_name = "gemini/gemini-2.5-flash" 
        
        try:
            print(f"✅ Chargement LLM : Gemini ({model_name})")
            return LLM(
                model=model_name,
                api_key=api_key,
                temperature=0.1
            )
        except Exception as e:
            print(f"⚠️ Erreur chargement Gemini : {e}")
            raise e