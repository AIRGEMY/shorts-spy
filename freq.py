from datetime import datetime, timezone, timedelta
from rich.panel import Panel
from rich.table import Table
from rich import box

from utils import console, section, fmt, load_freq, db_file, load_cache
import state

def _update_freq_tracker(freq, ch_videos_collected, today):
    """
    For each channel, record how many Shorts were published in
    each of the last N weeks, derived from the video publish dates.
    ch_videos_collected: dict channel_name -> [published_iso, ...]
    """
    now = datetime.now(timezone.utc)
    for ch_name, pub_dates in ch_videos_collected.items():
        entry = freq.setdefault(ch_name, {"weekly": {}, "last_seen": today})
        entry["last_seen"] = today
        # Count uploads per ISO week
        for pub in pub_dates:
            if not pub: continue
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                iso_week = dt.strftime("%G-W%V")   # e.g. "2025-W12"
                entry["weekly"][iso_week] = entry["weekly"].get(iso_week, 0) + 1
            except: pass


def _analyse_freq(freq):
    """
    Returns per-channel cadence stats:
    - avg_per_week: rolling 8-week average
    - recent_per_week: last 2 weeks average
    - status: "surge" | "active" | "quiet" | "ghost"
    - trend: change ratio recent vs older
    - weeks_since_last: how many weeks since last upload
    """
    now      = datetime.now(timezone.utc)
    results  = []

    for ch_name, data in freq.items():
        weekly = data.get("weekly", {})
        if not weekly:
            continue

        # Build ordered list of (week_str, count) for last 12 weeks
        week_list = []
        for w in range(11, -1, -1):
            dt      = now - timedelta(weeks=w)
            wk_str  = dt.strftime("%G-W%V")
            week_list.append((wk_str, weekly.get(wk_str, 0)))

        counts = [c for _, c in week_list]
        recent_2  = counts[-2:]
        older_8   = counts[-10:-2]

        avg_recent = sum(recent_2) / max(len(recent_2), 1)
        avg_older  = sum(older_8)  / max(len(older_8),  1)
        avg_all    = sum(counts)   / max(len(counts), 1)

        # Weeks since last upload
        weeks_since = 0
        for i in range(len(counts)-1, -1, -1):
            if counts[i] > 0: break
            weeks_since += 1

        # Status logic
        if weeks_since >= 4:
            status = "ghost"
        elif avg_recent < avg_older * 0.4 and avg_older > 0.5:
            status = "quiet"
        elif avg_recent > avg_older * 1.6 and avg_older > 0:
            status = "surge"
        elif avg_recent > 1.5:
            status = "active"
        else:
            status = "low"

        trend_ratio = round(avg_recent / max(avg_older, 0.1), 2)

        results.append({
            "channel":      ch_name,
            "avg_per_week": round(avg_all, 1),
            "recent_avg":   round(avg_recent, 1),
            "older_avg":    round(avg_older, 1),
            "trend_ratio":  trend_ratio,
            "status":       status,
            "weeks_since":  weeks_since,
            "week_counts":  counts,          # 12 weeks of bars
            "week_labels":  [w for w,_ in week_list],
            "total_tracked": sum(counts),
        })

    results.sort(key=lambda x: (
        {"surge":0,"active":1,"low":2,"quiet":3,"ghost":4}[x["status"]], -x["recent_avg"]
    ))
    return results


def show_freq_tracker(rows):
    section("UPLOAD FREQUENCY TRACKER  —  Cadence · Quiet · Surge")

    freq = load_freq()
    if not freq:
        console.print("  [dim]No frequency data yet — run a Scan first (option 1).[/dim]\n")
        console.print("  [dim]The tracker is populated automatically during each scan.[/dim]\n")
        return

    results = _analyse_freq(freq)
    if not results:
        console.print("  [dim]Not enough history yet. Run 2+ scans over time.[/dim]\n")
        return

    my_name = next((v["channel"] for v in load_rows_if_available() if v.get("is_mine")), None)

    STATUS_COLOR = {
        "surge":  "[bold green]🚀 SURGE[/bold green]",
        "active": "[green]● Active[/green]",
        "low":    "[dim]○ Low[/dim]",
        "quiet":  "[yellow]⚠ Quiet[/yellow]",
        "ghost":  "[red]💀 Ghost[/red]",
    }

    # Summary counts
    surges = [r for r in results if r["status"] == "surge"]
    quiets = [r for r in results if r["status"] in ("quiet","ghost")]
    console.print(f"  [bold green]{len(surges)} surging[/bold green]  ·  [yellow]{len(quiets)} gone quiet / ghost[/yellow]  ·  [dim]{len(results)} channels tracked[/dim]\n")

    # Surge alert panel
    if surges:
        lines = []
        for r in surges[:5]:
            trend_str = f"+{int((r['trend_ratio']-1)*100)}% vs prior avg"
            lines.append(f"  [bold green]{r['channel'][:28]}[/bold green]  [dim]{r['recent_avg']:.1f}/wk now vs {r['older_avg']:.1f}/wk before  ·  {trend_str}[/dim]")
        console.print(Panel("\n".join(lines), title="[bold green]🚀  SURGING — They found something[/bold green]", border_style="green", padding=(0,1)))
        console.print()

    # Quiet / ghost alert panel
    if quiets:
        lines = []
        for r in quiets[:5]:
            gone = f"[red]{r['weeks_since']}w silent[/red]" if r["status"]=="ghost" else f"[yellow]posting dropped {int((1-r['trend_ratio'])*100)}%[/yellow]"
            lines.append(f"  [cyan]{r['channel'][:28]}[/cyan]  {gone}  [dim]was {r['older_avg']:.1f}/wk[/dim]")
        console.print(Panel("\n".join(lines), title="[bold yellow]💤  QUIET — Possible opportunity in their niche[/bold yellow]", border_style="yellow", padding=(0,1)))
        console.print()

    # Full table
    t = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white", min_width=90)
    t.add_column("Channel",    style="cyan",         width=24)
    t.add_column("Status",     style="white",        width=14)
    t.add_column("Recent/wk",  style="bright_white", width=10, justify="right")
    t.add_column("Prior/wk",   style="dim",          width=10, justify="right")
    t.add_column("Trend",      style="yellow",       width=9,  justify="right")
    t.add_column("Streak",     style="dim",          width=9,  justify="right")
    t.add_column("Last 12 Weeks ▸",  style="dim",   width=30)

    for r in results:
        trend_str = (f"[green]+{int((r['trend_ratio']-1)*100)}%[/green]" if r["trend_ratio"] > 1.1
                     else f"[red]{int((r['trend_ratio']-1)*100)}%[/red]" if r["trend_ratio"] < 0.9
                     else "[dim]~flat[/dim]")
        streak_str = (f"[red]{r['weeks_since']}w silent[/red]" if r["weeks_since"] >= 2
                      else "[green]active[/green]")
        # Mini sparkline using block chars
        mx = max(r["week_counts"]) if r["week_counts"] else 1
        BLOCKS = " ▁▂▃▄▅▆▇█"
        spark = "".join(BLOCKS[min(int(c/max(mx,1)*8), 8)] for c in r["week_counts"])
        name_str = f"[bold yellow]{r['channel'][:22]} ★[/bold yellow]" if r["channel"]==my_name else r["channel"][:24]
        t.add_row(
            name_str,
            STATUS_COLOR.get(r["status"], r["status"]),
            f"{r['recent_avg']:.1f}",
            f"{r['older_avg']:.1f}",
            trend_str,
            streak_str,
            f"[dim]{spark}[/dim]",
        )
    console.print(t)
    console.print("\n  [dim]Sparkline = last 12 weeks of upload count · Recent = last 2 weeks · Prior = weeks 3–10[/dim]\n")


def load_rows_if_available():
    """Helper to get rows without requiring all_rows to be passed in."""
    if not os.path.exists(db_file()): return []
    data  = json.load(open(db_file()))
    cache = load_cache()
    return build_rows(data, cache)


# ══════════════════════════════════════════════════════════════
#  ★ NEW FEATURE 3: YOUR CHANNEL BENCHMARKING
#  Shows exactly where your stats sit vs competitors in every metric
# ══════════════════════════════════════════════════════════════

