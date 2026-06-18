from backend.badge import render_badge_svg


def test_badge_is_valid_svg_with_amount():
    svg = render_badge_svg(42.5)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "burnmeter" in svg
    assert "$42.50" in svg


def test_badge_formats_two_decimals():
    assert "$0.00" in render_badge_svg(0)
    assert "$1234.60" in render_badge_svg(1234.6)


def test_badge_contains_no_secret_inputs():
    # Only the dollar figure is ever rendered.
    svg = render_badge_svg(7.0)
    for needle in ("sk-", "AIza", "api", "key"):
        assert needle.lower() not in svg.lower()


from backend import badge as badge_mod


def test_badge_file_written(tmp_path):
    path = tmp_path / "burn-badge.svg"
    badge_mod.write_badge(str(path), 12.3)
    assert path.read_text().startswith("<svg")
    assert "$12.30" in path.read_text()
