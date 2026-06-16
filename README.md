# Alpha OS

AI-augmented energy market signal triage for BANA 6070 (Alpha AI final project).

## Architecture

Public data sources feed source-specific adapters that emit unified `SignalEvent` envelopes. A three-agent pipeline classifies signals, synthesizes a ranked briefing, and generates a contrarian review. Results are exposed via FastAPI and a Streamlit analyst UI.

## Quick start

```bash
cd Projects/alpha-os
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Run the one-command demo (fixture mode):

```bash
python -m pipeline.demo
```

Start API:

```bash
uvicorn api.main:app --reload
```

Start UI:

```bash
cd Projects/alpha-os
streamlit run ui/app.py
```

Run tests:

```bash
pytest -q
```

Run evaluation:

```bash
python -m eval.runner
```

## Data sources

| Adapter | Source | Mode |
|---|---|---|
| `eia` | Henry Hub futures | Live with `EIA_API_KEY`, else fixture |
| `fred` | WTI + Henry Hub spot | Live with `FRED_API_KEY`, else fixture |
| `pjm` | PJM LMP | Fixture snapshot |
| `ercot` | ERCOT LMP | Fixture snapshot |
| `caiso` | Renewables/curtailment | Fixture snapshot |
| `noaa` | Weather forecast | Live or fixture |
| `eia_today` | Today in Energy headlines | RSS or fixture |
| `ferc` | Regulatory notices | Fixture snapshot |
| `opec` | Press releases | Fixture snapshot |

Set `INGESTION_FIXTURE_MODE=true` for reliable demo runs.

## LLM configuration (Anthropic)

| Agent | Model | Env var |
|---|---|---|
| Text classification | `claude-3-5-haiku-latest` | `ANTHROPIC_CLASSIFICATION_MODEL` |
| Synthesis + Contrarian | `claude-sonnet-4-6` | `ANTHROPIC_SYNTHESIS_MODEL` |

Timeseries classification uses rules only (no LLM spend). If `ANTHROPIC_API_KEY` is unset, all agents fall back to rules-based logic.

## Team ownership

- Eric: backend, orchestration, synthesis/contrarian agents
- Emily: ingestion/classification agent, Streamlit UI
- Scott: eval framework, headline curation workflow, presentation

## Project structure

```
adapters/     Source adapters
agents/       Ingestion, synthesis, contrarian agents
api/          FastAPI service
eval/         Rubric and golden scenarios
pipeline/     Store, normalize, orchestrator, scheduler, demo
ui/           Streamlit briefing app
tests/        Pytest + fixtures
```
