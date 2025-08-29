# app.py
import os
from math import radians, cos, sin, asin, sqrt
from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests
import openai
from database import init_db, add_user, get_user_by_username, create_itinerary, get_itineraries_by_user


app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev_secret_key')

OPENAI_KEY = os.getenv('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')
GOOGLE_KEY = os.getenv('AIzaSyDu0KIpa9arBxAtDwDWsO6FwNusFXpQ1-0')        
OPENWEATHER_KEY = os.getenv('cf009ed0a70d15304d445e66c8ba514e')  

if OPENAI_KEY:
    openai.api_key = OPENAI_KEY


init_db()


def haversine_km(lat1, lon1, lat2, lon2):
    # Haversine formula
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    km = 6371 * c
    return km

def geocode_place(place):
    """
    Try to get lat/lon using OpenStreetMap Nominatim.
    Returns (lat, lon) as floats or (None, None) on failure.
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        resp = requests.get(url, params={"q": place, "format": "json", "limit": 1},
                            headers={"User-Agent": "TravelPlanner/1.0 (+you@example.com)"}, timeout=10)
        data = resp.json()
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
    except Exception:
        pass
    return None, None

def get_distance_and_duration(source, destination):
    """
    Returns (distance_km, duration_text).
    Prefers Google Distance Matrix if GOOGLE_KEY present; else uses geocoding + Haversine.
    """
    if GOOGLE_KEY:
        try:
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": source,
                "destinations": destination,
                "key": GOOGLE_KEY,
                "units": "metric"
            }
            r = requests.get(url, params=params, timeout=10)
            j = r.json()
            elem = j['rows'][0]['elements'][0]
            if elem.get('status') == 'OK':
                dist_text = elem['distance']['text']
                distance_km = elem['distance']['value'] / 1000.0
                duration_text = elem['duration']['text']
                return distance_km, duration_text
        except Exception:
            pass

    # Fallback: geocode and haversine
    lat1, lon1 = geocode_place(source)
    lat2, lon2 = geocode_place(destination)
    if lat1 is None or lat2 is None:
        return None, "Unknown (geocoding failed)"
    distance_km = haversine_km(lat1, lon1, lat2, lon2)
    # simple duration estimate at 60 km/h
    hours = distance_km / 60.0
    if hours < 1:
        duration_text = f"{int(hours*60)} mins"
    else:
        duration_text = f"{hours:.1f} hours"
    return distance_km, duration_text

def get_weather_by_coords(lat, lon):
    if not OPENWEATHER_KEY:
        return None
    try:
        url = "http://api.openweathermap.org/data/2.5/weather"
        params = {"lat": lat, "lon": lon, "units": "metric", "appid": OPENWEATHER_KEY}
        r = requests.get(url, params=params, timeout=8)
        j = r.json()
        return {
            "temp": j.get("main", {}).get("temp"),
            "description": j.get("weather", [{}])[0].get("description"),
            "wind": j.get("wind", {}).get("speed")
        }
    except Exception:
        return None

def get_hotels_near(lat, lon, limit=5):
    """
    Use Google Places if available, else return a small fallback list.
    """
    hotels = []
    if GOOGLE_KEY:
        try:
            url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
            params = {
                "key": GOOGLE_KEY,
                "location": f"{lat},{lon}",
                "radius": 5000,
                "type": "lodging"
            }
            r = requests.get(url, params=params, timeout=8)
            j = r.json()
            results = j.get("results", [])[:limit]
            for place in results:
                hotels.append({
                    "name": place.get("name"),
                    "vicinity": place.get("vicinity"),
                    "rating": place.get("rating"),
                    "price_level": place.get("price_level", None)
                })
            if hotels:
                return hotels
        except Exception:
            pass

    # Fallback static sample hotels
    sample = [
        {"name": "Comfort Stay", "vicinity": "Central area", "rating": 4.1, "price_level": 2},
        {"name": "Budget Inn", "vicinity": "Near station", "rating": 3.8, "price_level": 1},
        {"name": "Luxury Suites", "vicinity": "Downtown", "rating": 4.6, "price_level": 4},
    ]
    return sample[:limit]

def estimate_costs(distance_km, nights, avg_hotel_per_night=2500, people=1):
    """
    Basic formula (tune numbers as you want):
    - travel: ₹10 per km per vehicle (approx)
    - hotel: avg_hotel_per_night per room per night
    - food+misc: ₹800 per person per day
    """
    if distance_km is None:
        travel_cost = None
    else:
        travel_cost = round(distance_km * 10)  # ₹10 per km

    hotel_cost = nights * avg_hotel_per_night
    food_misc = nights * 800 * people
    total = (travel_cost if travel_cost else 0) + hotel_cost + food_misc
    return {
        "travel_cost": travel_cost,
        "hotel_cost": hotel_cost,
        "food_misc": food_misc,
        "total_estimate": total
    }

def generate_ai_itinerary(dest, days, people=1):
    if not OPENAI_KEY:
        return None
    prompt = (
        f"Create a {days}-day travel itinerary for {dest} for {people} traveller(s). "
        "For each day give 3 activities/places with short notes and a per-day rough cost in INR. "
        "Also return top 5 must-visit places and approximate total cost. Keep concise."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful travel planner assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=700,
            temperature=0.7
        )
        return resp['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"AI error: {e}"

# ---------- Routes ----------
@app.route('/')
def home():
    return render_template('home.html')

# simple login/register (optional; same functions as before)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash("Username & password required.")
            return redirect(url_for('register'))
        if get_user_by_username(username):
            flash("Username exists.")
            return redirect(url_for('register'))
        add_user(username, password)
        flash("Registered. Please login.")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = get_user_by_username(username)
        if user and user[2] == password:
            session['username'] = username
            flash("Login successful.")
            return redirect(url_for('dashboard'))
        flash("Invalid credentials.")
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    username = session.get('username')
    if not username:
        flash("Please login.")
        return redirect(url_for('login'))
    itineraries = get_itineraries_by_user(username)
    return render_template('dashboard.html', username=username, itineraries=itineraries)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logged out.")
    return redirect(url_for('home'))

# Trip planning (source+destination)
@app.route('/plan', methods=['GET', 'POST'])
def plan():
    username = session.get('username', 'guest')  # guest mode if not logged in
    if request.method == 'POST':
        source = request.form.get('source', '').strip()
        destination = request.form.get('destination', '').strip()
        start_date = request.form.get('start_date', '').strip()
        end_date = request.form.get('end_date', '').strip()
        days = int(request.form.get('days', '1'))
        people = int(request.form.get('people', '1'))

        if not source or not destination:
            flash("Please provide both source and destination.")
            return redirect(url_for('plan'))

        distance_km, duration_text = get_distance_and_duration(source, destination)

        # geocode destination for weather/hotels
        dest_lat, dest_lon = geocode_place(destination)
        weather = None
        hotels = []
        if dest_lat and dest_lon:
            weather = get_weather_by_coords(dest_lat, dest_lon)
            hotels = get_hotels_near(dest_lat, dest_lon, limit=5)
        else:
            hotels = get_hotels_near(0, 0, limit=5)  # fallback sample

        nights = max(0, days - 1)
        costs = estimate_costs(distance_km, nights, avg_hotel_per_night=2500, people=people)

        ai_plan = generate_ai_itinerary(destination, days, people) if OPENAI_KEY else None

        # Optionally save a short record to DB as itinerary
        notes = f"From {source} to {destination}. Estimated dist: {round(distance_km,1) if distance_km else 'N/A'} km."
        create_itinerary(username, f"{source} → {destination}", start_date, end_date, notes)

        return render_template('plan_result.html',
                               source=source,
                               destination=destination,
                               distance_km=distance_km,
                               duration_text=duration_text,
                               weather=weather,
                               hotels=hotels,
                               costs=costs,
                               ai_plan=ai_plan,
                               days=days,
                               people=people,
                               username=username)

    return render_template('plan.html')

# legacy AI endpoint if you want separate form
@app.route('/suggest_itinerary', methods=['POST'])
def suggest_itinerary():
    dest = request.form.get('ai_destination', '').strip()
    days = int(request.form.get('ai_days', '3'))
    people = int(request.form.get('ai_people', '1'))
    if not dest:
        flash("Enter a destination.")
        return redirect(url_for('plan'))
    ai_plan = generate_ai_itinerary(dest, days, people)
    return render_template('itinerary.html', city=dest, days=days, itinerary=ai_plan)

# ---------- Run ----------
if __name__ == '__main__':
    app.run(debug=True)
