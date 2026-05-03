"""
STEP 1: Fetch the full "following" list from any Instagram account you follow.

HOW IT WORKS:
- Uses Instagram's private API to paginate through the following list
- Requires cookies from a browser session where you're logged in
- Gets 200 users per page, no rate limit on this endpoint
- Works even if the target account is private (as long as YOU follow them)

PREREQUISITES:
1. Log into Instagram in your browser
2. Extract cookies (see README for Chrome DevTools method)
3. Fill in the COOKIES dict below

OUTPUT:
- follow.txt: One username per line, complete following list
"""

import requests
import json
import time
from pathlib import Path

# ============================================================================
# FILL THIS IN: Your Instagram browser cookies
# Get these from Chrome DevTools > Application > Cookies > instagram.com
# ============================================================================
COOKIES = {
    "sessionid": "YOUR_SESSION_ID_HERE",           # Required: the main auth cookie
    "csrftoken": "YOUR_CSRF_TOKEN_HERE",            # Required: CSRF protection token
    "ds_user_id": "YOUR_USER_ID_HERE",              # Your Instagram numeric user ID
    # Optional but helpful:
    "ig_nrcb": "1",
    "mid": "YOUR_MID_HERE",
    "ig_did": "YOUR_IG_DID_HERE",
}

# Headers that Instagram expects
HEADERS = {
    "User-Agent": "Instagram 276.0.1 (iPhone14,5; iOS 16_0; en_IN; scale=3.00; 1284x2778)",
    "X-IG-App-ID": "936619743392459",  # Instagram's public web client App ID (not a secret)
    "X-CSRFToken": COOKIES["csrftoken"],
}

# ============================================================================
# CONFIG: Set this to the Instagram username you want to analyze
# ============================================================================
TARGET_USERNAME = "instagram"  # CHANGE THIS to the account you want to analyze


def get_user_id(username):
    """Get the numeric Instagram user ID for any username (no cookies needed)."""
    r = requests.get(
        f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
        headers={"User-Agent": HEADERS["User-Agent"], "X-IG-App-ID": HEADERS["X-IG-App-ID"]},
        timeout=10
    )
    if r.status_code == 200:
        data = r.json()["data"]["user"]
        return data["id"], data.get("edge_follow", {}).get("count", 0)
    else:
        # Fallback: try with cookies
        r2 = requests.get(
            f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers=HEADERS, cookies=COOKIES, timeout=10
        )
        if r2.status_code == 200:
            data = r2.json()["data"]["user"]
            return data["id"], data.get("edge_follow", {}).get("count", 0)
        raise Exception(f"Cannot get user ID. HTTP {r2.status_code}: {r2.text[:200]}")


def fetch_following(username):
    """Paginate through the full following list."""
    print(f"Fetching following list for @{username}...")

    user_id, follow_count = get_user_id(username)
    print(f"  User ID: {user_id}")
    print(f"  Following count: {follow_count}")

    all_users = []
    next_max_id = None
    page = 1

    while True:
        url = f"https://i.instagram.com/api/v1/friendships/{user_id}/following/"
        params = {"count": 200, "search_surface": "follow_list_page"}
        if next_max_id:
            params["max_id"] = next_max_id

        try:
            r = requests.get(url, headers=HEADERS, cookies=COOKIES,
                           params=params, timeout=15)

            if r.status_code == 200:
                data = r.json()
                users = data.get("users", [])
                for u in users:
                    all_users.append(u["username"])

                print(f"  Page {page}: {len(users)} users (total: {len(all_users)})")

                next_max_id = data.get("next_max_id")
                if not next_max_id or len(users) == 0:
                    break
                page += 1
                time.sleep(2.5)  # Gentle delay between pages

            elif r.status_code == 429:
                wait = 60
                print(f"  Rate limited! Waiting {wait}s...")
                time.sleep(wait)
                continue
            else:
                print(f"  HTTP {r.status_code}: {r.text[:200]}")
                break

        except Exception as e:
            print(f"  Error: {e}")
            break

    return all_users


if __name__ == "__main__":
    users = fetch_following(TARGET_USERNAME)

    output_file = Path(__file__).parent / "follow.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(users))

    print(f"\nDone! {len(users)} usernames saved to follow.txt")
