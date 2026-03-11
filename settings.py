import json
from rich.prompt import Prompt

from utils import console, section, fmt, load_config, save_config, send_discord, THUMB_OK, PRESETS_FILE
from data import load_presets

def show_settings():
    while True:
        cfg=load_config(); section("SETTINGS")
        wh=cfg.get("discord_webhook") or "[dim]not set[/dim]"; av=fmt(cfg.get("alert_min_views",0)) if cfg.get("alert_min_views") else "[dim]off[/dim]"; ad=cfg.get("alert_max_days",3)
        console.print(f"  Discord webhook  →  [cyan]{wh}[/cyan]\n  Alert threshold  →  [cyan]{av}[/cyan]  within [cyan]{ad}[/cyan] days\n  Thumbnails       →  [{'green]✓ available' if THUMB_OK else 'red]✗ pip install Pillow requests'}[/{'green' if THUMB_OK else 'red'}]\n")
        console.print("  [cyan]1[/cyan]  Set webhook  [cyan]2[/cyan]  Set alert  [cyan]3[/cyan]  Test webhook  [cyan]4[/cyan]  Manage presets  [cyan]q[/cyan]  Back\n")
        ch=Prompt.ask("  Pick", default="q").strip().lower()
        if ch=="1":
            cfg["discord_webhook"]=Prompt.ask("  Webhook URL (Enter to clear)", default=""); save_config(cfg); console.print("  [green]Saved![/green]")
        elif ch=="2":
            raw=Prompt.ask("  Min views (e.g. 500k, 0=disable)", default="0").lower()
            try:
                v=int(float(raw[:-1])*1_000_000) if raw.endswith("m") else int(float(raw[:-1])*1_000) if raw.endswith("k") else int(raw)
                cfg["alert_min_views"]=v
            except: console.print("  [red]Couldn't read[/red]"); continue
            try: cfg["alert_max_days"]=int(Prompt.ask("  Max age days", default="3"))
            except: pass
            save_config(cfg); console.print("  [green]Saved![/green]")
        elif ch=="3":
            wh=cfg.get("discord_webhook","")
            if not wh: console.print("  [red]Set webhook first[/red]")
            else: send_discord(wh,"✅ Shorts Spy — test!"); console.print("  [green]Sent![/green]")
        elif ch=="4":
            presets=load_presets()
            if not presets: console.print("  [dim]No presets.[/dim]")
            else:
                for i,(name,p) in enumerate(presets.items(),1): console.print(f"  [cyan]{i}[/cyan]  {name}")
                dp=Prompt.ask("  Delete #", default="")
                if dp.isdigit():
                    items=list(presets.items()); idx=int(dp)-1
                    if 0<=idx<len(items): del presets[items[idx][0]]; json.dump(presets,open(PRESETS_FILE,"w"),indent=2); console.print("  [green]Deleted.[/green]")
        elif ch=="q": break

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

