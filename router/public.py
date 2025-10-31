# app/router/public.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core import schemas
from function import parking_lot_function, public_function

router = APIRouter(prefix="/public", tags=["Public"])

@router.get("/parking_lot/list", summary="주차장 목록 검색")
def find_public_parking_lot_list(
    keyword: str = Query(..., description="검색키워드"),
    db: Session = Depends(get_db)
):
    """
    키워드로 현재 등록된 주차장을 검색하는 공개 API입니다.
    """
    # 비로그인(뷰어) 검색이므로 user_id=0을 전달합니다.
    parking_lot_list = public_function.find_parking_lot_public_list_by(db, user_id=0, keyword=keyword)
    return schemas.RootResponse.ok(parking_lot_list)


@router.get("/{parking_lot_id}/info", summary="주차장 기본 정보 조회")
def find_public_parking_lot_info(
    parking_lot_id: int,
    db: Session = Depends(get_db)
):
    """
    주차장 ID로 기본 정보를 조회하는 공개 API입니다.
    """
    # 내부 로직은 기존 함수를 그대로 재사용합니다.
    parking_lot_info = parking_lot_function.find_parking_lot_info(db, parking_lot_id)
    return schemas.RootResponse.ok(parking_lot_info)


@router.get("/{parking_lot_id}/car", summary="주차 차량 목록 조회")
def find_public_parking_list(
    parking_lot_id: int,
    db: Session = Depends(get_db)
):
    """
    주차장 ID로 현재 주차된 차량 목록을 조회하는 공개 API입니다.
    """
    from function import parking_function
    parking_list = parking_function.find_parking_list_by(db, parking_lot_id)
    return schemas.RootResponse.ok(parking_list)


@router.get("/{parking_lot_id}/layout", summary="주차장 도면 정보 조회")
def find_public_parking_lot_layout(
    parking_lot_id: int,
    db: Session = Depends(get_db)
):
    """
    주차장 ID로 도면 정보를 조회하는 공개 API입니다.
    """
    # 내부 로직은 기존 함수를 그대로 재사용합니다.
    layout = parking_lot_function.find_widget_list(db, parking_lot_id)
    return schemas.RootResponse.ok(layout)


@router.get("/{parking_lot_id}/status", summary="주차장 주차 현황 조회")
def find_public_parking_status(
    parking_lot_id: int,
    db: Session = Depends(get_db)
):
    """
    주차장 ID로 실시간 주차 현황을 조회하는 공개 API입니다.
    """
    parking_info = parking_lot_function.get_parking_info(db, parking_lot_id)
    return schemas.RootResponse.ok(parking_info)


# @router.get("/{parking_lot_id}/available", summary="[뷰어] 빈 주차면 정보 조회")
# def find_public_available_spots(
#     parking_lot_id: int,
#     db: Session = Depends(get_db)
# ):
#     """
#     주차장 ID만으로 이용 가능한 주차면 정보를 조회하는 공개 API입니다.
#     """
#     layout = parking_lot_function.find_available_widget_list(db, parking_lot_id)
#     return schemas.RootResponse.ok(layout)