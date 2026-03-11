import json, os, statistics
from datetime import datetime, timezone
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.panel import Panel
from rich import box

from utils import (
    console, section, fmt, age_str, hype_label, days_ago,
    load_notes, save_notes, db_file, load_cache,
    TOP_N, HOF_FILE,
)
import state

RANKINGS = [
    ("Most Views",             "👀", lambda r: r["views"], [
        ("Views",    lambda r: fmt(r["views"]),                         9, "bright_white"),
        ("Ch Avg",   lambda r: f"[dim]{fmt(int(r['ch_avg']))}[/dim]",  8, "white"),
        ("Like %",   lambda r: f"{r['like_ratio']:.1f}%",              7, "bright_blue"),
        ("Vibe",     lambda r: hype_label(r["score"]),                 14, "yellow"),
    ]),
    ("Most Viral (vs ch avg)", "🔥", lambda r: r["score"], [
        ("Hype",     lambda r: f"[bold]{r['score']:.1f}x[/bold]",      7, "red"),
        ("Views",    lambda r: fmt(r["views"]),                         9, "bright_white"),
        ("Ch Avg",   lambda r: f"[dim]{fmt(int(r['ch_avg']))}[/dim]",  8, "white"),
        ("Vibe",     lambda r: hype_label(r["score"]),                 14, "yellow"),
    ]),
    ("Best Daily Pace",        "📈", lambda r: r["vpd"], [
        ("Views/Day",lambda r: fmt(r["vpd"]),                          9, "bright_white"),
        ("Total",    lambda r: fmt(r["views"]),                        9, "white"),
        ("Age",      lambda r: age_str(r.get("published")),            8, "dim"),
        ("Velocity", lambda r: r["velocity"],                         16, "yellow"),
    ]),
    ("Fastest Growing",        "🚀", lambda r: r["growth"], [
        ("Growth",   lambda r: f"[green]+{fmt(r['growth'])}[/green]" if r["growth"]>0 else fmt(r["growth"]), 9, "bright_white"),
        ("Total",    lambda r: fmt(r["views"]),                        9, "white"),
        ("Ch Avg",   lambda r: f"[dim]{fmt(int(r['ch_avg']))}[/dim]", 8, "dim"),
        ("Vibe",     lambda r: hype_label(r["score"]),                14, "yellow"),
    ]),
    ("Most Liked",             "❤️ ", lambda r: r["likes"], [
        ("Likes",    lambda r: fmt(r["likes"]),                        9, "bright_white"),
        ("Like %",   lambda r: f"{r['like_ratio']:.1f}%",             7, "bright_blue"),
        ("Views",    lambda r: fmt(r["views"]),                        9, "white"),
        ("Vibe",     lambda r: hype_label(r["score"]),                14, "yellow"),
    ]),
    ("Best Like/View Ratio",   "💎", lambda r: r["like_ratio"], [
        ("Like %",   lambda r: f"[bold]{r['like_ratio']:.1f}%[/bold]",7, "bright_blue"),
        ("Likes",    lambda r: fmt(r["likes"]),                        9, "bright_white"),
        ("Views",    lambda r: fmt(r["views"]),                        9, "white"),
        ("Vibe",     lambda r: hype_label(r["score"]),                14, "yellow"),
    ]),
    ("Most Comments",          "💬", lambda r: r["comments"], [
        ("Comments", lambda r: fmt(r["comments"]),                     9, "bright_white"),
        ("Views",    lambda r: fmt(r["views"]),                        9, "white"),
        ("Like %",   lambda r: f"{r['like_ratio']:.1f}%",             7, "bright_blue"),
        ("Vibe",     lambda r: hype_label(r["score"]),                14, "yellow"),
    ]),
    ("Sub-Adjusted Viral",     "🏅", lambda r: r["adj_score"], [
        ("Adj Score",lambda r: f"[bold]{r['adj_score']:.1f}x[/bold]", 9, "red"),
        ("Subs",     lambda r: fmt(r["subs"]) if r["subs"] else "[dim]?[/dim]", 9, "dim"),
        ("Raw",      lambda r: f"{r['score']:.1f}x",                  7, "white"),
        ("Vibe",     lambda r: hype_label(r["score"]),                14, "yellow"),
    ]),
]

def make_table(title, emoji, sort_fn, cols, rows, notes):
    top=sorted(rows,key=sort_fn,reverse=True)[:TOP_N]
    t=Table(title=f"{emoji}  {title}",box=box.SIMPLE_HEAVY,border_style="bright_black",
            header_style="bold white",title_style="bold yellow",min_width=80)
    t.add_column("#",style="dim",width=3,justify="right")
    t.add_column("Channel",style="cyan",width=14,no_wrap=True)
    t.add_column("Title",style="white",width=22,no_wrap=True)
    for col_name,_,width,style in cols: t.add_column(col_name,style=style,width=width,justify="right",no_wrap=True)
    for i,r in enumerate(top,1):
        is_me=r.get("is_mine",False)
        ch_label=f"[bold yellow]{r['channel'][:12]} ★[/bold yellow]" if is_me else r["channel"][:14]
        flags = ("⚡" if r.get("is_spike") else "")+("🆕" if r.get("fresh_48h") else "")+("📝" if r["id"] in notes else "")
        t.add_row(str(i),ch_label,r["title"][:20]+flags,*[col_fn(r) for _,col_fn,_,_ in cols])
    return t

def show_dashboard(rows):
    if not rows: console.print("\n  [red]No videos match filters.[/red]\n"); return
    notes=load_notes()
    outliers=sorted([r for r in rows if r["score"]>=5],key=lambda x:x["score"],reverse=True)[:5]
    if outliers:
        lines=[]
        for r in outliers:
            me=" [bold yellow]★[/bold yellow]" if r.get("is_mine") else ""
            spike=" [bold red]⚡[/bold red]" if r.get("is_spike") else ""
            fresh=" [bold cyan]🆕[/bold cyan]" if r.get("fresh_48h") else ""
            vel=f"  {r['velocity']}" if len(r.get("view_history",[])) >= 3 else ""
            lines.append(f"  [bold white]{r['score']:.1f}x[/bold white]  [cyan]{r['channel'][:22]}[/cyan]{me}{spike}{fresh}  [white]{r['title'][:35]}[/white]  [dim]{age_str(r.get('published'))}  {fmt(r['views'])}[/dim]{vel}")
        console.print(Panel("\n".join(lines),title="[bold red]⚡  OUTLIERS — 5x+ above channel average[/bold red]",border_style="red",padding=(0,1)))
        console.print()
    spikes=[r for r in rows if r.get("is_spike")]
    if spikes:
        lines=[f"  [red]+{r.get('spike_pct','?')}%[/red]  [cyan]{r['channel'][:22]}[/cyan]  [white]{r['title'][:35]}[/white]  [dim]+{fmt(r.get('spike_growth',r.get('growth',0)))}[/dim]"
               for r in sorted(spikes,key=lambda x:x.get("spike_pct",0),reverse=True)[:5]]
        console.print(Panel("\n".join(lines),title=f"[bold yellow]⚡  {len(spikes)} SPIKES[/bold yellow]",border_style="yellow",padding=(0,1)))
        console.print()
    fresh=[r for r in rows if r.get("fresh_48h")]
    if fresh:
        lines=[f"  [cyan]{r['channel'][:22]}[/cyan]  [white]{r['title'][:40]}[/white]  [dim]{fmt(r['views'])} views · {age_str(r.get('published'))}[/dim]"
               for r in sorted(fresh,key=lambda x:x["views"],reverse=True)[:5]]
        console.print(Panel("\n".join(lines),title=f"[bold cyan]🆕  {len(fresh)} FRESH — <48h (vpd inflated)[/bold cyan]",border_style="cyan",padding=(0,1)))
        console.print()
    console.print(f"  [dim]{len(rows)} videos · ⚡=spike · 🆕=<48h · 📝=noted[/dim]\n")
    tables=[make_table(title,emoji,sort_fn,cols,rows,notes) for title,emoji,sort_fn,cols in RANKINGS]
    hype_sorted=sorted(rows,key=lambda r:r["score"],reverse=True)
    i=0
    while i<len(tables):
        if i+1<len(tables): console.print(Columns([tables[i],tables[i+1]],padding=(0,3)))
        else: console.print(tables[i])
        console.print(); i+=2
    console.print("  [dim]# = open · N# = note · R# = log remake · Enter = skip[/dim]")
    pick=Prompt.ask("  Pick", default="").strip().lower()
    if not pick: return
    if pick.startswith("n") and pick[1:].isdigit():
        idx=int(pick[1:])-1
        if 0<=idx<len(hype_sorted): add_note(hype_sorted[idx]["id"],hype_sorted[idx]["title"])
    elif pick.startswith("r") and pick[1:].isdigit():
        idx=int(pick[1:])-1
        if 0<=idx<len(hype_sorted): log_remake(hype_sorted[idx])
    elif pick.isdigit():
        idx=int(pick)-1
        if 0<=idx<len(hype_sorted):
            url=f"https://youtube.com/shorts/{hype_sorted[idx]['id']}"
            console.print(f"  [green]Opening:[/green] {url}"); webbrowser.open(url)

# ══════════════════════════════════════════════════════════════
#  CHANNEL SUMMARY
# ══════════════════════════════════════════════════════════════

def show_channel_summary(rows):
    section("CHANNEL SUMMARY")
    ch={}
    for r in rows:
        s=ch.setdefault(r["channel"],{"views":0,"growth":0,"likes":0,"count":0,"ratios":[],"is_mine":r.get("is_mine",False),"subs":r.get("subs",0)})
        s["views"]+=r["views"]; s["growth"]+=r["growth"]; s["likes"]+=r["likes"]; s["count"]+=1; s["ratios"].append(r["like_ratio"])
    t=Table(box=box.SIMPLE_HEAVY,border_style="bright_black",header_style="bold white")
    t.add_column("Channel",style="cyan",width=26); t.add_column("Subs",style="dim",width=8,justify="right")
    t.add_column("Shorts",style="dim",width=7,justify="right"); t.add_column("Total Views",style="bright_white",width=13,justify="right")
    t.add_column("Growth",width=10,justify="right"); t.add_column("Avg/Video",style="white",width=10,justify="right"); t.add_column("Avg Like%",style="bright_blue",width=10,justify="right")
    for name,s in sorted(ch.items(),key=lambda x:x[1]["views"],reverse=True):
        avg=s["views"]//max(s["count"],1); avg_lr=sum(s["ratios"])/len(s["ratios"]) if s["ratios"] else 0
        g=s["growth"]; g_str=f"[green]+{fmt(g)}[/green]" if g>0 else f"[dim]{fmt(g)}[/dim]"
        label=f"[bold yellow]{name[:23]} ★[/bold yellow]" if s["is_mine"] else name[:26]
        t.add_row(label,fmt(s["subs"]) if s["subs"] else "[dim]?[/dim]",str(s["count"]),fmt(s["views"]),g_str,fmt(avg),f"{avg_lr:.1f}%")
    console.print(t)
    if Confirm.ask("\n  Show posting time breakdown?", default=True): posting_time_analysis(rows)

# ══════════════════════════════════════════════════════════════
#  EXPORT CSV
# ══════════════════════════════════════════════════════════════

