from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core import schemas
from function import car_function
from core.dependencies import get_current_user_id

router = APIRouter(
    prefix="/car",
    tags=["Car"]
)

# 차량 등록 (일반)
@router.post("/add", summary="차량 등록", response_model=schemas.RootResponse)
def add_car(
    request: schemas.AddCarRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    car_function.add_car_to_user(db, user_id, request.car_number)
    return schemas.RootResponse.ok(None)

# 차량 등록 (주차장 차량 등록)
@router.post("/{parking_lot_id}/add", summary="주차장 차량 등록", response_model=schemas.RootResponse)
def add_car_in_parking(
    request: schemas.AddCarRequest,
    parking_lot_id: int = Path(..., description="주차장 ID"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    car_function.add_car_to_parking_lot(db, user_id, parking_lot_id, request.car_number)
    return schemas.RootResponse.ok(None)

# 주차장 등록 차량 목록 조회 (전체)
@router.get("/parking-lot/list", summary="주차장 등록 차량 목록 조회", response_model=schemas.RootResponse[List[schemas.CarResponse]])
def list_parking_lot_car(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    car_list = car_function.get_all_registered_cars_for_user(db, user_id)
    return schemas.RootResponse.ok(car_list)

# 내 차량 목록 조회
@router.get("/list", summary="내 차량 목록 조회", response_model=schemas.RootResponse[List[schemas.CarResponse]])
def list_my_car(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    car_list = car_function.get_user_car_list(db, user_id)
    return schemas.RootResponse.ok(car_list)

# 주차장 등록 차량 목록 조회 (특정 주차장)
@router.get("/{parking_lot_id}/list", summary="주차장 등록 내 차량 목록 조회", response_model=schemas.RootResponse[List[schemas.CarResponse]])
def list_car_in_parking(
    parking_lot_id: int = Path(..., description="주차장 ID"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    car_list = car_function.get_user_car_list_in_parking_lot(db, user_id, parking_lot_id)
    return schemas.RootResponse.ok(car_list)

# 차량 삭제
@router.delete("/{car_id}/delete", summary="차량 삭제", response_model=schemas.RootResponse)
def delete_car(
    car_id: int = Path(..., description="차량 ID"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    car_function.remove_car_from_user(db, user_id, car_id)
    return schemas.RootResponse.ok(None)

