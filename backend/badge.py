"""Render a shields-style SVG badge. Input is ONLY a dollar figure — never any
key, provider, or secret material."""
from __future__ import annotations


def render_badge_svg(amount_usd: float) -> str:
    value = f"${amount_usd:.2f}"
    label = "burnmeter"
    # crude but stable widths (6px/char + padding) so the badge renders standalone
    lw = 8 + len(label) * 6
    vw = 8 + len(value) * 7
    w = lw + vw
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" '
        f'aria-label="{label}: {value}">'
        f'<rect width="{lw}" height="20" fill="#2a2a2e"/>'
        f'<rect x="{lw}" width="{vw}" height="20" fill="#e5484d"/>'
        f'<g fill="#fff" font-family="Verdana,Geneva,sans-serif" font-size="11">'
        f'<text x="{lw / 2:.0f}" y="14" text-anchor="middle">{label}</text>'
        f'<text x="{lw + vw / 2:.0f}" y="14" text-anchor="middle">{value}</text>'
        f'</g></svg>'
    )


def write_badge(path: str, amount_usd: float) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_badge_svg(amount_usd))
