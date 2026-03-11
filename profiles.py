import re, json, os
from rich.prompt import Prompt

from utils import console, section, load_profiles, save_profiles
from config import YOUR_CHANNEL as _YOUR_CHANNEL, PROFILES_FILE
YOUR_CHANNEL = _YOUR_CHANNEL  # local mutable copy
import state

def load_profiles(): return json.load(open(PROFILES_FILE)) if os.path.exists(PROFILES_FILE) else {}
def save_profiles(p): json.dump(p, open(PROFILES_FILE, "w"), indent=2)

def select_profile():
    import state as _state
    profiles = load_profiles()
    if not profiles: return None
    section("PROFILES")
    items = list(profiles.items())
    for i, (name, p) in enumerate(items, 1):
        console.print(f"  [cyan]{i}[/cyan]  [white]{name}[/white]  [dim]{len(p['channels'])} channels[/dim]")
    console.print("  [cyan]n[/cyan]  New profile")
    console.print("  [cyan]d[/cyan]  Default\n")
    pick = Prompt.ask("  Pick", default="d").strip().lower()
    if pick == "d": return None
    if pick == "n": return manage_profiles(create_new=True)
    if pick.isdigit():
        idx = int(pick) - 1
        if 0 <= idx < len(items):
            name, p = items[idx]
            _state._active_profile = name
            state.CHANNELS[:]     = p["channels"]
            YOUR_CHANNEL    = p.get("your_channel", YOUR_CHANNEL)
            console.print(f"  [green]Profile: {name}[/green]\n")
            return name
    return None

def manage_profiles(create_new=False):
    import state as _state
    profiles = load_profiles()
    while True:
        section("PROFILES")
        if profiles:
            for i, (name, p) in enumerate(profiles.items(), 1):
                active = " [bold yellow]← active[/bold yellow]" if name == _state._active_profile else ""
                console.print(f"  [cyan]{i}[/cyan]  [white]{name}[/white]  [dim]{len(p['channels'])} channels[/dim]{active}")
        else: console.print("  [dim]No profiles yet[/dim]")
        console.print("\n  [cyan]n[/cyan]  New  [cyan]s[/cyan]  Switch  [cyan]e[/cyan]  Edit  [cyan]x[/cyan]  Delete  [cyan]q[/cyan]  Back\n")
        ch = Prompt.ask("  Pick", default="q").strip().lower()

        if ch == "n" or create_new:
            create_new = False
            name = Prompt.ask("  Profile name").strip()
            if not name: continue
            raw  = Prompt.ask("  Channel IDs (comma or newline separated)").strip()
            ids  = [x.strip() for x in re.split(r"[,\n]+", raw) if x.strip()]
            yc   = Prompt.ask("  Your channel ID (Enter to skip)", default="").strip()
            profiles[name] = {"channels": ids, "your_channel": yc or YOUR_CHANNEL}
            save_profiles(profiles)
            _state._active_profile = name; state.CHANNELS[:] = ids
            if yc: YOUR_CHANNEL = yc
            console.print(f"  [green]Created '{name}'[/green]")
            return name
        elif ch == "s":
            items = list(profiles.items())
            pick  = Prompt.ask("  Switch to #", default="").strip()
            if pick.isdigit():
                idx = int(pick) - 1
                if 0 <= idx < len(items):
                    name, p = items[idx]
                    _state._active_profile = name; state.CHANNELS[:] = p["channels"]
                    YOUR_CHANNEL = p.get("your_channel", YOUR_CHANNEL)
                    console.print(f"  [green]Switched to '{name}'[/green]")
        elif ch == "e":
            items = list(profiles.items())
            pick  = Prompt.ask("  Edit #", default="").strip()
            if pick.isdigit():
                idx = int(pick) - 1
                if 0 <= idx < len(items):
                    name, p = items[idx]
                    sub = Prompt.ask("  [cyan]a[/cyan]=add  [cyan]r[/cyan]=remove", default="q").strip().lower()
                    if sub == "a":
                        raw = Prompt.ask("  New IDs").strip()
                        new_ids = [x.strip() for x in re.split(r"[,\n]+", raw) if x.strip()]
                        p["channels"] = list(dict.fromkeys(p["channels"] + new_ids))
                        save_profiles(profiles)
                        if name == _state._active_profile: state.CHANNELS[:] = p["channels"]
                        console.print(f"  [green]+{len(new_ids)} added[/green]")
                    elif sub == "r":
                        for j, cid in enumerate(p["channels"], 1): console.print(f"  [dim]{j}[/dim]  {cid}")
                        rm = Prompt.ask("  Remove #", default="").strip()
                        if rm.isdigit():
                            rmidx = int(rm) - 1
                            if 0 <= rmidx < len(p["channels"]):
                                p["channels"].pop(rmidx); save_profiles(profiles)
                                if name == _state._active_profile: state.CHANNELS[:] = p["channels"]
        elif ch == "x":
            items = list(profiles.items())
            pick  = Prompt.ask("  Delete #", default="").strip()
            if pick.isdigit():
                idx = int(pick) - 1
                if 0 <= idx < len(items):
                    name, _ = items[idx]; del profiles[name]; save_profiles(profiles)
                    if _state._active_profile == name: _state._active_profile = None
                    console.print(f"  [green]Deleted '{name}'[/green]")
        elif ch == "q": break
    return _active_profile

# ══════════════════════════════════════════════════════════════
#  CACHE: playlist IDs + subscriber counts
# ══════════════════════════════════════════════════════════════

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
