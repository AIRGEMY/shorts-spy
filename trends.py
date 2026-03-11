import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table
from rich import box
import webbrowser

from utils import console, section, fmt

def _extract_topic_keywords(title):
    """Extract meaningful topic keywords from a title, removing noise words."""
    STOPWORDS = {
        "the","a","an","and","or","but","in","on","at","to","for","of","is","it",
        "this","that","be","are","was","were","i","my","you","your","with","how",
        "what","when","they","their","have","has","all","not","do","did","just",
        "so","up","out","we","he","she","vs","s","can","its","if","as","by",
        "from","about","into","will","would","who","which","been","then","than",
        "these","those","get","got","one","two","three","first","last","new","old",
        "day","time","way","now","back","still","here","there","where","why",
        "made","make","take","took","use","used","pov","shorts","short","youtube",
        "part","every","ever","never","always","just","also","even","only","very",
        "really","actually","literally","basically","guys","people","things","thing"
    }
    words = re.sub(r'[^\w\s]', '', title.lower()).split()
    return [w for w in words if w not in STOPWORDS and len(w) >= 4]


def _compute_trend_radar(rows, window_days=7):
    """
    Groups videos by topic cluster. A 'topic' is a keyword that appears
    in titles from 2+ different channels within the time window.
    Returns ranked trend signals.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    # Only look at recent videos
    recent = [r for r in rows if r.get("published") and
              datetime.fromisoformat(r["published"].replace("Z", "+00:00")) >= cutoff
              and not r.get("is_mine")]

    if not recent:
        return [], window_days

    # Map keyword → list of (channel, views, title, video_id, published)
    kw_map = defaultdict(list)
    for r in recent:
        kws = _extract_topic_keywords(r["title"])
        for kw in set(kws):  # dedupe per video
            kw_map[kw].append({
                "channel": r["channel"],
                "views":   r["views"],
                "title":   r["title"],
                "id":      r["id"],
                "published": r.get("published",""),
                "score":   r["score"],
            })

    # Filter: must appear on 2+ different channels
    trends = []
    for kw, entries in kw_map.items():
        channels = list({e["channel"] for e in entries})
        if len(channels) < 2:
            continue
        total_views = sum(e["views"] for e in entries)
        avg_views   = int(total_views / len(entries))
        best        = max(entries, key=lambda x: x["views"])
        avg_score   = round(sum(e["score"] for e in entries) / len(entries), 2)

        # Trend strength: channels × avg_views × avg_score
        strength = len(channels) * avg_views * max(avg_score, 0.5)

        trends.append({
            "keyword":   kw,
            "channels":  channels,
            "ch_count":  len(channels),
            "vid_count": len(entries),
            "total_views": total_views,
            "avg_views": avg_views,
            "best_title": best["title"],
            "best_views": best["views"],
            "best_channel": best["channel"],
            "best_id":    best["id"],
            "avg_score":  avg_score,
            "strength":   strength,
            "entries":    sorted(entries, key=lambda x: x["views"], reverse=True)[:5],
        })

    trends.sort(key=lambda x: x["strength"], reverse=True)
    return trends[:30], window_days


def show_trend_radar(rows):
    section("TREND RADAR  —  Topics Blowing Up Across Channels")

    window = 7
    choice = Prompt.ask("  Window (days)", default="7").strip()
    try: window = int(choice)
    except: pass

    trends, wd = _compute_trend_radar(rows, window_days=window)

    if not trends:
        console.print(f"  [dim]No cross-channel trends found in the last {wd} days.\n  Tip: Scan more data or widen the window.[/dim]\n")
        return

    console.print(f"  [dim]Analysed last {wd} days · {len(trends)} trend signals detected[/dim]\n")

    t = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white", min_width=90)
    t.add_column("#",         style="dim",          width=3,  justify="right")
    t.add_column("Topic",     style="bold cyan",    width=16)
    t.add_column("Channels",  style="yellow",       width=7,  justify="right")
    t.add_column("Videos",    style="dim",          width=7,  justify="right")
    t.add_column("Avg Views", style="bright_white", width=11, justify="right")
    t.add_column("Best",      style="green",        width=11, justify="right")
    t.add_column("Avg Hype",  style="red",          width=9,  justify="right")
    t.add_column("Signal",    style="dim",          width=18)
    t.add_column("Best Channel", style="cyan",      width=18)

    for i, tr in enumerate(trends[:20], 1):
        ch_count = tr["ch_count"]
        signal = (
            "[bold red]🔥 MULTI-VIRAL[/bold red]" if ch_count >= 5 and tr["avg_score"] >= 3 else
            "[bold magenta]🚨 SURGING[/bold magenta]"    if ch_count >= 4 else
            "[red]📈 TRENDING[/red]"                    if ch_count >= 3 else
            "[yellow]👀 WATCH[/yellow]"
        )
        t.add_row(
            str(i),
            tr["keyword"],
            str(ch_count),
            str(tr["vid_count"]),
            fmt(tr["avg_views"]),
            fmt(tr["best_views"]),
            f"{tr['avg_score']:.1f}×",
            signal,
            tr["best_channel"][:18],
        )
    console.print(t)

    # Detail panel for top 5
    console.print("\n  [bold white]Top 5 Trend Details:[/bold white]\n")
    for i, tr in enumerate(trends[:5], 1):
        ch_list = ", ".join(tr["channels"][:6]) + ("..." if len(tr["channels"]) > 6 else "")
        lines = [
            f"  [bold cyan]#{i}  \"{tr['keyword']}\"[/bold cyan]  [dim]— {tr['ch_count']} channels · {tr['vid_count']} videos · last {wd}d[/dim]",
            f"  [dim]Channels:[/dim] [yellow]{ch_list}[/yellow]",
            f"  [dim]Best video:[/dim] [white]{tr['best_title'][:50]}[/white]  [green]{fmt(tr['best_views'])} views[/green]",
            "  [dim]Top videos:[/dim]",
        ]
        for e in tr["entries"][:3]:
            lines.append(f"    [dim]{e['channel'][:20]}[/dim]  [white]{e['title'][:38]}[/white]  [dim]{fmt(e['views'])}[/dim]")
        console.print(Panel("\n".join(lines), border_style="bright_black", padding=(0,1)))

    pick = Prompt.ask("\n  Open best video for trend # (Enter skip)", default="").strip()
    if pick.isdigit():
        idx = int(pick) - 1
        if 0 <= idx < len(trends):
            webbrowser.open(f"https://youtube.com/shorts/{trends[idx]['best_id']}")


def _compute_trend_radar_data(rows, window_days=7):
    """Web dashboard version — returns serializable data."""
    trends, wd = _compute_trend_radar(rows, window_days=window_days)
    result = []
    for tr in trends:
        result.append({
            "keyword":    tr["keyword"],
            "ch_count":   tr["ch_count"],
            "vid_count":  tr["vid_count"],
            "avg_views":  tr["avg_views"],
            "best_views": tr["best_views"],
            "best_title": tr["best_title"],
            "best_channel": tr["best_channel"],
            "best_id":    tr["best_id"],
            "avg_score":  tr["avg_score"],
            "channels":   tr["channels"][:8],
            "entries":    tr["entries"],
        })
    return result


# ══════════════════════════════════════════════════════════════
#  ★ NEW FEATURE 2: UPLOAD FREQUENCY TRACKER
#  Tracks posting cadence per channel, detects quiet / surge
# ══════════════════════════════════════════════════════════════

