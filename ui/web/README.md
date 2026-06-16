# Handoff: Alpha OS — Energy Analyst Dashboard (web frontend)

## Overview
A dark, Bloomberg-terminal-meets-modern-SaaS analyst dashboard for the **Alpha OS** energy-market signal-triage system. It is a web rendering of the existing Streamlit briefing app (`ui/app.py`), built to consume the project's existing **FastAPI** service (`api/main.py`). It shows a KPI row, the side-by-side **Synthesis Briefing** / **Contrarian Review** agent outputs, and a filterable **Classified Signals** table.

This is an **additive** frontend — it does not replace the Streamlit UI. It talks to the same backend endpoints.

## About the Design Files
The file in this bundle — `Alpha OS Dashboard.html` — is a **design reference / working prototype** built in plain HTML + CSS + vanilla JS. It already fetches from the live API and falls back to an embedded sample payload when no server is reachable, so it runs standalone for review.

The task is to **integrate this design into the `alpha-os` repo** using whatever fits the team's plan:
- **Simplest path (recommended):** serve the HTML as a static file from the existing FastAPI app (see *Integration* below). The file is self-contained (one HTML file, fonts via Google Fonts CDN) and needs no build step.
- **If a JS framework is later adopted (React/Vue/etc.):** recreate the components below pixel-for-pixel using that framework's patterns; the data-fetching contract and design tokens here are the source of truth.

Do **not** treat the inline sample data as production data — it exists only as an offline fallback. Production data comes from the API.

## Fidelity
**High-fidelity.** Final colors, typography, spacing, badges, and interactions. Recreate exactly if porting to a framework.

---

## Integration (FastAPI static serving — the fast path)

1. Place the file at `ui/web/index.html` in the repo (rename `Alpha OS Dashboard.html` → `index.html`).
2. Mount static files in `api/main.py`:
   ```python
   from fastapi.staticfiles import StaticFiles
   from pathlib import Path

   WEB_DIR = Path(__file__).resolve().parent.parent / "ui" / "web"
   app.mount("/dashboard", StaticFiles(directory=WEB_DIR, html=True), name="dashboard")
   ```
3. Run the API: `uvicorn api.main:app --reload`
4. Open `http://localhost:8000/dashboard/`. Because it's served same-origin, fetches to `/briefings/latest` and `/signals` resolve against the same host automatically — but note the page currently defaults `API_BASE` to `http://localhost:8000` (see *Configuration*). For same-origin serving, change the default to `""` (empty string = relative URLs).

CORS is already permissive (`allow_origins=["*"]` in `api/main.py`), so cross-origin hosting also works.

### Configuration
At the top of the `<script>` block:
```js
const API_BASE = new URLSearchParams(location.search).get("api") || "http://localhost:8000";
```
- Override per-load with a query param: `index.html?api=http://localhost:8000`
- For same-origin static serving, set the default to `""`.

---

## API Contract (consumed)
All shapes mirror `model_dump(mode="json")` of the Pydantic models in `models/events.py`.

### `GET /briefings/latest` → `{ briefing, contrarian }`
- `briefing` (`Briefing`): `briefing_id`, `created_at` (ISO 8601), `summary` (str), `signal_count` (int), `ranked_items` (list of `BriefingItem`).
- `BriefingItem`: `rank` (int), `title` (str), `confidence` (0–1 float), `corroboration_notes` (str), `contradiction_notes` (str), `evidence_links` (list of URL strings), `supporting_signal_ids` (list).
- `contrarian` (`ContrarianReview` | null): `alternative_interpretation` (str), `confidence_adjustment` (−1…1 float), `counterarguments` (list of str), `failure_modes` (list of str).

### `GET /signals?hours=` → `{ events, classified }`
- `classified` (list of `ClassifiedSignal`) is what the table renders. Fields used: `ts` (ISO), `source` (str code), `modality` (`"timeseries"|"text"`), `commodity` (str), `urgency` (`"low"|"medium"|"high"`), `sentiment` (−1…1), `relevance_score` (0–1), `confidence` (0–1), `one_line_summary` (str).
- `events` is not currently rendered (available for a future raw-feed tab).

### `POST /pipeline/run` → `{ summary, ... }`
Triggered by the header Refresh button; the page then re-fetches the two GETs above.

---

## Screens / Views

There is **one screen** (single-page dashboard), composed of four regions stacked vertically inside a 1680px max-width centered column with 16px padding and 14px gaps. Below 1080px the KPI row collapses to 2 columns and the two panels stack.

### 1. Top bar (`.topbar`)
- **Layout:** sticky, full-width, 52px tall, `linear-gradient(180deg, --bg-2, --bg-1)`, 1px bottom border `--line`, horizontal flex, 18px side padding, 20px gap.
- **Components:**
  - **Brand:** 26×26 rounded-6px amber gradient tile with `α` glyph (IBM Plex Mono 700, dark text), wordmark "Alpha**OS**" (OS in amber), and a `triage` pill (mono 10px, bordered). Right-bordered divider.
  - **Top nav:** Briefing (active) / Signals / Sources / Evaluation / Pipeline. Active = white text + 2px amber bottom-border. (Nav is currently non-routing decoration.)
  - **Spacer** pushes the rest right.
  - **Data-source pill (`#dataSrc`):** mono 11px, shows `● LIVE · {host}` (green pulsing dot) when API responds, `● SAMPLE DATA` (amber dot) on fallback, `● CONNECTING…` (grey) initially.
  - **Clock (`#clock`):** mono 12px, live `America/New_York` HH:MM:SS + grey `ET`.
  - **Refresh button (`#refreshBtn`):** 32px square, bordered, circular-arrow icon; spins while the pipeline runs.

### 2. KPI row (`.kpi-row`)
- **Layout:** CSS grid, 5 equal columns, 12px gap.
- **Card (`.kpi`):** `--bg-1` fill, 1px `--line-soft` border, 8px radius, 13–15px padding, 3px left accent bar (per-card color via `--accent`). Label is mono-style uppercase 10.5px `--txt-3` 600 with 0.09em tracking; value is IBM Plex Mono 600 30px.
- **Cards (left→right):**
  1. **Signals** (accent amber) — count of `classified`; sub = `{n} sources · {n} ranked`.
  2. **High Urgency** (accent red `--high`) — count where `urgency==="high"`, value colored red; sub = `{pct}% of feed`.
  3. **Commodities** (accent cyan `--power`) — three mini stats Power/NatGas/Crude with colored square dots and counts.
  4. **Top Confidence** (accent amber) — `ranked_items[0].confidence` as `NN%`; 5px amber progress bar below.
  5. **Last Run** (accent green `--up`) — `created_at` as `Mon DD · HH:MM` (value 23px); sub = relative `Xm ago` (pulsing dot) `· N adapters`.

### 3. Panels (`.panels`)
- **Layout:** grid, columns `1.32fr 1fr`, 14px gap. Each `.panel`: `--bg-1`, 1px `--line-soft`, 8px radius, min-height 340px, header + scrollable body.
- **Panel header:** 24px rounded icon tile (Σ amber for Synthesis, ⚠ red for Contrarian), 13.5px 600 title, and a right-aligned mono tag reading `claude-sonnet-4-6` (the synthesis/contrarian model per the repo README).

#### 3a. Synthesis Briefing (left)
- **Summary (`.headline`):** `briefing.summary`, 15.5px 500, line-height 1.5; the words "power" and "bullish" get amber emphasis via a light regex (cosmetic only — safe to drop when porting).
- **Byline (`.byline`):** mono 10.5px — `◴ {signal_count} classified signals · {sources} sources · {n} ranked items`, with a bottom hairline.
- **"Ranked items" label** with a `click to expand` hint.
- **Ranked item (`.item`) — EXPANDER:** the header row (`.item-head`, cursor pointer) shows `#rank` (amber mono), title (600 13.5px, turns amber on hover), `conf 0.NN` + 34px confidence bar, and a `›` chevron that rotates 90° + turns amber when open. Clicking toggles `.open`, which animates `.item-detail` `max-height` 0→520px over 0.28s. **Expanded body** contains:
  - **Corrob.** note — mono uppercase key (green `--up`) + `corroboration_notes` text.
  - **Contra.** note — mono uppercase key (red `--down`) + `contradiction_notes` text.
  - **Evidence** chips — one per `evidence_links` URL; label derived from the URL host (e.g. `eia.gov`→EIA), `↗` prefix, hover turns amber, opens in new tab.
  - First item is expanded by default; open/closed state persists across re-render/refresh (tracked in a JS `Set`).

#### 3b. Contrarian Review (right)
- **Alternative interpretation (`.alt-box`):** `--bg` fill, 3px red left-border, 7px radius; mono uppercase red key + `alternative_interpretation` text (13px).
- **Confidence adjustment (`.adj-row`):** bordered row — mono key "Confidence adjustment", note "applied to briefing", and the signed value (mono 20px 600) colored green if ≥0 else red, formatted `+0.NN` / `−0.NN` (`confidence_adjustment`).
- **Counterarguments:** mono uppercase header (red square bullet) + list; each `<li>` is a 16px grid with a mono `–` marker.
- **Failure modes:** same pattern, header accent amber `--med`, markers are `!` in amber.

### 4. Classified Signals table (`.table-wrap`)
- **Header bar:** title `Classified Signals` + mono count `— showing N of M`, and a right-aligned filter cluster:
  - **Search** (`#searchInput`): bordered 32px field with magnifier icon; substring match over summary + commodity label + source label + modality.
  - **Commodity** segmented group: All / Power / NatGas / Crude (active button gets a 2px bottom inset in the commodity color).
  - **Urgency** segmented group: All / High / Med / Low.
  - **Modality** segmented group: All / Series / Text.
  - **Source** `<select>` (`#sourceFilter`): "All sources" + one option per distinct source in the data.
- **Table:** sticky `--bg-2` header; every `<th data-sort>` is click-to-sort (toggles direction, amber ▲/▼ arrow on the active column). Default sort: `ts` descending. Row height 38px, 1px row separators, hover highlights row.
- **Columns:** Time (`ts`→HH:MM) · One-line Summary (`one_line_summary`, wraps, max 380px) · Commodity (colored dot + label) · Source (mono uppercase label) · Modality (`.modtag` pill: Series=blue `--ts`, Text=violet `--text`) · Urgency (`.badge` high/medium/low) · Sentiment (mono, signed `+0.NN`/`−0.NN`, green if >0.05 / red if <−0.05 / grey neutral) · Relevance (`relevance_score`, 2-dp) · Conf (34px amber bar + 2-dp value).
- **Empty state:** "No signals match the current filters." when filters exclude all rows.
- **Footer:** mono status (`Showing all signals` or `Filtered by …`) + a legend of the three urgency badges.

---

## Interactions & Behavior
- **Load:** `loadData()` runs on page load → `Promise.all([GET /briefings/latest, GET /signals])` with a 2.5s `AbortController` timeout. Success → render from API + set pill to LIVE. Failure/timeout → render embedded `SAMPLE_*` payload + set pill to SAMPLE DATA.
- **Refresh button:** adds spin class → `POST /pipeline/run` (best-effort; ignored on failure) → `loadData()` again.
- **Ranked-item expanders:** click header toggles `.open`; `max-height` transition; state stored in `openItems` Set.
- **Filters:** all filtering/sorting is client-side over the loaded `classified` array; re-renders only the `<tbody>`.
- **Clock:** updates every 1s. "Xm ago" recomputes every 30s from `briefing.created_at`.
- **Sorting:** string columns (summary/commodity/source/modality) default ascending; numeric/time columns default descending; clicking the active column flips direction.

## State Management
JS module-scope state (no framework):
- `DATA` — `{ briefing, contrarian, classified }` (from API or sample).
- `filters` — `{ commodity, urgency, modality, source, search, sortKey, sortDir }`.
- `openItems` — `Set<number>` of expanded ranked-item indices (default `{0}`).
- `API_BASE` — resolved from `?api=` or default.

When porting to a framework: `DATA` → a fetched store/query; `filters` → component state driving a derived/sorted list; `openItems` → accordion open-state; the three render functions map to Briefing, Contrarian, and Table components.

## Design Tokens
Colors are authored in **OKLCH** (CSS custom properties on `:root`). Equivalent hex in parentheses for convenience.

| Token | OKLCH | ~Hex | Use |
|---|---|---|---|
| `--bg` | `oklch(0.158 0.007 256)` | `#0d1014` | App background |
| `--bg-1` | `oklch(0.196 0.008 256)` | `#161a20` | Cards / panels |
| `--bg-2` | `oklch(0.225 0.009 256)` | `#1c2128` | Header / table head |
| `--bg-3` | `oklch(0.262 0.010 256)` | `#242a32` | Track / elevated |
| `--line` | `oklch(0.318 0.012 256)` | `#323a44` | Borders |
| `--line-soft` | `oklch(0.262 0.010 256)` | `#242a32` | Subtle borders |
| `--txt` | `oklch(0.948 0.004 256)` | `#eef0f2` | Primary text |
| `--txt-2` | `oklch(0.742 0.008 256)` | `#a6abb3` | Secondary text |
| `--txt-3` | `oklch(0.582 0.010 256)` | `#7a8089` | Muted / labels |
| `--amber` | `oklch(0.812 0.132 78)` | `#e0a23c` | Primary accent |
| `--amber-dim` | `oklch(0.66 0.10 78)` | `#b07e2e` | Accent gradient end |
| `--up` | `oklch(0.770 0.150 152)` | `#3cc27a` | Positive / online |
| `--down` | `oklch(0.680 0.180 25)` | `#df5a4a` | Negative / contra |
| `--high` | `oklch(0.680 0.185 25)` | `#df5645` | High urgency |
| `--med` | `oklch(0.815 0.130 78)` | `#e2a53e` | Medium urgency |
| `--low` | `oklch(0.720 0.105 232)` | `#5aa0d8` | Low urgency |
| `--power` | `oklch(0.760 0.115 196)` | `#3eb6bd` | Commodity: Power (cyan) |
| `--natgas` | `oklch(0.715 0.120 256)` | `#6f96e0` | Commodity: NatGas (blue) |
| `--crude` | `oklch(0.760 0.140 56)` | `#d18b3e` | Commodity: Crude (orange) |
| `--ts` | `oklch(0.730 0.075 220)` | `#6fa0c0` | Modality: timeseries |
| `--text` | `oklch(0.745 0.090 312)` | `#b285c8` | Modality: text |

- **Radius:** cards/panels 8px (`--radius`); pills/badges/buttons 4–7px.
- **Row height:** 38px (`--row-h`).
- **Spacing:** page padding 16px; section gap 14px; KPI gap 12px; intra-card 9–15px.
- **Typography:**
  - **Sans (UI):** "IBM Plex Sans", system-ui fallback. Weights 400/500/600/700.
  - **Mono (all data, codes, numbers, labels):** "IBM Plex Mono", weights 400/500/600, with `font-variant-numeric: tabular-nums` on numeric values.
  - Both loaded from Google Fonts (`fonts.googleapis.com/css2?family=IBM+Plex+Mono…&family=IBM+Plex+Sans…`). If the codebase self-hosts fonts, swap the `<link>` accordingly.
  - Key sizes: KPI value 30px/600; panel title 13.5px/600; headline 15.5px/500; table body 12.5–13px; mono labels 9.5–11px uppercase with 0.04–0.09em tracking.

## Assets
- **No image assets.** The α brand mark is a CSS gradient tile with a text glyph; all icons (search, refresh) are inline SVG; status/urgency/commodity indicators are CSS shapes. Fonts come from the Google Fonts CDN.
- If the repo standardizes on a font self-host or an icon set, substitute those; nothing here depends on a binary asset.

## Files
- `Alpha OS Dashboard.html` — the complete self-contained dashboard (HTML + CSS + JS). All logic is in the single `<script>` block at the bottom; all styles are in the single `<style>` block in `<head>`. Search for these anchors when porting:
  - `API_BASE`, `loadData`, `fetchJSON` — data layer
  - `renderKpis`, `renderBriefing` (expanders), `renderContrarian`, `renderTable` — view layer
  - `SAMPLE_BRIEFING`, `SAMPLE_SIGNALS` — offline fallback (remove for production if undesired)

## Repo reference (read-only context used to build this)
- `ui/app.py` — Streamlit equivalent (KPI columns, side-by-side panels, filtered dataframe).
- `api/main.py` — endpoints + CORS.
- `models/events.py` — `ClassifiedSignal`, `Briefing`, `BriefingItem`, `ContrarianReview`, `Urgency`.
- `pipeline/store.py` — persistence (SQLite) behind the API.
