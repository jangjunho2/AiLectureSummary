from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
import tempfile
import os
import logging
import subprocess
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests

# 환경 변수 로드
load_dotenv()

# OpenAI 임포트
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Lecture Summary API",
    description="동영상 강의 요약 서비스",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = WhisperModel(
    model_size_or_path="base",
    device="cpu",
    compute_type="int8",
    download_root="/app/models"
)
KST = timezone(timedelta(hours=9))

class SummaryResponse(BaseModel):
    title: str
    aiSummary: str
    originalText: str
    duration: int
    filename: str
    timestamp: str
    thumbnailSent: bool = False  # 썸네일 전송 성공 여부

    class Config:
        alias_generator = None
        allow_population_by_field_name = True

api_key = os.getenv("GPT_SECRET_KEY") or os.getenv("OPENAI_API_KEY")
if api_key and OpenAI:
    client = OpenAI(api_key=api_key)
    logger.info("OpenAI 클라이언트 초기화 성공")
else:
    client = None
    logger.warning("OpenAI API 키를 찾을 수 없습니다")

def get_video_duration(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        duration_str = result.stdout.strip()
        try:
            return float(duration_str)
        except (ValueError, TypeError):
            logger.error(f"동영상 길이 문자열 변환 실패: '{duration_str}'")
            return 0.0
    except Exception as e:
        logger.error(f"동영상 길이 추출 실패: {str(e)}")
        return 0.0

def format_duration(seconds: float) -> str:
    try:
        if seconds is None or not isinstance(seconds, (int, float)) or seconds < 0:
            logger.warning(f"잘못된 동영상 길이 값: {seconds}, 0으로 처리합니다.")
            seconds = 0
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes}:{seconds:02d}"
    except Exception as e:
        logger.error(f"동영상 길이 포맷 실패: {str(e)}")
        return "0:00"

# 썸네일을 Spring 서버로 멀티파트폼 전송 (임시 파일 없이)
def send_thumbnail_to_spring_with_bytes(video_path: str, spring_url: str, timestamp: str = "00:00:01"):
    try:
        # ffmpeg로 1초 지점 썸네일 이미지를 메모리로 추출
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", timestamp,
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-"
        ]
        thumb_proc = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        image_data = thumb_proc.stdout
        if not image_data:
            logger.error(f"썸네일 추출 실패: {thumb_proc.stderr.decode(errors='ignore')}")
            return False

        files = {
            "file": ("thumbnail.jpg", image_data, "image/jpeg")
        }
        # 인증 토큰이 필요하면 여기에 추가
        headers = {
            "Authorization": f"Bearer {{your_token_here}}"  # Replace with your token logic
        }
        response = requests.post(spring_url, files=files, headers=headers)
        if response.status_code == 200:
            logger.info("썸네일을 스프링 서버로 전송 성공")
            return True
        else:
            logger.error(f"썸네일 전송 실패: {response.status_code}, {response.text}")
            return False
    except Exception as e:
        logger.error(f"썸네일 전송 중 예외 발생: {str(e)}")
        return False

@app.get("/", include_in_schema=False)
async def root():
    return {"status": "active", "model": "whisper-base", "device": "cpu"}

@app.post("/api/summary", response_model=SummaryResponse)
async def process_video(file: UploadFile = File(...)):
    temp_video_path = None
    temp_audio_path = None
    thumbnail_sent = False

    try:
        if not file.filename.lower().endswith(('.mp4', '.mov')):
            raise HTTPException(400, "지원하지 않는 파일 형식입니다.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            content = await file.read()
            if len(content) > 500 * 1024 * 1024:
                raise HTTPException(413, "파일 크기 초과 (최대 500MB)")
            temp_video.write(content)
            temp_video_path = temp_video.name

        # 썸네일 추출 및 Spring 서버로 전송 (임시 파일 없이)
        try:
            spring_url = "http://backend:8080/api/lecture/upload/thumbnail"  # 썸네일 전용 엔드포인트
            thumbnail_sent = send_thumbnail_to_spring_with_bytes(temp_video_path, spring_url)
        except Exception as e:
            logger.warning(f"썸네일 추출/전송 실패: {str(e)}")

        try:
            temp_audio_path = temp_video_path + ".wav"
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", temp_video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                "-af", "highpass=f=300,lowpass=f=3000",
                temp_audio_path
            ]
            result = subprocess.run(
                ffmpeg_cmd,
                check=True,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg 오류: {result.stderr}")
        except Exception as e:
            logger.error(f"오디오 추출 실패: {str(e)}")
            raise HTTPException(500, "오디오 추출 실패") from e

        try:
            segments, info = model.transcribe(
                audio=temp_audio_path,
                beam_size=5,
                language="ko",
                vad_filter=True
            )
            original_text = " ".join(segment.text.strip() for segment in segments)
        except Exception as e:
            logger.error(f"음성 인식 실패: {str(e)}")
            raise HTTPException(500, "음성 인식 오류") from e

        # 동영상 길이 처리
        duration_sec = 0.0
        if hasattr(info, 'duration') and info.duration and info.duration > 0:
            duration_sec = info.duration
            logger.info(f"Whisper 추출 동영상 길이: {duration_sec}초")
        else:
            duration_sec = get_video_duration(temp_video_path)
            logger.info(f"ffprobe 추출 동영상 길이: {duration_sec}초")

        if duration_sec <= 0 or not isinstance(duration_sec, (int, float)):
            logger.warning(f"유효하지 않은 동영상 길이: {duration_sec}, 0으로 설정")
            duration_sec = 0

        logger.info(f"최종 포맷된 동영상 길이(초): {duration_sec}")

        # GPT 요약 프롬프트
        title = "요약 제목 없음"
        ai_summary = "OpenAI API 키를 설정해주세요."

        if client:
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "아래의 원문 텍스트를 참고하여 "
                                "1줄 분량의 강의 제목(제목:)과 3줄 이내의 핵심 요약(요약:)을 한국어로 작성해 주세요.\n"
                                "예시 형식:\n제목: [짧은 제목]\n요약: [3줄 이내 핵심 요약]\n"
                                "절대 새로운 내용을 추가하지 말고, 원문 내용만 요약하세요."
                            )
                        },
                        {
                            "role": "user",
                            "content": original_text[:12000]
                        }
                    ],
                    temperature=0.5
                )
                generated_text = response.choices[0].message.content

                # 파싱 로직 (한국어 기준)
                if "제목:" in generated_text and "요약:" in generated_text:
                    title = generated_text.split("제목:")[1].split("요약:")[0].strip()
                    ai_summary = generated_text.split("요약:")[1].strip()
                else:
                    title = "자동 생성 제목"
                    ai_summary = generated_text

            except Exception as e:
                logger.error(f"GPT 요약 실패: {str(e)}")
                title = "요약 생성 오류"
                ai_summary = f"오류 내용: {str(e)}"

        # camelCase로 응답
        return {
            "title": title,
            "aiSummary": ai_summary,
            "originalText": original_text,
            "duration": int(duration_sec),
            "filename": file.filename,
            "timestamp": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "thumbnailSent": thumbnail_sent
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"처리 실패: {str(e)}", exc_info=True)
        raise HTTPException(500, "서버 내부 오류") from e

    finally:
        for path in [temp_video_path, temp_audio_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception as e:
                    logger.warning(f"임시 파일 삭제 실패: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9090)
