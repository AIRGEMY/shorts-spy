"""
brainstorm.py  —  REWRITE v4.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The ONE job of this file: show you exactly which video to remake and
give you the complete ready-to-film package — title, hook script,
angle, and a 0–100 Remake Score you can trust.

What's new:
  • NO video limit — shows every video in your data, sorted by score
  • #1 PICK called out at the top in a bold "MAKE THIS NOW" banner
  • Remake Score = transparent formula (views + hype + vpd + likes + recency)
  • Exact hook script generated for every video (say these words in the first 3s)
  • Exact title to use (not "here's a format", the actual title)
  • Exact angle in plain English — no jargon
  • Seen system — s# sends it to the bottom, un# brings it back
  • Age filter — just type a number (1, 7, 30…)
  • t# = 10 ready-to-copy title variants
  • g  = AI generates a completely original idea from your data
  • New card design — clean, dense, readable
"""

import json, os, re, math
from datetime import datetime, timezone
from collections import defaultdict, Counter

from rich.prompt  import Prompt, Confirm
from rich.panel   import Panel
from rich.rule    import Rule
from rich.table   import Table
from rich.text    import Text
from rich         import box

from utils import (
    console, section, fmt, age_str, days_ago,
    load_cache, save_cache, db_file,
)
from scan  import analyze_thumbnail, fetch_subscriber_counts, thumb_summary
from data  import log_remake

# ─────────────────────────────────────────────────────────────
#  SEEN
# ─────────────────────────────────────────────────────────────
SEEN_FILE = "spy_seen.json"

def load_seen():
    try:    return set(json.load(open(SEEN_FILE)))
    except: return set()

def save_seen(s): json.dump(list(s), open(SEEN_FILE, "w"), indent=2)

# ─────────────────────────────────────────────────────────────
#  STOPWORDS
# ─────────────────────────────────────────────────────────────
SW = {
    "the","a","an","and","or","but","in","on","at","to","for","of","is","it","this","that",
    "be","are","was","were","i","my","you","your","with","how","what","when","they","have",
    "has","all","not","do","did","just","so","up","out","we","he","she","vs","can","its",
    "if","as","by","from","about","into","will","would","who","which","been","then","than",
    "these","those","get","got","one","two","three","first","last","new","old","day","time",
    "way","now","back","still","here","there","where","why","made","make","take","use",
    "pov","shorts","short","youtube","part","every","ever","never","always","also","even",
    "only","very","really","actually","literally","basically","guys","people","things","thing",
    "more","some","most","her","him","they","been","that","dont","im","its","ive",
}

# ─────────────────────────────────────────────────────────────
#  FORMAT DETECT
# ─────────────────────────────────────────────────────────────
def detect_format(title):
    t = title.lower()
    if any(x in t for x in ("pov","when you","me when","me trying")):                 return "POV"
    if any(x in t for x in ("how to","tutorial","guide","step by step")):              return "Tutorial"
    if any(x in t for x in ("tier list","ranking","ranked","best ","worst ","top ")): return "Ranking"
    if any(x in t for x in (" vs "," vs.","versus")):                                 return "Comparison"
    if any(x in t for x in ("secret","hidden","you didn't know","nobody knows")):      return "Reveal"
    if any(x in t for x in ("challenge","i tried","attempting","24 hours")):           return "Challenge"
    if any(x in t for x in ("react","reacting","watching")):                           return "Reaction"
    if any(x in t for x in ("story","storytime","this happened")):                     return "Story"
    if re.search(r'\bpart\s*[1-6]\b|\bday\s*[1-9]\b|\bep\.?\s*[1-6]\b', t):          return "Series"
    if any(x in t for x in ("what if","imagine","what would")):                        return "Hypothetical"
    if any(x in t for x in ("exposed","caught","proof","they don't want")):            return "Expose"
    if t.strip().endswith("?"):                                                         return "Question"
    return "Other"

# ─────────────────────────────────────────────────────────────
#  REMAKE SCORE  (0–100, fully transparent)
# ─────────────────────────────────────────────────────────────
def remake_score(r, all_rows):
    """
    Composite 0–100 score that answers: 'how worth it is this to remake?'

    Components:
      40pts  Hype score  — how far above channel avg (proven viral)
      25pts  Views/day   — current algorithmic momentum
      20pts  Like ratio  — audience actually liked it (not just clickbait)
      10pts  Raw views   — absolute size of the prize
       5pts  Recency     — algorithm is still warm on this
    """
    vpds = [r2.get("vpd", 0) for r2 in all_rows]
    lrs  = [r2.get("like_ratio", 0) for r2 in all_rows]
    vws  = [r2.get("views", 0) for r2 in all_rows]
    scs  = [r2.get("score", 0) for r2 in all_rows]

    def norm(val, lo, hi):
        if hi == lo: return 0.5
        return max(0.0, min(1.0, (val - lo) / (hi - lo)))

    hype_pts  = norm(r["score"],              min(scs),  max(scs))  * 40
    vpd_pts   = norm(r.get("vpd", 0),         0,          max(vpds) or 1) * 25
    lr_pts    = norm(r.get("like_ratio", 0),  0,          max(lrs) or 1)  * 20
    views_pts = norm(r.get("views", 0),       0,          max(vws) or 1)  * 10
    age       = days_ago(r.get("published")) or 30
    rec_pts   = norm(1 / max(age, 1), 1/365, 1) * 5

    return round(hype_pts + vpd_pts + lr_pts + views_pts + rec_pts)

# ─────────────────────────────────────────────────────────────
#  EXACT HOOK SCRIPT  (say these exact words in second 1–3)
# ─────────────────────────────────────────────────────────────
def exact_hook(r):
    ft    = detect_format(r["title"])
    t     = r["title"]
    tl    = t.lower()
    words = [w for w in re.sub(r'[^\w\s]', '', t).split() if w.lower() not in SW and len(w) > 2]
    core  = " ".join(words[:3]) if words else t[:20]
    views_str = fmt(r["views"])
    ch    = r["channel"]

    hooks = {
        "POV":         f'Open already IN the scenario. Camera on your face. First word out loud: "POV:" then immediately say the situation. No title card. No intro. Just: "POV: [situation]." Cut.',
        "Tutorial":    f'Hold up the end result to camera first. Say: "This took me 3 days to figure out — watch." Then cut to step 1. Never say "hey guys" or "today we\'re gonna."',
        "Ranking":     f'Start mid-sentence: "Okay so [most controversial pick] is obviously number one, and if you disagree—" then cut to your list. Comments write themselves.',
        "Comparison":  f'Show result B first (the surprising winner). Say: "Everyone thinks [A] wins. They\'re wrong." Cut to the comparison. Reveal why at the very end.',
        "Reveal":      f'TEXT on screen frame 1: "[THE SECRET]". Then you on camera: "I wasn\'t supposed to show this." Pause 1 second. Then reveal it. Keep them for 80% of the video.',
        "Challenge":   f'Start on the fail. Literally. The worst attempt first. Say: "Day 1." Cut. Show the fail. Then let the journey play out. End on success. Never explain the challenge — show it.',
        "Reaction":    f'Your face fills the frame. Reaction starts BEFORE the clip plays. Say nothing. Let your expression do it. Text overlay: "[what you\'re reacting to]". Let them feel it.',
        "Story":       f'Start at the most insane moment of the story. Say: "So this actually happened—" then cut. Rewind. Now tell it from the start. Cliffhanger at 25s.',
        "Series":      f'Series Part 1 formula: establish stakes in second 1. "I\'m about to [do X] for [timeframe]. Nobody has done this before." Look at camera. Cut to it starting.',
        "Expose":      f'Show the screenshot / clip / evidence on screen first, no words. Let them read it. Then: "Yeah. That\'s real." Let it sit. Then explain it.',
        "Question":    f'Ask the question to CAMERA, not as a title card. Look directly at lens: "[Question]?" Pause 1 full second of silence. Then give your take. That pause = watch time.',
        "Hypothetical":f'State the scenario and immediately go to the most extreme consequence. "What if [X]? This would happen by day 3—" Cut to it. Don\'t ease in.',
    }
    return hooks.get(ft,
        f'First 2 seconds: say the most interesting thing about this topic, not an intro. '
        f'Cut immediately after. Think: what would make someone stop scrolling? Lead with that.')

# ─────────────────────────────────────────────────────────────
#  EXACT TITLE TO USE
# ─────────────────────────────────────────────────────────────
def exact_title(r):
    ft    = detect_format(r["title"])
    t     = r["title"]
    words = [w for w in re.sub(r'[^\w\s]', '', t).split() if w.lower() not in SW and len(w) > 2]
    core  = " ".join(words[:4]) if words else t[:25]

    templates = {
        "POV":         f"POV: {core}",
        "Tutorial":    f"How to {core} (nobody tells you this)",
        "Ranking":     f"Ranking every {core} from worst to best",
        "Comparison":  f"{core} vs {core} — the truth",
        "Reveal":      f"The {core} secret they don't want you to know",
        "Challenge":   f"I tried {core} for 30 days. Here's what happened",
        "Reaction":    f"Reacting to the craziest {core}",
        "Story":       f"The {core} story nobody believed (true)",
        "Series":      f"{core} Part 1: it starts here",
        "Expose":      f"{core} is a lie. Here's the proof",
        "Question":    f"Why does {core} actually work?",
        "Hypothetical":f"What if {core} happened tomorrow?",
    }
    base = templates.get(ft, t)

    # Sentence-case it
    return base[:1].upper() + base[1:]

# ─────────────────────────────────────────────────────────────
#  EXACT ANGLE  (plain English, no jargon, what to actually do)
# ─────────────────────────────────────────────────────────────
def exact_angle(r):
    ft   = detect_format(r["title"])
    age  = days_ago(r.get("published")) or 30
    vpd  = r.get("vpd", 0)
    lr   = r.get("like_ratio", 0)
    cmts = r.get("comments", 0)
    sc   = r.get("score", 0)
    t    = r["title"].lower()
    th   = r.get("thumbnail") or {}
    face = th.get("face_pct", 0) > 8

    # Urgency tag
    urgent = age <= 3 and sc >= 3
    hot    = vpd >= 80_000

    prefix = ""
    if urgent: prefix = "⏰ POST WITHIN 24H — "
    elif hot:  prefix = "🔥 TRENDING — "

    angles = {
        "POV": (
            "Film it in one uncut take. The scenario IS the hook — no setup needed. "
            "Pick the most relatable version of this topic for your audience. "
            "End without resolution — they should feel it, not understand it."
        ),
        "Tutorial": (
            "Film the end result first, then teach backwards. "
            "Keep it to 3 steps max. The 3rd step should be the unexpected one nobody knows. "
            f"{'Keep your face in frame — the reaction to the result is half the content.' if face else 'No face needed — show the output on screen the whole time.'}"
        ),
        "Ranking": (
            "Put your most controversial pick at #1 or dead last. "
            "That placement IS the content — comments will do the rest. "
            "Deliver your reasoning fast and confident, no hedging. "
            f"{'High engagement here means people FOUGHT about the rankings — be opinionated.' if cmts >= 300 else 'Be the most decisive take in your niche on this topic.'}"
        ),
        "Comparison": (
            "Show the 'underdog' winning. Set up expectations for A to win, then flip it. "
            "Film side by side if you can. End result on screen at the end — no talking needed."
        ),
        "Reveal": (
            "Tease it in the thumbnail. Delay the payoff until second 20+. "
            "Never fully explain it — leave one thing unresolved so they share it to find out. "
            "Text overlay on screen the entire time: '[WHAT IT IS]'."
        ),
        "Challenge": (
            "Film your worst attempt first and put it at the start. "
            "Show 3 attempts minimum. The failure is what gets watched. "
            "End on the win — but make the win look hard-earned."
        ),
        "Reaction": (
            "Your reaction face before the clip starts. No intro. "
            "Find the most insane version of this topic this week — your emotion amplifies it. "
            "Text overlay tells them what they're watching so they don't scroll."
        ),
        "Story": (
            "Start at the climax — the most insane/funny/unexpected moment. "
            "Then rewind: 'okay so here's how we got here.' "
            "Keep it under 45s. Cut every pause. End on the emotional payoff, not an explanation."
        ),
        "Series": (
            "This is a series Part 1 that already went viral. You can drop YOUR Part 1 on the same topic RIGHT NOW. "
            "Don't copy their episodes — make YOUR version of episode 1. "
            "Same premise, different creator = algorithm treats it as new content."
        ),
        "Expose": (
            "Lead with the evidence — screenshot, clip, or text on screen. "
            "Say nothing for 2 seconds. Let them process it. "
            "Then your take — fast and blunt. End with a question to camera."
        ),
        "Question": (
            "Say the question directly to camera. Pause. Answer it in a way no one else has. "
            "The question in the title should NOT match the question you say on camera — "
            "the double curiosity gap forces rewatches."
        ),
        "Hypothetical": (
            "Go straight to the most extreme consequence. Skip the 'what if' setup. "
            "By second 3 you should already be showing what would happen. "
            "End with the least expected outcome — that's the share moment."
        ),
    }

    base = angles.get(ft,
        "Replicate the pacing exactly — count the cuts per second and match them. "
        "The format is doing more work than the topic. "
        "Change the topic slightly (your niche version) but keep everything else identical."
    )
    return prefix + base

# ─────────────────────────────────────────────────────────────
#  SATURATION CHECK
# ─────────────────────────────────────────────────────────────
def saturation(r, all_rows):
    kws = set(w.lower() for w in r["title"].split() if len(w) > 3 and w.lower() not in SW)
    if not kws: return 0
    channels = set()
    for other in all_rows:
        if other["id"] == r["id"]: continue
        ok = set(w.lower() for w in other["title"].split() if len(w) > 3 and w.lower() not in SW)
        if len(kws & ok) / max(len(kws), 1) >= 0.35: channels.add(other["channel"])
    return len(channels)

# ─────────────────────────────────────────────────────────────
#  TITLE MUTATIONS
# ─────────────────────────────────────────────────────────────
def show_title_mutations(r):
    ft    = detect_format(r["title"])
    t     = r["title"]
    words = [w for w in re.sub(r'[^\w\s]', '', t).split() if w.lower() not in SW and len(w) > 2]
    core  = " ".join(words[:4]) if words else t[:25]
    c     = core.lower()

    variants = [
        f"POV: you {c}",
        f"I tried {c} for 7 days. This is what happened",
        f"Why everyone is wrong about {c}",
        f"The {c} secret nobody tells you",
        f"I did {c} every day for a month",
        f"How {c} actually works (they lied to you)",
        f"Ranking every type of {c} from worst to best",
        f"Stop doing {c} wrong — here's the fix",
        f"What actually happens when you {c}",
        f"The honest truth about {c}",
        f"I tested every {c} method. Here's the winner",
        f"{core} Part 1: it starts here",
    ]
    if ft == "Tutorial":  variants.append(f"Nobody teaches {c} like this")
    if ft == "POV":       variants.append(f"POV: {c} hits different")
    if r.get("like_ratio",0) >= 6: variants.append(f"The {c} thing everyone gets wrong (and how I fixed it)")

    console.print()
    console.print(Rule(f"[bold white] TITLE MUTATIONS — {r['title'][:35]} [/bold white]", style="cyan"))
    console.print(f"\n  [dim]Original: {t}[/dim]\n")
    for i, v in enumerate(variants[:12], 1):
        console.print(f"  [cyan]{i:>2}.[/cyan]  [white]{v}[/white]")
    console.print()

# ─────────────────────────────────────────────────────────────
#  AI GENERATE IDEA
# ─────────────────────────────────────────────────────────────
def ai_generate_idea(rows):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        console.print("\n  [yellow]⚠  Set ANTHROPIC_API_KEY to use this.[/yellow]")
        console.print("  [dim]  export ANTHROPIC_API_KEY=sk-ant-...[/dim]\n")
        return
    try:
        import requests as _req
    except ImportError:
        console.print("  [red]pip install requests[/red]"); return

    top = sorted(rows, key=lambda x: x.get("score", 0), reverse=True)[:15]
    kw_v = defaultdict(list)
    for r in top:
        for w in re.sub(r'[^\w\s]', '', r["title"].lower()).split():
            if w not in SW and len(w) >= 4: kw_v[w].append(r["views"])
    kw_str = ", ".join(f"{k}({fmt(sum(v))})" for k,v in
                       sorted(kw_v.items(), key=lambda x: sum(x[1]), reverse=True)[:10])
    best_fmt = Counter(detect_format(r["title"]) for r in top).most_common(1)[0][0]
    top_vids = "\n".join(f'- "{r["title"]}" — {fmt(r["views"])} views, {r["score"]:.1f}× hype, {r["channel"]}'
                         for r in top[:8])

    system = (
        "You are the best YouTube Shorts strategist alive. "
        "Generate 5 completely ORIGINAL video ideas — not remakes, not copies — that will blow up. "
        "Each idea must be filmable on a phone, psychologically irresistible, and something competitors haven't done. "
        "Format EXACTLY like this for each:\n\n"
        "IDEA [N]: [EXACT TITLE]\n"
        "Hook: [Exact first 2 seconds — what you say/show/do]\n"
        "Why: [One sentence — the psychological reason this works]\n"
        "Format: [format name]\n---"
    )
    user = (
        f"My niche data:\n\nTop performing videos right now:\n{top_vids}\n\n"
        f"Dominant format: {best_fmt}\nTop keywords by views: {kw_str}\n\n"
        "Generate 5 original ideas I can film TODAY. No copying. New angles only. Be brutally specific."
    )

    console.print("\n  [dim]🤖 Generating...[/dim]", end="", flush=True)
    try:
        resp = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-opus-4-5", "max_tokens": 1400, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=30,
        )
        resp.raise_for_status()
        out = resp.json()["content"][0]["text"]
        console.print(" [green]done[/green]")
        console.print()
        console.print(Rule("[bold cyan] 🤖 AI ORIGINAL IDEAS [/bold cyan]", style="cyan"))
        console.print(f"  [dim]from {len(top)} top videos · dominant format: {best_fmt}[/dim]\n")
        for idea in out.split("---"):
            idea = idea.strip()
            if not idea: continue
            lines = idea.split("\n")
            title = lines[0] if lines else ""
            body  = "\n  ".join(l for l in lines[1:] if l.strip())
            if title:
                console.print(Panel(f"  [bold white]{title}[/bold white]\n  {body}",
                                    border_style="cyan", padding=(0,1)))
        console.print()
        if Confirm.ask("  Save to file?", default=True):
            fname = f"ai_ideas_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            open(fname, "w").write(out)
            console.print(f"  [green]✓ {fname}[/green]")
    except Exception as e:
        console.print(f"\n  [red]Failed: {e}[/red]")

# ─────────────────────────────────────────────────────────────
#  CARD RENDERER
# ─────────────────────────────────────────────────────────────
def render_card(i, r, rs, all_rows, is_pick=False):
    sat   = saturation(r, all_rows)
    age   = days_ago(r.get("published")) or 0
    ft    = detect_format(r["title"])
    score = r.get("score", 0)
    vpd   = r.get("vpd", 0)
    lr    = r.get("like_ratio", 0)
    cmts  = r.get("comments", 0)

    # Score color
    sc_col = "bold green" if rs >= 80 else "green" if rs >= 65 else "yellow" if rs >= 45 else "dim"

    # Saturation color
    sat_s = (f"[red]saturated[/red]" if sat >= 5 else
             f"[yellow]{sat} others[/yellow]" if sat >= 2 else
             f"[green]fresh[/green]")

    # Spike / trending badges
    badges = []
    if r.get("is_spike"):    badges.append(f"[bold red]⚡SPIKE +{r.get('spike_pct','?')}%[/bold red]")
    if age <= 1:             badges.append("[bold magenta]🔥 POSTED TODAY[/bold magenta]")
    elif age <= 3:           badges.append("[magenta]🔥 3d old[/magenta]")
    if r.get("vel_change",0) > 0.2: badges.append("[green]🚀 accelerating[/green]")
    badge_str = "  ".join(badges)

    # Card content
    border = "bold yellow" if is_pick else "bright_black"
    prefix = "  🏆 [bold yellow]#1 PICK — MAKE THIS NOW[/bold yellow]\n  " if is_pick else "  "

    lines = [
        f"{prefix}[bold white]{i}.[/bold white]  [cyan]{r['channel']}[/cyan]",
        f"  [bold white]{r['title']}[/bold white]  [dim]{ft}[/dim]",
        "",
        f"  [dim]👀 {fmt(r['views'])}   {score:.1f}× hype   {fmt(vpd)}/day   "
        f"👍 {lr:.1f}%   💬 {fmt(cmts)}   📅 {age_str(r.get('published'))}[/dim]",
        f"  [{sc_col}]▶ REMAKE SCORE: {rs}/100[/{sc_col}]   🌊 {sat_s}",
    ]
    if badge_str: lines.append(f"  {badge_str}")
    lines += [
        "",
        f"  [bold]TITLE TO USE:[/bold]  [green]{exact_title(r)}[/green]",
        "",
        f"  [bold]HOOK SCRIPT:[/bold]",
        f"  [italic dim]{exact_hook(r)}[/italic dim]",
        "",
        f"  [bold]ANGLE:[/bold]",
        f"  [white]{exact_angle(r)}[/white]",
    ]
    if r.get("thumbnail"):
        lines += ["", f"  [dim]📸 {thumb_summary(r['thumbnail'])}[/dim]"]

    console.print(Panel("\n".join(lines), border_style=border, padding=(0,1)))
    console.print()

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
def ai_brainstorm(all_rows):
    console.print()
    console.print(Rule("[bold white] BRAINSTORM v4 [/bold white]", style="cyan"))
    console.print()

    # ── Age filter ──────────────────────────────────────────
    console.print("  [dim]Filter by age?  Type a number (1=today, 7=week, 30=month) or Enter for all[/dim]")
    raw = Prompt.ask("  Days", default="").strip()
    max_age = int(raw) if raw.isdigit() else None

    if max_age:
        rows = [r for r in all_rows if (days_ago(r.get("published")) or 9999) <= max_age]
        console.print(f"  [dim]Last {max_age}d → [cyan]{len(rows)}[/cyan] videos[/dim]\n")
    else:
        rows = all_rows
        console.print(f"  [dim]All time → [cyan]{len(rows)}[/cyan] videos[/dim]\n")

    if not rows:
        console.print("  [yellow]No videos in this range. Try a wider filter.[/yellow]\n"); return

    # ── Compute remake scores ───────────────────────────────
    scored = []
    for r in rows:
        rs = remake_score(r, rows)
        scored.append((rs, r))
    scored.sort(key=lambda x: x[0], reverse=True)

    # ── Seen split ──────────────────────────────────────────
    seen = load_seen()
    unseen = [(rs, r) for rs, r in scored if r["id"] not in seen]
    seen_l = [(rs, r) for rs, r in scored if r["id"] in seen]

    # ── Fetch thumbnails for top 20 ─────────────────────────
    db      = json.load(open(db_file())) if os.path.exists(db_file()) else {}
    changed = False
    for _, r in unseen[:20]:
        if not r.get("thumbnail"):
            th = analyze_thumbnail(r["id"]); r["thumbnail"] = th
            if r["id"] in db: db[r["id"]]["thumbnail"] = th; changed = True
    cache = load_cache()
    cids  = [r.get("channelId","") for _,r in unseen[:50] if r.get("channelId")]
    if cids: fetch_subscriber_counts(cids, cache); save_cache(cache)

    # Save predictions
    now_iso = datetime.now(timezone.utc).isoformat()
    for rs, r in unseen:
        if r["id"] in db and not db[r["id"]].get("predicted_success"):
            db[r["id"]]["predicted_success"] = rs
            db[r["id"]]["predicted_at"]      = now_iso; changed = True
    if changed and os.path.exists(db_file()):
        json.dump(db, open(db_file(),"w"), indent=2)

    age_label = f"last {max_age}d" if max_age else "all time"
    total = len(unseen)
    console.print(f"  [dim]{total} videos ranked by Remake Score · {len(seen_l)} seen[/dim]\n")

    # ── Render all unseen cards ─────────────────────────────
    for i, (rs, r) in enumerate(unseen, 1):
        render_card(i, r, rs, rows, is_pick=(i == 1))

    # ── SEEN section ────────────────────────────────────────
    if seen_l:
        console.print(Rule("[dim] ✓ SEEN [/dim]", style="bright_black"))
        console.print()
        for i, (rs, r) in enumerate(seen_l, 1):
            console.print(
                f"  [dim strike]{i:>3}. [{rs:>3}]  {r['channel'][:18]}  "
                f"{r['title'][:38]}  {fmt(r['views'])} · {age_str(r.get('published'))}[/dim strike]")
        console.print()

    # ── Command bar ─────────────────────────────────────────
    console.print(Rule("[dim] Commands [/dim]", style="bright_black"))
    console.print()
    console.print("  [cyan]s#[/cyan]  Seen  (sinks to bottom)    [cyan]un#[/cyan] Un-see")
    console.print("  [cyan]r#[/cyan]  Log Remake                  [cyan]t#[/cyan]  Title Mutations (12 variants)")
    console.print("  [cyan]g[/cyan]   🤖 AI Original Idea         [cyan]save[/cyan] Export .txt")
    console.print("  [cyan]open#[/cyan] Open in browser           [cyan]Enter[/cyan] Exit")
    console.print()

    unseen_map = {i+1: (rs,r) for i,(rs,r) in enumerate(unseen)}
    seen_map   = {i+1: (rs,r) for i,(rs,r) in enumerate(seen_l)}

    while True:
        cmd = Prompt.ask("  ›", default="").strip().lower()
        if not cmd: break

        # seen
        if cmd.startswith("s") and not cmd.startswith("sa") and cmd[1:].isdigit():
            idx = int(cmd[1:])
            if idx in unseen_map:
                rs, r = unseen_map[idx]
                seen.add(r["id"]); save_seen(seen)
                console.print(f"  [green]✓ Seen → {r['title'][:45]}[/green]  [dim](sinks to bottom next open)[/dim]")
            continue

        # un-see
        if cmd.startswith("un") and cmd[2:].isdigit():
            idx = int(cmd[2:])
            if idx in seen_map:
                rs, r = seen_map[idx]
                seen.discard(r["id"]); save_seen(seen)
                console.print(f"  [green]✓ Un-seen → {r['title'][:45]}[/green]")
            continue

        # remake
        if cmd.startswith("r") and cmd[1:].isdigit():
            idx = int(cmd[1:])
            if idx in unseen_map: log_remake(unseen_map[idx][1])
            continue

        # title mutations
        if cmd.startswith("t") and cmd[1:].isdigit():
            idx = int(cmd[1:])
            if idx in unseen_map: show_title_mutations(unseen_map[idx][1])
            continue

        # open in browser
        if cmd.startswith("open") and cmd[4:].isdigit():
            import webbrowser
            idx = int(cmd[4:])
            if idx in unseen_map:
                vid_id = unseen_map[idx][1]["id"]
                webbrowser.open(f"https://youtube.com/shorts/{vid_id}")
            continue

        # ai generate
        if cmd == "g":
            ai_generate_idea(rows); continue

        # save
        if cmd == "save":
            fname = f"brainstorm_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(f"Brainstorm — {datetime.now().strftime('%Y-%m-%d %H:%M')} | {age_label}\n\n")
                for i, (rs, r) in enumerate(unseen, 1):
                    f.write(
                        f"#{i}  [{rs}/100]  {r['channel']} — {r['title']}\n"
                        f"     Format: {detect_format(r['title'])}\n"
                        f"     Views: {fmt(r['views'])}  Hype: {r['score']:.1f}×  "
                        f"VPD: {fmt(r.get('vpd',0))}  Like%: {r.get('like_ratio',0):.1f}%  "
                        f"Age: {age_str(r.get('published'))}\n"
                        f"     TITLE: {exact_title(r)}\n"
                        f"     HOOK:  {exact_hook(r)}\n"
                        f"     ANGLE: {exact_angle(r)}\n\n"
                    )
            console.print(f"  [green]✓ Saved → {fname}[/green]")
            continue

        console.print(f"  [dim]Unknown: '{cmd}' — try s#, r#, t#, open#, g, save or Enter[/dim]")