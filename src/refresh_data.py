# Pulls fresh hiscores + TempleOSRS collection log data for the group, appends a
# snapshot to snapshots.json (replacing an existing snapshot from the same day),
# then rebuilds ../OSRS Toolkit.html.
# Run:  python refresh_data.py
import io, json, os, sys, time, datetime, urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "snapshots.json")
PLAYERS = ["Papa Davo", "GIM DogSauce", "GIM ArchNem"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PapaDavo-toolkit"}

def get_json(url, tries=4):
    """These APIs intermittently 403 or time out; retry before giving up."""
    delay = 1.5
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 400/401/404/410 mean "this will never work" (e.g. a player who isn't on
            # RuneProfile) — retrying just stalls. 403/429/5xx are usually rate limiting.
            if e.code in (400, 401, 404, 410):
                raise
            if attempt == tries:
                raise
            print(f"      retry {attempt}/{tries - 1} after HTTP {e.code}")
            time.sleep(delay)
            delay *= 2
        except Exception as e:
            if attempt == tries:
                raise
            print(f"      retry {attempt}/{tries - 1} after {type(e).__name__}: {e}")
            time.sleep(delay)
            delay *= 2

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
    # Quests come from RuneProfile (nothing else publishes them).
    try:
        rp = get_json(f"https://www.runeprofile.com/api/profiles/{q}")
        quests = rp.get("quests") or []
        if not quests:
            raise ValueError("no quest data")
        p["quests"] = {
            "qp": sum(x["points"] for x in quests if x["state"] == 2),
            "synced": (rp.get("updatedAt") or "")[:10],
            "_raw": {x["name"]: [x["state"], x["type"], x["points"]] for x in quests},
        }
        done = sum(1 for x in quests if x["state"] == 2)
        print(f"    quests: {done}/{len(quests)} done, {p['quests']['qp']} QP "
              f"(RuneProfile, synced {p['quests']['synced']})")
        # Same payload carries diaries and combat achievements.
        # RuneProfile omits any tier with 0 tasks done, so absent == not started.
        diaries = rp.get("achievementDiaryTiers") or []
        if diaries:
            p["diaries"] = {f"{d['area']}|{d['tierName']}":
                            [d["completedCount"], d["tasksCount"]] for d in diaries}
            print(f"    diaries: {sum(d['completedCount'] for d in diaries)}"
                  f"/{sum(d['tasksCount'] for d in diaries)} tasks in {len(diaries)} tiers")
        ca = rp.get("combatAchievementTiers") or []
        if ca:
            p["ca"] = {"points": rp.get("totalCombatAchievementPoints") or 0,
                       "reached": rp.get("combatAchievementTierReached") or 0,
                       "tiers": {t["name"]: [t["completedCount"], t["tasksCount"]] for t in ca}}
            print(f"    combat achievements: {sum(t['completedCount'] for t in ca)}"
                  f"/{sum(t['tasksCount'] for t in ca)} tasks, {p['ca']['points']} pts")
    except Exception:
        print("    quests: not on RuneProfile")
    return p

def fetch_categories():
    """Category metadata: {group: {slug: total_item_count}}, in Temple's display order.
    Rarely changes, so a failure just keeps the copy already on disk."""
    try:
        cats = get_json("https://templeosrs.com/api/collection-log/categories.php")
        meta = {g: {slug: len(ids) for slug, ids in slugs.items()} for g, slugs in cats.items()}
        io.open(os.path.join(HERE, "clog_categories.json"), "w", encoding="utf-8").write(
            json.dumps(meta, separators=(",", ":")))
        print(f"  categories: {sum(len(v) for v in meta.values())} across {len(meta)} groups")
    except Exception as e:
        print(f"  categories: fetch failed ({type(e).__name__}) - keeping existing list")

def pack_quests(players):
    """Quest names/types/points live once in quests_meta.json (append-only so old
    snapshots stay aligned); each player keeps only a state string indexed by it."""
    path = os.path.join(HERE, "quests_meta.json")
    try:
        meta = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        meta = []
    known = {m["n"] for m in meta}
    for p in players.values():
        for qname, (_, qtype, qpts) in (p.get("quests") or {}).get("_raw", {}).items():
            if qname not in known:
                meta.append({"n": qname, "t": qtype, "p": qpts})
                known.add(qname)
    io.open(path, "w", encoding="utf-8").write(json.dumps(meta, separators=(",", ":")))
    for p in players.values():
        q = p.get("quests")
        if not q:
            continue
        raw = q.pop("_raw", None)
        if raw is None:
            continue          # carried forward from a previous snapshot: already packed
        q["state"] = "".join(str(raw.get(m["n"], [0])[0]) for m in meta)
    if meta:
        print(f"  quests: {len(meta)} known quests/miniquests")

def main():
    fetch_categories()
    snaps = json.load(io.open(SNAP, encoding="utf-8"))
    today = datetime.date.today()
    snap = {
        "date": today.isoformat(),
        "label": today.strftime("%#d %b %Y") if os.name == "nt" else today.strftime("%-d %b %Y"),
        "players": {},
    }
    prev = snaps[-1]["players"] if snaps else {}
    stale = []
    for name in PLAYERS:
        try:
            snap["players"][name] = fetch_player(name)
        except Exception as e:
            # Never write a snapshot with a player missing - the page expects all of
            # them. Carry the last known data forward and say so.
            if name not in prev:
                print(f"  {name}: FAILED ({type(e).__name__}) and no previous data - aborting")
                sys.exit(1)
            print(f"  {name}: FAILED ({type(e).__name__}) - carrying previous data forward")
            snap["players"][name] = json.loads(json.dumps(prev[name]))
            stale.append(name)
    pack_quests(snap["players"])
    if stale:
        print(f"  NOTE: {', '.join(stale)} could not be reached; their numbers are unchanged.")
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
