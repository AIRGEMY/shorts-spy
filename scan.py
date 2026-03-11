import json, os, io, time, webbrowser
from datetime import datetime, timezone
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt
from rich import box

try:
    import requests as _req
    from PIL import Image
except ImportError:
    pass

from utils import (
    console, section, fmt, is_short, is_fresh_48h, like_ratio,
    age_str,
    load_cache, save_cache, load_freq, save_freq, load_config, save_config,
    send_discord, db_file, hof_file, days_ago,
    THUMB_OK,
)
from config import (
    API_KEY, YOUR_CHANNEL, VIDEOS_PER_CHANNEL, MAX_VELOCITY_HISTORY,
    HOF_THRESHOLD, SPIKE_MIN_GROWTH, SPIKE_MIN_PCT,
)
import state
from freq import _update_freq_tracker
from data import build_rows

def get_playlist_id(youtube, channel_id, cache):
    if channel_id.startswith("UU"): return channel_id
    if channel_id in cache.get("playlists", {}): return cache["playlists"][channel_id]
    try:
        res   = youtube.channels().list(part="contentDetails", id=channel_id).execute()
        pl_id = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        cache.setdefault("playlists", {})[channel_id] = pl_id
        return pl_id
    except: return None

def fetch_subscriber_counts(channel_ids, cache):
    missing = [cid for cid in channel_ids if cid and cid not in cache.get("subs", {})]
    if not missing: return
    youtube = build("youtube", "v3", developerKey=API_KEY)
    for i in range(0, len(missing), 50):
        try:
            res = youtube.channels().list(part="statistics", id=",".join(missing[i:i+50])).execute()
            for item in res.get("items", []):
                cache.setdefault("subs", {})[item["id"]] = int(item["statistics"].get("subscriberCount", 0))
        except: pass

# ══════════════════════════════════════════════════════════════
#  THUMBNAIL ANALYSIS
# ══════════════════════════════════════════════════════════════

def analyze_thumbnail(video_id):
    if not THUMB_OK: return None
    try:
        resp   = _req.get(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", timeout=5)
        img    = Image.open(io.BytesIO(resp.content)).convert("RGB").resize((160, 90))
        raw    = img.tobytes()
        pixels = [(raw[i], raw[i+1], raw[i+2]) for i in range(0, len(raw), 3)]
        brightness = sum(0.299*r + 0.587*g + 0.114*b for r,g,b in pixels) / len(pixels)
        spreads    = [max(p)-min(p) for p in pixels]
        saturation = sum(spreads) / len(spreads)
        hc_pct     = sum(1 for s in spreads if s>100) / len(spreads) * 100
        w, h = 160, 90
        center = [img.getpixel((x,y)) for y in range(h//2) for x in range(w//4, 3*w//4)]
        def skin(r,g,b): return r>95 and g>40 and b>20 and max(r,g,b)-min(r,g,b)>15 and r>g and r>b
        face_pct = sum(1 for r,g,b in center if skin(r,g,b)) / len(center) * 100
        dom = Counter([(r//32*32, g//32*32, b//32*32) for r,g,b in pixels]).most_common(1)[0][0]
        return {"brightness":round(brightness,1),"saturation":round(saturation,1),
                "high_contrast_pct":round(hc_pct,1),"face_pct":round(face_pct,1),
                "dominant_color":"#{:02x}{:02x}{:02x}".format(*dom)}
    except: return None

def thumb_summary(t):
    if not t: return "[dim]no thumb data[/dim]"
    parts = ["[green]face ✓[/green]" if t["face_pct"]>8 else "[dim]no face[/dim]"]
    if t["high_contrast_pct"]>20: parts.append("[yellow]text overlay[/yellow]")
    bri = t["brightness"]
    parts.append("[white]bright[/white]" if bri>160 else "[dim]dark[/dim]" if bri<80 else "[dim]mid-tone[/dim]")
    parts.append(f"[dim]sat {t['saturation']:.0f}[/dim]")
    return "  ".join(parts)

# ══════════════════════════════════════════════════════════════
#  SPIKE DETECTION
# ══════════════════════════════════════════════════════════════

def find_spikes(db):
    spikes = []
    for vid, v in db.items():
        prev   = v.get("prev_views", 0)
        curr   = v["views"]
        growth = curr - prev
        if growth < SPIKE_MIN_GROWTH or prev == 0: continue
        if growth / prev < SPIKE_MIN_PCT: continue
        spikes.append({**v, "spike_growth": growth, "spike_pct": round(growth/prev*100)})
    return sorted(spikes, key=lambda x: x["spike_pct"], reverse=True)

# ══════════════════════════════════════════════════════════════
#  HALL OF FAME
# ══════════════════════════════════════════════════════════════

def update_hof(db, rows):
    hf  = hof_file()
    hof = json.load(open(hf)) if os.path.exists(hf) else {}
    added = 0
    for r in rows:
        if r["score"] >= HOF_THRESHOLD and r["id"] not in hof:
            hof[r["id"]] = {
                **{k: r[k] for k in ("id","channel","title","views","likes","comments","published")},
                "score_at_entry": round(r["score"],2),
                "entered_at":     datetime.now(timezone.utc).isoformat(),
            }
            added += 1
    json.dump(hof, open(hf,"w"), indent=2)
    return added

def show_hof():
    hf = hof_file()
    if not os.path.exists(hf): console.print("  [dim]Hall of Fame empty — scan first.[/dim]\n"); return
    hof = json.load(open(hf))
    if not hof: console.print("  [dim]No videos crossed HOF threshold yet.[/dim]\n"); return
    section("HALL OF FAME  —  All-Time Viral Shorts")
    console.print(f"  [dim]{len(hof)} videos  ·  threshold: {HOF_THRESHOLD}× channel avg[/dim]\n")
    t = Table(box=box.SIMPLE_HEAVY, border_style="bright_black", header_style="bold white")
    t.add_column("Channel", style="cyan",        width=18)
    t.add_column("Title",   style="white",        width=30)
    t.add_column("Views",   style="bright_white", width=10, justify="right")
    t.add_column("Score",   style="red",          width=7,  justify="right")
    t.add_column("Like%",   style="bright_blue",  width=7,  justify="right")
    t.add_column("Age",     style="dim",          width=9,  justify="right")
    t.add_column("Entered", style="dim",          width=12, justify="right")
    items = sorted(hof.values(), key=lambda x: x["score_at_entry"], reverse=True)
    for v in items:
        lr = like_ratio(v.get("likes",0), v.get("views",1))
        t.add_row(v["channel"][:18], v["title"][:30], fmt(v["views"]),
                  f"{v['score_at_entry']:.1f}×", f"{lr:.1f}%", age_str(v.get("published")), v.get("entered_at","")[:10])
    console.print(t)
    pick = Prompt.ask("\n  Open # (Enter to skip)", default="")
    if pick.isdigit():
        idx = int(pick) - 1
        if 0 <= idx < len(items): webbrowser.open(f"https://youtube.com/shorts/{items[idx]['id']}")

# ══════════════════════════════════════════════════════════════
#  SCAN
# ══════════════════════════════════════════════════════════════

def fetch_one_channel(channel_id, cache):
    videos = []
    for attempt in range(3):
        try:
            youtube  = build("youtube", "v3", developerKey=API_KEY)
            playlist = get_playlist_id(youtube, channel_id, cache)
            if not playlist: return videos
            video_ids = []
            next_page = None
            while len(video_ids) < VIDEOS_PER_CHANNEL:
                remaining   = VIDEOS_PER_CHANNEL - len(video_ids)
                page_size   = min(50, remaining)
                req_kwargs  = dict(part="contentDetails", playlistId=playlist, maxResults=page_size)
                if next_page: req_kwargs["pageToken"] = next_page
                res        = youtube.playlistItems().list(**req_kwargs).execute()
                page_ids   = [i["contentDetails"]["videoId"] for i in res.get("items", [])]
                video_ids += page_ids
                next_page  = res.get("nextPageToken")
                if not next_page or not page_ids: break
            if not video_ids: return videos
            for batch_start in range(0, len(video_ids), 50):
                batch = video_ids[batch_start : batch_start + 50]
                stats = youtube.videos().list(
                    part="statistics,snippet,contentDetails", id=",".join(batch)
                ).execute()
                for v in stats.get("items", []):
                    if not is_short(v): continue
                    views = int(v["statistics"].get("viewCount", 0))
                    likes = int(v["statistics"].get("likeCount", 0))
                    videos.append({
                        "id":        v["id"],
                        "channel":   v["snippet"]["channelTitle"],
                        "channelId": v["snippet"]["channelId"],
                        "title":     v["snippet"]["title"][:60],
                        "tags":      v["snippet"].get("tags", []),
                        "views":     views,
                        "likes":     likes,
                        "comments":  int(v["statistics"].get("commentCount", 0)),
                        "like_ratio": like_ratio(likes, views),
                        "published":  v["snippet"].get("publishedAt", ""),
                        "is_mine":    channel_id == YOUR_CHANNEL,
                        "fresh_48h":  is_fresh_48h(v["snippet"].get("publishedAt","")),
                    })
            return videos
        except HttpError as e:
            if e.resp.status == 404: return videos
            console.print(f"[dim red]  skipped {channel_id[:12]}: {e.reason}[/dim red]")
            return videos
        except Exception:
            if attempt < 2: time.sleep(2**attempt)
            else: console.print(f"[dim red]  failed {channel_id[:12]} after 3 attempts[/dim red]")
    return videos


def do_scan(silent=False):
    if not API_KEY:
        console.print(Panel(
            "1. Go to [cyan]console.cloud.google.com[/cyan]\n"
            "2. Create project → enable 'YouTube Data API v3'\n"
            "3. Credentials → API key\n"
            "4. Set env var: export YOUTUBE_API_KEY=your_key\n"
            "   or paste directly into config.py",
            title="⚠  Need API Key", border_style="red")); return

    if os.path.exists(db_file()):
        with open(db_file()) as f: db = json.load(f)
    else:
        db = {}
    cache = load_cache()
    freq  = load_freq()
    now   = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_channels = list(dict.fromkeys(state.CHANNELS))
    if YOUR_CHANNEL and YOUR_CHANNEL not in all_channels: all_channels.append(YOUR_CHANNEL)

    if not silent:
        section("SCAN" + (f"  [{state._active_profile}]" if state._active_profile else ""))
        console.print(f"  Scanning [cyan]{len(all_channels)}[/cyan] channels  ([dim]up to {VIDEOS_PER_CHANNEL} videos each via pagination[/dim])\n")

    cfg=load_config(); webhook=cfg.get("discord_webhook",""); alert_views=cfg.get("alert_min_views",0)
    alert_days=cfg.get("alert_max_days",3); alerts_fired=[]; new_count=0; ch_counts={}
    alerted_ids = set()  # prevent duplicate alerts per scan

    # Collect per-channel videos for freq tracker
    ch_videos_collected = defaultdict(list)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_one_channel, ch, cache): ch for ch in all_channels}
        done = 0
        for future in as_completed(futures):
            done += 1
            if not silent: print(f"  ⏳  {done}/{len(all_channels)}...", end="\r")
            for v in future.result():
                vid        = v["id"]
                prev_entry = db.get(vid, {})
                prev_views = prev_entry.get("views", v["views"])
                growth     = v["views"] - prev_views
                if vid not in db: new_count += 1
                ch_counts[v["channel"]] = ch_counts.get(v["channel"], 0) + 1
                history = prev_entry.get("view_history", [])
                history.append({"views": v["views"], "at": now})
                if len(history) > MAX_VELOCITY_HISTORY: history = history[-MAX_VELOCITY_HISTORY:]
                db[vid] = {
                    **v,
                    "growth":          growth,
                    "prev_views":      prev_views,
                    "scanned_at":      now,
                    "prev_scanned_at": prev_entry.get("scanned_at"),
                    "thumbnail":       prev_entry.get("thumbnail"),
                    "view_history":    history,
                    "predicted_success": prev_entry.get("predicted_success"),
                    "predicted_at":      prev_entry.get("predicted_at"),
                }
                ch_videos_collected[v["channel"]].append(v["published"])

                # ── Discord alert check ──
                if (webhook and alert_views and vid not in alerted_ids
                        and v["views"] >= alert_views
                        and (days_ago(v.get("published", "")) or 999) <= alert_days):
                    alerts_fired.append(v)
                    alerted_ids.add(vid)

    # ── Update upload frequency tracker ──
    _update_freq_tracker(freq, ch_videos_collected, today)
    save_freq(freq)

    with open(db_file(), "w") as f: json.dump(db, f, indent=2)
    save_cache(cache)

    rows_for_hof = build_rows(db, cache)
    hof_added    = update_hof(db, rows_for_hof)
    if alerts_fired: save_config(cfg)
    for v in alerts_fired:
        send_discord(webhook, f"🔥 **{v['channel']}** — {v['title']}\n👀 {fmt(v['views'])} views · {age_str(v.get('published'))}\nhttps://youtube.com/shorts/{v['id']}")

    spikes = find_spikes(db)
    if not silent:
        console.print(f"\n  ✅  [green]+{new_count} new[/green]  │  [cyan]{len(db)} total[/cyan]  │  "
                      f"[yellow]~{len(all_channels)*4} API units[/yellow]  [dim](limit: 10,000/day)[/dim]")
        if hof_added: console.print(f"  [bold yellow]🏆  +{hof_added} added to Hall of Fame[/bold yellow]")
        if alerts_fired: console.print(f"  [bold yellow]📣  Sent {len(alerts_fired)} Discord alert(s)[/bold yellow]")
        if spikes:
            console.print(f"\n  [bold red]⚡  {len(spikes)} SPIKE(S)[/bold red]\n")
            for s in spikes[:5]:
                console.print(f"   [red]+{s['spike_pct']}%[/red]  [cyan]{s['channel'][:22]}[/cyan]  "
                              f"[white]{s['title'][:40]}[/white]  [dim]+{fmt(s.get('spike_growth',0))} views[/dim]")
        console.print("\n  [bold]Shorts per channel:[/bold]\n")
        my_name = next((v["channel"] for v in db.values() if v.get("is_mine")), None)
        for ch, count in sorted(ch_counts.items(), key=lambda x: x[1], reverse=True):
            bar   = "█" * min(count, 40)
            label = f"[bold yellow]{ch[:28]} ★[/bold yellow]" if ch==my_name else f"[cyan]{ch[:28]}[/cyan]"
            console.print(f"  {label:<40}  [dim]{bar}[/dim] [white]{count}[/white]")
        console.print()

# ══════════════════════════════════════════════════════════════
#  AUTO SCAN
# ══════════════════════════════════════════════════════════════

def start_auto_scan():
    try: import schedule as sched
    except ImportError: console.print("[red]Run: pip install schedule[/red]"); return
    section("AUTO SCAN")
    console.print("  [cyan]1[/cyan]  Every 6h  [cyan]2[/cyan]  Every 12h  [cyan]3[/cyan]  Every 24h  [cyan]q[/cyan]  Cancel\n")
    hours = {"1":6,"2":12,"3":24}.get(Prompt.ask("  Pick", default="1"))
    if not hours: return
    console.print(f"\n  [green]Auto-scan every {hours}h started.[/green]  [dim]Ctrl+C to stop.[/dim]\n")
    def job():
        console.print(f"  [dim]{datetime.now().strftime('%H:%M')}  scanning...[/dim]", end="")
        do_scan(silent=True); console.print("  [green]done ✓[/green]")
    sched.every(hours).hours.do(job); job()
    try:
        while True: sched.run_pending(); time.sleep(60)
    except KeyboardInterrupt: console.print("\n  [dim]Stopped.[/dim]")

# ══════════════════════════════════════════════════════════════
#  FILTERS
# ══════════════════════════════════════════════════════════════

