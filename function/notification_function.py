# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
from sqlalchemy.orm import Session
from typing import List

from core import models, schemas
from core.database import SessionLocal
# from . import parking_lot_function, login_function, user_function # 최상위 Import 제거
from service import push_manager
from service.websocket_manager import manager


# 특정 주차장의 특정 정책 활성화 여부를 확인하는 헬퍼 함수
def _is_policy_active_for_lot(db: Session, parking_lot_id: int, policy_id: int) -> bool:
    """DB에서 특정 주차장의 특정 정책 ID가 활성화되어 있는지 확인합니다."""
    setting = db.query(models.PolicySetting).filter(
        models.PolicySetting.parking_lot_id == parking_lot_id,
        models.PolicySetting.policy_id == policy_id
    ).first()
    # 설정이 존재하고, active_yn이 'Y'인 경우에만 True를 반환합니다.
    return setting is not None and setting.active_yn == models.YnType.Y


def get_parking_lot_admins(db: Session, parking_lot_id: int) -> List[int]:
    """특정 주차장의 모든 관리자 user_id 목록을 반환합니다."""
    admins = db.query(models.ParkingLotUser.user_id).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_role == models.UserRole.ADMIN,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()
    return [admin.user_id for admin in admins]

def get_notification_settings(db: Session, user_id: int, parking_lot_id: int) -> List[schemas.NotificationActive]:
    """사용자의 주차장별 알림 설정 목록을 조회합니다."""
    from . import parking_lot_function # 함수 내에서 Import
    parking_lot_function._get_parking_lot_by_id(db, parking_lot_id) # 주차장 존재 여부 검증
     
    settings = db.query(models.NotificationSetting).filter(
        models.NotificationSetting.user_id == user_id,
        models.NotificationSetting.parking_lot_id == parking_lot_id
    ).all()
     
    # 스키마의 alias를 존중하기 위해 직접 인스턴스화합니다.
    return [
        schemas.NotificationActive(
            notificationId=setting.notification_id,
            activeYn=setting.active_yn
        ) for setting in settings
    ]

def set_notification_settings(db: Session, user_id: int, parking_lot_id: int, settings_to_update: List[schemas.NotificationActive]):
    """사용자의 알림 설정을 업데이트합니다."""
    from . import parking_lot_function, user_function # 함수 내에서 Import
    # 주차장 및 사용자 존재 여부 검증
    parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    user_function.get_user_by_id(db, user_id)
     
    for setting_update in settings_to_update:
        # 복합 키를 사용하여 조회
        setting = db.query(models.NotificationSetting).filter(
            models.NotificationSetting.user_id == user_id,
            models.NotificationSetting.parking_lot_id == parking_lot_id,
            models.NotificationSetting.notification_id == setting_update.notification_id
        ).first()
         
        if setting:
            setting.active_yn = setting_update.active_yn
        else:
            # 설정이 없는 경우 새로 생성
            new_setting = models.NotificationSetting(
                user_id=user_id,
                parking_lot_id=parking_lot_id,
                notification_id=setting_update.notification_id,
                active_yn=setting_update.active_yn
            )
            db.add(new_setting)
    db.commit()

def is_notification_active(db: Session, user_id: int, parking_lot_id: int, notification_id: int) -> bool:
    """특정 알림이 활성화되어 있는지 확인합니다."""
    setting = db.query(models.NotificationSetting).filter(
        models.NotificationSetting.user_id == user_id,
        models.NotificationSetting.parking_lot_id == parking_lot_id,
        models.NotificationSetting.notification_id == notification_id
    ).first()
     
    # 설정이 없으면 활성화로 간주, 있으면 YnType.Y인지 확인
    return setting is not None and setting.active_yn == models.YnType.Y

def init_notification_settings(db: Session, user_id: int, parking_lot_id: int):
    """사용자가 주차장에 처음 가입할 때 모든 알림 설정을 기본값(활성)으로 생성합니다."""
    all_notifications = db.query(models.Notification).all()
     
    for notification in all_notifications:
        # merge를 사용하여 PK가 존재하면 무시하고, 없으면 INSERT
        new_setting = models.NotificationSetting(
            user_id=user_id,
            parking_lot_id=parking_lot_id,
            notification_id=notification.notification_id,
            active_yn=models.YnType.Y
        )
        db.merge(new_setting)
    db.commit()

def remove_all_user_settings(db: Session, user_id: int):
    """회원 탈퇴 시 사용자의 모든 알림 설정을 삭제합니다."""
    db.query(models.NotificationSetting).filter(
        models.NotificationSetting.user_id == user_id
    ).delete(synchronize_session=False)
    db.commit()

# =================================================================
# 이벤트 핸들러 (Java의 NotificationEventListener 역할)
# =================================================================

# ID 1: 주차장 근처 진입 (Geofence)
def handle_geofence_entry_event(user_id: int, parking_lot_id: int):
    """1번 알림: 주차장 근접(지오펜싱) 시 알림을 보냅니다. (백그라운드 실행용)"""
    db: Session = None
    try:
        db = SessionLocal()
        from . import parking_lot_function # 함수 내에서 Import

        # 1번 알림이 활성화되어 있는지 확인
        if is_notification_active(db, user_id, parking_lot_id, 1):
            parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
            push_manager.send_push_notification(
                db=db,
                user_id=user_id,
                title=f"{parking_lot.parking_lot_name}",
                body="주차장 근처에 오셨군요. 남은 주차자리를 확인해보세요.",
                data={"parking_lot_id": str(parking_lot_id), "type": models.NotificationType.PULL_IN.value}
            )
    except Exception as e:
        print(f"[BG_TASK_ERROR] Geofence 알림 처리 중 오류 발생: {e}")
    finally:
        if db:
            db.close()

# ID 2: 주차 완료
def handle_pull_in_event(event: schemas.PullInPushEvent):
    """2번 알림: 자동/수동 입차 완료 시 푸시 알림을 보냅니다."""
    from . import parking_lot_function # 함수 내에서 Import
    db: Session = None
    try:
        # 백그라운드 작업을 위한 새로운 DB 세션 생성
        db = SessionLocal()
        if is_notification_active(db, event.user_id, event.parking_lot_id, 2):
            parking_lot = parking_lot_function._get_parking_lot_by_id(db, event.parking_lot_id)
            title = f"{parking_lot.parking_lot_name} - {event.car_number}"
            message = "주차를 완료했어요. 정확한 주차위치와 예상 출차 시간을 확인하고 설정해주세요."
             
            push_manager.send_push_notification(
                db=db,
                user_id=event.user_id,
                title=title,
                body=message,
                data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.PARKING.value}
            )
    except Exception as e:
        print(f"[BG_TASK_ERROR] 입차 알림 처리 중 오류 발생: {e}")
    finally:
        if db:
            db.close()


# ID 3: 고정 출차 30분 전
def handle_pull_out_reminder_event(db: Session, event: schemas.ScheduledPushEvent):
    """[수정] 3번 알림: 출차 시각 30분 전 알림 (차량 번호 유무에 따라 제목 분기)"""
    from . import parking_lot_function # 함수 내에서 Import
    if is_notification_active(db, event.user_id, event.parking_lot_id, 3):
        parking_lot = parking_lot_function._get_parking_lot_by_id(db, event.parking_lot_id)
        
        # [핵심 분기 로직] car_number가 있으면 제목에 추가, 없으면 주차장 이름만 사용
        if event.car_number:
            title = f"{parking_lot.parking_lot_name} - {event.car_number}"
        else:
            title = f"{parking_lot.parking_lot_name}"

        push_manager.send_push_notification(
            db=db,
            user_id=event.user_id,
            title=title,
            body="출차 시각 30분 전입니다. 출차를 준비해주세요.",
            data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.PULL_OUT_START_TIME.value}
        )

# ID 4: 고정 출차 시간
def handle_pull_out_due_event(db: Session, event: schemas.ScheduledPushEvent):
    """[수정] 4번 알림: 출차 시각 정시 알림 (차량 번호 유무에 따라 제목 분기)"""
    from . import parking_lot_function # 함수 내에서 Import
    if is_notification_active(db, event.user_id, event.parking_lot_id, 4):
        parking_lot = parking_lot_function._get_parking_lot_by_id(db, event.parking_lot_id)
        
        # [핵심 분기 로직] car_number가 있으면 제목에 추가, 없으면 주차장 이름만 사용
        if event.car_number:
            title = f"{parking_lot.parking_lot_name} - {event.car_number}"
        else:
            title = f"{parking_lot.parking_lot_name}"

        push_manager.send_push_notification(
            db=db,
            user_id=event.user_id,
            title=title,
            body="출차 시각입니다. 출차를 준비해주세요.",
            data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.PULL_OUT_END_TIME.value}
        )

# ID 5: 채팅
def handle_chat_message_event(event: schemas.ChatMessagePushEvent):
    """ID 5: 채팅 메시지 이벤트 발생 시 푸시 알림을 보냅니다."""
    db: Session = None
    try:
        db = SessionLocal()
        from . import parking_lot_function
        
        # [추가] 현재 웹소켓에 연결된 (채팅방을 보고 있는) 사용자 ID 목록을 가져옵니다.
        active_user_ids = manager.get_connected_user_ids(event.parking_lot_id)
        
        # 채팅방에 참여중인 모든 사용자 목록 조회
        all_users_in_lot = parking_lot_function.get_chat_user_list(db, event.parking_lot_id, models.YnType.Y)

        # 알림을 받을 사용자 필터링
        recipients = []
        for user in all_users_in_lot:
            # 1. 메시지를 보낸 자신 제외
            # 2. 채팅 알림(ID: 5)을 켠 사용자
            # 3. 현재 채팅방을 보고 있지 않은 (웹소켓에 연결되지 않은) 사용자
            if (user.user_id != event.send_user_id and
                is_notification_active(db, user.user_id, event.parking_lot_id, 5) and
                user.user_id not in active_user_ids):
                recipients.append(user.user_id)

        if recipients:
            push_manager.send_push_notification_to_users(
                db=db,
                user_ids=recipients,
                title=event.parking_lot_name,
                body="새로운 메시지가 있습니다.",
                data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.CHAT.value}
            )
    except Exception as e:
        print(f"[BG_TASK_ERROR] 채팅 알림 처리 중 오류 발생: {e}")
    finally:
        if db:
            db.close()


# ID 6: 공지
def handle_notice_append_event(event: schemas.NoticeAppendPushEvent):
    """ID 6: 공지 등록 이벤트 발생 시 푸시 알림을 보냅니다."""
    db: Session = None
    try:
        db = SessionLocal()
        from . import parking_lot_function
        
        parking_lot = parking_lot_function._get_parking_lot_by_id(db, event.parking_lot_id)
        
        # 주차장에 가입된 모든 사용자 목록 조회 (내부용 함수 대신 직접 쿼리)
        joined_users = db.query(models.ParkingLotUser).filter(
            models.ParkingLotUser.parking_lot_id == event.parking_lot_id,
            models.ParkingLotUser.del_yn == models.YnType.N,
            models.ParkingLotUser.accept_yn == models.YnType.Y
        ).all()

        recipients = []
        for user in joined_users:
            # 공지를 작성한 자신을 제외하고, 공지 알림(ID: 6)이 활성화된 사용자만 추가
            if user.user_id != event.create_by and is_notification_active(db, user.user_id, event.parking_lot_id, 6):
                recipients.append(user.user_id)
        
        if recipients:
            push_manager.send_push_notification_to_users(
                db=db,
                user_ids=recipients,
                title=parking_lot.parking_lot_name,
                body="새로운 공지가 있어요. 확인해보세요.",
                data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.NOTICE.value}
            )
    except Exception as e:
        print(f"[BG_TASK_ERROR] 공지 알림 처리 중 오류 발생: {e}")
    finally:
        if db:
            db.close()


# ID 7: 투표
def handle_vote_append_event(event: schemas.VoteAppendPushEvent):
    """ID 7: 투표 등록 이벤트 발생 시 푸시 알림을 보냅니다."""
    db: Session = None
    try:
        db = SessionLocal()
        from . import parking_lot_function
        
        parking_lot = parking_lot_function._get_parking_lot_by_id(db, event.parking_lot_id)

        # 주차장에 가입된 모든 사용자 목록 조회
        joined_users = db.query(models.ParkingLotUser).filter(
            models.ParkingLotUser.parking_lot_id == event.parking_lot_id,
            models.ParkingLotUser.del_yn == models.YnType.N,
            models.ParkingLotUser.accept_yn == models.YnType.Y
        ).all()

        recipients = []
        for user in joined_users:
            # 투표를 등록한 자신을 제외하고, 투표 알림(ID: 7)이 활성화된 사용자만 추가
            if user.user_id != event.create_by and is_notification_active(db, user.user_id, event.parking_lot_id, 7):
                recipients.append(user.user_id)

        if recipients:
            push_manager.send_push_notification_to_users(
                db=db,
                user_ids=recipients,
                title=parking_lot.parking_lot_name,
                body="새로운 투표가 있어요. 투표해주세요.",
                data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.VOTE.value}
            )
    except Exception as e:
        print(f"[BG_TASK_ERROR] 투표 알림 처리 중 오류 발생: {e}")
    finally:
        if db:
            db.close()

# ID 8: 주차 정책
def handle_policy_violation_event(event: schemas.PolicyViolationPushEvent):
    """8번 알림: 주차장 정책 활성화 여부 확인 후, 알림 설정 사용자에게만 알림"""
    db: Session = None
    try:
        db = SessionLocal()
        from . import parking_lot_function

        # 1. 정책 유형(reason)에 따라 정책 ID와 메시지 본문을 결정합니다.
        if event.reason == "MULTIPLE_PARKING":
            policy_id_to_check = 1
            body = f"{event.user_nickname} 님이 2대 이상 주차했어요."
        elif event.reason == "PARKING_LOT_FULL":
            policy_id_to_check = 2
            body = f"주차장이 만차에요. 주차 현황을 확인해보세요."
        else:
            print(f"알 수 없는 정책 위반 유형입니다: {event.reason}")
            return

        # 2. 해당 주차장에서 이 특정 정책(1번 또는 2번)이 활성화되어 있는지 확인합니다.
        if not _is_policy_active_for_lot(db, event.parking_lot_id, policy_id_to_check):
            print(f"정책 ID {policy_id_to_check}가 주차장 {event.parking_lot_id}에 대해 비활성화되어 알림을 보내지 않습니다.")
            return

        # 3. 정책이 활성화된 경우, 알림을 보낼 대상자를 필터링합니다.
        parking_lot = parking_lot_function._get_parking_lot_by_id(db, event.parking_lot_id)
        # title = f"{parking_lot.parking_lot_name} 주차 정책 알림"
        title = parking_lot.parking_lot_name
        
        # 주차장에 속한 모든 사용자 ID를 가져옵니다.
        all_users_in_lot = db.query(models.ParkingLotUser.user_id).filter(
            models.ParkingLotUser.parking_lot_id == event.parking_lot_id,
            models.ParkingLotUser.del_yn == models.YnType.N
        ).all()
        all_user_ids = [user.user_id for user in all_users_in_lot]
        
        # 알림을 받을 사용자(ID 8번 알림을 활성화한) 목록을 필터링합니다.
        ids_to_notify = [
            user_id for user_id in all_user_ids 
            if is_notification_active(db, user_id, event.parking_lot_id, 8)
        ]
        
        # 4. 최종 대상자에게 알림을 전송합니다.
        if ids_to_notify:
            print(f"정책 알림(ID: {policy_id_to_check}) 전송 대상자: {ids_to_notify}")
            push_manager.send_push_notification_to_users(
                db=db,
                user_ids=ids_to_notify,
                title=title,
                body=body,
                data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.POLICY.value}
            )
        else:
            print(f"정책 알림(ID: {policy_id_to_check})을 수신할 사용자가 없습니다.")

    except Exception as e:
        import traceback
        print(f"[BG_TASK_ERROR] 정책 위반 알림 처리 중 오류 발생: {e}")
        traceback.print_exc()
    finally:
        if db:
            db.close()

# [추가] ID 9: 미등록 차량 입차 (관리자용) - 가정
def handle_unregistered_car_event(parking_lot_id: int, car_number: str):
    """ID 9: 미등록 차량 입차 시 모든 관리자에게 알림을 보냅니다."""
    db: Session = None
    try:
        db = SessionLocal()
        from . import parking_lot_function

        # 1. 해당 주차장의 모든 관리자 ID를 가져옵니다.
        admin_ids = get_parking_lot_admins(db, parking_lot_id)
        if not admin_ids:
            print(f"주차장 ID {parking_lot_id}에 관리자가 없어 알림을 보내지 않습니다.")
            return

        # # 2. 알림을 받을 관리자를 필터링합니다. (9번 알림을 활성화한 관리자만)
        # recipients = [
        #     admin_id for admin_id in admin_ids
        #     if is_notification_active(db, admin_id, parking_lot_id, 9)
        # ]
        recipients = admin_ids

        # 3. 최종 대상자에게 알림을 전송합니다.
        if recipients:
            parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
            title = f"{parking_lot.parking_lot_name}"
            body = f"[TEST] 미등록 차량 [{car_number}]이(가) 입차했어요."
            
            print(f"미등록 차량 알림 전송 대상자: {recipients}")
            push_manager.send_push_notification_to_users(
                db=db,
                user_ids=recipients,
                title=title,
                body=body,
                data={"parking_lot_id": str(parking_lot_id), "type": models.CarType.UNREGISTERED.value}
            )
        else:
            print(f"미등록 차량 알림을 수신할 관리자가 없습니다.")

    except Exception as e:
        import traceback
        print(f"[BG_TASK_ERROR] 미등록 차량 알림 처리 중 오류 발생: {e}")
        traceback.print_exc()
    finally:
        if db:
            db.close()

# 출차 이벤트 (ID와 직접적 연관 없음)
def handle_pull_out_event(event: schemas.PullOutPushEvent):
    """자동/수동 출차 이벤트 발생 시 푸시 알림을 보냅니다."""
    db: Session = None
    try:
        # 백그라운드 작업을 위한 새로운 DB 세션 생성
        db = SessionLocal()
        from . import parking_lot_function
        
        parking_lot = parking_lot_function._get_parking_lot_by_id(db, event.parking_lot_id)
        if not parking_lot:
            print(f"주차장 정보를 찾을 수 없습니다. parking_lot_id: {event.parking_lot_id}")
            return

        title = f"{parking_lot.parking_lot_name} - {event.car_number}"
        message = "차량이 출차되었습니다."
        
        # print(f"푸시 알림 전송 시도 -> User ID: {event.user_id}, Title: {title}")
        
        push_manager.send_push_notification(
            db=db,
            user_id=event.user_id,
            title=title,
            body=message,
            data={"parking_lot_id": str(event.parking_lot_id), "type": models.NotificationType.PULL_OUT.value}
        )

    except Exception as e:
        print(f"[BG_TASK_ERROR] 출차 알림 처리 중 오류 발생: {e}")
    finally:
        if db:
            db.close()
            # print("DB 세션을 닫았습니다.")

