# app/router/notice.py
from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import math

from core.database import get_db
from core import schemas
from function import notice_function, parking_lot_function
from core.dependencies import get_current_user_id

router = APIRouter(
    prefix="/notice", 
    tags=["Notice"]
)

# # (가정) Spring의 @RequestAttribute를 대체하는 의존성
# async def get_current_user_id(request: Request) -> int:
#     return 1

@router.put("/edit", summary="공지 수정", response_model=schemas.RootResponse)
def edit_notice(
    request: schemas.EditNoticeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    notice_function.edit_notice(
        db, user_id, request.parking_lot_id, request.notice_id,
        request.notice_title, request.notice_content
    )
    return schemas.RootResponse.ok(None)

@router.post("/add", summary="공지 등록", response_model=schemas.RootResponse)
def add_notice(
    request: schemas.AddNoticeRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    notice_function.add_notice(
        db, background_tasks, user_id, request.parking_lot_id, 
        request.notice_title, request.notice_content
    )
    return schemas.RootResponse.ok(None)

@router.get("/list", summary="공지 목록 조회")
def find_notice_list(
    parking_lot_id: int = Query(..., alias="parking_lot_id", description="주차장ID"),
    page: int = Query(1, description="페이지"),
    limit: int = Query(10, description="개수"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    
    notice_list, total_count = notice_function.get_notice_list(db, parking_lot_id, page, limit)
    
    page_info = schemas.PageInfo(
        page_number=page,
        page_size=limit,
        total_pages=math.ceil(total_count / limit) if limit > 0 else 0,
        total_content_count=total_count,
        content=[schemas.NoticeDomain.from_orm(notice) for notice in notice_list]
    )
    return schemas.RootResponse.ok(page_info)

@router.delete("/delete", summary="공지 삭제", response_model=schemas.RootResponse)
def delete_notice(
    request: schemas.DeleteNoticeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    notice_function.delete_notice(db, user_id, request.parking_lot_id, request.notice_id)
    return schemas.RootResponse.ok(None)
