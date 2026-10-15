"""렌더링 결과물 다운로드 (웹: 첨부 파일 응답 라우트 / 데스크톱: ~/Downloads 로 복사)"""
import io
import os
import glob
import shutil
import zipfile
from datetime import datetime
from typing import Optional

PREFIX = "anmasarang"


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def card_files(exports_dir: str) -> list:
    return sorted(glob.glob(os.path.join(exports_dir, "cards", "slide_*.png")))


def shorts_file(exports_dir: str) -> Optional[str]:
    path = os.path.join(exports_dir, "shorts", "final_shorts.mp4")
    return path if os.path.exists(path) else None


def build_cards_zip(exports_dir: str) -> bytes:
    """카드뉴스 PNG 전체를 ZIP으로 묶기"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:  # PNG는 이미 압축되어 있어 재압축 생략
        for path in card_files(exports_dir):
            zf.write(path, arcname=os.path.basename(path))
    return buf.getvalue()


def register_routes(app, exports_dir: str) -> None:
    """Flet ASGI(FastAPI) 앱에 다운로드 라우트 추가. 정적 파일 마운트보다 먼저 매칭되도록 맨 앞에 삽입"""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse, Response
    from fastapi.routing import APIRoute

    def download_cards():
        if not card_files(exports_dir):
            raise HTTPException(status_code=404, detail="렌더링된 카드뉴스가 없습니다.")
        return Response(
            content=build_cards_zip(exports_dir),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{PREFIX}_cards_{stamp()}.zip"',
                     "Cache-Control": "no-store"},
        )

    def download_shorts():
        path = shorts_file(exports_dir)
        if not path:
            raise HTTPException(status_code=404, detail="렌더링된 쇼츠 영상이 없습니다.")
        return FileResponse(path, media_type="video/mp4", filename=f"{PREFIX}_shorts_{stamp()}.mp4",
                            headers={"Cache-Control": "no-store"})

    routes = [
        APIRoute("/download/cards.zip", download_cards, methods=["GET"]),
        APIRoute("/download/shorts.mp4", download_shorts, methods=["GET"]),
    ]
    for route in reversed(routes):
        app.router.routes.insert(0, route)


def save_to_downloads(exports_dir: str, kind: str) -> str:
    """데스크톱 앱 모드용: 결과물을 ~/Downloads 에 시간 표시가 붙은 이름으로 저장하고 경로 반환"""
    target_dir = os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(target_dir, exist_ok=True)
    if kind == "cards":
        dest = os.path.join(target_dir, f"{PREFIX}_cards_{stamp()}.zip")
        with open(dest, "wb") as f:
            f.write(build_cards_zip(exports_dir))
        return dest
    src = shorts_file(exports_dir)
    if not src:
        raise FileNotFoundError("렌더링된 쇼츠 영상이 없습니다.")
    dest = os.path.join(target_dir, f"{PREFIX}_shorts_{stamp()}.mp4")
    shutil.copy2(src, dest)
    return dest
