# app/router/login.py
from fastapi import APIRouter, Depends, Request, Response, Cookie
from sqlalchemy.orm import Session
from typing import Optional

from core.database import get_db
from core.dependencies import get_current_user_id
from core import schemas
from function import login_function

router = APIRouter(
    tags=["Login"]     # Swagger 문서 태그 지정
)

def _set_refresh_token_cookie(response: Response, refresh_token: str):
    response.set_cookie(
        key="refresh-token",
        value=refresh_token,
        max_age=604800, # 7 days
        samesite="none",
        secure=True,
        httponly=True,
        path="/"
    )

@router.put("/login/edit-phone", summary="로그인 휴대폰 번호 변경", response_model=schemas.RootResponse[schemas.LoginResponse])
def edit_phone(
    request: schemas.EditPhoneRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user_tokens = login_function.edit_user_phone(db, request)
    _set_refresh_token_cookie(response, user_tokens.refresh_token)
    return schemas.RootResponse.ok(schemas.LoginResponse(accessToken=user_tokens.access_token))

@router.post("/token", summary="토큰 갱신", response_model=schemas.RootResponse[schemas.TokenResponse])
def refresh_access_token(
    request: schemas.TokenRequest, # Java 원본과 같이 Request Body를 받도록 수정
    response: Response,
    refresh_token: Optional[str] = Cookie(None, alias="refresh-token"),
    db: Session = Depends(get_db) # DB 세션 추가
):
    # Refresh Token으로 새로운 토큰 쌍 발급
    new_tokens = login_function.refresh_access_token(db, refresh_token, request)
    
    # 새로운 Refresh Token을 쿠키에 설정
    _set_refresh_token_cookie(response, new_tokens.refresh_token)
    
    # 새로운 Access Token과 Refresh Token을 응답 본문에 반환
    return schemas.RootResponse.ok(
        schemas.TokenResponse(
            accessToken=new_tokens.access_token,
            refreshToken=new_tokens.refresh_token
        )
    )

@router.post("/sign-up", summary="회원 가입", response_model=schemas.RootResponse[schemas.LoginResponse])
def sign_up(
    request: schemas.SignUpRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user_tokens = login_function.sign_up(db, request)
    _set_refresh_token_cookie(response, user_tokens.refresh_token)
    return schemas.RootResponse.ok(schemas.LoginResponse(accessToken=user_tokens.access_token))

@router.post("/login", summary="로그인", response_model=schemas.RootResponse[schemas.LoginResponse])
def login(
    request: schemas.LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user_tokens = login_function.login(db, request)
    _set_refresh_token_cookie(response, user_tokens.refresh_token)
    return schemas.RootResponse.ok(schemas.LoginResponse(accessToken=user_tokens.access_token))

@router.post("/login/social", summary="소셜 로그인", response_model=schemas.RootResponse[schemas.LoginResponse])
async def social_login(
    request: schemas.SocialLoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user_tokens = await login_function.social_login(db, request)
    _set_refresh_token_cookie(response, user_tokens.refresh_token)
    return schemas.RootResponse.ok(schemas.LoginResponse(accessToken=user_tokens.access_token))

@router.delete("/logout", summary="로그아웃", response_model=schemas.RootResponse)
def logout(
    request: schemas.LogoutRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    login_function.logout(db, user_id, request.login_device_uuid)
    return schemas.RootResponse.ok(None)
