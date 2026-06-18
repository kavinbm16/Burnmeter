from backend.main import _prior_range


def test_prior_range_multi_day():
    # 2026-06-11..2026-06-17 is 7 days inclusive; prior is 2026-06-04..2026-06-10
    assert _prior_range("2026-06-11", "2026-06-17") == ("2026-06-04", "2026-06-10")


def test_prior_range_single_day():
    assert _prior_range("2026-06-18", "2026-06-18") == ("2026-06-17", "2026-06-17")
