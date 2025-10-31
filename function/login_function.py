# app/function/login_function.py (AWS SNS 로직 복원)

# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
import jwt # pyjwt
from jwt import PyJWTError, ExpiredSignatureError, InvalidTokenError
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.dialects.mysql import insert as mysql_insert
from typing import Optional, Dict, Any
import httpx
import boto3 # AWS SNS 사용을 위해 boto3 다시 추가
from botocore.exceptions import ClientError # boto3 예외 처리
import re

from core import models, schemas, exceptions, constants
from core.config import settings
# from . import user_function # 최상위 Import 제거

from zoneinfo import ZoneInfo

# 한국 시간대(KST) 객체 정의
KST = ZoneInfo("Asia/Seoul")

# =================================================================
# JWT Provider Logic (기존 코드와 동일)
# =================================================================
def _create_token(user_id: int, expires_delta: timedelta) -> str:
    to_encode = {"sub": str(user_id)}
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_user_tokens(user_id: int) -> schemas.UserTokens:
    access_token_expires = timedelta(days=settings.JWT_ACCESS_EXPIRATION_DAYS)
    refresh_token_expires = timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS)
    access_token = _create_token(user_id, access_token_expires)
    refresh_token = _create_token(user_id, refresh_token_expires)
    return schemas.UserTokens(access_token=access_token, refresh_token=refresh_token)

def validate_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: No subject")
        return user_id
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except (InvalidTokenError, PyJWTError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# =================================================================
# Helper Functions (AWS SNS 로직 복원)
# =================================================================

def _upsert_login_info(db: Session, user_id: int, device_info: schemas.LoginDeviceInfo, push_token: Optional[str], push_arn: Optional[str]):
    """
    사용자 로그인 정보를 추가하거나 업데이트합니다(UPSERT).
    push_arn 필드를 다시 사용합니다.
    """
    stmt = mysql_insert(models.LoginInfo).values(
        user_id=user_id,
        login_device_uuid=device_info.login_device_uuid,
        login_device_type=device_info.login_device_type,
        login_device_name=device_info.login_device_name,
        login_device_os=device_info.login_device_os,
        push_token=push_token,
        push_arn=push_arn
    )
    on_duplicate_stmt = stmt.on_duplicate_key_update(
        login_device_type=stmt.inserted.login_device_type,
        login_device_name=stmt.inserted.login_device_name,
        login_device_os=stmt.inserted.login_device_os,
        push_token=stmt.inserted.push_token,
        push_arn=stmt.inserted.push_arn,
        create_at=datetime.now(KST)
    )
    db.execute(on_duplicate_stmt)
    db.commit()
     
def _append_login_history(db: Session, user_id: Optional[int], device_info: schemas.LoginDeviceInfo, result: str):
    history = models.LoginHistory(
        user_id=user_id if user_id else -1,
        result=result,
        login_device_uuid=device_info.login_device_uuid,
        login_device_type=device_info.login_device_type,
        login_device_name=device_info.login_device_name,
        login_device_os=device_info.login_device_os,
    )
    db.add(history)
    db.commit()

# --- AWS SNS 관련 함수 복원 ---
def _get_sns_client():
    """boto3 SNS 클라이언트를 생성합니다."""
    return boto3.client(
        'sns', 
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_SNS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SNS_SECRET_KEY
    )

def _register_device_for_push(push_token: Optional[str]) -> Optional[str]:
    """Push Token으로 AWS SNS에서 Endpoint ARN을 생성합니다."""
    if not push_token:
        return None
    try:
        sns_client = _get_sns_client()
        response = sns_client.create_platform_endpoint(
            PlatformApplicationArn=settings.AWS_SNS_ARN,
            Token=push_token
        )
        return response.get('EndpointArn')
    except ClientError as e:
        error_message = str(e)
        if 'Endpoint already exists with the same Token' in error_message:
            match = re.search(r'(arn:aws:sns[^"]+)', error_message)
            if match:
                return match.group(0)
        print(f"AWS SNS Push ARN 생성 실패: {e}")
        return None
    except Exception as e:
        print(f"Push ARN 생성 중 알 수 없는 오류 발생: {e}")
        return None
     
def _delete_push_endpoint(push_arn: Optional[str]):
    """주어진 ARN의 AWS SNS platform endpoint를 삭제합니다."""
    if not push_arn:
        return
    try:
        sns_client = _get_sns_client()
        sns_client.delete_endpoint(EndpointArn=push_arn)
    except ClientError as e:
        if e.response['Error']['Code'] != 'NotFound':
            print(f"SNS Endpoint 삭제 실패: {e}")
# -----------------------------

# =================================================================
# OAuth Provider Logic (Google, Apple 구현 추가)
# =================================================================

def _get_apple_private_key_string() -> str:
    """.env에 저장된 APPLE_KEY_PATH (파일 경로)에서 실제 키 문자열을 읽어옵니다."""
    try:
        # APPLE_KEY_PATH는 .env에 정의된 *파일 경로*입니다.
        with open(settings.APPLE_KEY_PATH, 'r') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Apple P8 키 파일을 찾을 수 없습니다. 경로: {settings.APPLE_KEY_PATH}")
        raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)
    except Exception as e:
        print(f"Apple P8 키 파일 읽기 실패: {e}")
        raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)

def _create_apple_client_secret() -> str:
    """Apple client_secret 생성을 위한 JWT를 생성합니다."""
    now = datetime.utcnow()
    headers = {
        "alg": "ES256",
        "kid": settings.APPLE_LOGIN_KEY
    }
    payload = {
        "iss": settings.APPLE_TEAM_ID,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "aud": "https://appleid.apple.com",
        "sub": settings.APPLE_CLIENT_ID,
    }
    
    try:
        # settings.APPLE_KEY_PATH의 문자열이 아닌 해당 경로에 있는 .p8 파일에서 읽은 키 문자열을 사용합니다.
        private_key_string = _get_apple_private_key_string()
        return jwt.encode(payload, private_key_string, algorithm="ES256", headers=headers)
    except Exception as e:
        print(f"Apple client secret 생성 실패: {e}")
        raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)

async def _get_kakao_user_info(code: str) -> schemas.OauthUserInfo:
    """카카오 서버와 통신하여 사용자 정보를 가져옵니다."""
    token_url = settings.KAKAO_TOKEN_URI
    user_info_url = settings.KAKAO_USER_INFO_URI
    
    async with httpx.AsyncClient() as client:
        try:
            token_response = await client.post(
                token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.KAKAO_CLIENT_ID,
                    "redirect_uri": settings.KAKAO_REDIRECT_URI,
                    "code": code,
                    "client_secret": settings.KAKAO_CLIENT_SECRET,
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")

            if not access_token:
                raise exceptions.ApiException(constants.ResponseCode.INVALID_OAUTH_TOKEN)

            user_info_response = await client.get(
                user_info_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                },
            )
            user_info_response.raise_for_status()
            user_info = user_info_response.json()
            
            social_login_id = str(user_info.get("id"))
            if not social_login_id:
                 raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)

            return schemas.OauthUserInfo(social_login_id=social_login_id)

        except httpx.HTTPStatusError as e:
            print(f"카카오 OAuth 통신 에러: {e.response.status_code} - {e.response.text}")
            raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)
        except Exception as e:
            print(f"카카오 사용자 정보 조회 실패: {e}")
            raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)

async def _get_google_user_info(code: str) -> schemas.OauthUserInfo:
    """구글 서버와 통신하여 사용자 정보를 가져옵니다."""
    token_url = settings.GOOGLE_TOKEN_URI
    user_info_url = settings.GOOGLE_USER_INFO_URI

    async with httpx.AsyncClient() as client:
        try:
            token_response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "code": code,
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")

            if not access_token:
                raise exceptions.ApiException(constants.ResponseCode.INVALID_OAUTH_TOKEN)
            
            user_info_response = await client.get(
                user_info_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info_response.raise_for_status()
            user_info = user_info_response.json()

            social_login_id = user_info.get("id")
            if not social_login_id:
                raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)
            
            return schemas.OauthUserInfo(social_login_id=str(social_login_id))

        except httpx.HTTPStatusError as e:
            print(f"구글 OAuth 통신 에러: {e.response.status_code} - {e.response.text}")
            raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)
        except Exception as e:
            print(f"구글 사용자 정보 조회 실패: {e}")
            raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)

async def _get_apple_user_info(code: str) -> schemas.OauthUserInfo:
    """애플 서버와 통신하여 사용자 정보를 가져옵니다."""
    token_url = settings.APPLE_TOKEN_URI
    keys_url = settings.APPLE_KEY_URI
    
    client_secret = _create_apple_client_secret()

    async with httpx.AsyncClient() as client:
        try:
            # 1. 토큰 요청
            token_response = await client.post(
                token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": settings.APPLE_CLIENT_ID,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.APPLE_REDIRECT_URI,
                },
            )
            token_response.raise_for_status()
            id_token = token_response.json().get("id_token")
            
            if not id_token:
                raise exceptions.ApiException(constants.ResponseCode.INVALID_OAUTH_TOKEN)

            # 2. Apple Public Key 요청 및 id_token 검증
            keys_response = await client.get(keys_url)
            keys_response.raise_for_status()
            apple_keys = keys_response.json()["keys"]
            
            header = jwt.get_unverified_header(id_token)
            key = [k for k in apple_keys if k["kid"] == header["kid"]][0]
            
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
            
            payload = jwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                audience=settings.APPLE_CLIENT_ID,
                issuer="https://appleid.apple.com",
            )
            
            social_login_id = payload.get("sub")
            if not social_login_id:
                raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)

            return schemas.OauthUserInfo(social_login_id=social_login_id)
        
        except httpx.HTTPStatusError as e:
            print(f"애플 OAuth 통신 에러: {e.response.status_code} - {e.response.text}")
            raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)
        except (InvalidTokenError, PyJWTError, IndexError, KeyError) as e:
            print(f"애플 id_token 검증 실패: {e}")
            raise exceptions.ApiException(constants.ResponseCode.INVALID_ACCESS_TOKEN)
        except Exception as e:
            print(f"애플 사용자 정보 조회 실패: {e}")
            raise exceptions.ApiException(constants.ResponseCode.FAILED_OAUTH_LOGIN)


async def get_oauth_user_info(social_type: models.SocialType, code: str) -> schemas.OauthUserInfo:
    if social_type == models.SocialType.KAKAO:
        return await _get_kakao_user_info(code)
    elif social_type == models.SocialType.GOOGLE:
        return await _get_google_user_info(code)
    elif social_type == models.SocialType.APPLE:
        return await _get_apple_user_info(code)
    else:
        raise exceptions.ApiException(constants.ResponseCode.INVALID_OAUTH_SERVICE)

# =================================================================
# Main Service Functions (AWS SNS 로직 복원)
# =================================================================

def login(db: Session, request: schemas.LoginRequest) -> schemas.UserTokens:
    from . import user_function
    user = None
    try:
        user = user_function.authenticate_phone_user(
            db,
            user_name=request.user_name,
            user_phone=request.user_phone,
            user_ci=request.user_ci
        )
        tokens = create_user_tokens(user.user_id)
        
        # push_arn 생성 로직 복원
        push_arn = _register_device_for_push(request.push_token)
        _upsert_login_info(db, user.user_id, request.login_device_info, request.push_token, push_arn)
        _append_login_history(db, user.user_id, request.login_device_info, "SUCCESS")
        return tokens
    except Exception as e:
        user_id = user.user_id if user else None
        _append_login_history(db, user_id, request.login_device_info, "FAIL")
        if isinstance(e, HTTPException):
            raise e
        else:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")

async def social_login(db: Session, request: schemas.SocialLoginRequest) -> schemas.UserTokens:
    from . import user_function
    user = None
    try:
        oauth_user_info = await get_oauth_user_info(request.social_type, request.code)
        
        user = user_function.get_user_by_social_info(db, oauth_user_info.social_login_id, request.social_type)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail={
                    "code": "USER_NOT_FOUND_SOCIAL",
                    "social_login_id": oauth_user_info.social_login_id
                }
            )

        tokens = create_user_tokens(user.user_id)
        
        # push_arn 생성 로직 복원
        push_arn = _register_device_for_push(request.push_token)
        _upsert_login_info(db, user.user_id, request.login_device_info, request.push_token, push_arn)
        _append_login_history(db, user.user_id, request.login_device_info, "SUCCESS")
        
        return tokens
    except Exception as e:
        user_id = user.user_id if user else None
        _append_login_history(db, user_id, request.login_device_info, "FAIL")
        
        if isinstance(e, HTTPException):
            raise e
        else:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred during social login.")

def sign_up(db: Session, request: schemas.SignUpRequest) -> schemas.UserTokens:
    """회원가입을 처리합니다. (AWS SNS 버전)"""
    from . import user_function
    temp_user = user_function.get_temp_user(db, request.user_name, request.user_phone)
    if not temp_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PHONE_VERIFICATION_REQUIRED")

    new_user = user_function.create_user(db, request, temp_user.temp_user_ci)
    user_function.remove_temp_user(db, temp_user.temp_user_id)

    tokens = create_user_tokens(new_user.user_id)
    
    # push_arn 생성 로직 복원
    push_arn = _register_device_for_push(request.push_token)
    _upsert_login_info(db, new_user.user_id, request.login_device_info, request.push_token, push_arn)
    _append_login_history(db, new_user.user_id, request.login_device_info, "SIGN_UP_SUCCESS")

    return tokens

def edit_user_phone(db: Session, request: schemas.EditPhoneRequest) -> schemas.UserTokens:
    """휴대폰 번호 변경 (본인인증 기반) (AWS SNS 버전)"""
    from . import user_function
    
    # 1. 새 번호로 인증받은 임시 사용자 정보를 가져옵니다.
    temp_user = user_function.get_temp_user(db, request.user_name, request.user_phone)
    
    # 2. CI 값으로 기존 사용자 계정을 찾습니다.
    user = user_function.get_user_by_ci(db, temp_user.temp_user_ci)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORIGINAL_USER_NOT_FOUND")

    # 3. 기존 사용자 정보(이름, 번호)를 새 정보로 업데이트합니다.
    user_function.update_user_info(db, user.user_id, request.user_name, request.user_phone)
    
    # 4. 임시 사용자 정보를 삭제합니다.
    user_function.remove_temp_user(db, temp_user.temp_user_id)
    
    # 5. 새 토큰을 발급하고 로그인 처리합니다.
    tokens = create_user_tokens(user.user_id)
    push_arn = _register_device_for_push(request.push_token)
    _upsert_login_info(db, user.user_id, request.login_device_info, request.push_token, push_arn)
    _append_login_history(db, user.user_id, request.login_device_info, "EDIT_PHONE_SUCCESS")
    
    return tokens

def logout(db: Session, user_id: int, device_uuid: str):
    """로그아웃 시 특정 기기의 로그인 정보를 삭제합니다. (AWS SNS 버전)"""
    login_info_to_delete = db.query(models.LoginInfo).filter(
        models.LoginInfo.user_id == user_id,
        models.LoginInfo.login_device_uuid == device_uuid
    ).first()

    if login_info_to_delete:
        # SNS Endpoint 삭제 로직 복원
        _delete_push_endpoint(login_info_to_delete.push_arn)
        db.delete(login_info_to_delete)
        db.commit()

def refresh_access_token(db: Session, refresh_token: str, request: schemas.TokenRequest) -> schemas.UserTokens:
    """토큰 갱신 (Java 로직과 동일하게 수정) (AWS SNS 버전)"""
    if not refresh_token:
        raise exceptions.AuthenticationException(constants.ResponseCode.INVALID_REFRESH_TOKEN)
        
    try:
        user_id_str = validate_token(refresh_token)
        user_id = int(user_id_str)
    except exceptions.ApiException as e:
        if e.code == constants.ResponseCode.EXPIRE_REFRESH_TOKEN.value['code']:
             # 만료된 경우, DB에서 로그인 정보 삭제 (보안 강화)
             try:
                 user_id_from_expired = int(jwt.decode(refresh_token, options={"verify_signature": False})["sub"])
                 logout(db, user_id_from_expired, request.login_device_uuid)
             except Exception:
                 pass # 디코딩 실패 등은 무시
        raise e # 예외 다시 발생

    # DB에서 해당 기기의 로그인 정보 확인
    login_info = db.query(models.LoginInfo).filter(
        models.LoginInfo.user_id == user_id,
        models.LoginInfo.login_device_uuid == request.login_device_uuid
    ).first()
    
    if not login_info:
        raise exceptions.AuthenticationException(constants.ResponseCode.INVALID_LOGIN_INFO)

    # 푸시 토큰 및 ARN 업데이트
    new_push_arn = login_info.push_arn
    if login_info.push_token != request.push_token:
        # 토큰이 변경되었으면 SNS Endpoint 업데이트
        _delete_push_endpoint(login_info.push_arn) 
        new_push_arn = _register_device_for_push(request.push_token)

    login_info.push_token = request.push_token
    login_info.push_arn = new_push_arn
    login_info.create_at = datetime.now(KST)
    db.commit()

    # 새 토큰 생성
    return create_user_tokens(user_id)

def remove_all_login_info(db: Session, user_id: int):
    """회원 탈퇴 시, 사용자의 모든 로그인 정보를 삭제합니다."""
    login_infos = db.query(models.LoginInfo).filter(models.LoginInfo.user_id == user_id).all()
    for info in login_infos:
        _delete_push_endpoint(info.push_arn)
    
    db.query(models.LoginInfo).filter(models.LoginInfo.user_id == user_id).delete()
    db.commit()