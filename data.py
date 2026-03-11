import json, os, csv
from datetime import datetime, timezone

from rich.prompt import Prompt, Confirm

from utils import (
    console, section, fmt, days_ago, views_per_day, like_ratio,
    velocity_label, velocity_change,
    load_cache, load_notes, save_notes, load_remakes, save_remakes,
    PRESETS_FILE, SPIKE_MIN_GROWTH, SPIKE_MIN_PCT,
)
def load_presets(): return json.load(open(PRESETS_FILE)) if os.path.exists(PRESETS_FILE) else {}

def save_preset(name, min_views, max_days):
    p = load_presets(); p[name]={"min_views":min_views,"max_days":max_days}
    json.dump(p, open(PRESETS_FILE,"w"), indent=2); console.print(f"  [green]Saved '{name}'[/green]")

def ask_filters():
    presets = load_presets(); section("FILTERS")
    if presets:
        for i,(name,p) in enumerate(presets.items(),1):
            console.print(f"  [cyan]{i}[/cyan]  {name}  [dim]≥{fmt(p['min_views']) if p['min_views'] else 'any'} · {str(p['max_days'])+'d' if p['max_days'] else 'any'}[/dim]")
        console.print()
        pick = Prompt.ask("  Use preset # or Enter for new", default="").strip()
        if pick.isdigit():
            items = list(presets.items()); idx=int(pick)-1
            if 0<=idx<len(items): _,p=items[idx]; return p["min_views"],p["max_days"]
    raw = Prompt.ask("  Min views (e.g. 700k, Enter skip)", default="").strip().lower()
    min_views = 0
    if raw:
        try:
            if raw.endswith("m"): min_views=int(float(raw[:-1])*1_000_000)
            elif raw.endswith("k"): min_views=int(float(raw[:-1])*1_000)
            else: min_views=int(raw.replace(",",""))
        except: pass
    raw2=Prompt.ask("  Max age days (Enter skip)", default="").strip()
    max_days=None
    if raw2:
        try: max_days=int(raw2)
        except: pass
    if (min_views or max_days) and Confirm.ask("\n  Save as preset?", default=False):
        save_preset(Prompt.ask("  Name", default="my filter"), min_views, max_days)
    return min_views, max_days

def apply_filters(rows, min_views, max_days):
    out = rows
    if min_views:            out=[r for r in out if r["views"]>=min_views]
    if max_days is not None: out=[r for r in out if (days_ago(r.get("published")) or 9999)<=max_days]
    return out

# ══════════════════════════════════════════════════════════════
#  BUILD ROWS
# ══════════════════════════════════════════════════════════════

def build_rows(data, cache=None):
    import math
    if cache is None: cache = load_cache()
    ch_views = {}
    for v in data.values(): ch_views.setdefault(v["channel"],[]).append(v["views"])
    ch_avg = {ch: max(sum(vs)/len(vs),1000) for ch,vs in ch_views.items()}
    subs_map = cache.get("subs", {})
    rows = []
    for v in data.values():
        avg      = ch_avg[v["channel"]]
        raw_score= v["views"] / avg
        subs     = subs_map.get(v.get("channelId",""), 0)
        adj_score= raw_score / (math.log10(max(subs,1000)/1000)+1) if subs>0 else raw_score
        prev_views = v.get("prev_views", 0)
        spike_growth = v.get("spike_growth", v.get("growth", 0))
        is_spike = bool(
            spike_growth >= SPIKE_MIN_GROWTH and
            prev_views > 0 and
            spike_growth / prev_views >= SPIKE_MIN_PCT
        ) if prev_views else False
        rows.append({
            **v,
            "score":      raw_score,
            "adj_score":  round(adj_score,2),
            "subs":       subs,
            "ch_avg":     avg,
            "vpd":        views_per_day(v["views"], v.get("published")),
            "like_ratio": like_ratio(v.get("likes",0), v.get("views",1)),
            "is_spike":   is_spike,
            "spike_growth": spike_growth if is_spike else 0,
            "spike_pct":  round(spike_growth / prev_views * 100) if is_spike and prev_views else 0,
            "velocity":   velocity_label(v.get("view_history",[])),
            "vel_change": velocity_change(v.get("view_history",[])),
        })
    return rows

# ══════════════════════════════════════════════════════════════
#  NOTES
# ══════════════════════════════════════════════════════════════

def add_note(video_id, title):
    notes=load_notes(); existing=notes.get(video_id,{}).get("note","")
    if existing: console.print(f"  [dim]Existing: {existing}[/dim]")
    note=Prompt.ask("  Note", default=existing)
    notes[video_id]={"note":note,"title":title,"updated_at":datetime.now(timezone.utc).isoformat()}
    save_notes(notes); console.print("  [green]Saved.[/green]")

def show_notes():
    notes=load_notes()
    if not notes: console.print("  [dim]No notes yet. From Dashboard: type N# to add a note.[/dim]\n"); return
    section("NOTES")
    for vid,n in sorted(notes.items(), key=lambda x: x[1].get("updated_at",""), reverse=True):
        console.print(f"  [cyan]{n.get('title','?')[:40]}[/cyan]")
        console.print(f"  [white]{n['note']}[/white]  [dim]{n.get('updated_at','')[:10]}[/dim]")
        console.print(f"  [dim]https://youtube.com/shorts/{vid}[/dim]\n")

# ══════════════════════════════════════════════════════════════
#  REMAKE HISTORY
# ══════════════════════════════════════════════════════════════

def _parse_views(raw):
    raw=raw.strip().lower()
    try:
        if raw.endswith("m"): return int(float(raw[:-1])*1_000_000)
        if raw.endswith("k"): return int(float(raw[:-1])*1_000)
        return int(raw)
    except: return 0

def log_remake(source_row):
    remakes=load_remakes(); rid=source_row["id"]
    console.print(f"\n  Logging remake of: [cyan]{source_row['title']}[/cyan]")
    your_url   = Prompt.ask("  Your video URL (Enter skip)", default="").strip()
    your_views = _parse_views(Prompt.ask("  Your views so far (Enter skip)", default=""))
    remakes[rid]={
        "source_id":rid,"source_channel":source_row["channel"],"source_title":source_row["title"],
        "source_views":source_row["views"],"source_score":round(source_row["score"],2),
        "your_url":your_url,"your_views":your_views,
        "logged_at":datetime.now(timezone.utc).isoformat(),"result":"pending",
    }
    save_remakes(remakes); console.print("  [green]Logged![/green]")

def show_remake_history():
    remakes=load_remakes()
    if not remakes: console.print("  [dim]No remakes logged yet.[/dim]\n"); return
    section("REMAKE HISTORY")
    success=[r for r in remakes.values() if r.get("result")=="success"]
    flop   =[r for r in remakes.values() if r.get("result")=="flop"]
    pending=[r for r in remakes.values() if r.get("result")=="pending"]
    console.print(f"  [green]{len(success)} success[/green]  [red]{len(flop)} flop[/red]  [dim]{len(pending)} pending[/dim]\n")
    for r in sorted(remakes.values(), key=lambda x: x.get("logged_at",""), reverse=True):
        rc={"success":"green","flop":"red","partial":"yellow"}.get(r.get("result"),"dim")
        ratio=""
        if r.get("your_views") and r.get("source_views"):
            ratio=f"  [dim]you got {int(r['your_views']/r['source_views']*100)}% of source[/dim]"
        console.print(f"  [{rc}]{r.get('result','?').upper():<8}[/{rc}]  [cyan]{r['source_channel'][:18]}[/cyan]  [white]{r['source_title'][:35]}[/white]{ratio}")
        if r.get("your_url"): console.print(f"           [dim]{r['your_url']}[/dim]")
    console.print()
    items=list(remakes.items()); pick=Prompt.ask("  Update result for # (Enter skip)", default="")
    if pick.isdigit():
        idx=int(pick)-1
        if 0<=idx<len(items):
            rid,r=items[idx]
            vr=Prompt.ask("  Update your views", default=str(r.get("your_views",""))).strip()
            r["your_views"]=_parse_views(vr) if vr else r.get("your_views",0)
            r["result"]=Prompt.ask("  Result",choices=["pending","success","flop","partial"],default=r.get("result","pending"))
            r["updated_at"]=datetime.now(timezone.utc).isoformat()
            save_remakes(remakes); console.print("  [green]Updated.[/green]")

# ══════════════════════════════════════════════════════════════
#  ★ NEW FEATURE 1: TREND RADAR
#  Detects topics blowing up across multiple channels at once
# ══════════════════════════════════════════════════════════════


def export_csv(rows):
    section("EXPORT"); min_views,max_days=ask_filters(); rows=apply_filters(rows,min_views,max_days)
    if not rows: console.print("  [yellow]No videos matched.[/yellow]"); return
    filename=f"shorts_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    with open(filename,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["channel","subs","title","views","likes","comments","like_ratio",
            "views_per_day","hype_score","adj_score","growth","published","age_days","fresh_48h","url",
            "thumb_brightness","thumb_saturation","thumb_face_pct","thumb_has_text","thumb_color"])
        w.writeheader()
        for r in sorted(rows,key=lambda x:x["score"],reverse=True):
            th=r.get("thumbnail") or {}
            w.writerow({"channel":r["channel"],"subs":r.get("subs",0),"title":r["title"],"views":r["views"],
                "likes":r.get("likes",0),"comments":r.get("comments",0),"like_ratio":f"{r['like_ratio']:.2f}%",
                "views_per_day":r["vpd"],"hype_score":f"{r['score']:.2f}x","adj_score":f"{r['adj_score']:.2f}x",
                "growth":r["growth"],"published":r.get("published",""),"age_days":days_ago(r.get("published")) or "",
                "fresh_48h":"yes" if r.get("fresh_48h") else "no","url":f"https://youtube.com/shorts/{r['id']}",
                "thumb_brightness":th.get("brightness",""),"thumb_saturation":th.get("saturation",""),
                "thumb_face_pct":th.get("face_pct",""),"thumb_has_text":"yes" if th.get("high_contrast_pct",0)>20 else "no",
                "thumb_color":th.get("dominant_color","")})
    console.print(f"  ✅  [green]Exported [bold]{len(rows)}[/bold] → [bold]{filename}[/bold][/green]")