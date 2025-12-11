# nutrigo-ai/Dockerfile

# 1. Python 베이스 이미지 선택 (3.11 권장)
FROM python:3.11-slim

# 2. 컨테이너 안에서 작업할 디렉토리
WORKDIR /app

# 3. 파이썬 기본 설정 (캐시 파일 안 남기기, 출력 버퍼링 끔)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. 시스템 패키지 (필요하면 여기서 추가)
#    크롤링 / playwright / tesseract 등 필요해지면 여기에 apt 패키지 더 넣으면 됨
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

# 5. 프로젝트 파일 전체 복사
#    (pyproject.toml / setup.cfg / src / nutrigo_ai 패키지 등 전부)
COPY . .

# 6. 파이썬 의존성 설치
RUN pip install -r requirements.txt

# 7. FastAPI가 띄워질 포트
EXPOSE 9000

# 8. Uvicorn으로 앱 실행
#    로컬에서 쓰던 명령: uvicorn nutrigo_ai.api.main:app --host 0.0.0.0 --port 9000
CMD ["uvicorn", "nutrigo_ai.api.main:app", "--host", "0.0.0.0", "--port", "9000"]
