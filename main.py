import json, os

from utils import console, fmt, load_cache, save_cache, db_file
import state

from profiles   import select_profile, manage_profiles
from scan       import do_scan, start_auto_scan, fetch_subscriber_counts
from data       import build_rows, apply_filters, ask_filters, show_notes, show_remake_history, export_csv
from dashboard  import show_dashboard, show_channel_summary
from scan       import show_hof
from analysis   import show_analysis_menu
from brainstorm import ai_brainstorm
from trends     import show_trend_radar
from freq       import show_freq_tracker
from benchmarking import show_benchmarking
from web          import generate_web_dashboard
from settings     import show_settings
from velocity     import show_velocity_curves
from wordpower    import show_word_performance
from remakroi     import show_remake_roi

from rich.panel import Panel
from rich.prompt import Prompt

def main():
    console.print("[bold cyan]  SHORTS SPY[/bold cyan]  [dim]v4.2[/dim]")
    console.print(Panel("[dim]track competitors · spot trends · find what's blowing up[/dim]", border_style="bright_black",padding=(0,2)))
    select_profile()

    while True:
        ptag=f"  [dim]profile: [yellow]{state._active_profile}[/yellow][/dim]" if state._active_profile else ""
        console.print(f"\n  [bold white]MENU[/bold white]{ptag}\n")
        console.print("  [cyan]1[/cyan]  📡  Scan              [dim]fetch data · spikes · HOF · sub counts[/dim]")
        console.print("  [cyan]2[/cyan]  📊  Dashboard         [dim]8 rankings · outliers · spikes · notes[/dim]")
        console.print("  [cyan]3[/cyan]  📺  Channels          [dim]totals · subs · posting time[/dim]")
        console.print("  [cyan]4[/cyan]  🔬  Analysis          [dim]title patterns · hashtags · thumbnail colors · gap finder[/dim]")
        console.print("  [cyan]5[/cyan]  🧠  Brainstorm        [dim]top 10 · angles · freshness · backtest · remake log[/dim]")
        console.print("  [cyan]6[/cyan]  🏆  Hall of Fame      [dim]all-time viral (never deleted)[/dim]")
        console.print("  [cyan]7[/cyan]  🔁  Remake History    [dim]track what you made and how it performed[/dim]")
        console.print("  [cyan]8[/cyan]  📝  Notes")
        console.print("  [cyan]9[/cyan]  🌐  Web Dashboard     [dim]generate HTML · open in browser[/dim]")
        console.print("  [cyan]10[/cyan] 📁  Export CSV")
        console.print("  [cyan]11[/cyan] ⏰  Auto-scan")
        console.print("  [cyan]12[/cyan] 👤  Profiles          [dim]multi-niche channel lists[/dim]")
        console.print("  [cyan]13[/cyan] ⚙️   Settings")
        console.print("  [bold cyan]── NEW ──[/bold cyan]")
        console.print("  [cyan]14[/cyan] 📡  Trend Radar       [dim]topics blowing up across multiple channels[/dim]")
        console.print("  [cyan]15[/cyan] 📅  Upload Frequency  [dim]cadence · quiet channels · surge detection[/dim]")
        console.print("  [cyan]16[/cyan] ⚔️   Benchmarking      [dim]your stats vs every competitor metric[/dim]")
        console.print("  [bold cyan]── v5 NEW ──[/bold cyan]")
        console.print("  [cyan]17[/cyan] 📈  Velocity Curves   [dim]per-video view history · still climbing vs fading[/dim]")
        console.print("  [cyan]18[/cyan] 🔤  Word Power        [dim]which title words drive more views[/dim]")
        console.print("  [cyan]19[/cyan] 💰  Remake ROI        [dim]win rate by format · channel · saturation[/dim]")
        console.print("  [cyan]q[/cyan]  👋  Quit\n")

        choice=Prompt.ask("  Pick", default="2").strip().lower()

        if choice=="1": do_scan()
        elif choice in ("2","3","4","5","9","10","14","15","16","17","18"):
            needs_data = choice in ("2","3","4","5","9","10","14","16","17","18")
            if needs_data and not os.path.exists(db_file()):
                console.print("\n  [red]No data — scan first (pick 1)[/red]\n"); continue

            if choice == "15":
                show_freq_tracker(None)
                continue

            with open(db_file()) as _f: data = json.load(_f)
            cache=load_cache()
            channel_ids=list({v.get("channelId","") for v in data.values() if v.get("channelId")})
            fetch_subscriber_counts(channel_ids,cache); save_cache(cache)
            all_rows=build_rows(data,cache)

            if   choice=="3":  show_channel_summary(all_rows)
            elif choice=="4":  show_analysis_menu(all_rows)
            elif choice=="5":  ai_brainstorm(all_rows)
            elif choice=="9":  generate_web_dashboard(all_rows)
            elif choice=="10": export_csv(all_rows)
            elif choice=="14": show_trend_radar(all_rows)
            elif choice=="16": show_benchmarking(all_rows)
            elif choice=="17": show_velocity_curves(all_rows)
            elif choice=="18": show_word_performance(all_rows)
            else:
                min_views,max_days=ask_filters(); rows=apply_filters(all_rows,min_views,max_days)
                label=" + ".join(filter(None,[f">={fmt(min_views)}" if min_views else "",f"last {max_days}d" if max_days else ""])) or "all videos"
                console.print(f"\n  [dim]Filter: [white]{label}[/white]  →  [cyan]{len(rows)} videos[/cyan][/dim]\n")
                if not rows: console.print("  [yellow]No videos matched.[/yellow]\n")
                else: show_dashboard(rows)
        elif choice=="6":  show_hof()
        elif choice=="7":  show_remake_history()
        elif choice=="8":  show_notes()
        elif choice=="11": start_auto_scan()
        elif choice=="12": manage_profiles()
        elif choice=="13": show_settings()
        elif choice=="19": show_remake_roi([])
        elif choice=="q":  console.print("\n  [dim]Later! 👋[/dim]\n"); break
        else: console.print("  [red]Type 1–19 or q[/red]")


if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"\nCRASHED: {e}"); import traceback; traceback.print_exc()
    finally: input("\nPress Enter to close...")