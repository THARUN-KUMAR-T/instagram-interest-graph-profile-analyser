# Instagram Interest Graph

**Build an interest profile from any Instagram account's following list.**

Given a list of accounts someone follows, this pipeline:
1. Classifies them as public/private
2. Gets their follower counts and display names
3. Enriches with Wikidata (occupation, known films/shows/music)
4. Fetches Instagram bios and professional categories
5. Categorizes everything (actor, musician, athlete, chef, etc.)
6. Generates an interactive HTML graph
7. Outputs movie/series watchlists and Spotify playlist prompts

---

## Quick Start

```bash
pip install -r requirements.txt
```

Then run scripts 1 through 7 in order. Each script saves its output and resumes from where it left off.

---

## Prerequisites

### 1. Python 3.9+

### 2. Instagram account that follows the target

You need to follow the account you want to analyze (or be that account).

### 3. Browser cookies (REQUIRED)

You need 3 cookies from an Instagram browser session:

| Cookie | How to get it |
|---|---|
| `sessionid` | Chrome DevTools → Application → Cookies → `instagram.com` → `sessionid` |
| `csrftoken` | Same place → `csrftoken` |
| `ds_user_id` | Same place → `ds_user_id` (your numeric Instagram ID) |

Optional but helpful: `ig_nrcb`, `mid`, `ig_did`

**How to extract cookies:**
1. Log into Instagram in Chrome
2. Press F12 (DevTools) → Application tab → Cookies → instagram.com
3. Copy the `Value` column for each cookie
4. Paste into the `COOKIES` dict in each script

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1          STEP 2          STEP 3          STEP 4         │
│  Fetch           Classify        Scrape          Wikidata       │
│  Following       Public vs       Follower        Enrichment     │
│  List            Private         Counts                         │
│                                                                 │
│  follow.txt  →   public.txt  →   follow_50k  →   enriched_      │
│  3000 names      private.txt     .json           wikidata.json  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5          STEP 6          STEP 7                         │
│  Fetch           Build           Recommendations                │
│  Bios            Profile                                        │
│                                                                 │
│  enriched_   →   category_   →   recommendations.txt            │
│  final.json      summary.txt     (movies + Spotify)             │
│                  interest_                                       │
│                  graph.html                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Instructions

### Step 1: Fetch the Following List

```bash
python 1_fetch_following.py
```

**What it does:** Uses Instagram's private API to paginate through the full following list of the target account. Gets 200 users per page.

**Input:** Nothing (reads `TARGET_USERNAME` from script config)

**Output:** `follow.txt` (one username per line, ~1200-1500 entries)

**Rate limit:** No significant rate limit on this endpoint. Gentle 2.5s delay between pages.

**Before running:** Set `TARGET_USERNAME` in the script and fill in your `COOKIES`.

---

### Step 2: Classify Public vs Private

```bash
python 2_public_private.py
```

**What it does:** Calls Instagram's `web_profile_info` API for each username. Reads `is_private` field.

**Strategy that works:**
- Phase 1: No-cookie requests (works for ~18 calls before rate limit)
- Phase 2: Cookie-authenticated, 15 requests per batch, 8s delay, 90s cooldown

**Input:** `follow.txt`

**Output:** `public.txt`, `private.txt`, `remaining.txt` (unclassified)

---

### Step 3: Scrape Follower Counts

```bash
python 3_scrape_followers.py
```

**What it does:** Visits `instagram.com/{username}/` with your cookies, extracts `og:title` (display name) and `og:description` (follower/following/post counts) from meta tags.

**Key insight:** Web pages have MUCH higher rate limits than the API. 2-second delay works continuously. The `og:title`/`og:description` meta tags are ALWAYS correct for the target profile even when SSR JSON contains the logged-in user's data.

**What DOESN'T work:** Extracting bio from the HTML page — the SSR JSON blocks contain the logged-in user's data, not the target's. Use Step 5 for bios.

**Input:** `public.txt` (or `follow.txt` if no classification done)

**Output:** `follow_data.json`, `follow_50k.json` (accounts above threshold)

**Config:** Set `MIN_FOLLOWERS` to your desired threshold (default: 50,000)

---

### Step 4: Wikidata Enrichment

```bash
python 4_wikidata_enrich.py
```

**What it does:** Searches Wikidata for each account by display name. Tries 6 matching strategies:
1. Exact name match
2. Cleaned name (remove emojis, special chars)
3. First name only (for very famous people with 500K+ followers)
4. Last name + first name (reversed)
5. Username with dots/underscores converted to spaces
6. Relaxed criteria for short names

For matched entities, queries SPARQL for:
- **P106** (occupation) — actor, singer, model, athlete, etc.
- **P800** (notable work) — films, albums, shows
- **P136** (genre) — music genres

**Rate limit:** None. Wikidata API handles rapid requests.

**Input:** `follow_50k.json`

**Output:** `enriched_wikidata.json`

---

### Step 5: Fetch Instagram Bios

```bash
python 5_fetch_bios.py
```

**What it does:** Calls the Instagram `web_profile_info` API WITH cookies for each account. Extracts:
- `biography` — the bio text
- `category_name` — Instagram's professional category (e.g., "Musician/Band", "Actor")
- `business_category_name` — alternative category field
- `is_verified` — blue check
- `external_url` — link in bio

Then re-categorizes using ALL available data (Wikidata + Instagram category + bio keywords).

**Critical rate limit strategy:**
- 15 requests per batch
- 8 seconds between individual requests
- 90 seconds cooldown between batches
- **Saves after EVERY request** (not per batch)
- If you get rate-limited, just re-run the script — it resumes from checkpoint

**What works:** Cookie-authenticated requests (no-cookie mode is instantly rate-limited)

**Input:** `enriched_wikidata.json`

**Output:** `enriched_final.json` (the complete enriched dataset)

---

### Step 6: Build Interest Profile

```bash
python 6_build_profile.py
```

**What it does:** Reads the final enriched data and produces:
- Category breakdown with counts and top members
- Interactive HTML graph (PyVis) — nodes colored by category, sized by followers
- NetworkX graph with community detection

**Input:** `enriched_final.json`

**Output:** `category_summary.txt`, `interest_graph.html`

---

### Step 7: Recommendations

```bash
python 7_recommendations.py
```

**What it does:** Generates:
- **Spotify AI playlist prompt** — clean list of all musicians, ready to paste into Spotify
- **Movies/series watchlist** — filmographies from Wikidata + manual database
- **Connection map** — which actors share projects (Euphoria, Outer Banks, etc.)
- **Priority top 10** — ranked by relevance

**Input:** `enriched_final.json`

**Output:** `recommendations.txt`

---

## What Worked Best

| Technique | Why it works |
|---|---|
| **Web scrape og:meta** | NO rate limit. Fast. og:title/og:description always correct. |
| **Wikidata wbsearchentities** | Fast (~0.2s/search). 6-strategy matching catches most notable people. |
| **Instagram API with cookies** | Gets bios + professional categories. The `category_name` field is the strongest classification signal. |
| **15 req/batch + 90s cooldown** | Sweet spot for cookie-authenticated API. More = rate limit, less = too slow. |
| **Save after EVERY request** | If you get rate-limited mid-batch, no data is lost. Just re-run. |
| **Multiple classification sources** | Wikidata occupations + Instagram category + bio keywords = high accuracy. |

## What Didn't Work

| Technique | Why it failed |
|---|---|
| **No-cookie API calls** | Works for ~18 requests then permanent 401 rate limit. Unusable at scale. |
| **Extracting bio from HTML** | SSR JSON blocks contain the logged-in user's data, not the target's. Only og:meta is reliable. |
| **Large API batches (>20)** | Triggers 429 rate limit. 15 is the max reliable batch size. |
| **Short cooldowns (<60s)** | Rate limit persists. 90s is minimum for reliable reset. |
| **`?__a=1` endpoint** | Instagram blocked this public JSON endpoint. |
| **Wikidata for Indian creators** | Most Indian influencers/content creators are not in Wikidata. Bios fill this gap. |

---

## Output Files

| File | Description |
|---|---|
| `follow.txt` | Complete following list (from Step 1) |
| `public.txt` / `private.txt` | Classification (Step 2) |
| `follow_50k.json` | Accounts above follower threshold with names + counts (Step 3) |
| `enriched_final.json` | Full dataset: Wikidata + bios + categories (Step 5) |
| `category_summary.txt` | Category breakdown with top members (Step 6) |
| `interest_graph.html` | Interactive browser visualization (Step 6) |
| `recommendations.txt` | Movies/series watchlist + Spotify prompt (Step 7) |

---

## Tips for AI-Assisted Replication

If you're using an AI coding assistant (like Cursor, Claude Code, or similar) to run this:

1. **Give the AI your cookies** — paste them into the `COOKIES` dict at the top of each script
2. **Run scripts 1-7 in order** — each depends on the previous one's output
3. **If a script times out**, just re-run it. All scripts resume from checkpoint
4. **The web scrape (Step 3) is the bottleneck** — ~1300 accounts at 2s each = 43 minutes. Let it run.
5. **Step 5 takes longest** — 15 req × 8s + 90s cooldown per batch. ~300 accounts = ~1 hour total
6. **Wikidata enrichment (Step 4) is fast** — no rate limits
7. **You can skip Step 2** if you only care about notable accounts (public accounts with large followings). Jump from Step 1 → Step 3 directly on `follow.txt`.

---

## Customization

- **Follower threshold:** Change `MIN_FOLLOWERS` in `3_scrape_followers.py` (default: 50,000)
- **Target account:** Change `TARGET_USERNAME` in `1_fetch_following.py`
- **Rate limit tuning:** Adjust `BATCH_SIZE`, `REQUEST_DELAY`, `COOLDOWN_SECONDS` in `5_fetch_bios.py`
- **Category colors:** Edit `COLOR_MAP` in `6_build_profile.py`
- **Manual filmographies:** Edit `KNOWN_FILMOGRAPHIES` in `7_recommendations.py`

---

## License

MIT — use it, modify it, share it.
