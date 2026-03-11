# velocity.py — Velocity Curves: per-video view-history timelines
import json, os, webbrowser
from rich.table import Table
from rich.prompt import Prompt
from rich import box

from utils import console, section, fmt, db_file


def _compute_velocity_data(db, top_n=30):
    """Extract per-video view-history timelines for the top N videos by view count."""
    items = []
    for vid, v in db.items():
        hist = v.get("view_history", [])
        if len(hist) < 2:
            continue
        items.append({
            "id":      vid,
            "title":   v["title"][:45],
            "channel": v["channel"],
            "views":   v["views"],
            "is_mine": v.get("is_mine", False),
            "points":  [{"views": h["views"], "at": h["at"]} for h in hist],
        })
    items.sort(key=lambda x: x["views"], reverse=True)
    return items[:top_n]


def _vel_status(seq):
    """Return (label, rich_markup) for a view sequence."""
    if len(seq) < 2:
        return "→ Holding", "[dim]→ Holding[/dim]"
    if len(seq) == 2:
        if seq[1] > seq[0]:
            return "↑ Growing", "[green]↑ Growing[/green]"
        return "→ Flat", "[dim]→ Flat[/dim]"
    d1 = seq[-1] - seq[-2]
    d2 = seq[-2] - seq[-3]
    if d2 <= 0:
        return "↑ Growing", "[green]↑ Growing[/green]"
    chg = (d1 - d2) / d2
    if chg > 0.5:    return "🚀 Accelerating", "[bold green]🚀 Accelerating[/bold green]"
    if chg > 0.1:    return "↑ Still Growing", "[green]↑ Still Growing[/green]"
    if chg > -0.2:   return "→ Holding",       "[dim]→ Holding[/dim]"
    if chg > -0.5:   return "↓ Slowing",       "[yellow]↓ Slowing[/yellow]"
    return "📉 Fading", "[red]📉 Fading[/red]"


def show_velocity_curves(rows):
    section("VELOCITY CURVES  —  Is It Still Climbing or Already Dead?")
    if not os.path.exists(db_file()):
        console.print("  [dim]No data yet — scan first.[/dim]\n"); return

    with open(db_file()) as f:
        db = json.load(f)
    items = _compute_velocity_data(db, top_n=20)
    if not items:
        console.print("  [dim]Need 2+ scans to build velocity history. Scan again later.[/dim]\n"); return

    BLOCKS = " ▁▂▃▄▅▆▇█"
    accel_count = sum(1 for it in items if _vel_status([p["views"] for p in it["points"]])[0] == "🚀 Accelerating")
    fading_count = sum(1 for it in items if _vel_status([p["views"] for p in it["points"]])[0] == "📉 Fading")
    console.print(f"  [bold green]{accel_count} accelerating[/bold green]  "
                  f"[red]{fading_count} fading[/red]  [dim]{len(items)} tracked[/dim]\n")

    t = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white", min_width=90)
    t.add_column("#",        style="dim",          width=3,  justify="right")
    t.add_column("Channel",  style="cyan",         width=20)
    t.add_column("Title",    style="white",        width=32)
    t.add_column("Views",    style="bright_white", width=10, justify="right")
    t.add_column("Scans",    style="dim",          width=6,  justify="right")
    t.add_column("Velocity", style="yellow",       width=22)
    t.add_column("Sparkline ▸", style="dim",       width=14)

    for i, it in enumerate(items, 1):
        pts  = it["points"]
        seq  = [p["views"] for p in pts]
        mx   = max(seq) or 1
        spark = "".join(BLOCKS[min(int(v / mx * 8), 8)] for v in seq)
        _, vel_markup = _vel_status(seq)
        is_me = it.get("is_mine", False)
        ch_label = f"[bold yellow]{it['channel'][:18]} ★[/bold yellow]" if is_me else it["channel"][:20]
        t.add_row(str(i), ch_label, it["title"][:32], fmt(it["views"]), str(len(pts)),
                  vel_markup, f"[dim]{spark}[/dim]")

    console.print(t)
    console.print()
    pick = Prompt.ask("  Open # (Enter skip)", default="").strip()
    if pick.isdigit():
        idx = int(pick) - 1
        if 0 <= idx < len(items):
            webbrowser.open(f"https://youtube.com/shorts/{items[idx]['id']}")
