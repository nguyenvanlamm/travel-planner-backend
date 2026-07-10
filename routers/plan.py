from fastapi import APIRouter, HTTPException
from models.schemas import TravelInput, TravelPlan
from services.planner import generate_plan, get_supported_destinations

router = APIRouter(prefix="/api", tags=["travel"])


@router.get("/destinations")
def list_destinations():
    return {"destinations": get_supported_destinations()}


@router.post("/plan", response_model=TravelPlan)
def create_plan(input_data: TravelInput):
    try:
        return generate_plan(input_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
