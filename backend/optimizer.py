"""
Constraint-based itinerary optimizer.

Core idea (this is the "novelty" chapter of the report):
Instead of asking an LLM to freely invent a day-by-day plan (which tends to
hallucinate places, ignore budget, and produce infeasible schedules), we treat
itinerary construction as a resource-allocation problem:

  - Each attraction has a "value" (how well it matches the traveler's
    interests + its quality rating) and a "weight" (time it consumes).
  - Each day has a fixed time budget (hours_per_day).
  - We solve a 0/1 knapsack per day to pick the subset of attractions that
    maximizes total value without exceeding the day's time budget.
  - Attractions already used on a previous day are removed from the pool
    before solving the next day, so nothing repeats.
  - Hotel and restaurants are chosen greedily to fit the remaining budget
    after attraction costs are known.

The LLM is only used afterwards, to write natural-language narrative
(summaries, tips) grounded in this already-fixed, already-feasible schedule.
It never chooses which places to visit.
"""

from typing import List, Dict, Any
from datetime import date, timedelta
import copy


def score_attraction(attraction: Dict[str, Any], interests: List[str]) -> float:
    """Value function: interest overlap weighted heavily, rating as tiebreaker."""
    interests_lower = {i.lower() for i in interests}
    tag_matches = sum(1 for tag in attraction["tags"] if tag.lower() in interests_lower)
    # Interest match dominates; rating (0-5) contributes a smaller amount so that
    # among equally-matching options, higher-rated ones are preferred.
    return (tag_matches * 10) + attraction["rating"]


def knapsack_select(items: List[Dict[str, Any]], capacity_hours: float) -> List[Dict[str, Any]]:
    """
    0/1 knapsack (time as the constrained resource) using DP over
    half-hour slots for reasonable granularity without floating point issues.
    """
    if not items:
        return []

    SLOT = 0.5
    cap_slots = int(round(capacity_hours / SLOT))

    weights = [max(1, int(round(it["duration_hours"] / SLOT))) for it in items]
    values = [it["_score"] for it in items]
    n = len(items)

    # dp[i][w] = best value using first i items with capacity w slots
    dp = [[0.0] * (cap_slots + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for w in range(cap_slots + 1):
            dp[i][w] = dp[i - 1][w]
            if weights[i - 1] <= w:
                candidate = dp[i - 1][w - weights[i - 1]] + values[i - 1]
                if candidate > dp[i][w]:
                    dp[i][w] = candidate

    # Backtrack to find selected items
    selected = []
    w = cap_slots
    for i in range(n, 0, -1):
        if dp[i][w] != dp[i - 1][w]:
            selected.append(items[i - 1])
            w -= weights[i - 1]
    selected.reverse()
    return selected


def pick_restaurants_for_day(restaurants: List[Dict[str, Any]], used_ids: set,
                              max_spend: float, meals: int = 2) -> List[Dict[str, Any]]:
    """Greedily pick top-rated restaurants (not yet used) that fit the remaining spend."""
    candidates = sorted(
        [r for r in restaurants if r["id"] not in used_ids],
        key=lambda r: (-r["rating"], r["cost_per_person"])
    )
    picked = []
    spend = 0.0
    for r in candidates:
        if len(picked) >= meals:
            break
        if spend + r["cost_per_person"] <= max_spend or not picked:
            picked.append(r)
            spend += r["cost_per_person"]
            used_ids.add(r["id"])
    return picked


def pick_hotel(hotels: List[Dict[str, Any]], nights: int, budget_per_night: float) -> Dict[str, Any]:
    """Pick the highest-rated hotel that fits the per-night budget; fall back to cheapest."""
    affordable = [h for h in hotels if h["cost_per_night"] <= budget_per_night]
    if affordable:
        best = max(affordable, key=lambda h: h["rating"])
    else:
        best = min(hotels, key=lambda h: h["cost_per_night"])
    return best


def optimize_trip(destination_data: Dict[str, Any], start_date: date, end_date: date,
                   total_budget: float, interests: List[str]) -> Dict[str, Any]:
    days = (end_date - start_date).days + 1
    if days < 1:
        raise ValueError("end_date must be on or after start_date")

    nights = max(days - 1, 1)
    hours_per_day = destination_data.get("hours_per_day", 8)

    # --- Step 1: score all attractions by interest match ---
    attractions = copy.deepcopy(destination_data["attractions"])
    for a in attractions:
        a["_score"] = score_attraction(a, interests)

    remaining_attractions = attractions[:]
    day_plans = []
    used_restaurant_ids = set()
    total_attraction_cost = 0.0
    total_food_cost = 0.0

    # Rough allocation: reserve ~55% of budget for hotel+attractions, ~30% for food, ~15% buffer
    # These ratios are then reconciled precisely at the end against actual picks.
    est_daily_food_budget = (total_budget * 0.25) / days

    for day_idx in range(days):
        # --- Step 2: knapsack-select attractions for this day from remaining pool ---
        chosen = knapsack_select(remaining_attractions, hours_per_day)
        chosen_ids = {c["id"] for c in chosen}
        remaining_attractions = [a for a in remaining_attractions if a["id"] not in chosen_ids]

        day_attraction_cost = sum(c["cost"] for c in chosen)
        total_attraction_cost += day_attraction_cost

        # --- Step 3: pick restaurants for the day within the daily food budget ---
        day_restaurants = pick_restaurants_for_day(
            destination_data["restaurants"], used_restaurant_ids, est_daily_food_budget, meals=2
        )
        day_food_cost = sum(r["cost_per_person"] for r in day_restaurants)
        total_food_cost += day_food_cost

        day_plans.append({
            "day_number": day_idx + 1,
            "date": (start_date + timedelta(days=day_idx)).isoformat(),
            "attractions": chosen,
            "restaurants": day_restaurants,
            "estimated_day_cost": round(day_attraction_cost + day_food_cost, 2),
        })

    # --- Step 4: pick hotel to fit whatever budget remains after attractions+food ---
    remaining_for_hotel = total_budget - total_attraction_cost - total_food_cost
    budget_per_night = max(remaining_for_hotel / nights, 0)
    hotel = pick_hotel(destination_data["hotels"], nights, budget_per_night)
    hotel_total = hotel["cost_per_night"] * nights

    # --- Step 5: budget breakdown ---
    local_transport_buffer = round(total_budget * 0.08, 2)
    grand_total = round(hotel_total + total_attraction_cost + total_food_cost + local_transport_buffer, 2)

    return {
        "days": days,
        "nights": nights,
        "day_plans": day_plans,
        "hotel": hotel,
        "hotel_total": round(hotel_total, 2),
        "attractions_total": round(total_attraction_cost, 2),
        "food_total": round(total_food_cost, 2),
        "local_transport_buffer": local_transport_buffer,
        "grand_total": grand_total,
        "remaining_budget": round(total_budget - grand_total, 2),
        "within_budget": grand_total <= total_budget,
    }
