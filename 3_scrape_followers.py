"""
STEP 3: Web scrape Instagram profile pages for display names and follower counts.

HOW IT WORKS:
- Visits instagram.com/{username}/ with your browser cookies
- Extracts og:title meta tag (contains display name like "Zendaya (@zendaya)")
- Extracts og:description meta tag (contains follower/following/post counts)
- 2-second delay between requests (web pages tolerate this well)
- Filters to accounts above a follower threshold

WHAT WORKED BEST:
- Web pages have MUCH higher rate limits than the API
- og:title and og:description are ALWAYS correct for the target profile
- Even private accounts show these meta tags if you follow them
- 2s delay with no batching needed - runs continuously
- Saves checkpoint every 100 requests

WHAT DOESN'T WORK:
- The SSR JSON in the page contains the LOGGED-IN user's data, not the target's
- So we can't extract bios from HTML - only meta tags are reliable

INPUT:  public.txt (from Step 2) or follow.txt (from Step 1)
OUTPUT: follow_data.json (name, follower_count per username)
        Also saves accounts above threshold to follow_50k.json
"""

import requests
import re
import json
import time
from pathlib import Path

# ============================================================================
# FILL THIS IN: Your Instagram browser session cookies
# ============================================================================
COOKIES = {
    "sessionid": "YOUR_SESSION_ID_HERE",
    "csrftoken": "YOUR_CSRF_TOKEN_HERE",
    "ds_user_id": "YOUR_USER_ID_HERE",
    "ig_nrcb": "1",
    "mid": "YOUR_MID_HERE",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# ============================================================================
# CONFIG: Minimum follower threshold for "notable" accounts
# ============================================================================
MIN_FOLLOWERS = 50_000  # Change to 100_000 if you want fewer, more notable accounts


def parse_og_title(html, username):
    """Extract display name from og:title meta tag."""
    m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
    if not m:
        return username

    title = m.group(1)
    # Remove HTML entities and Instagram formatting
    title = title.replace("&#x2022;", "").replace("&#064;", "@")
    title = title.replace("  Instagram photos and videos", "")
    title = title.replace(" \u2022 Instagram photos and videos", "")

    # Format 1: "Full Name (@username) ..."
    name_match = re.match(r'^(.+?)\s*\(@', title)
    if name_match and name_match.group(1).strip():
        return name_match.group(1).strip()

    # Format 2: "username ..." (no display name set)
    if "\u2022" in title:
        name = title.split("\u2022")[0].strip()
        if name and not name.startswith("(@"):
            return name

    return username


def parse_followers(html):
    """Extract follower count from og:description meta tag."""
    m = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
    if not m:
        return 0

    desc = m.group(1)
    fc_match = re.search(r'([\d.,]+[KMBkmb]?)\s*Followers?', desc)
    if not fc_match:
        return 0

    val = fc_match.group(1).replace(",", "")
    if val.upper().endswith("K"):
        return int(float(val[:-1]) * 1_000)
    elif val.upper().endswith("M"):
        return int(float(val[:-1]) * 1_000_000)
    elif val.upper().endswith("B"):
        return int(float(val[:-1]) * 1_000_000_000)
    return int(float(val))


def main():
    BASE = Path(__file__).parent

    # Read input - use public.txt if available, otherwise follow.txt
    input_file = BASE / "public.txt"
    if not input_file.exists():
        input_file = BASE / "follow.txt"
    with open(input_file, "r", encoding="utf-8") as f:
        usernames = [l.strip() for l in f if l.strip()]

    print(f"Input file: {input_file.name} ({len(usernames)} usernames)")
    print(f"Minimum follower threshold: {MIN_FOLLOWERS:,}")

    # Load checkpoint
    ckpt_path = BASE / "follow_data.json"
    if ckpt_path.exists():
        with open(ckpt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"Resuming from checkpoint: {len(data)} already scraped")
    else:
        data = {}
        print("Starting fresh scrape")

    todo = [u for u in usernames if u not in data]
    print(f"To scrape: {len(todo)}")

    big_accounts = {}
    start = time.time()

    for i, username in enumerate(todo):
        try:
            r = requests.get(
                f"https://www.instagram.com/{username}/",
                headers=HEADERS, cookies=COOKIES, timeout=10
            )

            if r.status_code != 200:
                data[username] = {"error": f"HTTP {r.status_code}", "follower_count": 0}
                continue

            name = parse_og_title(r.text, username)
            fc = parse_followers(r.text)

            data[username] = {
                "name": re.sub(r"&#x[0-9a-fA-F]+;", "", name).strip(),
                "follower_count": fc,
            }

            if fc >= MIN_FOLLOWERS:
                big_accounts[username] = data[username]
                elapsed = time.time() - start
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"[{i+1}/{len(todo)}] BIG: {data[username]['name']} (@{username}) — {fc:,} followers | "
                      f"{len(big_accounts)} found | {rate:.1f} req/s")

        except Exception as e:
            data[username] = {"error": str(e), "follower_count": 0}

        # Checkpoint every 100 requests
        if (i + 1) % 100 == 0:
            with open(ckpt_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  [checkpoint at {i+1}/{len(todo)}]")

        time.sleep(2)  # Gentle delay - web pages handle this well

    # Final save
    with open(ckpt_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    big_file = BASE / "follow_50k.json"
    with open(big_file, "w", encoding="utf-8") as f:
        json.dump(big_accounts, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Scraped: {len(data)} | Big (>={MIN_FOLLOWERS:,}): {len(big_accounts)}")
    print(f"Data saved to: {ckpt_path}")
    print(f"Big accounts saved to: {big_file}")

    # Show top accounts
    if big_accounts:
        print(f"\nTop 20 by followers:")
        sorted_big = sorted(big_accounts.items(), key=lambda x: -x[1]["follower_count"])
        for u, info in sorted_big[:20]:
            safe_name = info["name"].encode("ascii", "replace").decode()
            print(f"  {info['follower_count']:>14,}  {safe_name}  @{u}")


if __name__ == "__main__":
    main()
