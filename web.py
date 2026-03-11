import json, os, re, html, statistics, webbrowser
from datetime import datetime, timezone
from collections import defaultdict, Counter

from utils import (
    console, section, fmt, age_str, hype_label, days_ago,
    load_notes, load_remakes, load_cache, db_file, hof_file,
    DAYS,
)
from rich.prompt import Prompt, Confirm
from trends import _compute_trend_radar_data
from benchmarking import _compute_benchmarks
from freq import _analyse_freq, load_freq
import state

def _compute_title_patterns(rows):
    def extract_pattern(title):
        t=title.lower(); t=re.sub(r'\d+','NUM',t)
        if t.startswith("how to"): return "How to [X]"
        if t.startswith("when "): return "When [X]"
        if t.startswith("pov"): return "POV: [X]"
        if " vs " in t or " vs. " in t: return "[X] vs [X]"
        if t.startswith("i tried"): return "I tried [X]"
        if t.startswith("i "): return "I [verb] [X]"
        if "tier" in t: return "Tier list"
        if "best " in t or "worst " in t: return "Best/Worst [X]"
        if "top " in t and "NUM" in t: return "Top NUM [X]"
        if "you didn't know" in t or "nobody knows" in t: return "Secrets"
        if "secret" in t or "hidden" in t: return "Hidden [X]"
        if "what if" in t: return "What if [X]"
        if t.endswith("?"): return "Question title"
        if "react" in t or "reacting" in t: return "Reaction"
        if "challenge" in t: return "Challenge"
        if "#" in title: return "Hashtag-led"
        return "Other"
    pd=defaultdict(list)
    for r in rows: pd[extract_pattern(r["title"])].append(r["views"])
    result=[]
    for pattern,vs in sorted(pd.items(),key=lambda x:statistics.mean(x[1]),reverse=True):
        result.append({"pattern":pattern,"count":len(vs),"avg":int(statistics.mean(vs)),"best":max(vs),"median":int(statistics.median(vs))})
    return result

def _compute_title_lengths(rows):
    buckets=defaultdict(list)
    for r in rows:
        wc=len(r["title"].split()); b=f"{(wc//5)*5+1}-{(wc//5)*5+5}w"; buckets[b].append(r["views"])
    result=[]
    for bucket,vs in sorted(buckets.items(),key=lambda x:statistics.mean(x[1]),reverse=True):
        result.append({"bucket":bucket,"count":len(vs),"avg":int(statistics.mean(vs)),"best":max(vs)})
    return result

def _compute_hashtags(rows):
    tv=defaultdict(list); tc=Counter()
    for r in rows:
        for tag in r.get("tags",[]):
            tl=tag.lower().strip()
            if not tl or tl in ("shorts","short","youtube","viral","trending"): continue
            tv[tl].append(r["views"]); tc[tl]+=1
    by_avg=[{"tag":tag,"avg":int(statistics.mean(vs)),"count":len(vs)} for tag,vs in sorted(tv.items(),key=lambda x:statistics.mean(x[1]),reverse=True)[:40]]
    by_use=[{"tag":tag,"count":cnt,"avg":int(statistics.mean(tv[tag]))} for tag,cnt in tc.most_common(40)]
    return {"by_avg":by_avg,"by_use":by_use}

def _compute_posting_time(rows):
    by_day=defaultdict(list); by_hour=defaultdict(list); heatmap=defaultdict(list)
    for r in rows:
        if not r.get("published"): continue
        try:
            dt=datetime.fromisoformat(r["published"].replace("Z","+00:00")); d,h=dt.weekday(),dt.hour
            by_day[d].append(r["views"]); by_hour[h].append(r["views"]); heatmap[f"{d}_{h}"].append(r["views"])
        except: pass
    days_out=[{"day":DAYS[d],"avg":int(statistics.mean(vs)),"count":len(vs)} for d,vs in sorted(by_day.items())]
    hours_out=[{"hour":h,"avg":int(statistics.mean(vs)),"count":len(vs)} for h,vs in sorted(by_hour.items())]
    heat_out=[{"key":k,"d":int(k.split("_")[0]),"h":int(k.split("_")[1]),"avg":int(statistics.mean(vs)),"count":len(vs)} for k,vs in heatmap.items()]
    return {"days":days_out,"hours":hours_out,"heatmap":heat_out}

def _compute_channel_summary(rows):
    ch={}
    for r in rows:
        s=ch.setdefault(r["channel"],{"views":0,"growth":0,"likes":0,"count":0,"ratios":[],"is_mine":r.get("is_mine",False),"subs":r.get("subs",0),"scores":[]})
        s["views"]+=r["views"]; s["growth"]+=r["growth"]; s["likes"]+=r["likes"]
        s["count"]+=1; s["ratios"].append(r["like_ratio"]); s["scores"].append(r["score"])
    result=[]
    for name,s in sorted(ch.items(),key=lambda x:x[1]["views"],reverse=True):
        result.append({"channel":name,"views":s["views"],"growth":s["growth"],"count":s["count"],
            "avg":s["views"]//max(s["count"],1),"avg_lr":round(sum(s["ratios"])/len(s["ratios"]),2) if s["ratios"] else 0,
            "avg_score":round(sum(s["scores"])/len(s["scores"]),2) if s["scores"] else 0,
            "best_score":round(max(s["scores"]),2) if s["scores"] else 0,
            "likes":s["likes"],"is_mine":s["is_mine"],"subs":s["subs"]})
    return result

def _compute_brainstorm(rows):
    import math
    def norm(val,mn,mx): return 0.5 if mx==mn else max(0.0,min(1.0,(val-mn)/(mx-mn)))
    vpds=[r["vpd"] for r in rows]; lrs=[r["like_ratio"] for r in rows]
    coms=[r["comments"] for r in rows]; scs=[r["score"] for r in rows]
    def composite(r):
        age=days_ago(r.get("published")) or 30; rec=norm(1/max(age,1),1/30,1)
        return(norm(r["score"],min(scs),max(scs))*0.35+norm(r["vpd"],min(vpds),max(vpds))*0.25+
               norm(r["like_ratio"],min(lrs),max(lrs))*0.20+norm(r["comments"],min(coms),max(coms))*0.10+rec*0.10)
    def success_pct(r):
        return min(int(min(r["score"]/10,1)*60+min(r["like_ratio"]/10,1)*30+max(0,10-(days_ago(r.get("published")) or 10))),97)
    def repro_score(r):
        if r["score"]>=5 and r["like_ratio"]>=5: return 9
        if r["score"]>=3 and (days_ago(r.get("published")) or 99)<=7: return 8
        if r["score"]>=2: return 7
        if r["like_ratio"]>=4: return 6
        return 5
    def detect_fmt(title):
        t=title.lower()
        if any(x in t for x in ("pov","when you","me when")): return "POV"
        if any(x in t for x in ("how to","tutorial")): return "Tutorial"
        if any(x in t for x in ("tier list","ranking","best ","top ")): return "Ranking"
        if " vs " in t: return "Comparison"
        if any(x in t for x in ("secret","hidden","you didn't know")): return "Reveal"
        if any(x in t for x in ("challenge","i tried")): return "Challenge"
        if any(x in t for x in ("react","reacting")): return "Reaction"
        return "Other"
    ranked=sorted(rows,key=composite,reverse=True)[:20]
    result=[]
    for r in ranked:
        kws=set(w.lower() for w in r["title"].split() if len(w)>3)
        similar=sum(1 for o in rows if o["id"]!=r["id"] and
            len(kws&set(w.lower() for w in o["title"].split() if len(w)>3))/max(len(kws),1)>=0.4)
        result.append({"id":r["id"],"channel":r["channel"],"title":r["title"],"views":r["views"],
            "score":round(r["score"],2),"vpd":r["vpd"],"lr":round(r["like_ratio"],2),
            "age":age_str(r.get("published")),"format":detect_fmt(r["title"]),
            "success":success_pct(r),"repro":repro_score(r),"saturation":similar,
            "is_spike":r.get("is_spike",False),"is_mine":r.get("is_mine",False)})
    return result

def _compute_thumbnail_data(rows):
    wt=[r for r in rows if r.get("thumbnail")]
    if not wt: return None
    bri_b={"dark":[],"mid":[],"bright":[]}
    face_b={"face":[],"no_face":[]}
    text_b={"text":[],"no_text":[]}
    for r in wt:
        th=r["thumbnail"]; bri=th["brightness"]
        if bri<80: bri_b["dark"].append(r["views"])
        elif bri<160: bri_b["mid"].append(r["views"])
        else: bri_b["bright"].append(r["views"])
        face_b["face" if th["face_pct"]>8 else "no_face"].append(r["views"])
        text_b["text" if th["high_contrast_pct"]>20 else "no_text"].append(r["views"])
    def bucket_stats(d):
        return {k:{"avg":int(statistics.mean(v)),"count":len(v)} for k,v in d.items() if v}
    return {"brightness":bucket_stats(bri_b),"face":bucket_stats(face_b),"text":bucket_stats(text_b),"total":len(wt)}


def _compute_freq_data():
    """Serialize upload frequency data for the web dashboard."""
    freq    = load_freq()
    results = _analyse_freq(freq)
    out     = []
    for r in results:
        out.append({
            "channel":    r["channel"],
            "status":     r["status"],
            "recent_avg": r["recent_avg"],
            "older_avg":  r["older_avg"],
            "trend_ratio":r["trend_ratio"],
            "weeks_since":r["weeks_since"],
            "week_counts":r["week_counts"],
            "week_labels":r["week_labels"],
        })
    return out


def _compute_benchmark_data(rows):
    """Serialize benchmark data for the web dashboard."""
    bm = _compute_benchmarks(rows)
    if not bm:
        return None

    METRIC_KEYS = ["avg_views","avg_vpd","avg_score","avg_lr","avg_likes","avg_comments","top_video"]
    out_metrics = []
    for key in METRIC_KEYS:
        d = bm[key]
        out_metrics.append({
            "key":       key,
            "label":     d["label"],
            "my_val":    round(d["my_val"], 2),
            "their_val": round(d["their_val"], 2),
            "gap_ratio": d["gap_ratio"],
            "rank":      d["rank"],
            "total":     d["total"],
            "breakdown": [{"channel": x["channel"], "value": round(x["value"],2), "is_mine": x.get("is_mine",False)}
                          for x in d["breakdown"]],
        })
    return {
        "my_name":    bm["_my_name"],
        "my_count":   bm["_my_count"],
        "their_count":bm["_their_count"],
        "metrics":    out_metrics,
        "my_top_kws":   [{"kw":k,"views":v} for k,v in bm["_my_top_kws"]],
        "comp_top_kws": [{"kw":k,"views":v} for k,v in bm["_comp_top_kws"]],
    }


def generate_web_dashboard(rows):
    section("WEB DASHBOARD")
    if not rows: console.print("  [red]No data.[/red]"); return
    notes   = load_notes()
    remakes = load_remakes()

    payload = []
    for r in sorted(rows, key=lambda x: x["score"], reverse=True):
        payload.append({
            "id":        r["id"],
            "channel":   r["channel"],
            "title":     r["title"],
            "views":     r["views"],
            "likes":     r.get("likes", 0),
            "comments":  r.get("comments", 0),
            "score":     round(r["score"], 2),
            "adj_score": round(r["adj_score"], 2),
            "vpd":       r["vpd"],
            "lr":        round(r["like_ratio"], 2),
            "ch_avg":    round(r["ch_avg"]),
            "subs":      r.get("subs", 0),
            "age":       age_str(r.get("published")),
            "published": r.get("published", ""),
            "is_mine":   r.get("is_mine", False),
            "is_spike":  r.get("is_spike", False),
            "fresh":     r.get("fresh_48h", False),
            "has_note":  r["id"] in notes,
            "note":      notes.get(r["id"], {}).get("note", ""),
            "remade":    r["id"] in remakes,
            "growth":    r.get("growth", 0),
            "thumb_face": (r.get("thumbnail") or {}).get("face_pct", 0),
            "thumb_bri":  (r.get("thumbnail") or {}).get("brightness", 0),
        })

    title_patterns  = _compute_title_patterns(rows)
    title_lengths   = _compute_title_lengths(rows)
    hashtag_data    = _compute_hashtags(rows)
    posting_data    = _compute_posting_time(rows)
    channel_data    = _compute_channel_summary(rows)
    brainstorm_data = _compute_brainstorm(rows)
    thumb_data      = _compute_thumbnail_data(rows)
    trend_data      = _compute_trend_radar_data(rows, window_days=7)
    freq_data       = _compute_freq_data()
    bench_data      = _compute_benchmark_data(rows)
    hof_data        = []
    hf = hof_file()
    if os.path.exists(hf):
        hof_raw = json.load(open(hf))
        hof_data = sorted(hof_raw.values(), key=lambda x: x.get("score_at_entry",0), reverse=True)

    data_js         = json.dumps(payload)
    patterns_js     = json.dumps(title_patterns)
    lengths_js      = json.dumps(title_lengths)
    hashtags_js     = json.dumps(hashtag_data)
    posting_js      = json.dumps(posting_data)
    channels_js     = json.dumps(channel_data)
    brainstorm_js   = json.dumps(brainstorm_data)
    thumb_js        = json.dumps(thumb_data)
    trend_js        = json.dumps(trend_data)
    freq_js         = json.dumps(freq_data)
    bench_js        = json.dumps(bench_data)
    hof_js          = json.dumps(hof_data)

    profile_label = html.escape(state._active_profile or "Default")
    scan_time     = datetime.now().strftime("%b %d, %Y · %H:%M")
    total         = len(payload)
    viral_count   = sum(1 for r in payload if r["score"] >= 3)
    spike_count   = sum(1 for r in payload if r["is_spike"])
    fresh_count   = sum(1 for r in payload if r["fresh"])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shorts Spy · {html.escape(profile_label)}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=DM+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#06080e;--s1:#0b0e18;--s2:#10141f;--s3:#151b2a;
  --border:#1c2333;--border2:#2a3448;
  --accent:#00e8b5;--accent2:#ff375f;--accent3:#f5b700;--blue:#4f8ef7;--purple:#9b72ff;
  --text:#dde3f0;--muted:#5a6480;--muted2:#8892aa;
  --mono:'Space Mono',monospace;--sans:'DM Sans',sans-serif;
  --radius:8px;
}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;min-height:100vh}}
::-webkit-scrollbar{{width:5px;height:5px}}
::-webkit-scrollbar-track{{background:var(--s1)}}
::-webkit-scrollbar-thumb{{background:var(--border2);border-radius:3px}}
a{{color:var(--accent);text-decoration:none}}

/* ── LEFT NAV ── */
body{{display:flex;height:100vh;overflow:hidden}}
.leftnav{{
  width:196px;flex-shrink:0;
  background:var(--s1);border-right:1px solid var(--border);
  display:flex;flex-direction:column;
  height:100vh;overflow-y:auto;position:sticky;top:0;z-index:100;
}}
.leftnav::-webkit-scrollbar{{width:3px}}
.logo{{
  font-family:var(--mono);font-size:14px;font-weight:700;letter-spacing:3px;
  background:linear-gradient(90deg,var(--accent),var(--blue));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  padding:20px 16px 14px;white-space:nowrap;flex-shrink:0;
}}
.nav-group-label{{
  font-family:var(--mono);font-size:9px;letter-spacing:2.5px;text-transform:uppercase;
  color:var(--muted);padding:10px 16px 5px;margin-top:4px;
}}
.nav-tab{{
  font-family:var(--sans);font-size:13px;font-weight:500;
  padding:9px 14px 9px 16px;
  display:flex;align-items:center;gap:10px;width:100%;
  color:var(--muted2);border:none;background:transparent;cursor:pointer;
  border-left:3px solid transparent;transition:.12s;white-space:nowrap;
  text-align:left;
}}
.nav-tab:hover{{color:var(--text);background:var(--s2)}}
.nav-tab.active{{
  color:var(--accent);background:rgba(0,232,181,.07);
  border-left-color:var(--accent);
}}
.nav-tab .nav-icon{{font-size:14px;width:18px;text-align:center;flex-shrink:0}}
.nav-divider{{height:1px;background:var(--border);margin:8px 12px}}
.nav-spacer{{flex:1}}
.nav-kpis{{
  border-top:1px solid var(--border);padding:14px 16px 12px;
  display:grid;grid-template-columns:1fr 1fr;gap:10px 8px;
}}
.kpi-mini{{}}
.kpi-v{{font-family:var(--mono);font-size:17px;font-weight:700;color:#fff;line-height:1}}
.kpi-v.g{{color:var(--accent)}}.kpi-v.r{{color:var(--accent2)}}.kpi-v.y{{color:var(--accent3)}}
.kpi-l{{font-size:9px;color:var(--muted);letter-spacing:1.5px;text-transform:uppercase;margin-top:2px}}
.nav-meta{{
  padding:0 16px 16px;font-size:10px;color:var(--muted);
  font-family:var(--mono);line-height:1.6;
}}

/* ── MAIN CONTENT ── */
.main-content{{flex:1;overflow-y:auto;overflow-x:hidden;height:100vh}}

/* ── PAGES ── */
.page{{display:none;min-height:100%}}
.page.active{{display:block}}

/* ── TOOLBAR ── */
.toolbar{{
  background:var(--s1);border-bottom:1px solid var(--border);
  padding:10px 24px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;
  position:sticky;top:0;z-index:50;
}}
.search-wrap{{position:relative;flex:1;min-width:180px;max-width:300px}}
.search-wrap svg{{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--muted);pointer-events:none}}
input[type=text],input[type=number]{{
  background:var(--s2);border:1px solid var(--border);color:var(--text);
  border-radius:var(--radius);padding:8px 12px 8px 34px;font-size:13px;
  width:100%;outline:none;font-family:var(--sans);transition:.12s;
}}
.bare-input{{padding-left:12px}}
input:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,232,181,.08)}}
.pill{{
  font-family:var(--mono);font-size:10px;letter-spacing:.5px;
  padding:6px 11px;border-radius:20px;border:1px solid var(--border);
  color:var(--muted);background:var(--s2);cursor:pointer;transition:.12s;white-space:nowrap;
}}
.pill:hover{{color:var(--muted2);border-color:var(--border2)}}
.pill.active{{background:rgba(0,232,181,.1);border-color:var(--accent);color:var(--accent)}}
.pill.red.active{{background:rgba(255,55,95,.1);border-color:var(--accent2);color:var(--accent2)}}
.pill.blue.active{{background:rgba(79,142,247,.1);border-color:var(--blue);color:var(--blue)}}
.pill.yellow.active{{background:rgba(245,183,0,.1);border-color:var(--accent3);color:var(--accent3)}}
.rcount{{font-family:var(--mono);font-size:11px;color:var(--muted);margin-left:auto;white-space:nowrap}}

/* ── 2-COL LAYOUT (Videos page internal sidebar) ── */
.layout{{display:grid;grid-template-columns:250px 1fr;min-height:calc(100vh - 57px)}}
.sidebar{{background:var(--s1);border-right:1px solid var(--border);padding:16px;overflow-y:auto;position:sticky;top:57px;height:calc(100vh - 57px)}}
.sb-title{{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:3px;text-transform:uppercase;margin:0 4px 10px;}}
.ch-item{{display:flex;align-items:center;justify-content:space-between;padding:7px 9px;border-radius:6px;cursor:pointer;transition:.1s;border:1px solid transparent;margin-bottom:2px}}
.ch-item:hover{{background:var(--s2);border-color:var(--border)}}
.ch-item.sel{{background:rgba(0,232,181,.07);border-color:rgba(0,232,181,.25)}}
.ch-name{{font-size:12px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}}
.ch-name.mine{{color:var(--accent3)}}
.ch-cnt{{font-family:var(--mono);font-size:11px;color:var(--muted);margin-left:6px;flex-shrink:0}}
.ch-bar{{height:2px;border-radius:1px;background:linear-gradient(90deg,var(--accent),var(--blue));margin-top:3px;transition:.2s}}
.hype-row{{display:flex;align-items:center;gap:9px;padding:7px 10px;border-radius:6px;cursor:pointer;border:1px solid var(--border);background:var(--s2);margin-bottom:5px;transition:.1s}}
.hype-row:hover{{background:#131826}}
.hype-row.sel{{border-color:rgba(0,232,181,.35);background:rgba(0,232,181,.05)}}
.hd{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.hlbl{{font-size:12px;font-weight:500;flex:1}}
.hcnt{{font-family:var(--mono);font-size:11px;color:var(--muted)}}

/* ── FEED ── */
.feed{{padding:16px 20px;overflow-y:auto}}
.card{{
  background:var(--s2);border:1px solid var(--border);border-radius:9px;
  padding:13px 15px;margin-bottom:7px;cursor:pointer;transition:.13s;
  border-left:3px solid var(--border);
  display:grid;grid-template-columns:34px 1fr;gap:0 11px;
}}
.card:hover{{background:var(--s3);border-color:var(--border2);transform:translateX(2px)}}
.card.hl{{border-left-color:#ff2244}}.card.hi{{border-left-color:#d44dff}}
.card.hv{{border-left-color:#ff6600}}.card.hh{{border-left-color:#ffcc00}}
.card.hr{{border-left-color:#44ff88}}.card.hn{{border-left-color:var(--border)}}
.c-rank{{font-family:var(--mono);font-size:13px;color:var(--muted);padding-top:1px}}
.c-ch{{font-weight:600;font-size:13px;color:var(--accent);margin-right:6px}}
.c-ch.mine{{color:var(--accent3)}}
.c-top{{display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-bottom:4px}}
.c-title{{font-size:13px;color:var(--text);line-height:1.4;margin-bottom:7px}}
.c-meta{{display:flex;gap:12px;flex-wrap:wrap}}
.m{{font-family:var(--mono);font-size:11px;color:var(--muted2)}}
.m.w{{color:#fff}}.m.g{{color:var(--accent)}}.m.r{{color:var(--accent2)}}.m.y{{color:var(--accent3)}}.m.b{{color:var(--blue)}}
.badge{{font-family:var(--mono);font-size:9px;padding:2px 6px;border-radius:4px;border:1px solid;white-space:nowrap;font-weight:700;letter-spacing:.3px}}
.b-sp{{color:var(--accent2);border-color:rgba(255,55,95,.4);background:rgba(255,55,95,.08)}}
.b-fr{{color:var(--blue);border-color:rgba(79,142,247,.4);background:rgba(79,142,247,.08)}}
.b-me{{color:var(--accent3);border-color:rgba(245,183,0,.4);background:rgba(245,183,0,.08)}}
.b-nt{{color:#b89eff;border-color:rgba(155,114,255,.4);background:rgba(155,114,255,.08)}}
.b-hl{{padding:2px 7px}}
.bhl{{color:#ff2244;border-color:rgba(255,34,68,.4);background:rgba(255,34,68,.08)}}
.bhi{{color:#d44dff;border-color:rgba(212,77,255,.4);background:rgba(212,77,255,.08)}}
.bhv{{color:#ff6600;border-color:rgba(255,102,0,.4);background:rgba(255,102,0,.08)}}
.bhh{{color:#ffcc00;border-color:rgba(255,204,0,.4);background:rgba(255,204,0,.08)}}
.bhr{{color:#44ff88;border-color:rgba(68,255,136,.4);background:rgba(68,255,136,.08)}}
.bhn{{color:var(--muted);border-color:var(--border);background:transparent}}
.note-line{{font-size:12px;color:#b89eff;font-style:italic;margin-top:5px;padding-left:45px}}

/* ── MODAL ── */
.overlay{{position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:300;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(5px)}}
.modal{{background:var(--s1);border:1px solid var(--border2);border-radius:12px;padding:26px;max-width:500px;width:calc(100% - 32px);animation:mi .17s ease}}
@keyframes mi{{from{{opacity:0;transform:scale(.95)}}to{{opacity:1;transform:scale(1)}}}}
.modal-ch{{font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:5px}}
.modal-t{{font-size:17px;font-weight:600;color:#fff;margin-bottom:18px;line-height:1.3}}
.sg{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-bottom:18px}}
.sb{{background:var(--s2);border:1px solid var(--border);border-radius:7px;padding:9px 11px}}
.sk{{font-size:9px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-bottom:3px}}
.sv{{font-family:var(--mono);font-size:15px;font-weight:700;color:#fff}}
.modal-note{{background:rgba(155,114,255,.07);border:1px solid rgba(155,114,255,.2);border-radius:7px;padding:9px 13px;margin-bottom:14px;font-size:13px;color:#c4b5fd;font-style:italic}}
.btn-row{{display:flex;gap:9px}}
.btn{{padding:9px 18px;border-radius:7px;border:none;cursor:pointer;font-size:14px;font-weight:600;font-family:var(--sans);transition:.12s;display:flex;align-items:center;gap:7px}}
.btn-yt{{background:#ff0000;color:#fff}}.btn-yt:hover{{background:#cc0000}}
.btn-cl{{background:var(--s2);color:var(--muted2);border:1px solid var(--border)}}.btn-cl:hover{{background:var(--border);color:#fff}}

/* ── ANALYTICS PAGES ── */
.apage{{padding:24px}}
.apage-title{{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:3px;text-transform:uppercase;margin-bottom:20px}}
.section-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:28px}}
.acard{{background:var(--s1);border:1px solid var(--border);border-radius:10px;padding:20px}}
.acard-title{{font-family:var(--mono);font-size:11px;color:var(--muted2);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}}
.bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:9px}}
.bar-label{{font-size:13px;color:var(--text);min-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-track{{flex:1;height:8px;background:var(--s2);border-radius:4px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px;background:linear-gradient(90deg,var(--accent),var(--blue));transition:.3s}}
.bar-val{{font-family:var(--mono);font-size:11px;color:var(--muted2);min-width:54px;text-align:right}}
.bar-cnt{{font-family:var(--mono);font-size:10px;color:var(--muted);min-width:32px;text-align:right}}

/* time heatmap */
.hm-wrap{{overflow-x:auto}}
.hm-grid{{display:grid;grid-template-columns:40px repeat(24,1fr);gap:2px;min-width:700px}}
.hm-lbl{{font-family:var(--mono);font-size:10px;color:var(--muted);display:flex;align-items:center;justify-content:center}}
.hm-cell{{height:28px;border-radius:3px;background:var(--s2);display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:9px;color:transparent;cursor:default;transition:.1s}}
.hm-cell:hover{{color:#fff}}

/* channel table */
.ch-table{{width:100%;border-collapse:collapse}}
.ch-table th{{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;padding:8px 10px;border-bottom:1px solid var(--border);text-align:right}}
.ch-table th:first-child{{text-align:left}}
.ch-table td{{padding:9px 10px;border-bottom:1px solid var(--border);font-size:13px;text-align:right}}
.ch-table td:first-child{{text-align:left;font-weight:500}}
.ch-table tr:hover td{{background:var(--s2)}}
.mine-row td:first-child{{color:var(--accent3)}}

/* brainstorm cards */
.bs-card{{background:var(--s1);border:1px solid var(--border);border-radius:10px;padding:18px;margin-bottom:12px}}
.bs-rank{{font-family:var(--mono);font-size:22px;font-weight:700;color:var(--border2);margin-bottom:8px}}
.bs-channel{{font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}}
.bs-title{{font-size:16px;font-weight:600;color:#fff;margin-bottom:12px}}
.bs-meta{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:14px}}
.bs-m{{font-family:var(--mono);font-size:12px;color:var(--muted2)}}
.bs-m.g{{color:var(--accent)}}.bs-m.y{{color:var(--accent3)}}.bs-m.r{{color:var(--accent2)}}
.progress-row{{display:flex;align-items:center;gap:12px;margin-bottom:8px}}
.progress-lbl{{font-size:12px;color:var(--muted2);min-width:80px}}
.progress-bar{{flex:1;height:6px;background:var(--s2);border-radius:3px;overflow:hidden}}
.progress-fill{{height:100%;border-radius:3px}}
.progress-val{{font-family:var(--mono);font-size:12px;min-width:40px;text-align:right}}
.sat-badge{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;margin-bottom:10px}}
.sat-fresh{{background:rgba(0,232,181,.1);color:var(--accent);border:1px solid rgba(0,232,181,.3)}}
.sat-part{{background:rgba(245,183,0,.1);color:var(--accent3);border:1px solid rgba(245,183,0,.3)}}
.sat-sat{{background:rgba(255,55,95,.1);color:var(--accent2);border:1px solid rgba(255,55,95,.3)}}
.fmt-badge{{display:inline-block;padding:2px 9px;border-radius:4px;font-family:var(--mono);font-size:10px;background:var(--s2);border:1px solid var(--border);color:var(--muted2);margin-left:8px}}
.bs-open{{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:7px;background:#ff0000;color:#fff;font-size:13px;font-weight:600;border:none;cursor:pointer;margin-top:10px;text-decoration:none}}

/* HOF */
.hof-card{{background:var(--s1);border:1px solid var(--border);border-radius:9px;padding:14px 16px;margin-bottom:8px;display:grid;grid-template-columns:auto 1fr auto;gap:0 14px;align-items:center}}
.hof-score{{font-family:var(--mono);font-size:20px;font-weight:700;color:var(--accent2);white-space:nowrap}}
.hof-ch{{font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:1px;text-transform:uppercase;margin-bottom:3px}}
.hof-t{{font-size:14px;font-weight:500;color:#fff}}
.hof-right{{text-align:right}}
.hof-views{{font-family:var(--mono);font-size:14px;color:#fff;margin-bottom:4px}}
.hof-age{{font-size:11px;color:var(--muted)}}

/* ── TREND RADAR styles ── */
.tr-card{{background:var(--s1);border:1px solid var(--border);border-radius:10px;padding:18px;margin-bottom:10px}}
.tr-keyword{{font-family:var(--mono);font-size:20px;font-weight:700;color:var(--accent);margin-bottom:10px}}
.tr-signal{{display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;margin-bottom:10px}}
.tr-sig-mv{{background:rgba(255,34,68,.1);color:#ff2244;border:1px solid rgba(255,34,68,.3)}}
.tr-sig-su{{background:rgba(212,77,255,.1);color:#d44dff;border:1px solid rgba(212,77,255,.3)}}
.tr-sig-tr{{background:rgba(0,232,181,.1);color:var(--accent);border:1px solid rgba(0,232,181,.3)}}
.tr-sig-wa{{background:rgba(245,183,0,.1);color:var(--accent3);border:1px solid rgba(245,183,0,.3)}}
.tr-meta{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px}}
.tr-m{{font-family:var(--mono);font-size:12px;color:var(--muted2)}}
.tr-ch-pills{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}}
.tr-ch-pill{{font-size:11px;padding:3px 9px;border-radius:20px;background:var(--s2);border:1px solid var(--border);color:var(--muted2)}}
.tr-entry{{display:flex;align-items:center;gap:10px;padding:7px 10px;background:var(--s2);border-radius:6px;margin-bottom:5px}}
.tr-entry-ch{{font-size:11px;color:var(--accent);min-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.tr-entry-t{{font-size:12px;color:var(--text);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.tr-entry-v{{font-family:var(--mono);font-size:11px;color:#fff;margin-left:auto}}

/* ── FREQUENCY TRACKER styles ── */
.freq-table{{width:100%;border-collapse:collapse}}
.freq-table th{{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;padding:8px 10px;border-bottom:1px solid var(--border);text-align:left}}
.freq-table th:not(:first-child){{text-align:right}}
.freq-table td{{padding:9px 10px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:middle}}
.freq-table td:not(:first-child){{text-align:right}}
.freq-table tr:hover td{{background:var(--s2)}}
.spark{{font-family:monospace;font-size:14px;letter-spacing:1px;color:var(--accent)}}
.freq-status{{display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700}}
.fs-surge{{background:rgba(0,232,181,.1);color:var(--accent);border:1px solid rgba(0,232,181,.3)}}
.fs-active{{background:rgba(79,142,247,.1);color:var(--blue);border:1px solid rgba(79,142,247,.3)}}
.fs-low{{background:var(--s2);color:var(--muted);border:1px solid var(--border)}}
.fs-quiet{{background:rgba(245,183,0,.1);color:var(--accent3);border:1px solid rgba(245,183,0,.3)}}
.fs-ghost{{background:rgba(255,55,95,.1);color:var(--accent2);border:1px solid rgba(255,55,95,.3)}}
.freq-alert-section{{margin-bottom:20px}}
.freq-alert-card{{background:var(--s1);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:8px}}
.freq-alert-title{{font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--muted2);text-transform:uppercase;margin-bottom:10px}}

/* ── BENCHMARK styles ── */
.bm-scorecard{{width:100%;border-collapse:collapse;margin-bottom:24px}}
.bm-scorecard th{{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;padding:8px 12px;border-bottom:1px solid var(--border);text-align:right}}
.bm-scorecard th:first-child{{text-align:left}}
.bm-scorecard td{{padding:11px 12px;border-bottom:1px solid var(--border);font-size:13px;text-align:right}}
.bm-scorecard td:first-child{{text-align:left;font-weight:500;color:var(--text)}}
.bm-scorecard tr:hover td{{background:var(--s2)}}
.bm-you{{color:var(--accent3);font-weight:700}}
.bm-ahead{{color:var(--accent)}}
.bm-close{{color:var(--accent3)}}
.bm-trail{{color:var(--accent2)}}
.bm-big{{color:#ff2244;font-weight:700}}
.bm-bar-wrap{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.bm-bar-label{{font-size:12px;color:var(--text);min-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bm-bar-track{{flex:1;height:10px;background:var(--s2);border-radius:5px;overflow:hidden;position:relative}}
.bm-bar-fill{{height:100%;border-radius:5px;position:absolute;left:0;top:0}}
.bm-bar-val{{font-family:var(--mono);font-size:11px;color:var(--muted2);min-width:60px;text-align:right}}
.bm-you-bar .bm-bar-fill{{background:linear-gradient(90deg,var(--accent3),#ffd700)}}
.bm-comp-bar .bm-bar-fill{{background:linear-gradient(90deg,var(--accent),var(--blue))}}
.kw-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px}}

/* empty */
.empty{{padding:60px;text-align:center;color:var(--muted)}}
.empty-icon{{font-size:36px;margin-bottom:10px}}

@media(max-width:800px){{
  body{{flex-direction:column;height:auto;overflow:auto}}
  .leftnav{{width:100%;height:auto;flex-direction:row;flex-wrap:wrap;position:relative;overflow:visible}}
  .logo{{padding:12px 16px 8px}}
  .nav-group-label{{display:none}}
  .nav-divider{{display:none}}
  .nav-spacer{{display:none}}
  .nav-kpis{{grid-template-columns:repeat(4,1fr);border-top:none;padding:8px 16px}}
  .nav-meta{{padding:4px 16px 8px}}
  .nav-tab{{padding:8px 10px;font-size:12px}}
  .main-content{{height:auto;overflow:visible}}
  .layout{{grid-template-columns:1fr}}
  .sidebar{{display:none}}
  .section-grid{{grid-template-columns:1fr}}
  .kw-grid{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>

<!-- LEFT SIDEBAR NAV -->
<nav class="leftnav">
  <div class="logo">SHORTS SPY</div>

  <div class="nav-group-label">Discover</div>
  <button class="nav-tab active" onclick="showTab('videos')"><span class="nav-icon">📊</span>Videos</button>
  <button class="nav-tab" onclick="showTab('brainstorm')"><span class="nav-icon">🧠</span>Brainstorm</button>
  <button class="nav-tab" onclick="showTab('trends')"><span class="nav-icon">📡</span>Trend Radar</button>

  <div class="nav-divider"></div>
  <div class="nav-group-label">Competitor Intel</div>
  <button class="nav-tab" onclick="showTab('benchmark')"><span class="nav-icon">⚔️</span>Benchmark</button>
  <button class="nav-tab" onclick="showTab('freq')"><span class="nav-icon">📅</span>Upload Freq</button>
  <button class="nav-tab" onclick="showTab('channels')"><span class="nav-icon">📺</span>Channels</button>

  <div class="nav-divider"></div>
  <div class="nav-group-label">Analytics</div>
  <button class="nav-tab" onclick="showTab('titles')"><span class="nav-icon">📝</span>Titles</button>
  <button class="nav-tab" onclick="showTab('hashtags')"><span class="nav-icon">🏷</span>Hashtags</button>
  <button class="nav-tab" onclick="showTab('thumbnails')"><span class="nav-icon">🎨</span>Thumbnails</button>
  <button class="nav-tab" onclick="showTab('timing')"><span class="nav-icon">🕐</span>Timing</button>

  <div class="nav-divider"></div>
  <div class="nav-group-label">Records</div>
  <button class="nav-tab" onclick="showTab('hof')"><span class="nav-icon">🏆</span>Hall of Fame</button>

  <div class="nav-spacer"></div>

  <div class="nav-kpis">
    <div class="kpi-mini"><div class="kpi-v" id="kT">{total}</div><div class="kpi-l">Tracked</div></div>
    <div class="kpi-mini"><div class="kpi-v g" id="kV">{viral_count}</div><div class="kpi-l">Viral</div></div>
    <div class="kpi-mini"><div class="kpi-v r" id="kS">{spike_count}</div><div class="kpi-l">Spikes</div></div>
    <div class="kpi-mini"><div class="kpi-v y" id="kF">{fresh_count}</div><div class="kpi-l">Fresh</div></div>
  </div>
  <div class="nav-meta">{scan_time}<br>{html.escape(profile_label)}</div>
</nav>

<!-- MAIN CONTENT -->
<div class="main-content">

<!-- ════════════════ PAGE: VIDEOS ════════════════ -->
<div class="page active" id="page-videos">
  <div class="toolbar">
    <div class="search-wrap">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input type="text" id="vsearch" placeholder="Search title, channel…" oninput="renderVideos()">
    </div>
    <input type="text" class="bare-input" id="vminviews" placeholder="Min views (e.g. 500k)" style="max-width:160px;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--s2);color:var(--text);font-size:13px;width:160px;outline:none;font-family:var(--sans)" oninput="renderVideos()">
    <input type="number" class="bare-input" id="vmaxdays" placeholder="Max days" style="max-width:110px;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--s2);color:var(--text);font-size:13px;width:110px;outline:none;font-family:var(--sans)" oninput="renderVideos()">
    <div id="filterPills" style="display:flex;gap:6px;flex-wrap:wrap"></div>
    <div id="sortPills" style="display:flex;gap:6px;flex-wrap:wrap"></div>
    <div class="rcount" id="rcount"></div>
  </div>
  <div class="layout">
    <div class="sidebar">
      <div class="sb-title" style="margin-top:4px">Hype Level</div>
      <div id="hypeSB"></div>
      <div class="sb-title" style="margin-top:16px">Channel</div>
      <div id="chSB"></div>
    </div>
    <div class="feed" id="vfeed"></div>
  </div>
</div>

<!-- ════════════════ PAGE: BRAINSTORM ════════════════ -->
<div class="page" id="page-brainstorm">
  <div class="apage" id="bsContent"></div>
</div>

<!-- ════════════════ PAGE: TREND RADAR ════════════════ -->
<div class="page" id="page-trends">
  <div class="apage">
    <div class="apage-title">📡 Trend Radar — Topics Blowing Up Across Multiple Channels</div>
    <div id="trendSummary" style="margin-bottom:18px"></div>
    <div class="section-grid">
      <div class="acard">
        <div class="acard-title">Top Trending Topics (last 7 days)</div>
        <div id="trendBarChart"></div>
      </div>
      <div class="acard">
        <div class="acard-title">Signal Strength — Channel Coverage</div>
        <div id="trendCoverageChart"></div>
      </div>
    </div>
    <div id="trendCards"></div>
  </div>
</div>

<!-- ════════════════ PAGE: FREQ TRACKER ════════════════ -->
<div class="page" id="page-freq">
  <div class="apage">
    <div class="apage-title">📅 Upload Frequency Tracker — Cadence · Quiet · Surge</div>
    <div id="freqAlerts" class="freq-alert-section"></div>
    <div class="acard" style="overflow-x:auto">
      <div class="acard-title">All Channels — Last 12 Weeks</div>
      <div id="freqTable"></div>
    </div>
  </div>
</div>

<!-- ════════════════ PAGE: BENCHMARK ════════════════ -->
<div class="page" id="page-benchmark">
  <div class="apage">
    <div class="apage-title">⚔️ Your Channel vs Competitors</div>
    <div id="bmContent"></div>
  </div>
</div>

<!-- ════════════════ PAGE: TITLES ════════════════ -->
<div class="page" id="page-titles">
  <div class="apage">
    <div class="apage-title">Title Pattern Analysis</div>
    <div class="section-grid">
      <div class="acard"><div class="acard-title">Format patterns by avg views</div><div id="patternsChart"></div></div>
      <div class="acard"><div class="acard-title">Title length (words) by avg views</div><div id="lengthChart"></div></div>
    </div>
    <div class="acard"><div class="acard-title">Pattern detail table</div><div id="patternTable"></div></div>
  </div>
</div>

<!-- ════════════════ PAGE: HASHTAGS ════════════════ -->
<div class="page" id="page-hashtags">
  <div class="apage">
    <div class="apage-title">Hashtag Analysis</div>
    <div class="section-grid">
      <div class="acard"><div class="acard-title">🏆 Best avg views per tag</div><div id="tagAvgChart"></div></div>
      <div class="acard"><div class="acard-title">📊 Most used tags</div><div id="tagUseChart"></div></div>
    </div>
  </div>
</div>

<!-- ════════════════ PAGE: THUMBNAILS ════════════════ -->
<div class="page" id="page-thumbnails">
  <div class="apage"><div class="apage-title">Thumbnail Analysis</div><div id="thumbContent"></div></div>
</div>

<!-- ════════════════ PAGE: CHANNELS ════════════════ -->
<div class="page" id="page-channels">
  <div class="apage"><div class="apage-title">Channel Summary</div><div class="acard" style="overflow-x:auto"><div id="chTable"></div></div></div>
</div>

<!-- ════════════════ PAGE: TIMING ════════════════ -->
<div class="page" id="page-timing">
  <div class="apage">
    <div class="apage-title">Posting Time Analysis</div>
    <div class="section-grid">
      <div class="acard"><div class="acard-title">Best day to post (avg views)</div><div id="dayChart"></div></div>
      <div class="acard"><div class="acard-title">Best hour UTC (avg views)</div><div id="hourChart"></div></div>
    </div>
    <div class="acard"><div class="acard-title">Day × Hour heatmap (avg views)</div><div class="hm-wrap"><div id="heatmap"></div></div></div>
  </div>
</div>

<!-- ════════════════ PAGE: HOF ════════════════ -->
<div class="page" id="page-hof">
  <div class="apage"><div class="apage-title">Hall of Fame — All-Time Viral</div><div id="hofContent"></div></div>
</div>

<!-- MODAL -->
<div id="modalWrap" style="display:none"></div>

<script>
// ── DATA ──
const VIDEOS      = {data_js};
const PATTERNS    = {patterns_js};
const LENGTHS     = {lengths_js};
const HASHTAGS    = {hashtags_js};
const POSTING     = {posting_js};
const CHANNELS    = {channels_js};
const BRAINSTORM  = {brainstorm_js};
const THUMBDATA   = {thumb_js};
const TRENDS      = {trend_js};
const FREQ        = {freq_js};
const BENCHMARK   = {bench_js};
const HOF         = {hof_js};
const DAYS        = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

// ── STATE ──
let sortKey = "score", activeHype = "all", activeChannel = null
let filterSpike = false, filterFresh = false, filterMine = false

const SORTS = [
  {{key:"score",   label:"🔥 Viral",    fn:r=>r.score}},
  {{key:"views",   label:"👀 Views",    fn:r=>r.views}},
  {{key:"vpd",     label:"📈 VPD",      fn:r=>r.vpd}},
  {{key:"growth",  label:"🚀 Growth",   fn:r=>r.growth}},
  {{key:"likes",   label:"❤ Likes",    fn:r=>r.likes}},
  {{key:"lr",      label:"💎 Like%",    fn:r=>r.lr}},
  {{key:"comments",label:"💬 Comments", fn:r=>r.comments}},
  {{key:"adj",     label:"🏅 Sub-Adj",  fn:r=>r.adj_score}},
]
const HYPE = [
  {{key:"all",      label:"All Levels",  color:"#5a6480",  min:0,  max:999}},
  {{key:"legendary",label:"LEGENDARY",   color:"#ff2244",  min:10, max:999}},
  {{key:"insane",   label:"INSANE",      color:"#d44dff",  min:5,  max:10}},
  {{key:"viral",    label:"VIRAL",       color:"#ff6600",  min:3,  max:5}},
  {{key:"hot",      label:"HOT",         color:"#ffcc00",  min:2,  max:3}},
  {{key:"rising",   label:"Rising",      color:"#44ff88",  min:1.3,max:2}},
  {{key:"normal",   label:"Normal",      color:"#374151",  min:0,  max:1.3}},
]
const HCLASS = {{legendary:"hl",insane:"hi",viral:"hv",hot:"hh",rising:"hr",normal:"hn"}}
const BCLASS = {{legendary:"bhl",insane:"bhi",viral:"bhv",hot:"bhh",rising:"bhr",normal:"bhn"}}

function fmt(n) {{
  if (!n && n !== 0) return "—"
  if (n >= 1e6) return (n/1e6).toFixed(1)+"M"
  if (n >= 1e3) return (n/1e3).toFixed(1)+"K"
  return String(Math.round(n))
}}
function parseMV(s) {{
  if (!s) return 0; s=s.toLowerCase().trim()
  if (s.endsWith("m")) return parseFloat(s)*1e6
  if (s.endsWith("k")) return parseFloat(s)*1e3
  return parseFloat(s)||0
}}
function hypeOf(score) {{
  if (score>=10) return "legendary"; if (score>=5) return "insane"
  if (score>=3)  return "viral";     if (score>=2) return "hot"
  if (score>=1.3)return "rising";    return "normal"
}}
function barRow(label, val, max, extra="", colorOverride="") {{
  const pct = max>0 ? Math.round(val/max*100) : 0
  const fillStyle = colorOverride ? `background:${{colorOverride}};width:${{pct}}%` : `width:${{pct}}%`
  return `<div class="bar-row">
    <div class="bar-label">${{label}}</div>
    <div class="bar-track"><div class="bar-fill" style="${{fillStyle}}"></div></div>
    <div class="bar-val">${{fmt(val)}}</div>
    ${{extra ? `<div class="bar-cnt">${{extra}}</div>` : ""}}
  </div>`
}}

// ── TABS ──
function showTab(id) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'))
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'))
  document.getElementById('page-'+id).classList.add('active')
  // activate matching nav button
  document.querySelectorAll('.nav-tab').forEach(t => {{
    if (t.getAttribute('onclick') && t.getAttribute('onclick').includes("'"+id+"'"))
      t.classList.add('active')
  }})
  // scroll main content to top on tab switch
  document.querySelector('.main-content').scrollTop = 0
  const renders = {{
    titles:renderTitles, hashtags:renderHashtags, thumbnails:renderThumbnails,
    channels:renderChannels, timing:renderTiming, brainstorm:renderBrainstorm,
    hof:renderHOF, trends:renderTrends, freq:renderFreq, benchmark:renderBenchmark
  }}
  if (renders[id]) renders[id]()
}}

// ── VIDEO FEED (unchanged from v4.1) ──
function getFiltered() {{
  const q  = document.getElementById("vsearch").value.toLowerCase()
  const mv = parseMV(document.getElementById("vminviews").value)
  const md = parseInt(document.getElementById("vmaxdays").value)||null
  const sf = SORTS.find(s=>s.key===sortKey).fn
  return VIDEOS.filter(r => {{
    if (q && !r.title.toLowerCase().includes(q) && !r.channel.toLowerCase().includes(q)) return false
    if (mv && r.views < mv) return false
    if (md && r.published) {{
      const d = Math.floor((Date.now()-new Date(r.published))/86400000)
      if (d > md) return false
    }}
    if (filterSpike && !r.is_spike) return false
    if (filterFresh && !r.fresh)    return false
    if (filterMine  && !r.is_mine)  return false
    if (activeHype !== "all") {{
      const lvl = HYPE.find(h=>h.key===activeHype)
      if (!lvl) {{}} else if (activeHype==="legendary") {{ if (r.score < 10) return false }}
      else {{ if (r.score < lvl.min || r.score >= lvl.max) return false }}
    }}
    if (activeChannel && r.channel !== activeChannel) return false
    return true
  }}).sort((a,b)=>sf(b)-sf(a))
}}

function renderVideos() {{
  const filtered = getFiltered()
  const fp = [
    {{k:"Spike",label:"⚡ Spikes",cls:"red",val:filterSpike}},
    {{k:"Fresh",label:"🆕 <48h",cls:"blue",val:filterFresh}},
    {{k:"Mine", label:"★ Mine", cls:"yellow",val:filterMine}},
  ]
  document.getElementById("filterPills").innerHTML = fp.map(p =>
    `<div class="pill ${{p.cls}} ${{p.val?"active":""}}" data-fk="${{p.k}}">${{p.label}}</div>`
  ).join("")
  document.querySelectorAll("#filterPills .pill").forEach(el => {{
    el.addEventListener("click", () => {{
      if(el.dataset.fk==="Spike") filterSpike=!filterSpike
      if(el.dataset.fk==="Fresh") filterFresh=!filterFresh
      if(el.dataset.fk==="Mine")  filterMine=!filterMine
      renderVideos()
    }})
  }})
  document.getElementById("sortPills").innerHTML = SORTS.map(s =>
    `<div class="pill ${{s.key===sortKey?"active":""}}" data-sk="${{s.key}}">${{s.label}}</div>`
  ).join("")
  document.querySelectorAll("#sortPills .pill").forEach(el => {{
    el.addEventListener("click", () => {{ sortKey=el.dataset.sk; renderVideos() }})
  }})
  document.getElementById("rcount").textContent = filtered.length + " / " + VIDEOS.length + " videos"

  const hypeCounts = {{}}
  HYPE.forEach(h => {{
    if (h.key==="all") hypeCounts[h.key] = VIDEOS.length
    else hypeCounts[h.key] = VIDEOS.filter(r => {{
      if (h.key==="legendary") return r.score>=10
      return r.score>=h.min && r.score<h.max
    }}).length
  }})
  document.getElementById("hypeSB").innerHTML = HYPE.map(h =>
    `<div class="hype-row ${{activeHype===h.key?"sel":""}}" data-hk="${{h.key}}">
      <div class="hd" style="background:${{h.color}}"></div>
      <div class="hlbl">${{h.label}}</div>
      <div class="hcnt">${{hypeCounts[h.key]||0}}</div>
    </div>`
  ).join("")
  document.querySelectorAll("#hypeSB .hype-row").forEach(el => {{
    el.addEventListener("click", () => {{ activeHype=el.dataset.hk; renderVideos() }})
  }})

  const chMap = {{}}
  VIDEOS.forEach(r => {{
    if (!chMap[r.channel]) chMap[r.channel] = {{count:0,views:0,is_mine:r.is_mine}}
    chMap[r.channel].count++; chMap[r.channel].views += r.views
  }})
  const chArr = Object.entries(chMap).sort((a,b)=>b[1].views-a[1].views)
  const maxV = chArr[0]?.[1].views||1
  document.getElementById("chSB").innerHTML = chArr.map(([ch,s]) => {{
    const pct = Math.round(s.views/maxV*100)
    return `<div class="ch-item ${{activeChannel===ch?"sel":""}}" data-ch="${{ch.replace(/"/g,"&quot;")}}">
      <div><div class="ch-name ${{s.is_mine?"mine":""}}">${{ch}}</div>
      <div class="ch-bar" style="width:${{pct}}%"></div></div>
      <div class="ch-cnt">${{s.count}}</div>
    </div>`
  }}).join("")
  document.querySelectorAll("#chSB .ch-item").forEach(el => {{
    el.addEventListener("click", () => {{
      activeChannel = activeChannel===el.dataset.ch ? null : el.dataset.ch
      renderVideos()
    }})
  }})

  const feed = document.getElementById("vfeed")
  if (!filtered.length) {{ feed.innerHTML = `<div class="empty"><div class="empty-icon">🔍</div><p>No videos match</p></div>`; return }}
  feed.innerHTML = filtered.slice(0,200).map((r,i) => {{
    const hp = hypeOf(r.score)
    const badges = [
      r.is_spike?`<span class="badge b-sp">⚡SPIKE</span>`:"",
      r.fresh?`<span class="badge b-fr">🆕48H</span>`:"",
      r.is_mine?`<span class="badge b-me">★YOU</span>`:"",
      r.has_note?`<span class="badge b-nt">📝</span>`:"",
      `<span class="badge b-hl ${{BCLASS[hp]}}">${{hp.toUpperCase()}}</span>`,
    ].filter(Boolean).join(" ")
    return `<div class="card ${{HCLASS[hp]}}" data-idx="${{i}}">
      <div class="c-rank">#${{i+1}}</div>
      <div>
        <div class="c-top"><span class="c-ch ${{r.is_mine?"mine":""}}">${{r.channel}}</span>${{badges}}</div>
        <div class="c-title">${{r.title}}</div>
        <div class="c-meta">
          <span class="m w">👀 ${{fmt(r.views)}}</span>
          <span class="m g">${{r.score.toFixed(1)}}×</span>
          <span class="m">📈 ${{fmt(r.vpd)}}/d</span>
          <span class="m b">❤ ${{r.lr.toFixed(1)}}%</span>
          ${{r.growth>0?`<span class="m g">+${{fmt(r.growth)}}</span>`:""}}
          <span class="m">${{r.age}}</span>
          ${{r.subs?`<span class="m">👥 ${{fmt(r.subs)}}</span>`:""}}
        </div>
        ${{r.note?`<div class="note-line">📝 ${{r.note}}</div>`:""}}
      </div>
    </div>`
  }}).join("")
  if (filtered.length>200) feed.innerHTML += `<div class="empty"><p style="color:var(--muted2)">Showing top 200 of ${{filtered.length}} — use filters to narrow down</p></div>`
  document.querySelectorAll(".card[data-idx]").forEach(el => {{
    el.addEventListener("click", () => {{ const r=filtered[parseInt(el.dataset.idx)]; if(r) openModal(r) }})
  }})
}}

function openModal(r) {{
  const hp = hypeOf(r.score)
  const hcol = {{legendary:"#ff2244",insane:"#d44dff",viral:"#ff6600",hot:"#ffcc00",rising:"#44ff88",normal:"#6b7280"}}
  const sb = (k,v) => `<div class="sb"><div class="sk">${{k}}</div><div class="sv">${{v}}</div></div>`
  document.getElementById("modalWrap").style.display="flex"
  document.getElementById("modalWrap").className="overlay"
  document.getElementById("modalWrap").innerHTML = `
    <div class="modal">
      <div class="modal-ch">${{r.channel}}</div>
      <div class="modal-t">${{r.title}}</div>
      <div class="sg">
        ${{sb("Views",fmt(r.views))}}${{sb("Hype",`<span style="color:${{hcol[hp]}}">${{r.score.toFixed(1)}}×</span>`)}}${{sb("Views/Day",fmt(r.vpd))}}
        ${{sb("Like%",r.lr.toFixed(1)+"%")}}${{sb("Likes",fmt(r.likes))}}${{sb("Comments",fmt(r.comments))}}
        ${{sb("Ch Avg",fmt(r.ch_avg))}}${{sb("Sub-Adj",r.adj_score.toFixed(1)+"×")}}${{sb("Subs",r.subs?fmt(r.subs):"—")}}
        ${{sb("Growth",r.growth>=0?"+"+fmt(r.growth):fmt(r.growth))}}${{sb("Age",r.age)}}${{sb("Level",`<span style="color:${{hcol[hp]}}">${{hp.toUpperCase()}}</span>`)}}
      </div>
      ${{r.note?`<div class="modal-note">📝 ${{r.note}}</div>`:""}}
      <div class="btn-row">
        <a class="btn btn-yt" href="https://youtube.com/shorts/${{r.id}}" target="_blank">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>Open Short
        </a>
        <button class="btn btn-cl" onclick="document.getElementById('modalWrap').style.display='none'">Close</button>
      </div>
    </div>`
}}
document.addEventListener("keydown",e=>{{if(e.key==="Escape")document.getElementById("modalWrap").style.display="none"}})
document.addEventListener("click",e=>{{if(e.target.id==="modalWrap")e.target.style.display="none"}})

// ── BRAINSTORM ──
function renderBrainstorm() {{
  if (!BRAINSTORM.length) {{ document.getElementById("bsContent").innerHTML='<div class="empty"><div class="empty-icon">🧠</div><p>No data</p></div>'; return }}
  let h = `<div class="apage-title">Top 20 Videos to Remake — Composite Score</div>`
  BRAINSTORM.forEach((r,i) => {{
    const sc = r.is_spike ? `<span class="badge b-sp" style="margin-left:8px">⚡SPIKE</span>` : ""
    const mc = r.is_mine  ? `<span class="badge b-me" style="margin-left:8px">★ YOU</span>` : ""
    const satCls = r.saturation>=5?"sat-sat":r.saturation>=2?"sat-part":"sat-fresh"
    const satLbl = r.saturation>=5?`🔴 Saturated (${{r.saturation}} channels)`:r.saturation>=2?`🟡 Partial (${{r.saturation}} channels)`:`🟢 Fresh (only ${{r.saturation}} others)`
    const sPct   = r.success
    const sColor = sPct>=75?"var(--accent)":sPct>=55?"var(--accent3)":"var(--accent2)"
    h += `<div class="bs-card">
      <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px">
        <div class="bs-rank">#${{i+1}}</div>
        <div class="fmt-badge">${{r.format}}</div>${{sc}}${{mc}}
      </div>
      <div class="bs-channel">${{r.channel}}</div>
      <div class="bs-title">${{r.title}}</div>
      <div class="bs-meta">
        <span class="bs-m w">👀 ${{fmt(r.views)}}</span>
        <span class="bs-m g">${{r.score.toFixed(1)}}×</span>
        <span class="bs-m">📈 ${{fmt(r.vpd)}}/d</span>
        <span class="bs-m b">❤ ${{r.lr.toFixed(1)}}%</span>
        <span class="bs-m">${{r.age}}</span>
      </div>
      <div class="sat-badge ${{satCls}}">${{satLbl}}</div>
      <div class="progress-row">
        <div class="progress-lbl">Success est.</div>
        <div class="progress-bar"><div class="progress-fill" style="width:${{sPct}}%;background:${{sColor}}"></div></div>
        <div class="progress-val" style="color:${{sColor}};font-family:var(--mono);font-size:12px">${{sPct}}%</div>
      </div>
      <div class="progress-row">
        <div class="progress-lbl">Repro score</div>
        <div class="progress-bar"><div class="progress-fill" style="width:${{r.repro*10}}%;background:var(--blue)"></div></div>
        <div class="progress-val" style="color:var(--blue);font-family:var(--mono);font-size:12px">${{r.repro}}/10</div>
      </div>
      <a class="bs-open" href="https://youtube.com/shorts/${{r.id}}" target="_blank">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>Open Short
      </a>
    </div>`
  }})
  document.getElementById("bsContent").innerHTML = h
}}

// ══════════════════════════════════════════════════════════════
// ★ TREND RADAR rendering
// ══════════════════════════════════════════════════════════════
function renderTrends() {{
  if (!TRENDS.length) {{
    document.getElementById("trendCards").innerHTML = `<div class="empty"><div class="empty-icon">📡</div><p>No cross-channel trends found in the last 7 days.<br><span style="font-size:12px;color:var(--muted)">Scan more data or wait for channels to post on the same topic.</span></p></div>`
    document.getElementById("trendSummary").innerHTML = ""
    document.getElementById("trendBarChart").innerHTML = `<div class="empty"><p>No data yet</p></div>`
    document.getElementById("trendCoverageChart").innerHTML = `<div class="empty"><p>No data yet</p></div>`
    return
  }}

  // Summary stats
  const mvCount  = TRENDS.filter(t=>t.ch_count>=5).length
  const surCount = TRENDS.filter(t=>t.ch_count>=4 && t.ch_count<5).length
  const trCount  = TRENDS.filter(t=>t.ch_count>=3 && t.ch_count<4).length
  document.getElementById("trendSummary").innerHTML = `
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:4px">
      <div style="background:rgba(255,34,68,.08);border:1px solid rgba(255,34,68,.25);border-radius:8px;padding:10px 18px;text-align:center">
        <div style="font-family:var(--mono);font-size:22px;font-weight:700;color:#ff2244">${{mvCount}}</div>
        <div style="font-size:11px;color:var(--muted)">MULTI-VIRAL</div>
      </div>
      <div style="background:rgba(212,77,255,.08);border:1px solid rgba(212,77,255,.25);border-radius:8px;padding:10px 18px;text-align:center">
        <div style="font-family:var(--mono);font-size:22px;font-weight:700;color:#d44dff">${{surCount}}</div>
        <div style="font-size:11px;color:var(--muted)">SURGING</div>
      </div>
      <div style="background:rgba(0,232,181,.08);border:1px solid rgba(0,232,181,.25);border-radius:8px;padding:10px 18px;text-align:center">
        <div style="font-family:var(--mono);font-size:22px;font-weight:700;color:var(--accent)">${{trCount}}</div>
        <div style="font-size:11px;color:var(--muted)">TRENDING</div>
      </div>
      <div style="background:var(--s1);border:1px solid var(--border);border-radius:8px;padding:10px 18px;text-align:center">
        <div style="font-family:var(--mono);font-size:22px;font-weight:700;color:#fff">${{TRENDS.length}}</div>
        <div style="font-size:11px;color:var(--muted)">TOTAL SIGNALS</div>
      </div>
    </div>`

  // Bar chart: top 15 by avg views
  const maxAvg = TRENDS[0].avg_views
  document.getElementById("trendBarChart").innerHTML = TRENDS.slice(0,15).map(t =>
    barRow(`"${{t.keyword}}"`, t.avg_views, maxAvg, `${{t.ch_count}} channels`)
  ).join("")

  // Coverage chart: top 15 by channel count
  const sorted_by_ch = [...TRENDS].sort((a,b)=>b.ch_count-a.ch_count).slice(0,15)
  const maxCh = sorted_by_ch[0]?.ch_count||1
  document.getElementById("trendCoverageChart").innerHTML = sorted_by_ch.map(t =>
    barRow(`"${{t.keyword}}"`, t.ch_count, maxCh, fmt(t.avg_views), "rgba(155,114,255,1)")
  ).join("")

  // Trend detail cards
  const SIGS = {{
    multi: {{cls:"tr-sig-mv", label:"🔥 MULTI-VIRAL"}},
    surge: {{cls:"tr-sig-su", label:"🚨 SURGING"}},
    trend: {{cls:"tr-sig-tr", label:"📈 TRENDING"}},
    watch: {{cls:"tr-sig-wa", label:"👀 WATCH"}},
  }}
  function sigOf(t) {{
    if (t.ch_count>=5 && t.avg_score>=3) return SIGS.multi
    if (t.ch_count>=4) return SIGS.surge
    if (t.ch_count>=3) return SIGS.trend
    return SIGS.watch
  }}
  document.getElementById("trendCards").innerHTML = TRENDS.slice(0,20).map((t,i) => {{
    const sig = sigOf(t)
    const chPills = t.channels.slice(0,6).map(c=>`<div class="tr-ch-pill">${{c}}</div>`).join("")
    const entries = t.entries.slice(0,3).map(e => `
      <div class="tr-entry">
        <div class="tr-entry-ch">${{e.channel}}</div>
        <div class="tr-entry-t">${{e.title}}</div>
        <div class="tr-entry-v">${{fmt(e.views)}}</div>
        <a href="https://youtube.com/shorts/${{e.id}}" target="_blank" style="color:var(--accent);font-size:11px;margin-left:6px">▶</a>
      </div>`).join("")
    return `<div class="tr-card">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:6px">
        <div style="font-family:var(--mono);font-size:13px;color:var(--muted)">#${{i+1}}</div>
        <div class="tr-keyword">"${{t.keyword}}"</div>
        <div class="tr-signal ${{sig.cls}}">${{sig.label}}</div>
      </div>
      <div class="tr-meta">
        <span class="tr-m">📺 ${{t.ch_count}} channels</span>
        <span class="tr-m">🎬 ${{t.vid_count}} videos</span>
        <span class="tr-m">👀 avg ${{fmt(t.avg_views)}}</span>
        <span class="tr-m">🏆 best ${{fmt(t.best_views)}}</span>
        <span class="tr-m">🔥 ${{t.avg_score.toFixed(1)}}× avg hype</span>
      </div>
      <div class="tr-ch-pills">${{chPills}}${{t.channels.length>6?`<div class="tr-ch-pill">+${{t.channels.length-6}} more</div>`:""}}</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:8px">Top videos for this topic:</div>
      ${{entries}}
    </div>`
  }}).join("")
}}

// ══════════════════════════════════════════════════════════════
// ★ UPLOAD FREQUENCY TRACKER rendering
// ══════════════════════════════════════════════════════════════
function renderFreq() {{
  if (!FREQ.length) {{
    document.getElementById("freqAlerts").innerHTML = ""
    document.getElementById("freqTable").innerHTML = `<div class="empty"><div class="empty-icon">📅</div><p>No frequency data yet.<br><span style="font-size:12px;color:var(--muted)">Run a Scan — frequency data is collected automatically.</span></p></div>`
    return
  }}

  const BLOCKS = " ▁▂▃▄▅▆▇█"
  function spark(counts) {{
    const mx = Math.max(...counts, 1)
    return counts.map(c => BLOCKS[Math.min(Math.floor(c/mx*8),8)]).join("")
  }}
  const STATUS_CSS = {{surge:"fs-surge",active:"fs-active",low:"fs-low",quiet:"fs-quiet",ghost:"fs-ghost"}}
  const STATUS_LABEL = {{surge:"🚀 SURGE",active:"● Active",low:"○ Low",quiet:"⚠ Quiet",ghost:"💀 Ghost"}}

  const surges = FREQ.filter(r=>r.status==="surge")
  const quiets = FREQ.filter(r=>r.status==="quiet"||r.status==="ghost")

  let alerts = ""
  if (surges.length) {{
    const cards = surges.slice(0,5).map(r => `
      <div style="display:flex;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid var(--border)">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:#fff">${{r.channel}}</div>
          <div style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px">
            ${{r.recent_avg.toFixed(1)}}/wk now vs ${{r.older_avg.toFixed(1)}}/wk before
            · <span style="color:var(--accent)">+${{Math.round((r.trend_ratio-1)*100)}}%</span>
          </div>
        </div>
        <div class="spark" style="color:var(--accent)">${{spark(r.week_counts)}}</div>
      </div>`).join("")
    alerts += `<div class="freq-alert-card" style="border-color:rgba(0,232,181,.3)">
      <div class="freq-alert-title" style="color:var(--accent)">🚀 Surging — They found something (${{surges.length}} channels)</div>
      ${{cards}}
    </div>`
  }}
  if (quiets.length) {{
    const cards = quiets.slice(0,5).map(r => `
      <div style="display:flex;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid var(--border)">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600;color:#fff">${{r.channel}}</div>
          <div style="font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:2px">
            ${{r.status==="ghost"?`${{r.weeks_since}} weeks silent`:`Dropped ${{Math.round((1-r.trend_ratio)*100)}}% from ${{r.older_avg.toFixed(1)}}/wk`}}
          </div>
        </div>
        <div class="spark" style="color:var(--accent3)">${{spark(r.week_counts)}}</div>
      </div>`).join("")
    alerts += `<div class="freq-alert-card" style="border-color:rgba(245,183,0,.3)">
      <div class="freq-alert-title" style="color:var(--accent3)">💤 Gone Quiet — Opportunity in their niche (${{quiets.length}} channels)</div>
      ${{cards}}
    </div>`
  }}
  document.getElementById("freqAlerts").innerHTML = alerts

  // Full table
  const rows_html = FREQ.map(r => {{
    const tr_col = r.trend_ratio > 1.1 ? `style="color:var(--accent)"` :
                   r.trend_ratio < 0.9 ? `style="color:var(--accent2)"` : `style="color:var(--muted2)"`
    const tr_str = r.trend_ratio > 1.1 ? `+${{Math.round((r.trend_ratio-1)*100)}}%` :
                   r.trend_ratio < 0.9 ? `${{Math.round((r.trend_ratio-1)*100)}}%` : `~flat`
    const streak_html = r.weeks_since >= 2
      ? `<span style="color:var(--accent2)">${{r.weeks_since}}w silent</span>`
      : `<span style="color:var(--accent)">active</span>`
    return `<tr>
      <td style="font-weight:500;color:#fff;text-align:left">${{r.channel}}</td>
      <td><span class="freq-status ${{STATUS_CSS[r.status]||"fs-low"}}">${{STATUS_LABEL[r.status]||r.status}}</span></td>
      <td style="font-family:var(--mono)">${{r.recent_avg.toFixed(1)}}</td>
      <td style="font-family:var(--mono);color:var(--muted)">${{r.older_avg.toFixed(1)}}</td>
      <td ${{tr_col}} style="font-family:var(--mono)">${{tr_str}}</td>
      <td>${{streak_html}}</td>
      <td><span class="spark" style="color:var(--accent);font-size:13px">${{spark(r.week_counts)}}</span></td>
    </tr>`
  }}).join("")

  document.getElementById("freqTable").innerHTML = `
    <table class="freq-table">
      <thead><tr>
        <th>Channel</th><th>Status</th><th>Recent/wk</th><th>Prior/wk</th>
        <th>Trend</th><th>Streak</th><th>Last 12 Weeks ▸</th>
      </tr></thead>
      <tbody>${{rows_html}}</tbody>
    </table>
    <p style="font-size:11px;color:var(--muted);margin-top:12px">Recent = last 2 weeks avg · Prior = weeks 3–10 avg · Sparkline = upload count per week</p>`
}}

// ══════════════════════════════════════════════════════════════
// ★ BENCHMARK rendering
// ══════════════════════════════════════════════════════════════
function renderBenchmark() {{
  const bm = BENCHMARK
  if (!bm) {{
    document.getElementById("bmContent").innerHTML = `<div class="empty"><div class="empty-icon">⚔️</div><p>YOUR_CHANNEL not found in data.<br><span style="font-size:12px;color:var(--muted)">Set YOUR_CHANNEL at the top of shorts_spy.py and re-scan.</span></p></div>`
    return
  }}

  function fmtVal(key, v) {{
    if (key==="avg_score") return v.toFixed(2)+"×"
    if (key==="avg_lr")    return v.toFixed(2)+"%"
    return fmt(v)
  }}

  const STATUS = {{
    ahead: {{cls:"bm-ahead", label:"✅ Beating avg"}},
    close: {{cls:"bm-close", label:"⚠ Close behind"}},
    trail: {{cls:"bm-trail", label:"⬇ Trailing"}},
    big:   {{cls:"bm-big",   label:"🚨 Big gap"}},
  }}
  function statusOf(ratio) {{
    if (ratio<=1.0) return STATUS.ahead
    if (ratio<=1.5) return STATUS.close
    if (ratio<=3.0) return STATUS.trail
    return STATUS.big
  }}

  // Scorecard
  let sc = `
    <div style="margin-bottom:8px;font-size:13px;color:var(--muted2)">
      Channel: <span style="color:var(--accent3);font-weight:700">${{bm.my_name}}</span>
      &nbsp;·&nbsp; ${{bm.my_count}} your videos &nbsp;·&nbsp; ${{bm.their_count}} competitor videos
    </div>
    <div class="acard" style="overflow-x:auto;margin-bottom:24px">
    <div class="acard-title">Performance Scorecard</div>
    <table class="bm-scorecard">
      <thead><tr>
        <th>Metric</th><th>★ You</th><th>Competitor Avg</th><th>Gap</th><th>Your Rank</th><th>Status</th>
      </tr></thead><tbody>`

  bm.metrics.forEach(m => {{
    const s = statusOf(m.gap_ratio)
    const gap_str = m.gap_ratio<=1.0 ? `<span class="bm-ahead">ahead!</span>` : `${{m.gap_ratio.toFixed(1)}}×`
    sc += `<tr>
      <td>${{m.label}}</td>
      <td class="bm-you">${{fmtVal(m.key, m.my_val)}}</td>
      <td style="color:var(--muted2)">${{fmtVal(m.key, m.their_val)}}</td>
      <td>${{gap_str}}</td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--muted2)">#${{m.rank}} of ${{m.total}}</td>
      <td class="${{s.cls}}">${{s.label}}</td>
    </tr>`
  }})
  sc += `</tbody></table></div>`

  // Per-metric bar chart: pick first metric (avg_views)
  const viewsMet = bm.metrics.find(m=>m.key==="avg_views")
  if (viewsMet) {{
    const maxV = Math.max(...viewsMet.breakdown.map(x=>x.value), 1)
    sc += `<div class="section-grid">`
    sc += `<div class="acard">
      <div class="acard-title">Avg Views — Channel Ranking</div>`
    viewsMet.breakdown.forEach(ch => {{
      const pct  = Math.round(ch.value/maxV*100)
      const color = ch.is_mine ? "linear-gradient(90deg,var(--accent3),#ffd700)" : "linear-gradient(90deg,var(--accent),var(--blue))"
      sc += `<div class="bm-bar-wrap">
        <div class="bm-bar-label" style="${{ch.is_mine?"color:var(--accent3);font-weight:700":""}}">${{ch.is_mine?"★ "+ch.channel:ch.channel}}</div>
        <div class="bm-bar-track"><div class="bm-bar-fill" style="width:${{pct}}%;background:${{color}}"></div></div>
        <div class="bm-bar-val">${{fmtVal("avg_views",ch.value)}}</div>
      </div>`
    }})
    sc += `</div>`

    // Score chart
    const scoreMet = bm.metrics.find(m=>m.key==="avg_score")
    if (scoreMet) {{
      const maxS = Math.max(...scoreMet.breakdown.map(x=>x.value), 1)
      sc += `<div class="acard">
        <div class="acard-title">Avg Hype Score — Channel Ranking</div>`
      scoreMet.breakdown.forEach(ch => {{
        const pct  = Math.round(ch.value/maxS*100)
        const color = ch.is_mine ? "linear-gradient(90deg,var(--accent3),#ffd700)" : "linear-gradient(90deg,#ff6600,#ff2244)"
        sc += `<div class="bm-bar-wrap">
          <div class="bm-bar-label" style="${{ch.is_mine?"color:var(--accent3);font-weight:700":""}}">${{ch.is_mine?"★ "+ch.channel:ch.channel}}</div>
          <div class="bm-bar-track"><div class="bm-bar-fill" style="width:${{pct}}%;background:${{color}}"></div></div>
          <div class="bm-bar-val">${{fmtVal("avg_score",ch.value)}}</div>
        </div>`
      }})
      sc += `</div>`
    }}
    sc += `</div>` // end section-grid
  }}

  // Keyword comparison
  sc += `<div class="kw-grid">
    <div class="acard">
      <div class="acard-title">★ Your Top Topics (by total views)</div>`
  bm.my_top_kws.forEach(k => {{
    const maxKw = bm.my_top_kws[0]?.views||1
    sc += barRow(k.kw, k.views, maxKw, "", "linear-gradient(90deg,var(--accent3),#ffd700)")
  }})
  sc += `</div><div class="acard">
    <div class="acard-title">Competitor Top Topics (by total views)</div>`
  bm.comp_top_kws.forEach(k => {{
    const maxKw = bm.comp_top_kws[0]?.views||1
    sc += barRow(k.kw, k.views, maxKw, "")
  }})
  sc += `</div></div>` // end kw-grid

  // Gap narrative
  const avBm = bm.metrics.find(m=>m.key==="avg_views")
  if (avBm) {{
    const gapClass = avBm.gap_ratio<=1 ? "bm-ahead" : avBm.gap_ratio<=3 ? "bm-close" : "bm-big"
    sc += `<div class="acard" style="margin-top:20px">
      <div class="acard-title">Gap Summary</div>
      <div style="font-size:14px;line-height:2">
        Your avg views: <span class="bm-you">${{fmt(avBm.my_val)}}</span><br>
        Competitor avg: <span style="color:var(--muted2)">${{fmt(avBm.their_val)}}</span><br>
        ${{avBm.gap_ratio>1
          ? `Gap: <span class="${{gapClass}}">${{avBm.gap_ratio.toFixed(1)}}× behind</span> — ${{Math.round((1-1/avBm.gap_ratio)*100)}}% of competitor avg`
          : `<span class="bm-ahead">🎉 You're outperforming the competitor average!</span>`
        }}<br>
        Overall rank: <strong style="color:#fff">#${{avBm.rank}} out of ${{avBm.total}} channels</strong>
      </div>
    </div>`
  }}

  document.getElementById("bmContent").innerHTML = sc
}}

// ── TITLES ──
function renderTitles() {{
  if (!PATTERNS.length) return
  const maxAvg = PATTERNS[0].avg
  document.getElementById("patternsChart").innerHTML = PATTERNS.map(p => barRow(p.pattern, p.avg, maxAvg, `${{p.count}}`)).join("")
  const maxL = LENGTHS[0]?.avg||1
  document.getElementById("lengthChart").innerHTML = LENGTHS.map(l => barRow(l.bucket, l.avg, maxL, `${{l.count}}`)).join("")
  let tbl = `<table class="ch-table"><thead><tr><th>Pattern</th><th>Count</th><th>Avg Views</th><th>Best</th><th>Median</th></tr></thead><tbody>`
  PATTERNS.forEach(p => {{
    tbl += `<tr><td style="text-align:left;color:var(--accent)">${{p.pattern}}</td><td>${{p.count}}</td><td>${{fmt(p.avg)}}</td><td style="color:var(--accent)">${{fmt(p.best)}}</td><td>${{fmt(p.median)}}</td></tr>`
  }})
  document.getElementById("patternTable").innerHTML = tbl + `</tbody></table>`
}}

// ── HASHTAGS ──
function renderHashtags() {{
  if (!HASHTAGS.by_avg?.length) {{
    document.getElementById("tagAvgChart").innerHTML = `<div class="empty"><p>No tag data</p></div>`; return
  }}
  const maxA = HASHTAGS.by_avg[0].avg
  document.getElementById("tagAvgChart").innerHTML = HASHTAGS.by_avg.slice(0,30).map(t => barRow(t.tag, t.avg, maxA, `${{t.count}}`)).join("")
  const maxU = HASHTAGS.by_use[0]?.count||1
  document.getElementById("tagUseChart").innerHTML = HASHTAGS.by_use.slice(0,30).map(t => barRow(t.tag, t.count, maxU, fmt(t.avg))).join("")
}}

// ── THUMBNAILS ──
function renderThumbnails() {{
  const wrap = document.getElementById("thumbContent")
  if (!THUMBDATA) {{ wrap.innerHTML = `<div class="empty"><div class="empty-icon">🎨</div><p>No thumbnail data yet</p></div>`; return }}
  const section = (title, data) => {{
    const vals = Object.values(data).map(v=>v.avg); const mx = Math.max(...vals)||1
    let h = `<div class="acard" style="margin-bottom:16px"><div class="acard-title">${{title}}</div>`
    for (const [k,v] of Object.entries(data)) {{
      const labels = {{"dark":"🌑 Dark (<80)","mid":"🌤 Mid-tone","bright":"☀️ Bright (>160)","face":"🙂 Face present","no_face":"🚫 No face","text":"📝 Text overlay","no_text":"✨ Clean"}}
      h += barRow(labels[k]||k, v.avg, mx, `${{v.count}} vids`)
    }}
    h += `<p style="font-size:11px;color:var(--muted);margin-top:10px">Based on ${{THUMBDATA.total}} videos with thumbnail data</p></div>`
    return h
  }}
  wrap.innerHTML = `<div class="section-grid">${{section("🌟 Brightness", THUMBDATA.brightness)}}${{section("🙂 Face", THUMBDATA.face)}}</div>${{section("📝 Text Overlay", THUMBDATA.text)}}`
}}

// ── CHANNELS ──
function renderChannels() {{
  const maxV = CHANNELS[0]?.views||1
  let tbl = `<table class="ch-table"><thead><tr><th>Channel</th><th>Subs</th><th>Shorts</th><th>Total Views</th><th>Growth</th><th>Avg Views</th><th>Avg Score</th><th>Best Score</th><th>Like%</th></tr></thead><tbody>`
  CHANNELS.forEach(c => {{
    const g = c.growth>0?`<span style="color:var(--accent)">+${{fmt(c.growth)}}</span>`:`<span style="color:var(--muted)">${{fmt(c.growth)}}</span>`
    tbl += `<tr class="${{c.is_mine?"mine-row":""}}">
      <td>${{c.channel}}${{c.is_mine?" ★":""}}</td><td>${{c.subs?fmt(c.subs):"—"}}</td><td>${{c.count}}</td>
      <td style="color:#fff">${{fmt(c.views)}}</td><td>${{g}}</td><td>${{fmt(c.avg)}}</td>
      <td style="color:${{c.avg_score>=3?"var(--accent2)":c.avg_score>=1.5?"var(--accent3)":"inherit"}}">${{c.avg_score.toFixed(2)}}×</td>
      <td style="color:var(--accent)">${{c.best_score.toFixed(2)}}×</td>
      <td style="color:var(--blue)">${{c.avg_lr.toFixed(1)}}%</td>
    </tr>`
  }})
  document.getElementById("chTable").innerHTML = tbl + `</tbody></table>`
}}

// ── TIMING ──
function renderTiming() {{
  if (!POSTING.days?.length) return
  const mxD = Math.max(...POSTING.days.map(d=>d.avg))||1
  document.getElementById("dayChart").innerHTML = POSTING.days.map(d => barRow(d.day, d.avg, mxD, `${{d.count}}`)).join("")
  const allH = Array.from({{length:24}},(_,i)=>POSTING.hours.find(h=>h.hour===i)||{{hour:i,avg:0,count:0}})
  const mxH = Math.max(...allH.map(h=>h.avg))||1
  document.getElementById("hourChart").innerHTML = allH.map(h => barRow(h.hour.toString().padStart(2,"0")+":00", h.avg, mxH, `${{h.count}}`)).join("")
  const hm = POSTING.heatmap||[]
  const maxHM = Math.max(...hm.map(c=>c.avg),1)
  let hmHTML = `<div class="hm-grid"><div class="hm-lbl"></div>`
  for (let h=0;h<24;h++) hmHTML += `<div class="hm-lbl">${{h.toString().padStart(2,"0")}}</div>`
  for (let d=0;d<7;d++) {{
    hmHTML += `<div class="hm-lbl">${{DAYS[d]}}</div>`
    for (let h=0;h<24;h++) {{
      const cell=hm.find(c=>c.d===d&&c.h===h); const avg=cell?.avg||0
      const alpha=0.05+(avg/maxHM)*0.85
      hmHTML += `<div class="hm-cell" style="background:rgba(0,232,181,${{alpha.toFixed(2)}})" title="${{avg?DAYS[d]+" "+h.toString().padStart(2,"0")+":00 — avg "+fmt(avg):""}}">${{avg?fmt(avg):""}}</div>`
    }}
  }}
  document.getElementById("heatmap").innerHTML = hmHTML + `</div>`
}}

// ── HOF ──
function renderHOF() {{
  if (!HOF.length) {{ document.getElementById("hofContent").innerHTML='<div class="empty"><div class="empty-icon">🏆</div><p>Hall of Fame empty</p></div>'; return }}
  document.getElementById("hofContent").innerHTML = HOF.map(v => `
    <div class="hof-card">
      <div class="hof-score">${{v.score_at_entry.toFixed(1)}}×</div>
      <div><div class="hof-ch">${{v.channel}}</div><div class="hof-t">${{v.title}}</div></div>
      <div class="hof-right">
        <div class="hof-views">${{fmt(v.views)}}</div>
        <div class="hof-age">${{v.entered_at?.slice(0,10)||""}}</div>
        <a href="https://youtube.com/shorts/${{v.id}}" target="_blank" style="font-family:var(--mono);font-size:10px;color:var(--accent)">▶ Open</a>
      </div>
    </div>`).join("")
}}

// ── INIT ──
renderVideos()
</script>
</div><!-- end .main-content -->
</body>
</html>"""

    os.makedirs("dashboards", exist_ok=True)
    fname = os.path.join("dashboards", f"shorts_dashboard_{datetime.now().strftime('%Y%m%d_%H%M')}.html")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html_content)
    console.print(f"  ✅  [green]Generated → [bold]{fname}[/bold][/green]")
    if Confirm.ask("  Open in browser?", default=True):
        webbrowser.open(os.path.abspath(fname))

# ══════════════════════════════════════════════════════════════
#  BRAINSTORM
# ══════════════════════════════════════════════════════════════

