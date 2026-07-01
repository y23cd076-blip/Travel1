from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class TripRequest(BaseModel):
    source: str = Field(..., description="City the traveler departs from")
    destination: str = Field(..., description="Pilot destination key, e.g. 'goa', 'manali', 'jaipur', 'kerala', 'hyderabad'")
    start_date: date
    end_date: date
    budget: float = Field(..., gt=0, description="Total trip budget in INR")
    interests: List[str] = Field(..., description="e.g. ['beaches', 'adventure', 'food', 'history', 'nightlife']")


class AttractionOut(BaseModel):
    name: str
    tags: List[str]
    cost: float
    duration_hours: float
    rating: float
    description: Optional[str] = None


class RestaurantOut(BaseModel):
    name: str
    cuisine: str
    cost_per_person: float
    rating: float


class DayPlan(BaseModel):
    day_number: int
    date: str
    attractions: List[AttractionOut]
    restaurants: List[RestaurantOut]
    summary: Optional[str] = None
    estimated_day_cost: float


class HotelOut(BaseModel):
    name: str
    cost_per_night: float
    rating: float
    total_cost: float


class BudgetBreakdown(BaseModel):
    hotel_total: float
    attractions_total: float
    food_total: float
    local_transport_buffer: float
    grand_total: float
    remaining_budget: float
    within_budget: bool


class TripResponse(BaseModel):
    source: str
    destination: str
    days: int
    itinerary: List[DayPlan]
    hotel: HotelOut
    budget_breakdown: BudgetBreakdown
    travel_tips: List[str]
    things_to_avoid: List[str]
    packing_tips: List[str]
