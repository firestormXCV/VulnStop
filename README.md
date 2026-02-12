# 🛡️ VulnStop

**Automated Cybersecurity Audit for Everyone.**

VulnStop is an automated auditing solution designed to democratize cybersecurity for SMEs and developers. Born from the realization that 80% of European SMEs lack the resources to identify their IT vulnerabilities , this tool allows non-experts to scan websites and source code and receive clear, AI-generated reports.

**Key Features:**

* **🤖 AI Chatbot:** Interact with an AI assistant to answer security questions.



* **🌐 Web Scanner (DAST):** Automated website auditing powered by OWASP ZAP.



* **💻 Code Scanner (SAST):** Static code analysis using Semgrep to find vulnerabilities in files.



* **📄 Automated Reporting:** Generates PDF reports (Managerial or Technical) with actionable remediation steps.



---

## 🚀 Quick Start (Recommended)

We provide automated scripts to launch the project effortlessly using Docker.

### Prerequisites

* **Docker** (Desktop for Windows, Engine for Linux).



* **Google Gemini API Key** (Free at [aistudio.google.com](https://aistudio.google.com)) or Groq Key.



### 🐧 On Linux / Mac

1. Clone the repository.
2. Run the installer script:
```bash
./install.sh
```


3. Follow the interactive assistant to set up your API key and optional domain name (HTTPS).



### 🪟 On Windows

1. Clone the repository.
2. **Configure Environment:**
    * Rename `.env.example` to `.env`.
    * Open it and add your API Key: `GEMINI_API_KEY=your_key_here`.
    * **Crucial:** You must generate a Chainlit secret.
        * Open a terminal and run: `chainlit create-secret`
        * *If you don't have Chainlit installed locally yet, you can generate a random 32-character string.*
        * Paste it in the file: `CHAINLIT_AUTH_SECRET=your_generated_secret_here`.

3. Open a terminal and run:
```bash
docker compose up
```



Note: The first launch may take a few minutes to download images.



**Access the App:** Open your browser at `http://localhost:8000`.

---

## 🛠️ Manual Installation (Local without Docker)

For advanced users who prefer running tools on their host machine.

### 1. Install External Tools

* **OWASP ZAP (Java required):**
* Download from [zaproxy.org](https://www.zaproxy.org/download) and install it.


* Launch ZAP and keep it running in the background.


* **Config:** Go to `Tools > Options`. Copy the **API Key** from the "API" tab and ensure "Local Proxies" is set to `localhost` port `8080`.




* **Semgrep:**
* Install via pip: `python3 -m pip install semgrep`.





### 2. Configure Environment

1.  Create a `.env` file in the root directory.
2.  Generate a secure secret key by running this command in your terminal:
    ```bash
    chainlit create-secret
    ```
3.  Add the following variables to your `.env` file:
    ```ini
    GEMINI_API_KEY=your_gemini_key
    CHAINLIT_AUTH_SECRET=the_secret_you_just_generated
    ZAP_API_KEY=your_zap_api_key_from_step_1
    ZAP_PROXY=[http://127.0.0.1:8080](http://127.0.0.1:8080)
    ```



### 3. Run the Application

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Launch Chainlit
chainlit run app.py -w
```



---

## 🏗️ Technical Architecture

The project uses a containerized architecture to ensure portability.

**The Metaphor: A Code Health Clinic** 

* **👨‍⚕️ The Coordinator (App):** The Chat interface (Chainlit/Python) receives user requests and coordinates tasks.



* **🧪 The Lab (Scanners):** Isolated Docker containers running ZAP (Web) and Semgrep (Code) to perform raw security tests.



* **🧠 The Specialist (Gemini AI):** Analyzes the complex raw data from the lab, diagnoses issues, and writes the prescription (remediation report).




---

## 📂 Source Code Structure

Here is how the codebase is organized:

```text
📁/
│
├── 📄 app.py                  # 🚀 Main Entry Point (Chainlit Interface)
├── 📄 install.sh              # ⚡ Auto-install script (Linux/Mac)
├── 📄 docker-compose.yml      # 🐳 Docker orchestration config
├── 📄 Dockerfile              # 📦 Python image build definition
├── 📄 requirements.txt        # 📦 Python dependencies list
├── 📄 .env                    # 🔑 API Keys & Configuration (Secrets)
├── 📄 Caddyfile               # 🌐 Server Config (HTTPS & Reverse Proxy)
├── 📄 chainlit.md             # 📄 Welcome page content for the UI
├── 📄 Licenses.md             # ⚖️ Project usage rights
├── 📄 .gitignore              # 🙈 Ignored files (venv, .env, etc.)
│
├── 📁 public/                 # 🎨 UI Assets (Custom styling)
│   ├── 📄 custom.js           #    Frontend scripts (Auto-scroll)
│   └── 🖼️ favicon.png         #    Application Icon
│
├── 📁 .chainlit_data/         # 💾 Data Persistence
│   ├── 📄 chat_history.sqlite #    Local SQL Database
│   └── 📁 files/              #    Permanent storage for generated PDFs
│
├── 📁 reports/                # 📂 Output folder for local Reports (JSON/PDF)
│
└── 📁 modules/                # 🧠 Core Application Logic
    ├── 📄 __init__.py         #    Makes folder importable
    │
    ├── 🟠 ORCHESTRATION
    │   └── 📄 orchestrator.py #    Pipeline & Workflow Manager
    │
    ├── 🔴 CYBERSECURITY TOOLS
    │   ├── 📄 scanner.py      #    OWASP ZAP API Pilot (DAST)
    │   ├── 📄 semgrep.py      #    Semgrep API Pilot (SAST)
    │   ├── 📄 git_utils.py    #    Git Repository Cloning & Handling
    │   └── 📄 utils.py        #    Helper functions (Data cleaning, etc.)
    │
    ├── 🟢 AI ENGINE (CrewAI)
    │   ├── 📄 agents.py       #    AI Agent definitions
    │   ├── 📄 tasks.py        #    Task logic & Prompt injection
    │   ├── 📄 llm.py          #    LLM Setup (Gemini/Groq)
    │   └── 📄 prompts.py      #    System Prompts
    │
    ├── 🔵 DATABASE
    │   └── 📄 db_manager.py   #    SQLite Async Manager
    │
    └── 📁 reporting/          # 📄 PDF Generation Engine
        ├── 📄 managerial_report.py
        └── 📄 technical_report.py

```
---

## 🤝 Contributing & Improvements

We designed VulnStop to be modular. Here are some areas for contribution:

* **LLM Flexibility:** Replace Gemini with other models (GPT-4, Mistral) in `modules/llm.py`.



* **New Scanners:** Add new tools to the Docker Compose and `modules/` folder.
* **Prompt Engineering:** Improve the System Prompts in `modules/prompts.py` to reduce hallucinations or improve report quality.



* **Performance:** Optimize the "Chunking" logic for processing very large reports to manage API token limits.




**Note:** If you change UI assets (CSS/Logo), remember to clear your browser cache (Ctrl+F5).

*Happy Coding!*

