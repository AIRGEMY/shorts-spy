# wordpower.py — Word Power: title words ranked by view multiplier vs global avg
import statistics
from collections import defaultdict

from rich.table import Table
from rich import box

from utils import console, section, fmt

WORD_STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","is","it",
    "this","that","be","are","was","were","i","my","you","your","with","how",
    "what","when","they","their","have","has","all","not","do","did","just",
    "so","up","out","we","he","she","vs","s","can","its","if","as","by",
    "from","get","got","one","two","three","am","me","him","her","us","no",
    "into","will","would","who","which","been","than","these","those","then",
    "more","about","like","make","use","our","had","his",
}


def _compute_word_performance(rows):
    """Rank every title word by (avg views when present) / (global avg views).
    Returns (results_list, global_avg_int).
    """
    all_views = [r["views"] for r in rows]
    if not all_views:
        return [], 0
    global_avg = statistics.mean(all_views)

    word_views = defaultdict(list)
    for r in rows:
        words = {w.lower().strip(".,!?\"'#:;()[]") for w in r["title"].split()}
        for w in words:
            if w in WORD_STOPWORDS or len(w) < 3:
                continue
            word_views[w].append(r["views"])

    results = []
    for word, views in word_views.items():
        if len(views) < 3:
            continue
        avg  = statistics.mean(views)
        mult = avg / max(global_avg, 1)
        results.append({
            "word":       word,
            "count":      len(views),
            "avg":        int(avg),
            "multiplier": round(mult, 2),
            "best":       max(views),
            "median":     int(statistics.median(views)),
        })

    results.sort(key=lambda x: x["multiplier"], reverse=True)
    return results[:150], int(global_avg)


def show_word_performance(rows):
    section("WORD POWER  —  Which Title Words Correlate With More Views?")
    word_data, global_avg = _compute_word_performance(rows)
    if not word_data:
        console.print("  [dim]Not enough data — scan more channels first (need 3+ title appearances per word).[/dim]\n")
        return

    console.print(
        f"  [dim]Global avg: [white]{fmt(global_avg)}[/white] views  ·  "
        "Min 3 appearances  ·  "
        "Multiplier = avg-when-present ÷ global-avg[/dim]\n"
    )

    t = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white")
    t.add_column("#",          style="dim",          width=4,  justify="right")
    t.add_column("Word",       style="bold cyan",    width=18)
    t.add_column("Multiplier", style="red",          width=11, justify="right")
    t.add_column("Avg Views",  style="bright_white", width=11, justify="right")
    t.add_column("vs Global",  style="yellow",       width=10, justify="right")
    t.add_column("Uses",       style="dim",          width=6,  justify="right")
    t.add_column("Best",       style="green",        width=10, justify="right")

    for i, w in enumerate(word_data[:40], 1):
        delta = (w["multiplier"] - 1) * 100
        delta_str = f"+{int(delta)}%" if delta >= 0 else f"{int(delta)}%"
        color = "green" if w["multiplier"] >= 1.5 else "yellow" if w["multiplier"] >= 1 else "red"
        t.add_row(
            str(i), w["word"],
            f"{w['multiplier']:.2f}×",
            fmt(w["avg"]),
            f"[{color}]{delta_str}[/{color}]",
            str(w["count"]),
            fmt(w["best"]),
        )
    console.print(t)

    # Bottom words — correlated with fewer views
    bottom = [w for w in word_data if w["count"] >= 5 and w["multiplier"] < 1.0]
    bottom.sort(key=lambda x: x["multiplier"])
    if bottom:
        console.print("\n  [bold red]⚠  Words correlated with below-average views:[/bold red]\n")
        for w in bottom[:15]:
            delta = int((w["multiplier"] - 1) * 100)
            console.print(
                f"  [red]{w['multiplier']:.2f}×[/red]  [dim]{w['word']:<18}[/dim]  "
                f"avg {fmt(w['avg'])}  [red]{delta}% below avg[/red]  ({w['count']} uses)"
            )
    console.print()
