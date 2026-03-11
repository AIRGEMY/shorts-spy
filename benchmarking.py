import statistics
from collections import defaultdict, Counter
from rich.prompt import Prompt
from rich.table import Table
from rich import box

from utils import console, section, fmt
from trends import _extract_topic_keywords
import state

def _compute_benchmarks(rows):
    """
    Compares YOUR channel's aggregate stats against all competitors.
    Returns a dict with per-metric breakdowns.
    """
    my_rows    = [r for r in rows if r.get("is_mine")]
    their_rows = [r for r in rows if not r.get("is_mine")]

    if not my_rows:
        return None

    def safe_mean(lst): return statistics.mean(lst) if lst else 0
    def safe_median(lst): return statistics.median(lst) if lst else 0

    # Per-competitor-channel aggregates
    comp_ch = defaultdict(list)
    for r in their_rows:
        comp_ch[r["channel"]].append(r)

    def ch_metric(ch_rows, fn):
        vals = [fn(r) for r in ch_rows]
        return safe_mean(vals) if vals else 0

    metrics = [
        ("avg_views",   "Avg Views",       lambda r: r["views"],      fmt),
        ("avg_vpd",     "Views/Day",        lambda r: r["vpd"],        fmt),
        ("avg_score",   "Hype Score",       lambda r: r["score"],      lambda x: f"{x:.2f}×"),
        ("avg_lr",      "Like Ratio %",     lambda r: r["like_ratio"], lambda x: f"{x:.2f}%"),
        ("avg_likes",   "Avg Likes",        lambda r: r["likes"],      fmt),
        ("avg_comments","Avg Comments",     lambda r: r["comments"],   fmt),
        ("top_video",   "Best Video Views", lambda r: r["views"],      fmt),
    ]

    results = {}
    for key, label, fn, fmt_fn in metrics:
        my_vals   = [fn(r) for r in my_rows]
        their_vals= [fn(r) for r in their_rows]

        if key == "top_video":
            my_val    = max(my_vals)    if my_vals    else 0
            their_val = max(their_vals) if their_vals else 0
        else:
            my_val    = safe_mean(my_vals)
            their_val = safe_mean(their_vals)

        gap_ratio  = round(their_val / max(my_val, 0.001), 2)
        pct_behind = round((their_val - my_val) / max(their_val, 0.001) * 100, 1)
        rank_pos   = sum(1 for ch, ch_rows in comp_ch.items()
                         if ch_metric(ch_rows, fn) > my_val) + 1
        total_chs  = len(comp_ch) + 1  # +1 for you

        # Per-channel breakdown
        ch_breakdown = []
        for ch_name, ch_rows in comp_ch.items():
            val = max(fn(r) for r in ch_rows) if key=="top_video" else ch_metric(ch_rows, fn)
            ch_breakdown.append({"channel": ch_name, "value": val})
        ch_breakdown.append({"channel": "★ YOU", "value": my_val, "is_mine": True})
        ch_breakdown.sort(key=lambda x: x["value"], reverse=True)

        results[key] = {
            "label":        label,
            "my_val":       my_val,
            "their_val":    their_val,
            "gap_ratio":    gap_ratio,
            "pct_behind":   pct_behind,
            "rank":         rank_pos,
            "total":        total_chs,
            "fmt_fn":       fmt_fn,
            "breakdown":    ch_breakdown[:15],
            "raw_my":       my_vals,
            "raw_their":    their_vals,
        }

    # Best-performing topics for you vs competitors
    my_kws  = Counter()
    for r in my_rows:
        for kw in _extract_topic_keywords(r["title"]):
            my_kws[kw] += r["views"]

    comp_kws = Counter()
    for r in their_rows:
        for kw in _extract_topic_keywords(r["title"]):
            comp_kws[kw] += r["views"]

    results["_my_name"]   = my_rows[0]["channel"] if my_rows else "You"
    results["_my_count"]  = len(my_rows)
    results["_their_count"] = len(their_rows)
    results["_my_top_kws"]   = my_kws.most_common(10)
    results["_comp_top_kws"] = comp_kws.most_common(10)

    return results


def show_benchmarking(rows):
    section("YOUR CHANNEL  vs  COMPETITORS")

    bm = _compute_benchmarks(rows)
    if not bm:
        console.print("  [dim]YOUR_CHANNEL not found in data.[/dim]\n")
        console.print("  [dim]Make sure YOUR_CHANNEL at the top of the file matches your channel ID.[/dim]\n")
        return

    my_name = bm["_my_name"]
    console.print(f"  Channel: [bold yellow]{my_name}[/bold yellow]  ·  "
                  f"[dim]{bm['_my_count']} your videos  ·  {bm['_their_count']} competitor videos[/dim]\n")

    METRIC_KEYS = ["avg_views","avg_vpd","avg_score","avg_lr","avg_likes","avg_comments","top_video"]

    # ── Summary scorecard ──
    t = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white", title="📊  Performance Scorecard", title_style="bold yellow")
    t.add_column("Metric",       style="white",        width=18)
    t.add_column("★ You",        style="bold yellow",  width=12, justify="right")
    t.add_column("Competitor Avg",style="cyan",        width=14, justify="right")
    t.add_column("Gap",          style="red",          width=10, justify="right")
    t.add_column("Your Rank",    style="bright_white", width=12, justify="right")
    t.add_column("Status",       style="dim",          width=20)

    for key in METRIC_KEYS:
        d  = bm[key]
        ff = d["fmt_fn"]
        gap_str = f"{d['gap_ratio']:.1f}×" if d["gap_ratio"] > 1 else "[green]ahead![/green]"

        if d["gap_ratio"] <= 1.0:
            status = "[bold green]✅ Beating avg[/bold green]"
        elif d["gap_ratio"] <= 1.5:
            status = "[yellow]⚠ Close behind[/yellow]"
        elif d["gap_ratio"] <= 3.0:
            status = "[red]⬇ Trailing[/red]"
        else:
            status = "[bold red]🚨 Big gap[/bold red]"

        rank_str = f"#{d['rank']} of {d['total']}"
        t.add_row(
            d["label"],
            ff(d["my_val"]),
            ff(d["their_val"]),
            gap_str,
            rank_str,
            status,
        )
    console.print(t)
    console.print()

    # ── Per-metric channel ranking ──
    section_choice = Prompt.ask(
        "\n  Deep-dive metric:\n"
        "  [cyan]1[/cyan] Views  [cyan]2[/cyan] VPD  [cyan]3[/cyan] Hype  [cyan]4[/cyan] Like%  "
        "[cyan]5[/cyan] Best Video  [cyan]q[/cyan] Skip",
        default="q"
    ).strip().lower()

    key_map = {"1":"avg_views","2":"avg_vpd","3":"avg_score","4":"avg_lr","5":"top_video"}
    if section_choice in key_map:
        key = key_map[section_choice]
        d   = bm[key]
        ff  = d["fmt_fn"]
        console.print(f"\n  [bold white]{d['label']} — Channel Ranking[/bold white]\n")
        t2 = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white")
        t2.add_column("Rank",    style="dim",          width=6,  justify="right")
        t2.add_column("Channel", style="white",        width=28)
        t2.add_column("Value",   style="bright_white", width=14, justify="right")
        t2.add_column("vs You",  style="yellow",       width=12, justify="right")
        for rank, ch_d in enumerate(d["breakdown"], 1):
            is_me = ch_d.get("is_mine", False)
            ratio_vs_you = round(ch_d["value"] / max(d["my_val"], 0.001), 2)
            vs_str = "[bold yellow]— you —[/bold yellow]" if is_me else f"{ratio_vs_you:.1f}×"
            ch_label = f"[bold yellow]{ch_d['channel']}[/bold yellow]" if is_me else ch_d["channel"]
            t2.add_row(f"#{rank}", ch_label, ff(ch_d["value"]), vs_str)
        console.print(t2)

    # ── Topic overlap ──
    console.print(f"\n  [bold white]Your Top Topics vs Competitor Top Topics[/bold white]\n")
    t3 = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white")
    t3.add_column(f"★ {my_name[:20]} (by total views)", style="yellow", width=28)
    t3.add_column("Competitors (by total views)",        style="cyan",   width=28)

    my_kws   = bm["_my_top_kws"]
    comp_kws = bm["_comp_top_kws"]
    rows_len = max(len(my_kws), len(comp_kws))
    for i in range(rows_len):
        my_side   = f"{my_kws[i][0]}  [dim]{fmt(my_kws[i][1])}[/dim]"   if i < len(my_kws)   else ""
        comp_side = f"{comp_kws[i][0]}  [dim]{fmt(comp_kws[i][1])}[/dim]" if i < len(comp_kws) else ""
        overlap_marker = " ←same" if i < len(my_kws) and i < len(comp_kws) and my_kws[i][0] == comp_kws[i][0] else ""
        t3.add_row(my_side, comp_side + overlap_marker)
    console.print(t3)

    # ── Gap narrative ──
    avg_views_bm = bm["avg_views"]
    console.print(f"\n  [bold white]Gap Summary[/bold white]\n")
    console.print(f"  Your avg views:       [bold yellow]{avg_views_bm['fmt_fn'](avg_views_bm['my_val'])}[/bold yellow]")
    console.print(f"  Competitor avg views: [cyan]{avg_views_bm['fmt_fn'](avg_views_bm['their_val'])}[/cyan]")
    if avg_views_bm['gap_ratio'] > 1:
        console.print(f"  Gap:                  [red]{avg_views_bm['gap_ratio']:.1f}× behind[/red]  [dim]({avg_views_bm['pct_behind']:.0f}% less)[/dim]")
    else:
        console.print(f"  [bold green]  You're outperforming the competitor average! 🎉[/bold green]")

    score_bm = bm["avg_score"]
    console.print(f"\n  Your avg hype score:  [bold yellow]{score_bm['fmt_fn'](score_bm['my_val'])}[/bold yellow]")
    console.print(f"  Competitor avg score: [cyan]{score_bm['fmt_fn'](score_bm['their_val'])}[/cyan]")
    console.print(f"\n  Your rank overall: [bold white]#{avg_views_bm['rank']} out of {avg_views_bm['total']} channels[/bold white]\n")


# ══════════════════════════════════════════════════════════════
#  ANALYSIS MENU
# ══════════════════════════════════════════════════════════════

