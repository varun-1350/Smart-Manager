from __future__ import annotations

from dataclasses import dataclass

from .intents import MUTATING_INTENTS, SAME_ACTION  # noqa: F401 (MUTATING_INTENTS re-exported for train.py)

# Starting values for a tiny dataset. Tune them with the evaluation report.
MIN_CONFIDENCE = 0.45
MIN_CONFIDENCE_MUTATING = 0.60
MIN_MARGIN = 0.10          # gap between best and second-best intent


@dataclass(frozen=True)
class Confidence:
    top_intent: str
    top_prob: float
    second_intent: str | None
    margin: float


def summarize(classes, probs) -> Confidence:
    order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
    top = order[0]
    second = order[1] if len(order) > 1 else None
    top_p = float(probs[top])
    second_p = float(probs[second]) if second is not None else 0.0
    return Confidence(
        top_intent=str(classes[top]),
        top_prob=top_p,
        second_intent=str(classes[second]) if second is not None else None,
        margin=top_p - second_p,
    )


def is_confident(c: Confidence) -> bool:
    threshold = MIN_CONFIDENCE_MUTATING if c.top_intent in MUTATING_INTENTS else MIN_CONFIDENCE
    # Top two are the same action (both clipboard intents): pool their probability
    # and skip the margin test.
    if c.second_intent and frozenset({c.top_intent, c.second_intent}) in SAME_ACTION:
        second_prob = c.top_prob - c.margin
        return c.top_prob + second_prob >= threshold
    return c.top_prob >= threshold and c.margin >= MIN_MARGIN