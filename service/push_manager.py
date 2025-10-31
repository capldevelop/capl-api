import os
from typing import List, Dict, Any, Optional

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy.orm import Session

from core import models
from core.config import settings

def initialize_firebase():
    """
    Firebase Admin SDK를 초기화합니다.
    환경 변수, 파일 존재 여부, 인증서 유효성을 모두 검사합니다.
    """
    # 1. 이미 초기화되었는지 확인 (가장 먼저)
    if firebase_admin._apps:
        print("[FIREBASE_INIT] Firebase 앱이 이미 초기화되어 있습니다.")
        return

    try:
        # 2. 설정 파일에서 경로 가져오기
        cred_path = settings.FIREBASE_ADMIN_SDK_PATH
        print(f"[FIREBASE_INIT] 인증서 경로를 확인합니다.")

        # 3. 파일 존재 여부 확인
        if not os.path.exists(cred_path):
            print(f"[FIREBASE_ERROR] SDK 키 파일을 찾을 수 없습니다. 경로: {cred_path}")
            return
        
        # 4. 인증서 객체 생성 및 앱 초기화 (가장 중요)
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("[FIREBASE_INIT] Firebase Admin SDK가 성공적으로 초기화되었습니다.")

    except Exception as e:
        # ValueError (파일 내용 오류), PermissionError 등 모든 예외를 잡습니다.
        print(f"[FIREBASE_CRITICAL_ERROR] Firebase SDK 초기화 중 심각한 오류 발생: {e}")
        traceback.print_exc()


def send_push_notification(db: Session, user_id: int, title: str, body: str, data: Optional[Dict[str, str]] = None):
    """
    특정 사용자 한 명에게 푸시 알림을 보냅니다.
    """
    send_push_notification_to_users(db, user_ids=[user_id], title=title, body=body, data=data)


def send_push_notification_to_users(db: Session, user_ids: List[int], title: str, body: str, data: Optional[Dict[str, str]] = None):
    """
    지정된 여러 사용자(user_ids)에게 푸시 알림을 보냅니다.
    """
    # 초기화가 안됐을 경우를 대비한 방어 코드 추가
    if not firebase_admin._apps:
        print("[PUSH_ERROR] Firebase 앱이 초기화되지 않아 푸시를 보낼 수 없습니다.")
        return
    
    try:
        if not user_ids:
            print("알림을 보낼 사용자가 없습니다.")
            return

        login_infos = db.query(models.LoginInfo).filter(
            models.LoginInfo.user_id.in_(user_ids),
            models.LoginInfo.push_token.isnot(None)
        ).all()

        if not login_infos:
            print(f"푸시 알림 대상 기기가 없습니다. (user_ids: {user_ids})")
            return

        android_tokens = [info.push_token for info in login_infos if info.login_device_type == models.LoginDeviceType.ANDROID]
        ios_tokens = [info.push_token for info in login_infos if info.login_device_type == models.LoginDeviceType.IOS]

        if not android_tokens and not ios_tokens:
            print("발송할 유효한 토큰이 없습니다.")
            return

        # [수정] data가 None일 경우를 대비하고, 모든 값을 문자열로 변환하여 안전성을 높입니다.
        safe_data = {k: str(v) for k, v in data.items()} if data else {}

        # Android 알림 전송
        if android_tokens:
            android_message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=safe_data,
                tokens=android_tokens,
                # [추가] AndroidConfig를 통해 높은 우선순위(high)를 설정합니다.
                android=messaging.AndroidConfig(
                    priority='high'
                )
            )
            # [수정] send_multicast -> send_each_for_multicast
            response = messaging.send_each_for_multicast(android_message)
            # print(f"Android 푸시 알림 전송 완료 (user_ids: {user_ids}, 성공: {response.success_count}, 실패: {response.failure_count})")
            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        print(f"  - 실패 토큰 (Android): {android_tokens[idx]}, 원인: {resp.exception}")

        # iOS 알림 전송
        if ios_tokens:
            apns_payload = messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(title=title, body=body),
                    badge=1,
                    sound="default",
                    # [추가] content-available을 1로 설정하여 앱이 백그라운드에서 깨어날 수 있도록 합니다.
                    content_available=True 
                ),
                **{k: str(v) for k, v in data.items()} # APNS 페이로드는 모든 값이 문자열이어야 할 수 있습니다.
            )
            
            ios_message = messaging.MulticastMessage(
                # iOS에서는 APNSPayload를 통해 알림이 제어되므로 notification 필드는 선택적일 수 있습니다.
                # 하지만 명확성을 위해 포함합니다.
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                apns=messaging.APNSConfig(
                    payload=apns_payload,
                    # [추가] APNs 헤더를 통해 높은 우선순위(10)를 설정합니다.
                    headers={
                        'apns-push-type': 'alert', # iOS 13 이상에서는 alert, background 타입 명시 필요
                        'apns-priority': '10'      # 10: 즉시 전송, 5: 배터리 고려하여 전송
                    }
                ),
                tokens=ios_tokens
            )
            # [수정] send_multicast -> send_each_for_multicast
            response = messaging.send_each_for_multicast(ios_message)
            # print(f"iOS 푸시 알림 전송 완료 (user_ids: {user_ids}, 성공: {response.success_count}, 실패: {response.failure_count})")
            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                         print(f"  - 실패 토큰 (iOS): {ios_tokens[idx]}, 원인: {resp.exception}")

    except Exception as e:
        import traceback
        print(f"푸시 알림 전송 중 오류 발생 (user_ids: {user_ids}): {e}")
        traceback.print_exc()
