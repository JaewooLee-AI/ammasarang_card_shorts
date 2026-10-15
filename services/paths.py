"""앱 경로 한곳 정리 — 개발 실행과 Flet 배포(flet build/pack) 모두에서 동작하도록.

- 읽기 전용 리소스(폰트 등): assets/  (배포 시 FLET_ASSETS_DIR)
- 쓰기 가능한 데이터(결과물·업로드·로그): 배포 앱은 앱 설치 폴더가 읽기 전용이므로
  FLET_APP_STORAGE_DATA(운영체제의 앱 데이터 폴더)를 사용, 개발 실행 시에는 프로젝트 폴더
"""
import os
import sys
import subprocess

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

# flet build 로 만든 배포 앱 안에서 실행 중인지 (Flet이 FLET_PLATFORM을 설정)
IS_PACKAGED = os.environ.get("FLET_PLATFORM") is not None


def _host_exe_dir() -> str:
    """배포 앱 실행 파일(AnmasarangStudio.exe)이 있는 폴더 — 파이썬이 앱 안에 내장되어 있어 sys.executable 대신 프로세스 경로 사용"""
    if sys.platform == "win32":
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetModuleFileNameW(None, buf, len(buf)):
            return os.path.dirname(buf.value)
    return os.path.dirname(sys.executable)


def _setup_windows_bundle():
    """Windows 배포 앱: 함께 배포된 ffmpeg/ 폴더를 PATH에 추가하고, ffmpeg 호출 시 콘솔 창이 뜨지 않게 함"""
    bundled = os.path.join(_host_exe_dir(), "ffmpeg")
    if os.path.isfile(os.path.join(bundled, "ffmpeg.exe")):
        os.environ["PATH"] = bundled + os.pathsep + os.environ.get("PATH", "")

    # GUI 앱에서 콘솔 프로그램(ffmpeg)을 실행하면 호출마다 검은 창이 깜빡이므로 기본으로 CREATE_NO_WINDOW 적용
    # (asyncio.create_subprocess_exec 도 내부적으로 subprocess.Popen 을 사용)
    _popen_init = subprocess.Popen.__init__

    def _popen_init_no_window(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        _popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _popen_init_no_window


if IS_PACKAGED and sys.platform == "win32":
    _setup_windows_bundle()
