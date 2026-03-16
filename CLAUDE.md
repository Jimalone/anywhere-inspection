# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

윤성에프앤씨 검수확인서(Inspection Report) 발행 시스템 ver2.0. Flask 웹앱으로, 모바일/PC에서 검수 정보를 입력하면 PDF를 생성하고 이메일로 자동 발송한다.

## Commands

```bash
# 의존성 설치
pip install -r requirements.txt

# 개발 서버 실행 (debug 모드)
python flask_app.py

# 프로덕션 실행
gunicorn flask_app:app
```

## Architecture

**단일 파일 Flask 앱** (`flask_app.py`)이 모든 백엔드 로직을 담당한다:

- `GET /` → 입력 폼 렌더링 (`templates/index.html`)
- `POST /preview` → 문서번호 없이 PDF 미리보기 생성 (브라우저에서 바로 표시)
- `POST /generate` → 문서번호 자동 채번 + PDF 생성 + Gmail SMTP 발송 + PDF base64를 JSON 응답으로 반환

**PDF 생성 흐름**: 폼 데이터 → base64 사진/서명을 임시 파일로 저장 → Jinja2로 `templates/report.html` 렌더링 → `xhtml2pdf`로 HTML→PDF 변환 → 임시 파일 정리

**문서번호 채번**: `doc_counter.json` 파일에 일자별 순번을 저장하여 `YYYY-MMDD-NNN` 형식으로 생성한다.

**프론트엔드** (`templates/index.html`): 바닐라 JS 단일 파일. 사진 업로드(HEIC 변환, 회전, 리사이즈), 서명 캔버스, localStorage 기반 정보 고정 기능을 포함한다.

## Key Details

- 한글 PDF 렌더링을 위해 `Pretendard-Regular.ttf` 폰트 파일이 프로젝트 루트에 필요하다.
- 사진은 최대 4장, 서버에서 480px 폭으로 리사이즈된다.
- 루트의 `index.html`, `report.html`은 이전 버전 파일이며, 실제 서비스는 `templates/` 디렉토리의 파일을 사용한다.
- 프로젝트 정보(과제명, 수행기간)는 `flask_app.py`의 `PROJECT_INFO` dict에 하드코딩되어 있다.
- 모든 보고서는 1장으로 출력하고 공간은 1page 전부를 사용한다.
