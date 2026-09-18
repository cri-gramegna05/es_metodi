# Scout

Nightly pipeline that looks for small Italian premium **men's footwear** brands that could
be acquisition targets for Venexis: it collects brand-level data from shopping sources,
merges duplicates, applies deterministic rules, and (next steps) scores them with a local
LLM, enriches the best ones with Claude and publishes to Google Sheets + Telegram.

## Status

| Module | State |
| --- | --- |
| `collectors/` (html, shopify, farfetch, yoox, giglio) | done |
| `dedupe/` (name normalization + cross-source merge) | done |
| `rules/` (deterministic filter + prescore) | done |
| `classify/` (Ollama, structured JSON + retry) | done |
| `enrich/` (Claude + server-side web search) | done |
| `publish/` (Google Sheets + Telegram) | done |
| CLI (`run`, `show`, `brief`, `stats`, `sources`, `init-db`) | done |

Every external dependency has an offline stand-in, so the whole pipeline runs with no
model, no API key and no network — see *Dry-run the whole pipeline* below.

## Setup

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
cp config.example.yaml config.yaml   # then edit
.venv/bin/scout init-db
```

`scout` is also available as `python -m scout.cli`.

## Dry-run the whole pipeline (no model, no keys, no network)

Three stand-ins ship with the repo, each speaking the real protocol:

| Real service | Stand-in |
| --- | --- |
| a shop (listing HTML + Shopify `products.json`) | `scripts/serve_fixtures.sh` on :8765 |
| Ollama `/api/chat` | `scripts/fake_ollama.py` on :11435 (`--flaky` exercises the retry path) |
| Telegram Bot API | `scripts/fake_telegram.py` on :18080 (logs the messages) |

```bash
./scripts/serve_fixtures.sh &
python scripts/fake_ollama.py --port 11435 --flaky &
python scripts/fake_telegram.py --port 18080 --out data/telegram.log &

scout run --config config.demo.yaml            # collect -> rules -> classify -> enrich -> notify
scout show "Edhèn Milano" --config config.demo.yaml
scout brief "Edhèn Milano" --config config.demo.yaml
scout stats --config config.demo.yaml
```

`config.demo.yaml` points `classify` at the fake Ollama, uses `enrich.backend: stub`
(no API key), and sends notifications to the fake Bot API. Switch each one over by editing
the config: `classify.host` to your real Ollama, `enrich.backend: claude`, and the real
Telegram token + `sheets.enabled: true`.

## Commands

```bash
scout run                      # all enabled sources, all stages
scout run --source giglio      # one source, even if disabled in config
scout run --no-classify        # stop after the deterministic rules
scout run --no-enrich          # classify but skip the paid Claude stage
scout run --no-publish         # no Telegram, no Sheets
scout run --dry-run            # parse and score, write nothing
scout run --json               # machine-readable summary
scout show "Edhèn Milano"      # observations, classification, rules verdict
scout brief "Edhèn Milano"     # the Markdown brief Claude wrote
scout stats                    # database and last-run counters
scout sources                  # configured sources and their state
```

## Sources

Two collector types cover most shops; a new source is usually a config block, not code.

- `html` — listing pages. Products are read from schema.org JSON-LD when present,
  otherwise from the CSS selectors given in config. `farfetch`, `yoox` and `giglio` are
  presets of this type with selectors already filled in (`scout/collectors/sites.py`).
- `shopify` — `/<collection>/products.json`. Gives brand (`vendor`), price and
  `compare_at_price` (i.e. the discount) without HTML parsing. Many small Italian
  boutiques run Shopify, so one entry per domain is enough.

**Farfetch and YOOX are disabled by default.** Their robots.txt and bot protection gate
listing pages; Scout skips any URL robots.txt disallows for our user-agent, so enabling
them may simply yield nothing. Check their robots.txt yourself before flipping `enabled`.

Crawling manners, enforced in `scout/http.py`: robots.txt honoured per host (including
`Crawl-delay`), one honest user-agent with a contact, per-host rate limit, exponential
backoff with jitter on retries, and every page cached on disk so a re-run does not hit the
site again within `cache_ttl_hours`.

## Rules

Hard filters (`scout/rules/filters.py`) drop the bulk before any LLM is involved:
blacklisted groups, brands every source agrees are foreign, women-only, prices outside
250–700 € (±20 %), assortments too large or too small, sneaker-first brands. What survives
gets a deterministic prescore 0–100 from the positive signals: price in band, chronic
discount ≥ 40 %, few items, Italian, men's.

Unknown values (a marketplace rarely states a brand's country) are kept, not dropped — the
classification stage decides.

## Classification, enrichment, publishing

**classify** sends the observed facts (never our own score) to a local Ollama model with
`format` set to the Pydantic JSON schema. The answer is validated; on invalid JSON the
model is re-asked with the validation error in the prompt, up to `max_retries`. Brands
below `classify.min_prescore` never reach the LLM.

**enrich** runs only for scores at or above `enrich.min_score`, at most `max_per_run` per
night: Claude (`claude-opus-5`) with the server-side `web_search` tool researches the
brand and writes the Italian brief (storia, fondatori, distribuzione, stima fatturato,
segnali di stress, perché interessante, prossimo passo). An existing brief is reused until
it is `refresh_after_days` old or the score moves by `rerun_on_score_delta` — a nightly
re-run does not re-pay for the same brief.

**publish** upserts one row per brand in the `candidati` tab (keyed on the slug, so it
updates instead of appending) and appends a run row to `log`. Telegram fires only for a
brand that is new or whose score moved more than `score_delta_threshold`, and each
notification is recorded in SQLite so it is never sent twice for the same run.

## Storage

SQLite (`data/scout.db`), one row per brand keyed on its normalized slug; each run appends
observations and a rules verdict. Re-running never duplicates a brand: `Edhèn Milano`,
`EDHÈN MILANO` and `Edhen Milano S.r.l.` all resolve to `edhen-milano`, and near-misses are
merged with a fuzzy match above the configured threshold.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Unit tests cover normalization/merging and every rule; integration tests run the collectors
and the whole pipeline against the saved fixtures, with no network.

## Nightly run on WSL (Ubuntu)

```bash
# 1. system packages (Ubuntu 22.04/24.04 on WSL2)
sudo apt update && sudo apt install -y git curl build-essential

# 2. uv (brings its own Python 3.12, so the distro version does not matter)
curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
uv python install 3.12

# 3. the project
git clone https://github.com/cri-gramegna05/es_metodi.git ~/scout
cd ~/scout && git checkout claude/scout-footwear-pipeline-x7mxxm
uv venv --python 3.12 .venv && uv pip install -e ".[dev]"

# 4. Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama serve >/dev/null 2>&1 &
ollama pull gemma3:4b

# 5. config and secrets
cp config.example.yaml config.yaml && cp .env.example .env   # then edit both
```

Keep the repo inside the Linux filesystem (`~/scout`), not under `/mnt/c` — SQLite and the
HTML cache are much slower on the Windows mount.

Scheduling, in order of reliability:

1. **Windows Task Scheduler** (recommended: it wakes WSL if it is not running).
   Program `C:\Windows\System32\wsl.exe`, arguments:
   `-d Ubuntu -- bash -lc "~/scout/deploy/run_nightly.sh"`, daily at 03:17.
2. **systemd timer** (needs `systemd=true` under `[boot]` in `/etc/wsl.conf`, then `wsl --shutdown`):
   ```bash
   mkdir -p ~/.config/systemd/user && cp deploy/systemd/scout.* ~/.config/systemd/user/
   systemctl --user enable --now scout.timer
   ```
3. **cron inside WSL** — only fires while WSL is running:
   ```bash
   sudo service cron start && crontab deploy/scout.cron
   ```

`deploy/run_nightly.sh` loads `.env`, starts Ollama if it is not listening, runs the
pipeline and appends everything to `data/nightly.log`.

## Nightly run on macOS (launchd)

```bash
cp deploy/com.venexis.scout.plist ~/Library/LaunchAgents/
# edit the paths inside, then:
launchctl load ~/Library/LaunchAgents/com.venexis.scout.plist
launchctl start com.venexis.scout
```

Logs land in `data/scout.log` (structured) plus the stdout/stderr files named in the plist.

## Going live

- **Ollama** — `brew install ollama && ollama serve && ollama pull gemma3:4b`, then set
  `classify.host` / `classify.model` in `config.yaml`.
- **Anthropic** — `export ANTHROPIC_API_KEY=...` and set `enrich.backend: claude`.
- **Google service account** — create it in Google Cloud, enable the Sheets API, download
  the JSON key to `credentials/service_account.json`, share the sheet with the service
  account e-mail; `sheets` section in `config.yaml`.
- **Telegram bot** — talk to @BotFather, take the token, get your chat id from
  `https://api.telegram.org/bot<TOKEN>/getUpdates`; set `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` in the environment (`config.yaml` reads `${VAR}`).
