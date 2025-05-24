from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import tempfile
import subprocess
import os
import logging
import requests

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

KST = timezone(timedelta(hours=9))

class SummaryResponse(BaseModel):
    title: str
    aiSummary: str
    originalText: str
    duration: int
    filename: str
    timestamp: str
    thumbnailSent: bool

@app.get("/", include_in_schema=False)
async def root():
    return {"status": "ready", "mode": "OpenAI Whisper API"}

@app.post("/api/summary", response_model=SummaryResponse)
async def process_video(file: UploadFile = File(...)):
    temp_video_path = None
    temp_audio_path = None

    try:
        if not file.filename.lower().endswith(('.mp4', '.mov')):
            raise HTTPException(400, "지원하지 않는 파일 형식입니다.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            content = await file.read()
            if len(content) > 500 * 1024 * 1024:
                raise HTTPException(413, "파일 크기 초과 (최대 500MB)")
            temp_video.write(content)
            temp_video_path = temp_video.name

        # 썸네일 추출 및 Spring 서버로 전송
        try:
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", temp_video_path,
                "-ss", "00:00:01",
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
            if image_data:
                files = {
                    "file": ("thumbnail.jpg", image_data, "image/jpeg")
                }
                headers = {
                    "Authorization": f"Bearer {{your_token_here}}"  # 필요 시 토큰 삽입
                }
                spring_url = "http://backend:8080/api/lecture/upload/thumbnail"
                thumb_response = requests.post(spring_url, files=files, headers=headers)
                thumbnail_sent = thumb_response.status_code == 200
                logger.info(f"썸네일 전송 결과: {thumbnail_sent}, 코드: {thumb_response.status_code}")
            else:
                logger.warning("썸네일 이미지 데이터가 비어있음")
                thumbnail_sent = False
        except Exception as e:
            logger.warning(f"썸네일 전송 중 예외 발생: {str(e)}")
            thumbnail_sent = False

        temp_audio_path = temp_video_path + ".wav"
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", temp_video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            temp_audio_path
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        with open(temp_audio_path, "rb") as audio_file:
            api_key = os.getenv("GPT_SECRET_KEY")
            if not api_key:
                raise HTTPException(500, "OpenAI API 키 없음")

            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (file.filename, audio_file, "audio/wav")},
                data={"model": "whisper-1"}
            )

            if response.status_code != 200:
                logger.error(response.text)
                raise HTTPException(500, "Whisper API 호출 실패")

            result = response.json()
            text = result.get("text", "")

        # GPT 요약 생성 부분 (OpenAI API 호출)
        generated_text = text
        # GPT 프롬프트 전송 및 결과 처리
        api_key = os.getenv("GPT_SECRET_KEY")
        if not api_key:
            raise HTTPException(500, "OpenAI API 키 없음")

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "아래의 텍스트를 한국어로 핵심만 뽑아 3줄 이내로 요약해줘. "
                                "제목도 같이 1줄로 요약해줘. 형식은 다음과 같아:\n"
                                "제목: ...\n요약: ..."
                            )
                        },
                        {
                            "role": "user",
                            "content": text[:12000]
                        }
                    ],
                    "temperature": 0.5
                }
            )
            if response.status_code != 200:
                raise HTTPException(500, f"GPT 요약 실패: {response.text}")

            gpt_text = response.json()["choices"][0]["message"]["content"]

            if "제목:" in gpt_text and "요약:" in gpt_text:
                title = gpt_text.split("제목:")[1].split("요약:")[0].strip()
                raw_summary = gpt_text.split("요약:")[1].strip()
                summary_lines = [line.strip() for line in raw_summary.splitlines() if line.strip()]
                ai_summary = "\n".join(summary_lines[:3])
            else:
                title = "자동 생성 제목"
                ai_summary = "\n".join(gpt_text.strip().splitlines()[:3])
        except Exception as e:
            logger.error(f"GPT 처리 중 오류: {str(e)}")
            title = "요약 실패"
            ai_summary = "요약 중 오류가 발생했습니다."

        duration_sec = float(get_video_duration(temp_video_path))

        return {
            "title": title,
            "aiSummary": ai_summary,
            "originalText": text,
            "duration": int(duration_sec),
            "filename": file.filename,
            "timestamp": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "thumbnailSent": thumbnail_sent
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise HTTPException(500, "서버 오류")
    finally:
        for path in [temp_video_path, temp_audio_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

def get_video_duration(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE, text=True
        )
        return float(result.stdout.strip())
    except:
        return 0.0

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9090)
