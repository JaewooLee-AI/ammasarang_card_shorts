"""Veo(Gemini API)로 쇼츠 일부 장면을 실제로 움직이는 AI 영상으로 만드는 선택 기능.

- 장면에 배치된 이미지(첨부·AI 생성)를 시작 프레임으로 이미지→영상 생성, 이미지가 없으면 장면 묘사로 생성
- 이미 첨부 동영상이 배치된 장면은 건너뜀 (원래 움직이는 영상이므로 비용을 쓰지 않음)
- 결과는 캐시: 같은 이미지·프롬프트·모델·길이면 다시 생성(과금)하지 않음
- 실패한 장면은 기존 카메라 무브(줌·팬)로 그대로 렌더링
요금: Google 공식 요금표(2026-10 확인), 1080p 기준 초당 단가, 생성에 성공한 경우에만 과금
"""
import os
import asyncio
import hashlib
import logging
from typing import Awaitable, Callable, Dict, List, Optional, Tuple
from models.schema import EditableStoryboard, MediaAsset
from services.media_assets import MediaLibrary

logger = logging.getLogger(__name__)

VEO_MODELS = {
    "lite": ("veo-3.1-lite-generate-preview", "Veo 3.1 Lite", 0.08),
    "fast": ("veo-3.1-fast-generate-preview", "Veo 3.1 Fast", 0.12),
    "standard": ("veo-3.1-generate-preview", "Veo 3.1 표준", 0.40),
}
SCOPES = {
    "none": "사용 안 함 (현재 방식: 이미지 줌·팬)",
    "opening": "오프닝 1장면",
    "key2": "핵심 2장면 (오프닝 + 핵심 장면)",
    "all": "전체 장면",
}
CLIP_LENGTHS = (4, 6, 8)  # Veo가 만드는 클립 길이(초)
POLL_SEC = 10
TIMEOUT_SEC = 600

ProgressFn = Optional[Callable[[str], Awaitable[None]]]


def clip_length(scene_seconds: float) -> int:
    """장면 길이에 맞는 가장 짧은 클립 길이 (8초보다 긴 장면은 8초 클립을 반복 재생)"""
    return next((c for c in CLIP_LENGTHS if c >= scene_seconds), CLIP_LENGTHS[-1])


def pick_scenes(sb: EditableStoryboard, scope: str) -> List[int]:
    """옵션에 따른 대상 장면 인덱스 (첨부 동영상이 이미 있는 장면은 제외)"""
    n = len(sb.shorts_scenes)
    if scope == "none" or n == 0:
        return []
    if scope == "opening":
        idx = [0]
    elif scope == "key2":
        # 오프닝 + 숫자가 강조된 장면(없으면 두 번째 장면)
        key = next((i for i, sc in enumerate(sb.shorts_scenes[1:], 1)
                    if any(ch.isdigit() for w in sc.emphasis_words for ch in w) and sc.section_type != "conclusion"), 1 if n > 1 else None)
        idx = [0] + ([key] if key is not None else [])
    else:
        idx = list(range(n))
    return [i for i in idx if not ((a := sb.asset(sb.shorts_scenes[i].asset_id)) and a.kind == "video" and a.source == "user")]


def estimate(sb: Optional[EditableStoryboard], scope: str, quality: str, shorts_seconds: int = 45) -> Tuple[int, float]:
    """(생성 초 수, 예상 비용 USD). 스토리보드가 있으면 장면별 예상 길이로, 없으면 쇼츠 길이로 추정"""
    price = VEO_MODELS[quality][2]
    if scope == "none":
        return 0, 0.0
    if sb and sb.shorts_scenes:
        secs = sum(clip_length(sb.shorts_scenes[i].duration_seconds) for i in pick_scenes(sb, scope))
    else:
        per = 8
        secs = {"opening": per, "key2": per * 2}.get(scope, max(per, int(round(shorts_seconds / 4.0) * 4)))
    return secs, round(secs * price, 2)


class VeoGenerator:
    def __init__(self, library: MediaLibrary, cache_dir: str):
        self.library = library
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    async def generate(self, sb: EditableStoryboard, scope: str, quality: str, api_key: str,
                       scene_seconds: Dict[int, float], progress: ProgressFn = None) -> Tuple[Dict[int, MediaAsset], List[str]]:
        """대상 장면별 Veo 클립 생성 → {장면 인덱스: 동영상 에셋}, 로그"""
        targets = pick_scenes(sb, scope)
        if not targets:
            return {}, []
        if not api_key:
            return {}, ["ℹ️ Gemini 키가 없어 Veo 영상화를 건너뛰었습니다."]
        from google import genai
        client = genai.Client(api_key=api_key)
        model, label, price = VEO_MODELS[quality]
        results: Dict[int, MediaAsset] = {}
        errors: List[str] = []
        billed_secs = 0
        done = 0

        async def one(i: int):
            nonlocal billed_secs, done
            scene = sb.shorts_scenes[i]
            seconds = clip_length(scene_seconds.get(i, scene.duration_seconds))
            asset = sb.asset(scene.asset_id)
            image_path = asset.preview_path if asset and asset.kind == "image" else None
            prompt = (f"{scene.visual_motion_prompt or scene.display_caption}\n"
                      "Gentle, natural cinematic motion. Vertical 9:16 short-form video. No text, no captions, no logos.")
            key_src = (open(image_path, "rb").read() if image_path else b"") + f"|{prompt}|{model}|{seconds}".encode()
            cached = os.path.join(self.cache_dir, hashlib.sha256(key_src).hexdigest()[:24] + ".mp4")
            try:
                if not os.path.exists(cached):
                    await self._create(client, model, prompt, image_path, seconds, cached)
                    billed_secs += seconds
                vid_id = f"V{i + 1}"
                results[i] = await self.library.ingest(cached, vid_id, original_name=f"Veo_{label}_{vid_id}.mp4", source="ai")
            except Exception as e:
                logger.warning(f"Veo 생성 실패 (장면 {i + 1}): {e}")
                errors.append(f"장면 {i + 1}: {type(e).__name__}: {str(e)[:90]}")
            done += 1
            if progress:
                await progress(f"Veo AI 영상 생성 중... ({done}/{len(targets)}) — 클립당 1~3분 소요")

        if progress:
            await progress(f"Veo AI 영상 생성 시작 ({len(targets)}개 장면, {label})")
        await asyncio.gather(*(one(i) for i in targets))

        logs = []
        if results:
            cost = f" · 이번 과금 약 ${billed_secs * price:.2f} ({billed_secs}초)" if billed_secs else " · 캐시 재사용(추가 과금 없음)"
            logs.append(f"🎞️ Veo 영상 {len(results)}개 적용 ({label}){cost}")
        if errors:
            logs.append(f"⚠️ Veo 영상 {len(errors)}개 생성 실패 → 해당 장면은 기존 줌·팬 효과로 렌더링 ({errors[0]})")
        return results, logs

    async def _create(self, client, model: str, prompt: str, image_path: Optional[str], seconds: int, out_path: str):
        from google.genai import types
        source = types.GenerateVideosSource(prompt=prompt)
        if image_path:
            with open(image_path, "rb") as f:
                source = types.GenerateVideosSource(
                    prompt=prompt, image=types.Image(image_bytes=f.read(), mime_type="image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"))
        operation = await client.aio.models.generate_videos(
            model=model,
            source=source,
            config=types.GenerateVideosConfig(number_of_videos=1, duration_seconds=seconds, aspect_ratio="9:16", resolution="1080p"),
        )
        waited = 0
        while not operation.done:
            if waited >= TIMEOUT_SEC:
                raise TimeoutError(f"{TIMEOUT_SEC // 60}분 안에 생성되지 않았습니다")
            await asyncio.sleep(POLL_SEC)
            waited += POLL_SEC
            operation = await client.aio.operations.get(operation)
        if getattr(operation, "error", None):
            raise RuntimeError(str(operation.error)[:200])
        response = operation.response
        videos = getattr(response, "generated_videos", None) or []
        if not videos:
            reasons = getattr(response, "rai_media_filtered_reasons", None)
            raise RuntimeError(f"영상이 생성되지 않았습니다 (안전 필터 등: {reasons})")
        tmp = out_path + ".part"
        await asyncio.to_thread(client.files.download, file=videos[0].video, destination=tmp)
        os.replace(tmp, out_path)
