"""첨부 에셋이 없는 슬라이드/씬에 Gemini 이미지 모델로 AI 이미지를 생성해 채우는 서비스.

Claude API는 이미지 생성을 지원하지 않으므로 이미지 생성은 Gemini 키가 있을 때만 동작한다.
"""
import os
import logging
import asyncio
import tempfile
from typing import Awaitable, Callable, List, Optional, Tuple
from models.schema import EditableStoryboard, UserRequestPayload
from services.media_assets import MediaLibrary

# 앞에서부터 시도하고, 모델을 찾을 수 없으면 다음 모델로 대체
GEMINI_IMAGE_MODELS = [m for m in [os.environ.get("GEMINI_IMAGE_MODEL"), "gemini-3.1-flash-image", "gemini-2.5-flash-image"] if m]
MAX_CONCURRENCY = 3

ProgressFn = Optional[Callable[[str], Awaitable[None]]]


class AIImageGenerator:
    def __init__(self, library: MediaLibrary):
        self.library = library
        self._working_model: Optional[str] = None

    async def fill_missing(self, sb: EditableStoryboard, payload: UserRequestPayload, progress: ProgressFn = None) -> List[str]:
        """비어 있는 슬라이드·씬에 이미지를 생성해 배치하고, 결과 로그를 반환"""
        if not payload.generate_ai_images:
            return ["ℹ️ AI 이미지 생성 꺼짐: 에셋이 없는 장면은 브랜드 디자인 배경으로 렌더링합니다."]

        targets: List[Tuple[object, str, str]] = []  # (슬라이드 또는 씬, 프롬프트, 화면비)
        for slide in sb.card_slides:
            if not slide.asset_id and slide.slide_type != "comparison_table":
                targets.append((slide, slide.image_prompt or slide.lead_headline, "4:5"))
        for scene in sb.shorts_scenes:
            if not scene.asset_id:
                targets.append((scene, scene.visual_motion_prompt or scene.display_caption, "9:16"))
        if not targets:
            return []

        api_key = payload.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return [f"ℹ️ Gemini API 키가 없어 AI 이미지 {len(targets)}장을 생성하지 않았습니다 (Claude API는 이미지 생성 미지원). 해당 장면은 브랜드 디자인 배경으로 렌더링합니다."]

        from google import genai
        client = genai.Client(api_key=api_key)
        # 이전 생성분 파일을 덮어쓰지 않도록 폴더에 이미 있는 G번호 다음부터 사용
        existing = [f.split(".")[0] for f in os.listdir(self.library.assets_dir) if f.startswith("G")]
        used = [int(x[1:]) for x in existing if x[1:].isdigit()]
        first = max(int(MediaLibrary.next_id(sb.assets, "G")[1:]), max(used, default=0) + 1)
        ids = [f"G{first + i}" for i in range(len(targets))]

        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        done = 0
        errors: List[str] = []
        aborted = False

        async def run(target, prompt: str, aspect: str, asset_id: str):
            nonlocal done, aborted
            async with sem:
                if aborted:
                    errors.append("이전 인증 오류로 건너뜀")
                    return
                try:
                    data, ext = await self._generate(client, prompt, aspect)
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        tmp.write(data)
                    try:
                        asset = await self.library.ingest(tmp.name, asset_id, original_name=f"AI_{asset_id}{ext}", source="ai")
                    finally:
                        os.remove(tmp.name)
                    asset.description = prompt.splitlines()[0][:120]
                    sb.assets.append(asset)
                    target.asset_id = asset.id
                except Exception as e:
                    logging.getLogger(__name__).warning(f"AI 이미지 생성 실패 ({asset_id}): {e}")
                    errors.append(f"{type(e).__name__}: {str(e)[:100]}")
                    # 키 오류·권한 오류는 나머지 요청도 실패하므로 즉시 중단 (불필요한 과금/대기 방지)
                    if getattr(e, "code", None) in (400, 401, 403) and "key" in str(e).lower():
                        aborted = True
                done += 1
                if progress:
                    await progress(f"AI 이미지 생성 중... ({done}/{len(targets)})")

        await asyncio.gather(*(run(t, p, a, i) for (t, p, a), i in zip(targets, ids)))
        sb.assets.sort(key=lambda a: (a.source != "user", len(a.id), a.id))

        made = len(targets) - len(errors)
        logging.getLogger(__name__).info(f"AI 이미지 생성 결과: 성공 {made} / 실패 {len(errors)}")
        logs = [f"🎨 AI 이미지 {made}장 생성 완료 ({self._working_model or GEMINI_IMAGE_MODELS[0]})"] if made else []
        if errors:
            logs.append(f"⚠️ AI 이미지 {len(errors)}장 생성 실패 → 디자인 배경 사용 ({errors[0]})")
        return logs

    async def _generate(self, client, prompt: str, aspect: str) -> Tuple[bytes, str]:
        from google.genai import types, errors as genai_errors

        models = [self._working_model] if self._working_model else GEMINI_IMAGE_MODELS
        last_error: Optional[Exception] = None
        for model in models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(aspect_ratio=aspect),
                    ),
                )
            except genai_errors.ClientError as e:
                # 모델 미존재(404)면 다음 후보 모델로, 그 외 오류는 그대로 전달
                if getattr(e, "code", None) == 404 and not self._working_model:
                    last_error = e
                    continue
                raise
            for part in response.parts or []:
                if part.inline_data and part.inline_data.data:
                    self._working_model = model
                    mime = part.inline_data.mime_type or "image/png"
                    return part.inline_data.data, ".jpg" if "jpeg" in mime else ".png"
            raise RuntimeError("응답에 이미지가 없습니다 (안전 필터 또는 프롬프트 문제)")
        raise last_error or RuntimeError("사용 가능한 Gemini 이미지 모델이 없습니다")
