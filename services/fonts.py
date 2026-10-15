"""카드뉴스·쇼츠 렌더러가 함께 쓰는 한글 폰트 로더와 픽셀 기준 줄바꿈 유틸리티"""
import os
from functools import lru_cache
from typing import List, Optional, Tuple
from PIL import ImageFont

# (경로, {굵기: ttc 인덱스 또는 별도 파일 경로})
_FONT_CANDIDATES: List[Tuple[str, dict]] = [
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", {"regular": 0, "medium": 2, "semibold": 4, "bold": 6}),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", {"regular": 0, "medium": 0,
                                                         "semibold": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                                                         "bold": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"}),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", {"regular": 1, "medium": 1,
                                                                "semibold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                                                                "bold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"}),
    ("C:/Windows/Fonts/malgun.ttf", {"regular": 0, "medium": 0,
                                     "semibold": "C:/Windows/Fonts/malgunbd.ttf", "bold": "C:/Windows/Fonts/malgunbd.ttf"}),
    ("/System/Library/Fonts/Supplemental/AppleGothic.ttf", {"regular": 0, "medium": 0, "semibold": 0, "bold": 0}),
]


def find_korean_font_path() -> Optional[str]:
    for path, _ in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


@lru_cache(maxsize=128)
def korean_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """한글 지원 폰트를 굵기별로 로드 (시스템에 없으면 Pillow 기본 폰트)"""
    for path, weights in _FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        spec = weights.get(weight, 0)
        try:
            if isinstance(spec, str):
                if os.path.exists(spec):
                    return ImageFont.truetype(spec, size, index=0 if spec.endswith(".ttf") else 1)
                spec = weights.get("regular", 0)
            return ImageFont.truetype(path, size, index=spec)
        except Exception:
            continue
    return ImageFont.load_default(size=size)


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
