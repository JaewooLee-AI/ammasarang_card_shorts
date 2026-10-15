import logging
import os
import asyncio
import subprocess
import tempfile
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps
from jinja2 import Environment, FileSystemLoader, select_autoescape
from models.schema import CardSlide, EditableStoryboard, MediaAsset
from services.fonts import korean_font, display_font, wrap_text_px, text_height

HOTLINE = "1577-1398"


def normalize_table(table: Optional[dict]) -> Tuple[List[str], List[List[str]]]:
    """비교표 dict를 (헤더, 데이터 행) 형태로 정규화.

    스토리보드의 comparison_table은 {행 라벨: [값1, 값2, ...]} 구조이며
    첫 항목이 헤더 행이다. 예) {"구분": ["도입 전", "도입 후"], "부담금": ["26억 원", "21억 원"]}
    """
    if not table or not isinstance(table, dict):
        return [], []
    items = []
    for key, values in table.items():
        vals = values if isinstance(values, list) else [values]
        items.append([str(key)] + [str(v) for v in vals])
    width = max(len(r) for r in items)
    items = [r + [""] * (width - len(r)) for r in items]
    return items[0], items[1:]


class CardNewsRendererService:
    """고해상도 카드뉴스 (1080x1350) 자동 렌더링 서비스"""

    WIDTH = 1080
    HEIGHT = 1350
    MARGIN = 70

    TYPE_NAMES = {
        "cover": "핵심 이슈 브리핑",
        "body": "팩트 체크 & 분석",
        "comparison_table": "핵심 수치 비교",
        "call_to_action": "도입 신청 & 무료 상담",
    }

    def __init__(self, export_dir: str = None):
        if not export_dir:
            from services.paths import EXPORTS_DIR
            self.export_dir = os.path.join(EXPORTS_DIR, "cards")
        else:
            self.export_dir = export_dir
        os.makedirs(self.export_dir, exist_ok=True)

    async def render_all_slides(self, storyboard: EditableStoryboard) -> List[str]:
        """스토리보드의 모든 카드뉴스 슬라이드를 고화질 PNG로 렌더링"""
        self._remove_stale_outputs(len(storyboard.card_slides))
        output_paths = []
        total = len(storyboard.card_slides)
        for i, slide in enumerate(storyboard.card_slides):
            out_path = os.path.join(self.export_dir, f"slide_{i+1:02d}.png")
            photo = None
            asset = storyboard.asset(slide.asset_id)
            if asset and slide.slide_type != "comparison_table":
                photo = await asyncio.to_thread(self._load_asset_image, asset)
            if photo is not None:
                await asyncio.to_thread(self._render_photo_slide, slide, photo, i + 1, total, out_path)
            else:
                await asyncio.to_thread(self._render_single_slide, slide, i + 1, total, out_path)
            output_paths.append(out_path)

        await asyncio.to_thread(self._render_html_bundle, storyboard)
        return output_paths

    def _remove_stale_outputs(self, count: int):
        """이전 렌더링이 더 많은 장수였다면 남은 파일 정리 (예: 8장 → 7장)"""
        for name in os.listdir(self.export_dir):
            if name.startswith("slide_") and name.endswith((".png", ".html")):
                try:
                    idx = int(name[6:8])
                except ValueError:
                    continue
                if idx > count:
                    os.remove(os.path.join(self.export_dir, name))

    # ------------------------------------------------------------------
    # 에셋 이미지 로드 (동영상은 원본 해상도로 대표 프레임 추출)
    # ------------------------------------------------------------------
    def _load_asset_image(self, asset: MediaAsset) -> Optional[Image.Image]:
        try:
            if asset.kind == "image":
                with Image.open(asset.path) as im:
                    return ImageOps.exif_transpose(im).convert("RGB")
            times = asset.keyframe_times or [asset.duration / 2]
            t = times[len(times) // 2]
            with tempfile.TemporaryDirectory() as tmp:
                frame = os.path.join(tmp, "frame.png")
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", asset.path, "-frames:v", "1", frame],
                               check=True, capture_output=True)
                with Image.open(frame) as im:
                    return im.convert("RGB")
        except Exception as e:
            logging.getLogger(__name__).warning(f"에셋 로드 실패 {asset.id}: {e}")
            return None

    @staticmethod
    def _cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
        """비율을 유지하며 영역을 꽉 채우도록 자르기 (인물 얼굴이 잘리지 않게 약간 위쪽 기준)"""
        return ImageOps.fit(img, (w, h), method=Image.LANCZOS, centering=(0.5, 0.42))

    def _render_photo_slide(self, slide: CardSlide, photo: Image.Image, index: int, total: int, output_path: str):
        """사진이 배치된 슬라이드: 표지/CTA는 전면 사진 + 하단 텍스트, 본문은 상단 사진 + 하단 텍스트"""
        W, H, M = self.WIDTH, self.HEIGHT, self.MARGIN
        full_bleed = slide.slide_type in ("cover", "call_to_action")
        f_small = korean_font(21, "semibold")
        badge = f"{index} / {total}"
        bw = int(f_small.getlength(badge)) + 44

        if full_bleed:
            img = self._cover_fit(photo, W, H).convert("RGBA")
            # 텍스트 가독성을 위한 하단 그라데이션 + 상단 살짝 어둡게
            shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shade)
            for y in range(H):
                if y < 220:
                    a = int(120 * (1 - y / 220))
                elif y > H * 0.38:
                    a = int(235 * min(1.0, (y - H * 0.38) / (H * 0.42)))
                else:
                    a = 0
                sd.line([(0, y), (W, y)], fill=(0, 20, 60, a))
            img = Image.alpha_composite(img, shade).convert("RGB")
            draw = ImageDraw.Draw(img)
            self._pill(draw, (M, 60), "안마사랑", display_font(26, "안마사랑"), "#00236F", "#FFFFFF", pad_x=22, height=52, radius=10)
            draw.text((M + 180, 85), "국가공인 헬스키퍼 연계고용", font=f_small, fill="#E2E8F0", anchor="lm")
            self._pill(draw, (W - M - bw, 60), badge, f_small, "#FFFFFF", "#00236F", pad_x=22, height=50, radius=25)

            tag_text = self.TYPE_NAMES.get(slide.slide_type, "비즈니스 솔루션")
            f_lead, lead_lines = self._fit_lines(slide.lead_headline, W - 2 * M, start=60, minimum=40, max_lines=3, weight="bold")
            lh = int(text_height(f_lead) * 1.18)
            f_body, body_lines = self._fit_lines(slide.body_content.replace("\n", " "), W - 2 * M, start=30, minimum=24, max_lines=3, weight="medium")
            blh = int(text_height(f_body) * 1.35)
            block_h = 66 + lh * len(lead_lines) + 24 + blh * len(body_lines)
            y = 1060 - block_h
            self._pill(draw, (M, y), tag_text, display_font(21, tag_text), "#FFB800", "#0F172A", pad_x=24, height=48, radius=24)
            y += 66
            for line in lead_lines:
                draw.text((M, y), line, font=f_lead, fill="#FFFFFF")
                y += lh
            y += 24
            for line in body_lines:
                draw.text((M, y), line, font=f_body, fill="#E2E8F0")
                y += blh
            self._draw_takeaway_and_footer(draw, slide, dark=True)
        else:
            img = Image.new("RGB", (W, H), "#F8FAFC")
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 0, W, 20], fill="#00236F")
            self._pill(draw, (M, 60), "안마사랑", display_font(26, "안마사랑"), "#00236F", "#FFFFFF", pad_x=22, height=52, radius=10)
            draw.text((M + 180, 85), "국가공인 헬스키퍼 연계고용", font=f_small, fill="#475569", anchor="lm")
            self._pill(draw, (W - M - bw, 60), badge, f_small, "#EFF6FF", "#2563EB", pad_x=22, height=50, radius=25, outline="#BFDBFE")

            # 상단 사진 (둥근 모서리)
            px0, py0, pw, ph = M, 140, W - 2 * M, 500
            pic = self._cover_fit(photo, pw, ph)
            mask = Image.new("L", (pw, ph), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw, ph], radius=24, fill=255)
            img.paste(pic, (px0, py0), mask)

            tag_text = self.TYPE_NAMES.get(slide.slide_type, "비즈니스 솔루션")
            self._pill(draw, (M, 670), tag_text, display_font(21, tag_text), "#DBEAFE", "#1E3A8A", pad_x=24, height=46, radius=23)
            f_lead, lead_lines = self._fit_lines(slide.lead_headline, W - 2 * M, start=44, minimum=32, max_lines=2, weight="bold")
            y = 740
            lh = int(text_height(f_lead) * 1.18)
            for line in lead_lines:
                draw.text((M, y), line, font=f_lead, fill="#00236F")
                y += lh
            self._draw_bullets(draw, slide.body_content, (M + 6, y + 18, W - M, 1055))
            self._draw_takeaway_and_footer(draw, slide, dark=False)

        img.save(output_path, "PNG")

    def _draw_takeaway_and_footer(self, draw, slide: CardSlide, dark: bool):
        W, M = self.WIDTH, self.MARGIN
        bar = (M, 1080, W - M, 1190)
        draw.rounded_rectangle(bar, radius=18, fill="#00236F" if not dark else "#FFFFFF")
        cx, cy = M + 52, (bar[1] + bar[3]) // 2
        draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill="#FFB800")
        draw.text((cx, cy), "!", font=korean_font(28, "bold"), fill="#00236F", anchor="mm")
        f_take, take_lines = self._fit_lines(slide.takeaway, bar[2] - bar[0] - 130, start=28, minimum=20, max_lines=2, weight="bold")
        t_lh = int(text_height(f_take) * 1.15)
        t_y = cy - (t_lh * len(take_lines)) // 2
        for line in take_lines:
            draw.text((M + 100, t_y), line, font=f_take, fill="#FFFFFF" if not dark else "#00236F")
            t_y += t_lh
        draw.line([M, 1225, W - M, 1225], fill="#E2E8F0" if not dark else "#94A3B8", width=2)
        draw.text((M, 1270), "anmasarang.com | 대한민국 1등 헬스케어 바우처", font=korean_font(22, "medium"),
                  fill="#64748B" if not dark else "#E2E8F0", anchor="lm")
        draw.text((W - M, 1270), f"상담문의 {HOTLINE}", font=display_font(24, f"상담문의 {HOTLINE}"),
                  fill="#2563EB" if not dark else "#FFD400", anchor="rm")

    # ------------------------------------------------------------------
    # PNG 렌더링 (사진 없는 텍스트 디자인)
    # ------------------------------------------------------------------
    def _render_single_slide(self, slide: CardSlide, index: int, total: int, output_path: str):
        W, H, M = self.WIDTH, self.HEIGHT, self.MARGIN
        img = Image.new("RGB", (W, H), "#F8FAFC")
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, W, 20], fill="#00236F")

        # 1. 헤더: 로고 + 슬로건 + 페이지 뱃지
        f_logo = display_font(26, "안마사랑")
        f_small = korean_font(21, "semibold")
        self._pill(draw, (M, 60), "안마사랑", f_logo, "#00236F", "#FFFFFF", pad_x=22, height=52, radius=10)
        draw.text((M + 180, 85), "국가공인 헬스키퍼 연계고용", font=f_small, fill="#475569", anchor="lm")
        badge = f"{index} / {total}"
        bw = int(f_small.getlength(badge)) + 44
        self._pill(draw, (W - M - bw, 60), badge, f_small, "#EFF6FF", "#2563EB", pad_x=22, height=50, radius=25, outline="#BFDBFE")
        draw.line([M, 135, W - M, 135], fill="#E2E8F0", width=2)

        # 2. 슬라이드 유형 태그
        tag_text = self.TYPE_NAMES.get(slide.slide_type, "비즈니스 솔루션")
        self._pill(draw, (M, 170), tag_text, display_font(21, tag_text), "#DBEAFE", "#1E3A8A", pad_x=24, height=50, radius=25)

        # 3. Lead 헤드라인 (최대 3줄, 넘치면 글자 크기 축소)
        content_w = W - 2 * M
        f_lead, lead_lines = self._fit_lines(slide.lead_headline, content_w, start=50, minimum=34, max_lines=3, weight="bold")
        y = 255
        lh = int(text_height(f_lead) * 1.18)
        for line in lead_lines:
            draw.text((M, y), line, font=f_lead, fill="#00236F")
            y += lh

        # 4. Body 카드
        card_top = max(y + 30, 430)
        card_bottom = 1050
        draw.rounded_rectangle([M, card_top, W - M, card_bottom], radius=24, fill="#FFFFFF", outline="#CBD5E1", width=2)
        inner = (M + 36, card_top + 36, W - M - 36, card_bottom - 36)

        header, rows = normalize_table(slide.comparison_table)
        if header and rows:
            self._draw_table(draw, header, rows, inner)
        else:
            self._draw_bullets(draw, slide.body_content, inner)

        # 5. Takeaway 바 (이모지 대신 직접 그린 아이콘 사용 — 시스템 폰트에 컬러 이모지 글리프가 없음)
        bar = (M, 1080, W - M, 1190)
        draw.rounded_rectangle(bar, radius=18, fill="#00236F")
        cx, cy = M + 52, (bar[1] + bar[3]) // 2
        draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill="#FFB800")
        draw.text((cx, cy), "!", font=korean_font(28, "bold"), fill="#00236F", anchor="mm")
        f_take, take_lines = self._fit_lines(slide.takeaway, bar[2] - bar[0] - 130, start=28, minimum=20, max_lines=2, weight="bold")
        t_lh = int(text_height(f_take) * 1.15)
        t_y = cy - (t_lh * len(take_lines)) // 2
        for line in take_lines:
            draw.text((M + 100, t_y), line, font=f_take, fill="#FFFFFF")
            t_y += t_lh

        # 6. 푸터
        f_footer = korean_font(22, "medium")
        draw.line([M, 1225, W - M, 1225], fill="#E2E8F0", width=2)
        draw.text((M, 1270), "anmasarang.com | 대한민국 1등 헬스케어 바우처", font=f_footer, fill="#64748B", anchor="lm")
        draw.text((W - M, 1270), f"상담문의 {HOTLINE}", font=display_font(24, f"상담문의 {HOTLINE}"), fill="#2563EB", anchor="rm")

        img.save(output_path, "PNG")

    def _pill(self, draw, xy, text, font, fill, color, pad_x=20, height=50, radius=25, outline=None):
        x, y = xy
        w = int(font.getlength(text)) + pad_x * 2
        draw.rounded_rectangle([x, y, x + w, y + height], radius=radius, fill=fill, outline=outline, width=2 if outline else 0)
        draw.text((x + w / 2, y + height / 2), text, font=font, fill=color, anchor="mm")
        return w

    def _fit_lines(self, text: str, max_width: int, start: int, minimum: int, max_lines: int, weight: str = "regular"):
        """지정 줄 수 안에 들어갈 때까지 폰트 크기를 줄여가며 줄바꿈"""
        size = start
        while True:
            # 굵은 문구(헤드라인·요약 바)는 디스플레이 폰트, 그 외는 본문 폰트
            font = display_font(size, text) if weight == "bold" else korean_font(size, weight)
            lines = wrap_text_px(text, font, max_width)
            if len(lines) <= max_lines or size <= minimum:
                if len(lines) > max_lines:
                    lines = lines[:max_lines]
                    lines[-1] = lines[-1].rstrip() + "…"
                return font, lines
            size -= 2

    def _draw_bullets(self, draw, body: str, box):
        x0, y0, x1, y1 = box
        paragraphs = [p.strip() for p in (body or "").split("\n") if p.strip()]
        size = 30
        while size >= 20:
            font = korean_font(size, "medium")
            lh = int(text_height(font) * 1.35)
            wrapped = [wrap_text_px(p, font, x1 - x0 - 34) for p in paragraphs]
            needed = sum(len(w) * lh for w in wrapped) + max(0, len(wrapped) - 1) * int(lh * 0.45)
            if needed <= (y1 - y0) or size == 20:
                break
            size -= 2
        y = y0 + max(0, ((y1 - y0) - needed) // 2)
        for lines in wrapped:
            if y + lh > y1:
                break
            draw.ellipse([x0, y + lh // 2 - 6, x0 + 12, y + lh // 2 + 6], fill="#2563EB")
            for line in lines:
                if y + lh > y1:
                    break
                draw.text((x0 + 34, y), line, font=font, fill="#334155")
                y += lh
            y += int(lh * 0.45)

    def _draw_table(self, draw, header: List[str], rows: List[List[str]], box):
        """열 폭 자동 배분 + 셀 내부 줄바꿈 + 넘침 시 글자 크기 축소"""
        x0, y0, x1, y1 = box
        total_w = x1 - x0
        n_cols = len(header)
        first_w = int(total_w * (0.30 if n_cols > 2 else 0.34))
        other_w = (total_w - first_w) // max(1, n_cols - 1)
        col_ws = [first_w] + [other_w] * (n_cols - 1)
        pad = 16

        size = 26
        while True:
            font = korean_font(size, "medium")
            bold = korean_font(size, "bold")
            lh = int(text_height(font) * 1.25)
            def cell_lines(text, w, f):
                return wrap_text_px(text, f, w - pad * 2) or [""]
            head_lines = [cell_lines(h, w, bold) for h, w in zip(header, col_ws)]
            head_h = max(len(l) for l in head_lines) * lh + pad * 2
            row_lines = [[cell_lines(c, w, bold if i == 0 else font) for i, (c, w) in enumerate(zip(r, col_ws))] for r in rows]
            row_hs = [max(len(l) for l in rl) * lh + pad * 2 for rl in row_lines]
            if head_h + sum(row_hs) <= (y1 - y0) or size <= 18:
                break
            size -= 2

        # 헤더 (표 전체를 카드 안에서 세로 중앙 정렬)
        y = y0 + max(0, ((y1 - y0) - head_h - sum(row_hs)) // 2)
        draw.rounded_rectangle([x0, y, x1, y + head_h], radius=10, fill="#1E3A8A")
        x = x0
        for lines, w in zip(head_lines, col_ws):
            ty = y + pad
            for line in lines:
                draw.text((x + pad, ty), line, font=bold, fill="#FFFFFF")
                ty += lh
            x += w
        y += head_h

        # 데이터 행
        for r_idx, (lines_per_cell, rh) in enumerate(zip(row_lines, row_hs)):
            if y + rh > y1 + 4:
                break
            draw.rectangle([x0, y, x1, y + rh], fill="#F8FAFC" if r_idx % 2 == 0 else "#FFFFFF")
            draw.line([x0, y + rh, x1, y + rh], fill="#E2E8F0", width=1)
            x = x0
            for c_idx, (lines, w) in enumerate(zip(lines_per_cell, col_ws)):
                if c_idx == n_cols - 1 and n_cols > 2:
                    color = "#2563EB"
                elif c_idx == 0:
                    color = "#0F172A"
                else:
                    color = "#334155" if n_cols > 2 else "#1E3A8A"
                ty = y + pad
                for line in lines:
                    draw.text((x + pad, ty), line, font=bold if c_idx == 0 else font, fill=color)
                    ty += lh
                x += w
            y += rh

    # ------------------------------------------------------------------
    # HTML 번들
    # ------------------------------------------------------------------
    def _render_html_bundle(self, storyboard: EditableStoryboard):
        templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
        if not os.path.exists(os.path.join(templates_dir, "card_template.html")):
            return
        # LLM/사용자 입력 텍스트가 HTML로 해석되지 않도록 자동 이스케이프
        env = Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape(["html"]))
        template = env.get_template("card_template.html")

        total = len(storyboard.card_slides)
        for i, slide in enumerate(storyboard.card_slides):
            table_headers, table_rows = normalize_table(slide.comparison_table)
            asset = storyboard.asset(slide.asset_id)
            photo_src = ""
            if asset and asset.preview_path and slide.slide_type != "comparison_table":
                photo_src = os.path.relpath(asset.preview_path, self.export_dir).replace(os.sep, "/")
            html_content = template.render(
                photo_src=photo_src,
                bg_gradient="linear-gradient(180deg, #F8FAFC 0%, #EFF6FF 100%)",
                slide_index=i + 1,
                total_slides=total,
                slide_type_name=self.TYPE_NAMES.get(slide.slide_type, slide.slide_type.upper()),
                tag_bg="#DBEAFE",
                tag_color="#1E3A8A",
                headline_size=38,
                lead_headline=slide.lead_headline,
                body_content=slide.body_content,
                takeaway=slide.takeaway,
                comparison_table=bool(table_rows),
                table_headers=table_headers,
                table_rows=table_rows,
            )
            with open(os.path.join(self.export_dir, f"slide_{i+1:02d}.html"), "w", encoding="utf-8") as hf:
                hf.write(html_content)
