"""
STEP 6: Build the final interest profile - category summaries, lists, and interactive graph.

HOW IT WORKS:
- Reads enriched_final.json (output of Step 5)
- Outputs category breakdown with counts and top members
- Sorted lists of musicians, actors, models, etc. with follower counts
- Builds an interactive HTML graph using PyVis + NetworkX
- Nodes colored by category, sized by follower count
- Edges connect accounts sharing categories

OUTPUT:
- category_summary.txt  (category breakdown with top members)
- interest_graph.html   (interactive browser visualization)
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
import networkx as nx

BASE = Path(__file__).parent

# Color scheme for graph visualization
COLOR_MAP = {
    "Actor": "#e74c3c",
    "Musician": "#8e44ad",
    "Model": "#f39c12",
    "Athlete/Sports": "#2ecc71",
    "Comedian": "#e67e22",
    "Creator/Influencer": "#1abc9c",
    "Director/Filmmaker": "#c0392b",
    "Dancer": "#ec407a",
    "Writer": "#9b59b6",
    "Entrepreneur": "#ff6f00",
    "Artist/Designer": "#f1c40f",
    "Chef/Food": "#e91e63",
    "Photography": "#795548",
    "Politics": "#d35400",
    "Doctor/Health": "#00bcd4",
    "Science/Tech": "#16a085",
    "Education": "#4caf50",
    "Major Celebrity": "#ff0000",
    "Major Creator": "#e040fb",
    "Creator": "#90a4ae",
}


def main():
    input_file = BASE / "enriched_final.json"
    if not input_file.exists():
        print("Error: enriched_final.json not found. Run Step 5 first.")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    print(f"Loaded {len(profiles)} enriched profiles")

    # =========================================================================
    # Category Breakdown
    # =========================================================================
    cat_counts = Counter()
    category_members = defaultdict(list)

    for username, data in profiles.items():
        name = data.get("wd_label", data.get("name", username))
        fc = data.get("follower_count", 0)
        for cat in data.get("categories", []):
            cat_counts[cat] += 1
            category_members[cat].append((name, username, fc))

    print("\n" + "="*60)
    print("INTEREST PROFILE - CATEGORY BREAKDOWN")
    print("="*60)

    output_lines = []
    for cat, count in cat_counts.most_common():
        bar = "=" * min(count, 40)
        output_lines.append(f"\n[{cat}] ({count} accounts)")
        output_lines.append("-" * 40)

        members = sorted(category_members[cat], key=lambda x: -x[2])[:10]
        for name, username, fc in members:
            safe_name = name.encode("ascii", "replace").decode()[:30]
            safe_uname = username[:30]
            output_lines.append(f"  {fc:>12,}  {safe_name:<30} @{safe_uname}")

        print(f"\n[{cat}] ({count} accounts)")
        for name, username, fc in members[:8]:
            safe_name = name.encode("ascii", "replace").decode()[:30]
            print(f"  {fc:>12,}  {safe_name:<30} @{username}")

    # =========================================================================
    # Build Graph
    # =========================================================================
    print(f"\n\nBuilding graph...")
    G = nx.Graph()

    for username, data in profiles.items():
        primary = data.get("primary_category", "Unknown")
        name = data.get("wd_label", data.get("name", username))
        fc = data.get("follower_count", 0)
        G.add_node(username, label=name, category=primary, followers=fc)

    # Create edges between same-category accounts
    cat_users = defaultdict(list)
    for username, data in profiles.items():
        for cat in data.get("categories", []):
            cat_users[cat].append(username)

    for cat, users in cat_users.items():
        for i in range(len(users)):
            for j in range(i + 1, min(i + 5, len(users))):
                if users[i] in G and users[j] in G:
                    G.add_edge(users[i], users[j], weight=1, relation=cat)

    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # =========================================================================
    # PyVis Interactive HTML
    # =========================================================================
    try:
        from pyvis.network import Network

        net = Network(height="900px", width="100%", bgcolor="#1a1a2e", font_color="white", directed=False)
        options = {
            "physics": {
                "barnesHut": {
                    "gravitationalConstant": -3000,
                    "centralGravity": 0.3,
                    "springLength": 150,
                    "springConstant": 0.04,
                },
                "maxVelocity": 30,
                "solver": "barnesHut",
                "stabilization": {"iterations": 200},
            },
            "interaction": {"hover": True, "tooltipDelay": 100, "navigationButtons": True},
        }
        net.set_options(json.dumps(options))

        for node, data in G.nodes(data=True):
            cat = data.get("category", "Unknown")
            color = COLOR_MAP.get(cat, "#95a5a6")
            label = data.get("label", node)
            fc = data.get("followers", 0)
            tooltip = f"<b>{label}</b><br>@{node}<br>{cat}<br>{fc:,} followers"
            size = max(8, min(40, int(fc ** 0.22) + 5)) if fc else 8
            net.add_node(node, label=label[:20], title=tooltip, color=color, size=size)

        for a, b, d in G.edges(data=True):
            net.add_edge(a, b, value=0.3, color="#ffffff30")

        graph_html = BASE / "interest_graph.html"
        net.write_html(str(graph_html))
        print(f"Graph saved to: {graph_html}")

    except ImportError:
        print("PyVis not installed. Run: pip install pyvis")

    # =========================================================================
    # Save summary
    # =========================================================================
    with open(BASE / "category_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
    print(f"Summary saved to: {BASE / 'category_summary.txt'}")

    print("\nDone!")


if __name__ == "__main__":
    main()
