# app/router/chat.py
from fastapi import APIRouter, Depends, Query, Request, Form, UploadFile
from sqlalchemy.orm import Session
from typing import List, Optional, Annotated

from core.database import get_db
from core import schemas, models
from function import chat_function, notification_function
from core.dependencies import get_current_user_id

router = APIRouter(
    prefix="/chat",   # <-- Spring Boot의 @RequestMapping("/auth") 역할
    tags=["Chat"]     # Swagger 문서 태그 지정
)

# # (가정) Spring의 @RequestAttribute(value = "requestUserId")를 대체하는 의존성
# async def get_current_user_id(request: Request) -> int:
#     # 실제로는 JWT 토큰 등에서 사용자 ID를 추출해야 합니다.
#     return 92

@router.post("/send", summary="채팅 메시지 전송", response_model=schemas.RootResponse)
def send_message(
    request: schemas.SendRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    chat_function.create_message(db, user_id, request.parking_lot_id, request.message, None)
    return schemas.RootResponse.ok(None)

@router.post("/send/file", summary="채팅 파일 전송", response_model=schemas.RootResponse)
def send_file(
    file: UploadFile,
    request: schemas.SendFileRequest = Depends(),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    chat_function.create_message(db, user_id, request.parking_lot_id, None, file)
    return schemas.RootResponse.ok(None)

@router.get("/notification/active", summary="채팅 알림 활성화 여부 조회", response_model=schemas.RootResponse[schemas.ChatNotificationResponse])
def find_chat_notification_active(
    parking_lot_id: int = Query(..., alias="parking_lot_id", description="주차장ID"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    is_active = notification_function.is_notification_active(db, user_id, parking_lot_id, 5)
    active_yn = models.YnType.Y if is_active else models.YnType.N
    return schemas.RootResponse.ok(schemas.ChatNotificationResponse(activeYn=active_yn))

@router.post("/notification/active", summary="채팅 알림 설정", response_model=schemas.RootResponse)
def set_chat_notification_active(
    request: schemas.SetChatNotificationRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    notification_function.set_notification_settings(db, user_id, request.parking_lot_id, [schemas.NotificationActive(notificationId=5, activeYn=request.active_yn)])
    return schemas.RootResponse.ok(None)

@router.post("/invite", summary="채팅 참여자 추가", response_model=schemas.RootResponse)
def invite_chat(
    request: schemas.InviteChatRequest,
    admin_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    # parkingLotRoleValidator.verifyAdminRole -> 의존성으로 처리 가능
    chat_function.invite_users_to_chat(db, admin_user_id, request.parking_lot_id, request.user_id_list)
    return schemas.RootResponse.ok(None)

@router.post("/exit", summary="채팅 나가기", response_model=schemas.RootResponse)
def exit_chat(
    request: schemas.ExitChatRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    chat_function.exit_from_chat(db, user_id, request.parking_lot_id)
    return schemas.RootResponse.ok(None)

@router.get("/user/list", summary="채팅 참여자 목록 조회" ,response_model=schemas.RootResponse[List[schemas.ChatUserResponse]])
def find_chat_user_list(
    parking_lot_id: int = Query(..., alias="parking_lot_id", description="주차장ID"),
    chat_join_yn: models.YnType = Query(..., alias="chat_join_yn", description="채팅참여여부"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    # parkingLotRoleValidator.verifyUser(userId, parkingLotId); -> 의존성으로 처리 가능
    user_list = chat_function.get_chat_user_list(db, parking_lot_id, chat_join_yn)
    return schemas.RootResponse.ok(user_list)

@router.get("/list", summary="채팅 메시지 목록 조회", response_model=schemas.RootResponse[List[schemas.MessageResponse]])
def find_chat_message_list(
    parking_lot_id: int = Query(..., alias="parking_lot_id", description="주차장ID"),
    last_message_id: Optional[int] = Query(None, alias="last_message_id", description="마지막수신메시지ID"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    message_list = chat_function.get_message_list(db, user_id, parking_lot_id, last_message_id)
    return schemas.RootResponse.ok(message_list)

@router.get("/latest", summary="마지막 수신 메시지 ID 조회", response_model=schemas.RootResponse[schemas.MessageIdResponse])
def find_last_read_message_id(
    parking_lot_id: int = Query(..., alias="parking_lot_id", description="주차장ID"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    last_id = chat_function.get_last_read_message_id(db, user_id, parking_lot_id)
    return schemas.RootResponse.ok(schemas.MessageIdResponse(messageId=last_id))
