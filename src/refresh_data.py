# Pulls fresh hiscores + TempleOSRS collection log data for the group, appends a
# snapshot to snapshots.json (replacing an existing snapshot from the same day),
# then rebuilds ../OSRS Toolkit.html.
# Run:  python refresh_data.py
import io, json, os, datetime, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "snapshots.json")
PLAYERS = ["Papa Davo", "GIM DogSauce", "GIM ArchNem"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PapaDavo-toolkit"}

def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_player(name):
    q = urllib.parse.quote(name)
    hs = get_json(f"https://secure.runescape.com/m=hiscore_oldschool/index_lite.json?player={q}")
    p = {
        "skills": {s["name"]: [s["level"], s["xp"]] for s in hs["skills"]},
        "activities": {a["name"]: a["score"] for a in hs["activities"] if a["score"] > 0},
    }
    try:
        t = get_json("https://templeosrs.com/api/collection-log/player_collection_log.php"
                     f"?player={q}&categories=all&includenames=1")["data"]
        p["temple"] = {
            "slots": [t["total_collections_finished"], t["total_collections_available"]],
            "ehc": round(float(t.get("ehc", 0)), 1),
            "items": {cat: {i["name"]: i["count"] for i in items}
                      for cat, items in t["items"].items() if items},
        }
        try:
            rec = get_json("https://templeosrs.com/api/collection-log/player_recent_items.php"
                           f"?player={q}")["data"]
            p["temple"]["recent"] = [[i["name"], i["date"][:16], 1 if i.get("notable_item") else 0]
                                     for i in rec[:15]]
        except Exception:
            p["temple"]["recent"] = []   # nothing unlocked since initial sync yet
        print(f"  {name}: hiscores OK, collection log OK "
              f"({t['total_collections_finished']}/{t['total_collections_available']} slots, "
              f"{len(p['temple']['recent'])} recent unlocks)")
    except Exception as e:
        print(f"  {name}: hiscores OK, collection log not synced ({e})")
    return p

def fetch_categories():
    """Category metadata: {group: {slug: total_item_count}}, in Temple's display order."""
    cats = get_json("https://templeosrs.com/api/collection-log/categories.php")
    meta = {g: {slug: len(ids) for slug, ids in slugs.items()} for g, slugs in cats.items()}
    io.open(os.path.join(HERE, "clog_categories.json"), "w", encoding="utf-8").write(
        json.dumps(meta, separators=(",", ":")))
    print(f"  categories: {sum(len(v) for v in meta.values())} across {len(meta)} groups")

def main():
    fetch_categories()
    snaps = json.load(io.open(SNAP, encoding="utf-8"))
    today = datetime.date.today()
    snap = {
        "date": today.isoformat(),
        "label": today.strftime("%#d %b %Y") if os.name == "nt" else today.strftime("%-d %b %Y"),
        "players": {},
    }
    for name in PLAYERS:
        snap["players"][name] = fetch_player(name)
    if snaps and snaps[-1]["date"] == snap["date"]:
        print("replacing existing snapshot for", snap["date"])
        snaps[-1] = snap
    else:
        snaps.append(snap)
    io.open(SNAP, "w", encoding="utf-8").write(json.dumps(snaps, separators=(",", ":")))
    print(f"snapshots.json now holds {len(snaps)} snapshot(s)")
    import build_toolkit
    build_toolkit.main()

if __name__ == "__main__":
    main()
