"""앱 경로 한곳 정리 — 개발 실행과 Flet 배포(flet build/pack) 모두에서 동작하도록.

- 읽기 전용 리소스(폰트 등): assets/  (배포 시 FLET_ASSETS_DIR)
- 쓰기 가능한 데이터(결과물·업로드·로그): 배포 앱은 앱 설치 폴더가 읽기 전용이므로
  FLET_APP_STORAGE_DATA(운영체제의 앱 데이터 폴더)를 사용, 개발 실행 시에는 프로젝트 폴더
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ASSETS_DIR = os.path.abspath(os.environ.get("FLET_ASSETS_DIR") or os.path.join(BASE_DIR, "assets"))
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")

DATA_DIR = os.path.abspath(
    os.environ.get("ANMASARANG_DATA_DIR") or os.environ.get("FLET_APP_STORAGE_DATA") or BASE_DIR
)
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
LOG_DIR = os.path.join(DATA_DIR, "logs")

for _d in (os.path.join(EXPORTS_DIR, "cards"), os.path.join(EXPORTS_DIR, "shorts"), UPLOAD_DIR, LOG_DIR):
    os.makedirs(_d, exist_ok=True)
