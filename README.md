# BOOK

ChatGPT와 Claude를 활용해 약 1년 동안 실제 프로젝트를 진행한 대화를 바탕으로 쓰는 경험 논픽션 프로젝트입니다. 독자는 개발을 모르는 일반인입니다.

## 현재 상태

- 전체 대화 통합 마스터 V1 구축 완료(2026-10-22 스냅샷): 사건·보존 구간 4,953개, 원본 메시지 레코드 207,077개(웹 53,591 · 로컬 153,486).
- 원본 유실 로컬 세션 5개와 내보내기 첨부 손상은 해소되지 않았습니다. 상세 내용은 [검증 보고서](conversation_master_v1/MASTER_AUDIT.md)에 있습니다.
- 출판 원고는 아직 작성하지 않았습니다. 기존 C·D판 원고와 목차는 폐기했으며 기준으로 쓰지 않습니다.

## 주요 파일

| 위치 | 내용 |
|---|---|
| [CLAUDE.md](CLAUDE.md) | 집필 원칙과 작업 절차 |
| [conversation_master_v1/BOOK_CONVERSATION_MASTER.md](conversation_master_v1/BOOK_CONVERSATION_MASTER.md) | 사건·원문 마스터(시간순) |
| [conversation_master_v1/MASTER_INDEX.md](conversation_master_v1/MASTER_INDEX.md) | 전체 대화·로컬 세션 목록 |
| [conversation_master_v1/MASTER_AUDIT.md](conversation_master_v1/MASTER_AUDIT.md) | 누락·무결성 검증 보고서 |
| `conversation_master_v1/parts/` | 사건별 원문 전개본 |
| `conversation_master_v1/*.json` | 사건·메시지 대장, 연결 후보, 검증 데이터, 해시 목록 |
| [conversation_master_v1/tools/README.md](conversation_master_v1/tools/README.md) | 재생성·검증 방법 |
| [conversation_master_v1/SOURCE_ARCHIVE/README.md](conversation_master_v1/SOURCE_ARCHIVE/README.md) | 로컬 전용 원본 보관 범위 |
| `manuscript/chapters/` | 출판 원고 |
| [manuscript/SOURCES.md](manuscript/SOURCES.md) | 원고 근거의 사건 ID·메시지 ID |

가림 없는 원본과 회사·사생활 자료는 로컬 `SOURCE_ARCHIVE/`에만 보관하며 Git에서 제외합니다. 이 저장소의 가림 처리본은 조사 자료이며 출판 승인을 뜻하지 않습니다.

마스터 파일 검사(원본 없이 실행 가능):

```sh
python3 conversation_master_v1/tools/archive.py check-files
```
