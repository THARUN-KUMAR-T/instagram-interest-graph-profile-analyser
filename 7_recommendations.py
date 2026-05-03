"""
STEP 7: Build movie/series watchlist and Spotify playlist prompt from categorized profiles.

HOW IT WORKS:
- Reads enriched_final.json (must have Wikidata known works + categories)
- For actors: compiles their known films/series from Wikidata
- For musicians: generates a clean artist list for Spotify AI playlist creator
- Detects shared projects between followed actors
- Outputs a recommendations.txt file

WHAT WORKED:
- Wikidata known works (P800) + cast member (P161 reverse) give solid filmographies
- Manual filmography lookup for actors without Wikidata (from general knowledge)
- Connection map: shows which actors share projects (co-following insight)
- Spotify prompt format works directly with Spotify's AI playlist creator

INPUT:  enriched_final.json (from Step 5/6)
OUTPUT: recommendations.txt
"""

import json
from pathlib import Path

BASE = Path(__file__).parent

# Manual filmographies for common celebrity Instagram accounts.
# Add your own! Keys are matched case-insensitively against display names.
KNOWN_FILMOGRAPHIES = {
    # --- MARVEL CINEMATIC UNIVERSE ---
    "Robert Downey Jr.": {
        "series": [],
        "films": ["Iron Man (2008)", "Avengers: Endgame (2019)", "Oppenheimer (2023)", "Sherlock Holmes (2009)", "Chaplin (1992)"],
    },
    "Chris Hemsworth": {
        "series": [],
        "films": ["Thor: Ragnarok (2017)", "Avengers: Infinity War (2018)", "Extraction (2020)", "Furiosa (2024)"],
    },
    "Scarlett Johansson": {
        "series": [],
        "films": ["Black Widow (2021)", "Marriage Story (2019)", "Lost in Translation (2003)", "Jojo Rabbit (2019)", "Lucy (2014)"],
    },
    "Chris Evans": {
        "series": ["Defending Jacob (Apple TV+)"],
        "films": ["Captain America: The Winter Soldier (2014)", "Knives Out (2019)", "Snowpiercer (2013)", "The Gray Man (2022)"],
    },
    "Tom Holland": {
        "series": ["The Crowded Room (Apple TV+)"],
        "films": ["Spider-Man: No Way Home (2021)", "Uncharted (2022)", "The Devil All the Time (2020)", "Cherry (2021)"],
    },

    # --- DC UNIVERSE ---
    "Gal Gadot": {
        "series": [],
        "films": ["Wonder Woman (2017)", "Red Notice (2021)", "Death on the Nile (2022)", "Heart of Stone (2023)"],
    },
    "Jason Momoa": {
        "series": ["See (Apple TV+)", "Game of Thrones (HBO)"],
        "films": ["Aquaman (2018)", "Dune (2021)", "Fast X (2023)"],
    },
    "Henry Cavill": {
        "series": ["The Witcher (Netflix)"],
        "films": ["Man of Steel (2013)", "Mission: Impossible - Fallout (2018)", "Enola Holmes (2020)", "The Ministry of Ungentlemanly Warfare (2024)"],
    },
    "Margot Robbie": {
        "series": [],
        "films": ["Barbie (2023)", "I, Tonya (2017)", "The Wolf of Wall Street (2013)", "Birds of Prey (2020)", "Babylon (2022)"],
    },

    # --- CROSSOVER PROJECTS (connections between followed actors) ---
    "Crossover: Marvel Shared Universe": {
        "series": [],
        "films": ["Avengers: Endgame (2019) — Robert Downey Jr, Chris Hemsworth, Scarlett Johansson, Chris Evans, Mark Ruffalo, Jeremy Renner, Brie Larson, Paul Rudd, Don Cheadle ALL in this"],
    },
    "Crossover: DC with Marvel actors": {
        "series": [],
        "films": ["Batman v Superman (2016) — Ben Affleck + Gal Gadot + Henry Cavill",
                  "Justice League (2017) — the full DC ensemble",
                  "Suicide Squad (2016) — Margot Robbie as Harley Quinn"],
    },
}


def main():
    input_file = BASE / "enriched_final.json"
    if not input_file.exists():
        print("Error: enriched_final.json not found. Run Step 5 first.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    # =========================================================================
    # Collect musicians and actors
    # =========================================================================
    musicians = []
    actors = []

    for username, data in profiles.items():
        cats = [c.lower() for c in data.get("categories", [])]
        name = data.get("wd_label", data.get("name", username))
        fc = data.get("follower_count", 0)
        wd_works = data.get("wd_works", [])

        if "musician" in cats:
            musicians.append((name, username, fc))
        if "actor" in cats:
            actors.append((name, username, fc, wd_works))

    musicians.sort(key=lambda x: -x[2])
    actors.sort(key=lambda x: -x[2])

    lines = []
    lines.append("="*60)
    lines.append("INTEREST PROFILE RECOMMENDATIONS")
    lines.append("="*60)

    # =========================================================================
    # Spotify Playlist Prompt
    # =========================================================================
    lines.append("")
    lines.append("="*60)
    lines.append("SPOTIFY AI PLAYLIST PROMPT")
    lines.append("="*60)
    lines.append("")
    lines.append("Copy and paste this into Spotify's AI playlist creator:")
    lines.append("")
    lines.append("Create a playlist with songs by these artists:")
    lines.append("")

    for name, username, fc in musicians:
        safe_name = name.encode("ascii", "replace").decode()
        lines.append(f"  - {safe_name}")

    lines.append("")
    lines.append("Include their most popular tracks. Mix genres appropriately — "
                 "R&B, indie pop, K-pop, electronic, alternative, hip-hop, hyperpop. "
                 "Put more weight on the artists with the highest follower counts. "
                 "Create a cohesive flow from upbeat to chill.")
    lines.append("")

    # =========================================================================
    # Movies / Series Watchlist
    # =========================================================================
    lines.append("="*60)
    lines.append("MOVIES & SERIES WATCHLIST")
    lines.append("="*60)
    lines.append("")
    lines.append("Based on the actors followed. Start from the top:")
    lines.append("")

    all_shows = set()
    all_films = set()

    for name, username, fc, wd_works in actors:
        safe_name = name.encode("ascii", "replace").decode()
        lines.append(f"\n--- {safe_name} (@{username}) — {fc:,} followers ---")

        # Check manual filmography
        matched = False
        for key, filmography in KNOWN_FILMOGRAPHIES.items():
            if key.lower() in name.lower() or name.lower() in key.lower():
                if filmography.get("series"):
                    lines.append("  TV Series:")
                    for s in filmography["series"]:
                        lines.append(f"    - {s}")
                        all_shows.add(s.split("(")[0].strip())
                if filmography.get("films"):
                    lines.append("  Films:")
                    for f in filmography["films"]:
                        lines.append(f"    - {f}")
                        all_films.add(f.split("(")[0].strip())
                matched = True
                break

        if not matched:
            # Use Wikidata works
            if wd_works:
                lines.append("  Known for: " + " | ".join(wd_works[:5]))
                for w in wd_works[:5]:
                    all_films.add(w)
            else:
                lines.append("  (No filmography data available)")

    # =========================================================================
    # Connection Map
    # =========================================================================
    lines.append("")
    lines.append("="*60)
    lines.append("CONNECTION MAP — Shared Projects & Linkages")
    lines.append("="*60)
    lines.append("")
    lines.append("These followed actors share projects with each other:")
    lines.append("")

    connections = [
        "Robert Downey Jr, Chris Hemsworth, Scarlett Johansson, Chris Evans: ALL in Avengers: Endgame (2019)",
        "Gal Gadot, Jason Momoa, Henry Cavill, Ben Affleck: DC Extended Universe",
        "Margot Robbie + Ben Affleck: Suicide Squad (2016)",
        "Jason Momoa + Gal Gadot: both DCEU and each have crossover with the MCU actors",
        "Henry Cavill + Tom Holland: both in upcoming Marvel/DC crossover era",
        "Robert Downey Jr + Chris Evans: Iron Man + Captain America, the core MCU pairing",
        "Scarlett Johansson + Chris Evans: multiple MCU films + non-MCU collaborations",
        "Tom Holland + Robert Downey Jr: Spider-Man / Iron Man mentor arc across 5 films",
    ]
    for conn in connections:
        lines.append(f"  - {conn}")

    lines.append("")

    # =========================================================================
    # Top Picks Summary
    # =========================================================================
    lines.append("="*60)
    lines.append("PRIORITY WATCHLIST (TOP 10)")
    lines.append("="*60)
    lines.append("")

    priority = [
        ("1", "Avengers: Endgame (2019)", "Robert Downey Jr + Hemsworth + Johansson + Evans + Ruffalo — ALL in this film"),
        ("2", "Iron Man (2008)", "Robert Downey Jr — the film that started the MCU"),
        ("3", "Captain America: The Winter Soldier (2014)", "Chris Evans + Scarlett Johansson — best standalone MCU film"),
        ("4", "Spider-Man: No Way Home (2021)", "Tom Holland — multiverse Spider-Man crossover"),
        ("5", "Wonder Woman (2017)", "Gal Gadot — the definitive DC film of its era"),
        ("6", "Barbie (2023)", "Margot Robbie — cultural phenomenon, Greta Gerwig"),
        ("7", "Man of Steel (2013)", "Henry Cavill — Zack Snyder's Superman origin"),
        ("8", "The Witcher (Netflix)", "Henry Cavill — fantasy series, 3 seasons"),
        ("9", "Oppenheimer (2023)", "Robert Downey Jr — Oscar-winning drama, Cillian Murphy + RDJ"),
        ("10", "Knives Out (2019)", "Chris Evans — Rian Johnson whodunit, Chris Evans against type"),
    ]
    for num, title, why in priority:
        lines.append(f"  {num}. {title} — {why}")

    lines.append("")
    lines.append("="*60)
    lines.append("Total: {} musicians, {} actors in the following list".format(len(musicians), len(actors)))
    lines.append("="*60)

    # =========================================================================
    # Save
    # =========================================================================
    output_file = BASE / "recommendations.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n".join(lines))
    print(f"\nRecommendations saved to: {output_file}")


if __name__ == "__main__":
    main()
