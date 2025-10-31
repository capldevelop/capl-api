# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings # .env 값을 읽어온 설정 객체 import

# 1. DB 연결 설정
# .env 파일에 정의된 DATABASE_URL을 사용
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# SQLAlchemy 엔진 생성
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # SQLite를 사용할 경우에만 필요한 옵션
    # connect_args={"check_same_thread": False} 
    
    # 1800초(30분) 이상 사용되지 않은 커넥션은 자동으로 재연결합니다.
    pool_recycle=1800
)

# 2. DB 세션 생성
# autocommit=False: 데이터를 변경했을 때 자동으로 commit하지 않음
# autoflush=False: 세션에 변경사항이 생겨도 자동으로 flush(DB에 임시 반영)하지 않음
# bind=engine: 이 세션이 사용할 DB 엔진을 지정
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. ORM 모델의 기본 클래스 생성
# 모든 DB 모델 클래스는 이 Base 클래스를 상속받아야 함
Base = declarative_base()


# 4. FastAPI 의존성 주입을 위한 DB 세션 생성 함수
def get_db():
    """
    API 요청마다 DB 세션을 생성하고, 요청 처리가 끝나면 세션을 닫습니다.
    이 함수는 각 API 엔드포인트에서 `Depends(get_db)` 형태로 사용됩니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

