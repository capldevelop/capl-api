import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case
from typing import List, Optional, Set
from datetime import time, datetime
from collections import defaultdict
import math

from core import models, schemas
from core.config import settings


def find_parking_lot_public_list_by(db: Session, user_id: int, keyword: str) -> List[schemas.ParkingLotPublicResponse]:
    """키워드로 공개된 주차장 목록만 검색합니다."""
    parking_lots = db.query(models.ParkingLot).filter(
        (models.ParkingLot.parking_lot_name.contains(keyword)) |
        (models.ParkingLot.parking_lot_address.contains(keyword)),
        models.ParkingLot.del_yn == models.YnType.N,
        models.ParkingLot.parking_lot_public == models.YnType.Y
    ).all()
    return [schemas.ParkingLotPublicResponse.model_validate(lot) for lot in parking_lots]