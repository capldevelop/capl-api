# app/function/auth_function.py
import uuid
import httpx
import json
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from core import models, schemas
from utils.crypto_handler import crypto_handler

async def _send_api(url: str, json_data: dict) -> dict:
    """Java의 sendApi 메서드를 Python httpx로 대체"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=json_data)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            print(f"API 요청 실패: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="외부 API 통신에 실패했습니다."
            )

def phone_auth_request() -> dict:
    """
    본인인증을 요청하고, 인증사 페이지로 전달할 JSON 데이터를 생성합니다.
    """
    client_tx_id = settings.MOBILE_CLIENT_PREFIX + uuid.uuid4().hex
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    req_client_info = f"{client_tx_id}|{now_str}"

    encrypt_req_client_info = crypto_handler.create_signature(req_client_info)
    return_url = f"{settings.HOST}/api/auth/return-signup"

    json_payload = {
        "usageCode": "01001",
        "serviceId": "your_service_id",
        "encryptReqClientInfo": encrypt_req_client_info,
        "serviceType": "telcoAuth",
        "retTransferType": "MOKToken",
        "returnUrl": return_url
    }
    return json_payload

async def signup(db: Session, result_data: str) -> schemas.AuthSignupResponse:
    """
    인증 결과를 처리하고, 임시 사용자 정보를 저장한 후 응답 데이터를 반환합니다.
    """
    # ✨ [수정] JSON 파싱 전 데이터가 비어있는지 확인하는 방어 코드 추가
    if not result_data or not result_data.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증 결과 데이터(result_data)가 비어있습니다."
        )

    result_json = json.loads(result_data)
    encrypt_mok_key_token = result_json.get("encryptMOKKeyToken")
    encrypt_mok_result = result_json.get("encryptMOKResult")

    if encrypt_mok_key_token:
        request_data = {"encryptMOKKeyToken": encrypt_mok_key_token}
        response_data = await _send_api(settings.MOBILE_URL, request_data)
        encrypt_mok_result = response_data.get("encryptMOKResult")

    if not encrypt_mok_result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증 결과(encryptMOKResult)가 없습니다."
        )

    decrypted_result_str = crypto_handler.decrypt_rsa(encrypt_mok_result)
    decrpyt_result_json = json.loads(decrypted_result_str)
    
    user_name = decrpyt_result_json.get("userName")
    ci = decrpyt_result_json.get("ci")
    user_phone = decrpyt_result_json.get("userPhone")

    existing_user = db.query(models.PhoneAuthTempUser).filter(
        models.PhoneAuthTempUser.temp_user_name == user_name,
        models.PhoneAuthTempUser.temp_user_phone == user_phone
    ).first()

    if not existing_user:
        temp_user_entity = models.PhoneAuthTempUser(
            expire_at=datetime.now() + timedelta(hours=1),
            temp_user_name=user_name,
            temp_user_phone=user_phone,
            temp_user_ci=ci
        )
        db.add(temp_user_entity)
        db.commit()

    return schemas.AuthSignupResponse(name=user_name, phone=user_phone, ci=ci)
