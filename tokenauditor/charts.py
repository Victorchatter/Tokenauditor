"""SVG chart generators for tokenauditor.

Light-mode, self-contained SVG strings (no external assets) so they embed in HTML
reports and render inline on GitHub. Palette is the dataviz reference instance,
validated with scripts/validate_palette.js (worst adjacent CVD ΔE 9.1, normal ΔE 19.6;
magenta/yellow/aqua sit below 3:1 contrast on the light surface, which is satisfied
by the direct labels / y-axis labels used here — the relief rule).
"""
from .parsers import Session

# Palette (light) — roles, not raw hex, kept here because SVG can't read CSS vars.
_SURFACE = "#fcfcfb"
_PAGE = "#f9f9f7"
_INK = "#0b0b0b"
_INK_2 = "#52514e"
_MUTED = "#898781"
_GRID = "#e1e0d9"
_AXIS = "#c3c2b7"
_DEEMPH = "#cfcec8"      # gray for the non-story bars
_ACCENT = "#2a78d6"      # slot 1 blue — the emphasized (largest) category
# Per-turn input composition (categorical, validated 3-slot light set)
_SER_CACHE_READ = "#2a78d6"   # slot 1 blue   — cached prefix re-sent
_SER_CACHE_CREATE = "#008300"  # slot 2 green  — newly written to cache
_SER_UNCACHED = "#e87ba4"     # slot 3 magenta — fresh, uncached input

_CAT_ORDER = ["system+tools_prefix", "user_text", "assistant_text",
              "thinking", "tool_use_args", "tool_results"]
_CAT_LABEL = {
    "system+tools_prefix": "system + tools prefix",
    "user_text": "user turns",
    "assistant_text": "assistant text",
    "thinking": "thinking",
    "tool_use_args": "tool-call args",
    "tool_results": "tool results",
}


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _fmt(n):
    return f"{n:,}"


def category_bar_svg(session: Session, width: int = 720) -> str:
    """Horizontal bar chart of the estimated category breakdown.

    One measure (estimated tokens), nominal categories — y-axis labels carry
    identity, so color isn't needed to tell them apart. Emphasis form: the
    largest category (the waste) in accent blue, the rest in de-emphasis gray.
    """
    cats = session.categories
    rows = [(k, cats.get(k, 0)) for k in _CAT_ORDER if cats.get(k, 0) > 0 or k in cats]
    if not rows:
        return ""
    max_v = max(v for _, v in rows) or 1
    biggest = max(rows, key=lambda r: r[1])[0]

    left = 168
    right = width - 78
    plot_w = right - left
    row_h = 40
    bar_h = 24
    top = 64
    height = top + 28 + row_h * len(rows) + 16

    out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" role="img" '
           f'aria-label="Estimated token breakdown by category">']
    out.append(f'<rect width="{width}" height="{height}" fill="{_SURFACE}"/>')

    # title + subtitle
    out.append(f'<text x="24" y="30" font-size="16" font-weight="600" fill="{_INK}">'
               f'Where the budget went</text>')
    out.append(f'<text x="24" y="48" font-size="11" fill="{_INK_2}">'
               f'estimated tokens by category &middot; {_esc(session.format)}</text>')

    # x gridlines + ticks (4 steps)
    for i in range(5):
        gx = left + plot_w * i // 4
        out.append(f'<line x1="{gx}" y1="{top}" x2="{gx}" y2="{top + row_h*len(rows)}" '
                   f'stroke="{_GRID}" stroke-width="1"/>')
        out.append(f'<text x="{gx}" y="{top + row_h*len(rows) + 16}" font-size="10" '
                   f'fill="{_MUTED}" text-anchor="middle">{_fmt(max_v*i//4)}</text>')

    for i, (k, v) in enumerate(rows):
        y = top + i * row_h + (row_h - bar_h) // 2
        # y-axis label (identity) — text token, not series color
        out.append(f'<text x="{left - 14}" y="{y + bar_h - 6}" font-size="12" '
                   f'fill="{_INK_2}" text-anchor="end">{_esc(_CAT_LABEL.get(k, k))}</text>')
        # bar: 4px rounded data-end, square at baseline (x=left)
        fill = _ACCENT if k == biggest else _DEEMPH
        bw = int(plot_w * v / max_v)
        out.append(f'<rect x="{left}" y="{y}" width="{bw}" height="{bar_h}" rx="4" ry="4" '
                   f'fill="{fill}"/>')
        # value at the tip, in ink (never the series color)
        out.append(f'<text x="{left + bw + 8}" y="{y + bar_h - 6}" font-size="12" '
                   f'fill="{_INK}">{_fmt(v)}</text>')

    out.append(f'<text x="{width - 24}" y="{height - 8}" font-size="10" fill="{_MUTED}" '
               f'text-anchor="end">~{ _esc(_fmt(cats.get("total_visible", 0))) } total visible</text>')
    out.append("</svg>")
    return "\n".join(out)


def turn_area_svg(session: Session, width: int = 760, height: int = 300) -> str:
    """Stacked area of per-turn reported input composition.

    Bottom→top: cache_read (cached prefix re-sent), cache_creation (newly cached),
    uncached input. Only rendered when turns carry reported usage (Claude Code /
    Codex with token_count); returns "" for OpenAI-style transcripts.
    """
    turns = [t for t in session.turns if t.total_input > 0 or t.cache_read > 0
             or t.cache_creation > 0]
    if len(turns) < 2:
        return ""

    left, right = 56, width - 24
    top, bottom = 52, height - 44
    plot_w = right - left
    plot_h = bottom - top
    n = len(turns)
    max_total = max((t.cache_read + t.cache_creation + max(0, t.total_input - t.cache_read - t.cache_creation)
                     for t in turns), default=1) or 1

    def x(i):
        return left + (plot_w * i / (n - 1))

    def y(val):
        return bottom - (plot_h * val / max_total)

    # Build cumulative stacks: [uncached, cache_creation, cache_read] drawn bottom-up.
    # layer values per turn
    def uncached(t):
        return max(0, t.total_input - t.cache_read - t.cache_creation)

    layers = [
        ("cache_read", _SER_CACHE_READ, lambda t: t.cache_read),
        ("cache_creation", _SER_CACHE_CREATE, lambda t: t.cache_creation),
        ("uncached input", _SER_UNCACHED, uncached),
    ]

    out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="system-ui,-apple-system,Segoe UI,sans-serif" role="img" '
           f'aria-label="Per-turn reported input composition">']
    out.append(f'<rect width="{width}" height="{height}" fill="{_SURFACE}"/>')
    out.append(f'<text x="24" y="26" font-size="16" font-weight="600" fill="{_INK}">'
               f'Context over the session</text>')
    out.append(f'<text x="24" y="44" font-size="11" fill="{_INK_2}">'
               f'reported input tokens per turn &middot; stacked</text>')

    # y gridlines (4 steps)
    for i in range(5):
        gy = bottom - plot_h * i // 4
        out.append(f'<line x1="{left}" y1="{gy}" x2="{right}" y2="{gy}" '
                   f'stroke="{_GRID}" stroke-width="1"/>')
        out.append(f'<text x="{left - 8}" y="{gy + 3}" font-size="10" fill="{_MUTED}" '
                   f'text-anchor="end">{_fmt(max_total*i//4)}</text>')

    # stacked areas: cumulative from bottom
    cum = [0] * n
    for name, color, getter in layers:
        vals = [getter(t) for t in turns]
        new_cum = [cum[i] + vals[i] for i in range(n)]
        # top edge of this band = new_cum; bottom edge = cum
        top_pts = [f"{x(i):.1f},{y(new_cum[i]):.1f}" for i in range(n)]
        bot_pts = [f"{x(i):.1f},{y(cum[i]):.1f}" for i in range(n - 1, -1, -1)]
        d = "M " + " L ".join(top_pts) + " L " + " L ".join(bot_pts) + " Z"
        out.append(f'<path d="{d}" fill="{color}" fill-opacity="0.92"/>')
        # 2px surface separator along the top edge of this band (except the topmost)
        out.append(f'<polyline points="{" ".join(top_pts)}" fill="none" '
                   f'stroke="{_SURFACE}" stroke-width="2"/>')
        cum = new_cum

    # x-axis baseline
    out.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" '
               f'stroke="{_AXIS}" stroke-width="1"/>')
    out.append(f'<text x="{left}" y="{height - 18}" font-size="10" fill="{_MUTED}">turn 1</text>')
    out.append(f'<text x="{right}" y="{height - 18}" font-size="10" fill="{_MUTED}" '
               f'text-anchor="end">turn {n}</text>')

    # legend (≥2 series → always present)
    lx = left + 8
    ly = top + 10
    for name, color, _ in layers:
        out.append(f'<rect x="{lx}" y="{ly}" width="10" height="10" rx="2" fill="{color}"/>')
        out.append(f'<text x="{lx + 14}" y="{ly + 9}" font-size="10" fill="{_INK_2}">'
                   f'{_esc(name)}</text>')
        lx += 14 + len(name) * 6 + 18

    out.append("</svg>")
    return "\n".join(out)