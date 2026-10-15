import logging
import os
import json
import re
import base64
import asyncio
from typing import Optional, List, Dict, Any, Literal, Tuple
from pydantic import BaseModel, Field
from models.schema import (
    UserRequestPayload,
    EditableStoryboard,
    CardSlide,
    ShortsScene,
    MediaAsset,
)

# 모델 ID는 환경변수로 교체 가능 (모델 지원 종료 시 코드 수정 없이 대응)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

HOTLINE = "1577-1398"
WEBSITE = "anmasarang.com"


# ---------------------------------------------------------------------------
# LLM 구조화 출력 전용 스키마
# (EditableStoryboard의 Dict[str, Any] 비교표는 JSON Schema 강제 출력에 부적합하므로
#  행 단위 리스트로 받은 뒤 변환한다)
# ---------------------------------------------------------------------------
class LLMCardSlide(BaseModel):
    slide_number: int
    slide_type: Literal["cover", "body", "comparison_table", "call_to_action"]
    lead_headline: str
    body_content: str
    takeaway: str
    image_prompt: str = Field(description="asset_id가 비어 있을 때 AI 이미지 생성에 쓸 장면 묘사 (글자 없는 이미지)")
    asset_id: str = Field(default="", description="이 슬라이드에 배치할 첨부 에셋 ID (예: A1). 적합한 에셋이 없으면 빈 문자열")
    comparison_rows: List[List[str]] = Field(
        default_factory=list,
        description="comparison_table 슬라이드에서만 사용. 첫 행은 헤더(예: ['구분','도입 전','도입 후']), 이후 데이터 행",
    )


class LLMShortsScene(BaseModel):
    scene_number: int
    section_type: Literal["hook", "body", "conclusion"]
    narration_script: str
    display_caption: str
    visual_motion_prompt: str = Field(description="asset_id가 비어 있을 때 AI 이미지 생성에 쓸 장면 묘사")
    duration_seconds: float
    asset_id: str = Field(default="", description="이 씬 화면에 쓸 첨부 에셋 ID. 없으면 빈 문자열")
    clip_start: float = Field(default=0.0, description="동영상 에셋이면 사용 시작 시각(초)")
    emphasis_words: List[str] = Field(default_factory=list, description="display_caption 안에서 크게 강조할 핵심 단어 1~2개 (문구에 있는 그대로)")


class LLMAssetNote(BaseModel):
    asset_id: str
    description: str = Field(description="에셋에 보이는 내용 한 문장 요약 (한국어)")


class LLMStoryboard(BaseModel):
    asset_notes: List[LLMAssetNote] = Field(default_factory=list)
    title: str
    target_audience: str
    tone_and_manner: str
    visual_style: str
    card_slides: List[LLMCardSlide]
    shorts_scenes: List[LLMShortsScene]
    sns_caption: str
    hashtags: List[str]


# ---------------------------------------------------------------------------
# 타겟 클러스터별 도메인 팩 (수치를 새로 만들어내지 않도록 검증된 문구만 사용)
# ---------------------------------------------------------------------------
CLUSTER_PACKS: Dict[str, Dict[str, Any]] = {
    "b2b": {
        "why_headline": "왜 안마사랑 연계고용인가?",
        "why_body": [
            "보건복지부 유권해석에 근거한 합법 연계고용 모델입니다.",
            "국가공인 시각장애인 안마사(헬스키퍼)가 사내에서 임직원을 케어합니다.",
            "장애인 고용부담금 감면과 임직원 복지 향상을 한 번에 해결합니다.",
        ],
        "why_takeaway": "법적 리스크 없이 비용 절감과 복지를 동시에",
        "cta_headline": "우리 회사 맞춤 절감 시뮬레이션을 받아보세요",
        "cta_body": [
            "사업장 규모에 맞춘 도입 방안을 무료로 상담해 드립니다.",
            f"전문 상담 센터: {HOTLINE} | {WEBSITE}",
        ],
        "cta_takeaway": "ESG 상생 경영, 오늘 바로 시작하세요.",
        "cta_narration": f"우리 회사 맞춤 도입 상담은 안마사랑 고객센터 {HOTLINE}, 안마사랑닷컴에서 신청하세요.",
        "hashtags": ["#장애인고용부담금", "#연계고용", "#헬스키퍼", "#임직원복지", "#HR인사총무", "#ESG경영"],
    },
    "b2c": {
        "why_headline": "안마사랑 헬스케어 바우처, 이렇게 씁니다",
        "why_body": [
            "바우처 핀번호를 입력하면 플랫폼에 바로 충전됩니다.",
            "가까운 국가공인 안마원을 검색하고 원하는 시간에 예약합니다.",
            "방문 이용과 자택 출장 중 편한 방식을 선택할 수 있습니다.",
        ],
        "why_takeaway": "회사 복지 포인트를 가장 건강하게 쓰는 방법",
        "cta_headline": "지금 안마사랑에서 바우처를 사용해 보세요",
        "cta_body": [
            "국가공인 시각장애인 안마사의 전문 케어를 경험하세요.",
            f"고객센터: {HOTLINE} | {WEBSITE}",
        ],
        "cta_takeaway": "내 몸을 위한 가장 확실한 복지",
        "cta_narration": f"지금 안마사랑닷컴에서 바우처를 사용해 보세요. 고객센터는 {HOTLINE}입니다.",
        "hashtags": ["#헬스케어바우처", "#복지포인트", "#직장인건강", "#국가공인안마사", "#힐링"],
    },
    "csr": {
        "why_headline": "안마사랑이 만드는 상생의 가치",
        "why_body": [
            "시각장애인 안마사는 수혜 대상이 아닌 전문 일자리의 주체입니다.",
            "기업·기관과 지역 안마원을 연결해 지속 가능한 일자리를 만듭니다.",
            "건강한 일터와 포용적인 사회를 함께 만들어 갑니다.",
        ],
        "why_takeaway": "전문성과 존엄을 지키는 일자리 플랫폼",
        "cta_headline": "상생의 일자리에 함께해 주세요",
        "cta_body": [
            "기업·기관의 참여가 시각장애인 전문 일자리를 지킵니다.",
            f"문의: {HOTLINE} | {WEBSITE}",
        ],
        "cta_takeaway": "함께할 때 더 밝아지는 세상",
        "cta_narration": f"상생의 일자리에 함께해 주세요. 안마사랑 {HOTLINE}, 안마사랑닷컴.",
        "hashtags": ["#장애인일자리", "#시각장애인안마사", "#사회적가치", "#ESG", "#상생"],
    },
    "partner": {
        "why_headline": "안마사랑 파트너가 되어야 하는 이유",
        "why_body": [
            "고객사의 장애인 고용부담금 문제를 합법적으로 해결하는 솔루션입니다.",
            "기존 컨설팅·보험 영업에 결합할 수 있는 신규 제안 상품입니다.",
            "도입 이후 운영은 안마사랑이 전담합니다.",
        ],
        "why_takeaway": "고객 가치와 파트너 수익을 함께 키우는 모델",
        "cta_headline": "지금 파트너 제휴를 문의하세요",
        "cta_body": [
            "제휴 조건과 영업 자료를 상세히 안내해 드립니다.",
            f"제휴 문의: {HOTLINE} | {WEBSITE}",
        ],
        "cta_takeaway": "새로운 B2B 영업 파이프라인을 열어 보세요.",
        "cta_narration": f"파트너 제휴 문의는 안마사랑 고객센터 {HOTLINE}으로 연락 주세요.",
        "hashtags": ["#B2B영업", "#법인영업", "#경영컨설팅", "#파트너모집", "#연계고용"],
    },
}

# 팩트 락 라벨 (scenarios.json의 fact_locks 키 → 표시용 한글)
FACT_LABELS = {
    "burden_reduction": "고용부담금 감면", "legal_basis": "법적 근거", "operating_model": "운영 모델",
    "voucher_types": "바우처 권종", "pin_format": "충전 방식", "rate_comparison": "이용 요금",
    "contract_amount": "계약 규모", "tax_saving_per_person": "1인당 절세", "fund_mechanism": "기금 구조",
    "break_time": "휴식 시간", "qualification": "자격", "pain_relief": "통증 완화",
    "treatment_time": "시술 시간", "symptoms": "주요 증상", "customer_center": "고객센터",
    "burden_scale": "부담금 규모", "healthcare_worker": "의료진 케어", "legal_compliance": "법 준수",
    "three_year_burden": "3년 부담금", "report_format": "보고서 형식", "target_group": "대상",
    "developer_pain": "개발자 통증", "talent_retention": "인재 유지", "in_house_room": "사내 공간",
    "satisfaction_score": "만족도", "track_record": "운영 실적", "audit_safety": "감사 안전성",
    "medical_law": "의료법", "court_precedent": "판례", "comparison": "법적 구조",
    "ai_voice_tool": "취재 도구", "dignity_of_work": "일의 가치", "interview_focus": "취재 초점",
    "regional_editions": "지역판 발행", "local_matching": "지역 매칭", "community_welfare": "지역 복지",
    "acquired_blindness": "중도실명 비율", "education_hours": "교육 이수", "constitutional_court": "헌법재판소",
    "no_upfront_fee": "초기 비용", "bundle_deal": "결합 상품",
}

# 원문에서 "수치형 팩트"를 추출하는 패턴 (금액/시간/점수/비율/전화번호 등)
FACT_REGEX = re.compile(
    r"\d{4}-\d{4}"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:억|만|천)?\s*(?:원권|원|시간|점|%|명|분|자리|주|년|개월|개|곳|배)"
)


class AIDirectorService:
    """Gemini 및 Claude를 지원하는 멀티 AI 디렉터 및 팩트 락 / 마스킹 엔진"""

    # 실명 엔티티 마스킹 사전 (긴 키부터 치환)
    ENTITY_MASK_MAP = {
        "경기도청 북부청사": "수도권 광역지자체 G청 북부청사",
        "서울대병원": "국내 빅5 대형 대학병원 S병원",
        "경기도청": "수도권 광역지자체 G청",
        "IBM": "글로벌 IT 기업 I사",
        "KBS": "대형 공영방송사 K사",
        "KT": "국내 대형 통신사 K사",
    }

    REQUEST_SENTENCE = re.compile(r"(만들|제작|생성|작성|편집)\S*\s*(고\s*싶|해\s*줘|해\s*주세요|주세요|줘|바랍니다|부탁)")

    def __init__(self):
        self.scenarios_data = self._load_scenarios()

    def _load_scenarios(self) -> List[Dict[str, Any]]:
        preset_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scenarios.json")
        if os.path.exists(preset_path):
            with open(preset_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    # ------------------------------------------------------------------
    # 진입점
    # ------------------------------------------------------------------
    async def generate_storyboard(self, payload: UserRequestPayload) -> EditableStoryboard:
        """선택된 AI 공급자(gemini 또는 claude)를 통해 스토리보드를 비동기 생성"""
        provider = (payload.ai_provider or "gemini").lower()
        if provider == "claude":
            api_key = payload.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        else:
            api_key = payload.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        source = self._resolve_source(payload)

        storyboard = None
        notes: List[str] = []
        if api_key:
            try:
                if provider == "gemini":
                    storyboard = await self._call_gemini(payload, source, api_key)
                elif provider == "claude":
                    storyboard = await self._call_claude(payload, source, api_key)
            except Exception as e:
                notes.append(f"⚠️ {provider} 호출 실패 → 규칙 기반 엔진으로 전환 ({type(e).__name__}: {str(e)[:120]})")
                logging.getLogger(__name__).warning(f"{provider} 호출 오류: {e}")
        else:
            notes.append(f"ℹ️ {provider.upper()} API 키 미설정 → 규칙 기반 스마트 엔진으로 생성")

        auto_assign = storyboard is None
        if not storyboard:
            storyboard = self._generate_rule_based_storyboard(payload, source)
        self._ensure_emphasis(storyboard)

        self._bind_assets(storyboard, payload, auto_assign, notes)
        return self._apply_guardrails(storyboard, payload, source, notes)

    # 강조어 후보: 도메인 핵심 단어 (키네틱 타이포에서 크게 표시)
    EMPHASIS_KEYWORDS = ["합법", "감면", "절감", "절세", "국가공인", "만족도", "바우처", "의료법", "위반", "형사처벌",
                         "헬스키퍼", "연계고용", "무료", "선수금", "전원일치", "합헌", "상생", "일자리", "통증", "안마사랑"]

    EMPHASIS_NUMBER = re.compile(r"\d{4}-\d{4}|\d[\d,]*(?:\.\d+)?\s*(?:억|만|천)?\s*(?:원권|원|점|%|시간|분|명|개월|년|곳|배|자리)?")

    def _ensure_emphasis(self, sb: EditableStoryboard):
        """씬별 강조어 검증·보완: 문구에 실제로 있는 단어만 남기고, 없으면 숫자 → 도메인 키워드 → 가장 긴 단어 순으로 선택"""
        for scene in sb.shorts_scenes:
            caption = scene.display_caption or ""
            words = [w for w in (scene.emphasis_words or []) if w and w.strip() and w.strip() in caption]
            if not words:
                words = [m.group(0).strip() for m in self.EMPHASIS_NUMBER.finditer(caption)][:2]
            if not words:
                words = [k for k in self.EMPHASIS_KEYWORDS if k in caption][:1]
            if not words and caption.strip():
                tokens = [t.strip(".,!?·…") for t in caption.split()]
                words = [max(tokens, key=len)] if tokens else []
            scene.emphasis_words = words[:2]

    # ------------------------------------------------------------------
    # 에셋 배치 (LLM 결과 검증 / 규칙 기반 자동 배치)
    # ------------------------------------------------------------------
    def _bind_assets(self, sb: EditableStoryboard, payload: UserRequestPayload, auto: bool, notes: List[str]):
        assets = list(payload.assets)
        sb.assets = assets
        by_id = {a.id: a for a in assets}
        for item in list(sb.card_slides) + list(sb.shorts_scenes):
            if item.asset_id and item.asset_id not in by_id:
                item.asset_id = None
        if not assets:
            return

        if auto or not any(s.asset_id for s in sb.card_slides):
            # 카드: 비교표 슬라이드를 제외하고 첨부 순서대로 1회씩 배치
            eligible = [s for s in sb.card_slides if s.slide_type != "comparison_table"]
            for slide, asset in zip(eligible, assets):
                slide.asset_id = asset.id
        if auto or not any(sc.asset_id for sc in sb.shorts_scenes):
            # 쇼츠: 동영상을 우선 배치하고, 남는 씬은 동영상의 다른 구간을 재사용
            ordered = [a for a in assets if a.kind == "video"] + [a for a in assets if a.kind == "image"]
            videos = [a for a in assets if a.kind == "video"]
            for i, scene in enumerate(sb.shorts_scenes):
                if i < len(ordered):
                    scene.asset_id = ordered[i].id
                elif videos:
                    scene.asset_id = videos[i % len(videos)].id

        # 동영상 사용 구간: 같은 영상이 여러 씬에 쓰이면 서로 다른 구간에서 시작
        usage: Dict[str, int] = {}
        for scene in sb.shorts_scenes:
            asset = by_id.get(scene.asset_id or "")
            if not asset or asset.kind != "video":
                scene.clip_start = 0.0
                continue
            k = usage.get(asset.id, 0)
            usage[asset.id] = k + 1
            if auto or scene.clip_start <= 0 and k > 0:
                times = asset.keyframe_times or [0.0]
                scene.clip_start = max(0.0, times[k % len(times)] - 0.5)
            scene.clip_start = round(min(max(0.0, scene.clip_start), max(0.0, asset.duration - 1.0)), 2)

        used = {i.asset_id for i in list(sb.card_slides) + list(sb.shorts_scenes) if i.asset_id}
        unused = [a.id for a in assets if a.id not in used]
        notes.append(f"🖼️ 첨부 에셋 {len(assets)}개 배치 완료" + (f" (미사용: {', '.join(unused)})" if unused else ""))

    # ------------------------------------------------------------------
    # 원천 텍스트 해석 (시나리오 프리셋 / 사용자가 편집한 텍스트 / 자유 입력)
    # ------------------------------------------------------------------
    def _resolve_source(self, payload: UserRequestPayload) -> Dict[str, Any]:
        scenario = None
        if payload.scenario_id:
            scenario = next((s for s in self.scenarios_data if s.get("id") == payload.scenario_id), None)

        text = (payload.raw_text or "").strip()
        title_match = re.match(r"^\[(.+?)\]\s*$", text.splitlines()[0]) if text else None
        sections = self._parse_sections(text)
        edited = False

        if sections:
            # 상황/전개/결과 형식 → 사용자가 편집한 내용을 그대로 반영
            situation, development, result = sections.get("상황", ""), sections.get("전개", ""), sections.get("결과", "")
            title = title_match.group(1) if title_match else (scenario.get("title") if scenario else "")
            if scenario and not self._same_as_preset(scenario, situation, development, result):
                # 사용자가 원문을 고쳤다면 프리셋 팩트 대신 편집된 텍스트의 수치를 기준으로 검증
                edited = True
        elif scenario and (not text or text == scenario.get("situation", "").strip()):
            situation, development, result = scenario.get("situation", ""), scenario.get("development", ""), scenario.get("result", "")
            title = scenario.get("title", "")
        else:
            # 자유 입력: 시나리오 프리셋과 무관하게 입력 문장을 3등분
            scenario = None
            sentences = self._split_sentences(text)
            # "~ 만들어 주세요" 같은 제작 요청 문장은 콘텐츠 본문에서 제외 (모두 요청문이면 그대로 사용)
            content_only = [x for x in sentences if not self.REQUEST_SENTENCE.search(x)]
            sentences = content_only or sentences
            n = len(sentences)
            a, b = max(1, round(n / 3)), max(1, round(n * 2 / 3))
            situation = " ".join(sentences[:a])
            development = " ".join(sentences[a:b])
            result = " ".join(sentences[b:])
            title = title_match.group(1) if title_match else (self._headline(sentences[0], 30) if sentences else "안마사랑 맞춤 헬스케어")

        if not title:
            title = "안마사랑 맞춤 헬스케어"
        core_title = re.sub(r"^시나리오\s*\d+\s*:\s*", "", title).strip()

        fact_locks = scenario.get("fact_locks", {}) if scenario and not edited else {}
        source_text = " ".join([situation, development, result] + list(fact_locks.values()))
        return {
            "scenario": scenario,
            "title": title,
            "core_title": core_title,
            "situation": situation.strip(),
            "development": development.strip(),
            "result": result.strip(),
            "fact_locks": fact_locks,
            "facts": self._extract_facts(source_text),
        }

    @staticmethod
    def _same_as_preset(scenario: Dict[str, Any], situation: str, development: str, result: str) -> bool:
        norm = lambda t: re.sub(r"\s+", "", t or "")
        return (norm(situation) == norm(scenario.get("situation"))
                and norm(development) == norm(scenario.get("development"))
                and norm(result) == norm(scenario.get("result")))

    @staticmethod
    def _parse_sections(text: str) -> Dict[str, str]:
        sections: Dict[str, str] = {}
        current = None
        for line in text.splitlines():
            m = re.match(r"^\s*(상황|전개|결과)\s*[:：]\s*(.*)$", line)
            if m:
                current = m.group(1)
                sections[current] = m.group(2).strip()
            elif current and line.strip():
                sections[current] += " " + line.strip()
        return sections

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text:
            return []
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    @staticmethod
    def _headline(sentence: str, limit: int = 38) -> str:
        """문장을 헤드라인 길이로 다듬기 (쉼표 절 우선, 그 다음 단어 경계)"""
        s = sentence.strip().rstrip(".")
        if len(s) <= limit:
            return s
        first_clause = re.split(r"[,，]\s*", s)[0]
        if 8 <= len(first_clause) <= limit:
            return first_clause
        cut = s[:limit]
        if " " in cut:
            cut = cut[: cut.rfind(" ")]
        return cut + "…"

    @staticmethod
    def _extract_facts(text: str) -> List[str]:
        seen, facts = set(), []
        for m in FACT_REGEX.finditer(text or ""):
            key = re.sub(r"\s+", "", m.group(0))
            if key not in seen:
                seen.add(key)
                facts.append(m.group(0).strip())
        return facts

    def _cluster_key(self, payload: UserRequestPayload, scenario: Optional[Dict[str, Any]]) -> str:
        label = payload.target_audience if payload.target_audience and payload.target_audience != "AI 자동 추천" else ""
        if not label and scenario:
            label = scenario.get("cluster", "")
        if "영업" in label or "파트너" in label:
            return "partner"
        if "B2C" in label or "B2E" in label or "이용자" in label:
            return "b2c"
        if "CSR" in label or "대중" in label:
            return "csr"
        return "b2b"

    # ------------------------------------------------------------------
    # LLM 호출
    # ------------------------------------------------------------------
    async def _call_gemini(self, payload: UserRequestPayload, source: Dict[str, Any], api_key: str) -> Optional[EditableStoryboard]:
        """Google Gemini API를 통한 구조화된 스토리보드 JSON 생성"""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        contents: List[Any] = [self._build_llm_prompt(payload, source)]
        for label, frames in self._asset_inputs(payload.assets):
            contents.append(label)
            for data in frames:
                contents.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LLMStoryboard,
                temperature=0.2,
            ),
        )
        llm_sb = LLMStoryboard.model_validate_json(response.text)
        return self._from_llm(llm_sb, payload, f"gemini:{GEMINI_MODEL}")

    async def _call_claude(self, payload: UserRequestPayload, source: Dict[str, Any], api_key: str) -> Optional[EditableStoryboard]:
        """Anthropic Claude API 구조화 출력(messages.parse)으로 스토리보드 생성"""
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        content: List[Dict[str, Any]] = [{"type": "text", "text": self._build_llm_prompt(payload, source)}]
        for label, frames in self._asset_inputs(payload.assets):
            content.append({"type": "text", "text": label})
            for data in frames:
                content.append({"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(data).decode()}})
        response = await client.beta.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            system="당신은 안마사랑(anmasarang.com) 헬스케어 플랫폼의 마케팅 디렉터입니다. 원문 수치를 절대 바꾸거나 새로 만들지 마십시오.",
            messages=[{"role": "user", "content": content}],
            output_format=LLMStoryboard,
        )
        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            raise RuntimeError(f"Claude 응답 불완전 (stop_reason={response.stop_reason})")
        return self._from_llm(response.parsed_output, payload, f"claude:{response.model}")

    @staticmethod
    def _asset_inputs(assets: List[MediaAsset]):
        """(설명 라벨, 대표 프레임 JPEG 바이트 목록) — 이미지는 1장, 동영상은 시점별 여러 장"""
        for a in assets:
            if a.kind == "video":
                times = ", ".join(f"{t:.1f}초" for t in a.keyframe_times)
                label = f"[{a.id}] 동영상 '{a.original_name}' ({a.width}x{a.height}, 길이 {a.duration:.1f}초). 아래 프레임은 각각 {times} 시점입니다."
            else:
                label = f"[{a.id}] 이미지 '{a.original_name}' ({a.width}x{a.height})"
            frames = []
            for kf in a.keyframes:
                with open(kf, "rb") as f:
                    frames.append(f.read())
            yield label, frames

    def _from_llm(self, llm_sb: LLMStoryboard, payload: UserRequestPayload, engine: str) -> EditableStoryboard:
        notes = {n.asset_id: n.description for n in llm_sb.asset_notes}
        for a in payload.assets:
            if notes.get(a.id):
                a.description = notes[a.id]
        slides = []
        for s in llm_sb.card_slides:
            table = None
            if s.comparison_rows and len(s.comparison_rows) >= 2:
                table = {row[0]: row[1:] for row in s.comparison_rows if row}
            slides.append(CardSlide(
                slide_number=s.slide_number, slide_type=s.slide_type, lead_headline=s.lead_headline,
                body_content=s.body_content, takeaway=s.takeaway, image_prompt=s.image_prompt,
                asset_id=s.asset_id or None, comparison_table=table,
            ))
        scenes = [ShortsScene(**{**sc.model_dump(), "asset_id": sc.asset_id or None}) for sc in llm_sb.shorts_scenes]
        return EditableStoryboard(
            title=llm_sb.title, target_audience=llm_sb.target_audience, tone_and_manner=llm_sb.tone_and_manner,
            visual_style=llm_sb.visual_style, is_anonymized=payload.anonymize, card_slides=slides,
            shorts_scenes=scenes, sns_caption=llm_sb.sns_caption, hashtags=llm_sb.hashtags, engine=engine,
        )

    def _build_llm_prompt(self, payload: UserRequestPayload, source: Dict[str, Any]) -> str:
        facts = "\n".join(f"- {v}" for v in source["fact_locks"].values()) or "- (별도 팩트 없음: 원문 수치만 사용)"
        if payload.assets:
            asset_rule = (
                f"- 아래에 첨부된 에셋({', '.join(a.id for a in payload.assets)})의 실제 내용을 보고, 내용이 맞는 슬라이드·씬의 asset_id에 배치할 것\n"
                "- 동영상 에셋은 프레임 시점을 참고해 해당 장면이 나오는 clip_start(초)를 지정할 것. 하나의 영상을 여러 씬에 다른 구간으로 써도 됨\n"
                "- 카피는 첨부 에셋에 실제로 보이는 장면과 어긋나지 않게 작성하고, asset_notes에 각 에셋 내용을 요약할 것\n"
                "- 적합한 에셋이 없는 슬라이드·씬은 asset_id를 빈 문자열로 두고 image_prompt/visual_motion_prompt에 생성할 장면을 구체적으로 묘사할 것"
            )
        else:
            asset_rule = "- 첨부 에셋이 없으므로 모든 asset_id는 빈 문자열로 두고 image_prompt/visual_motion_prompt에 장면을 구체적으로 묘사할 것"
        return f"""다음은 시각장애인 국가공인 안마사 연계고용 및 헬스케어 바우처 플랫폼 '안마사랑(anmasarang.com)'의 콘텐츠 생성 요청입니다.

[사용자 프롬프트 원문]:
{payload.raw_text.strip()}

[원문 해석 참고]:
- 제목: {source['title']}
- 상황: {source['situation']}
- 전개: {source['development']}
- 결과: {source['result']}

[반드시 보존할 핵심 팩트]:
{facts}

[설정]:
- 타겟 오디언스: {payload.target_audience}
- 톤앤매너: {payload.tone_and_manner}
- 비주얼 스타일: {payload.visual_style}
- 실명 마스킹: {payload.anonymize} (True면 IBM→글로벌 IT 기업 I사, 서울대병원→국내 빅5 대학병원 S병원, KBS→대형 공영방송사 K사 등으로 표기)
- 팩트 락: {payload.fact_lock} (True면 원문의 금액·시간·비율·점수·전화번호를 한 글자도 바꾸지 말고, 원문에 없는 수치는 만들지 말 것)

[작성 규칙]:
- 카드뉴스 {payload.card_count}장: 1장 cover, 중간은 body(수치 비교가 있으면 1장은 comparison_table + comparison_rows 작성), 마지막 장 call_to_action
- 각 lead_headline은 40자 이내, body_content는 줄바꿈으로 구분된 3~4줄, takeaway는 30자 이내
- 쇼츠 4~6씬, 전체 내레이션 {payload.shorts_seconds}초 내외(한국어 초당 약 6~7자): 첫 씬 hook, 중간 body, 마지막 씬 conclusion. display_caption은 30자 이내
- 각 씬의 emphasis_words에는 display_caption 속 핵심 단어 1~2개(숫자·금액·핵심 명사)를 문구에 적힌 그대로 넣을 것
{asset_rule}
- image_prompt/visual_motion_prompt는 이미지 안에 글자가 들어가지 않는 장면 묘사로 작성
- 마지막 장/씬에는 고객센터 {HOTLINE} 과 {WEBSITE} 를 포함
- 모든 문장은 한국어로 작성
"""

    # ------------------------------------------------------------------
    # 규칙 기반 스마트 엔진 (API 키가 없거나 호출 실패 시)
    # ------------------------------------------------------------------
    def _generate_rule_based_storyboard(self, payload: UserRequestPayload, source: Dict[str, Any]) -> EditableStoryboard:
        scenario = source["scenario"]
        pack = CLUSTER_PACKS[self._cluster_key(payload, scenario)]
        core_title = source["core_title"]

        target = payload.target_audience if payload.target_audience and payload.target_audience != "AI 자동 추천" else (
            scenario.get("target_audience") if scenario else "기업 의사결정권자")
        tone = payload.tone_and_manner if payload.tone_and_manner and payload.tone_and_manner != "AI 자동 추천" else (
            scenario.get("default_tone") if scenario else "정보 전달형")
        style = payload.visual_style or (scenario.get("default_style") if scenario else "실사풍 / 인포그래픽")

        sit = self._split_sentences(source["situation"])
        dev = self._split_sentences(source["development"])
        res = self._split_sentences(source["result"])
        fact_values = list(source["fact_locks"].values())

        cover_headline = self._headline(core_title, 40)
        section_labels = {"상황": "지금 무슨 일이 일어나고 있나?", "전개": "어떻게 해결했나?", "결과": "무엇이 달라졌나?"}

        def section_slide(no: int, sentences: List[str], tag: str, takeaway: str, prompt: str) -> CardSlide:
            if not sentences:
                sentences = [section_labels[tag]]
            headline = self._headline(sentences[0])
            if headline.rstrip("…") in cover_headline or cover_headline.rstrip("…") in headline:
                headline = section_labels[tag]
                body = sentences
            else:
                body = sentences[1:] if len(sentences) > 1 else sentences
            return CardSlide(
                slide_number=no, slide_type="body",
                lead_headline=headline,
                body_content="\n".join(body),
                takeaway=takeaway,
                image_prompt=prompt,
            )

        cover_body = [f"대상: {target}"] + ([f"핵심: {fact_values[0]}"] if fact_values else []) + (sit[:1])
        slides = [
            CardSlide(
                slide_number=1, slide_type="cover",
                lead_headline=cover_headline,
                body_content="\n".join(cover_body),
                takeaway="안마사랑 국가공인 시각장애인 헬스키퍼 · 헬스케어 바우처",
                image_prompt=f"Cover visual for '{core_title}', {style}, clean corporate healthcare aesthetic",
            ),
            section_slide(2, sit, "상황", self._headline(fact_values[1] if len(fact_values) > 1 else "지금 이 문제, 해결책이 있습니다", 30),
                          "Problem situation scene, empathetic and realistic"),
            section_slide(3, dev, "전개", self._headline(fact_values[2] if len(fact_values) > 2 else "안마사랑의 해법", 30),
                          "Solution in action, certified therapist providing care in a modern office"),
        ]

        if source["fact_locks"]:
            table = {"구분": ["검증된 핵심 팩트"]}
            for key, value in source["fact_locks"].items():
                table[FACT_LABELS.get(key, key.replace("_", " "))] = [value]
            slides.append(CardSlide(
                slide_number=4, slide_type="comparison_table",
                lead_headline="숫자로 확인하는 핵심 팩트",
                body_content="\n".join(fact_values),
                takeaway="모든 수치는 원문 그대로 보존됩니다 (Fact-Lock)",
                image_prompt="Clean infographic table with key facts, high contrast data visualization",
                comparison_table=table,
            ))
        else:
            points = [self._headline(x[0], 34) for x in (sit, dev, res) if x]
            slides.append(CardSlide(
                slide_number=4, slide_type="body", lead_headline="한눈에 보는 핵심 포인트",
                body_content="\n".join(points) or core_title, takeaway="상황 → 해법 → 결과",
                image_prompt="Three-step summary infographic",
            ))

        slides.append(section_slide(5, res, "결과", "변화는 이미 시작되었습니다",
                                    "Positive outcome, relieved and smiling people, warm cinematic lighting"))
        slides.append(CardSlide(
            slide_number=6, slide_type="body", lead_headline=pack["why_headline"],
            body_content="\n".join(pack["why_body"]), takeaway=pack["why_takeaway"],
            image_prompt="Brand value proposition visual for Anmasarang healthcare platform",
        ))
        slides.append(CardSlide(
            slide_number=7, slide_type="call_to_action", lead_headline=pack["cta_headline"],
            body_content="\n".join(pack["cta_body"]), takeaway=pack["cta_takeaway"],
            image_prompt=f"Friendly consultation call-to-action with phone number {HOTLINE}",
        ))

        slides = self._fit_card_count(slides, payload.card_count, sit + dev + res)
        for slide in slides:
            if slide.slide_type != "comparison_table":
                slide.image_prompt = self._visual_prompt(f"{slide.lead_headline}. {slide.body_content}", style)

        # 쇼츠 길이 예산: 한국어 내레이션 초당 약 6.5자
        budget = max(60, int(payload.shorts_seconds * 6.5))
        body_budget = max(20, (budget - len(core_title) - len(pack["cta_narration"]) - 10) // 3)

        def within(sentences: List[str]) -> str:
            out = ""
            for sent in sentences:
                if out and len(out) + len(sent) + 1 > body_budget:
                    break
                out = f"{out} {sent}".strip()
            return out

        # 쇼츠 5씬: 훅 → 상황 → 전개 → 결과 → CTA
        def scene(no: int, section: str, narration: str, caption: str, motion: str) -> ShortsScene:
            narration = narration.strip() or caption
            return ShortsScene(
                scene_number=no, section_type=section, narration_script=narration,
                display_caption=self._headline(caption, 34),
                visual_motion_prompt=self._visual_prompt(f"{caption}. {narration}", style, motion),
                duration_seconds=round(max(3.0, len(narration) / 7.0), 1),
            )

        hook_intro = self._tone_intro(tone)

        def section_head(sentences: List[str], tag: str) -> str:
            head = self._headline(sentences[0]) if sentences else section_labels[tag]
            return section_labels[tag] if head.rstrip("…") in cover_headline else head
        scenes = [
            scene(1, "hook", f"{hook_intro} {core_title}.".strip(), core_title, "Fast zoom-in hook with bold title"),
            scene(2, "body", within(sit), section_head(sit, "상황"), "problem situation"),
            scene(3, "body", within(dev), section_head(dev, "전개"), "solution in action"),
            scene(4, "body", within(res), section_head(res, "결과"), "positive outcome"),
            scene(5, "conclusion", pack["cta_narration"], f"상담 {HOTLINE}", "Call-to-action end card"),
        ]

        bullets = "\n".join(f"✔️ {v}" for v in fact_values) or "\n".join(f"✔️ {self._headline(x[0], 40)}" for x in (sit, dev, res) if x)
        sns_caption = (
            f"[{core_title}]\n\n"
            f"{source['situation']}\n\n"
            f"{bullets}\n\n"
            f"{res[0] if res else ''}\n\n"
            f"📞 상담 문의: {HOTLINE} | 🌐 {WEBSITE}"
        )
        hashtags = ["#안마사랑"] + pack["hashtags"] + ["#국가공인안마사"]

        return EditableStoryboard(
            title=core_title,
            target_audience=target,
            tone_and_manner=tone,
            visual_style=style,
            is_anonymized=payload.anonymize,
            card_slides=slides,
            shorts_scenes=scenes,
            sns_caption=sns_caption,
            hashtags=list(dict.fromkeys(hashtags)),
            engine="rule-based",
        )

    @staticmethod
    def _visual_prompt(text: str, style: str, extra: str = "") -> str:
        """AI 이미지 생성용 장면 묘사 (안마사랑 도메인 맥락 + 글자 없는 이미지)"""
        style_hint = "2D flat illustration, webtoon style" if ("일러스트" in style or "툰" in style or "만화" in style) else \
            "clean modern infographic-style illustration" if "다이어그램" in style else "photorealistic, natural light, documentary photo"
        return (f"장면: {text.strip()[:220]}\n"
                f"맥락: 한국의 기업·병원·공공기관에서 국가공인 시각장애인 안마사(헬스키퍼)가 임직원의 어깨·목을 전문적으로 케어하는 헬스케어 복지 서비스 '안마사랑'. {extra}\n"
                f"스타일: {style_hint}, Korean people, warm and trustworthy mood.\n"
                "제약: 이미지 안에 글자·숫자·로고·워터마크를 넣지 말 것.")

    def _fit_card_count(self, slides: List[CardSlide], count: int, sentences: List[str]) -> List[CardSlide]:
        """요청 장수(5~10장)에 맞춰 보조 슬라이드를 빼거나 '현장 스케치' 슬라이드를 추가"""
        count = max(5, min(10, count or 7))
        why_heads = {p["why_headline"] for p in CLUSTER_PACKS.values()}
        removable_checks = [
            lambda sl: sl.slide_type == "body" and sl.lead_headline in why_heads,
            lambda sl: sl.slide_type == "comparison_table" or sl.lead_headline == "한눈에 보는 핵심 포인트",
        ]
        for check in removable_checks:
            if len(slides) <= count:
                break
            slides = [sl for sl in slides if not check(sl)]
        extra_idx = 0
        while len(slides) < count:
            sent = sentences[extra_idx % len(sentences)] if sentences else "안마사랑 헬스키퍼 현장"
            slides.insert(len(slides) - 1, CardSlide(
                slide_number=0, slide_type="body", lead_headline="현장 스케치",
                body_content=sent, takeaway="국가공인 시각장애인 안마사가 함께합니다", image_prompt=""))
            extra_idx += 1
        for i, sl in enumerate(slides):
            sl.slide_number = i + 1
        return slides

    @staticmethod
    def _tone_intro(tone: str) -> str:
        if "경고" in tone or "경각심" in tone:
            return "알고 계셨습니까?"
        if "이익" in tone or "효율" in tone or "비즈니스" in tone:
            return "숫자로 확인하세요."
        if "유머" in tone or "공감" in tone or "트렌디" in tone:
            return "혹시 저만 이런가요?"
        if "감동" in tone or "가치" in tone or "역경" in tone:
            return "이 이야기를 들어보세요."
        return ""

    # ------------------------------------------------------------------
    # 가드레일: 실명 마스킹 + 팩트 락 검증
    # ------------------------------------------------------------------
    def _mask_text(self, text: str) -> str:
        if not text:
            return text
        res = text
        for real, masked in sorted(self.ENTITY_MASK_MAP.items(), key=lambda kv: -len(kv[0])):
            # "통신 대기업 K사(KT)"처럼 익명명과 실명이 병기된 경우 괄호 속 실명만 제거
            res = re.sub(r"\s*\(\s*" + re.escape(real) + r"\s*\)", "", res)
            # 영문 약어는 단어 경계에서만 치환 (예: KTX의 KT는 제외) + 뒤따르는 조사 보정
            boundary = r"(?<![A-Za-z])" if re.fullmatch(r"[A-Za-z]+", real) else ""
            tail = r"(?![A-Za-z])" if boundary else ""
            pattern = boundary + re.escape(real) + tail + r"(은|는|이|가|을|를|과|와|으로|로)?(?![가-힣])"
            res = re.sub(pattern, lambda m, mk=masked: mk + self._fix_particle(mk, m.group(1)), res)
            res = re.sub(boundary + re.escape(real) + tail, masked, res)
        return res

    @staticmethod
    def _fix_particle(word: str, particle: Optional[str]) -> str:
        if not particle:
            return ""
        last = word[-1]
        has_batchim = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
        pairs = {"은": ("은", "는"), "는": ("은", "는"), "이": ("이", "가"), "가": ("이", "가"),
                 "을": ("을", "를"), "를": ("을", "를"), "과": ("과", "와"), "와": ("과", "와"),
                 "으로": ("으로", "로"), "로": ("으로", "로")}
        with_b, without_b = pairs[particle]
        if particle in ("으로", "로") and (ord(last) - 0xAC00) % 28 == 8:  # ㄹ 받침은 '로'
            return "로"
        return with_b if has_batchim else without_b

    def _apply_guardrails(self, storyboard: EditableStoryboard, payload: UserRequestPayload,
                          source: Dict[str, Any], notes: List[str]) -> EditableStoryboard:
        logs: List[str] = list(notes)
        logs.append(f"🤖 생성 엔진: {storyboard.engine or 'unknown'}")

        if payload.anonymize:
            m = self._mask_text
            storyboard.title = m(storyboard.title)
            storyboard.sns_caption = m(storyboard.sns_caption)
            storyboard.hashtags = [m(h) for h in storyboard.hashtags]
            for slide in storyboard.card_slides:
                slide.lead_headline = m(slide.lead_headline)
                slide.body_content = m(slide.body_content)
                slide.takeaway = m(slide.takeaway)
                if slide.comparison_table:
                    slide.comparison_table = {m(k): [m(str(v)) for v in (vals if isinstance(vals, list) else [vals])]
                                              for k, vals in slide.comparison_table.items()}
            for scene in storyboard.shorts_scenes:
                scene.narration_script = m(scene.narration_script)
                scene.display_caption = m(scene.display_caption)
                for w in scene.word_timestamps:
                    w.text = m(w.text)
            storyboard.is_anonymized = True
            logs.append("🔒 엔티티 마스킹 완료: 실명 기업/기관명이 이니셜로 치환되었습니다.")

        if payload.fact_lock:
            output_text = re.sub(r"\s+", "", self._storyboard_text(storyboard))
            facts = source["facts"]
            if not facts:
                logs.append("ℹ️ 팩트 락: 원문에서 검증할 수치형 팩트가 발견되지 않았습니다.")
            for fact in facts:
                if re.sub(r"\s+", "", fact) in output_text:
                    logs.append(f"✅ 팩트 보존 확인: {fact}")
                else:
                    logs.append(f"⚠️ 팩트 누락/변형 의심: '{fact}' 가 결과물에 없습니다. 검수가 필요합니다.")
        else:
            logs.append("ℹ️ 팩트 락 비활성화: 수치 보존 검증을 건너뛰었습니다.")

        storyboard.fact_check_log = logs
        return storyboard

    @staticmethod
    def _storyboard_text(sb: EditableStoryboard) -> str:
        parts = [sb.title, sb.sns_caption]
        for s in sb.card_slides:
            parts += [s.lead_headline, s.body_content, s.takeaway]
            if s.comparison_table:
                parts += [json.dumps(s.comparison_table, ensure_ascii=False)]
        for sc in sb.shorts_scenes:
            parts += [sc.narration_script, sc.display_caption]
        return " ".join(parts)

    @staticmethod
    def fact_status(storyboard: EditableStoryboard) -> Tuple[int, int]:
        """(보존된 팩트 수, 누락 의심 팩트 수)"""
        ok = sum(1 for l in storyboard.fact_check_log if l.startswith("✅"))
        warn = sum(1 for l in storyboard.fact_check_log if l.startswith("⚠️ 팩트"))
        return ok, warn
