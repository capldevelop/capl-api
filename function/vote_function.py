# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Tuple
from datetime import datetime
from fastapi import HTTPException, status, BackgroundTasks

from core import models, schemas
from . import notification_function, schedule_function, parking_lot_function

def _get_vote_by_id(db: Session, vote_id: int) -> models.Vote:
    """ID로 투표 정보를 조회하고 없으면 예외를 발생시킵니다."""
    vote = db.query(models.Vote).options(joinedload(models.Vote.items)).filter(
        models.Vote.vote_id == vote_id,
        models.Vote.del_yn == models.YnType.N
    ).first()
    if not vote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_VOTE")
    return vote

def get_vote_list(db: Session, parking_lot_id: int, user_id: int, page: int, limit: int) -> Tuple[List[schemas.VoteDomain], int]:
    """투표 목록을 페이지네이션하여 조회하고, 추가 정보를 포함합니다."""
    query = db.query(models.Vote).filter(
        models.Vote.parking_lot_id == parking_lot_id,
        models.Vote.del_yn == models.YnType.N
    ).order_by(models.Vote.vote_id.desc())
     
    total_count = query.count()
    vote_list = query.offset((page - 1) * limit).limit(limit).all()

    vote_ids = [v.vote_id for v in vote_list]
    if not vote_ids:
        return [], 0
         
    # 총 투표자 수 계산
    total_counts = db.query(
        models.VoteItem.vote_id,
        func.count(models.VoteChoice.user_id.distinct())
    ).join(models.VoteChoice).filter(models.VoteItem.vote_id.in_(vote_ids)).group_by(models.VoteItem.vote_id).all()
    total_counts_map = dict(total_counts)

    # 현재 사용자의 투표 여부 확인
    user_votes = db.query(models.VoteItem.vote_id).join(models.VoteChoice).filter(
        models.VoteItem.vote_id.in_(vote_ids),
        models.VoteChoice.user_id == user_id
    ).distinct().all()
    user_voted_ids = {v[0] for v in user_votes}

    # 스키마 객체로 변환
    response_list = []
    for vote in vote_list:
        vote_data = schemas.VoteDomain(
            vote_id=vote.vote_id,
            parking_lot_id=vote.parking_lot_id,
            vote_title=vote.vote_title,
            active_yn=vote.active_yn,
            multiple_yn=vote.multiple_yn,
            anonymous_yn=vote.anonymous_yn,
            end_at=vote.end_at,
            create_by=vote.create_by,
            vote_yn=models.YnType.Y if vote.vote_id in user_voted_ids else models.YnType.N,
            total_vote_count=total_counts_map.get(vote.vote_id, 0)
        )
        response_list.append(vote_data)
         
    return response_list, total_count

def get_vote_with_details(db: Session, vote_id: int, user_id: int) -> schemas.VoteDomain:
    """단일 투표 정보를 추가 정보와 함께 조회합니다."""
    vote = _get_vote_by_id(db, vote_id)
     
    total_vote_count = db.query(func.count(models.VoteChoice.user_id.distinct())).join(models.VoteItem).filter(
        models.VoteItem.vote_id == vote_id
    ).scalar() or 0

    user_voted = db.query(models.VoteChoice).join(models.VoteItem).filter(
        models.VoteItem.vote_id == vote_id,
        models.VoteChoice.user_id == user_id
    ).first() is not None

    return schemas.VoteDomain(
        vote_id=vote.vote_id,
        parking_lot_id=vote.parking_lot_id,
        vote_title=vote.vote_title,
        active_yn=vote.active_yn,
        multiple_yn=vote.multiple_yn,
        anonymous_yn=vote.anonymous_yn,
        end_at=vote.end_at,
        create_by=vote.create_by,
        vote_yn=models.YnType.Y if user_voted else models.YnType.N,
        total_vote_count=total_vote_count
    )

def get_vote_item_list(db: Session, vote_id: int) -> List[models.VoteItem]:
    """투표의 모든 항목 목록을 조회합니다."""
    vote = _get_vote_by_id(db, vote_id) # 투표 존재 여부 검증
    return vote.items

def get_vote_user_list(db: Session, user_id: int, parking_lot_id: int, vote_id: int) -> List[schemas.VoteUserResponse]:
    """투표 항목별 투표자 정보를 조회합니다."""
    from . import parking_lot_function # 함수 내에서 Import
    vote = _get_vote_by_id(db, vote_id)
     
    response_list = []
    for item in vote.items:
        # joinedload를 사용하여 N+1 문제 방지
        choices = db.query(models.VoteChoice).filter(models.VoteChoice.vote_item_id == item.vote_item_id).all()
        user_ids_who_chose = {choice.user_id for choice in choices}
         
        vote_users = []
        if vote.anonymous_yn == models.YnType.N:
            # 주차장에서 해당 유저들의 닉네임 정보를 가져옵니다.
            vote_users = parking_lot_function.get_user_info_list(db, parking_lot_id, user_ids_who_chose)

        response_list.append(schemas.VoteUserResponse(
            vote_item_id=item.vote_item_id,
            vote_yn=models.YnType.Y if user_id in user_ids_who_chose else models.YnType.N,
            vote_user_count=len(choices),
            vote_user_list=vote_users
        ))
    return response_list

def add_vote(db: Session, background_tasks: BackgroundTasks, user_id: int, request: schemas.AddVoteRequest):
    """새로운 투표를 등록합니다."""
    new_vote = models.Vote(
        parking_lot_id=request.parking_lot_id, vote_title=request.vote_title,
        multiple_yn=request.multiple_yn, anonymous_yn=request.anonymous_yn,
        end_at=request.end_at, create_by=user_id, update_by=user_id
    )
    db.add(new_vote)
    db.commit()
    db.refresh(new_vote)

    for item_content in request.vote_item_list:
        new_item = models.VoteItem(vote_id=new_vote.vote_id, content=item_content)
        db.add(new_item)
    db.commit()

    if request.end_at:
        event = schemas.ScheduleCreateEvent(
            user_id=user_id, parking_lot_id=request.parking_lot_id,
            task_type=models.TaskType.VOTE_END_AT, type_id=new_vote.vote_id,
            execute_time=request.end_at
        )
        # 스케줄 생성은 동기적으로 처리해도 무방할 수 있습니다.
        schedule_function.create_schedule(db, event)

    # 투표 등록 푸시 알림을 위한 백그라운드 작업 추가
    push_event = schemas.VoteAppendPushEvent(parking_lot_id=request.parking_lot_id, create_by=user_id)
    background_tasks.add_task(notification_function.handle_vote_append_event, push_event)

def edit_vote(db: Session, background_tasks: BackgroundTasks, user_id: int, request: schemas.EditVoteRequest):
    """투표를 수정합니다."""
    vote = _get_vote_by_id(db, request.vote_id)
    if vote.end_at and vote.end_at < datetime.now():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VOTE_ALREADY_ENDED")
     
    # 스케줄 변경 로직
    if vote.end_at != request.end_at:
        if vote.end_at:
            delete_event = schemas.ScheduleDeleteEvent(task_type=models.TaskType.VOTE_END_AT, type_id=vote.vote_id)
            schedule_function.delete_schedule(db, delete_event)
        if request.end_at:
            create_event = schemas.ScheduleCreateEvent(
                user_id=user_id, parking_lot_id=vote.parking_lot_id,
                task_type=models.TaskType.VOTE_END_AT, type_id=vote.vote_id,
                execute_time=request.end_at
            )
            schedule_function.create_schedule(db, create_event)

    vote.vote_title = request.vote_title
    vote.multiple_yn = request.multiple_yn
    vote.anonymous_yn = request.anonymous_yn
    vote.end_at = request.end_at
    vote.update_by = user_id
     
    # 1단계: 삭제할 VoteItem들의 ID를 먼저 조회합니다.
    item_ids_to_delete = db.query(models.VoteItem.vote_item_id).filter(models.VoteItem.vote_id == request.vote_id)
     
    # 2단계: 조회된 ID를 사용하여 VoteChoice 테이블의 데이터를 삭제합니다. (join 없음)
    db.query(models.VoteChoice).filter(models.VoteChoice.vote_item_id.in_(item_ids_to_delete)).delete(synchronize_session=False)

    # 3단계: VoteItem 테이블의 데이터를 삭제합니다. (join 없음)
    db.query(models.VoteItem).filter(models.VoteItem.vote_id == request.vote_id).delete(synchronize_session=False)

    db.flush() # 삭제사항 반영

    if request.vote_item_list:
        for item_content in request.vote_item_list:
            new_item = models.VoteItem(vote_id=request.vote_id, content=item_content)
            db.add(new_item)
    db.commit()

def delete_vote(db: Session, background_tasks: BackgroundTasks, user_id: int, request: schemas.DeleteVoteRequest):
    """투표를 삭제합니다."""
    vote = _get_vote_by_id(db, request.vote_id)
    if vote.end_at:
        event = schemas.ScheduleDeleteEvent(task_type=models.TaskType.VOTE_END_AT, type_id=vote.vote_id)
        schedule_function.delete_schedule(db, event)
    vote.del_yn = models.YnType.Y
    vote.update_by = user_id
    db.commit()

def add_choice(db: Session, user_id: int, request: schemas.VoteRequest):
    """투표 항목을 선택(투표)합니다."""
    vote = _get_vote_by_id(db, request.vote_id)
    if vote.active_yn == models.YnType.N or (vote.end_at and vote.end_at < datetime.now()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VOTE_IS_INACTIVE")
    if vote.multiple_yn == models.YnType.N and len(request.vote_item_id_list) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MULTIPLE_VOTING_IS_NOT_POSSIBLE")

    # 단일 선택일 경우, 기존 투표를 먼저 삭제
    if vote.multiple_yn == models.YnType.N:
        remove_choice(db, user_id, request.vote_id)

    for item_id in request.vote_item_id_list:
        # 항목이 이 투표에 속하는지 확인
        item_exists = db.query(models.VoteItem).filter(
            models.VoteItem.vote_item_id == item_id,
            models.VoteItem.vote_id == request.vote_id
        ).first()
        if not item_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"VOTE_ITEM_NOT_FOUND: {item_id}")

        new_choice = models.VoteChoice(vote_item_id=item_id, user_id=user_id)
        db.merge(new_choice) # PK가 존재하면 무시, 없으면 INSERT
    db.commit()

def remove_choice(db: Session, user_id: int, vote_id: int):
    """사용자의 투표 선택을 취소합니다."""
    vote = _get_vote_by_id(db, vote_id)
    if vote.active_yn == models.YnType.N or (vote.end_at and vote.end_at < datetime.now()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VOTE_IS_INACTIVE")
     
    # 1단계: 이 투표에 속한 항목들의 ID를 먼저 조회합니다.
    item_ids_in_vote = db.query(models.VoteItem.vote_item_id).filter(models.VoteItem.vote_id == vote_id)
     
    # 2단계: 조회된 ID와 사용자 ID를 사용하여 VoteChoice를 삭제합니다. (join 없음)
    db.query(models.VoteChoice).filter(
        models.VoteChoice.vote_item_id.in_(item_ids_in_vote),
        models.VoteChoice.user_id == user_id
    ).delete(synchronize_session=False)
    db.commit()

def remove_all_votes_in_lot(db: Session, updater_id: int, parking_lot_id: int):
    """주차장의 모든 투표를 논리적으로 삭제합니다."""
    db.query(models.Vote).filter(
        models.Vote.parking_lot_id == parking_lot_id
    ).update({"del_yn": models.YnType.Y, "update_by": updater_id}, synchronize_session=False)
    # db.commit()
