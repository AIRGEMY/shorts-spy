# ══════════════════════════════════════════════════════════════
#  config.py  —  THE ONLY FILE YOU NEED TO EDIT
#  Change your API key, your channel, and your competitor list here.
#  Never touch track.py unless you're adding new features.
# ══════════════════════════════════════════════════════════════

# ── YouTube Data API v3 key ────────────────────────────────────
# Get one free at https://console.cloud.google.com/
# Set via environment variable: export YOUTUBE_API_KEY="your_key_here"
# Or paste directly below (never commit a real key to git!)
import os as _os
API_KEY = _os.environ.get("YOUTUBE_API_KEY", "AIzaSyD2G3VWv3AyU1sa1fpOcoAsm0AtJg-cd98")

# ── Your own channel ID (used for benchmarking) ───────────────
YOUR_CHANNEL = "UUjHaiSX0jk8RYKmCvy5LKQg"

# ── Competitor channel IDs ────────────────────────────────────
# Add or remove channel IDs here. Format: "UCxxxxxxxxxxxxxxxx"
# Find a channel's ID: go to their YouTube page → view source → search "channelId"
DEFAULT_CHANNELS = [
    "UUvfOguCxMXoQDzZb3uo4HOA",
    "UUVOXN655jR4YNKZiQEbkGSg",
    "UUIq1M0TimwHS_3DaARKNdrA",
    "UUvr6O63sa9c0eTNsUuh5UGw",
    "UUREUULiZoD-waDletPPCvtw",
    "UUkm6BGcIQj1d3RZ50rqDYxg",
    "UU2lmQdO56zHuqIv1EPCavZQ",
    "UUG81_efih1CaioidNy3H6kA",
    "UUDchcHCx2wsEakgIKZQuJnA",
    "UU7iLvX33nUR6cFvU0V8Pklw",
    "UUPux2PKDpIB2beJZpazB0gQ",
    "UURw9gK-IdQg0J-Ng4F5Y1Lg",
    "UUI5-KgWQ8qVmb6S7ywlABgw",
    "UUvyoMrWm0_h_7NDgVlpCxjA",
    "UU9bLi23xJDO64n523xUgBoQ",
    "UUcJMKr4O33lCHrlfxSQte0g",
    "UUoMTFlBbyx7ld7-XDcranzQ",
    "UUvVefNs55PdT3wclXGXZVWw",
    "UULaORppJNnjwHnvAsQ3Cfjw",
    "UUWqTubqu9z6Gd5ZKSi2o_8Q",
    "UUqsIUFa8l288lSfuymvY69A",
    "UUtyb4sfjNApRKOALMOiXZAA",
    "UUsu0NO3W0fftaYm_xEh4zqA",
    "UUsV_hvVAG3DJioDlm6mCs6A",
    "UUY-k-6V0uS6kC9vWE9VyeiA",
    "UUtmm5_5Frb3y_qdInKw_JzA",
    "UUiIs7oUGbTeeut5A71SlWow",
    "UU9Q3yuL-JVZW38037xq9fNw",
    "UUMnRvgSGunowThEcqnD-veA",
    "UULlMUtaC_IPXD29740q9qfA",
    "UUXRFfkHvcgbOQF_lmSUSGyQ",
    "UUgoi2le6lhgM32c3AO_mfiA",
    "UUQrFGvPdGeqADOJSLkKgqPA",
    "UUrGeWLdH4VZn36TMUS9VDIQ",
    "UUcGpZ8YIm2DlMD00bUXBbJw",
    "UUoUXSrVjIaclxkEdkQgzV4A",
    "UUGHUurB-2aMkGvzFwtOuqAw",
    "UUdX5PargxH_dGcoOs90Z8Ew",
    "UU_ATiITa-Q7Xlpx8cu-mbNA",
    "UUXZEsJtGMXXt4NR6Jj9LwkA",
    "UUPbX9kcq4GK9hwDgMmvwQOg",
    "UUjHaiSX0jk8RYKmCvy5LKQg",  # ← your own channel (included in scans)
]

# ── Scan settings ─────────────────────────────────────────────
VIDEOS_PER_CHANNEL   = 200    # max videos to pull per channel (costs API quota)
TOP_N                = 15     # how many results to show in rankings

# ── Algorithm thresholds ──────────────────────────────────────
HOF_THRESHOLD        = 3.0    # hype score to enter Hall of Fame  (e.g. 3.0 = 3× channel avg)
SPIKE_MIN_GROWTH     = 10_000 # minimum new views to count as a spike
SPIKE_MIN_PCT        = 0.30   # minimum % growth to count as a spike (0.30 = 30%)
MAX_VELOCITY_HISTORY = 10     # how many scan snapshots to keep per video for velocity

# ── Data file names (you can rename these if needed) ──────────
PROFILES_FILE = "spy_profiles.json"
DB_FILE       = "spy_data.json"
HOF_FILE      = "spy_hof.json"
CACHE_FILE    = "spy_cache.json"
PRESETS_FILE  = "spy_presets.json"
CONFIG_FILE   = "spy_config.json"
REMAKE_FILE   = "spy_remakes.json"
NOTES_FILE    = "spy_notes.json"
FREQ_FILE     = "spy_freq.json"

# ── Misc ──────────────────────────────────────────────────────
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
