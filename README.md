# Anime Dub Monitor

Automacao para monitorar contas do Twitter/X especializadas em animes dublados em portugues (PT-BR), identificar posts sobre novos episodios e sincronizar os dados com uma planilha Google Sheets.

## Contas monitoradas

| Conta | Descricao |
|---|---|
| @naisebra | Naise BR |
| @cherrysodaaudio | Cherry Soda Audio |
| @anime_dub_br | Anime Dub BR |
| @dubmotions | Dub Motions |
| @animedubladobr | Anime Dublado BR |
| @wdn_br | WDN BR |
| @startdustrwby | Stardust RWBY |
| @rapadubla | Rapa Dubla |

## Estrutura do projeto

```
anime-dub-monitor/
├── twitter_monitor.py       # Script de monitoramento (raspa tweets + IA)
├── sync_sheet.py            # Sincroniza animes.json com Google Sheets
├── openclaw_workflow.json   # Workflow do OpenClaw para execucao automatizada
├── requirements.txt         # Dependencias Python
├── .env.example             # Modelo de variaveis de ambiente
└── data/                    # Gerado automaticamente ao rodar
    ├── animes.json          # Banco de dados principal
    ├── historico_tweets.json# IDs de tweets ja processados
    ├── monitor.log          # Log do monitoramento
    └── sync.log             # Log da sincronizacao
```

## Como funciona

### twitter_monitor.py
1. Raspa os tweets recentes de cada conta via **ntscraper** (sem precisar de API key do Twitter)
2. Envia cada tweet novo para o **GPT-4o-mini** que classifica:
   - Se e relevante (fala de novo episodio de anime)
   - Nome do anime
   - Numero do episodio
   - Status: `Dublado` / `Dublagem em andamento` / `Legendado`
3. Atualiza `data/animes.json` com os dados extraidos
4. Evita duplicatas usando `data/historico_tweets.json`

### sync_sheet.py
1. Le o `data/animes.json`
2. Conecta na planilha Google Sheets via Service Account
3. Para cada anime:
   - Se ja existe na planilha: atualiza Status, Ultimo Episodio e Data (preserva checkbox Assistido)
   - Se nao existe: adiciona nova linha com checkbox Assistido desmarcado
4. Garante que a coluna "Assistido" tem formato checkbox

### Planilha gerada

| Anime | Status | Assistido | Ultimo Episodio | Conta Twitter | Data Atualizacao |
|---|---|---|---|---|---|
| Demon Slayer | Dublado | [ ] | 12 | animedubladobr | 2026-06-20 15:00 |
| Solo Leveling | Dublagem em andamento | [ ] | 8 | naisebra | 2026-06-20 14:30 |

## Instalacao

### 1. Clone o repositorio

```bash
git clone https://github.com/GabrielPaulao/anime-dub-monitor.git
cd anime-dub-monitor
```

### 2. Instale as dependencias

```bash
pip install -r requirements.txt
```

### 3. Configure o ambiente

```bash
copy .env.example .env
# Edite o .env com seus valores reais
```

### 4. Configure o Google Sheets

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto e ative a **Google Sheets API**
3. Crie uma **Service Account** e baixe o JSON de credenciais
4. Salve o JSON como `credentials.json` na raiz do projeto
5. Crie uma planilha no Google Sheets e copie o ID da URL
6. Compartilhe a planilha com o email da Service Account (editor)

## Uso

### Rodar o monitoramento

```bash
python twitter_monitor.py
```

### Sincronizar com Google Sheets

```bash
python sync_sheet.py
```

### Workflow completo via OpenClaw

Importe o arquivo `openclaw_workflow.json` no OpenClaw e execute o workflow completo, que:
1. Roda o monitoramento
2. Organiza e limpa o JSON via IA
3. Sincroniza com Google Sheets
4. Commita as mudancas no Git

## Estrutura do animes.json

```json
[
  {
    "anime": "Demon Slayer",
    "status": "Dublado",
    "assistido": false,
    "episodios": [
      {
        "ep": "12",
        "tweet_id": "1234567890",
        "conta": "animedubladobr",
        "data": "2026-06-20T15:00:00",
        "texto": "O episodio 12 de Demon Slayer ja esta disponivel dublado!"
      }
    ]
  }
]
```

## Variaveis de ambiente

| Variavel | Obrigatorio | Descricao |
|---|---|---|
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI |
| `OPENAI_MODEL` | Nao | Modelo a usar (padrao: gpt-4o-mini) |
| `SPREADSHEET_ID` | Sim (sync) | ID da planilha Google Sheets |
| `GOOGLE_CREDENTIALS_JSON` | Sim (sync) | Caminho para o JSON da Service Account |
| `SHEET_NAME` | Nao | Nome da aba (padrao: Animes) |

## Pasta local

Clone dentro de: `C:\Users\Gabriel Paulao\Desktop\MegaSync\Git\Anime Dub Monitor\`
