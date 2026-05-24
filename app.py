from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os, glob, json, sqlite3

app = Flask(__name__)

# ✅ Only allow API access from your GitHub Pages site
CORS(app, origins=[
    "https://mklbasist.github.io",
    "https://streamxcric.vercel.app",
])

# Folders/paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "test_matches")
DB_PATH = os.path.join(BASE_DIR, "matches.db")


# ---------- DB BUILD (runs once on boot) ----------
def build_db_if_missing():
    if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0:
        print(f"[DB] Using existing DB: {DB_PATH}")
        return

    print(f"[DB] Building SQLite DB at: {DB_PATH}")
    print(f"[DB] Reading JSON from: {DATA_DIR}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("PRAGMA temp_store = MEMORY;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS deliveries (
        match_id     TEXT,
        inning       INTEGER,
        over         INTEGER,
        ball         INTEGER,
        batter       TEXT,
        bowler       TEXT,
        runs         INTEGER,
        wicket_kind  TEXT
    )
    """)

    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    print(f"[DB] Found {len(files)} JSON files.")

    insert_sql = "INSERT INTO deliveries VALUES (?,?,?,?,?,?,?,?)"
    batch, batch_size, total_rows = [], 2000, 0

    for idx, path in enumerate(files, start=1):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[DB] Skipping {path}: {e}")
            continue

        match_id = (data.get("meta", {}) or {}).get("match", os.path.basename(path))

        for inning_idx, innings in enumerate(data.get("innings", []), start=1):
            for over in innings.get("overs", []):
                over_no = over.get("over")
                for ball_idx, delivery in enumerate(over.get("deliveries", []), start=1):
                    batter = delivery.get("batter")
                    bowler = delivery.get("bowler")
                    runs = (delivery.get("runs", {}) or {}).get("batter", 0)

                    wicket_kind = None
                    if "wickets" in delivery:
                        for w in delivery["wickets"]:
                            if w.get("kind") != "run out":
                                wicket_kind = w.get("kind")
                                break

                    batch.append((match_id, inning_idx, over_no, ball_idx,
                                  batter, bowler, runs, wicket_kind))

                    if len(batch) >= batch_size:
                        cur.executemany(insert_sql, batch)
                        conn.commit()
                        total_rows += len(batch)
                        batch.clear()

        if idx % 10 == 0:
            print(f"[DB] Processed {idx}/{len(files)} files; rows so far: {total_rows}")

    if batch:
        cur.executemany(insert_sql, batch)
        conn.commit()
        total_rows += len(batch)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_batter ON deliveries(batter)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bowler ON deliveries(bowler)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_batter_bowler ON deliveries(batter, bowler)")
    conn.commit()
    conn.close()
    print(f"[DB] Build complete. Rows inserted: {total_rows}")


# ---------- QUERY HELPERS ----------
def search_players(role, query):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if role == "batter":
        cur.execute("""
            SELECT DISTINCT batter
            FROM deliveries
            WHERE batter LIKE '%' || ? || '%' COLLATE NOCASE
            ORDER BY batter
            LIMIT 20
        """, (query,))
    else:
        cur.execute("""
            SELECT DISTINCT bowler
            FROM deliveries
            WHERE bowler LIKE '%' || ? || '%' COLLATE NOCASE
            ORDER BY bowler
            LIMIT 20
        """, (query,))
    results = [r[0] for r in cur.fetchall() if r[0]]
    conn.close()
    return results


def compute_stats(format_type, batter, bowler):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COALESCE(SUM(runs), 0) AS runs,
            COUNT(*)                 AS balls,
            SUM(CASE WHEN wicket_kind IS NOT NULL THEN 1 ELSE 0 END) AS outs
        FROM deliveries
        WHERE batter = ? AND bowler = ?
    """, (batter, bowler))
    runs, balls, outs = cur.fetchone()
    conn.close()

    sr = round((runs / balls * 100), 2) if balls else 0.0
    avg = round((runs / outs), 2) if outs > 0 else "-"

    return {
        "format": format_type,
        "batter": batter,
        "bowler": bowler,
        "runs": runs,
        "balls": balls,
        "outs": outs,
        "average": avg,
        "strike_rate": sr,
    }


# ---------- LAZY GRAPH CACHE ----------
matchup_cache = {}
cache_built = False

def build_matchup_cache():
    """Build cache of all batter-bowler matchups on first graph request"""
    global matchup_cache, cache_built
    print("[CACHE] Building matchup cache...")
    files = glob.glob(os.path.join(DATA_DIR, "*.json"))
    
    for idx, path in enumerate(files, start=1):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            continue
        
        players = data.get("info", {}).get("players", {})
        all_players = []
        for team_players in players.values():
            all_players.extend(team_players)
        
        for innings in data.get("innings", []):
            for over in innings.get("overs", []):
                for delivery in over.get("deliveries", []):
                    batter = delivery.get("batter")
                    bowler = delivery.get("bowler")
                    
                    if batter and bowler:
                        key = f"{batter}_{bowler}"
                        if key not in matchup_cache:
                            matchup_cache[key] = []
                        matchup_cache[key].append(data)
        
        if idx % 100 == 0:
            print(f"[CACHE] Processed {idx}/{len(files)} files")
    
    cache_built = True
    print(f"[CACHE] Complete! Cached {len(matchup_cache)} matchups")

def ensure_graph_cache():
    """Ensure cache is built before graph request"""
    global cache_built
    if not cache_built:
        build_matchup_cache()


# ---------- ROUTES ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search_batters")
def search_batters():
    q = request.args.get("query", "")
    return jsonify(search_players("batter", q))

@app.route("/search_bowlers")
def search_bowlers():
    q = request.args.get("query", "")
    return jsonify(search_players("bowler", q))

@app.route("/get_stats", methods=["POST"])
def get_stats_route():
    data = request.get_json() or request.form
    format_type = data.get("format", "Tests")
    batter_input = (data.get("batter") or "").strip()
    bowler_input = (data.get("bowler") or "").strip()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT batter
        FROM deliveries
        WHERE batter LIKE '%' || ? || '%' COLLATE NOCASE
        ORDER BY batter
        LIMIT 1
    """, (batter_input,))
    row = cur.fetchone()
    batter_name = row[0] if row else None
    cur.execute("""
        SELECT DISTINCT bowler
        FROM deliveries
        WHERE bowler LIKE '%' || ? || '%' COLLATE NOCASE
        ORDER BY bowler
        LIMIT 1
    """, (bowler_input,))
    row = cur.fetchone()
    bowler_name = row[0] if row else None
    conn.close()
    if not batter_name or not bowler_name:
        return jsonify({"error": "No matching batter/bowler found"}), 404
    stats = compute_stats(format_type, batter_name, bowler_name)
    stats["batterName"] = batter_name
    stats["bowlerName"] = bowler_name
    return jsonify(stats)


@app.route("/matchup_graph/<batter>/<bowler>")
def matchup_graph(batter, bowler):
    """Return cached match data for graphs"""
    ensure_graph_cache()  # Build cache on first request
    
    key = f"{batter}_{bowler}"
    matches_data = matchup_cache.get(key, [])
    
    return jsonify({
        "batter": batter,
        "bowler": bowler,
        "matches": matches_data
    })

# Build the DB on startup
build_db_if_missing()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
