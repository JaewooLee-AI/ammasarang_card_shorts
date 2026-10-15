import logging
import os
import time
from urllib.parse import urlparse
import asyncio
import subprocess
import flet as ft
import flet_video as ftv
from services.stitch_theme import StitchColors, create_badge, create_card_container
from models.schema import EditableStoryboard
from services import downloads

class RightPreviewPanel(ft.Container):
    """우측: 카드뉴스 캐러셀 프리뷰, 쇼츠 9:16 비디오 플레이어, SNS 배포 패키지 패널"""

    def __init__(self, page: ft.Page, exports_dir: str):
        super().__init__()
        self.app_page = page
        self.exports_dir = exports_dir
        self.width = 460
        self.padding = ft.Padding.all(16)
        self.bgcolor = StitchColors.SURFACE_WHITE
        self.border = ft.Border.only(left=ft.BorderSide(1, StitchColors.BORDER_DEFAULT))

        self.card_image_paths = []
        self.current_slide_idx = 0
        self.video_path = None
        self.storyboard: EditableStoryboard = None

        self._build_controls()

    def _build_controls(self):
        # 1. 카드뉴스 캐러셀 컴포넌트
        self.slide_image = ft.Image(
            src="",
            fit="contain",
            border_radius=ft.BorderRadius.all(12),
        )

        self.slide_counter_text = ft.Text("0 / 0", size=13, weight=ft.FontWeight.W_600, color=StitchColors.TEXT_SECONDARY)

        self.prev_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            icon_color=StitchColors.PRIMARY,
            on_click=self._prev_slide,
            disabled=True,
        )

        self.next_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            icon_color=StitchColors.PRIMARY,
            on_click=self._next_slide,
            disabled=True,
        )

        self.image_placeholder = ft.Column(
            controls=[
                ft.Icon(ft.Icons.PHOTO_LIBRARY_OUTLINED, size=52, color=StitchColors.TEXT_MUTED),
                ft.Text("카드뉴스 렌더링 대기 중", size=14, weight=ft.FontWeight.W_600, color=StitchColors.TEXT_SECONDARY),
                ft.Text(
                    "중앙 상단의 [카드뉴스 렌더링]을 누르면\n고해상도 1080x1350 카드뉴스가\n이곳에 슬라이드 쇼로 표시됩니다.",
                    size=12,
                    color=StitchColors.TEXT_MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )

        self.slide_image_container = ft.Container(
            content=self.image_placeholder,
            height=520,
            alignment=ft.Alignment.CENTER,
            bgcolor=StitchColors.CANVAS,
            border_radius=ft.BorderRadius.all(12),
            border=ft.Border.all(1, StitchColors.BORDER_DEFAULT),
        )

        self.download_cards_btn = ft.Button(
            content="카드뉴스 전체 다운로드 (ZIP)",
            icon=ft.Icons.DOWNLOAD,
            bgcolor=StitchColors.SECONDARY,
            color=StitchColors.ON_SECONDARY,
            disabled=True,
            on_click=self._download_cards,
        )

        self.cards_preview_box = ft.Container(
            content=ft.Column(
                controls=[
                    self.slide_image_container,
                    ft.Row(
                        controls=[
                            self.prev_btn,
                            self.slide_counter_text,
                            self.next_btn,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    ft.Row(controls=[self.download_cards_btn], alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=10,
            ),
        )

        # 2. 쇼츠 9:16 비디오 플레이어 컴포넌트
        self.video_player_container = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, size=64, color=StitchColors.TEXT_MUTED),
                    ft.Text("쇼츠 비디오를 렌더링하면 재생됩니다.", size=13, color=StitchColors.TEXT_MUTED),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            height=540,
            bgcolor="#0F172A",
            border_radius=ft.BorderRadius.all(16),
            alignment=ft.Alignment.CENTER,
        )

        self.download_video_btn = ft.Button(
            content="MP4 다운로드",
            icon=ft.Icons.DOWNLOAD,
            bgcolor=StitchColors.SECONDARY,
            color=StitchColors.ON_SECONDARY,
            disabled=True,
            on_click=self._download_video,
        )
        self.video_hint = ft.Text(
            "▶ 재생 버튼을 누르면 내레이션 소리와 함께 재생됩니다.",
            size=11, color=StitchColors.TEXT_MUTED, visible=False, text_align=ft.TextAlign.CENTER,
        )

        self.capture_thumb_btn = ft.Button(
            content="📸 썸네일",
            icon=ft.Icons.CAMERA_ALT,
            bgcolor=StitchColors.PRIMARY_CONTAINER,
            color=StitchColors.ON_PRIMARY,
            disabled=True,
            on_click=self._capture_thumbnail,
        )

        # 3. SNS 배포 패키지 컴포넌트
        self.sns_caption_field = ft.TextField(
            label="인스타그램 / 블로그 마케팅 본문 캡션",
            value="스토리보드가 생성되면 본문 캡션이 표시됩니다.",
            multiline=True,
            min_lines=6,
            max_lines=9,
            text_size=12,
            border_color=StitchColors.BORDER_DEFAULT,
            on_change=lambda e: self._refresh_copy_action(),
        )

        self.hashtags_wrap = ft.Row(wrap=True, spacing=6)
        self.hashtags: list = []

        self.copy_btn = ft.Button(
            content="📋 본문 & 해시태그 전체 복사",
            icon=ft.Icons.CONTENT_COPY,
            bgcolor=StitchColors.SECONDARY,
            color=StitchColors.ON_SECONDARY,
            disabled=True,
            action=ft.CopyToClipboard(""),
            on_click=self._copy_to_clipboard,
        )

        # 3개 프리뷰 서브 컨테이너
        self.cards_sub_container = ft.Container(content=self.cards_preview_box, expand=True, visible=True)
        self.shorts_sub_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.video_player_container,
                    self.video_hint,
                    ft.Row(controls=[self.download_video_btn, self.capture_thumb_btn],
                           alignment=ft.MainAxisAlignment.CENTER, spacing=8, wrap=True),
                ],
                spacing=12,
            ),
            expand=True,
            visible=False,
        )
        self.sns_sub_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.sns_caption_field,
                    ft.Text("타겟 맞춤 추천 해시태그", size=13, weight=ft.FontWeight.W_600, color=StitchColors.TEXT_PRIMARY),
                    self.hashtags_wrap,
                    ft.Container(height=8),
                    self.copy_btn,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
            expand=True,
            visible=False,
        )

        # Stitch 스타일 세그먼트 탭 버튼
        self.tab_btn_cards = ft.Button(
            content="카드뉴스",
            icon=ft.Icons.VIEW_CAROUSEL,
            bgcolor=StitchColors.PRIMARY_CONTAINER,
            color=StitchColors.ON_PRIMARY,
            on_click=lambda e: self._switch_tab(0),
        )

        self.tab_btn_shorts = ft.Button(
            content="쇼츠/릴스(9:16)",
            icon=ft.Icons.SMARTPHONE,
            bgcolor=StitchColors.SURFACE_WHITE,
            color=StitchColors.TEXT_SECONDARY,
            on_click=lambda e: self._switch_tab(1),
        )

        self.tab_btn_sns = ft.Button(
            content="SNS 배포",
            icon=ft.Icons.SHARE,
            bgcolor=StitchColors.SURFACE_WHITE,
            color=StitchColors.TEXT_SECONDARY,
            on_click=lambda e: self._switch_tab(2),
        )

        tab_bar = ft.Row(
            controls=[
                self.tab_btn_cards,
                self.tab_btn_shorts,
                self.tab_btn_sns,
            ],
            spacing=6,
        )

        # 전체 레이아웃
        self.content = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.PREVIEW, color=StitchColors.PRIMARY, size=20),
                        ft.Text("스튜디오 프리뷰 & 배포", size=16, weight=ft.FontWeight.W_700, color=StitchColors.TEXT_PRIMARY),
                    ],
                    spacing=8,
                ),
                ft.Divider(height=1, color=StitchColors.BORDER_DEFAULT),
                tab_bar,
                self.cards_sub_container,
                self.shorts_sub_container,
                self.sns_sub_container,
            ],
            spacing=10,
            expand=True,
        )

    def safe_update(self):
        try:
            self.update()
        except Exception:
            pass

    def _switch_tab(self, index: int):
        self.cards_sub_container.visible = (index == 0)
        self.shorts_sub_container.visible = (index == 1)
        self.sns_sub_container.visible = (index == 2)

        self.tab_btn_cards.bgcolor = StitchColors.PRIMARY_CONTAINER if index == 0 else StitchColors.SURFACE_WHITE
        self.tab_btn_cards.color = StitchColors.ON_PRIMARY if index == 0 else StitchColors.TEXT_SECONDARY

        self.tab_btn_shorts.bgcolor = StitchColors.PRIMARY_CONTAINER if index == 1 else StitchColors.SURFACE_WHITE
        self.tab_btn_shorts.color = StitchColors.ON_PRIMARY if index == 1 else StitchColors.TEXT_SECONDARY

        self.tab_btn_sns.bgcolor = StitchColors.PRIMARY_CONTAINER if index == 2 else StitchColors.SURFACE_WHITE
        self.tab_btn_sns.color = StitchColors.ON_PRIMARY if index == 2 else StitchColors.TEXT_SECONDARY

        self.safe_update()

    def set_card_slides(self, image_paths: list):
        """렌더링된 카드뉴스 이미지 목록 로드"""
        self.card_image_paths = image_paths
        self.current_slide_idx = 0
        if image_paths:
            self._enable_download(self.download_cards_btn, "/download/cards.zip")
        if image_paths:
            self._update_slide_view()
            self._switch_tab(0)
        self.safe_update()

    def _video_src(self, video_path: str) -> str:
        """웹 모드는 assets_dir(exports) 기준 URL, 데스크톱은 로컬 절대경로 사용"""
        if self.app_page and self.app_page.web:
            rel = os.path.relpath(video_path, self.exports_dir).replace(os.sep, "/")
            return f"/exports/{rel}?v={int(os.path.getmtime(video_path))}"
        return video_path

    def set_shorts_video(self, video_path: str):
        """렌더링된 9:16 쇼츠 MP4 비디오 로드"""
        self.video_path = video_path
        if video_path and os.path.exists(video_path):
            try:
                media = ftv.VideoMedia(self._video_src(video_path))
                video_ctrl = ftv.Video(
                    expand=True,
                    playlist=[media],
                    playlist_mode=ftv.PlaylistMode.LOOP,
                    fill_color="#0F172A",
                    aspect_ratio=9 / 16,
                    volume=100,
                    autoplay=False,  # 브라우저 자동재생 정책상 소리가 막히므로 사용자가 직접 재생
                    filter_quality=ft.FilterQuality.HIGH,
                    muted=False,
                )
                self.video_player_container.content = video_ctrl
                self.capture_thumb_btn.disabled = False
                self.video_hint.visible = True
                self._enable_download(self.download_video_btn, "/download/shorts.mp4")
                self._switch_tab(1)
            except Exception as e:
                logging.getLogger(__name__).warning(f"{e}")
                self.video_player_container.content = ft.Text(f"비디오 파일 로드 완료: {os.path.basename(video_path)}", size=13, color=StitchColors.TEXT_LIGHT)
        self.safe_update()

    def update_sns_package(self, storyboard: EditableStoryboard):
        """SNS 캡션 및 해시태그 업데이트"""
        self.storyboard = storyboard
        self.sns_caption_field.value = storyboard.sns_caption
        self.hashtags = list(storyboard.hashtags)
        self.hashtags_wrap.controls.clear()
        for tag in self.hashtags:
            self.hashtags_wrap.controls.append(
                create_badge(tag, StitchColors.SECONDARY_CONTAINER, StitchColors.SECONDARY)
            )
        self.copy_btn.disabled = False
        self._refresh_copy_action()
        self.safe_update()

    def _copy_text(self) -> str:
        return (self.sns_caption_field.value or "") + "\n\n" + " ".join(self.hashtags)

    def _refresh_copy_action(self):
        # 클릭 시점에 클라이언트가 바로 복사하도록 액션 인자를 최신 본문으로 갱신
        self.copy_btn.action = ft.CopyToClipboard(self._copy_text())
        self.safe_update()

    def _update_slide_view(self):
        if not self.card_image_paths:
            return
        total = len(self.card_image_paths)
        curr_path = self.card_image_paths[self.current_slide_idx]
        # 바이트로 전달하면 웹/데스크톱 모두에서 로컬 파일 서빙·캐시 문제 없이 표시됨
        with open(curr_path, "rb") as f:
            self.slide_image.src = f.read()
        self.slide_image_container.content = self.slide_image
        self.slide_counter_text.value = f"{self.current_slide_idx + 1} / {total}"
        self.prev_btn.disabled = (self.current_slide_idx == 0)
        self.next_btn.disabled = (self.current_slide_idx == total - 1)
        self.safe_update()

    def _prev_slide(self, e):
        if self.current_slide_idx > 0:
            self.current_slide_idx -= 1
            self._update_slide_view()

    def _next_slide(self, e):
        if self.current_slide_idx < len(self.card_image_paths) - 1:
            self.current_slide_idx += 1
            self._update_slide_view()

    # ------------------------------------------------------------------
    # 다운로드: 웹은 클릭과 동시에 브라우저가 다운로드 URL을 열고(팝업 차단 회피),
    #          데스크톱 앱은 ~/Downloads 로 복사
    # ------------------------------------------------------------------
    def _enable_download(self, btn: ft.Button, path: str):
        btn.disabled = False
        if self.app_page and self.app_page.web:
            btn.action = ft.OpenUrl(f"{self._http_origin()}{path}?t={int(time.time())}", target=ft.UrlTarget.BLANK)
        else:
            btn.action = None

    def _http_origin(self) -> str:
        """Flet 웹의 page.url은 웹소켓 주소(ws://호스트/ws)이므로 http(s)://호스트 형태로 변환"""
        parsed = urlparse(self.app_page.url or "")
        scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme or "http")
        return f"{scheme}://{parsed.netloc}" if parsed.netloc else ""

    def _download(self, kind: str):
        if self.app_page and self.app_page.web:
            self._toast("⬇️ 다운로드를 시작합니다. 브라우저의 다운로드 목록을 확인하세요.", StitchColors.SUCCESS)
            return
        try:
            dest = downloads.save_to_downloads(self.exports_dir, kind)
            self._toast(f"⬇️ 저장 완료: {dest}", StitchColors.SUCCESS)
        except Exception as ex:
            self._toast(f"다운로드 실패: {ex}", StitchColors.ERROR)

    def _download_cards(self, e):
        self._download("cards")

    def _download_video(self, e):
        self._download("shorts")

    def _toast(self, message: str, bgcolor: str = StitchColors.PRIMARY_CONTAINER):
        if self.app_page:
            self.app_page.show_dialog(ft.SnackBar(content=ft.Text(message), bgcolor=bgcolor))

    async def _capture_thumbnail(self, e):
        """쇼츠 영상의 1초 지점 프레임을 썸네일 PNG로 저장"""
        if not self.video_path or not os.path.exists(self.video_path):
            return
        thumb_path = os.path.join(os.path.dirname(self.video_path), "thumbnail.png")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-ss", "1", "-i", self.video_path, "-frames:v", "1", thumb_path,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode == 0 and os.path.exists(thumb_path):
            self._toast(f"📸 썸네일 저장 완료: {thumb_path}", StitchColors.SUCCESS)
        else:
            self._toast(f"썸네일 캡처 실패: {err.decode(errors='ignore')[:120]}", StitchColors.ERROR)

    def _copy_to_clipboard(self, e):
        # 실제 복사는 버튼의 CopyToClipboard 액션이 클라이언트에서 수행
        self._toast("📋 SNS 캡션과 해시태그가 클립보드에 복사되었습니다!")
