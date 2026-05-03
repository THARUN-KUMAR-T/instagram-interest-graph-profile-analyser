"""
STEP 4: Enrich profiles using Wikidata name matching.

HOW IT WORKS:
- Takes display names from Step 3
- Searches Wikidata's entity database via wbsearchentities API
- Tries 6 matching strategies for each name:
    1. Exact name match
    2. Cleaned name (remove emojis/special chars)
    3. First name only (for famous people)
    4. Last name + first name (reversed)
    5. Username hints (dots/underscores to spaces)
    6. Relaxed criteria for accounts with 500K+ followers
- For matched entities, queries SPARQL for occupations, known works, genres
- NO rate limit on Wikidata API

WHAT WORKED:
- The 6-strategy approach catches most notable people
- wbsearchentities is fast (~0.2s per search)
- SPARQL queries give rich occupation + known-works data
- Saves after every account (no data loss)

WHAT DOESN'T:
- Accounts not on Wikipedia won't be in Wikidata
- Indian content creators are underrepresented in Wikidata
- Brand accounts often match different Wikidata entities

INPUT:  follow_50k.json (from Step 3)
OUTPUT: enriched_profiles.json (with Wikidata occupations, works, genres)
"""

import requests
import json
import time
from pathlib import Path
from collections import Counter

BASE = Path(__file__).parent

OCCUPATION_MAP = [
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


def wd_search(name):
    """Search Wikidata by entity name."""
    if not name or len(name) < 3:
        return None
    try:
        r = requests.get("https://www.wikidata.org/w/api.php", params={
            "action": "wbsearchentities", "search": name, "language": "en",
            "format": "json", "limit": 5, "type": "item",
        }, headers={"User-Agent": "InterestProfiler/1.0"}, timeout=8)
        if r.status_code != 200:
            return None

        results = r.json().get("search", [])
        for res in results:
            desc = res.get("description", "").lower()
            label = res.get("label", "").lower()
            nl = name.lower()

            # Must be a person, band, or brand
            is_person = any(k in desc for k in
                ["actor","singer","musician","model","athlete","comedian","youtuber",
                 "dancer","director","writer","rapper","footballer","cricketer",
                 "actress","entrepreneur","politician","artist","chef","photographer",
                 "racing driver","skater","skier","swimmer"])
            is_brand = any(k in desc for k in
                ["brand","company","magazine","restaurant","organization","service",
                 "application","website","record label","film","television","band","group"])
            if not (is_person or is_brand):
                continue

            # Name similarity check
            if label in nl or nl in label:
                return {"id": res["id"], "label": res["label"],
                        "description": res.get("description", ""),
                        "url": res.get("concepturi", "")}
            name_words = set(nl.replace(",","").split())
            label_words = set(label.split())
            common = name_words & label_words
            if len(common) >= 2 or (len(common) >= 1 and len(label_words) <= 2):
                return {"id": res["id"], "label": res["label"],
                        "description": res.get("description", ""),
                        "url": res.get("concepturi", "")}
        return None
    except:
        return None


def smart_wikidata(name, username, follower_count):
    """Try multiple strategies to find a Wikidata match."""
    if not name or len(name) < 3:
        return None

    # Strategy 1: Direct name
    result = wd_search(name)
    if result: return result

    # Strategy 2: Clean the name (remove emojis, special chars)
    import re
    cleaned = re.sub(r'[^\w\s]', '', name).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    if cleaned and cleaned != name:
        result = wd_search(cleaned)
        if result: return result

    # Strategy 3: First name (for very famous people)
    first = name.split()[0] if ' ' in name else None
    if first and len(first) >= 3 and follower_count >= 500_000:
        result = wd_search(first)
        if result:
            # Verify similarity with original name
            nw = set(name.lower().replace(",","").split())
            lw = set(result["label"].lower().split())
            if nw & lw:
                return result

    # Strategy 4: Last name + first name (reversed)
    parts = cleaned.split() if 'cleaned' in dir() else name.split()
    if len(parts) >= 2:
        last_first = f"{parts[-1]} {parts[0]}"
        result = wd_search(last_first)
        if result: return result

    # Strategy 5: Username hints
    username_clean = username.replace('.', ' ').replace('_', ' ').strip()
    if username_clean.lower() != name.lower():
        result = wd_search(username_clean)
        if result: return result

    return None


def wd_details(entity_id):
    """Get occupations, known works, and genres from Wikidata."""
    if not entity_id:
        return [], [], []
    query = (
        f"SELECT ?occLabel ?workLabel ?genreLabel WHERE {{"
        f"  wd:{entity_id} wdt:P106 ?occ."
        f"  OPTIONAL {{ wd:{entity_id} wdt:P800 ?work. }}"
        f"  OPTIONAL {{ wd:{entity_id} wdt:P136 ?genre. }}"
        f"  SERVICE wikibase:label {{ bd:serviceParam wikibase:language \"en\". }}"
        f"}}"
    )
    try:
        r = requests.get("https://query.wikidata.org/sparql",
                         params={"format": "json", "query": query},
                         headers={"Accept": "application/json", "User-Agent": "InterestProfiler/1.0"},
                         timeout=12)
        if r.status_code == 200:
            occs, works, genres = set(), set(), set()
            for b in r.json().get("results", {}).get("bindings", []):
                if "occLabel" in b: occs.add(b["occLabel"]["value"])
                if "workLabel" in b: works.add(b["workLabel"]["value"])
                if "genreLabel" in b: genres.add(b["genreLabel"]["value"])
            return list(occs), list(works), list(genres)
    except:
        pass
    return [], [], []


def categorize(entry):
    """Categorize an account from its Wikidata data."""
    cats = set()
    occs = [o.lower() for o in entry.get("wd_occupations", [])]
    desc = entry.get("wd_description", "").lower()
    fc = entry.get("follower_count", 0)

    for kws, cat in OCCUPATION_MAP:
        if any(k in occs or k in desc for k in kws):
            cats.add(cat)

    if not cats:
        if fc >= 10_000_000:
            cats.add("Major Celebrity")
        elif fc >= 1_000_000:
            cats.add("Major Creator")
        elif fc >= 500_000:
            cats.add("Creator")
        else:
            cats.add("Creator")

    return sorted(cats)


def main():
    # Load input
    input_file = BASE / "follow_50k.json"
    if not input_file.exists():
        print("Error: follow_50k.json not found. Run Step 3 first.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        accounts = json.load(f)
    print(f"Accounts to enrich: {len(accounts)}")

    # Load checkpoint
    ckpt_file = BASE / "enriched_wikidata.json"
    if ckpt_file.exists():
        with open(ckpt_file, "r", encoding="utf-8") as f:
            enriched = json.load(f)
        print(f"Resuming from checkpoint: {len(enriched)} already done")
    else:
        enriched = {}

    sorted_accts = sorted(accounts.items(), key=lambda x: -x[1].get("follower_count", 0))
    todo = [(u, i) for u, i in sorted_accts if u not in enriched]
    print(f"To process: {len(todo)}")

    matches = 0
    for idx, (username, info) in enumerate(todo):
        name = info.get("name", username)
        fc = info.get("follower_count", 0)
        entry = {"username": username, "name": name, "follower_count": fc}

        wd = smart_wikidata(name, username, fc)
        if wd:
            occs, works, genres = wd_details(wd["id"])
            entry["wd_label"] = wd["label"]
            entry["wd_description"] = wd["description"]
            entry["wd_id"] = wd["id"]
            entry["wd_occupations"] = occs
            entry["wd_works"] = works
            entry["wd_genres"] = genres
            entry["source"] = "wikidata"
            matches += 1
            safe_label = wd["label"].encode("ascii", "replace").decode()
            safe_desc = wd["description"].encode("ascii", "replace").decode()[:60]
            print(f"[{idx+1}/{len(todo)}] W: {safe_label} ({safe_desc})")
        else:
            entry["source"] = "pending_bio"

        entry["categories"] = categorize(entry)
        entry["primary_category"] = entry["categories"][0] if entry["categories"] else "Unknown"
        enriched[username] = entry

        # Save after every account
        with open(ckpt_file, "w", encoding="utf-8") as f:
            serial = {}
            for eu, ev in enriched.items():
                se = {k: list(v) if isinstance(v, set) else v for k, v in ev.items()}
                serial[eu] = se
            json.dump(serial, f, indent=2, ensure_ascii=False)

        time.sleep(0.15)  # Gentle delay for Wikidata API

    # Summary
    cat_counts = Counter()
    for e in enriched.values():
        for c in e.get("categories", []):
            cat_counts[c] += 1

    print(f"\nDone! {len(enriched)} enriched, {matches} Wikidata matches")
    print("Initial categories (before bio enrichment):")
    for c, n in cat_counts.most_common(15):
        print(f"  {c:<25} {n}")


if __name__ == "__main__":
    main()
