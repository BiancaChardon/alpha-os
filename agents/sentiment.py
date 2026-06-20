from __future__ import annotations

from functools import lru_cache

NEGATIVE_KEYWORDS = {"cut", "sanction", "outage", "curtailment", "shortage", "spike", "tight", "surge"}
POSITIVE_KEYWORDS = {"build", "approval", "expansion", "record", "surplus", "decline", "drop", "ease"}


@lru_cache(maxsize=1)
def _vader_analyzer():
    try:
        import nltk
        from nltk.sentiment import SentimentIntensityAnalyzer

        try:
            return SentimentIntensityAnalyzer()
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
            return SentimentIntensityAnalyzer()
    except Exception:
        return None


def _keyword_sentiment(text: str) -> float:
    lower = text.lower()
    score = 0.0
    for word in NEGATIVE_KEYWORDS:
        if word in lower:
            score -= 0.2
    for word in POSITIVE_KEYWORDS:
        if word in lower:
            score += 0.2
    return max(-1.0, min(1.0, score))


def score_sentiment(text: str) -> float:
    """NLTK VADER compound score in [-1, 1], with keyword fallback."""
    cleaned = (text or "").strip()
    if not cleaned:
        return 0.0

    analyzer = _vader_analyzer()
    if analyzer is not None:
        compound = analyzer.polarity_scores(cleaned)["compound"]
        return round(max(-1.0, min(1.0, compound)), 3)

    return round(_keyword_sentiment(cleaned), 3)
