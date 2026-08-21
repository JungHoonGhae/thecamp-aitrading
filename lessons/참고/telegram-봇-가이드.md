# 텔레그램 봇 만들기 (5분)

점검 결과를 텔레그램으로 받으려면 **봇 토큰**과 **채널(또는 나와의 대화) ID** 두 개만
있으면 됩니다. 3~4주차에서도 같은 이름(`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`)을
씁니다 — 여기서 만든 봇을 그대로 이어 가세요.

## 순서
1. 텔레그램에서 **@BotFather** 검색 → 대화 시작 → `/newbot`.
2. 봇 이름을 정한다 (표시 이름, 그다음 `@…bot` 사용자명).
3. BotFather가 준 **토큰**(긴 문자열)을 복사한다. 이건 열쇠라 **공유·업로드 금지**.
4. 방금 만든 봇을 검색해 열고 **`/start`** 를 보낸다. (채널을 쓸 거면 채널에 봇을 관리자로 추가)
5. 브라우저 주소창에 붙여넣는다 (토큰만 바꿔서):
   ```
   https://api.telegram.org/bot여기에_토큰/getUpdates
   ```
6. 열린 글에서 `"chat":{"id":` 뒤에 나오는 **숫자**가 채널 ID 입니다.
   (나와의 대화면 양수, 채널이면 보통 `-100`으로 시작합니다)

> 숫자가 안 보이면: 봇에게 아무 말이나 한 번 더 보내고, 주소창을 새로고침하세요.

## 이 프로젝트에 쓰기
`.env.example` 을 복사해 `.env` 로 만든 뒤 두 줄을 채웁니다.
```
TELEGRAM_BOT_TOKEN=복사한_토큰
TELEGRAM_CHANNEL_ID=복사한_숫자
```
그다음 평소처럼 실행하면 화면 대신 텔레그램으로 갑니다.
```
python agent/agent.py
```
환경변수로 바로 넣을 수도 있습니다.
```
TELEGRAM_BOT_TOKEN="토큰" TELEGRAM_CHANNEL_ID="숫자" python agent/agent.py
```
Windows(PowerShell):
```
$env:TELEGRAM_BOT_TOKEN="토큰"; $env:TELEGRAM_CHANNEL_ID="숫자"; python agent/agent.py
```

## 주의
- 토큰은 그 봇으로 글을 쓸 수 있는 열쇠입니다. **공유·업로드 금지.**
- 없어도 실습은 됩니다 — 보고가 화면에만 나옵니다.
