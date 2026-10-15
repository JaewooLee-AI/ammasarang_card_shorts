# 안마사랑(Anmasarang) AI 콘텐츠 스튜디오 (Flet 1.0.4 + Stitch Design)

**안마사랑(Anmasarang)**의 시각장애인 국가공인 안마사 연계고용 및 헬스케어 바우처 플랫폼 비즈니스 모델을 기반으로, 기업 맞춤형 **카드뉴스(1080x1350)** 및 **쇼츠/릴스(9:16 세로형 1080x1920)** 콘텐츠를 자동 생성하는 AI 스튜디오 애플리케이션입니다.

---

## 🌟 주요 특징 및 아키텍처 하이라이트

1. **최신 Flet 1.0.4 프레임워크 기반 구축**
   - 구버전 문법(UserControl 등)을 완전히 배제하고, Flet 1.0+ 선언형 컴포넌트 아키텍처와 `ft.Colors`, `ft.Icons` (PascalCase), 비동기 이벤트 루프(`asyncio`) 적용
   - `flet-video` (`ftv.Video`)를 연동하여 앱 내에서 9:16 쇼츠 동영상을 직접 재생하고 썸네일을 캡처하는 미디어 스튜디오 구현

2. **Google Gemini & Anthropic Claude 듀얼 AI 디렉터 지원**
   - **fal.ai 대신 Gemini 또는 Claude API**를 선택하여 사용할 수 있도록 구성
   - `google-genai` (기본 `gemini-2.5-flash`) 및 `anthropic` (기본 `claude-opus-5-5`, 구조화 출력 `messages.parse`) 공식 SDK 탑재
   - 모델은 환경변수 `GEMINI_MODEL`, `CLAUDE_MODEL`로 교체 가능
   - API 호출이 실패하면 사유를 '팩트 락 & 마스킹 검증' 탭에 남기고 규칙 기반 엔진으로 자동 전환 (헤더 배지에 실제 사용 엔진 표시)
   - API 키가 없을 때도 도메인 지식이 완벽히 내장된 스마트 폴백 엔진으로 즉시 작동 및 시연 가능

3. **Stitch 디자인 시스템 (Civic Trust & Cognitive Clarity) 기반 고품격 UI**
   - 기관의 신뢰감과 현대적 테크 감성을 결합한 **Modern Enterprise 3단 레이아웃**
   - **좌측 패널**: 프롬프트 입력, 이미지·동영상 첨부, 생성 옵션, 팩트 락 & 마스킹 토글, AI 공급자·API 키 설정
   - **중앙 패널**: AI 디렉터가 기획한 슬라이드별 Lead-Body-Takeaway 및 쇼츠 대본/자막/타임라인을 인라인으로 직접 검수 및 수정(Human-in-the-Loop)
   - **우측 패널**: 카드뉴스 1080x1350 캐러셀 슬라이드 넘겨보기, 9:16 쇼츠 비디오 플레이어 재생, SNS 본문 캡션 및 해시태그 원클릭 복사

4. **철저한 비즈니스 팩트 락(Fact-Lock) 및 엔티티 마스킹(Masking)**
   - **팩트 락(Fact-Lock)**: 고용부담금 26억→21억 원(5억 감면), 경기도청 3년 만족도 97.14점, 소득세 25만 원 절세, 2,500시간 의학 이수(출석률 80%), 바우처 8만/15만 원, 고객센터 1577-1398 등 핵심 수치 왜곡 원천 차단
   - **엔티티 마스킹**: 대외 배포용 시 IBM -> 글로벌 IT 기업 I사, 서울대병원 -> 국내 빅5 대학병원 S사, KBS -> 대형 공영방송사 K사로 자동 치환

5. **자체 듀얼 렌더링 파이프라인 (카드뉴스 & 쇼츠/릴스)**
   - **카드뉴스**: 1080x1350(4:5) Smart Brevity 레이아웃, 인포그래픽 비교표, 안마사랑 브랜드 아이덴티티를 고화질 PNG 및 반응형 HTML로 단 1초 만에 렌더링
   - **쇼츠/릴스**: 씬별 한국어 TTS(macOS Yuna → gTTS 폴백) + 단어별 노래방식 하이라이트 자막(Pillow로 직접 합성하므로 libass 없는 FFmpeg에서도 동작) + FFmpeg 단일 패스 인코딩으로 MP4 생성. 편집용 `captions.ass` 사이드카도 함께 저장

---

## 🎬 사용 흐름 (프롬프트 + 내 미디어 → 카드뉴스·쇼츠)

1. **프롬프트 입력**: 만들고 싶은 콘텐츠를 설명합니다. (`data/scenarios.json` 예시 파일이 있으면 `예시 불러오기`로 선택 가능 — 공개 저장소에는 포함되지 않음)
2. **이미지·동영상 첨부** (선택): 현장 사진, 시술 영상, 공문 캡처 등. 웹 모드에서는 서버로 업로드 후 자동 분석됩니다.
3. **옵션**: 카드 장수(5~10), 쇼츠 길이(30/45/60초), 타겟·톤·비주얼 스타일, AI 이미지 생성 여부
4. **AI 디렉터 생성**: 선택한 LLM(Gemini 또는 Claude)이 첨부 미디어를 직접 보고(동영상은 대표 프레임 4장)
   카피를 쓰고, 어떤 사진/영상 구간을 몇 번째 슬라이드·씬에 쓸지 배치합니다.
5. **AI 이미지 보충**: 배치할 미디어가 없는 슬라이드·씬은 **Gemini 이미지 모델**로 생성합니다.
   (Claude API는 이미지 생성을 지원하지 않으므로 AI 이미지는 Gemini 키가 있을 때만 생성, 없으면 브랜드 디자인 배경)
6. **검수**: 중앙 편집기에서 문구 수정, 슬라이드·씬별 배치 에셋 교체, 영상 시작 시각 조정
7. **렌더링**: 카드뉴스(사진 레이아웃) PNG/HTML, 쇼츠(첨부 영상 9:16 변환·이미지 모션 + TTS 내레이션 + 하이라이트 자막) MP4

| 환경변수 | 기본값 | 용도 |
|---|---|---|
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | - | 화면에서 입력하지 않을 때 사용 |
| `GEMINI_MODEL` | `gemini-flash-latest` | Gemini 기획·미디어 분석 모델 |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Claude 기획·미디어 분석 모델 |
| `GEMINI_TTS_MODEL` | `gemini-3.8-flash-tts` (없으면 `gemini-2.5-flash-preview-tts`) | 쇼츠 내레이션 음성 합성 모델 |
| `GEMINI_IMAGE_MODEL` | `gemini-3.1-flash-image` (없으면 `gemini-2.5-flash-image`) | AI 이미지 생성 모델 |

> 첨부 동영상의 원본 소리는 사용하지 않고 TTS 내레이션으로 대체합니다.

**쇼츠 내레이션·자막 스타일 (렌더링 시점 옵션)**
- 내레이션: Gemini TTS(톤앤매너에 맞춘 말투·목소리 자동 선택, 결과 캐시로 재렌더링 시 재사용). 키가 없거나 실패하면 macOS Yuna → gTTS로 전체 대체 (Claude API는 음성 생성 미지원)
- 자막 스타일: **키네틱 타이포**(단어 순차 등장·마스크 리빌, 강조 단어 대형·형광펜, 숫자 장면은 대형 숫자 카운트업) 또는 **기본**(문구 팝업)
- 공통 모션: 장면별 카메라 무브(줌인·줌아웃·팬·대각선), 오프닝 펀치 줌, 장면 전환, 상단 진행 바
- **AI 영상화 (Veo, 선택 · 기본 사용 안 함)**: 오프닝 1장면 / 핵심 2장면 / 전체 장면을 Veo 3.1(Lite·Fast·표준)로 실제 움직이는 영상으로 생성.
  렌더링 전에 예상 비용 확인 창이 뜨며, 생성 결과는 캐시되어 같은 장면을 다시 렌더링해도 추가 과금이 없음.
  참고 요금(Google 공식, 1080p): Lite $0.08/초 · Fast $0.12/초 · 표준 $0.40/초 (오프닝 1장면 ≈ 8초 → Fast 약 $0.96)

**폰트 (assets/fonts, 배포 번들에 포함)**
- 타이틀·장면 핵심 문구·강조 단어·대형 숫자·카드 헤드라인: Gmarket Sans Bold (SIL OFL 1.1, `assets/fonts/OFL-GmarketSans.txt`)
- 하단 말자막·카드 본문: `assets/fonts/Pretendard-*.otf` 가 있으면 Pretendard, 없으면 시스템 한글 폰트(macOS: Apple SD Gothic Neo)

**배포(flet build / flet pack)**
- 폰트 등 리소스는 `assets/` → 배포 번들에 포함 (`flet pack main.py --add-data "assets:assets"`)
- 결과물·업로드·로그는 배포 앱에서 운영체제의 앱 데이터 폴더(`FLET_APP_STORAGE_DATA`)에 저장 (설치 폴더는 읽기 전용)
- 배포 설정은 `pyproject.toml`(`[tool.flet]`), 배포 앱 의존성은 `[project].dependencies` (웹 서버 패키지 제외)
- 배포 앱(`FLET_PLATFORM` 설정됨)은 `FLET_VIEW`와 관계없이 항상 데스크톱 앱으로 실행

**Windows 배포 자동 빌드 (GitHub Actions: `.github/workflows/build-windows.yml`)**
- `main` 푸시·PR·수동 실행(Actions → Build Windows → Run workflow): 빌드된 zip을 Actions 실행 결과의 Artifacts에서 다운로드
- `v*` 태그 푸시 시 GitHub Release에 zip 자동 첨부: `git tag v1.0.0 && git push origin v1.0.0` (태그 숫자가 앱 버전이 됨)
- 결과물 `AnmasarangStudio-windows-x64-<버전>.zip`: 압축을 풀고 `AnmasarangStudio.exe` 실행 (x64, ARM 윈도우에서도 동작)
- FFmpeg/ffprobe(gyan.dev essentials 빌드, GPL)를 `ffmpeg\` 폴더에 함께 배포 → 사용자 PC에 FFmpeg 설치 불필요
- 로컬 빌드: `powershell -ExecutionPolicy Bypass -File .\build_windows.ps1` (Visual Studio 2022 "C++를 사용한 데스크톱 개발" 필요, Flutter SDK는 자동 설치)
- 비공개 예시 데이터(`data/`)는 배포 번들에서 제외

---

## 📁 프로젝트 구조

```
ammasarang_card_shorts/
├── .venv/                         # Python 가상환경 (Flet 1.0.4, google-genai, anthropic, gTTS)
├── data/
│   └── scenarios.json            # (선택, 저장소 미포함) 예시 프롬프트 프리셋
├── models/
│   ├── __init__.py
│   └── schema.py                 # Pydantic 기반 스토리보드 및 슬라이드/씬 스키마
├── services/
│   ├── __init__.py
│   ├── ai_director.py            # Gemini & Claude 멀티모달 AI 디렉터 (미디어 분석·배치, 팩트 락 & 마스킹)
│   ├── media_assets.py           # 첨부 이미지/동영상 정규화·대표 프레임 추출
│   ├── image_generator.py        # Gemini 이미지 모델로 부족한 장면 AI 이미지 생성
│   ├── fonts.py                  # 한글 폰트 로더·픽셀 줄바꿈
│   ├── card_renderer.py          # 카드뉴스 고화질(1080x1350) 자동 렌더러
│   ├── shorts_renderer.py        # 쇼츠 타임라인 + TTS + ASS 자막 + FFmpeg 인코더
│   └── stitch_theme.py           # Stitch 디자인 시스템 색상/컴포넌트 토큰
├── templates/
│   └── card_template.html        # 카드뉴스 스마트 브레비티 반응형 HTML/CSS 템플릿
├── views/
│   ├── __init__.py
│   ├── left_input_panel.py       # 좌측: 시나리오 입력 & 전략 옵션 & AI 선택
│   ├── center_editor_panel.py    # 중앙: 스토리보드 검수 & 실시간 인라인 편집기
│   └── right_preview_panel.py    # 우측: 카드뉴스 캐러셀 + 쇼츠 비디오 + SNS 배포
├── exports/                      # 생성된 카드뉴스 PNG 세트 및 쇼츠 MP4 비디오
│   ├── cards/
│   └── shorts/
├── main.py                       # Flet 1.0.4 기반 메인 실행 애플리케이션
├── run.sh                        # 원클릭 실행 스크립트
└── README.md                     # 프로젝트 설명서
```

---

## 🚀 빠른 시작 가이드

### 0. 설치 (최초 1회)
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew install ffmpeg   # 쇼츠 렌더링에 필요
```

### 1. 실행 방법
터미널에서 아래 명령어를 실행하면 앱이 즉시 구동됩니다 (기본 http://localhost:8550, 이 PC에서만 접속 가능):

```bash
# 실행 스크립트 사용
./run.sh

# 또는 가상환경 직접 실행 (데스크톱 앱)
.venv/bin/python3 main.py

# 또는 웹 브라우저 모드로 실행
.venv/bin/flet run main.py --web
```

### 사전 요구사항
- Python 3.10+ (가상환경 `.venv`)
- **FFmpeg / ffprobe** (쇼츠 렌더링 필수): `brew install ffmpeg`
- 한글 폰트: macOS는 Apple SD Gothic Neo 자동 사용, Linux는 `fonts-nanum` 또는 Noto CJK 설치 권장
- 웹 모드(기본)는 `exports/` 폴더를 Flet `assets_dir`로 서빙하여 브라우저에서 미리보기·영상 재생. 데스크톱 앱 모드는 `FLET_VIEW=app .venv/bin/python3 main.py`

### 2. AI API 키 설정 (선택 사항)
환경 변수로 설정하거나 앱 좌측 패널의 입력 필드에 직접 입력할 수 있습니다:
```bash
# Gemini 사용 시
export GEMINI_API_KEY="your-gemini-api-key"

# Claude 사용 시
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```
*API 키가 없으면 규칙 기반 엔진으로 동작합니다(프롬프트 문장을 장면에 배분하는 수준이라 문구 품질이 낮고, AI 이미지 생성·미디어 분석은 동작하지 않음). 실사용에는 Gemini 키를 권장합니다.*
