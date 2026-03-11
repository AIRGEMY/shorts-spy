import re, statistics
from collections import defaultdict, Counter
from rich.prompt import Prompt
from rich.table import Table
from rich.columns import Columns
from rich import box

from utils import console, section, fmt, days_ago, DAYS, THUMB_OK
import state

def title_pattern_cluster(rows):
    section("TITLE PATTERN ANALYSIS")
    def extract_pattern(title):
        t=title.lower(); t=re.sub(r'\d+','NUM',t)
        if t.startswith("how to"): return "How to [X]"
        if t.startswith("when "): return "When [X]"
        if t.startswith("pov"): return "POV: [X]"
        if " vs " in t or " vs. " in t: return "[X] vs [X]"
        if t.startswith("i tried"): return "I tried [X]"
        if t.startswith("i "): return "I [verb] [X]"
        if "tier" in t: return "Tier list: [X]"
        if "best " in t or "worst " in t: return "Best/Worst [X]"
        if "top " in t and "NUM" in t: return "Top NUM [X]"
        if "you didn't know" in t or "nobody knows" in t: return "Secrets: [X]"
        if "secret" in t or "hidden" in t: return "Hidden [X]"
        if "what if" in t: return "What if [X]"
        if t.endswith("?"): return "Question title"
        if "react" in t or "reacting" in t: return "Reaction: [X]"
        if "challenge" in t: return "Challenge: [X]"
        if "#" in title: return "Hashtag-led"
        return "Other"
    pd=defaultdict(list)
    for r in rows: pd[extract_pattern(r["title"])].append(r["views"])
    console.print(f"  [dim]Analysed {len(rows)} videos across {len(pd)} patterns[/dim]\n")
    t=Table(box=box.SIMPLE_HEAVY,border_style="bright_black",header_style="bold white")
    t.add_column("Pattern",  style="cyan",        width=22)
    t.add_column("Count",    style="dim",         width=7,  justify="right")
    t.add_column("Avg Views",style="bright_white",width=11, justify="right")
    t.add_column("Best",     style="green",       width=11, justify="right")
    t.add_column("Median",   style="white",       width=11, justify="right")
    t.add_column("Bar",      style="dim",         width=24)
    rs=sorted(pd.items(),key=lambda x:statistics.mean(x[1]),reverse=True)
    mx=statistics.mean(rs[0][1]) if rs else 1
    for pattern,vs in rs:
        avg=int(statistics.mean(vs)); bar="█"*int(avg/mx*20)
        t.add_row(pattern,str(len(vs)),fmt(avg),fmt(max(vs)),fmt(int(statistics.median(vs))),bar)
    console.print(t)

def hashtag_analysis(rows):
    section("HASHTAG ANALYSIS")
    tv=defaultdict(list); tc=Counter()
    for r in rows:
        for tag in r.get("tags",[]):
            tl=tag.lower().strip()
            if not tl or tl in ("shorts","short","youtube","viral","trending"): continue
            tv[tl].append(r["views"]); tc[tl]+=1
    if not tv: console.print("  [dim]No tag data — scan recently to get tags.[/dim]\n"); return
    console.print(f"  [dim]{sum(tc.values())} tag instances · {len(tc)} unique tags[/dim]\n")
    t1=Table(title="🏆 Best Avg Views by Tag",box=box.SIMPLE_HEAVY,border_style="bright_black",header_style="bold white",title_style="bold yellow",min_width=35)
    t1.add_column("Tag",style="cyan",width=20); t1.add_column("Avg",style="bright_white",width=10,justify="right"); t1.add_column("Uses",style="dim",width=6,justify="right")
    for tag,vs in sorted(tv.items(),key=lambda x:statistics.mean(x[1]),reverse=True)[:20]:
        t1.add_row(tag,fmt(int(statistics.mean(vs))),str(len(vs)))
    t2=Table(title="📊 Most Used Tags",box=box.SIMPLE_HEAVY,border_style="bright_black",header_style="bold white",title_style="bold yellow",min_width=35)
    t2.add_column("Tag",style="cyan",width=20); t2.add_column("Uses",style="bright_white",width=6,justify="right"); t2.add_column("Avg Views",style="white",width=11,justify="right")
    for tag,count in tc.most_common(20): t2.add_row(tag,str(count),fmt(int(statistics.mean(tv[tag]))))
    console.print(Columns([t1,t2],padding=(0,3)))

def title_length_analysis(rows):
    section("TITLE LENGTH vs VIEWS")
    buckets=defaultdict(list)
    for r in rows:
        wc=len(r["title"].split()); b=f"{(wc//5)*5+1}-{(wc//5)*5+5} words"; buckets[b].append(r["views"])
    t=Table(box=box.SIMPLE_HEAVY,border_style="bright_black",header_style="bold white")
    t.add_column("Title Length",style="cyan",width=16); t.add_column("Videos",style="dim",width=8,justify="right")
    t.add_column("Avg Views",style="bright_white",width=11,justify="right"); t.add_column("Best",style="green",width=11,justify="right"); t.add_column("Bar",style="dim",width=25)
    rs=sorted(buckets.items(),key=lambda x:statistics.mean(x[1]),reverse=True); mx=statistics.mean(rs[0][1]) if rs else 1
    for bucket,vs in rs:
        avg=int(statistics.mean(vs)); t.add_row(bucket,str(len(vs)),fmt(avg),fmt(max(vs)),"█"*int(avg/mx*22))
    console.print(t)

def thumbnail_color_analysis(rows):
    section("THUMBNAIL COLOR vs PERFORMANCE")
    wt=[r for r in rows if r.get("thumbnail")]
    if not wt: console.print("  [dim]No thumbnail data — run Brainstorm first to fetch thumbs.[/dim]\n"); return
    bri_b={"dark (<80)":[],"mid (80-160)":[],"bright (>160)":[]}
    face_b={"face present":[],"no face":[]}
    text_b={"text overlay":[],"no text":[]}
    for r in wt:
        th=r["thumbnail"]; bri=th["brightness"]
        if bri<80: bri_b["dark (<80)"].append(r["views"])
        elif bri<160: bri_b["mid (80-160)"].append(r["views"])
        else: bri_b["bright (>160)"].append(r["views"])
        face_b["face present" if th["face_pct"]>8 else "no face"].append(r["views"])
        text_b["text overlay" if th["high_contrast_pct"]>20 else "no text"].append(r["views"])
    def print_b(title, data):
        console.print(f"  [bold]{title}[/bold]")
        avgs=[statistics.mean(vs) for vs in data.values() if vs]; mx=max(avgs) if avgs else 1
        for label,vs in data.items():
            if not vs: continue
            avg=int(statistics.mean(vs)); bar="█"*int(avg/mx*25)
            console.print(f"  [cyan]{label:<20}[/cyan]  [dim]{bar:<25}[/dim]  [white]{fmt(avg)}[/white]  [dim]({len(vs)})[/dim]")
        console.print()
    print_b("Brightness",bri_b); print_b("Face in thumbnail",face_b); print_b("Text overlay",text_b)

def competitor_gap_finder(rows):
    section("COMPETITOR GAP FINDER")
    your_rows =[r for r in rows if r.get("is_mine")]
    their_rows=[r for r in rows if not r.get("is_mine")]
    if not your_rows: console.print("  [dim]No videos from YOUR_CHANNEL found.[/dim]\n"); return
    stop={"the","a","an","and","or","but","in","on","at","to","for","of","is","it","this","that","be","are","was","were","i","my","you","your","with","how","what","when","they","their","have","has","all","not","do","did","just","so","up","out","we","he","she","vs","s"}
    def kws(title): return set(w.lower().strip(".,!?\"'#") for w in title.split() if w.lower() not in stop and len(w)>2)
    your_kws=set()
    for r in your_rows: your_kws.update(kws(r["title"]))
    gap_rows=[]
    for r in their_rows:
        k=kws(r["title"]); overlap=k&your_kws; gap_pct=1-(len(overlap)/max(len(k),1))
        if gap_pct>=0.6: gap_rows.append({**r,"gap_pct":round(gap_pct*100),"new_kws":k-your_kws})
    if not gap_rows: console.print("  [dim]No clear gaps — your content already covers most topics.[/dim]\n"); return
    top=sorted(gap_rows,key=lambda x:x["views"],reverse=True)[:20]
    console.print(f"  [dim]{len(gap_rows)} videos with topics you haven't covered · top 20[/dim]\n")
    t=Table(box=box.SIMPLE_HEAVY,border_style="bright_black",header_style="bold white")
    t.add_column("Channel",style="cyan",width=18); t.add_column("Title",style="white",width=32)
    t.add_column("Views",style="bright_white",width=10,justify="right"); t.add_column("Gap%",style="yellow",width=6,justify="right"); t.add_column("New words",style="dim",width=25)
    for r in top: t.add_row(r["channel"][:18],r["title"][:32],fmt(r["views"]),f"{r['gap_pct']}%",", ".join(list(r["new_kws"])[:5]))
    console.print(t)

def posting_time_analysis(rows):
    section("POSTING TIME ANALYSIS")
    by_day=defaultdict(list); by_hour=defaultdict(list); heatmap=defaultdict(list)
    for r in rows:
        if not r.get("published"): continue
        dt=datetime.fromisoformat(r["published"].replace("Z","+00:00")); d,h=dt.weekday(),dt.hour
        by_day[d].append(r["views"]); by_hour[h].append(r["views"]); heatmap[(d,h)].append(r["views"])
    day_avgs={d:int(statistics.mean(vs)) for d,vs in by_day.items()}; mx_d=max(day_avgs.values(),default=1)
    console.print("  [bold]Best day to post[/bold]\n")
    for d in range(7):
        avg=day_avgs.get(d,0); bar="█"*int(avg/mx_d*30)
        console.print(f"  [cyan]{DAYS[d]}[/cyan]  [dim]{bar:<30}[/dim]  [white]{fmt(avg):>7}[/white]  [dim]({len(by_day.get(d,[]))})[/dim]")
    hour_avgs={h:int(statistics.mean(vs)) for h,vs in by_hour.items()}; mx_h=max(hour_avgs.values(),default=1)
    console.print("\n  [bold]Best hour to post (UTC)[/bold]\n")
    for h in range(24):
        avg=hour_avgs.get(h,0); bar="█"*int(avg/mx_h*30)
        console.print(f"  [cyan]{h:02d}:00[/cyan]  [dim]{bar:<30}[/dim]  [white]{fmt(avg):>7}[/white]  [dim]({len(by_hour.get(h,[]))})[/dim]")
    if heatmap:
        top3=sorted(heatmap.items(),key=lambda x:statistics.mean(x[1]),reverse=True)[:3]
        console.print("\n  [bold yellow]🏆 Top 3 slots:[/bold yellow]")
        for (d,h),vs in top3:
            console.print(f"     [white]{DAYS[d]} {h:02d}:00 UTC[/white]  →  [green]{fmt(int(statistics.mean(vs)))}[/green] avg  [dim]({len(vs)} videos)[/dim]")
    console.print()

def show_analysis_menu(rows):
    while True:
        section("ANALYSIS")
        console.print("  [cyan]1[/cyan]  📝  Title pattern clusters")
        console.print("  [cyan]2[/cyan]  #   Hashtag breakdown")
        console.print("  [cyan]3[/cyan]  📏  Title length vs views")
        console.print("  [cyan]4[/cyan]  🎨  Thumbnail color vs performance")
        console.print("  [cyan]5[/cyan]  🕳   Competitor gap finder")
        console.print("  [cyan]6[/cyan]  🕐  Posting time breakdown")
        console.print("  [cyan]q[/cyan]  Back\n")
        ch=Prompt.ask("  Pick", default="q").strip().lower()
        if ch=="1": title_pattern_cluster(rows)
        elif ch=="2": hashtag_analysis(rows)
        elif ch=="3": title_length_analysis(rows)
        elif ch=="4": thumbnail_color_analysis(rows)
        elif ch=="5": competitor_gap_finder(rows)
        elif ch=="6": posting_time_analysis(rows)
        elif ch=="q": break

# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════

