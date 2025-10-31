# app/function/chat_function.py
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from core import models, schemas
from . import parking_lot_function, notification_function, car_function
from utils import s3_handler

def _get_chat_by_parking_lot_id(db: Session, parking_lot_id: int) -> models.Chat:
    """주차장 ID로 채팅방 정보를 조회합니다."""
    chat = db.query(models.Chat).filter(
        models.Chat.parking_lot_id == parking_lot_id,
        models.Chat.del_yn == models.YnType.N
    ).first()
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_CHAT")
    return chat

def _create_file(db: Session, user_id: int, file: UploadFile) -> int:
    """파일을 업로드하고 DB에 파일 정보를 저장합니다."""
    # S3 업로드 로직은 이제 주석 처리된 상태로 호출됩니다.
    file_path = s3_handler.upload_file_to_s3(file, "chat")
    
    new_file = models.File(
        origin_file_name=file.filename,
        upload_file_name=file_path.split("/")[-1],
        create_by=user_id,
        expire_at=datetime.now().replace(year=datetime.now().year + 1)
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)
    return new_file.file_id

def _create_message_internal(db: Session, user_id: int, chat_id: int, content: Optional[str], file_id: Optional[int], msg_type: models.MessageType) -> int:
    """메시지를 DB에 저장합니다."""
    new_message = models.Message(
        chat_id=chat_id,
        user_id=user_id,
        message_type=msg_type,
        content=content,
        file_id=file_id,
        send_at=datetime.now()
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    return new_message.message_id

def append_chat(db: Session, user_id: int, parking_lot_id: int):
    """주차장에 대한 채팅방을 생성합니다."""
    parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    new_chat = models.Chat(
        parking_lot_id=parking_lot_id,
        create_by=user_id,
        update_by=user_id
    )
    db.add(new_chat)
    db.commit()

def append_chat_user(db: Session, user_id: int, parking_lot_id: int):
    """주차장 가입 승인된 사용자를 채팅방에 자동으로 참여시킵니다."""
    user_in_lot = parking_lot_function._get_parking_lot_user(db, user_id, parking_lot_id)
    
    # 이미 참여중이면 아무것도 하지 않음
    if user_in_lot.chat_join_yn == models.YnType.Y:
        return
        
    user_in_lot.chat_join_yn = models.YnType.Y

    chat = _get_chat_by_parking_lot_id(db, parking_lot_id)
    content = f"{user_in_lot.user_nickname}님이 참여했습니다."
    
    _create_message_internal(
        db, user_id, chat.chat_id, content, None, models.MessageType.SYSTEM
    )

def remove_chat_user(db: Session, user_id: int, parking_lot_id: int):
    """사용자를 채팅방에서 나감 처리합니다."""
    user_in_lot = parking_lot_function._get_parking_lot_user(db, user_id, parking_lot_id)

    # 이미 나간 상태면 아무것도 하지 않음
    if user_in_lot.chat_join_yn == models.YnType.N:
        return

    user_in_lot.chat_join_yn = models.YnType.N
    
    chat = _get_chat_by_parking_lot_id(db, parking_lot_id)
    content = f"{user_in_lot.user_nickname}님이 나갔습니다."
    
    _create_message_internal(
        db, user_id, chat.chat_id, content, None, models.MessageType.SYSTEM
    )

def remove_chat(db: Session, user_id: int, parking_lot_id: int):
    """주차장의 채팅방을 논리적으로 삭제합니다."""
    chat = _get_chat_by_parking_lot_id(db, parking_lot_id)
    chat.del_yn = models.YnType.Y
    chat.update_by = user_id
    # db.commit()

def get_chat_user_list(db: Session, parking_lot_id: int, chat_join_yn: models.YnType) -> List[schemas.ChatUserResponse]:
    """채팅 참여자 목록을 조회합니다."""
    parking_lot_users = parking_lot_function.get_chat_user_list(db, parking_lot_id, chat_join_yn)
    response = []
    for user in parking_lot_users:
        cars = car_function.get_user_car_list_in_parking_lot(db, user.user_id, parking_lot_id)
        response.append(schemas.ChatUserResponse(
            userId=user.user_id,
            userNickname=user.user_nickname,
            userRole=user.user_role,
            carNumberList=[car.car_number for car in cars]
        ))
    return response

def exit_from_chat(db: Session, user_id: int, parking_lot_id: int):
    """채팅방에서 나갑니다."""
    remove_chat_user(db, user_id, parking_lot_id)
    print(f"User {user_id} exits chat for parking lot {parking_lot_id}")

def create_message(db: Session, user_id: int, parking_lot_id: int, content: Optional[str], file: Optional[UploadFile]):
    """메시지 또는 파일을 전송합니다."""
    chat = _get_chat_by_parking_lot_id(db, parking_lot_id)
    
    file_id = None
    if file:
        file_id = _create_file(db, user_id, file)

    message_id = _create_message_internal(
        db, user_id, chat.chat_id, content, file_id, 
        models.MessageType.FILE if file else models.MessageType.MESSAGE
    )

    parking_lot_function.update_last_chat_message_id(db, user_id, parking_lot_id, message_id)
    
    parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    event = schemas.ChatMessagePushEvent(
        sendUserId=user_id,
        parkingLotId=parking_lot_id,
        parkingLotName=parking_lot.parking_lot_name
    )
    notification_function.handle_chat_message_event(db, event)
    print(f"Message {message_id} created in chat {chat.chat_id}")

def get_message_list(db: Session, user_id: int, parking_lot_id: int, last_message_id: Optional[int]) -> List[schemas.MessageResponse]:
    """채팅 메시지 목록을 조회합니다."""
    # user_in_lot = parking_lot_function.get_parking_lot_user_info(db, user_id, parking_lot_id)
    # if user_in_lot.chat_join_yn == models.YnType.N:
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NOT_JOIN_CHAT")
    
    # start_message_id = last_message_id or user_in_lot.last_read_message_id
    
    # messages = db.query(models.Message).filter(...) # start_message_id 이후 메시지 조회 쿼리
    
    # if messages:
    #     parking_lot_function.update_last_chat_message_id(db, user_id, parking_lot_id, messages[-1].message_id)
        
    # ... (파일 정보 조회 및 응답 DTO 조합 로직) ...
    return [] # 임시 반환

def get_last_read_message_id(db: Session, user_id: int, parking_lot_id: int) -> Optional[int]:
    """마지막으로 읽은 메시지 ID를 조회합니다."""
    # user_in_lot = parking_lot_function.get_parking_lot_user_info(db, user_id, parking_lot_id)
    # return user_in_lot.last_read_message_id
    return 1 # 임시 반환

def invite_users_to_chat(db: Session, admin_user_id: int, parking_lot_id: int, user_id_list: List[int]):
    """사용자들을 채팅방에 초대합니다."""
    for user_id in user_id_list:
        append_chat_user(db, user_id, parking_lot_id)
