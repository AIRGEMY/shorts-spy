import json, os, re, csv, io, statistics, time, html, webbrowser
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

try:
    import isodate
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.columns import Columns
    from rich.rule import Rule
    from rich import box
except ImportError:
    print("Missing packages! Run: pip install google-api-python-client isodate rich schedule requests Pillow")
    import sys; sys.exit(1)

try:
    import requests as _req
    from PIL import Image
    THUMB_OK = True
except ImportError:
    THUMB_OK = False

from config import (
    API_KEY, YOUR_CHANNEL,
    VIDEOS_PER_CHANNEL, TOP_N,
    HOF_THRESHOLD, SPIKE_MIN_GROWTH, SPIKE_MIN_PCT, MAX_VELOCITY_HISTORY,
    PROFILES_FILE, DB_FILE, HOF_FILE, CACHE_FILE,
    PRESETS_FILE, CONFIG_FILE, REMAKE_FILE, NOTES_FILE, FREQ_FILE,
    DAYS,
)
import state

console = Console()

def fmt(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
    return str(n)

def days_ago(iso_str):
    if not iso_str: return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except: return None

def views_per_day(views, published_iso):
    d = days_ago(published_iso)
    if not d or d == 0: return views
    return int(views / d)

def like_ratio(likes, views):
    if not views: return 0.0
    return round((likes / views) * 100, 2)

def hype_label(score):
    if score >= 10:  return "[bold red]LEGENDARY[/bold red]"
    if score >= 5:   return "[bold magenta]INSANE[/bold magenta]"
    if score >= 3:   return "[red]VIRAL[/red]"
    if score >= 2:   return "[yellow]HOT[/yellow]"
    if score >= 1.3: return "[green]Rising[/green]"
    return               "[dim]Normal[/dim]"

def age_str(published_iso):
    d = days_ago(published_iso)
    if d is None: return "?"
    if d == 0:    return "today"
    if d == 1:    return "1d ago"
    return f"{d}d ago"

def is_short(v):
    try:
        secs = isodate.parse_duration(v["contentDetails"]["duration"]).total_seconds()
    except: return False
    if secs > 180: return False
    if secs <= 60: return True
    title = v["snippet"].get("title", "").lower()
    desc  = v["snippet"].get("description", "").lower()
    tags  = [t.lower() for t in v["snippet"].get("tags", [])]
    return "#shorts" in title or "#shorts" in desc or "shorts" in tags

def is_fresh_48h(published_iso):
    d = days_ago(published_iso)
    return d is not None and d <= 1

def load_config():  return json.load(open(CONFIG_FILE)) if os.path.exists(CONFIG_FILE) else {}
def save_config(c): json.dump(c, open(CONFIG_FILE, "w"), indent=2)
def load_cache():   return json.load(open(CACHE_FILE)) if os.path.exists(CACHE_FILE) else {}
def save_cache(c):  json.dump(c, open(CACHE_FILE, "w"), indent=2)
def load_remakes(): return json.load(open(REMAKE_FILE)) if os.path.exists(REMAKE_FILE) else {}
def save_remakes(r): json.dump(r, open(REMAKE_FILE, "w"), indent=2)
def load_notes():   return json.load(open(NOTES_FILE)) if os.path.exists(NOTES_FILE) else {}
def save_notes(n):  json.dump(n, open(NOTES_FILE, "w"), indent=2)
def load_freq():    return json.load(open(FREQ_FILE)) if os.path.exists(FREQ_FILE) else {}
def save_freq(f):   json.dump(f, open(FREQ_FILE, "w"), indent=2)

def send_discord(url, msg):
    try: _req.post(url, json={"content": msg}, timeout=5)
    except: pass

def section(title):
    console.print()
    console.print(Rule(f"[bold white] {title} [/bold white]", style="bright_black"))
    console.print()

def db_file():
    if state._active_profile:
        safe = re.sub(r"[^a-z0-9_]", "_", state._active_profile.lower())
        return f"spy_data_{safe}.json"
    return DB_FILE

def hof_file():
    if state._active_profile:
        safe = re.sub(r"[^a-z0-9_]", "_", state._active_profile.lower())
        return f"spy_hof_{safe}.json"
    return HOF_FILE

# ══════════════════════════════════════════════════════════════
#  PROFILES
# ══════════════════════════════════════════════════════════════

def load_profiles(): return json.load(open(PROFILES_FILE)) if os.path.exists(PROFILES_FILE) else {}
def save_profiles(p): json.dump(p, open(PROFILES_FILE, "w"), indent=2)

# ══════════════════════════════════════════════════════════════
#  VELOCITY
# ══════════════════════════════════════════════════════════════

def velocity_label(history):
    if not history or len(history) < 3: return "[dim]—[/dim]"
    recent  = history[-1]["views"] - history[-2]["views"]
    earlier = history[-2]["views"] - history[-3]["views"]
    if earlier == 0: return "[dim]flat[/dim]"
    change = (recent - earlier) / earlier
    if change > 0.5:  return "[bold green]🚀 accelerating[/bold green]"
    if change > 0.1:  return "[green]↑ growing[/green]"
    if change > -0.1: return "[dim]→ stable[/dim]"
    if change > -0.4: return "[yellow]↓ slowing[/yellow]"
    return "[red]📉 fading[/red]"

def velocity_change(history):
    if not history or len(history) < 3: return 0
    recent  = history[-1]["views"] - history[-2]["views"]
    earlier = history[-2]["views"] - history[-3]["views"]
    if earlier == 0: return 0
    return (recent - earlier) / earlier