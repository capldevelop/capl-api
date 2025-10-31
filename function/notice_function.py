# app/function/notice_function.py
from sqlalchemy.orm import Session
from typing import List, Tuple
from fastapi import HTTPException, status, BackgroundTasks

from core import models, schemas
from . import notification_function

def get_notice_list(db: Session, parking_lot_id: int, page: int, limit: int) -> Tuple[List[models.Notice], int]:
    """공지 목록을 페이지네이션하여 조회합니다."""
    if page < 1:
        page = 1
    skip = (page - 1) * limit

    query = db.query(models.Notice).filter(
        models.Notice.parking_lot_id == parking_lot_id,
        models.Notice.del_yn == models.YnType.N
    ).order_by(models.Notice.notice_id.desc())

    total_count = query.count()
    notice_list = query.offset(skip).limit(limit).all()
    
    return notice_list, total_count

def add_notice(db: Session, background_tasks: BackgroundTasks, user_id: int, parking_lot_id: int, title: str, content: str):
    """새로운 공지를 등록합니다."""
    # parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    
    new_notice = models.Notice(
        parking_lot_id=parking_lot_id,
        notice_title=title,
        notice_content=content,
        create_by=user_id,
        update_by=user_id
    )
    db.add(new_notice)
    db.commit()

    # [수정] 공지 등록 푸시 알림을 위한 백그라운드 작업 추가
    event = schemas.NoticeAppendPushEvent(
        create_by=user_id,
        parking_lot_id=parking_lot_id
    )
    background_tasks.add_task(notification_function.handle_notice_append_event, event)

def edit_notice(db: Session, user_id: int, parking_lot_id: int, notice_id: int, title: str, content: str):
    """공지를 수정합니다."""
    notice = db.query(models.Notice).filter(
        models.Notice.notice_id == notice_id,
        models.Notice.parking_lot_id == parking_lot_id,
        models.Notice.del_yn == models.YnType.N
    ).first()

    if not notice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_NOTICE")

    notice.notice_title = title
    notice.notice_content = content
    notice.update_by = user_id
    db.commit()

def delete_notice(db: Session, user_id: int, parking_lot_id: int, notice_id: int):
    """공지를 논리적으로 삭제합니다."""
    notice = db.query(models.Notice).filter(
        models.Notice.notice_id == notice_id,
        models.Notice.parking_lot_id == parking_lot_id,
        models.Notice.del_yn == models.YnType.N
    ).first()

    if not notice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_NOTICE")

    notice.del_yn = models.YnType.Y
    notice.update_by = user_id
    db.commit()

def remove_all_notices_in_lot(db: Session, user_id: int, parking_lot_id: int):
    """특정 주차장의 모든 공지를 논리적으로 삭제합니다."""
    db.query(models.Notice).filter(
        models.Notice.parking_lot_id == parking_lot_id
    ).update(
        {"del_yn": models.YnType.Y, "update_by": user_id},
        synchronize_session=False
    )
    # db.commit()
