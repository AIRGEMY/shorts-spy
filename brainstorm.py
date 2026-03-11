import json, os
from datetime import datetime, timezone
from rich.prompt import Prompt, Confirm
from rich.panel import Panel

from utils import (
    console, section, fmt, age_str, days_ago,
    load_cache, save_cache, db_file,
)
from scan import analyze_thumbnail, fetch_subscriber_counts, thumb_summary
from data import log_remake

def detect_format(title):
    t=title.lower()
    if any(x in t for x in ("pov","when you","me when","me trying")): return "pov"
    if any(x in t for x in ("how to","tutorial","guide","step by step")): return "tutorial"
    if any(x in t for x in ("tier list","ranking","ranked","best ","worst ","top ")): return "ranking"
    if any(x in t for x in (" vs "," vs.","versus")): return "comparison"
    if any(x in t for x in ("secret","hidden","you didn't know","nobody knows")): return "reveal"
    if any(x in t for x in ("challenge","i tried","attempting")): return "challenge"
    if any(x in t for x in ("react","reacting","watching")): return "reaction"
    if any(x in t for x in ("story","storytime","this happened")): return "story"
    return "other"

def angle(r, all_rows):
    ft=detect_format(r["title"]); has_face=(r.get("thumbnail") or {}).get("face_pct",0)>8
    if ft=="pov": return "POV format proven — swap in the most relatable current situation"
    if ft=="tutorial": return f"Tutorial format. {'Put payoff in first 2s' if not has_face else 'Keep face visible throughout'}. Apply to most-asked question in your niche"
    if ft=="ranking": return "Ranking format travels — pick the most contested topic. Controversial placements drive comments"
    if ft=="comparison": return "Head-to-head format. Use the most debated matchup — the debate IS the content"
    if ft=="reveal": return "Mystery/reveal hook. Tease in first frame, pay off at 80% mark"
    if ft=="challenge": return "Challenge format. Film multiple attempts — failure clips spike watch time"
    if ft=="reaction": return "Your face reaction IS the content. Find the most share-worthy clip in your niche"
    if r["like_ratio"]>=6: return "High like ratio = execution is the hook. Clone the format precisely"
    if r["vpd"]>=50_000 and r["score"]>=5: return "Trending RIGHT NOW — drop your version within 48h. Speed > originality"
    if r["comments"]>=1000: return "High comments = divisive topic. Make a 'my take' angle to ride the debate"
    if has_face: return "Face-forward thumbnail is working here. Stay on-camera, high energy in first 2s"
    return "Replicate the pacing and cut rhythm — format does more work than the topic"

def trend_freshness(r, all_rows):
    kws=set(w.lower() for w in r["title"].split() if len(w)>3)
    if not kws: return 0,[]
    similar=[]
    for other in all_rows:
        if other["id"]==r["id"]: continue
        ok=set(w.lower() for w in other["title"].split() if len(w)>3)
        if len(kws&ok)/max(len(kws),1)>=0.4: similar.append(other["channel"])
    return len(set(similar)),list(set(similar))[:4]

def success_pct(r):
    return min(int(min(r["score"]/10,1)*60 + min(r["like_ratio"]/10,1)*30 + max(0,10-(days_ago(r.get("published")) or 10))),97)

def repro_score(r):
    if r["score"]>=5 and r["like_ratio"]>=5: return 9
    if r["score"]>=3 and (days_ago(r.get("published")) or 99)<=7: return 8
    if r["score"]>=2: return 7
    if r["like_ratio"]>=4: return 6
    return 5

def do_backtest(all_rows):
    if not os.path.exists(db_file()): return
    db=json.load(open(db_file())); now=datetime.now(timezone.utc)
    candidates=[v for v in db.values() if v.get("predicted_at") and
                (now-datetime.fromisoformat(v["predicted_at"].replace("Z","+00:00"))).days>=21]
    if not candidates: console.print("  [dim]No predictions old enough (21+ days) yet.[/dim]\n"); return
    section("BACKTEST"); console.print(f"  [dim]{len(candidates)} predictions to evaluate[/dim]\n")
    rbi={r["id"]:r for r in all_rows}; correct=wrong=0
    for v in sorted(candidates,key=lambda x:x.get("predicted_success",0),reverse=True):
        r=rbi.get(v["id"])
        if not r: continue
        pred=v["predicted_success"]; match=(pred>=60)==(r["score"]>=1.5)
        if match: correct+=1
        else: wrong+=1
        console.print(f"  {'[green]✓[/green]' if match else '[red]✗[/red]'}  [dim]pred {pred}%[/dim]  [cyan]{v['channel'][:18]}[/cyan]  [white]{v['title'][:32]}[/white]  [dim]actual {r['score']:.1f}×[/dim]")
    total=correct+wrong
    if total:
        acc=int(correct/total*100); color="green" if acc>=65 else "yellow" if acc>=50 else "red"
        console.print(f"\n  Accuracy: [{color}]{acc}%[/{color}]  ({correct}/{total})  [dim](baseline 50%)[/dim]\n")

def ai_brainstorm(all_rows):
    section("BRAINSTORM  —  Top 10 Videos to Remake")
    def norm(val,mn,mx): return 0.5 if mx==mn else max(0.0,min(1.0,(val-mn)/(mx-mn)))
    vpds=[r["vpd"] for r in all_rows]; lrs=[r["like_ratio"] for r in all_rows]
    coms=[r["comments"] for r in all_rows]; scs=[r["score"] for r in all_rows]
    def composite(r):
        age=days_ago(r.get("published")) or 30; rec=norm(1/max(age,1),1/30,1)
        return(norm(r["score"],min(scs),max(scs))*0.35+norm(r["vpd"],min(vpds),max(vpds))*0.25+
               norm(r["like_ratio"],min(lrs),max(lrs))*0.20+norm(r["comments"],min(coms),max(coms))*0.10+rec*0.10)
    ranked=sorted(all_rows,key=composite,reverse=True)[:10]
    db=json.load(open(db_file())); changed=False
    for r in ranked:
        if not r.get("thumbnail"):
            thumb=analyze_thumbnail(r["id"]); r["thumbnail"]=thumb
            if r["id"] in db: db[r["id"]]["thumbnail"]=thumb; changed=True
    cache=load_cache(); channel_ids=[r.get("channelId","") for r in ranked if r.get("channelId")]
    if channel_ids: fetch_subscriber_counts(channel_ids,cache); save_cache(cache)
    now_iso=datetime.now(timezone.utc).isoformat()
    for r in ranked:
        if r["id"] in db and not db[r["id"]].get("predicted_success"):
            db[r["id"]]["predicted_success"]=success_pct(r); db[r["id"]]["predicted_at"]=now_iso; changed=True
    if changed: json.dump(db,open(db_file(),"w"),indent=2)
    console.print(f"  [dim]Scored {len(all_rows)} videos → top 10...[/dim]\n")
    for i,r in enumerate(ranked,1):
        sp=success_pct(r); rs=repro_score(r); sat_n,_=trend_freshness(r,all_rows)
        sp_style="bold green" if sp>=75 else "yellow" if sp>=55 else "red"
        sat_str=f"[red]saturated ({sat_n} channels)[/red]" if sat_n>=5 else f"[yellow]partial ({sat_n} channels)[/yellow]" if sat_n>=2 else f"[green]fresh (only {sat_n} others)[/green]"
        lines=[
            f"  [bold white]{i:>2}.[/bold white]  [cyan]{r['channel']}[/cyan]  [white]{r['title']}[/white]  [dim]{detect_format(r['title'])}[/dim]",
            f"      [dim]👀 {fmt(r['views'])}  ·  {r['score']:.1f}x  ·  {fmt(r['vpd'])}/d  ·  {r['like_ratio']:.1f}%  ·  {age_str(r.get('published'))}[/dim]",
            f"      🌊 {sat_str}",
            f"      💡 [italic]{angle(r,all_rows)}[/italic]",
        ]
        if r.get("thumbnail"): lines.append(f"      📸 {thumb_summary(r['thumbnail'])}")
        if r.get("is_spike"): lines.append(f"      ⚡ [red]SPIKING +{r.get('spike_pct','?')}%[/red]")
        if r.get("vel_change",0)>0.1: lines.append(f"      {r['velocity']}")
        lines.append(f"      [bold]Success:[/bold] [{sp_style}]{sp}%[/{sp_style}]   [bold]Repro:[/bold] [cyan]{'█'*rs+'░'*(10-rs)}[/cyan] [dim]{rs}/10[/dim]")
        console.print(Panel("\n".join(lines),border_style="bright_black",padding=(0,1))); console.print()
    db_r=json.load(open(db_file())); now=datetime.now(timezone.utc)
    has_old=any(v.get("predicted_at") and (now-datetime.fromisoformat(v["predicted_at"].replace("Z","+00:00"))).days>=21 for v in db_r.values())
    if has_old and Confirm.ask("  Old predictions found — run backtest?", default=True): do_backtest(all_rows)
    console.print("  [dim]Enter # to log as a remake (Enter skip)[/dim]")
    pick=Prompt.ask("  Log #", default="").strip()
    if pick.isdigit():
        idx=int(pick)-1
        if 0<=idx<len(ranked): log_remake(ranked[idx])
    if Confirm.ask("  Save to file?", default=True):
        fname=f"brainstorm_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        with open(fname,"w",encoding="utf-8") as f:
            for i,r in enumerate(ranked,1):
                sat_n,_=trend_freshness(r,all_rows)
                f.write(f"#{i} {r['channel']} — {r['title']}\n   Format: {detect_format(r['title'])}\n   Views: {fmt(r['views'])}  Hype: {r['score']:.1f}x  VPD: {fmt(r['vpd'])}  Like%: {r['like_ratio']:.1f}%\n   Freshness: {sat_n} channels covered similar content\n   Angle: {angle(r,all_rows)}\n   Success: {success_pct(r)}%  Repro: {repro_score(r)}/10\n\n")
        console.print(f"  [green]Saved → {fname}[/green]")

# ══════════════════════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════════════════════

