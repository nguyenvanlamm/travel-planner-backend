import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from models.schemas import TravelInput, TravelPlan
from services.planner import generate_plan, get_supported_destinations

router = APIRouter(prefix="/api", tags=["travel"])

SHARE_DIR = Path(__file__).resolve().parent.parent / "data" / "shared_plans"


@router.get("/destinations")
def list_destinations():
    return {"destinations": get_supported_destinations()}


@router.post("/plan", response_model=TravelPlan)
def create_plan(input_data: TravelInput):
    try:
        return generate_plan(input_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/share")
def share_plan(plan: TravelPlan):
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    share_id = uuid.uuid4().hex[:10]
    (SHARE_DIR / f"{share_id}.json").write_text(plan.model_dump_json(), encoding="utf-8")
    return {"id": share_id}


@router.get("/share/{share_id}", response_model=TravelPlan)
def get_shared_plan(share_id: str):
    if not re.fullmatch(r"[0-9a-f]{10}", share_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch được chia sẻ")
    path = SHARE_DIR / f"{share_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch được chia sẻ")
    return TravelPlan.model_validate_json(path.read_text(encoding="utf-8"))
