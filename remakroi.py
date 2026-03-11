# remakroi.py — Remake ROI: win-rate breakdown by format, source size, channel
import statistics
from collections import defaultdict

from rich.table import Table
from rich.columns import Columns
from rich import box

from utils import console, section, load_remakes


def _detect_remake_format(title):
    t = title.lower()
    if any(x in t for x in ("pov", "when you", "me when")):            return "POV"
    if any(x in t for x in ("how to", "tutorial")):                    return "Tutorial"
    if any(x in t for x in ("tier list", "ranking", "best ", "top ")): return "Ranking"
    if " vs " in t:                                                     return "Comparison"
    if any(x in t for x in ("secret", "hidden", "you didn't know")):   return "Reveal"
    if any(x in t for x in ("challenge", "i tried")):                  return "Challenge"
    if any(x in t for x in ("react", "reacting")):                     return "Reaction"
    return "Other"


def _sat_tier(source_views):
    if source_views >= 5_000_000: return "Mega (5M+)"
    if source_views >= 1_000_000: return "Viral (1M+)"
    if source_views >= 500_000:   return "Hot (500K+)"
    return "Moderate (<500K)"


def _compute_remake_roi():
    remakes = load_remakes()
    if not remakes:
        return None

    all_items = list(remakes.values())
    total   = len(all_items)
    success = sum(1 for r in all_items if r.get("result") == "success")
    flop    = sum(1 for r in all_items if r.get("result") == "flop")
    pending = sum(1 for r in all_items if r.get("result") == "pending")
    judged  = max(total - pending, 1)

    def group_breakdown(key_fn):
        grp = defaultdict(lambda: {"total": 0, "success": 0, "flop": 0, "your_pcts": []})
        for r in all_items:
            k = key_fn(r)
            grp[k]["total"] += 1
            if r.get("result") == "success": grp[k]["success"] += 1
            if r.get("result") == "flop":    grp[k]["flop"] += 1
            if r.get("your_views") and r.get("source_views"):
                grp[k]["your_pcts"].append(r["your_views"] / r["source_views"] * 100)
        out = []
        for name, d in grp.items():
            judged_grp = d["success"] + d["flop"]
            avg_pct = round(statistics.mean(d["your_pcts"]), 1) if d["your_pcts"] else None
            sr = round(d["success"] / max(judged_grp, 1) * 100)
            out.append({
                "name": name, "total": d["total"], "success": d["success"],
                "flop": d["flop"], "success_rate": sr, "avg_pct": avg_pct,
            })
        out.sort(key=lambda x: x["success_rate"], reverse=True)
        return out

    by_format  = group_breakdown(lambda r: _detect_remake_format(r.get("source_title", "")))
    by_channel = group_breakdown(lambda r: r.get("source_channel", "Unknown"))
    by_sat     = group_breakdown(lambda r: _sat_tier(r.get("source_views", 0)))

    # Learning curve: rolling win rate after each judged remake
    timeline = []
    running_s = running_t = 0
    for r in sorted(all_items, key=lambda x: x.get("logged_at", "")):
        if r.get("result") in ("success", "flop"):
            running_t += 1
            if r.get("result") == "success": running_s += 1
            timeline.append({"n": running_t, "rate": round(running_s / running_t * 100)})

    return {
        "total": total, "success": success, "flop": flop, "pending": pending,
        "overall_rate": round(success / judged * 100),
        "by_format":   by_format,
        "by_channel":  by_channel,
        "by_sat":      by_sat,
        "timeline":    timeline,
        "all":         all_items,
    }


def show_remake_roi(rows):
    section("REMAKE ROI  —  Win Rate by Format · Channel · Saturation")
    roi = _compute_remake_roi()
    if not roi:
        console.print("  [dim]No remakes logged yet.[/dim]\n")
        console.print("  [dim]From Brainstorm (option 5), pick a video and press R# to log it.[/dim]\n")
        return

    console.print(
        f"  [bold green]{roi['success']} wins[/bold green]  "
        f"[red]{roi['flop']} flops[/red]  [dim]{roi['pending']} pending[/dim]  "
        f"[bold white]{roi['overall_rate']}% overall win rate[/bold white]\n"
    )

    def mini_table(title, rows_data):
        t = Table(
            title=title, box=box.SIMPLE_HEAVY, border_style="bright_black",
            header_style="bold white", title_style="bold yellow", min_width=45,
        )
        t.add_column("Name",     style="cyan",  width=22)
        t.add_column("Tries",    style="dim",   width=6,  justify="right")
        t.add_column("Wins",     style="green", width=5,  justify="right")
        t.add_column("Win %",    style="white", width=8,  justify="right")
        t.add_column("Avg %Src", style="dim",   width=9,  justify="right")
        t.add_column("Bar",      style="dim",   width=15)
        for d in rows_data:
            sr = d["success_rate"]
            color = "green" if sr >= 60 else "yellow" if sr >= 40 else "red"
            bar = "█" * int(sr / 5)
            avg_str = f"{d['avg_pct']:.0f}%" if d.get("avg_pct") is not None else "—"
            t.add_row(
                str(d["name"])[:22], str(d["total"]), str(d["success"]),
                f"[{color}]{sr}%[/{color}]", avg_str, f"[{color}]{bar}[/{color}]",
            )
        return t

    console.print(Columns([
        mini_table("By Format",      roi["by_format"]),
        mini_table("By Source Size", roi["by_sat"]),
    ], padding=(0, 3)))
    console.print()
    console.print(mini_table("By Source Channel", roi["by_channel"][:12]))

    if roi["timeline"] and len(roi["timeline"]) >= 3:
        console.print("\n  [bold white]Learning Curve (win rate over time):[/bold white]\n")
        for p in roi["timeline"]:
            bar = "█" * int(p["rate"] / 5)
            color = "green" if p["rate"] >= 60 else "yellow" if p["rate"] >= 40 else "red"
            console.print(f"  Remake #{p['n']:>2}  [dim]{bar:<20}[/dim]  [{color}]{p['rate']}%[/{color}]")

        first3 = sum(p["rate"] for p in roi["timeline"][:3]) / 3
        last3  = sum(p["rate"] for p in roi["timeline"][-3:]) / 3
        if last3 > first3 + 5:
            console.print("\n  [green]📈 Win rate is improving — you're getting sharper at picking winners.[/green]")
        elif last3 < first3 - 5:
            console.print("\n  [red]📉 Win rate dropping — try different formats or channels.[/red]")
        else:
            console.print("\n  [dim]→ Win rate stable. Experiment with different formats.[/dim]")
    console.print()
