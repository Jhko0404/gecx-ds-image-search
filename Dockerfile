# Python 3.11 slim 경량 컨테이너 이미지 사용
FROM python:3.11-slim

# 표준 출력 버퍼링 비활성화 (Cloud Run 로그 실시간 출력)
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사
COPY main.py .

# Cloud Run 기본 포트
ENV PORT=8080
EXPOSE 8080

# Gunicorn 프로덕션 서버 실행
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "main:app"]
