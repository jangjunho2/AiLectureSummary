# 베이스 이미지
FROM python:3.9

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/usr/bin:${PATH}"

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사 (여기서 .env 파일도 복사됨)
COPY . .

# FFmpeg 설치 확인
RUN ffprobe -version

# 실행 시 명시적으로 .env 로드
CMD ["sh", "-c", "python -c 'from dotenv import load_dotenv; load_dotenv()' && uvicorn app.main:app --host 0.0.0.0 --port 9090"]
