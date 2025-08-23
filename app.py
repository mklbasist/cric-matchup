from flask import Flask, render_template, request, jsonify
import os, glob, json

app = Flask(__name__)

# Path to match JSON files (adjust if folder name differs)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATCHES_PATH = os.path.join(BASE_DIR, "data", "test_matches", "*.json")

all_batters = set()
all_bowlers = set()
match_data = []


def load_matches():
    """Load all match JSON files and extract players + events."""
    global all_batters, all_bowlers, match_data
    print(f"Loading matches from: {MATCHES_PATH}")
    files = glob.glob(MATCHES_PATH)
    print(f"Found {len(files)} match files")
    for file in files:
        with open(file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                match_data.append(data)
                # Extract batters/bowlers
                for innings in data.get("innings", []):
                    for over in innings.get("overs", []):
                        for delivery in over.get("deliveries", []):
                            batter = delivery.get("batter")
                            bowler = delivery.get("bowler")
                            if batter:
                                all_batters.add(batter)
                            if bowler:
                                all_bowlers.add(bowler)
            except Exception as e:
                print(f"Error reading {file}: {e}")


def get_stats(format_type, batter, bowler):
    """Calculate batter vs bowler stats across all matches."""
    runs = 0
    balls = 0
    outs = 0
    for data in match_data:
        for innings in data.get("innings", []):
            for over in innings.get("overs", []):
                for delivery in over.get("deliveries", []):
                    if delivery.get("batter") == batter and delivery.get("bowler") == bowler:
                        balls += 1
                        runs += delivery.get("runs", {}).get("batter", 0)
                        if "wickets" in delivery:
                            for w in delivery["wickets"]:
                                if w.get("kind") != "run out":
                                    outs += 1
    strike_rate = (runs / balls * 100) if balls > 0 else 0
    average = (runs / outs) if outs > 0 else "NA"
    return {
        "format": format_type,
        "batter": batter,
        "bowler": bowler,
        "runs": runs,
        "balls": balls,
        "outs": outs,
        "average": average,
        "strike_rate": round(strike_rate, 2),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search_batters")
def search_batters():
    query = request.args.get("query", "").lower()
    filtered = [b for b in sorted(all_batters) if b.lower().startswith(query)]
    return jsonify(filtered)


@app.route("/search_bowlers")
def search_bowlers():
    query = request.args.get("query", "").lower()
    filtered = [b for b in sorted(all_bowlers) if b.lower().startswith(query)]
    return jsonify(filtered)


@app.route("/get_stats", methods=["POST"])
def get_stats_route():
    data = request.get_json() or request.form
    format_type = data.get("format")
    batter = data.get("batter")
    bowler = data.get("bowler")
    stats = get_stats(format_type, batter, bowler)
    return jsonify(stats)


# Always load matches on startup (important for Render)
load_matches()
print(f"Loaded {len(match_data)} matches")

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
