"""
STEP 2: Classify accounts as public or private using Instagram's profile API.

HOW IT WORKS:
- Calls the web_profile_info endpoint for each username
- Reads is_private from the response
- Uses NO cookies first (works for ~20 requests)
- Falls back to cookie-authenticated requests (15 per batch, 90s cooldown)
- Checkpoints to public.txt and private.txt as it goes

WHAT WORKED:
- No-cookie mode: works for ~20 requests before rate limit. 
  After that, switch to cookie mode. Cookies allow ~15 requests per batch.
- The API returns is_private even for accounts you follow.
- Saving after every batch prevents data loss if rate-limited.

INPUT:  follow.txt (from Step 1)
OUTPUT: public.txt, private.txt, remaining.txt
"""

import requests
import json
import time
from pathlib import Path

# ============================================================================
# FILL THIS IN: Your Instagram session cookies
# ============================================================================
COOKIES = {
    "sessionid": "YOUR_SESSION_ID_HERE",
    "csrftoken": "YOUR_CSRF_TOKEN_HERE",
    "ds_user_id": "YOUR_USER_ID_HERE",
    "ig_nrcb": "1",
    "mid": "YOUR_MID_HERE",
    "ig_did": "YOUR_IG_DID_HERE",
}

HEADERS_NOAUTH = {
    "User-Agent": "Instagram 276.0.1 (iPhone14,5; iOS 16_0)",
    "X-IG-App-ID": "936619743392459",  # Instagram's public web client App ID (not a secret)
}

HEADERS_AUTH = {
    **HEADERS_NOAUTH,
    "X-CSRFToken": COOKIES["csrftoken"],
}


def read_usernames(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def main():
    BASE = Path(__file__).parent
    usernames = read_usernames(BASE / "follow.txt")
    print(f"Accounts to classify: {len(usernames)}")

    # Load existing results (resume support)
    public = read_usernames(BASE / "public.txt") if (BASE / "public.txt").exists() else []
    private = read_usernames(BASE / "private.txt") if (BASE / "private.txt").exists() else []
    done = set(public) | set(private)
    remaining = [u for u in usernames if u not in done]

    # Load checkpoint
    ckpt_path = BASE / "classification_ckpt.json"
    if ckpt_path.exists():
        with open(ckpt_path) as f:
            ckpt = json.load(f)
    else:
        ckpt = {"public": list(public), "private": list(private), "errors": []}

    already_checked = set(ckpt["public"]) | set(ckpt["private"]) | set(ckpt["errors"])
    todo = [u for u in remaining if u not in already_checked]
    print(f"Already classified: {len(done)} | To do: {len(todo)}")

    if not todo:
        print("All done!")
        return

    # Phase 1: Try no-cookie requests (works for ~20 calls)
    NOCOOKIE_LIMIT = 18
    for i, username in enumerate(todo[:NOCOOKIE_LIMIT]):
        try:
            r = requests.get(
                f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                headers=HEADERS_NOAUTH, timeout=10)
            if r.status_code == 200:
                is_private = r.json()["data"]["user"]["is_private"]
                if is_private:
                    ckpt["private"].append(username)
                    print(f" [{i+1}] {username}: PRIVATE")
                else:
                    ckpt["public"].append(username)
                    print(f" [{i+1}] {username}: PUBLIC")
            elif r.status_code == 429:
                print(f" [{i+1}] Rate limit hit at {username}, switching to cookie mode...")
                break
            else:
                ckpt["errors"].append(username)
        except Exception as e:
            ckpt["errors"].append(username)
            print(f" [{i+1}] {username}: ERROR {e}")
        time.sleep(3)

    # Phase 2: Cookie-authenticated requests (15/batch, 90s cooldown)
    still_todo = [u for u in todo if u not in set(ckpt["public"]) | set(ckpt["private"]) | set(ckpt["errors"])]
    BATCH = 15

    for bi in range(0, len(still_todo), BATCH):
        batch = still_todo[bi:bi+BATCH]
        print(f"\nBatch {bi//BATCH + 1}: {len(batch)} accounts")

        for username in batch:
            try:
                r = requests.get(
                    f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                    headers=HEADERS_AUTH, cookies=COOKIES, timeout=10)
                if r.status_code == 200:
                    is_private = r.json()["data"]["user"]["is_private"]
                    fc = r.json()["data"]["user"].get("edge_followed_by", {}).get("count", 0)
                    if is_private:
                        ckpt["private"].append(username)
                        tag = "PRIVATE"
                    else:
                        ckpt["public"].append(username)
                        tag = "PUBLIC"
                    print(f"  {username}: {tag} ({fc:,} followers)")
                elif r.status_code == 429:
                    ckpt["errors"].append(username)
                    print(f"  {username}: RATE LIMITED, breaking batch")
                    break
                else:
                    ckpt["errors"].append(username)
                    print(f"  {username}: HTTP {r.status_code}")
            except Exception as e:
                ckpt["errors"].append(username)
                print(f"  {username}: ERROR {e}")
            time.sleep(8)

        # Save checkpoint + files after each batch
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, indent=2, ensure_ascii=False)
        with open(BASE / "public.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(set(ckpt["public"]))))
        with open(BASE / "private.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(set(ckpt["private"]))))

        if bi + BATCH < len(still_todo):
            print("  [cooldown 90s]")
            time.sleep(90)

    # Save unclassified
    unclassified = [u for u in todo if u not in set(ckpt["public"]) | set(ckpt["private"]) | set(ckpt["errors"])]
    if unclassified:
        with open(BASE / "remaining.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(unclassified))

    print(f"\nDone! Public: {len(ckpt['public'])} | Private: {len(ckpt['private'])} | Unclassified: {len(unclassified)}")


if __name__ == "__main__":
    main()
