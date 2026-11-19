from flask import Flask, render_template, request, jsonify, Response
import sqlite3
import json
import time
from geopy.distance import geodesic

app = Flask(__name__)

# ============================================================
# KARUR DISTRICT — Places with real lat/lng coordinates
# ============================================================

KARUR_PLACES = {
    "Ammapalayam":              (10.9350, 78.2500),
    "Aravakurichi":             (10.7838, 78.1131),
    "Arugampatti":              (10.9050, 78.1700),
    "Ayyarmalai":               (10.9650, 78.2600),
    "Chinnadharapuram":         (10.8800, 78.0900),
    "Eraiyanur":                (10.8280, 78.1920),
    "Elachipalayam":            (10.9480, 78.0850),
    "Gandhigramam":             (10.9300, 78.0900),
    "Iyerpadi":                 (10.8450, 78.1650),
    "K.Paramathi":              (11.0030, 78.3640),
    "Kadavur":                  (10.8370, 78.0220),
    "Kalavanoor":               (10.9760, 78.0120),
    "Kalingarayanpalayam":      (10.9680, 78.3200),
    "Karur Junction":           (10.9580, 78.0740),
    "Karur South":              (10.9520, 78.0760),
    "Karur Town":               (10.9601, 78.0766),
    "Karumalaikundu":           (10.9900, 78.1400),
    "Kattur":                   (10.9450, 78.0580),
    "Kodumudi":                 (10.9800, 78.1800),
    "Kovai Road Area":          (10.9560, 78.0690),
    "Krishnapuram":             (10.8900, 78.1600),
    "Krishnarayapuram":         (10.9526, 78.3099),
    "Kulithalai":               (10.9346, 78.4197),
    "Mallur":                   (10.9050, 78.4010),
    "Manaparai":                (10.6090, 78.2205),
    "Manmangalam":              (10.9980, 78.2450),
    "Mela Karur":               (10.9650, 78.0800),
    "Mohanur":                  (11.0560, 78.1470),
    "Musiri":                   (10.9542, 78.4454),
    "Muthunaickenpalayam":      (10.9720, 78.2100),
    "Nallaneri":                (10.8920, 78.3200),
    "Nangavalli":               (11.0390, 78.4160),
    "Natham":                   (10.8500, 78.2100),
    "Neivasal":                 (10.9700, 78.4000),
    "Nerur":                    (10.9810, 78.1340),
    "Nochiyam":                 (10.9400, 78.1100),
    "Odugathur":                (10.8750, 78.0700),
    "Old Karur":                (10.9540, 78.0700),
    "Pallapatti":               (10.9200, 78.2300),
    "Panriti":                  (11.0100, 78.2900),
    "Papparapatti":             (10.9100, 78.0500),
    "Periyasamy Nagar":         (10.9620, 78.0720),
    "Peruvalanallur":           (10.8300, 78.3100),
    "Pettavaithalai":           (10.9000, 78.0400),
    "Poovalur":                 (10.9230, 78.2080),
    "Pugalur":                  (10.8780, 78.2360),
    "Rayanur":                  (10.9150, 78.0600),
    "Samudram":                 (10.9450, 78.1700),
    "Sendurai":                 (11.1014, 78.4824),
    "Sevanthipalayam":          (10.9500, 78.2000),
    "Sundarapandiam":           (10.8100, 78.2700),
    "Thalavapalayam":           (10.9270, 78.3000),
    "Thandavarayan":            (10.8560, 78.2700),
    "Thanthoni":                (10.8999, 78.1501),
    "Thanthonrimalai":          (10.8700, 78.1300),
    "Thiruvalanchuli":          (10.9130, 78.0310),
    "Thogaimalai":              (10.8120, 78.2340),
    "Thuvarankurichi":          (10.7600, 78.1800),
    "Uppidamangalam":           (10.8650, 78.1890),
    "Valavanthi":               (10.8200, 78.1400),
    "Vangal":                   (11.0210, 78.1120),
    "Vellalanallur":            (10.9410, 78.0430),
    "Vengamedu":                (10.9550, 78.0950),
    "Vengamedu East":           (10.9600, 78.1050),
    "Vettamangalam":            (10.9100, 78.3600),
}

PLACE_NAMES = sorted(KARUR_PLACES.keys())

PLACES_GROUP_AM = sorted(
    [p for p in KARUR_PLACES.keys() if p[0].upper() <= 'M']
)

PLACES_GROUP_NZ = sorted(
    [p for p in KARUR_PLACES.keys() if p[0].upper() > 'M']
)

PLACE_GROUPS = {
    "A – M": PLACES_GROUP_AM,
    "N – Z": PLACES_GROUP_NZ,
}


def get_place_count():
    return len(KARUR_PLACES)


# ============================================================
# PROXIMITY HELPER — returns closest places with donors first
# ============================================================

def get_nearby_places(origin_place, max_km=30, limit=15, blood=None):
    """
    Returns nearby places sorted by distance.
    If blood is supplied, places that HAVE donors for that blood group
    are floated to the top (within the distance-sorted order).
    limit is set high so no nearby place is silently dropped.
    """
    if origin_place not in KARUR_PLACES:
        return []
    origin_coords = KARUR_PLACES[origin_place]
    distances = []
    for place, coords in KARUR_PLACES.items():
        if place == origin_place:
            continue
        dist_km = geodesic(origin_coords, coords).km
        if dist_km <= max_km:
            distances.append((place, round(dist_km, 1)))
    distances.sort(key=lambda x: x[1])

    if blood:
        conn = get_db()
        donor_places = {
            row["place"] for row in conn.execute(
                "SELECT DISTINCT place FROM donors WHERE blood=? AND availability='Yes'", (blood,)
            ).fetchall()
        }
        conn.close()
        # Split into two lists: has donors vs no donors, both still sorted by distance
        with_donors    = [(p, d) for p, d in distances if p in donor_places]
        without_donors = [(p, d) for p, d in distances if p not in donor_places]
        distances = with_donors + without_donors

    return distances[:limit]


def find_nearest_place_to_coords(user_coords, donor_places_only=False):
    """
    Given GPS coordinates (lat, lng), find the nearest Karur locality.
    If donor_places_only=True, only considers places that have available donors.
    Returns (place_name, distance_km, has_donors).
    """
    conn = get_db()

    # Get all places that have available donors
    donor_rows = conn.execute("""
        SELECT DISTINCT place FROM donors
        WHERE availability='Yes' AND district='Karur'
    """).fetchall()
    conn.close()

    donor_place_set = {row["place"] for row in donor_rows}

    best_donor_place    = None
    best_donor_dist     = float("inf")
    best_fallback_place = None
    best_fallback_dist  = float("inf")

    for place_name, coords in KARUR_PLACES.items():
        dist_km = geodesic(user_coords, coords).km

        # Track closest place with donors
        if place_name in donor_place_set:
            if dist_km < best_donor_dist:
                best_donor_dist  = dist_km
                best_donor_place = place_name

        # Track absolute closest place (fallback)
        if dist_km < best_fallback_dist:
            best_fallback_dist  = dist_km
            best_fallback_place = place_name

    if best_donor_place:
        return best_donor_place, round(best_donor_dist, 1), True

    # No donor found anywhere — return nearest locality as fallback
    return best_fallback_place, round(best_fallback_dist, 1), False


# ============================================================
# DATABASE HELPERS
# ============================================================

def get_db():
    conn = sqlite3.connect("blood.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT,
            phone        TEXT,
            district     TEXT,
            place        TEXT,
            contact      TEXT,
            blood        TEXT,
            availability TEXT
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
    if count == 0:
        sample_donors = [
            ("Arjun Krishnan",       "9840012345", "Karur", "Karur Town",          "9841012345", "O+",  "Yes"),
            ("Priya Devi",           "9895090124", "Karur", "Karur Town",           "",           "A-",  "Yes"),
            ("Sanjay Kumar",         "9597112347", "Karur", "Karur Town",           "",           "A-",  "Yes"),
            ("Divya Menon",          "9841023456", "Karur", "Kulithalai",           "9840023456", "A+",  "Yes"),
            ("Karthik Reddy",        "9842034567", "Karur", "Nerur",                "9843034567", "B+",  "Yes"),
            ("Sneha Lakshmi",        "9843045678", "Karur", "Pugalur",              "",           "AB+", "Yes"),
            ("Arun Prasad",          "9751056789", "Karur", "Thanthoni",            "9750056789", "A+",  "Yes"),
            ("Maya Subramanian",     "9750067890", "Karur", "Gandhigramam",         "",           "B-",  "Yes"),
            ("Vikram Nair",          "9751078901", "Karur", "Rayanur",              "9752078901", "O+",  "Yes"),
            ("Anjali Sharma",        "9752089012", "Karur", "Thalavapalayam",       "",           "A-",  "Yes"),
            ("Rahul Verma",          "9753090123", "Karur", "Sevanthipalayam",      "9754090123", "B+",  "Yes"),
            ("Kishore Rao",          "9752089013", "Karur", "Aravakurichi",         "9753089013", "AB-", "Yes"),
            ("Suresh Iyer",          "9894089013", "Karur", "Thanthonrimalai",      "9895089013", "AB+", "Yes"),
            ("Anil Kumar",           "9896101235", "Karur", "Kadavur",              "9897101235", "O-",  "Yes"),
            ("Rohit Kumar",          "9896201234", "Karur", "Mohanur",              "9897201234", "B+",  "Yes"),
            ("Rajesh Sharma",        "9597112346", "Karur", "Kodumudi",             "",           "B+",  "Yes"),
            ("Divya Reddy",          "9598123455", "Karur", "Kodumudi",             "9599123455", "O+",  "Yes"),
            ("Sangeetha Reddy",      "9598123456", "Karur", "Kodumudi",             "9599123456", "A-",  "Yes"),
            ("Ananya Reddy",         "9598123457", "Karur", "Krishnarayapuram",     "9599123457", "O+",  "Yes"),
            ("Deepak Murugan",       "9599134568", "Karur", "Vangal",               "",           "O-",  "Yes"),
            ("Mohan Pandian",        "9443145679", "Karur", "Manmangalam",          "9444145679", "A+",  "Yes"),
            ("Deepa Selvi",          "9444156790", "Karur", "Poovalur",             "",           "AB-", "Yes"),
            ("kishore rana",         "9020106070", "karur", "thalavapalayam",       "",           "AB+", "Yes"),
            ("Vijay Arumugam",       "9445167891", "Karur", "Uppidamangalam",       "9446167891", "B+",  "Yes"),
            ("Kavitha Rajan",        "9344178902", "Karur", "Samudram",             "",           "O+",  "Yes"),
            ("Senthil Nathan",       "9345189013", "Karur", "K.Paramathi",          "9346189013", "A-",  "Yes"),
            ("Sanjay Patel",         "9787200124", "Karur", "Nangavalli",           "",           "A+",  "Yes"),
            ("Lakshmi Rao",          "9788211235", "Karur", "Mallur",               "9789211235", "AB+", "Yes"),
            ("Kumaravel Ganesan",    "9942222346", "Karur", "Vellalanallur",        "",           "O+",  "Yes"),
            ("Lakshmi Narayanan",    "9943233457", "Karur", "Kalavanoor",           "9944233457", "B+",  "Yes"),
            ("Priyanka Das",         "9944244568", "Karur", "Iyerpadi",             "",           "A-",  "Yes"),
            ("Raghavendra Rao",      "9945255679", "Karur", "Eraiyanur",            "9946255679", "AB+", "Yes"),
            ("Dhivyan Kumar",        "9946266790", "Karur", "Thandavarayan",        "",           "B-",  "Yes"),
            ("Anjali Menon",         "9947277891", "Karur", "Muthunaickenpalayam",  "9948277891", "O-",  "Yes"),
            ("Sathish Kumar",        "9442244568", "Karur", "Thogaimalai",          "",           "A+",  "Yes"),
            ("Meena Reddy",          "9443255679", "Karur", "Panriti",              "9444255679", "AB+", "Yes"),
            ("Ravi Shankar",         "9551122334", "Karur", "Papparapatti",         "",           "O+",  "Yes"),
            ("Uma Devi",             "9552233445", "Karur", "Vengamedu",            "9553233445", "B+",  "Yes"),
            ("Balaji Murugan",       "9553344556", "Karur", "Ayyarmalai",           "",           "A+",  "Yes"),
            ("Geetha Krishnan",      "9554455667", "Karur", "Nochiyam",             "9555455667", "O-",  "Yes"),
            ("Mani Sundar",          "9556566778", "Karur", "Nochiyam",             "",           "AB+", "Yes"),
            ("Saranya Prabhu",       "9557677889", "Karur", "Arugampatti",          "9558677889", "A-",  "Yes"),
            ("Ganesh Kumar",         "9559788990", "Karur", "Pallapatti",           "",           "B-",  "Yes"),
            ("Kavitha Murugan",      "9440112233", "Karur", "Natham",               "9441112233", "O+",  "Yes"),
            ("Selvam Raja",          "9441223344", "Karur", "Krishnapuram",         "",           "A+",  "Yes"),
            ("Nirmala Devi",         "9442334455", "Karur", "Odugathur",            "9443334455", "B+",  "Yes"),
            ("Murugesan P",          "9891001122", "Karur", "Karumalaikundu",       "",           "AB-", "Yes"),
            ("Ezhilarasi S",         "9892112233", "Karur", "Ammapalayam",          "9893112233", "O-",  "Yes"),
            ("Periyasamy K",         "9894223344", "Karur", "Pettavaithalai",       "",           "A+",  "Yes"),
            ("Vasantha M",           "9895334455", "Karur", "Thiruvalanchuli",      "9896334455", "B+",  "Yes"),
            ("Kumaran T",            "9897445566", "Karur", "Vengamedu East",       "",           "O+",  "Yes"),
            ("Senthilkumar R",       "9898556677", "Karur", "Elachipalayam",        "9899556677", "A+",  "Yes"),
            ("Muthu Lakshmi",        "9441667788", "Karur", "Karur Junction",       "",           "B+",  "Yes"),
            ("Dinesh Babu",          "9442778899", "Karur", "Mela Karur",           "9443778899", "O+",  "Yes"),
            ("Parvathi S",           "9443889900", "Karur", "Karur South",          "",           "AB+", "Yes"),
            ("Azhagappan K",         "9444990011", "Karur", "Old Karur",            "9445990011", "A-",  "Yes"),
            ("Vennila M",            "9445001122", "Karur", "Kattur",               "",           "B-",  "Yes"),
        ]
        conn.executemany("""
            INSERT INTO donors (name, phone, district, place, contact, blood, availability)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_donors)
        conn.commit()
        print(f"✅ Seeded {len(sample_donors)} sample donors")
    else:
        print(f"ℹ️  DB already has {count} records — skipping seed")
    conn.close()


def test_db():
    print("\n--- DB Check ---")
    try:
        conn = get_db()
        count = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
        avail = conn.execute("SELECT COUNT(*) FROM donors WHERE availability='Yes'").fetchone()[0]
        print(f"✅ {count} total donors, {avail} available")
        print(f"✅ {get_place_count()} localities registered")
        # Test proximity
        result = find_nearest_place_to_coords((10.9601, 78.0766))
        print(f"✅ Proximity test (Karur Town coords): nearest={result[0]}, dist={result[1]}km, has_donors={result[2]}")
        conn.close()
    except Exception as e:
        print(f"❌ {e}")
    print("----------------\n")


# ============================================================
# STARTUP
# ============================================================

init_db()
seed_db()
test_db()


# ============================================================
# DONOR COUNT HELPERS
# ============================================================

def get_donor_counts():
    conn = get_db()
    total     = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
    available = conn.execute("SELECT COUNT(*) FROM donors WHERE availability='Yes'").fetchone()[0]
    conn.close()
    return {"total": total, "available": available}


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():
    counts = get_donor_counts()
    return render_template("interface.html",
                           donor_count=counts["total"],
                           available_count=counts["available"],
                           place_count=get_place_count())


@app.route("/donor-count")
def donor_count():
    return jsonify(get_donor_counts())


@app.route("/place-count")
def place_count():
    return jsonify({"count": get_place_count()})


@app.route("/donor-count-stream")
def donor_count_stream():
    def generate():
        last_sent = {}
        while True:
            counts = get_donor_counts()
            counts["place_count"] = get_place_count()
            if counts != last_sent:
                yield f"data: {json.dumps(counts)}\n\n"
                last_sent = counts
            time.sleep(4)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/choice")
def choice():
    return render_template("choice.html",
                           place_count=get_place_count())


# ============================================================
# NEAREST PLACE — improved geopy matching
# Prioritises places that actually have available donors.
# Falls back to nearest locality if no donors found anywhere.
# ============================================================

@app.route("/nearest-place", methods=["POST"])
def nearest_place():
    data = request.get_json()
    if not data or "lat" not in data or "lng" not in data:
        return jsonify({"error": "lat and lng required"}), 400

    try:
        user_lat = float(data["lat"])
        user_lng = float(data["lng"])
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid coordinates"}), 400

    # Basic sanity check — Karur district is roughly in this bounding box
    if not (10.5 <= user_lat <= 11.3 and 77.8 <= user_lng <= 78.7):
        # Coords are outside Karur district — still find nearest, but warn
        place, dist_km, has_donors = find_nearest_place_to_coords(
            (user_lat, user_lng)
        )
        return jsonify({
            "place":       place,
            "distance_km": dist_km,
            "has_donors":  has_donors,
            "warning":     "Your location appears to be outside Karur district.",
        })

    place, dist_km, has_donors = find_nearest_place_to_coords(
        (user_lat, user_lng)
    )

    return jsonify({
        "place":       place,
        "distance_km": dist_km,
        "has_donors":  has_donors,
    })


# ── REGISTER ─────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    msg        = ""
    registered = None

    if request.method == "POST":
        name         = request.form.get("name", "").strip()
        phone        = request.form.get("phone", "").strip()
        place        = request.form.get("place", "").strip()
        contact      = request.form.get("contact", "").strip()
        blood        = request.form.get("blood", "").strip()
        availability = request.form.get("availability", "No").strip()

        if name and phone and place and blood:
            conn = get_db()
            conn.execute("""
                INSERT INTO donors (name, phone, district, place, contact, blood, availability)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, phone, "Karur", place, contact, blood, availability))
            conn.commit()
            registered = conn.execute(
                "SELECT * FROM donors WHERE phone=? ORDER BY id DESC LIMIT 1", (phone,)
            ).fetchone()
            conn.close()
            msg = "Registration Successful ✅"
        else:
            msg = "Please fill all required fields."

    return render_template("register.html",
                           msg=msg,
                           place_groups=PLACE_GROUPS,
                           places=PLACE_NAMES,
                           registered=registered)


# ── REQUEST ───────────────────────────────────────────────────
@app.route("/request", methods=["GET", "POST"])
def request_blood():
    msg             = ""
    donors          = []
    nearby_results  = []
    requested_place = ""
    requested_blood = ""

    if request.method == "POST":
        place = request.form.get("place", "").strip()
        blood = request.form.get("bloodGroup", "").strip()

        requested_place = place
        requested_blood = blood

        if not place or not blood:
            msg = "Please select both a place and a blood group."
            return render_template("result.html",
                                   donors=[], nearby_results=[],
                                   msg=msg,
                                   requested_place=place,
                                   requested_blood=blood)

        conn = get_db()
        donors = conn.execute("""
            SELECT * FROM donors
            WHERE district='Karur' AND place=? AND blood=? AND availability='Yes'
        """, (place, blood)).fetchall()

        nearby_places = get_nearby_places(place, max_km=30, blood=blood)
        for nearby_place, dist_km in nearby_places:
            nearby_donors = conn.execute("""
                SELECT * FROM donors
                WHERE district='Karur' AND place=? AND blood=? AND availability='Yes'
            """, (nearby_place, blood)).fetchall()
            if nearby_donors:
                nearby_results.append({
                    "place":    nearby_place,
                    "distance": dist_km,
                    "donors":   nearby_donors,
                })

        conn.close()

        if not donors and not nearby_results:
            msg = f"No donors with {blood} blood found in or near {place}."

        return render_template("result.html",
                               donors=donors,
                               nearby_results=nearby_results,
                               msg=msg,
                               requested_place=requested_place,
                               requested_blood=requested_blood)

    return render_template("request.html",
                           place_groups=PLACE_GROUPS,
                           places=PLACE_NAMES)


# ============================================================
if __name__ == "__main__":
    app.run(debug=True)