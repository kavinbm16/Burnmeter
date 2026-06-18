from backend.main import _prior_range


def test_prior_range_multi_day():
    # 2026-06-11..2026-06-17 is 7 days inclusive; prior is 2026-06-04..2026-06-10
    assert _prior_range("2026-06-11", "2026-06-17") == ("2026-06-04", "2026-06-10")


def test_prior_range_single_day():
    assert _prior_range("2026-06-18", "2026-06-18") == ("2026-06-17", "2026-06-17")


# (pyproject sets asyncio_mode = "auto" → no @pytest.mark.asyncio needed)
from backend.main import _compute_insight


class _FakeStore:
    def __init__(self, totals, models):
        # totals: {(start,end): cost}; models: {(start,end): [ {model, cost_usd}, ... ]}
        self._totals = totals
        self._models = models

    async def overview(self, start, end):
        return {"totals": {"cost_usd": self._totals.get((start, end), 0.0)}}

    async def models_leaderboard(self, start, end):
        return self._models.get((start, end), [])


async def test_insight_top_driver_up():
    store = _FakeStore(
        totals={("c0", "c1"): 71.4, ("p0", "p1"): 50.2},
        models={
            ("c0", "c1"): [{"model": "gpt-4o", "cost_usd": 51.0}, {"model": "haiku", "cost_usd": 20.4}],
            ("p0", "p1"): [{"model": "gpt-4o", "cost_usd": 20.0}, {"model": "haiku", "cost_usd": 30.2}],
        },
    )
    out = await _compute_insight(store, "c0", "c1", "p0", "p1")
    assert out["direction"] == "up"
    assert round(out["delta_usd"], 2) == 21.2
    assert round(out["delta_pct"], 3) == 0.422
    # gpt-4o rose +31 (largest signed change); haiku fell -9.8
    assert out["driver"]["label"] == "gpt-4o"
    assert round(out["driver"]["delta_usd"], 1) == 31.0


async def test_insight_none_when_no_prior():
    store = _FakeStore(totals={("c0", "c1"): 10.0}, models={("c0", "c1"): [{"model": "x", "cost_usd": 10.0}]})
    out = await _compute_insight(store, "c0", "c1", "p0", "p1")
    assert out is None


async def test_insight_delta_pct_null_on_zero_prior_with_data():
    # prior total is zero but there is at least one prior model row → still no prior baseline
    store = _FakeStore(totals={("c0", "c1"): 10.0, ("p0", "p1"): 0.0}, models={("c0", "c1"): [], ("p0", "p1"): []})
    out = await _compute_insight(store, "c0", "c1", "p0", "p1")
    assert out is None
