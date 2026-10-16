import os
import uuid
import asyncio
import flet as ft
from services.stitch_theme import StitchColors, create_badge, create_card_container
from services.media_assets import MediaLibrary, ALLOWED_EXTENSIONS, media_kind
from services import key_store
from services.tts_gemini import VOICE_OPTIONS
from services import veo_video
from models.schema import UserRequestPayload, MediaAsset


class LeftInputPanel(ft.Container):
    """좌측: 프롬프트 + 이미지/동영상 첨부 + 생성 옵션 + AI 엔진 설정 패널"""

    def __init__(self, page: ft.Page, scenarios: list, media_library: MediaLibrary, upload_dir: str,
                 on_generate_click, on_assets_change=None):
        super().__init__()
        self.app_page = page
        self.scenarios = scenarios
        self.media_library = media_library
        self.upload_dir = upload_dir
        self.on_generate_click = on_generate_click
        self.on_assets_change = on_assets_change

        self.assets: list[MediaAsset] = []
        self.scenario_id = None
        self.upload_session = uuid.uuid4().hex[:8]
        self._pending_uploads: dict[str, str] = {}  # 업로드 중 파일명 → 에셋 ID

        self.width = 400
        self.padding = ft.Padding.all(16)
        self.bgcolor = StitchColors.SURFACE_WHITE
        self.border = ft.Border.only(right=ft.BorderSide(1, StitchColors.BORDER_DEFAULT))

        self.file_picker = ft.FilePicker(on_upload=self._on_upload_progress)
        page.services.append(self.file_picker)

        self._build_controls()

    @staticmethod
    def format_scenario_text(sc: dict) -> str:
        return f"[{sc.get('title')}]\n상황: {sc.get('situation')}\n전개: {sc.get('development')}\n결과: {sc.get('result')}"

    def _build_controls(self):
        # 1. 프롬프트 (핵심 입력)
        self.text_input = ft.TextField(
            label="프롬프트 (만들고 싶은 콘텐츠를 설명하세요)",
            hint_text="예) 판교 IT기업에 헬스키퍼 사내 안마실을 도입한 현장 영상입니다. 개발자들의 거북목 통증이 줄고 고용부담금도 감면된 사례로 기업 담당자 대상 홍보 콘텐츠를 만들어 주세요.",
            multiline=True,
            min_lines=5,
            max_lines=8,
            text_size=13,
            border_color=StitchColors.BORDER_DEFAULT,
            focused_border_color=StitchColors.PRIMARY_LIGHT,
            on_change=self._on_prompt_change,
        )

        # 2. 예시 프롬프트 (14개 시나리오는 선택형 예시로 유지)
        self.example_dropdown = ft.Dropdown(
            label="예시 불러오기 (선택)",
            options=[
                ft.dropdown.Option(key=str(sc.get("id")), text=f"[{sc.get('id'):02d}] {sc.get('title')[:26]}...")
                for sc in self.scenarios
            ],
            on_select=self._on_example_select,
            border_color=StitchColors.BORDER_DEFAULT,
            dense=True,
            text_size=12,
            visible=bool(self.scenarios),  # data/scenarios.json 이 없으면(공개 저장소 clone 등) 숨김
        )

        # 3. 미디어 첨부
        self.attach_btn = ft.Button(
            content="이미지·동영상 첨부",
            icon=ft.Icons.ADD_PHOTO_ALTERNATE,
            bgcolor=StitchColors.SECONDARY_CONTAINER,
            color=StitchColors.PRIMARY,
            on_click=self._pick_files,
        )
        self.upload_status = ft.Text("", size=11, color=StitchColors.TEXT_MUTED)
        self.asset_list = ft.Column(spacing=6)
        self.asset_empty_text = ft.Text(
            "첨부한 사진·영상을 AI가 분석해 카드뉴스와 쇼츠의 장면에 배치합니다.\n첨부가 없거나 부족하면 AI 이미지를 생성합니다.",
            size=11, color=StitchColors.TEXT_MUTED,
        )

        # 4. 생성 옵션
        self.target_dropdown = ft.Dropdown(
            label="타겟 오디언스",
            options=[ft.dropdown.Option(x) for x in [
                "AI 자동 추천", "B2B 의사결정권자 (대표/HR/재무)", "B2C / B2E 이용자 (기업 임직원)",
                "B2B 영업 파트너 (컨설팅/FP)", "CSR 및 대중 홍보 (지자체/시민)"]],
            value="AI 자동 추천", dense=True, text_size=12, border_color=StitchColors.BORDER_DEFAULT,
        )
        self.tone_dropdown = ft.Dropdown(
            label="톤앤매너",
            options=[ft.dropdown.Option(x) for x in [
                "AI 자동 추천", "경고/솔루션형 (법률 뉴스 톤)", "이익/효율 강조형 (논리적 세무)",
                "유머/공감/일상형 (경쾌한 브이로그)", "감동/가치 전달형 (다큐멘터리)"]],
            value="AI 자동 추천", dense=True, text_size=12, border_color=StitchColors.BORDER_DEFAULT,
        )
        self.style_dropdown = ft.Dropdown(
            label="비주얼 스타일 (AI 이미지)",
            options=[ft.dropdown.Option(x) for x in [
                "실사풍 / 인포그래픽", "2D 일러스트 / 일상툰", "A4 원페이지 만화형 제안서", "모던 비즈니스 다이어그램"]],
            value="실사풍 / 인포그래픽", dense=True, text_size=12, border_color=StitchColors.BORDER_DEFAULT,
        )
        self.card_count_dropdown = ft.Dropdown(
            label="카드뉴스 장수",
            options=[ft.dropdown.Option("3", "3장 (테스트)")] + [ft.dropdown.Option(str(n), f"{n}장") for n in range(5, 11)],
            value="7", dense=True, text_size=12, width=150, border_color=StitchColors.BORDER_DEFAULT,
        )
        self.shorts_len_dropdown = ft.Dropdown(
            label="쇼츠 길이",
            options=[ft.dropdown.Option("15", "약 15초 (테스트)")] + [ft.dropdown.Option(str(n), f"약 {n}초") for n in (30, 45, 60)],
            value="45", dense=True, text_size=12, width=150, border_color=StitchColors.BORDER_DEFAULT,
        )
        self.caption_style_dropdown = ft.Dropdown(
            label="쇼츠 자막 스타일",
            options=[ft.dropdown.Option("kinetic", "키네틱 타이포 (단어 순차 등장·강조·대형 숫자)"),
                     ft.dropdown.Option("basic", "기본 (문구 팝업)")],
            value="kinetic", dense=True, text_size=12, border_color=StitchColors.BORDER_DEFAULT,
        )
        # Veo AI 영상화 (선택, 기본: 사용 안 함)
        self.current_storyboard = None
        self.veo_scope_dropdown = ft.Dropdown(
            label="AI 영상화 범위 (Veo)",
            options=[ft.dropdown.Option(k, v) for k, v in veo_video.SCOPES.items()],
            value="none", dense=True, text_size=12, border_color=StitchColors.BORDER_DEFAULT,
            on_select=lambda e: self.refresh_veo_estimate(),
        )
        self.veo_quality_dropdown = ft.Dropdown(
            label="Veo 모델",
            options=[ft.dropdown.Option(k, f"{label} · ${price:.2f}/초") for k, (_, label, price) in veo_video.VEO_MODELS.items()],
            value="fast", dense=True, text_size=12, border_color=StitchColors.BORDER_DEFAULT,
            on_select=lambda e: self.refresh_veo_estimate(),
        )
        self.veo_estimate_text = ft.Text("", size=11, color=StitchColors.TEXT_MUTED)

        self.voice_dropdown = ft.Dropdown(
            label="내레이션 목소리 (Gemini TTS)",
            options=[ft.dropdown.Option(v, label) for label, v in VOICE_OPTIONS.items()],
            value="auto", dense=True, text_size=12, border_color=StitchColors.BORDER_DEFAULT,
        )
        self.ai_image_switch = ft.Switch(
            label="에셋이 부족한 장면은 AI 이미지 생성 (Gemini)",
            value=True, active_color=StitchColors.PRIMARY_CONTAINER,
        )

        # 5. 가드레일
        self.fact_lock_switch = ft.Switch(label="팩트 락 (원문 수치 보존 검증)", value=True, active_color=StitchColors.PRIMARY_CONTAINER)
        self.anonymize_switch = ft.Switch(label="엔티티 마스킹 (IBM->I사, 서울대병원->S병원)", value=True, active_color=StitchColors.PRIMARY_CONTAINER)

        # 6. AI 엔진
        self.ai_provider_radio = ft.RadioGroup(
            content=ft.Row(
                controls=[
                    ft.Radio(value="gemini", label="Google Gemini"),
                    ft.Radio(value="claude", label="Anthropic Claude"),
                ],
                spacing=10,
            ),
            value="gemini",
        )
        saved = key_store.load_keys()
        self.gemini_key_field = ft.TextField(
            label="Gemini API Key (기획 + AI 이미지 생성)", value=saved.get("gemini", ""),
            password=True, can_reveal_password=True, dense=True, text_size=12, expand=True,
            border_color=StitchColors.BORDER_DEFAULT, hint_text="미입력 시 환경변수 GEMINI_API_KEY",
        )
        self.anthropic_key_field = ft.TextField(
            label="Anthropic API Key (Claude 기획 시)", value=saved.get("anthropic", ""),
            password=True, can_reveal_password=True, dense=True, text_size=12, expand=True,
            border_color=StitchColors.BORDER_DEFAULT, hint_text="미입력 시 환경변수 ANTHROPIC_API_KEY",
        )
        self.gemini_test_btn = ft.Button(content="테스트", height=36, on_click=self._test_gemini_key)
        self.anthropic_test_btn = ft.Button(content="테스트", height=36, on_click=self._test_anthropic_key)
        self.gemini_key_status = ft.Text(
            f"💾 저장된 키 사용 중 ({key_store.mask(saved['gemini'])})" if saved.get("gemini") else "",
            size=11, color=StitchColors.TEXT_MUTED)
        self.anthropic_key_status = ft.Text(
            f"💾 저장된 키 사용 중 ({key_store.mask(saved['anthropic'])})" if saved.get("anthropic") else "",
            size=11, color=StitchColors.TEXT_MUTED)
        self.save_keys_btn = ft.Button(content="키 저장", icon=ft.Icons.SAVE, height=36, on_click=self._save_keys)
        self.delete_keys_btn = ft.TextButton(content="저장된 키 삭제", on_click=self._delete_keys)

        self.generate_btn = ft.Button(
            content="✨ AI 디렉터 생성 (스토리보드 기획)",
            icon=ft.Icons.AUTO_AWESOME,
            bgcolor=StitchColors.PRIMARY,
            color=StitchColors.ON_PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=16, vertical=18),
            ),
            on_click=self._handle_generate_click,
        )

        header_section = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.TUNE, color=StitchColors.PRIMARY, size=20),
                        ft.Text("프롬프트 & 미디어 입력", size=16, weight=ft.FontWeight.W_700, color=StitchColors.TEXT_PRIMARY),
                    ],
                    spacing=8,
                ),
                ft.Text("설명과 사진·영상을 넣으면 카드뉴스와 쇼츠를 만들어 드립니다.", size=12, color=StitchColors.TEXT_MUTED),
                ft.Divider(height=1, color=StitchColors.BORDER_DEFAULT),
            ],
            spacing=4,
        )

        scrollable_body = ft.Column(
            controls=[
                self.text_input,
                self.example_dropdown,
                create_card_container(
                    content=ft.Column(
                        controls=[
                            ft.Row([self.attach_btn, self.upload_status], spacing=8, wrap=True),
                            self.asset_empty_text,
                            self.asset_list,
                        ],
                        spacing=8,
                    ),
                    title="미디어 첨부 (선택)",
                    padding=12,
                ),
                create_card_container(
                    content=ft.Column(
                        controls=[
                            ft.Row([self.card_count_dropdown, self.shorts_len_dropdown], spacing=8),
                            self.target_dropdown,
                            self.tone_dropdown,
                            self.style_dropdown,
                            self.ai_image_switch,
                            self.caption_style_dropdown,
                            self.voice_dropdown,
                            ft.Text("※ 자막 스타일·목소리는 렌더링할 때 적용되므로 다시 기획하지 않고 바꿔 렌더링할 수 있습니다.",
                                    size=11, color=StitchColors.TEXT_MUTED),
                        ],
                        spacing=10,
                    ),
                    title="생성 옵션",
                    padding=12,
                ),
                create_card_container(
                    content=ft.Column(
                        controls=[
                            self.veo_scope_dropdown,
                            self.veo_quality_dropdown,
                            self.veo_estimate_text,
                            ft.Text(
                                "참고 요금 (Google 공식, 1080p, 생성 성공 시에만 과금)\n"
                                "· Lite $0.08/초 · Fast $0.12/초 · 표준 $0.40/초\n"
                                "· 오프닝 1장면 ≈ 8초 → Fast 약 $0.96\n"
                                "· 핵심 2장면 ≈ 16초 → Fast 약 $1.92\n"
                                "· 전체 45초 쇼츠 ≈ 44초 → Fast 약 $5.28\n"
                                "· 클립당 1~3분 소요, 같은 장면을 다시 렌더링하면 재사용(추가 과금 없음)",
                                size=11, color=StitchColors.TEXT_MUTED,
                            ),
                        ],
                        spacing=8,
                    ),
                    title="AI 영상화 (Veo, 선택)",
                    padding=12,
                ),
                create_card_container(
                    content=ft.Column(controls=[self.fact_lock_switch, self.anonymize_switch], spacing=6),
                    title="무결성 가드레일 (Fact-Guard)",
                    padding=12,
                ),
                create_card_container(
                    content=ft.Column(
                        controls=[
                            ft.Text("기획(스토리보드)·미디어 분석 모델", size=12, weight=ft.FontWeight.W_600, color=StitchColors.TEXT_SECONDARY),
                            self.ai_provider_radio,
                            ft.Row([self.gemini_key_field, self.gemini_test_btn], spacing=6),
                            self.gemini_key_status,
                            ft.Row([self.anthropic_key_field, self.anthropic_test_btn], spacing=6),
                            self.anthropic_key_status,
                            ft.Row([self.save_keys_btn, self.delete_keys_btn], spacing=6),
                            ft.Text("※ 키는 이 PC의 ~/.anmasarang_studio/keys.json 에 저장됩니다.\n※ Claude는 이미지 생성을 지원하지 않아 AI 이미지는 Gemini 키로 생성합니다.",
                                    size=11, color=StitchColors.TEXT_MUTED),
                        ],
                        spacing=8,
                    ),
                    title="AI 엔진 설정",
                    padding=12,
                ),
                ft.Container(height=6),
                self.generate_btn,
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        self.content = ft.Column(controls=[header_section, scrollable_body], spacing=8, expand=True)
        self.shorts_len_dropdown.on_select = lambda e: self.refresh_veo_estimate()
        self.refresh_veo_estimate()

    def _safe_update(self, ctrl=None):
        try:
            (ctrl or self).update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 예시 / 프롬프트
    # ------------------------------------------------------------------
    def _on_example_select(self, e):
        sc_id = int(self.example_dropdown.value)
        sc = next((s for s in self.scenarios if s.get("id") == sc_id), None)
        if sc:
            self.text_input.value = self.format_scenario_text(sc)
            self.scenario_id = sc_id
            self._safe_update(self.text_input)

    def _on_prompt_change(self, e):
        # 예시를 지우고 새로 쓰면 더 이상 예시 기반이 아님
        if not (self.text_input.value or "").strip():
            self.scenario_id = None

    # ------------------------------------------------------------------
    # 미디어 첨부 (데스크톱: 로컬 경로 직접 사용 / 웹: 업로드 후 수집)
    # ------------------------------------------------------------------
    async def _pick_files(self, e):
        files = await self.file_picker.pick_files(
            dialog_title="이미지 또는 동영상 선택",
            allow_multiple=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=ALLOWED_EXTENSIONS,
        )
        if not files:
            return
        if all(f.path for f in files):
            for f in files:
                await self._ingest(f.path, f.name)
            return

        # 웹 모드: 브라우저 → 서버 업로드 후 on_upload 이벤트에서 수집
        upload_files = []
        for f in files:
            if not media_kind(f.name):
                continue
            asset_id = MediaLibrary.next_id(self.assets + [MediaAsset(id=i, kind="image", path="") for i in self._pending_uploads.values()], "A")
            self._pending_uploads[f.name] = asset_id
            upload_files.append(ft.FilePickerUploadFile(
                id=f.id, name=f.name,
                upload_url=self.app_page.get_upload_url(f"{self.upload_session}/{f.name}", 600),
            ))
        if upload_files:
            self.upload_status.value = f"업로드 중... (0/{len(upload_files)})"
            self._safe_update(self.upload_status)
            await self.file_picker.upload(upload_files)

    async def _on_upload_progress(self, e: ft.FilePickerUploadEvent):
        if e.error:
            self._pending_uploads.pop(e.file_name, None)
            self.upload_status.value = f"업로드 실패: {e.file_name} ({e.error})"
            self._safe_update(self.upload_status)
            return
        if e.progress is not None and e.progress >= 1.0 and e.file_name in self._pending_uploads:
            asset_id = self._pending_uploads.pop(e.file_name)
            path = os.path.join(self.upload_dir, self.upload_session, e.file_name)
            # 업로드 완료 직후 파일 쓰기가 끝날 때까지 잠시 대기
            for _ in range(20):
                if os.path.exists(path):
                    break
                await asyncio.sleep(0.25)
            await self._ingest(path, e.file_name, asset_id)
            try:
                os.remove(path)
            except OSError:
                pass
        remaining = len(self._pending_uploads)
        if not remaining:
            try:
                os.rmdir(os.path.join(self.upload_dir, self.upload_session))  # 비어 있으면 업로드 임시 폴더 정리
            except OSError:
                pass
        self.upload_status.value = f"업로드 중... (남은 파일 {remaining})" if remaining else ""
        self._safe_update(self.upload_status)

    async def _ingest(self, path: str, name: str, asset_id: str = None):
        asset_id = asset_id or MediaLibrary.next_id(self.assets, "A")
        self.upload_status.value = f"분석 준비 중: {name}"
        self._safe_update(self.upload_status)
        try:
            asset = await self.media_library.ingest(path, asset_id, original_name=name)
        except Exception as ex:
            self.upload_status.value = f"첨부 실패: {ex}"
            self._safe_update(self.upload_status)
            return
        self.assets.append(asset)
        self.assets.sort(key=lambda a: int(a.id[1:]))
        self.upload_status.value = ""
        self._refresh_asset_list()

    def _remove_asset(self, asset: MediaAsset):
        self.assets = [a for a in self.assets if a.id != asset.id]
        self.media_library.remove(asset)
        self._refresh_asset_list()

    def _refresh_asset_list(self):
        self.asset_list.controls.clear()
        for a in self.assets:
            with open(a.keyframes[0], "rb") as f:
                thumb = f.read()
            meta = f"동영상 · {a.duration:.1f}초 · {a.width}x{a.height}" if a.kind == "video" else f"이미지 · {a.width}x{a.height}"
            self.asset_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Image(src=thumb, width=64, height=48, fit=ft.BoxFit.COVER, border_radius=ft.BorderRadius.all(6)),
                            ft.Column(
                                controls=[
                                    ft.Row([create_badge(a.id, StitchColors.PRIMARY_CONTAINER, StitchColors.ON_PRIMARY),
                                            ft.Icon(ft.Icons.MOVIE if a.kind == "video" else ft.Icons.IMAGE, size=14, color=StitchColors.TEXT_MUTED)],
                                           spacing=6),
                                    ft.Text(a.original_name, size=11, color=StitchColors.TEXT_PRIMARY, max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS, width=180),
                                    ft.Text(meta, size=10, color=StitchColors.TEXT_MUTED),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=StitchColors.ERROR, icon_size=18,
                                          tooltip="첨부 삭제", on_click=lambda e, x=a: self._remove_asset(x)),
                        ],
                        spacing=8,
                    ),
                    padding=ft.Padding.all(6),
                    border=ft.Border.all(1, StitchColors.BORDER_DEFAULT),
                    border_radius=ft.BorderRadius.all(8),
                )
            )
        self.asset_empty_text.visible = not self.assets
        self._safe_update()
        if self.on_assets_change:
            self.on_assets_change(self.assets)

    # ------------------------------------------------------------------
    # API 키 테스트 / 저장
    # ------------------------------------------------------------------
    async def _test_gemini_key(self, e):
        await self._test_key("gemini")

    async def _test_anthropic_key(self, e):
        await self._test_key("anthropic")

    async def _test_key(self, provider: str):
        field = self.gemini_key_field if provider == "gemini" else self.anthropic_key_field
        status = self.gemini_key_status if provider == "gemini" else self.anthropic_key_status
        btn = self.gemini_test_btn if provider == "gemini" else self.anthropic_test_btn
        key = (field.value or "").strip() or os.environ.get("GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY", "")
        if not key:
            status.value, status.color = "❌ 키를 입력하세요.", StitchColors.ERROR
            self._safe_update(status)
            return
        btn.disabled = True
        status.value, status.color = "⏳ 연결 확인 중...", StitchColors.TEXT_MUTED
        self._safe_update()
        try:
            ok, msg = await (key_store.test_gemini(key) if provider == "gemini" else key_store.test_anthropic(key))
        except Exception as ex:
            ok, msg = False, f"테스트 실패: {ex}"
        btn.disabled = False
        status.value = ("✅ " if ok else "❌ ") + msg
        status.color = StitchColors.SUCCESS if ok else StitchColors.ERROR
        self._safe_update()

    def _save_keys(self, e):
        keys = {"gemini": self.gemini_key_field.value or "", "anthropic": self.anthropic_key_field.value or ""}
        if not any(v.strip() for v in keys.values()):
            self.app_page.show_dialog(ft.SnackBar(content=ft.Text("저장할 키를 입력하세요."), bgcolor=StitchColors.WARNING))
            return
        try:
            key_store.save_keys(keys)
        except OSError as ex:
            self.app_page.show_dialog(ft.SnackBar(content=ft.Text(f"키 저장 실패: {ex}"), bgcolor=StitchColors.ERROR))
            return
        for name, status in (("gemini", self.gemini_key_status), ("anthropic", self.anthropic_key_status)):
            if keys[name].strip() and not status.value.startswith("✅"):
                status.value, status.color = f"💾 저장됨 ({key_store.mask(keys[name].strip())})", StitchColors.TEXT_MUTED
        self._safe_update()
        self.app_page.show_dialog(ft.SnackBar(content=ft.Text("🔑 API 키를 저장했습니다. 다음 실행부터 자동으로 불러옵니다."),
                                              bgcolor=StitchColors.SUCCESS))

    def _delete_keys(self, e):
        key_store.delete_keys()
        self.gemini_key_field.value = ""
        self.anthropic_key_field.value = ""
        self.gemini_key_status.value = ""
        self.anthropic_key_status.value = ""
        self._safe_update()
        self.app_page.show_dialog(ft.SnackBar(content=ft.Text("저장된 API 키를 삭제했습니다."), bgcolor=StitchColors.PRIMARY_CONTAINER))

    def refresh_veo_estimate(self, storyboard=None):
        """선택한 범위·모델의 예상 비용 표시 (스토리보드가 있으면 장면별 예상 길이 기준)"""
        if storyboard is not None:
            self.current_storyboard = storyboard
        scope = self.veo_scope_dropdown.value or "none"
        quality = self.veo_quality_dropdown.value or "fast"
        if scope == "none":
            self.veo_estimate_text.value = "현재 방식(이미지 줌·팬)으로 렌더링합니다. 추가 비용 없음."
            self.veo_estimate_text.color = StitchColors.TEXT_MUTED
        else:
            secs, cost = veo_video.estimate(self.current_storyboard, scope, quality, int(self.shorts_len_dropdown.value or 45))
            basis = "현재 스토리보드 기준" if self.current_storyboard else "쇼츠 길이 기준 추정"
            self.veo_estimate_text.value = f"💰 예상 비용: 약 ${cost:.2f} ({secs}초 생성, {basis})"
            self.veo_estimate_text.color = StitchColors.WARNING
        self._safe_update(self.veo_estimate_text)

    def shorts_options(self):
        """쇼츠 렌더링 시점 옵션 (입력란 키 → 환경변수 → 저장된 키 순)"""
        from services.shorts_renderer import ShortsOptions
        key = (self.gemini_key_field.value or "").strip() or os.environ.get("GEMINI_API_KEY") or key_store.load_keys().get("gemini")
        return ShortsOptions(veo_scope=self.veo_scope_dropdown.value or "none",
                             veo_quality=self.veo_quality_dropdown.value or "fast",
                             caption_style=self.caption_style_dropdown.value or "kinetic",
                             voice=self.voice_dropdown.value or "auto", gemini_api_key=key)

    # ------------------------------------------------------------------
    def _handle_generate_click(self, e):
        text = (self.text_input.value or "").strip()
        if len(text) < 10:
            self.app_page.show_dialog(ft.SnackBar(content=ft.Text("프롬프트를 10자 이상 입력하거나 예시를 불러오세요."),
                                                  bgcolor=StitchColors.WARNING))
            return
        if self._pending_uploads:
            self.app_page.show_dialog(ft.SnackBar(content=ft.Text("첨부 파일 업로드가 끝난 뒤 생성하세요."),
                                                  bgcolor=StitchColors.WARNING))
            return
        payload = UserRequestPayload(
            scenario_id=self.scenario_id,
            raw_text=text,
            target_audience=self.target_dropdown.value,
            tone_and_manner=self.tone_dropdown.value,
            visual_style=self.style_dropdown.value,
            anonymize=self.anonymize_switch.value,
            fact_lock=self.fact_lock_switch.value,
            ai_provider=self.ai_provider_radio.value,
            gemini_api_key=(self.gemini_key_field.value or "").strip() or None,
            anthropic_api_key=(self.anthropic_key_field.value or "").strip() or None,
            card_count=int(self.card_count_dropdown.value or 7),
            shorts_seconds=int(self.shorts_len_dropdown.value or 45),
            generate_ai_images=self.ai_image_switch.value,
            assets=[a.model_copy(deep=True) for a in self.assets],
        )
        if self.on_generate_click:
            self.on_generate_click(payload)
