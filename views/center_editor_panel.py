import flet as ft
from services.stitch_theme import StitchColors, create_badge, create_card_container
from models.schema import EditableStoryboard, CardSlide, ShortsScene

class CenterEditorPanel(ft.Container):
    """중앙: AI 스토리보드 검수, 인라인 수정(Human-in-the-Loop), 렌더링 실행 패널"""

    def __init__(self, on_render_cards, on_render_shorts, on_render_all):
        super().__init__()
        self.on_render_cards = on_render_cards
        self.on_render_shorts = on_render_shorts
        self.on_render_all = on_render_all

        self.expand = True
        self.padding = ft.Padding.all(16)
        self.bgcolor = StitchColors.CANVAS

        self.storyboard: EditableStoryboard = None

        self._build_controls()

    def _build_controls(self):
        # 상단 진행 상태 바
        self.progress_bar = ft.ProgressBar(visible=False, color=StitchColors.SECONDARY, bgcolor=StitchColors.BORDER_DEFAULT)
        self.status_text = ft.Text("AI 기획 완료 대기 중...", size=12, color=StitchColors.TEXT_MUTED)

        # 렌더링 액션 버튼들
        self.render_cards_btn = ft.Button(
            content="🎨 카드뉴스",
            icon=ft.Icons.PHOTO_LIBRARY,
            bgcolor=StitchColors.SURFACE_WHITE,
            color=StitchColors.PRIMARY,
            disabled=True,
            on_click=lambda e: self.on_render_cards(self.get_current_storyboard()),
        )

        self.render_shorts_btn = ft.Button(
            content="🎬 쇼츠 비디오",
            icon=ft.Icons.MOVIE,
            bgcolor=StitchColors.SURFACE_WHITE,
            color=StitchColors.PRIMARY,
            disabled=True,
            on_click=lambda e: self.on_render_shorts(self.get_current_storyboard()),
        )

        self.render_all_btn = ft.Button(
            content="⚡ 원클릭 전체 렌더링",
            icon=ft.Icons.BOLT,
            bgcolor=StitchColors.SECONDARY,
            color=StitchColors.ON_SECONDARY,
            disabled=True,
            on_click=lambda e: self.on_render_all(self.get_current_storyboard()),
        )

        # 탭 뷰 (1. 카드뉴스 슬라이드 편집, 2. 쇼츠 씬 편집, 3. 팩트 가드 검증)
        self.cards_column = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO)
        self.shorts_column = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO)
        self.facts_column = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)

        self.cards_container = ft.Container(content=self.cards_column, expand=True, visible=True)
        self.shorts_container = ft.Container(content=self.shorts_column, expand=True, visible=False)
        self.facts_container = ft.Container(content=self.facts_column, expand=True, visible=False)

        # Stitch 스타일 세그먼트 탭 버튼
        self.tab_btn_cards = ft.Button(
            content="카드뉴스 슬라이드 (7장)",
            icon=ft.Icons.VIEW_CAROUSEL,
            bgcolor=StitchColors.PRIMARY_CONTAINER,
            color=StitchColors.ON_PRIMARY,
            on_click=lambda e: self._switch_tab(0),
        )

        self.tab_btn_shorts = ft.Button(
            content="쇼츠 대본 타임라인 (5씬)",
            icon=ft.Icons.VIDEO_LIBRARY,
            bgcolor=StitchColors.SURFACE_WHITE,
            color=StitchColors.TEXT_SECONDARY,
            on_click=lambda e: self._switch_tab(1),
        )

        self.tab_btn_facts = ft.Button(
            content="팩트 락 & 마스킹 검증",
            icon=ft.Icons.VERIFIED_USER,
            bgcolor=StitchColors.SURFACE_WHITE,
            color=StitchColors.TEXT_SECONDARY,
            on_click=lambda e: self._switch_tab(2),
        )

        tab_bar = ft.Row(
            controls=[
                self.tab_btn_cards,
                self.tab_btn_shorts,
                self.tab_btn_facts,
            ],
            spacing=8,
            wrap=True,
        )

        # 전체 레이아웃
        self.content = ft.Column(
            controls=[
                # 상단 헤더 (제목 줄과 렌더링 액션 줄을 분리해 좁은 폭에서도 버튼이 잘리지 않도록 함)
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.FACT_CHECK, color=StitchColors.PRIMARY, size=22),
                        ft.Text("스토리보드 & 팩트 검수", size=18, weight=ft.FontWeight.W_700, color=StitchColors.TEXT_PRIMARY),
                        create_badge("Human-in-the-Loop", StitchColors.SUCCESS_BG, StitchColors.SUCCESS, StitchColors.SUCCESS_BORDER),
                    ],
                    spacing=8,
                ),
                ft.Row(
                    controls=[
                        self.render_cards_btn,
                        self.render_shorts_btn,
                        self.render_all_btn,
                    ],
                    spacing=6,
                    wrap=True,
                ),
                self.status_text,
                self.progress_bar,
                ft.Divider(height=1, color=StitchColors.BORDER_DEFAULT),

                # 중앙 세그먼트 탭 바 및 컨테이너
                tab_bar,
                self.cards_container,
                self.shorts_container,
                self.facts_container,
            ],
            spacing=12,
            expand=True,
        )

    def safe_update(self):
        try:
            self.update()
        except Exception:
            pass

    def _switch_tab(self, index: int):
        self.cards_container.visible = (index == 0)
        self.shorts_container.visible = (index == 1)
        self.facts_container.visible = (index == 2)

        self.tab_btn_cards.bgcolor = StitchColors.PRIMARY_CONTAINER if index == 0 else StitchColors.SURFACE_WHITE
        self.tab_btn_cards.color = StitchColors.ON_PRIMARY if index == 0 else StitchColors.TEXT_SECONDARY

        self.tab_btn_shorts.bgcolor = StitchColors.PRIMARY_CONTAINER if index == 1 else StitchColors.SURFACE_WHITE
        self.tab_btn_shorts.color = StitchColors.ON_PRIMARY if index == 1 else StitchColors.TEXT_SECONDARY

        self.tab_btn_facts.bgcolor = StitchColors.PRIMARY_CONTAINER if index == 2 else StitchColors.SURFACE_WHITE
        self.tab_btn_facts.color = StitchColors.ON_PRIMARY if index == 2 else StitchColors.TEXT_SECONDARY

        self.safe_update()

    def load_storyboard(self, storyboard: EditableStoryboard):
        """AI가 생성한 스토리보드를 각 탭의 인라인 편집 컨트롤에 로드"""
        self.storyboard = storyboard
        self.status_text.value = f"'{storyboard.title}' 스토리보드 검수 준비 완료 (엔진: {storyboard.engine})"
        self._set_render_buttons_enabled(True)
        self.tab_btn_cards.content = f"카드뉴스 슬라이드 ({len(storyboard.card_slides)}장)"
        self.tab_btn_shorts.content = f"쇼츠 대본 타임라인 ({len(storyboard.shorts_scenes)}씬)"
        warn_count = sum(1 for log in storyboard.fact_check_log if log.startswith("⚠️"))
        self.tab_btn_facts.content = "팩트 락 & 마스킹 검증" + (f" (⚠️ {warn_count})" if warn_count else "")

        # 1. 카드뉴스 슬라이드 에디터 생성
        self.cards_column.controls.clear()
        for i, slide in enumerate(storyboard.card_slides):
            self.cards_column.controls.append(self._create_slide_editor_card(slide, i))

        # 2. 쇼츠 씬 에디터 생성
        self.shorts_column.controls.clear()
        for i, scene in enumerate(storyboard.shorts_scenes):
            self.shorts_column.controls.append(self._create_scene_editor_card(scene, i))

        # 3. 팩트 가드 검증 로그 생성
        self.facts_column.controls.clear()
        for log in storyboard.fact_check_log:
            self.facts_column.controls.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(
                                ft.Icons.WARNING_AMBER if log.startswith("⚠️") else
                                ft.Icons.INFO_OUTLINE if log.startswith(("ℹ️", "🤖")) else ft.Icons.CHECK_CIRCLE,
                                color=StitchColors.WARNING if log.startswith("⚠️") else
                                StitchColors.TEXT_MUTED if log.startswith(("ℹ️", "🤖")) else StitchColors.SUCCESS,
                                size=18,
                            ),
                            ft.Text(log, size=13, weight=ft.FontWeight.W_500, color=StitchColors.TEXT_PRIMARY, expand=True),
                        ],
                        spacing=8,
                    ),
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    bgcolor=StitchColors.SURFACE_WHITE,
                    border=ft.Border.all(1, StitchColors.BORDER_DEFAULT),
                    border_radius=ft.BorderRadius.all(6),
                )
            )

        self.safe_update()

    def _create_slide_editor_card(self, slide: CardSlide, index: int) -> ft.Control:
        """단일 카드뉴스 슬라이드 인라인 편집 카드"""
        tf_lead = ft.TextField(
            label="Lead (시선을 끄는 핵심 헤드라인)",
            value=slide.lead_headline,
            text_size=13,
            dense=True,
            border_color=StitchColors.BORDER_DEFAULT,
            on_change=lambda e, s=slide: setattr(s, "lead_headline", e.control.value),
        )

        tf_body = ft.TextField(
            label="Body (본문 팩트 3~4줄 또는 수치)",
            value=slide.body_content,
            multiline=True,
            min_lines=2,
            max_lines=3,
            text_size=12,
            border_color=StitchColors.BORDER_DEFAULT,
            on_change=lambda e, s=slide: setattr(s, "body_content", e.control.value),
        )

        tf_takeaway = ft.TextField(
            label="Takeaway (하단 한 줄 강조 요약)",
            value=slide.takeaway,
            text_size=12,
            dense=True,
            border_color=StitchColors.BORDER_DEFAULT,
            on_change=lambda e, s=slide: setattr(s, "takeaway", e.control.value),
        )

        return create_card_container(
            content=ft.Column(
                controls=[
                    self._asset_picker(slide, allow=slide.slide_type != "comparison_table"),
                    tf_lead,
                    tf_body,
                    tf_takeaway,
                ],
                spacing=8,
            ),
            title=f"슬라이드 #{slide.slide_number} ({slide.slide_type.upper()})",
            action=create_badge(f"Slide {index+1}", StitchColors.SURFACE_VARIANT, StitchColors.TEXT_SECONDARY),
            padding=12,
        )

    def _create_scene_editor_card(self, scene: ShortsScene, index: int) -> ft.Control:
        """단일 쇼츠 씬 인라인 편집 카드"""
        tf_narration = ft.TextField(
            label="내레이션 대사 (TTS 음성 합성용)",
            value=scene.narration_script,
            multiline=True,
            min_lines=2,
            max_lines=3,
            text_size=12,
            border_color=StitchColors.BORDER_DEFAULT,
            on_change=lambda e, sc=scene: setattr(sc, "narration_script", e.control.value),
        )

        tf_caption = ft.TextField(
            label="번인 하이라이트 자막 (화면 강조 문구)",
            value=scene.display_caption,
            text_size=12,
            dense=True,
            border_color=StitchColors.BORDER_DEFAULT,
            on_change=lambda e, sc=scene: setattr(sc, "display_caption", e.control.value),
        )

        return create_card_container(
            content=ft.Column(
                controls=[
                    self._asset_picker(scene, allow=True),
                    tf_caption,
                    ft.TextField(
                        label="강조 단어 (키네틱 타이포에서 크게 표시, 쉼표로 구분)",
                        value=", ".join(scene.emphasis_words), text_size=12, dense=True,
                        border_color=StitchColors.BORDER_DEFAULT,
                        on_change=lambda e, sc=scene: setattr(
                            sc, "emphasis_words", [w.strip() for w in (e.control.value or "").split(",") if w.strip()][:2]),
                    ),
                    tf_narration,
                ],
                spacing=8,
            ),
            title=f"씬 #{scene.scene_number} [{scene.section_type.upper()}] ({scene.duration_seconds}초)",
            action=create_badge(f"Scene {index+1}", StitchColors.PRIMARY_CONTAINER, StitchColors.ON_PRIMARY),
            padding=12,
        )

    def _set_render_buttons_enabled(self, enabled: bool):
        for btn in (self.render_cards_btn, self.render_shorts_btn, self.render_all_btn):
            btn.disabled = not enabled

    def _asset_picker(self, item, allow: bool) -> ft.Control:
        """슬라이드/씬에 배치된 에셋 썸네일 + 교체 드롭다운 (동영상이면 시작 시각 입력)"""
        sb = self.storyboard
        if not allow:
            return ft.Text("비교표 슬라이드는 사진 없이 표로 렌더링됩니다.", size=11, color=StitchColors.TEXT_MUTED)

        thumb = ft.Image(src=b"", width=96, height=64, fit=ft.BoxFit.COVER, border_radius=ft.BorderRadius.all(6), visible=False)
        placeholder = ft.Container(
            content=ft.Icon(ft.Icons.TEXT_FIELDS, size=20, color=StitchColors.TEXT_MUTED),
            width=96, height=64, bgcolor=StitchColors.SURFACE_VARIANT, border_radius=ft.BorderRadius.all(6),
            alignment=ft.Alignment.CENTER,
        )
        is_scene = isinstance(item, ShortsScene)
        clip_field = ft.TextField(
            label="시작(초)", value=str(getattr(item, "clip_start", 0.0)), width=90, dense=True, text_size=12,
            border_color=StitchColors.BORDER_DEFAULT, visible=False,
        )

        def refresh():
            asset = sb.asset(item.asset_id)
            if asset and asset.keyframes:
                with open(asset.keyframes[len(asset.keyframes) // 2] if asset.kind == "video" else asset.keyframes[0], "rb") as f:
                    thumb.src = f.read()
                thumb.visible, placeholder.visible = True, False
            else:
                thumb.visible, placeholder.visible = False, True
            clip_field.visible = bool(is_scene and asset and asset.kind == "video")
            if clip_field.visible:
                clip_field.label = f"시작(초) / {asset.duration:.1f}"

        def on_select(e):
            item.asset_id = dropdown.value if dropdown.value != "none" else None
            refresh()
            self.safe_update()

        def on_clip(e):
            try:
                asset = sb.asset(item.asset_id)
                item.clip_start = max(0.0, min(float(clip_field.value), max(0.0, (asset.duration if asset else 0) - 1)))
            except ValueError:
                pass

        clip_field.on_blur = on_clip
        clip_field.on_submit = on_clip
        options = [ft.dropdown.Option("none", "없음 (텍스트 디자인)")]
        for a in sb.assets:
            kind = "영상" if a.kind == "video" else ("AI 이미지" if a.source == "ai" else "이미지")
            options.append(ft.dropdown.Option(a.id, f"{a.id} · {kind} · {(a.description or a.original_name)[:18]}"))
        dropdown = ft.Dropdown(
            label="배치 에셋", options=options, value=item.asset_id or "none", dense=True, text_size=12,
            border_color=StitchColors.BORDER_DEFAULT, on_select=on_select, expand=True,
        )
        refresh()
        return ft.Row([thumb, placeholder, dropdown, clip_field], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def set_loading(self, is_loading: bool, message: str = ""):
        """작업 중에는 렌더링 버튼을 잠가 동일 출력 파일에 대한 중복 실행을 방지"""
        self.progress_bar.visible = is_loading
        self._set_render_buttons_enabled(not is_loading and self.storyboard is not None)
        if message:
            self.status_text.value = message
        self.safe_update()

    def get_current_storyboard(self) -> EditableStoryboard:
        return self.storyboard
