"""
STEP 5: Fetch Instagram bios, category_name, and business_category_name via API.

HOW IT WORKS:
- Uses the web_profile_info API with browser cookies
- Extracts: biography, category_name, business_category_name, is_verified, external_url
- Batched: 15 requests per batch, 8-second delay between requests, 90-second cooldown
- Saves after EVERY request (no data loss if rate-limited)
- Re-categorizes accounts with the new bio + category data

WHAT WORKED:
- Cookies must be fresh (sessionid + csrftoken from a recent browser login)
- 15 requests per batch is the sweet spot (more = rate limit)
- 90-second cooldown between batches reliably resets rate limit
- The category_name field from Instagram is the STRONGEST signal
  (e.g., "Musician/Band", "Actor", "Chef", "Digital Creator")

WHAT DOESN'T:
- No-cookie mode: INSTANTLY rate limited (don't bother)
- Larger batches: >20 requests triggers 429 rate limit
- Shorter cooldowns: <60 seconds doesn't clear the rate limit

INPUT:  enriched_wikidata.json (from Step 4)
OUTPUT: enriched_bios.json (adds bio, category_name, is_verified)
"""

import requests
import json
import time
from collections import Counter
from pathlib import Path

# ============================================================================
# FILL THIS IN: Your Instagram cookies
# ============================================================================
COOKIES = {
    "sessionid": "YOUR_SESSION_ID_HERE",
    "csrftoken": "YOUR_CSRF_TOKEN_HERE",
    "ds_user_id": "YOUR_USER_ID_HERE",
    "ig_did": "YOUR_IG_DID_HERE",
    "ig_nrcb": "1",
    "mid": "YOUR_MID_HERE",
}
HEADERS = {
    "User-Agent": "Instagram 276.0.1 (iPhone14,5; iOS 16_0; en_IN; scale=3.00; 1284x2778)",
    "X-IG-App-ID": "936619743392459",  # Instagram's public web client App ID (not a secret)
    "X-CSRFToken": COOKIES["csrftoken"],
}

# ============================================================================
# RATE LIMIT CONFIG
# ============================================================================
BATCH_SIZE = 15          # Requests per batch
REQUEST_DELAY = 8        # Seconds between individual requests
COOLDOWN_SECONDS = 90    # Seconds between batches

BASE = Path(__file__).parent


OCC_MAP = [
    (["actor","actress","film actor","television actor","voice actor","stage actor","theatre actor"], "Actor"),
    (["singer","musician","rapper","singer-songwriter","dj","music producer","composer","songwriter",
      "guitarist","drummer","pianist","bassist","vocalist","lyricist","record producer"], "Musician"),
    (["model","fashion model","supermodel","runway model","glamour model","spokesmodel"], "Model"),
    (["athlete","sportsperson","footballer","cricketer","basketball player","tennis player",
      "racing driver","figure skater","skier","swimmer","olympic","sports"], "Athlete/Sports"),
    (["comedian","stand-up comedian","humorist","comic"], "Comedian"),
    (["youtuber","content creator","vlogger","tiktoker","influencer","streamer","internet celebrity",
      "digital creator","blogger","online streamer"], "Creator/Influencer"),
    (["film director","director","screenwriter","cinematographer","filmmaker","film producer"], "Director/Filmmaker"),
    (["dancer","choreographer","ballet dancer","dance teacher","hip hop dancer"], "Dancer"),
    (["writer","author","poet","journalist","novelist","columnist"], "Writer"),
    (["entrepreneur","businessperson","ceo","founder","business executive","business owner"], "Entrepreneur"),
    (["artist","painter","designer","illustrator","graphic designer","fashion designer",
      "potter","ceramist","visual artist","tattoo artist"], "Artist/Designer"),
    (["chef","cook","food","restaurateur","baker","pastry chef","food blogger"], "Chef/Food"),
    (["photographer","photojournalist","videographer","cinematographer"], "Photography"),
    (["politician","activist","political party","political commentator"], "Politics"),
    (["physician","doctor","surgeon","therapist","nurse","dermatologist","psychologist"], "Doctor/Health"),
    (["engineer","scientist","researcher","mathematician","physicist","software engineer","developer"], "Science/Tech"),
    (["teacher","educator","professor","lecturer","academic"], "Education"),
]

INSTAGRAM_CATEGORY_MAP = {
    "musician/band": "Musician", "actor": "Actor", "model": "Model",
    "athlete": "Athlete/Sports", "comedian": "Comedian", "dancer": "Dancer",
    "chef": "Chef/Food", "artist": "Artist/Designer", "photographer": "Photography",
    "writer": "Writer", "entrepreneur": "Entrepreneur", "politician": "Politics",
    "doctor": "Doctor/Health", "scientist": "Science/Tech",
    "education": "Education", "food": "Chef/Food", "fashion": "Model",
    "beauty": "Creator/Influencer", "gaming": "Creator/Influencer",
    "sports": "Athlete/Sports", "racing driver": "Athlete/Sports",
    "journalist": "Writer", "designer": "Artist/Designer",
}


def classify(entry):
    """Classify from Wikidata + Instagram bio + category_name."""
    cats = set()

    # Wikidata occupations
    wd_occs = [o.lower() for o in entry.get("wd_occupations", [])]
    wd_desc = entry.get("wd_description", "").lower()
    for kws, cat in OCC_MAP:
        if any(k in wd_occs or k in wd_desc for k in kws):
            cats.add(cat)

    # Instagram category (strongest signal)
    ig_cat = (entry.get("category_name", "") + " " + entry.get("business_category_name", "")).lower()
    for kw, cat in INSTAGRAM_CATEGORY_MAP.items():
        if kw in ig_cat:
            cats.add(cat)

    # Bio keyword analysis
    bio = entry.get("bio", "").lower()
    bio_rules = [
        (["actor","actress","acting","film director","theatre","casting"], "Actor"),
        (["singer","musician","music","rapper","song","band","album","dj","producer","composer","spotify","soundcloud"], "Musician"),
        (["model","modeling","runway","fashion model"], "Model"),
        (["dancer","dance","choreographer","ballet","dance teacher"], "Dancer"),
        (["comedian","comedy","standup","stand up","jokes","improv"], "Comedian"),
        (["chef","cook","food","recipe","restaurant","cuisine","baker","kitchen"], "Chef/Food"),
        (["f1","formula 1","racing","driver","motorsport","grand prix"], "Athlete/Sports"),
        (["fitness","gym","workout","trainer","yoga","pilates","coach","bodybuilding"], "Athlete/Sports"),
        (["football","cricket","tennis","basketball","athlete","olympic","swim","skating"], "Athlete/Sports"),
        (["youtube","youtuber","vlogger","content creator","tiktok","influencer","streamer"], "Creator/Influencer"),
        (["artist","painting","drawing","illustrator","designer","potter","ceramic","tattoo"], "Artist/Designer"),
        (["photographer","photography","cinematographer","videographer","visuals"], "Photography"),
        (["writer","author","poet","poetry","journalist","blogger","writing"], "Writer"),
        (["entrepreneur","founder","ceo","startup","business","brand","shop"], "Entrepreneur"),
        (["doctor","medical","health","surgeon","dermatologist","skin","clinic","therapy"], "Doctor/Health"),
        (["fashion","style","outfit","beauty","makeup","skincare","hair stylist","cosmetics"], "Creator/Influencer"),
        (["meme","memes","funny","shitpost","viral","lol","humor","satire"], "Creator/Influencer"),
        (["travel","traveller","explore","wanderlust","adventure","backpack"], "Creator/Influencer"),
        (["gamer","gaming","esports","twitch","stream","discord"], "Creator/Influencer"),
        (["political","politics","activist","palestine","news","media"], "Politics"),
        (["engineer","software","developer","coding","tech","data","ml","ai","programmer"], "Science/Tech"),
        (["student","college","university","iit","nit","bits","phd","study"], "Science/Tech"),
    ]
    for kws, cat in bio_rules:
        if any(k in bio for k in kws):
            cats.add(cat)

    # Fallback: follower count signals
    fc = entry.get("follower_count", 0)
    if not cats:
        if fc >= 10_000_000: cats.add("Major Celebrity")
        elif fc >= 1_000_000: cats.add("Major Creator")
        elif fc >= 500_000: cats.add("Creator")
        else: cats.add("Creator")

    return sorted(cats)


def main():
    # Load input
    input_file = BASE / "enriched_wikidata.json"
    if not input_file.exists():
        print("Error: enriched_wikidata.json not found. Run Step 4 first.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        enriched = json.load(f)
    print(f"Accounts to enrich with bios: {len(enriched)}")

    # Load bio checkpoint
    bio_ckpt = BASE / "enriched_bios.json"
    if bio_ckpt.exists():
        with open(bio_ckpt, "r", encoding="utf-8") as f:
            bios_done = json.load(f)
    else:
        bios_done = {}

    sorted_accts = sorted(enriched.items(), key=lambda x: -x[1].get("follower_count", 0))
    todo = [(u, e) for u, e in sorted_accts if u not in bios_done]
    print(f"Already fetched: {len(bios_done)} | Remaining: {len(todo)}")

    if not todo:
        print("All bios already fetched!")
        return

    batches = [todo[i:i+BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    print(f"Batches: {len(batches)} of max {BATCH_SIZE}")

    for bi, batch in enumerate(batches):
        print(f"\n=== BATCH {bi+1}/{len(batches)} ({len(batch)}) ===")
        rate_limited = False

        for username, entry in batch:
            try:
                r = requests.get(
                    f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
                    headers=HEADERS, cookies=COOKIES, timeout=12)

                if r.status_code == 200:
                    j = r.json()
                    du = j["data"]["user"]
                    bio = du.get("biography", "")
                    cat_name = du.get("category_name", "") or ""
                    biz_cat = du.get("business_category_name", "") or ""
                    is_ver = du.get("is_verified", False)
                    ext_url = du.get("external_url", "") or ""

                    bios_done[username] = {
                        "bio": bio,
                        "category_name": cat_name,
                        "business_category_name": biz_cat,
                        "is_verified": is_ver,
                        "external_url": ext_url,
                    }

                    # Merge into enriched data
                    enriched[username]["bio"] = bio
                    enriched[username]["category_name"] = cat_name
                    enriched[username]["business_category_name"] = biz_cat
                    enriched[username]["is_verified"] = is_ver
                    enriched[username]["external_url"] = ext_url
                    enriched[username]["categories"] = classify(enriched[username])
                    enriched[username]["primary_category"] = enriched[username]["categories"][0]

                    cats = enriched[username].get("categories", [])
                    safe_name = enriched[username].get("wd_label", entry.get("name", username))
                    safe_name = safe_name.encode("ascii", "replace").decode()[:30]
                    safe_bio = bio[:50].encode("ascii", "replace").decode()
                    vtag = "V" if is_ver else " "
                    print(f"  +{vtag} {username:<30} {','.join(cats[:3]):<35} '{safe_bio}'")

                elif r.status_code == 429:
                    rate_limited = True
                    print(f"  RATE LIMIT at {username} - breaking batch")
                    break
                else:
                    print(f"  HTTP {r.status_code}: {username}")

            except Exception as e:
                print(f"  ERR {username}: {str(e)[:40]}")

            # Save after EVERY request
            with open(bio_ckpt, "w", encoding="utf-8") as f:
                json.dump(bios_done, f, indent=2, ensure_ascii=False)

            # Also save enriched data
            enriched_ckpt = BASE / "enriched_final.json"
            with open(enriched_ckpt, "w", encoding="utf-8") as f:
                serial = {}
                for eu, ev in enriched.items():
                    se = {k: list(v) if isinstance(v, set) else v for k, v in ev.items()}
                    serial[eu] = se
                json.dump(serial, f, indent=2, ensure_ascii=False)

            time.sleep(REQUEST_DELAY)

        # Cooldown between batches
        if bi < len(batches) - 1 and not rate_limited:
            print(f"  [cooldown {COOLDOWN_SECONDS}s...]")
            time.sleep(COOLDOWN_SECONDS)

    # Final summary
    cat_counts = Counter()
    for e in enriched.values():
        for c in e.get("categories", []):
            cat_counts[c] += 1

    bios_count = sum(1 for v in bios_done.values() if "bio" in v)
    print(f"\n{'='*60}")
    print(f"Done! Bios fetched: {bios_count}/{len(enriched)}")
    print(f"{'='*60}")
    print("Final Category Breakdown:")
    for c, n in cat_counts.most_common(25):
        print(f"  {c:<25} {n:>3}")

    # Save final enriched
    final_path = BASE / "enriched_final.json"
    with open(final_path, "w", encoding="utf-8") as f:
        serial = {}
        for eu, ev in enriched.items():
            se = {k: list(v) if isinstance(v, set) else v for k, v in ev.items()}
            serial[eu] = se
        json.dump(serial, f, indent=2, ensure_ascii=False)
    print(f"\nFinal data saved to: {final_path}")


if __name__ == "__main__":
    main()
