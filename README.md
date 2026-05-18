# 🔍 수익형 키워드 분석기

뉴스 기사를 붙여넣으면 네이버 블로그에 적합한 수익성 키워드와 제목을 자동 생성합니다.

## 기능
- Claude AI로 기사에서 SEO 키워드 15개 자동 추출
- 네이버 검색광고 API로 월간 검색량 실제 조회
- 네이버 블로그 검색 API로 경쟁 문서 수 확인
- 경쟁 강도 자동 계산 (문서량 ÷ 검색량)
- 최적 키워드 TOP 5 선별 + 블로그 제목 5개 생성

## 빠른 시작

### 1. 저장소 클론
```bash
git clone https://github.com/hkno3/keyword.git
cd keyword
```

### 2. 가상환경 생성 및 패키지 설치
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 환경변수 설정
```bash
cp .env.example .env
```
`.env` 파일을 열고 `ANTHROPIC_API_KEY` 값을 입력하세요.  
(네이버 API 키는 이미 설정되어 있습니다)

### 4. 앱 실행
```bash
streamlit run app.py
```
브라우저에서 `http://localhost:8501` 자동으로 열립니다.

## 사용 방법
1. 사이드바에 Claude API 키 확인
2. 뉴스 기사 전체를 텍스트 박스에 붙여넣기
3. **키워드 분석 시작** 버튼 클릭
4. 결과 테이블에서 ⭐⭐⭐⭐⭐ 키워드 확인
