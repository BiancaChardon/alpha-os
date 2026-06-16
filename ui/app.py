from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from config import settings
from models.events import ClassifiedSignal, Urgency
from pipeline.orchestrator import run_pipeline
from pipeline.store import EventStore

URGENCY_BADGES = {
    Urgency.HIGH: "🔴 High",
    Urgency.MEDIUM: "🟡 Medium",
    Urgency.LOW: "⚪ Low",
}


def filter_signals(
    signals: list[ClassifiedSignal],
    commodities: list[str],
    urgencies: list[str],
    sources: list[str],
    modalities: list[str],
) -> list[ClassifiedSignal]:
    filtered = signals
    if commodities:
        filtered = [s for s in filtered if s.commodity in commodities]
    if urgencies:
        filtered = [s for s in filtered if s.urgency.value in urgencies]
    if sources:
        filtered = [s for s in filtered if s.source in sources]
    if modalities:
        filtered = [s for s in filtered if s.modality in modalities]
    return filtered


def render_briefing_items(items: list) -> None:
    for item in items:
        with st.expander(f"#{item.rank} {item.title} (confidence {item.confidence:.0%})"):
            if item.evidence_links:
                st.markdown("**Evidence**")
                for link in item.evidence_links:
                    st.markdown(f"- [{link}]({link})")
            st.markdown(f"**Corroboration:** {item.corroboration_notes}")
            st.markdown(f"**Contradictions:** {item.contradiction_notes}")


st.set_page_config(page_title="Alpha OS Briefing", page_icon="⚡", layout="wide")

with st.sidebar:
    st.header("Filters")
    st.caption("Narrow the classified signal feed")

store = EventStore()

st.title("Alpha OS — Energy Market Signal Triage")
st.caption("AI-augmented synthesis for wholesale power and gas market signals")

col1, col2, col3 = st.columns(3)
with col1:
    fixture_mode = st.toggle("Fixture mode", value=settings.ingestion_fixture_mode)
    settings.ingestion_fixture_mode = fixture_mode
with col2:
    lookback = st.number_input(
        "Lookback hours", min_value=1, max_value=168, value=settings.signal_lookback_hours
    )
    settings.signal_lookback_hours = int(lookback)
with col3:
    if st.button("Refresh pipeline", type="primary", use_container_width=True):
        with st.spinner("Running ingestion and agents..."):
            result = run_pipeline(store=store)
            st.session_state["last_run"] = result

briefing = store.get_latest_briefing()
review = store.get_latest_contrarian_review()
classified = store.get_recent_classified_signals()

if "last_run" in st.session_state:
    st.success(st.session_state["last_run"].get("summary", "Pipeline completed"))

if not briefing:
    st.info("No briefing yet. Click **Refresh pipeline** to generate one.")
    st.stop()

# --- KPI row ---
high_urgency = sum(1 for s in classified if s.urgency == Urgency.HIGH)
commodities = {s.commodity for s in classified}
top_confidence = briefing.ranked_items[0].confidence if briefing.ranked_items else 0.0
last_run = briefing.created_at.strftime("%b %d, %H:%M")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Signals", len(classified))
k2.metric("High urgency", high_urgency)
k3.metric("Commodities", len(commodities))
k4.metric("Top confidence", f"{top_confidence:.0%}")
k5.metric("Last run", last_run)

st.divider()

# --- Sidebar filters (options from current data) ---
all_commodities = sorted({s.commodity for s in classified})
all_urgencies = sorted({s.urgency.value for s in classified})
all_sources = sorted({s.source for s in classified})
all_modalities = sorted({s.modality for s in classified})

with st.sidebar:
    if st.button("Clear filters", use_container_width=True):
        for key in (
            "filter_commodities",
            "filter_urgencies",
            "filter_sources",
            "filter_modalities",
        ):
            st.session_state[key] = []
        st.rerun()

    selected_commodities = st.multiselect(
        "Commodity", all_commodities, default=[], key="filter_commodities"
    )
    selected_urgencies = st.multiselect(
        "Urgency",
        all_urgencies,
        default=[],
        format_func=lambda u: u.title(),
        key="filter_urgencies",
    )
    selected_sources = st.multiselect("Source", all_sources, default=[], key="filter_sources")
    selected_modalities = st.multiselect(
        "Modality", all_modalities, default=[], key="filter_modalities"
    )

filtered_signals = filter_signals(
    classified,
    selected_commodities,
    selected_urgencies,
    selected_sources,
    selected_modalities,
)

# --- Side-by-side Synthesis | Contrarian ---
left, right = st.columns(2)

with left:
    st.subheader("Synthesis Briefing")
    st.write(briefing.summary)
    if briefing.ranked_items:
        render_briefing_items(briefing.ranked_items)
    else:
        st.info("No ranked items in this briefing.")

with right:
    st.subheader("Contrarian Review")
    if review:
        st.info(review.alternative_interpretation)
        st.metric("Confidence adjustment", f"{review.confidence_adjustment:+.2f}")
        st.markdown("**Counterarguments**")
        for arg in review.counterarguments:
            st.markdown(f"- {arg}")
        st.markdown("**Failure modes**")
        for mode in review.failure_modes:
            st.markdown(f"- {mode}")
    else:
        st.warning("No contrarian review available.")

st.divider()

# --- Filtered signal table ---
st.subheader("Classified signals")
shown = len(filtered_signals)
total = len(classified)
st.caption(f"Showing {shown} of {total} signals")

if filtered_signals:
    st.dataframe(
        [
            {
                "urgency": URGENCY_BADGES.get(s.urgency, s.urgency.value),
                "commodity": s.commodity,
                "source": s.source,
                "modality": s.modality,
                "sentiment": round(s.sentiment, 2),
                "relevance": round(s.relevance_score, 2),
                "confidence": round(s.confidence, 2),
                "summary": s.one_line_summary,
            }
            for s in filtered_signals[:50]
        ],
        width="stretch",
        hide_index=True,
    )
else:
    st.warning("No signals match the current filters.")
