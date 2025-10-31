# Ubuntu LTS 기반
FROM ubuntu:22.04

# Python 설치
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# Python 라이브러리 설치 (FastAPI + Uvicorn)
RUN pip install --no-cache-dir fastapi uvicorn

# (선택) requirements.txt 있으면 복사해서 설치
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . /app

# 컨테이너 실행 시 uvicorn 서버 시작
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
