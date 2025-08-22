from flask import Flask, render_template, request, jsonify
import os, glob, json

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATCHES_PATH = os.path.join(BASE_DIR, "data", "test_matches", "*.json")

all_batters = set()
all_bowlers = set()
match_data = []

def load_matches():
    global all_batters, all_bowlers, match_data
    print(f"Loading matches from: {MATCHES_PATH}")
    files = glob.glob(MATCHES_PATH)
    print(f"Files found: {files}")
    if not files:
        print("ERROR: No JSON files found. Please check your deployment files.")
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                match_data.append(data)

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

# The rest of your app.py code remains the same...

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
    format_type = request.form["format"]
    batter = request.form["batter"]
    bowler = request.form["bowler"]
    stats = get_stats(format_type, batter, bowler)
    return jsonify(stats)

if __name__ == "__main__":
    load_matches()
    print(f"Loaded {len(match_data)} matches")
    app.run(host="0.0.0.0", debug=True)
