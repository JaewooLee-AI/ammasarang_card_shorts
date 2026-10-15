import os
import sys
import json
import logging
import secrets
import asyncio
import flet as ft

from services.stitch_theme import StitchColors, StitchFonts, create_badge
from services.ai_director import AIDirectorService
from services.card_renderer import CardNewsRendererService
from services.shorts_renderer import ShortsRendererService
from services.media_assets import MediaLibrary
from services.image_generator import AIImageGenerator
from services import downloads
from services.veo_video import VeoGenerator, VEO_MODELS, SCOPES, estimate as veo_estimate
from models.schema import UserRequestPayload, EditableStoryboard

from views.left_input_panel import LeftInputPanel
from views.center_editor_panel import CenterEditorPanel
from views.right_preview_panel import RightPreviewPanel

from services.paths import BASE_DIR, ASSETS_DIR, FONTS_DIR, EXPORTS_DIR, UPLOAD_DIR, LOG_DIR, IS_PACKAGED

# 경로 규칙 (services/paths.py)
# - assets/ : 폰트 등 읽기 전용 리소스 → Flet assets_dir (배포 번들에 포함)
# - exports/ uploads/ logs/ : 결과물·업로드·로그 → 배포 앱에서는 운영체제의 앱 데이터 폴더(FLET_APP_STORAGE_DATA)
# 웹 모드 파일 업로드에는 FLET_SECRET_KEY가 필요
os.environ.setdefault("FLET_SECRET_KEY", secrets.token_hex(16))

# 오류 추적용 로그 파일 (서버 콘솔 출력이 버퍼링되어도 원인을 확인할 수 있도록)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("studio")
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass

async def main(page: ft.Page):
    page.title = "안마사랑(Anmasarang) AI 콘텐츠 스튜디오 - 카드뉴스 & 쇼츠/릴스 생성기"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = StitchColors.CANVAS
    page.padding = 0

    # 번들 폰트를 앱 화면에도 등록 (assets/fonts → 배포 파일에 포함)
    app_fonts = {}
    if os.path.exists(os.path.join(FONTS_DIR, "GmarketSansBold.otf")):
        app_fonts["Gmarket Sans"] = "/fonts/GmarketSansBold.otf"
    if os.path.exists(os.path.join(FONTS_DIR, "Pretendard-Regular.otf")):
        app_fonts["Pretendard"] = "/fonts/Pretendard-Regular.otf"
    page.fonts = app_fonts
    if "Pretendard" in app_fonts:
        page.theme = ft.Theme(font_family="Pretendard")
    page.window.width = 1480
    page.window.height = 960
    page.window.min_width = 1200
    page.window.min_height = 800

    # 1. 14대 시나리오 데이터 로드
    scenarios_path = os.path.join(BASE_DIR, "data", "scenarios.json")
    scenarios = []
    if os.path.exists(scenarios_path):
        with open(scenarios_path, "r", encoding="utf-8") as f:
            scenarios = json.load(f)

    # 2. 백엔드 서비스 인스턴스
    ai_director = AIDirectorService()
    card_renderer = CardNewsRendererService(export_dir=os.path.join(EXPORTS_DIR, "cards"))
    shorts_renderer = ShortsRendererService(export_dir=os.path.join(EXPORTS_DIR, "shorts"))
    media_library = MediaLibrary(EXPORTS_DIR)
    image_generator = AIImageGenerator(media_library)
    veo_generator = VeoGenerator(media_library, os.path.join(EXPORTS_DIR, "shorts", "veo_cache"))

    # 3. 상단 글로벌 네비게이션 헤더 (Stitch Midnight Slate & Civic Navy)
    status_scenario_badge = create_badge("첨부 0개", StitchColors.PRIMARY_CONTAINER, StitchColors.ON_PRIMARY)
    status_ai_badge = create_badge("AI: 대기", StitchColors.SECONDARY_CONTAINER, StitchColors.SECONDARY)
    status_fact_badge = create_badge("Fact-Lock: 대기", StitchColors.SUCCESS_BG, StitchColors.SUCCESS, StitchColors.SUCCESS_BORDER)

    top_header = ft.Container(
        content=ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(
                            content=ft.Icon(ft.Icons.SPA, color=StitchColors.ON_PRIMARY, size=22),
                            bgcolor=StitchColors.PRIMARY_CONTAINER,
                            padding=ft.Padding.all(8),
                            border_radius=ft.BorderRadius.all(8),
                        ),
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Text("안마사랑 AI 콘텐츠 스튜디오", size=19, color=StitchColors.TEXT_ON_DARK,
                                                font_family="Gmarket Sans" if "Gmarket Sans" in app_fonts else None,
                                                weight=None if "Gmarket Sans" in app_fonts else ft.FontWeight.W_800),
                                    ],
                                    spacing=8,
                                ),
                                ft.Text("시각장애인 국가공인 헬스키퍼 연계고용 & 헬스케어 바우처 멀티포맷 자동 생성 플랫폼", size=11, color=StitchColors.TEXT_ON_DARK_MUTED),
                            ],
                            spacing=2,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Row(
                    controls=[
                        status_scenario_badge,
                        status_ai_badge,
                        status_fact_badge,
                        ft.IconButton(
                            icon=ft.Icons.HELP_OUTLINE,
                            icon_color=StitchColors.TEXT_ON_DARK_MUTED,
                            tooltip="안마사랑 고객센터: 1577-1398",
                        ),
                    ],
                    spacing=8,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        bgcolor=StitchColors.SIDEBAR_BG,
        padding=ft.Padding.symmetric(horizontal=20, vertical=12),
        border=ft.Border.only(bottom=ft.BorderSide(1, StitchColors.BORDER_MUTED)),
    )

    def safe_control_update(ctrl):
        try:
            ctrl.update()
        except Exception:
            pass

    def toast(message: str, bgcolor: str = StitchColors.SUCCESS):
        page.show_dialog(ft.SnackBar(content=ft.Text(message), bgcolor=bgcolor))

    def reveal_preview():
        """좁은 화면(가로 스크롤 모드)에서는 렌더링 완료 후 오른쪽 프리뷰로 자동 스크롤.

        브라우저 탭이 숨겨져 있으면 스크롤 애니메이션 응답이 오지 않을 수 있으므로,
        완료 처리를 막지 않도록 백그라운드 작업 + 짧은 제한 시간으로 실행한다.
        """
        if not body_row.scroll:
            return

        async def _scroll():
            try:
                await asyncio.wait_for(body_row.scroll_to(offset=-1, duration=0), timeout=3)
            except Exception:
                logger.info("프리뷰 자동 스크롤 생략 (브라우저 응답 없음)")

        asyncio.create_task(_scroll())

    # 4. 이벤트 핸들러 정의
    def on_assets_change(assets):
        n_img = sum(1 for a in assets if a.kind == "image")
        n_vid = len(assets) - n_img
        status_scenario_badge.content.controls[-1].value = f"첨부 {len(assets)}개 (이미지 {n_img} · 영상 {n_vid})"
        safe_control_update(status_scenario_badge)

    async def on_generate_click(payload: UserRequestPayload):
        center_panel.set_loading(True, f"AI 디렉터가 '{payload.ai_provider.upper()}' 엔진으로 시나리오를 분석하고 팩트 락을 검증하는 중...")
        status_ai_badge.content.controls[-1].value = f"AI: {payload.ai_provider.upper()}"
        safe_control_update(status_ai_badge)

        try:
            if payload.assets:
                center_panel.set_loading(True, f"AI 디렉터가 첨부 미디어 {len(payload.assets)}개를 분석하고 장면별 배치를 기획하는 중...")
            storyboard = await ai_director.generate_storyboard(payload)

            async def image_progress(msg: str):
                center_panel.set_loading(True, msg)

            center_panel.set_loading(True, "에셋이 없는 장면을 확인하는 중...")
            storyboard.fact_check_log.extend(await image_generator.fill_missing(storyboard, payload, image_progress))
            center_panel.load_storyboard(storyboard)
            right_panel.update_sns_package(storyboard)
            left_panel.refresh_veo_estimate(storyboard)

            # 실제로 사용된 엔진과 팩트 락 결과를 헤더에 표시 (API 실패 시 폴백 여부가 드러나도록)
            status_ai_badge.content.controls[-1].value = f"AI: {storyboard.engine}"
            ok, warn = ai_director.fact_status(storyboard)
            if not payload.fact_lock:
                status_fact_badge.content.controls[-1].value = "Fact-Lock: OFF"
            elif warn:
                status_fact_badge.content.controls[-1].value = f"Fact-Lock: ⚠️ 누락 의심 {warn}건"
            else:
                status_fact_badge.content.controls[-1].value = f"Fact-Lock: ON (보존 {ok}건)"
            safe_control_update(status_ai_badge)
            safe_control_update(status_fact_badge)

            done_msg = "스토리보드 기획 완료! 각 슬라이드/씬을 검수하거나 렌더링하세요."
            if storyboard.engine == "rule-based" and (payload.gemini_api_key or payload.anthropic_api_key):
                done_msg += " (AI 호출 실패 → 규칙 기반 엔진 사용, '팩트 락 & 마스킹 검증' 탭에서 사유 확인)"
            center_panel.set_loading(False, done_msg)
        except Exception as ex:
            logger.exception("스토리보드 생성 실패")
            center_panel.set_loading(False, f"오류 발생: {ex} (자세한 내용: logs/app.log)")

    async def on_render_cards(storyboard: EditableStoryboard):
        if not storyboard:
            return
        center_panel.set_loading(True, f"고해상도 카드뉴스 (1080x1350) {len(storyboard.card_slides)}장 렌더링 중...")
        try:
            image_paths = await card_renderer.render_all_slides(storyboard)
            right_panel.set_card_slides(image_paths)
            reveal_preview()
            center_panel.set_loading(False, f"카드뉴스 렌더링 완료! ({len(image_paths)}장 → exports/cards)")
            toast(f"🎨 카드뉴스 {len(image_paths)}장이 생성되었습니다!")
        except Exception as ex:
            logger.exception("카드뉴스 렌더링 실패")
            center_panel.set_loading(False, f"카드뉴스 렌더링 실패: {ex}")
            toast(f"카드뉴스 렌더링 실패: {ex}", StitchColors.ERROR)

    async def confirm(title: str, message: str, ok_label: str) -> bool:
        """비용이 드는 작업 전 확인 대화상자"""
        fut = asyncio.get_running_loop().create_future()

        def close(result: bool):
            if not fut.done():
                fut.set_result(result)
            page.pop_dialog()

        page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[ft.TextButton("취소", on_click=lambda e: close(False)),
                     ft.Button(ok_label, on_click=lambda e: close(True))],
            on_dismiss=lambda e: (not fut.done()) and fut.set_result(False),
        ))
        return await fut

    async def on_render_shorts(storyboard: EditableStoryboard):
        if not storyboard:
            return
        opts = left_panel.shorts_options()
        veo_logs = []
        if opts.veo_scope != "none":
            secs, cost = veo_estimate(storyboard, opts.veo_scope, opts.veo_quality)
            label = VEO_MODELS[opts.veo_quality][1]
            if secs and not await confirm(
                "Veo AI 영상 생성",
                f"범위: {SCOPES[opts.veo_scope]}\n모델: {label} (1080p)\n생성 길이: 약 {secs}초\n"
                f"예상 비용: 약 ${cost:.2f} (생성 성공 시에만 과금, 이미 만든 장면은 재사용)\n소요 시간: 클립당 1~3분",
                "생성 진행",
            ):
                center_panel.set_loading(False, "Veo 영상 생성을 취소했습니다. (AI 영상화 옵션을 '사용 안 함'으로 바꾸면 바로 렌더링됩니다)")
                return

        center_panel.set_loading(True, "쇼츠 오디오 합성 및 ASS 노래방식 자막 비디오 인코딩 중...")

        async def shorts_progress(pct: float, msg: str):
            center_panel.set_loading(True, f"[{int(pct*100)}%] {msg}")

        async def veo_progress(msg: str):
            center_panel.set_loading(True, msg)

        try:
            if opts.veo_scope != "none":
                clips, veo_logs = await veo_generator.generate(
                    storyboard, opts.veo_scope, opts.veo_quality, opts.gemini_api_key,
                    {i: sc.duration_seconds for i, sc in enumerate(storyboard.shorts_scenes)}, veo_progress)
                opts.video_overrides = clips
                storyboard.fact_check_log.extend(veo_logs)
            mp4_path = await shorts_renderer.render_shorts_video(storyboard, shorts_progress, opts)
            right_panel.set_shorts_video(mp4_path)
            reveal_preview()
            warnings = shorts_renderer.last_warnings
            if warnings:
                center_panel.set_loading(False, "쇼츠 렌더링 완료 (경고: " + " / ".join(warnings) + ")"
                                         + (" · " + veo_logs[0] if veo_logs else ""))
                toast("🎬 쇼츠가 생성되었지만 경고가 있습니다: " + warnings[0], StitchColors.WARNING)
            else:
                center_panel.set_loading(False, f"쇼츠 비디오 (9:16) 렌더링 완료! 음성: {shorts_renderer.last_tts_engine}"
                                         + (" · " + " / ".join(veo_logs) if veo_logs else ""))
                toast("🎬 9:16 세로형 쇼츠 동영상이 생성되었습니다!")
        except Exception as ex:
            logger.exception("쇼츠 렌더링 실패")
            center_panel.set_loading(False, f"쇼츠 렌더링 실패: {ex}")
            toast(f"쇼츠 렌더링 실패: {ex}", StitchColors.ERROR)

    async def on_render_all(storyboard: EditableStoryboard):
        if not storyboard:
            return
        await on_render_cards(storyboard)
        await on_render_shorts(storyboard)

    # 5. 3단 레이아웃 뷰 생성
    left_panel = LeftInputPanel(
        page=page,
        scenarios=scenarios,
        media_library=media_library,
        upload_dir=UPLOAD_DIR,
        on_generate_click=lambda payload: asyncio.create_task(on_generate_click(payload)),
        on_assets_change=on_assets_change,
    )

    center_panel = CenterEditorPanel(
        on_render_cards=lambda sb: asyncio.create_task(on_render_cards(sb)),
        on_render_shorts=lambda sb: asyncio.create_task(on_render_shorts(sb)),
        on_render_all=lambda sb: asyncio.create_task(on_render_all(sb)),
    )

    right_panel = RightPreviewPanel(page=page, exports_dir=EXPORTS_DIR)

    # 6. 메인 바디 컨테이너
    body_row = ft.Row(
        controls=[
            left_panel,
            center_panel,
            right_panel,
        ],
        spacing=0,
        expand=True,
    )

    page.add(
        ft.Column(
            controls=[
                top_header,
                body_row,
            ],
            spacing=0,
            expand=True,
        )
    )

    # 7. 반응형 레이아웃: 창이 좁으면 패널 폭을 줄이고, 그래도 부족하면 가로 스크롤로 프리뷰 패널이 잘리지 않게 함
    def apply_layout(width):
        w = width or 1480
        if w >= 1400:
            left_panel.width, right_panel.width, center_w = 400, 460, None
        elif w >= 1150:
            left_panel.width, right_panel.width, center_w = 340, 400, None
        else:
            left_panel.width, right_panel.width, center_w = 340, 400, 560
        center_panel.width = center_w
        center_panel.expand = center_w is None
        body_row.scroll = ft.ScrollMode.ALWAYS if center_w else None
        safe_control_update(body_row)

    page.on_resize = lambda e: apply_layout(e.width)
    apply_layout(page.width)

    center_panel.set_loading(False, "왼쪽에 프롬프트를 입력하고 이미지·동영상을 첨부한 뒤 [AI 디렉터 생성]을 누르세요."
                             + (" (예시 불러오기도 가능)" if scenarios else ""))

def create_web_app():
    """웹 모드 ASGI 앱 (+ 결과물 다운로드 라우트)"""
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles
    app = ft.run(main, export_asgi_app=True, assets_dir=ASSETS_DIR, upload_dir=UPLOAD_DIR)
    downloads.register_routes(app, EXPORTS_DIR)
    # 결과물(쇼츠 영상 미리보기 등)은 /exports 경로로 서빙 — Flet 정적 파일 처리보다 먼저 매칭되도록 맨 앞에 삽입
    app.router.routes.insert(0, Mount("/exports", app=StaticFiles(directory=EXPORTS_DIR), name="exports"))
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8550"))
    view_mode = os.environ.get("FLET_VIEW", "web").lower()
    # flet build 배포 앱은 항상 데스크톱 앱으로 실행 (웹 서버 모드 X)
    if view_mode == "app" or IS_PACKAGED:
        ft.run(main, view=ft.AppView.FLET_APP, assets_dir=ASSETS_DIR, upload_dir=UPLOAD_DIR)
    else:
        import uvicorn
        logger.info(f"안마사랑 AI 콘텐츠 스튜디오 시작: http://localhost:{port}")
        # 기본은 이 PC에서만 접속 가능 (저장된 API 키가 같은 네트워크의 다른 기기에 노출되지 않도록).
        # 다른 기기에서 접속해야 하면 HOST=0.0.0.0 으로 실행
        host = os.environ.get("HOST", "127.0.0.1")
        uvicorn.run(create_web_app(), host=host, port=port, log_level="info")
