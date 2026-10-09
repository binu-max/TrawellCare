from dataclasses import dataclass
from uuid import UUID

WEIGHTS = {"price": 0.40, "specialty": 0.30, "rating": 0.20, "history": 0.10}


@dataclass(frozen=True)
class TariffCandidate:
    id: UUID
    procedure_slug: str
    procedure_name: str
    specialty: str
    amount_minor: int
    currency: str
    rating: float
    hospital_name: str
    title: str


def rank_tariffs(candidates: list[TariffCandidate], procedure_interest: str, limit: int = 3) -> list[tuple[TariffCandidate, float]]:
    interest = (procedure_interest or "").strip().lower()

    def matches(candidate: TariffCandidate) -> bool:
        if not interest:
            return False
        haystack = " ".join(
            (candidate.procedure_slug, candidate.procedure_name, candidate.specialty, candidate.title)
        ).lower()
        return interest in haystack

    matched = [candidate for candidate in candidates if matches(candidate)]
    pool = matched or list(candidates)
    if not pool:
        return []
    amounts = [candidate.amount_minor for candidate in pool]
    low, high = min(amounts), max(amounts)
    ranked: list[tuple[TariffCandidate, float]] = []
    for candidate in pool:
        price_score = 1.0 if high == low else (high - candidate.amount_minor) / (high - low)
        specialty_score = 1.0 if matched else 0.5
        rating_score = max(0.0, min(candidate.rating / 5.0, 1.0))
        score = (
            WEIGHTS["price"] * price_score
            + WEIGHTS["specialty"] * specialty_score
            + WEIGHTS["rating"] * rating_score
            + WEIGHTS["history"] * 0.0
        )
        ranked.append((candidate, round(score, 4)))
    ranked.sort(key=lambda item: (-item[1], item[0].amount_minor))
    return ranked[:limit]
