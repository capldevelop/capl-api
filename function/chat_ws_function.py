# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status
import uuid
from datetime import datetime

from core import models, schemas
from utils import s3_handler # 파일 업로드
# from . import parking_lot_function, notification_function, car_function # 최상위 Import 제거

def get_chat_user_list(db: Session, parking_lot_id: int, chat_join_yn: models.YnType) -> List[schemas.ChatUserResponse]:
    """
    DB에서 채팅 참여자 또는 미참여자 목록을 조회합니다.
    이 함수는 메시지 히스토리가 아닌, 사용자 상태 정보를 다룹니다.
    """
    from . import parking_lot_function, car_function # 함수 내에서 Import
    # parking_lot_function에서 사용자 목록을 가져옵니다.
    parking_lot_users = parking_lot_function.get_chat_user_list(db, parking_lot_id, chat_join_yn)
    response = []
    for user in parking_lot_users:
        # 각 사용자의 주차장 내 등록된 차량 정보를 가져옵니다.
        cars = car_function.get_user_car_list_in_parking_lot(db, user.user_id, parking_lot_id)
        response.append(schemas.ChatUserResponse(
            userId=user.user_id,
            userNickname=user.user_nickname,
            userRole=user.user_role,
            carNumberList=[car.car_number for car in cars]
        ))
    return response

def trigger_push_notification(db: Session, user_id: int, parking_lot_id: int):
    """
    메시지 전송 시 푸시 알림 이벤트를 트리거합니다.
    실제 메시지 내용은 저장하지 않습니다.
    """
    from . import parking_lot_function, notification_function # 함수 내에서 Import
    parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    event = schemas.ChatMessagePushEvent(
        send_user_id=user_id, # [수정] 스키마 필드명과 일치 (sendUserId -> send_user_id)
        parking_lot_id=parking_lot_id,
        parking_lot_name=parking_lot.parking_lot_name
    )
    # [수정] notification_function을 직접 호출하는 대신, 백그라운드에서 안전하게 실행되도록 이벤트 핸들러를 호출합니다.
    # 이 함수는 동기적으로 실행되므로, 실제 알림 전송은 이벤트 핸들러에서 처리합니다.
    notification_function.handle_chat_message_event(event)
    print(f"Push notification event created for parking lot {parking_lot_id} by user {user_id}")


def invite_users_to_chat(db: Session, admin_user_id: int, parking_lot_id: int, user_id_list: List[int]):
    """
    사용자들의 `chat_join_yn` 상태를 'Y'로 변경하여 채팅에 참여시킵니다.
    """
    from . import parking_lot_function # 함수 내에서 Import
    # 관리자 권한 확인
    parking_lot_function.verify_admin_role(db, admin_user_id, parking_lot_id)

    # 초대할 사용자들의 ParkingLotUser 정보를 가져옵니다.
    users_to_invite = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_id.in_(user_id_list),
        models.ParkingLotUser.del_yn == models.YnType.N,
        models.ParkingLotUser.accept_yn == models.YnType.Y # 가입이 승인된 사용자만 초대 가능
    ).all()

    if len(users_to_invite) != len(user_id_list):
        raise HTTPException(status_code=404, detail="One or more users not found or not accepted in the parking lot.")

    for user in users_to_invite:
        user.chat_join_yn = models.YnType.Y
     
    db.commit()
    print(f"Users {user_id_list} invited to chat in parking lot {parking_lot_id}")

def create_invite_system_message(db: Session, admin_user_id: int, parking_lot_id: int, invited_user_ids: List[int]) -> dict:
    """초대 시 WebSocket으로 보낼 시스템 메시지를 생성합니다."""
     
    # 초대된 사용자들의 닉네임을 조회합니다.
    invited_users = db.query(models.ParkingLotUser.user_nickname).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_id.in_(invited_user_ids)
    ).all()
     
    nicknames = [name for name, in invited_users]
     
    return {
        "messageType": "SYSTEM",
        "content": f"{', '.join(nicknames)}님이 채팅에 참여했습니다."
    }


def exit_from_chat(db: Session, user_id: int, parking_lot_id: int) -> str:
    """
    사용자의 `chat_join_yn` 상태를 'N'으로 변경하여 채팅에서 나가게 합니다.
    """
    from . import parking_lot_function # 함수 내에서 Import
    user_in_lot = parking_lot_function._get_parking_lot_user(db, user_id, parking_lot_id)
     
    if user_in_lot.chat_join_yn == models.YnType.N:
        raise HTTPException(status_code=400, detail="ALREADY_NOT_IN_CHAT")

    user_in_lot.chat_join_yn = models.YnType.N
    db.commit()
    print(f"User {user_id} exited from chat in parking lot {parking_lot_id}")
    return user_in_lot.user_nickname

def get_user_nickname(db: Session, user_id: int, parking_lot_id: int) -> str | None:
    """[추가] 특정 주차장에서 사용자의 닉네임을 조회합니다."""
    from . import parking_lot_function
    try:
        user_in_lot = parking_lot_function._get_parking_lot_user(db, user_id, parking_lot_id)
        if user_in_lot.chat_join_yn == models.YnType.N:
             return None # 채팅방 멤버가 아님
        return user_in_lot.user_nickname
    except HTTPException:
        return None # 주차장 멤버가 아님

def create_base_message(user_id: int, user_nickname: str) -> dict:
    """[추가] 모든 메시지의 기반이 되는 공통 정보를 생성합니다."""
    return {
        "messageId": str(uuid.uuid4()),
        "userId": user_id,
        "userNickname": user_nickname,
        "createdAt": datetime.now().isoformat()
    }

def create_text_message(base_message: dict, content: str) -> dict:
    """[추가] 텍스트 메시지 객체를 생성합니다."""
    base_message.update({
        "messageType": "TEXT",
        "content": content
    })
    return base_message

def create_file_message(db: Session, base_message: dict, file_path: str, original_filename: str) -> dict | None:
    """[추가] 파일 메시지 객체를 생성합니다. 다운로드용 Presigned URL을 포함합니다."""
    download_url = s3_handler.create_presigned_download_url(file_path)
    if not download_url:
        return None
    
    base_message.update({
        "messageType": "FILE",
        "content": "파일이 전송되었습니다.",
        "fileInfo": {
            "fileName": original_filename,
            "filePath": file_path,
            "downloadUrl": download_url
        }
    })
    return base_message