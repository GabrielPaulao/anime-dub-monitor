#!/usr/bin/env python3
"""
sync_sheet.py
=============
Sincroniza o arquivo data/animes.json com uma planilha Google Sheets.

Estrutura da planilha (aba "Animes"):
  Col A: Anime
  Col B: Status          (Dublado | Dublagem em andamento | Legendado)
  Col C: Assistido       (checkbox TRUE/FALSE)
  Col D: Ultimo Episodio
  Col E: Conta Twitter
  Col F: Data Atualizacao

Como funciona:
  - Le todos os animes do JSON
  - Para cada anime, verifica se ja existe na planilha (pelo nome)
  - Se existir: atualiza Status, Ultimo Episodio, Conta, Data (preserva Assistido)
  - Se nao existir: adiciona nova linha com Assistido = FALSE (checkbox)
  - Nao remove linhas existentes (seguro)

Requisitos:
  pip install gspread google-auth python-dotenv

Variaveis de ambiente (.env):
  GOOGLE_CREDENTIALS_JSON=caminho para o arquivo credentials.json da Service Account
  SPREADSHEET_ID=1AbCdEf...   (ID da planilha do Google Sheets)
  SHEET_NAME=Animes           (nome da aba, padrao: Animes)

Como criar as credenciais:
  1. Acesse https://console.cloud.google.com
  2. Crie um projeto e ative a API do Google Sheets
  3. Crie uma Service Account e baixe o JSON de credenciais
  4. Compartilhe a planilha com o email da Service Account
  5. Coloque o caminho do JSON em GOOGLE_CREDENTIALS_JSON no .env
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# ── Configuracao ─────────────────────────────────────────────────────────────
load_dotenv()

CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME       = os.getenv("SHEET_NAME", "Animes")

DATA_DIR    = Path(__file__).parent / "data"
ANIMES_JSON = DATA_DIR / "animes.json"
LOG_FILE    = DATA_DIR / "sync.log"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Cabecalho da planilha
HEADER = ["Anime", "Status", "Assistido", "Ultimo Episodio", "Conta Twitter", "Data Atualizacao"]

# ── Logging ──────────────────────────────────────────────────────────────────
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

# ── Google Sheets ─────────────────────────────────────────────────────────────

def connect_sheet():
    """Conecta ao Google Sheets e retorna o worksheet."""
    if not SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID nao definido no .env!")
    creds = Credentials.from_service_account_file(CREDENTIALS_JSON, scopes=SCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_NAME, rows=500, cols=10)
        log.info(f"Aba '{SHEET_NAME}' criada na planilha.")
    return ws


def ensure_header(ws):
    """Garante que o cabecalho existe na linha 1."""
    current = ws.row_values(1)
    if current != HEADER:
        ws.update("A1:F1", [HEADER])
        # Formata cabecalho em negrito
        ws.format("A1:F1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
        })
        log.info("Cabecalho criado/atualizado.")

# ── Sync ─────────────────────────────────────────────────────────────────────

def build_index(ws) -> dict:
    """Retorna dicionario {nome_lower: row_number} para todas as linhas existentes."""
    all_vals = ws.get_all_values()
    index = {}
    for i, row in enumerate(all_vals[1:], start=2):  # pula cabecalho
        if row and row[0].strip():
            index[row[0].strip().lower()] = i
    return index


def get_ultimo_ep(episodios: list) -> tuple[str, str]:
    """Retorna (ultimo_ep, conta) do episodio mais recente."""
    if not episodios:
        return "?", ""
    ultimo = episodios[-1]
    return str(ultimo.get("ep", "?")), ultimo.get("conta", "")


def sync(animes: list, ws):
    index     = build_index(ws)
    agora     = datetime.now().strftime("%Y-%m-%d %H:%M")
    novos     = 0
    atualizados = 0

    for anime in animes:
        nome   = anime.get("anime", "").strip()
        status = anime.get("status", "Legendado")
        ultimo_ep, conta = get_ultimo_ep(anime.get("episodios", []))

        if not nome:
            continue

        nome_lower = nome.lower()

        if nome_lower in index:
            row_num = index[nome_lower]
            # Preserva coluna C (Assistido) - nao sobrescreve
            existing = ws.row_values(row_num)
            assistido_val = existing[2] if len(existing) > 2 else "FALSE"

            ws.update(
                f"A{row_num}:F{row_num}",
                [[nome, status, assistido_val, ultimo_ep, conta, agora]]
            )
            atualizados += 1
            log.info(f"  Atualizado: {nome} | {status}")
        else:
            # Nova linha - adiciona no final
            next_row = len(index) + novos + 2  # +2 por causa do cabecalho e 0-index
            ws.append_row([nome, status, False, ultimo_ep, conta, agora])

            # Aplica checkbox na coluna C da nova linha
            # Conta quantas linhas tem agora
            all_vals = ws.get_all_values()
            new_row_num = len(all_vals)
            ws.update(f"C{new_row_num}", False)

            # Formata como checkbox
            ws.format(f"C{new_row_num}", {
                "dataValidation": {
                    "condition": {
                        "type": "BOOLEAN",
                    }
                }
            })

            index[nome_lower] = new_row_num
            novos += 1
            log.info(f"  Novo: {nome} | {status}")

    log.info(f"Sincronizacao concluida: {novos} novos, {atualizados} atualizados.")


def apply_checkboxes(ws):
    """Aplica formato checkbox em toda a coluna C (exceto cabecalho)."""
    all_vals = ws.get_all_values()
    last_row = len(all_vals)
    if last_row < 2:
        return
    # Usando a API de requests em batch via gspread
    sh = ws.spreadsheet
    sheet_id = ws.id
    requests = [{
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,        # linha 2 (0-indexed)
                "endRowIndex":   last_row,
                "startColumnIndex": 2,     # coluna C (0-indexed)
                "endColumnIndex":   3,
            },
            "cell": {
                "dataValidation": {
                    "condition": {"type": "BOOLEAN"},
                    "showCustomUi": True,
                }
            },
            "fields": "dataValidation",
        }
    }]
    sh.batch_update({"requests": requests})
    log.info("Checkboxes aplicados na coluna Assistido.")

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not ANIMES_JSON.exists():
        log.error(f"Arquivo {ANIMES_JSON} nao encontrado. Rode primeiro o twitter_monitor.py")
        return

    with open(ANIMES_JSON, encoding="utf-8") as f:
        animes = json.load(f)

    if not animes:
        log.info("Nenhum anime no JSON ainda.")
        return

    log.info(f"Conectando ao Google Sheets (ID: {SPREADSHEET_ID})...")
    ws = connect_sheet()
    ensure_header(ws)
    sync(animes, ws)
    apply_checkboxes(ws)
    log.info("Pronto!")


if __name__ == "__main__":
    main()
