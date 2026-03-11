# 📡 Shorts Spy v4.2

Track competitors, spot trends, and find what's blowing up — all from your terminal.

---

## ⚡ Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/shorts-spy.git
cd shorts-spy

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure (see below)
# Edit config.py

# 4. Run
python track.py
```

---

## ⚙️ Configuration

**You only ever need to edit `config.py`.** Never touch `track.py` unless you're adding new features.

| Setting | What it does |
|---|---|
| `API_KEY` | Your YouTube Data API v3 key ([get one free](https://console.cloud.google.com/)) |
| `YOUR_CHANNEL` | Your channel ID (for benchmarking) |
| `DEFAULT_CHANNELS` | List of competitor channel IDs to track |
| `VIDEOS_PER_CHANNEL` | How many videos to pull per channel (affects API quota) |
| `HOF_THRESHOLD` | Hype score required to enter Hall of Fame |
| `SPIKE_MIN_GROWTH` | Minimum new views to flag as a spike |
| `SPIKE_MIN_PCT` | Minimum % growth to flag as a spike |

### Finding a Channel ID
Go to their YouTube page → right-click → View Page Source → Ctrl+F `"channelId"` → copy the `UCxxxxxxxxxx` value.

---

## 🗂️ File Structure

```
shorts-spy/
├── config.py         ← ✏️  ONLY FILE YOU EDIT
├── main.py           ← entry point  (python main.py to run)
├── state.py          ← shared globals
├── utils.py          ← helpers + file I/O
├── profiles.py       ← multi-niche profile management
├── scan.py           ← YouTube fetching + scan logic
├── data.py           ← build_rows + filters + notes + remakes
├── dashboard.py      ← rankings + channel summary
├── analysis.py       ← title/hashtag/thumbnail/time analysis
├── brainstorm.py     ← top 10 picks + angles + backtest
├── trends.py         ← trend radar
├── freq.py           ← upload frequency tracker
├── benchmarking.py   ← your channel vs competitors
├── web.py            ← HTML dashboard generator
├── settings.py       ← settings menu
├── requirements.txt
├── .gitignore
└── README.md
```

Data files (`spy_*.json`, exports) are created locally and ignored by git.

> **To run:** `python main.py` (not track.py anymore)

---

## 📋 Features

| # | Feature | Description |
|---|---|---|
| 1 | **Scan** | Fetch latest data, detect spikes, update HOF |
| 2 | **Dashboard** | 8 rankings, outliers, spike alerts, notes |
| 3 | **Channels** | Totals, subs, posting time analysis |
| 4 | **Analysis** | Title patterns, hashtags, thumbnail colors, gap finder |
| 5 | **Brainstorm** | Top 10 angles + freshness + backtest + remake log |
| 6 | **Hall of Fame** | All-time viral shorts (never deleted) |
| 7 | **Remake History** | Track what you made and how it performed |
| 14 | **Trend Radar** | Topics blowing up across multiple channels |
| 15 | **Upload Frequency** | Posting cadence, quiet channels, surge detection |
| 16 | **Benchmarking** | Your stats vs every competitor metric |

---

## 🔄 Updating

When a new version of `track.py` is released, just pull it — your `config.py` stays untouched:

```bash
git pull
```

---

## 📦 Dependencies

```
google-api-python-client  — YouTube API
isodate                   — ISO 8601 duration parsing
rich                      — terminal UI
schedule                  — auto-scan timer
requests + Pillow         — thumbnail analysis (optional)
```
