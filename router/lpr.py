from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from core import schemas
from function import lpr_function

router = APIRouter(
    prefix="/lpr",
    tags=["LPR Management"]
)

# --- API Endpoints ---
@router.post("/sync-status", summary="[LPR Client 전용] 주기적 주차 현황 동기화")
def sync_parking_status_from_lpr(
    request: schemas.LprSyncRequest,
    db: Session = Depends(get_db)
):
    """
    미니 PC(LPR 클라이언트)로부터 1시간 주기로 전체 주차면 스캔 결과를 받아
    DB의 주차 현황과 동기화합니다. (미등록 차량 등록, 위치 보정 등)
    """
    summary = lpr_function.synchronize_parking_status(db, request.park_id, request.car_list)
    return schemas.RootResponse.ok(summary)

