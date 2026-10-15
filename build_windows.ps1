# 로컬 Windows 배포 빌드 (GitHub Actions의 .github/workflows/build-windows.yml 과 같은 절차)
# 필요: Python 3.12, Visual Studio 2022 "C++를 사용한 데스크톱 개발" 워크로드 (Flutter SDK는 flet이 자동 설치)
# 사용: powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$FletCliVersion = "1.0.4"
$FfmpegVersion = "7.1.1"
$env:PYTHONUTF8 = "1"

$version = (python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")

python -m pip install --upgrade "flet-cli==$FletCliVersion"
flet build windows --yes --build-version $version
if ($LASTEXITCODE -ne 0) { throw "flet build 실패" }

# FFmpeg 번들 (한 번 받은 파일은 build\ffmpeg-cache 에 보관)
$cache = "build\ffmpeg-cache"
$zip = "$cache\ffmpeg-$FfmpegVersion.zip"
if (-not (Test-Path $zip)) {
    New-Item -ItemType Directory -Force $cache | Out-Null
    Invoke-WebRequest "https://github.com/GyanD/codexffmpeg/releases/download/$FfmpegVersion/ffmpeg-$FfmpegVersion-essentials_build.zip" -OutFile $zip
}
$extract = "$cache\ffmpeg-$FfmpegVersion"
if (-not (Test-Path $extract)) { Expand-Archive $zip $extract }
$src = Get-ChildItem $extract -Directory | Select-Object -First 1
$dst = "build\windows\ffmpeg"
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item "$($src.FullName)\bin\ffmpeg.exe", "$($src.FullName)\bin\ffprobe.exe" $dst -Force
Copy-Item "$($src.FullName)\LICENSE" "$dst\LICENSE.txt" -Force

New-Item -ItemType Directory -Force dist | Out-Null
$out = "dist\AnmasarangStudio-windows-x64-$version.zip"
Compress-Archive -Path "build\windows\*" -DestinationPath $out -Force
Write-Host "완료: $out (압축 해제 후 AnmasarangStudio.exe 실행)"
