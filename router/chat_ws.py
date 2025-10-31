from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import uuid
from datetime import datetime

from core.database import get_db, SessionLocal
from core import schemas, models
from function import notification_function, chat_ws_function
from core.dependencies import get_current_user_id, get_user_id_from_token_ws
from service.websocket_manager import manager # WebSocket 관리자 임포트
from utils import s3_handler # 파일 업로드

router = APIRouter(
    prefix="/chat_ws",
    tags=["Chat_ws"]
)

# --- 파일 업로드를 위한 Presigned URL 생성 엔드포인트 ---
@router.get("/ws/upload-url", summary="파일 업로드를 위한 Presigned URL 생성", response_model=schemas.RootResponse[schemas.FileUploadResponse])
def get_upload_url(
    parking_lot_id: int = Query(..., alias="parkingLotId"),
    filename: str = Query(..., description="원본 파일 이름"),
    user_id: int = Depends(get_current_user_id) # HTTP이므로 기존 의존성 사용
):
    """클라이언트가 S3로 직접 파일을 업로드할 수 있는 임시 URL을 발급합니다."""
    directory = f"chat/{parking_lot_id}"
    result = s3_handler.create_presigned_upload_url(directory, filename)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create upload URL")
    return schemas.RootResponse.ok(schemas.FileUploadResponse(**result))


# --- [수정] WebSocket 엔드포인트 (헤더 인증) ---
@router.websocket("/ws/{parking_lot_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    parking_lot_id: int,
    # [수정] Query 대신 Header에서 토큰을 받습니다.
    # 클라이언트는 'Authorization' 헤더에 'Bearer <token>' 형식으로 전송해야 합니다.
    authorization: Optional[str] = Header(None, description="인증을 위한 JWT 토큰 (Bearer 스킵)")
):
    
    # --- 토큰 검증 로직 ---
    if authorization is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authorization header not found")
        return

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid Authorization header format. Expected 'Bearer <token>'")
        return
    
    user_id = get_user_id_from_token_ws(token)
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return
    # --- 토큰 검증 로직 ---

    await manager.connect(websocket, parking_lot_id, user_id)
    
    db: Session = SessionLocal()
    user_nickname = None # try 블록 밖에서 선언
    try:
        user_nickname = chat_ws_function.get_user_nickname(db, user_id, parking_lot_id)
        if not user_nickname:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not in parking lot")
            return

        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                message_type = message_data.get("messageType")
                
                # [수정] function 파일에 있던 로직을 가져옵니다. (순환참조 방지)
                base_message = {
                    "messageId": str(uuid.uuid4()),
                    "userId": user_id,
                    "userNickname": user_nickname,
                    "createdAt": datetime.now().isoformat()
                }

                if message_type == "TEXT":
                    content = message_data.get("content", "")
                    full_message = chat_ws_function.create_text_message(base_message, content)
                    await manager.broadcast_to_room(json.dumps(full_message), parking_lot_id, None) 

                elif message_type == "FILE":
                    file_info = message_data.get("fileInfo", {})
                    file_path = file_info.get("filePath")
                    original_filename = file_info.get("fileName")

                    if file_path and original_filename:
                        full_message = chat_ws_function.create_file_message(db, base_message, file_path, original_filename)
                        if full_message:
                            await manager.broadcast_to_room(json.dumps(full_message), parking_lot_id, None)

                if message_type in ["TEXT", "FILE"]:
                    chat_ws_function.trigger_push_notification(db, user_id, parking_lot_id)

            except json.JSONDecodeError:
                print(f"Invalid JSON received from user {user_id}")
            except Exception as e:
                print(f"Error processing message from user {user_id}: {e}")

    except WebSocketDisconnect:
        manager.disconnect(parking_lot_id, user_id)
        if user_nickname:
            system_message = json.dumps({
                "messageType": "SYSTEM", 
                "content": f"{user_nickname}님이 나갔습니다."
            })
            await manager.broadcast_to_room(system_message, parking_lot_id, user_id) 
    finally:
        db.close()


# --- HTTP API 엔드포인트 ---
@router.get("/notification/active", summary="채팅 알림 활성화 여부 조회", response_model=schemas.RootResponse[schemas.ChatNotificationResponse])
def find_chat_notification_active(
    parking_lot_id: int = Query(..., alias="parkingLotId", description="주차장ID"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """사용자의 특정 주차장에 대한 채팅 알림 활성화 상태를 조회합니다."""
    # 알림 ID 5는 '채팅'으로 약속되어 있습니다.
    is_active = notification_function.is_notification_active(db, user_id, parking_lot_id, 5)
    active_yn = models.YnType.Y if is_active else models.YnType.N
    return schemas.RootResponse.ok(schemas.ChatNotificationResponse(activeYn=active_yn))


@router.post("/notification/active", summary="채팅 알림 설정", response_model=schemas.RootResponse)
def set_chat_notification_active(
    request: schemas.SetChatNotificationRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """사용자의 채팅 알림 설정을 변경합니다."""
    # 알림 ID 5는 '채팅'으로 약속되어 있습니다.
    settings_to_update = [schemas.NotificationActive(notificationId=5, activeYn=request.active_yn)]
    notification_function.set_notification_settings(db, user_id, request.parking_lot_id, settings_to_update)
    return schemas.RootResponse.ok(None)


@router.post("/invite", summary="채팅 참여자 추가", response_model=schemas.RootResponse)
async def invite_chat(
    request: schemas.InviteChatRequest,
    admin_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """관리자가 사용자를 채팅방에 초대합니다. (DB의 chat_join_yn 상태 변경)"""
    # 실제 DB 상태를 변경하는 로직
    chat_ws_function.invite_users_to_chat(db, admin_user_id, request.parking_lot_id, request.user_id_list)

    # 초대되었다는 시스템 메시지를 WebSocket으로 브로드캐스트합니다.
    system_message = chat_ws_function.create_invite_system_message(db, admin_user_id, request.parking_lot_id, request.user_id_list)
    await manager.broadcast_to_room(json.dumps(system_message), request.parking_lot_id, None)

    return schemas.RootResponse.ok(None)


@router.post("/exit", summary="채팅 나가기", response_model=schemas.RootResponse)
async def exit_chat(
    request: schemas.ExitChatRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """사용자가 채팅방에서 나갑니다. (DB의 chat_join_yn 상태 변경)"""
    # 실제 DB 상태를 변경하는 로직
    user_nickname = chat_ws_function.exit_from_chat(db, user_id, request.parking_lot_id)

    # 퇴장했다는 시스템 메시지를 WebSocket으로 브로드캐스트합니다.
    system_message = {
        "messageType": "SYSTEM",
        "content": f"{user_nickname}님이 채팅방을 나갔습니다."
    }
    await manager.broadcast_to_room(json.dumps(system_message), request.parking_lot_id, None)
    
    return schemas.RootResponse.ok(None)


@router.get("/user/list", summary="채팅 참여자 목록 조회", response_model=schemas.RootResponse[List[schemas.ChatUserResponse]])
def find_chat_user_list(
    parking_lot_id: int = Query(..., alias="parkingLotId", description="주차장ID"),
    chat_join_yn: models.YnType = Query(..., alias="chatJoinYn", description="채팅참여여부"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    주차장의 사용자 목록을 채팅 참여 여부에 따라 조회합니다.
    이 정보는 DB의 ParkingLotUser 테이블에서 가져옵니다.
    """
    user_list = chat_ws_function.get_chat_user_list(db, parking_lot_id, chat_join_yn)
    return schemas.RootResponse.ok(user_list)
