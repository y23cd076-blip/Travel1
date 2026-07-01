import streamlit as st
import requests
import os
from datetime import date, timedelta

# Resolve backend URL in this priority order:
# 1. Streamlit Cloud "Secrets" (Settings -> Secrets -> BACKEND_URL = "https://your-backend.onrender.com")
# 2. Environment variable (useful for local testing against a deployed backend)
# 3. Fallback to localhost for local development
try:
    BACKEND_URL = st.secrets["BACKEND_URL"]
except Exception:
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="SmartTrip AI", page_icon="🧳", layout="wide")

st.title("🧳 SmartTrip AI - Travel Itinerary Planner")
st.caption("Constraint-based itinerary optimization, grounded in a curated dataset - not a hallucinated wishlist.")


@st.cache_data(ttl=300)
def get_destinations():
    try:
        resp = requests.get(f"{BACKEND_URL}/destinations", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


destinations = get_destinations()
dest_options = {d["name"]: d["key"] for d in destinations} if destinations else {
    "Backend not reachable - start it with `uvicorn main:app --reload`": None
}

with st.form("trip_form"):
    col1, col2 = st.columns(2)
    with col1:
        source = st.text_input("Source city", value="Hyderabad")
        destination_name = st.selectbox("Destination", list(dest_options.keys()))
        budget = st.number_input("Total budget (INR)", min_value=1000, value=25000, step=1000)
    with col2:
        start_date = st.date_input("Start date", value=date.today() + timedelta(days=14))
        end_date = st.date_input("End date", value=date.today() + timedelta(days=17))
        interests = st.multiselect(
            "Interests",
            ["beaches", "adventure", "food", "history", "nightlife"],
            default=["food", "history"],
        )

    submitted = st.form_submit_button("Generate Itinerary", type="primary", use_container_width=True)

if submitted:
    dest_key = dest_options.get(destination_name)
    if not dest_key:
        st.error("Backend is not reachable. Start it first: `cd backend && uvicorn main:app --reload`")
    elif not interests:
        st.error("Please select at least one interest.")
    elif end_date < start_date:
        st.error("End date must be on or after start date.")
    else:
        payload = {
            "source": source,
            "destination": dest_key,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "budget": budget,
            "interests": interests,
        }
        with st.spinner("Optimizing itinerary and generating your trip plan..."):
            try:
                resp = requests.post(f"{BACKEND_URL}/plan-trip", json=payload, timeout=30)
                resp.raise_for_status()
                st.session_state["trip"] = resp.json()
            except requests.HTTPError as e:
                st.error(f"Backend error: {e.response.json().get('detail', str(e))}")
            except Exception as e:
                st.error(f"Could not reach backend: {e}")

if "trip" in st.session_state:
    trip = st.session_state["trip"]

    st.divider()
    st.header(f"{trip['source']} → {trip['destination']} ({trip['days']} days)")

    bb = trip["budget_breakdown"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Hotel", f"₹{bb['hotel_total']:,.0f}")
    c2.metric("Attractions", f"₹{bb['attractions_total']:,.0f}")
    c3.metric("Food", f"₹{bb['food_total']:,.0f}")
    c4.metric("Total", f"₹{bb['grand_total']:,.0f}",
              delta=f"{'Within' if bb['within_budget'] else 'Over'} budget "
                    f"(₹{bb['remaining_budget']:,.0f} left)")

    st.subheader(f"🏨 Hotel: {trip['hotel']['name']}")
    st.write(f"₹{trip['hotel']['cost_per_night']:,.0f}/night · Rating {trip['hotel']['rating']} · "
              f"Total ₹{trip['hotel']['total_cost']:,.0f}")

    st.subheader("📅 Day-by-Day Itinerary")
    for day in trip["itinerary"]:
        with st.expander(f"Day {day['day_number']} — {day['date']} (₹{day['estimated_day_cost']:,.0f})", expanded=True):
            if day["summary"]:
                st.write(day["summary"])
            st.markdown("**Attractions:**")
            for a in day["attractions"]:
                st.write(f"- {a['name']} ({', '.join(a['tags'])}) · ₹{a['cost']:,.0f} · {a['duration_hours']}h · ⭐{a['rating']}")
            if not day["attractions"]:
                st.write("- Free day / rest & explore on foot")
            st.markdown("**Restaurants:**")
            for r in day["restaurants"]:
                st.write(f"- {r['name']} ({r['cuisine']}) · ₹{r['cost_per_person']:,.0f}/person · ⭐{r['rating']}")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("💡 Travel Tips")
        for t in trip["travel_tips"]:
            st.write(f"- {t}")
    with col_b:
        st.subheader("⚠️ Things to Avoid")
        for t in trip["things_to_avoid"]:
            st.write(f"- {t}")
    with col_c:
        st.subheader("🎒 Packing Tips")
        for t in trip["packing_tips"]:
            st.write(f"- {t}")
