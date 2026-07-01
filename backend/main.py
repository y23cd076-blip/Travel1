import json
from pathlib import Path
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import TripRequest, TripResponse, DayPlan, AttractionOut, RestaurantOut, HotelOut, BudgetBreakdown
from optimizer import optimize_trip
from llm_service import generate_narrative
from database import trip_store

app = FastAPI(
    title="SmartTrip AI - Travel Itinerary Planner",
    description="AI travel agent with constraint-based itinerary optimization and grounded LLM narrative generation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = Path(__file__).parent / "data" / "destinations.json"
DESTINATIONS = json.loads(DATA_PATH.read_text())


@app.get("/")
def root():
    return {"status": "ok", "message": "SmartTrip AI backend is running."}


@app.get("/destinations")
def list_destinations():
    """Returns pilot destinations available for planning (the dataset this MVP is grounded in)."""
    return [
        {"key": key, "name": val["name"], "state": val["state"]}
        for key, val in DESTINATIONS.items()
    ]


@app.post("/plan-trip", response_model=TripResponse)
def plan_trip(req: TripRequest):
    dest_key = req.destination.strip().lower()
    if dest_key not in DESTINATIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Destination '{req.destination}' not in pilot dataset. "
                   f"Available: {', '.join(DESTINATIONS.keys())}",
        )
    if req.end_date < req.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    destination_data = DESTINATIONS[dest_key]

    # --- Step 1: constraint-based optimization (algorithmic core) ---
    result = optimize_trip(
        destination_data=destination_data,
        start_date=req.start_date,
        end_date=req.end_date,
        total_budget=req.budget,
        interests=req.interests,
    )

    # --- Step 2: LLM narrative generation, grounded in the fixed schedule ---
    narrative = generate_narrative(
        destination_name=destination_data["name"],
        interests=req.interests,
        day_plans=result["day_plans"],
    )

    # --- Step 3: assemble response ---
    days_out = []
    for d in result["day_plans"]:
        days_out.append(DayPlan(
            day_number=d["day_number"],
            date=d["date"],
            attractions=[
                AttractionOut(name=a["name"], tags=a["tags"], cost=a["cost"],
                               duration_hours=a["duration_hours"], rating=a["rating"])
                for a in d["attractions"]
            ],
            restaurants=[
                RestaurantOut(name=r["name"], cuisine=r["cuisine"],
                               cost_per_person=r["cost_per_person"], rating=r["rating"])
                for r in d["restaurants"]
            ],
            summary=narrative["day_summaries"].get(str(d["day_number"]), ""),
            estimated_day_cost=d["estimated_day_cost"],
        ))

    hotel = result["hotel"]
    response = TripResponse(
        source=req.source,
        destination=destination_data["name"],
        days=result["days"],
        itinerary=days_out,
        hotel=HotelOut(
            name=hotel["name"], cost_per_night=hotel["cost_per_night"],
            rating=hotel["rating"], total_cost=result["hotel_total"],
        ),
        budget_breakdown=BudgetBreakdown(
            hotel_total=result["hotel_total"],
            attractions_total=result["attractions_total"],
            food_total=result["food_total"],
            local_transport_buffer=result["local_transport_buffer"],
            grand_total=result["grand_total"],
            remaining_budget=result["remaining_budget"],
            within_budget=result["within_budget"],
        ),
        travel_tips=narrative["travel_tips"],
        things_to_avoid=narrative["things_to_avoid"],
        packing_tips=narrative["packing_tips"],
    )

    # --- Step 4: persist trip (Mongo if configured, else local JSON fallback) ---
    trip_store.save_trip({
        "source": req.source,
        "destination": req.destination,
        "start_date": str(req.start_date),
        "end_date": str(req.end_date),
        "budget": req.budget,
        "interests": req.interests,
        "response": response.model_dump(),
    })

    return response


@app.get("/trips")
def list_saved_trips():
    return trip_store.list_trips()
