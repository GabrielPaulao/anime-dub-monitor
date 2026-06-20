#!/usr/bin/env python3
"""
twitter_monitor.py
==================
Monitora contas do Twitter/X para identificar posts sobre novos
episodios de animes dublados em portugues (BR).

Contas monitoradas:
  @naisebra, @cherrysodaaudio, @anime_dub_br, @dubmotions,
  @animedubladobr, @wdn_br, @startdustrwby, @rapadubla

Fluxo:
  1. Raspa os tweets recentes de cada conta via ntscraper (sem API key)
  2. Usa OpenAI GPT para classificar se o tweet e sobre novo episodio/anime dublado
  3. Extrai: nome do anime, episodio, status (Dublado / Dublagem em andamento / Legendado)
  4. Atualiza animes.json com os dados novos
  5. Evita duplicatas usando historico de tweet IDs

Requisitos:
  pip install ntscraper openai python-dotenv

Variaveis de ambiente (.env):
  OPENAI_API_KEY=sk-...
  OPENAI_MODEL=gpt-4o-mini  (opcional, default gpt-4o-mini)
"""

import os
import json
import re
import time
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from ntscraper import Nitter
from openai import OpenAI

# ── Configuracao ────────────────────────────────────────────────────────────
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

ACCOUNTS = [
    "naisebra",
    "cherrysodaaudio",
    "anime_dub_br",
    "dubmotions",
    "animedubladobr",
    "wdn_br",
    "startdustrwby",
    "rapadubla",
]

DATA_DIR      = Path(__file__).parent / "data"
ANIMES_JSON   = DATA_DIR / "animes.json"
HISTORY_JSON  = DATA_DIR / "historico_tweets.json"
LOG_FILE      = DATA_DIR / "monitor.log"

TWEETS_PER_ACCOUNT = 20  # quantos tweets recentes buscar por conta

# ── Logging ─────────────────────────────────────────────────────────────────
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Helpers de JSON ──────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Scraping ─────────────────────────────────────────────────────────────────

def fetch_tweets(account: str, scraper: Nitter, n: int = TWEETS_PER_ACCOUNT):
    """Retorna lista de dicts com id, text, date do usuario."""
    try:
        result = scraper.get_tweets(account, mode="user", number=n)
        tweets = result.get("tweets", [])
        log.info(f"  @{account}: {len(tweets)} tweet(s) encontrado(s)")
        return tweets
    except Exception as e:
        log.error(f"  @{account}: erro ao buscar tweets -> {e}")
        return []

# ── Classificacao com IA ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Voce e um assistente especializado em animes dublados em portugues brasileiro.
Dado o texto de um tweet, determine se ele anuncia ou menciona um novo episodio
de anime que esta dublado (ou com dublagem em andamento) em PT-BR.

Responda APENAS com JSON valido no seguinte formato (sem markdown, sem explicacoes):

{
  "relevante": true ou false,
  "anime": "Nome do Anime ou null",
  "episodio": "numero ou descricao do episodio, ou null",
  "status": "Dublado" | "Dublagem em andamento" | "Legendado" | null
}

Regras:
- "relevante": true somente se o tweet fala de lancamento/disponibilidade de episodio de anime.
- "status":
    "Dublado"              -> episodio ja disponivel em portugues dublado
    "Dublagem em andamento"-> dublagem anunciada mas ainda nao finalizada / em producao
    "Legendado"            -> disponivel somente legendado em PT
    null                   -> nao aplicavel
- Se nao tiver certeza do anime, retorne null para anime.
"""


def classify_tweet(text: str, client: OpenAI) -> dict | None:
    """Chama GPT para classificar o tweet. Retorna dict ou None em caso de erro."""
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": text},
            ],
            temperature=0,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        # Remove blocos de codigo se o modelo colocou
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"  IA retornou JSON invalido: {e} | raw={raw[:200]}")
        return None
    except Exception as e:
        log.error(f"  Erro na chamada OpenAI: {e}")
        return None

# ── Atualizacao do banco de dados ────────────────────────────────────────────

def merge_anime(animes: list, anime_name: str, episode: str, status: str,
                tweet_id: str, account: str, tweet_text: str, tweet_date: str):
    """
    Insere ou atualiza entrada de anime na lista.
    Estrutura de cada item:
    {
      "anime": str,
      "status": str,
      "assistido": false,
      "episodios": [ { "ep": str, "tweet_id": str, "conta": str, "data": str, "texto": str } ]
    }
    """
    # Normaliza nome para comparacao
    nome_lower = anime_name.strip().lower()

    for entry in animes:
        if entry["anime"].strip().lower() == nome_lower:
            # Atualiza status se necessario (prioridade: Dublado > Dublagem em andamento > Legendado)
            prioridade = {"Dublado": 3, "Dublagem em andamento": 2, "Legendado": 1}
            if prioridade.get(status, 0) > prioridade.get(entry["status"], 0):
                entry["status"] = status
            # Adiciona episodio se nao existir
            eps_ids = {e["tweet_id"] for e in entry["episodios"]}
            if tweet_id not in eps_ids:
                entry["episodios"].append({
                    "ep":        episode or "?",
                    "tweet_id":  tweet_id,
                    "conta":     account,
                    "data":      tweet_date,
                    "texto":     tweet_text[:280],
                })
            return

    # Novo anime
    animes.append({
        "anime":     anime_name.strip(),
        "status":    status or "Legendado",
        "assistido": False,
        "episodios": [{
            "ep":       episode or "?",
            "tweet_id": tweet_id,
            "conta":    account,
            "data":     tweet_date,
            "texto":    tweet_text[:280],
        }],
    })

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not OPENAI_API_KEY:
        log.error("OPENAI_API_KEY nao definida no .env!")
        return

    client  = OpenAI(api_key=OPENAI_API_KEY)
    animes  = load_json(ANIMES_JSON,  [])
    history = load_json(HISTORY_JSON, {})  # { account: [tweet_ids] }

    scraper = Nitter(log_level=1, skip_instance_check=False)

    total_novos = 0

    for account in ACCOUNTS:
        log.info(f"Buscando tweets de @{account}...")
        tweets = fetch_tweets(account, scraper)
        seen_ids = set(history.get(account, []))
        new_ids  = []

        for tweet in tweets:
            tid  = str(tweet.get("id", tweet.get("link", "")))
            text = tweet.get("text", "")
            date = tweet.get("date", datetime.now().isoformat())

            if tid in seen_ids:
                continue

            new_ids.append(tid)
            log.info(f"  Novo tweet {tid}: {text[:80]}...")

            classification = classify_tweet(text, client)
            if not classification:
                continue

            if classification.get("relevante") and classification.get("anime"):
                merge_anime(
                    animes,
                    anime_name = classification["anime"],
                    episode    = classification.get("episodio"),
                    status     = classification.get("status", "Legendado"),
                    tweet_id   = tid,
                    account    = account,
                    tweet_text = text,
                    tweet_date = date,
                )
                log.info(
                    f"    -> RELEVANTE: {classification['anime']} | "
                    f"ep={classification.get('episodio')} | status={classification.get('status')}"
                )
                total_novos += 1
            else:
                log.debug(f"    -> nao relevante")

            time.sleep(0.3)  # Evita rate limit da IA

        # Atualiza historico
        history[account] = list(seen_ids | set(new_ids))

    # Persiste dados
    save_json(ANIMES_JSON,  animes)
    save_json(HISTORY_JSON, history)
    log.info(f"Concluido. {total_novos} novos registros adicionados ao animes.json")


if __name__ == "__main__":
    main()
