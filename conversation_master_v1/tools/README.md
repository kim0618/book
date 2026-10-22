# 재생성 및 검증

Python 3 표준 라이브러리만 사용합니다. 저장소 루트에서 실행합니다.

```sh
python3 conversation_master_v1/tools/archive.py build
python3 conversation_master_v1/tools/archive.py verify
```

입력은 로컬 전용 `SOURCE_ARCHIVE/recovery_state/`의 정규화 메시지·분류 결과와 `SOURCE_ARCHIVE/original_exports/` 및 로컬 로그 사본입니다. 입력과 비공개 가림 규칙은 Git에서 제외되므로 이 저장소만 내려받은 환경에서는 원본을 대조하는 검증을 재현할 수 없습니다. 파일만 확인하려면 다음 명령을 사용합니다.

```sh
python3 conversation_master_v1/tools/archive.py check-files
```

`build`는 기존 원고나 원천 기록을 수정하지 않으며 이 아카이브의 생성 파일만 갱신합니다. `verify`는 원본 JSON의 모든 메시지 식별자·텍스트, 원본 사본 해시, 구간의 중복·공백, 보관 예외, 가림 처리 후 원문 일치, 출력 파일 해시를 검사하고 오류가 있으면 실패합니다. 이미 유실된 원본이나 누락된 첨부는 복구됐다고 간주하지 않습니다.

기존 분류가 없는 구간은 사용자 역할 메시지의 시작점에서 나누어 요청·응답을 그대로 보존합니다. 사건을 임의로 합치지 않으며, 그 구간의 배경·결과를 추측하여 작성하지 않습니다. 유사한 문장에 의한 세션 연결은 확정된 인과관계와 구분합니다.
