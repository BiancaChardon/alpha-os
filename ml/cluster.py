from __future__ import annotations

from collections import Counter
from typing import Any

from ml.features import signal_feature_vector
from models.events import ClassifiedSignal

CLUSTER_LABELS = [
    "Bullish momentum",
    "Bearish stress",
    "Neutral watch",
    "High urgency mix",
]


def cluster_signals(signals: list[ClassifiedSignal], *, k: int = 4) -> dict[str, Any]:
    if len(signals) < 4:
        return {"model": "insufficient_data", "k": 0, "assignments": [], "clusters": []}

    try:
        import numpy as np
        from sklearn.cluster import KMeans
    except ImportError:
        return {"model": "sklearn_unavailable", "k": 0, "assignments": [], "clusters": []}

    k = max(2, min(k, len(signals) // 2, 4))
    matrix = np.array([signal_feature_vector(s) for s in signals])
    kmeans = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = kmeans.fit_predict(matrix)

    clusters = []
    for cluster_id in range(k):
        members = [signals[i] for i, label in enumerate(labels) if label == cluster_id]
        if not members:
            continue
        avg_sent = sum(m.sentiment for m in members) / len(members)
        urg_high = sum(1 for m in members if m.urgency.value == "high") / len(members)
        commodities = Counter(m.commodity for m in members).most_common(1)[0][0]
        label = _label_cluster(avg_sent, urg_high, cluster_id)
        clusters.append(
            {
                "cluster_id": cluster_id,
                "label": label,
                "size": len(members),
                "avg_sentiment": round(avg_sent, 3),
                "high_urgency_pct": round(urg_high, 2),
                "top_commodity": commodities,
                "sample_summary": members[0].one_line_summary[:120],
            }
        )

    assignments = [
        {"signal_id": signals[i].signal_id, "cluster_id": int(labels[i])}
        for i in range(len(signals))
    ]
    return {
        "model": "kmeans",
        "k": k,
        "assignments": assignments,
        "clusters": clusters,
    }


def _label_cluster(avg_sentiment: float, high_urgency_pct: float, cluster_id: int) -> str:
    if high_urgency_pct >= 0.5:
        return CLUSTER_LABELS[3]
    if avg_sentiment >= 0.15:
        return CLUSTER_LABELS[0]
    if avg_sentiment <= -0.15:
        return CLUSTER_LABELS[1]
    return CLUSTER_LABELS[2] if cluster_id % 2 else CLUSTER_LABELS[2]


def apply_cluster_assignments(
    signals: list[ClassifiedSignal], result: dict[str, Any]
) -> list[ClassifiedSignal]:
    cluster_map = {c["cluster_id"]: c["label"] for c in result.get("clusters", [])}
    by_id = {row["signal_id"]: row["cluster_id"] for row in result.get("assignments", [])}
    updated: list[ClassifiedSignal] = []
    for signal in signals:
        cluster_id = by_id.get(signal.signal_id)
        if cluster_id is None:
            updated.append(signal)
            continue
        stats = dict(signal.stats)
        stats["cluster_id"] = cluster_id
        stats["cluster_label"] = cluster_map.get(cluster_id, f"Cluster {cluster_id}")
        updated.append(signal.model_copy(update={"stats": stats}))
    return updated
