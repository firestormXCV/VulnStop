FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Installation des outils système de base
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Create a directory for reports
RUN mkdir -p reports
# Le port 8000 est standard pour Chainlit
EXPOSE 8000

# Lancement
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]
