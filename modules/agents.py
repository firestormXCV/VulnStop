# modules/agents.py
from crewai import Agent
from modules.llm import get_llm_instance
from modules.prompts import (
    AUDIT_ROLE, AUDIT_GOAL, AUDIT_BACKSTORY,
    CHAT_ROLE, CHAT_GOAL, CHAT_BACKSTORY,
    WRITER_ROLE, WRITER_GOAL, WRITER_BACKSTORY,
    RISK_ADVISER_ROLE, RISK_ADVISER_GOAL, RISK_ADVISER_BACKSTORY
)

# 1. On récupère le "Cerveau" configuré
llm_engine = get_llm_instance()

# 2. Définition des Agents
audit_analyst = Agent(
    role=AUDIT_ROLE,
    goal=AUDIT_GOAL,
    backstory=AUDIT_BACKSTORY,
    llm=llm_engine,
    verbose=True
)

chat_assistant = Agent(
    role=CHAT_ROLE,
    goal=CHAT_GOAL,
    backstory=CHAT_BACKSTORY,
    llm=llm_engine,
    verbose=True
)

pdf_writer_agent = Agent(
    role=WRITER_ROLE,
    goal=WRITER_GOAL,
    backstory=WRITER_BACKSTORY,
    llm=llm_engine,
    verbose=True
)

sme_risk_advisor = Agent(
    role=RISK_ADVISER_ROLE,
    goal=RISK_ADVISER_GOAL,
    backstory=RISK_ADVISER_BACKSTORY,
    llm=llm_engine,
    verbose=True
)
