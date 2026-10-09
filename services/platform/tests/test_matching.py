from uuid import uuid4

from app.modules.clinical.matching import TariffCandidate, rank_tariffs


def _candidate(name: str, amount: int, rating: float, slug: str = "ivf") -> TariffCandidate:
    return TariffCandidate(
        id=uuid4(),
        procedure_slug=slug,
        procedure_name=name,
        specialty="fertility",
        amount_minor=amount,
        currency="INR",
        rating=rating,
        hospital_name=name,
        title=f"{name} package",
    )


def test_rank_prefers_matching_cheaper_higher_rated_tariffs():
    cheap = _candidate("City", 100, 3)
    pricey = _candidate("Metro", 500, 5)
    other = _candidate("Dental", 50, 5, slug="dental")
    ranked = rank_tariffs([pricey, other, cheap], "ivf")
    assert [item[0].procedure_name for item in ranked] == ["City", "Metro"]
    assert ranked[0][1] >= ranked[1][1]


def test_rank_falls_back_when_nothing_matches():
    ranked = rank_tariffs([_candidate("Dental", 50, 4, slug="dental")], "ivf")
    assert len(ranked) == 1
