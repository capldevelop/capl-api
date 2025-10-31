# app/routers/vote.py
from fastapi import APIRouter, Depends, Query, Path, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import math

from core.database import get_db
from core import schemas
from function import vote_function, parking_lot_function
from core.dependencies import get_current_user_id

router = APIRouter(
    prefix="/vote", 
    tags=["Vote"]
)

@router.put("/edit", summary="투표 수정")
def edit_vote(
    request: schemas.EditVoteRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    vote_function.edit_vote(db, background_tasks, user_id, request)
    return schemas.RootResponse.ok(None)

@router.post("", summary="투표하기")
def vote(
    request: schemas.VoteRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    vote_function.add_choice(db, user_id, request)
    return schemas.RootResponse.ok(None)

@router.post("/add", summary="투표 등록")
def add_vote(
    request: schemas.AddVoteRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    vote_function.add_vote(db, background_tasks, user_id, request)
    return schemas.RootResponse.ok(None)


@router.get("/list", summary="투표 목록 조회")
def find_vote_list(
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    
    vote_list_data, total_count = vote_function.get_vote_list(db, parking_lot_id, user_id, page, limit)
    
    page_info = schemas.PageInfo(
        page_number=page, 
        page_size=limit,
        total_pages=math.ceil(total_count / limit) if limit > 0 else 0,
        total_content_count=total_count,
        content=vote_list_data # vote_function에서 이미 스키마 객체로 변환됨
    )
    return schemas.RootResponse.ok(page_info)

@router.get("/{vote_id}", summary="투표 상세 조회")
def find_vote(
    vote_id: int = Path(...),
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)

    vote = vote_function.get_vote_with_details(db, vote_id, user_id)
    return schemas.RootResponse.ok(vote)


@router.get("/items/choice", summary="투표 항목 투표자 정보 조회", response_model=schemas.RootResponse[List[schemas.VoteUserResponse]])
def find_vote_item_user_list(
    vote_id: int = Query(..., alias="vote_id"),
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    vote_user_list = vote_function.get_vote_user_list(db, user_id, parking_lot_id, vote_id)
    return schemas.RootResponse.ok(vote_user_list)

@router.get("/item/list", summary="투표 항목 목록 조회", response_model=schemas.RootResponse[List[schemas.VoteItemResponse]])
def find_vote_item_list(
    vote_id: int = Query(..., alias="vote_id"),
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    vote_item_list = vote_function.get_vote_item_list(db, vote_id)
    return schemas.RootResponse.ok([schemas.VoteItemResponse.model_validate(item) for item in vote_item_list])

@router.delete("/delete", summary="투표 삭제")
def delete_vote(
    request: schemas.DeleteVoteRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    vote_function.delete_vote(db, background_tasks, user_id, request)
    return schemas.RootResponse.ok(None)

@router.delete("/cancel", summary="투표 취소")
def cancel_vote(
    request: schemas.CancelVoteRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    vote_function.remove_choice(db, user_id, request.vote_id)
    return schemas.RootResponse.ok(None)

