# app/routers/auth.py
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Annotated

from core.database import get_db
from function import auth_function
from core import schemas

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

@router.post("/request")
def auth_request():
    # 이 함수는 변경사항 없습니다.
    return auth_function.phone_auth_request()

@router.post("/return-signup")
async def callback_auth_signup(
    request: Request, # ✨ [수정] Form() 대신 전체 Request 객체를 받습니다.
    db: Session = Depends(get_db)
):
    """본인인증 후 회원가입 처리를 위한 콜백 API"""
    
    # ✨ [수정] request 객체에서 form 데이터를 직접 파싱합니다.
    # 이 방식이 Java의 request.getParameter("data")와 가장 유사합니다.
    form_data = await request.form()
    result_data = form_data.get("data")

    # 데이터가 없는 경우 에러 처리
    if not result_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="인증 결과 'data' 파라미터가 없습니다."
        )

    # FastAPI의 form()은 자동으로 URL 디코딩을 처리하므로, Java의 URLDecoder는 필요 없습니다.
    auth_signup_response = await auth_function.signup(db=db, result_data=result_data)
    
    return schemas.RootResponse.ok(auth_signup_response)
