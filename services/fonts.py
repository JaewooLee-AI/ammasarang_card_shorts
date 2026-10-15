"""카드뉴스·쇼츠 렌더러가 함께 쓰는 폰트 로더와 픽셀 기준 줄바꿈 유틸리티.

폰트 역할
- display_font : 타이틀·장면 핵심 문구·강조 단어·대형 숫자·카드 헤드라인 → Gmarket Sans Bold
- korean_font  : 하단 말자막·카드 본문·표 → Pretendard(번들에 있을 때) → 시스템 한글 폰트

모든 폰트는 먼저 assets/fonts(배포 번들 포함)에서 찾고, 없을 때만 시스템 폰트를 쓴다.
디스플레이 폰트에 없는 글자(예: ✔)가 들어간 문구는 본문 폰트로 자동 대체한다.
"""
import os
from functools import lru_cache
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from services.paths import FONTS_DIR

_HOME_FONTS = os.path.join(os.path.expanduser("~"), "Library", "Fonts")


def _first_existing(*paths: str) -> Optional[str]:
    return next((p for p in paths if p and os.path.exists(p)), None)


# 디스플레이 폰트 (Gmarket Sans Bold, SIL OFL 1.1 — assets/fonts/OFL-GmarketSans.txt)
DISPLAY_FONT_PATH = _first_existing(
    os.path.join(FONTS_DIR, "GmarketSansBold.otf"),
    os.path.join(_HOME_FONTS, "GmarketSansBold.otf"),
    "/Library/Fonts/GmarketSansBold.otf",
    "C:/Windows/Fonts/GmarketSansBold.otf",
)

# 본문/자막: 번들된 Pretendard(있으면) → 시스템 한글 폰트 → 번들된 Gmarket Sans Medium
_PRETENDARD = {w: os.path.join(FONTS_DIR, f"Pretendard-{n}.otf")
               for w, n in {"regular": "Regular", "medium": "Medium", "semibold": "SemiBold", "bold": "Bold"}.items()}

# (경로, {굵기: ttc 인덱스 또는 별도 파일 경로})
_FONT_CANDIDATES: List[Tuple[str, dict]] = [
    (_PRETENDARD["regular"], {w: p for w, p in _PRETENDARD.items()}),
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", {"regular": 0, "medium": 2, "semibold": 4, "bold": 6}),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", {"regular": 0, "medium": 0,
                                                         "semibold": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                                                         "bold": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"}),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", {"regular": 1, "medium": 1,
                                                                "semibold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                                                                "bold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"}),
    ("C:/Windows/Fonts/malgun.ttf", {"regular": 0, "medium": 0,
                                     "semibold": "C:/Windows/Fonts/malgunbd.ttf", "bold": "C:/Windows/Fonts/malgunbd.ttf"}),
    (os.path.join(FONTS_DIR, "GmarketSansMedium.otf"), {"regular": 0, "medium": 0,
                                                       "semibold": os.path.join(FONTS_DIR, "GmarketSansBold.otf"),
                                                       "bold": os.path.join(FONTS_DIR, "GmarketSansBold.otf")}),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", {"regular": 0, "medium": 0, "semibold": 0, "bold": 0}),
]


def find_korean_font_path() -> Optional[str]:
    for path, _ in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


@lru_cache(maxsize=128)
def korean_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """본문·자막용 한글 폰트를 굵기별로 로드 (없으면 Pillow 기본 폰트)"""
    for path, weights in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        spec = weights.get(weight, 0)
        try:
            if isinstance(spec, str):
                if not os.path.exists(spec):
                    spec = weights.get("regular", 0)
                if isinstance(spec, str):
                    index = 1 if spec.endswith(".ttc") else 0
                    return ImageFont.truetype(spec, size, index=index)
            return ImageFont.truetype(path, size, index=spec)
        except Exception:
            continue
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=128)
def _display_font(size: int) -> Optional[ImageFont.FreeTypeFont]:
    if not DISPLAY_FONT_PATH:
        return None
    try:
        return ImageFont.truetype(DISPLAY_FONT_PATH, size)
    except Exception:
        return None


@lru_cache(maxsize=4096)
def _display_has(ch: str) -> bool:
    """디스플레이 폰트에 해당 글자가 있는지 (없는 글자는 '대체 상자'와 같은 모양으로 그려지는 것으로 판별)"""
    font = _display_font(48)
    if font is None or ch.isspace():
        return True

    def bitmap(c: str) -> bytes:
        im = Image.new("L", (72, 72), 0)
        ImageDraw.Draw(im).text((8, 4), c, font=font, fill=255)
        return im.tobytes()

    return bitmap(ch) != bitmap("\U000F0000")


def display_font(size: int, text: str = "") -> ImageFont.FreeTypeFont:
    """타이틀·강조용 Gmarket Sans Bold. 문구에 없는 글자가 있거나 폰트가 없으면 본문 굵은 폰트로 대체"""
    font = _display_font(size)
    if font is None or (text and not all(_display_has(c) for c in set(text))):
        return korean_font(size, "bold")
    return font


def wrap_text_px(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """실제 픽셀 폭 기준 줄바꿈 (단어 단위, 한 단어가 너무 길면 글자 단위로 분할)"""
    lines: List[str] = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split(" ")
        curr = ""
        for word in words:
            candidate = f"{curr} {word}" if curr else word
            if font.getlength(candidate) <= max_width:
                curr = candidate
                continue
            if curr:
                lines.append(curr)
            # 단어 자체가 한 줄보다 긴 경우 글자 단위로 분할
            curr = ""
            for ch in word:
                if font.getlength(curr + ch) <= max_width:
                    curr += ch
                else:
                    lines.append(curr)
                    curr = ch
        if curr:
            lines.append(curr)
    return lines


def text_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent
