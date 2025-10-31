from fastapi import FastAPI, Depends, Body, Query, UploadFile, Form, File, Request, HTTPException, APIRouter, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from core.exceptions import ApiException, AuthenticationException, AuthorizationException
from core.schemas import RootResponse

from contextlib import asynccontextmanager
import asyncio
from service.tcp_manager import start_tcp_server
from core.database import SessionLocal
from core.config import settings

from function.function import get_token_from_header, verify_token, create_dev_access_token
from service.push_manager import initialize_firebase
from router.auth import router as auth_router
from router.car import router as car_router
from router.chat import router as chat_router
from router.parking_lot import router as parking_lot_router
from router.user import router as user_router
from router.parking import router as parking_router
from router.login import router as login_router
from router.notice import router as notice_router
from router.vote import router as vote_router
from router.chat_ws import router as chat_ws_router
from router.public import router as public_router


# # FastAPI 생명주기(lifespan) 관리자 정의
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # 애플리케이션 시작 시 TCP 서버를 백그라운드 태스크로 실행합니다.
#     print("Starting TCP server...")
#     # TCP 서버가 DB를 사용할 수 있도록 DB 세션 생성 함수를 전달합니다.
#     tcp_task = asyncio.create_task(start_tcp_server(settings.TCP_HOST, settings.TCP_PORT, SessionLocal))
#     yield
#     # 애플리케이션 종료 시 TCP 서버 태스크를 정리합니다.
#     print("Stopping TCP server...")
#     tcp_task.cancel()
#     try:
#         await tcp_task
#     except asyncio.CancelledError:
#         print("TCP server task cancelled.")


# FastAPI 생명주기(lifespan) 관리자 정의
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    [수정] 애플리케이션 시작/종료 시 실행될 로직을 통합 관리합니다.
    """
    # --- 애플리케이션 시작 로직 ---
    print("="*50)
    print("[APP START] Starting application lifespan...")
    
    # 1. Firebase 초기화
    try:
        print("[APP START] Initializing Firebase...")
        initialize_firebase()
        print("[APP START] Firebase initialized successfully.")
    except Exception as e:
        print(f"[APP START ERROR] Failed to initialize Firebase: {e}")
        traceback.print_exc()

    # 2. TCP 서버 시작
    tcp_task = None
    try:
        print("[APP START] Starting TCP server...")
        tcp_task = asyncio.create_task(start_tcp_server(settings.TCP_HOST, settings.TCP_PORT, SessionLocal))
        print(f"[APP START] TCP server scheduled to run on {settings.TCP_HOST}:{settings.TCP_PORT}")
    except Exception as e:
        print(f"[APP START ERROR] Failed to start TCP server: {e}")
        traceback.print_exc()

    print("[APP START] Application startup process complete. Yielding to application.")
    print("="*50)

    yield # 애플리케이션 실행

    # --- 애플리케이션 종료 로직 ---
    print("="*50)
    print("[APP SHUTDOWN] Starting application shutdown...")
    if tcp_task and not tcp_task.done():
        print("[APP SHUTDOWN] Stopping TCP server...")
        tcp_task.cancel()
        try:
            await tcp_task
        except asyncio.CancelledError:
            print("[APP SHUTDOWN] TCP server task cancelled successfully.")
    print("[APP SHUTDOWN] Application shutdown complete.")
    print("="*50)

app = FastAPI(
    title="Capl API Server",
    openapi_url="/openapi.json",  # OpenAPI 문서 경로
    docs_url="/docs",            # Swagger UI 경로
    redoc_url="/redoc",          # ReDoc 경로
    root_path="/API",
    lifespan=lifespan
)


# # FastAPI 시작 시 Firebase 초기화
# @app.on_event("startup")
# async def startup_event():
#     initialize_firebase()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

########## Custom Exception Handlers ##########
@app.exception_handler(ApiException)
async def api_exception_handler(request: Request, exc: ApiException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=RootResponse(code=exc.code, message=exc.message, data=exc.data).model_dump(exclude_none=True)
    )

@app.exception_handler(AuthenticationException)
async def authentication_exception_handler(request: Request, exc: AuthenticationException):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=RootResponse(code=exc.code, message=exc.message).model_dump(exclude_none=True)
    )

@app.exception_handler(AuthorizationException)
async def authorization_exception_handler(request: Request, exc: AuthorizationException):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=RootResponse(code=exc.code, message=exc.message).model_dump(exclude_none=True)
    )


def custom_openapi():

    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="CAPL API",
        version="1.0.0",
        description="CAPL API documentation with JWT authentication",
        routes=app.routes,
    )
    # Security 정의 추가
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    # 기본 보안 적용
    openapi_schema["security"] = [{"BearerAuth": []}]

    # root_path 추가 (FastAPI에서 기본적으로 적용)
    if app.root_path:
        openapi_schema["servers"] = [{"url": app.root_path}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


# custom_openapi 함수를 FastAPI 앱에 적용
app.openapi = custom_openapi


@app.middleware("http")
async def global_auth_middleware(request: Request, call_next):
    exempt_routes = [
        "/API/",
        "/API/docs",
        "/API/openapi.json",
        "/API/redoc",
        "/API/static/swagger-ui.css",  # Swagger UI 정적 파일 예시
        "/API/static/swagger-ui-bundle.js",
        "/API/getGrpList",
        "/API/favicon.ico",
        "/API/auth/request",
        "/API/dev-token/", # 매개변수가 있어서 시작 경로로 지정
        "/API/viewer-token"
    ]
     # OPTIONS 요청 무시
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # WebSocket 요청 무시
    if request.scope['type'] == 'websocket':
        return await call_next(request)
    
    # 토큰 검증을 제외할 경로인지 확인
    is_exempt = False
    for route in exempt_routes:
        if request.url.path.startswith(route):
            is_exempt = True
            break
    
    # 토큰 검증을 제외할 경로
    if not is_exempt:
        
        token = request.headers.get("Authorization")
        
        if not token:
            raise HTTPException(status_code=401, detail="Token missing")
        
        # Bearer 제거
        token = token.split(" ")[1] if token.startswith("Bearer ") else token

        # 토큰 검증 및 갱신
        try:
            result = verify_token(token)
            new_token = result.get("new_token")  # 갱신된 토큰
        except HTTPException as http_exc:
            # 명시적으로 처리된 HTTPException을 JSON 응답으로 반환
            return JSONResponse(status_code=http_exc.status_code, content={"detail": http_exc.detail})
        except HTTPException as e:
            raise e

    # 요청 처리
    response = await call_next(request)

    # 갱신된 토큰이 있다면 응답 헤더에 추가
    if "new_token" in locals():
        response.headers["Authorization"] = f"Bearer {new_token}"

    return response


@app.get("/", description="Connetion Check")
def root():
    return "Capl FastAPI Server"

@app.get("/dev-token/{user_id}", description="지정한 사용자의 테스트 토큰 생성")
def create_dev_token(user_id: int):
    token = create_dev_access_token(data={"sub": str(user_id)})
    return {
        "user_id": user_id,
        "access_token": token,
        "bearer_token": f"Bearer {token}",
        "message": "Copy 'bearer_token' and paste it into Swagger's Authorize."
    }

@app.get("/viewer-token", description="뷰어용 영구 토큰 생성")
def create_viewer_token():
    """
    만료되지 않는 뷰어 전용(user_id=0) JWT 토큰을 생성합니다.
    """
    user_id = 0
    
    # 'sub' 클레임에 뷰어 ID를 넣어 토큰 생성
    token = create_dev_access_token(data={"sub": str(user_id)})
    
    return {
        "user_id": user_id,
        "access_token": token,
        "bearer_token": f"Bearer {token}",
        "message": "This is a non-expiring viewer token."
    }

# Auth
app.include_router(auth_router)

# Public
app.include_router(public_router)

# User
app.include_router(user_router)

# Car
app.include_router(car_router)

# Chat
# app.include_router(chat_router)

# Chat_ws
app.include_router(chat_ws_router)

# Parking-lot
app.include_router(parking_lot_router)

# Parking
app.include_router(parking_router)

# Login
app.include_router(login_router)

# Notice
app.include_router(notice_router)

# Vote
app.include_router(vote_router)