"""Rebuild and verify the conversation archive using private, preserved inputs."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

BASE = Path(__file__).resolve().parents[1]
REPO = BASE.parent
ARCH = BASE / 'SOURCE_ARCHIVE'
STATE = ARCH / 'recovery_state'
KST = dt.timezone(dt.timedelta(hours=9))
PLAT = {'chatgpt': 'ChatGPT', 'claude_web': 'Claude 웹',
        'claude_code_wsl': 'Claude Code (WSL)', 'claude_code_win': 'Claude Code (Windows)',
        'codex_wsl': 'Codex (WSL)', 'codex_win': 'Codex (Windows)'}
INCLUDED = {'PROJECT', 'BOUNDARY_INVEST', 'BOUNDARY_SELF', 'BOUNDARY_BACKGROUND'}
CLASS_KO = {'PROJECT': '프로젝트', 'BOUNDARY_INVEST': '개인 투자 경계 자료',
            'BOUNDARY_SELF': '작업 성향 경계 자료', 'BOUNDARY_BACKGROUND': '개발 배경·연결 미확인',
            'WORK': '회사 업무 제외', 'PRIVATE': '사생활 제외', 'META': '빈 대화·시스템 자료'}
PROJECT_KO = {'SITE_CALC': '계산기 사이트', 'SITE_WELFARE': '복지 정보 사이트',
              'SITE_TAROT': '타로 상담 사이트', 'SITE_FORM': '문서 양식 사이트',
              'BLOG_NAVER': '네이버 블로그', 'BLOG_PERSONAL': '개인 블로그',
              'TRADE_COIN_EARLY': '코인 자동매매 초기 기록', 'TRADE_US': '미국주식 연구·자동매매',
              'TRADE_CRYPTO': '암호화폐 매매 연구', 'GAME': '게임', 'APP': '앱',
              'STRATEGY': '아이디어·기획·수익화', 'AI_TOOLS': 'AI 도구·개발환경',
              'BOOK': '책·출판', 'OTHER': '기타·연결 미확인'}
PRIVATE_TITLE = re.compile(
    r'운세|사주|궁합|연애|MBTI|건강|통증|뻑뻑|피부|여드름|헬리코|내시경|물집|여행|호텔|신주쿠|'
    r'로밍|여권|쇼핑|침대|디퓨저|벽지|자취|에어컨|세탁기|물 새|커피|전자레인지|'
    r'전화번호|이메일 확인|가까운 장소|카페 위치|바 추천|인형뽑기|청년전용 대출|전세대출|'
    r'보험서류|고용보험|수험표|SQLD 시험|기출문제|운동|트레이닝|사진 보정|피부 보정|'
    r'퇴사 준비|이직|연봉|공무원|개인정보|신년|투표|날씨|청년 혜택|유심|넷플릭스|'
    r'발급|표준재무|부가세|영수증|중학교 표현|성향 분석|성격 분석|Profile', re.I)
PRIVATE_POLICY = json.loads((STATE / 'policy.json').read_text(encoding='utf-8')) if (STATE / 'policy.json').exists() else {}
WORK_TITLE = re.compile(
    r'OCR|리포트|report|XML|쿼리|SQL|'
    r'JSP|톰캣|톰켓|Tomcat|전자문서|전자서식|서식 통합|발송|고객|인수인계|PL 확인|'
    r'Azure|애저|MobaXterm|WebView|메일|EAN|바코드|ESG|기업 정보|PPT 데모|'
    + '|'.join(PRIVATE_POLICY.get('company_title_terms', ['(?!)'])), re.I)
CORP_TEXT = re.compile('|'.join(PRIVATE_POLICY.get('company_terms', ['(?!)'])), re.I)
PRIVATE_REQUEST = re.compile(r'생년월일|주민등록번호|연애\s*상담|사주\s*(?:풀이|분석)|건강\s*상담')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def time_iso(t):
    if t is None:
        return None
    if isinstance(t, (float, int)):
        return dt.datetime.fromtimestamp(t, KST).isoformat(timespec='seconds')
    return dt.datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(KST).isoformat(timespec='seconds')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_inputs():
    if not (STATE / 'norm/convs.json').exists():
        raise SystemExit('비공개 원본 입력이 없습니다. 파일 검사는 check-files 명령을 사용하십시오.')
    if not (STATE / 'policy.json').exists():
        raise SystemExit('비공개 분류·가림 정책 입력이 없습니다. 자료 생성을 중지합니다.')
    convs = read_json(STATE / 'norm/convs.json')
    sessions = read_json(STATE / 'norm/local_sessions.json')
    web = collections.defaultdict(list)
    local = collections.defaultdict(list)
    for name, dest in [('messages', web), ('local_messages', local)]:
        with (STATE / f'norm/{name}.jsonl').open(encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                dest[(r['platform'], r['conv_id'])].append(r)
    return convs, sessions, web, local


def masker():
    # Site/account-specific rules stay with the private source, never in Git.
    module = load_module('private_archive_masks', STATE / 'redact.py')
    rules = [
        (re.compile(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@'), r'\1⟦인증정보⟧@'),
        (re.compile(r'(?i)(?:https?|ssh|git|ftp|postgres(?:ql)?|mysql)://[^\s<>"\'`]+'), '⟦URL⟧'),
        (re.compile(r'(?i)\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:kr|com|net|org|io|dev|app|co|ai)(?:/[^\s<>"\'`]*)?\b'), '⟦도메인⟧'),
        (re.compile(r'(?:/(?:home|root|mnt|Users|var/www|srv)/|[A-Za-z]:[\\/])[^\s<>"\'`]*'), '⟦로컬 경로⟧'),
        (re.compile(r'(?i)(\b(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token)\b["\']?\s*[:=]\s*)[^\n,;]+'), r'\1⟦비밀정보 가림⟧'),
        (re.compile(r'(?i)((?:비밀번호|비번|패스워드)\s*(?:은|는|:|=|：|->|→)?\s*)[A-Za-z0-9!@#$%^&*._~+/-]{4,}'), r'\1⟦비밀정보 가림⟧'),
        (re.compile(r'(?<!\d)\d{6}\s*[-]\s*[1-8]\d{6}(?!\d)'), '⟦개인식별번호⟧'),
        (re.compile(r'(?<![\w-])[a-f0-9]{7,40}(?![\w-])', re.I), '⟦해시⟧'),
    ]

    def mask(text):
        t = text or ''
        for pattern, replacement in rules:
            t = pattern.sub(replacement, t)
        return module.redact(t)
    return mask


def project_for(c):
    t = (c.get('title') or '').lower()
    if re.search(r'us-b|미국.*(?:주식|전략)', t):
        return 'TRADE_US'
    if re.search(r'gift|암호화폐|선물|코인', t):
        return 'TRADE_CRYPTO'
    if re.search(r'로고|리뉴얼|계산기|디자인', t):
        return 'SITE_CALC'
    if re.search(r'책|출판|kdp', t):
        return 'BOOK'
    if re.search(r'블로그', t):
        return 'BLOG_NAVER'
    if re.search(r'앱|app', t):
        return 'APP'
    return 'AI_TOOLS'


def fallback_class(c, prior, msgs):
    title = c.get('title') or ''
    if prior.startswith('PRIVATE') or PRIVATE_TITLE.search(title):
        return 'PRIVATE'
    if prior == 'WORK' or re.search(r'회의 내용 정리', title):
        return 'WORK'
    if not msgs:
        return 'META'
    if re.search(r'성향|성격|1억', title):
        return 'BOUNDARY_SELF'
    if re.search(r'투자|주식.*(?:리서치|분석)|전망 분석|금리|TRON|출금|과세', title, re.I):
        return 'BOUNDARY_INVEST'
    if prior == 'PRE':
        if WORK_TITLE.search(title) or any(CORP_TEXT.search(r['text'] or '') for r in msgs):
            return 'WORK'
        return 'BOUNDARY_BACKGROUND'
    return 'PROJECT'


def finalize_segments(convs, web):
    labels = read_json(STATE / 'labels.json')
    by_unit = {}
    recovered = []
    for p in sorted((STATE / 'results').glob('batch_*.json')):
        for unit in read_json(p):
            by_unit[(unit['conv_id'], unit['chunk'])] = unit
    # Load the preserved results again, including results completed after the old validation.
    for bi, batch in enumerate(read_json(STATE / 'batches.json')):
        for u in batch:
            unit = by_unit.get((u['conv'], u['chunk']))
            if unit:
                for s in unit.get('segments', []):
                    s = dict(s, conv_id=u['conv'], batch=bi, chunk=u['chunk'], method='기존 내용 분류')
                    recovered.append(s)
    segments = collections.defaultdict(list)
    for s in recovered:
        segments[s['conv_id']].append(s)
    for c in convs:
        cid = c['conv_id']
        ms = web[(c['platform'], cid)]
        covered = set()
        for s in segments[cid]:
            covered.update(range(s['start'], s['end'] + 1))
        default = fallback_class(c, labels[cid][0], ms)
        # Never infer that two distinct requests are the same event.
        remaining = [n for n in range(1, len(ms) + 1) if n not in covered]
        chunks = []
        for n in remaining:
            r = ms[n - 1]
            if not chunks or n != chunks[-1][-1] + 1 or (r['role'] == 'user' and r['kind'] == 'visible'):
                chunks.append([])
            chunks[-1].append(n)
        for ns in chunks:
            segments[cid].append(dict(
                conv_id=cid, start=ns[0], end=ns[-1], **{'class': default}, project=project_for(c),
                label='요청·응답 원문 보존 구간', background='확인 불가(설명문을 추정하지 않고 아래 실제 발언을 보존)',
                outcome='발언 내용 외 실제 수행·종료 여부는 확인 불가', refs=[],
                method='사용자 역할 메시지 경계에서 기계 분할', note='사건의 의미상 경계는 미확정. 인접 구간과 자동으로 합치지 않음.'))
        if not ms:
            segments[cid] = []
        segments[cid].sort(key=lambda s: s['start'])
        expect = 1
        for i, s in enumerate(segments[cid], 1):
            if s['start'] != expect or not s['start'] <= s['end'] <= len(ms):
                raise ValueError(f'구간 공백/중복: {cid} {expect} {s["start"]}~{s["end"]}')
            expect = s['end'] + 1
            s['key'] = f'{cid}:{s["start"]}-{s["end"]}'
            s['sid'] = f'S{i:04d}'
            # Do not publish failed/abbreviated reference quotes as original evidence.
            good = []
            for ref in s.get('refs', []):
                n, q = ref.get('n'), ref.get('quote', '')
                if isinstance(n, int) and s['start'] <= n <= s['end'] and q and q in (ms[n - 1]['text'] or ''):
                    good.append(ref)
            s['verified_refs'] = good
        if expect != len(ms) + 1:
            raise ValueError(f'마지막 구간 누락: {cid}')
    return segments


def transcript(path, title, ms):
    path.parent.mkdir(parents=True, exist_ok=True)
    positions = {}
    with path.open('w', encoding='utf-8', newline='\n') as f:
        line = 1

        def put(t):
            nonlocal line
            f.write(t + '\n')
            line += t.count('\n') + 1

        put('# ' + (title or '(제목 없음)'))
        put('# 비공개 텍스트 전개본. 구조화 자료 및 도구 결과는 원본 JSON/JSONL 참조.')
        for n, r in enumerate(ms, 1):
            positions[str(n)] = line
            put(f'<<<MSG {n} | {r["platform"]} | {r["role"]} | {r["t"]} | {r["msg_id"]} | node {r["node_id"]} | {r["kind"]} | branch={r["on_branch"]}>>>')
            put(r['text'] or '')
            for kind, text in r.get('extras', []):
                put(f'<<<EXTRA {kind}>>>')
                put(text or '')
            if r.get('attachments'):
                put('<<<ATTACHMENT NAMES ' + json.dumps(r['attachments'], ensure_ascii=False) + '>>>')
    return dict(file=path.relative_to(BASE).as_posix(), lines=positions)


def render_message(r, n, event_id, mask, ledger, lines):
    mid = r['msg_id'] or r['node_id'] or f'record-{n}'
    role = {'user': '사용자 역할', 'assistant': PLAT[r['platform']], 'system': '시스템', 'tool': '도구'}.get(r['role'], r['role'])
    heading = f'#### [{n}] {role} · {r["t"] or "시각 없음"} · 메시지 `{mid}` · 노드 `{r["node_id"]}`'
    meta = [heading, '']
    if not r['on_branch']:
        meta += ['> 현재 선택 분기 밖 메시지. 편집·재생성 이력이며 삭제하지 않음.', '']
    if r.get('parent'):
        meta += [f'- 부모 노드: `{r["parent"]}`', '']
    if r['kind'] != 'visible' or r.get('hidden'):
        lines['archive_only_' + r['kind']] += 1
        return '\n'.join(meta + [f'원본 보관본 참조: `{r["kind"]}` 항목. 공개 원문에 전재하지 않음.', ''])
    original = r['text'] or ''
    # Corporate records pasted into an otherwise project-related exchange stay private.
    if CORP_TEXT.search(original) or (r['role'] == 'user' and PRIVATE_REQUEST.search(original)):
        lines['privacy_blocked_messages'] += 1
        return '\n'.join(meta + ['⟦회사·사생활 포함 가능 발언: 전문은 비공개 보관본 참조⟧', ''])
    text = mask(original)
    fence = '`' * max([3] + [len(m.group()) + 1 for m in re.finditer(r'`{3,}', text)])
    meta += [fence + 'text', text, fence, '']
    record = dict(event=event_id, platform=r['platform'], conv_id=r['conv_id'], msg_id=r['msg_id'],
                  node_id=r['node_id'], n=n, source_sha256=sha(original), rendered_sha256=sha(text))
    ledger.append(record)
    lines['rendered_messages'] += 1
    lines['rendered_characters_before_mask'] += len(original)
    if text != original:
        lines['masked_messages'] += 1
    for kind, value in r.get('extras', []):
        if kind == 'attachment':
            # Attachments may contain private/work content: keep the complete extraction locally.
            lines['archive_only_attachment_blocks'] += 1
        else:
            lines['archive_only_extra_' + kind] += 1
    if r.get('extras') or r.get('attachments'):
        meta += ['첨부·도구·추론 등의 부가 자료는 위 비공개 보관본의 같은 메시지에서 확인.', '']
    return '\n'.join(meta)


class Parts:
    def __init__(self):
        self.files = []
        self.current = None
        self.handle = None
        self.size = 0
        self.numbers = collections.Counter()
        self.groups = {}

    def add(self, kind, month, event_id, body):
        group = (kind, month)
        state = self.groups.get(group)
        new = state is None or state['size'] + len(body.encode('utf-8')) > 7_000_000
        if new:
            self.numbers[group] += 1
            fn = f'parts/{kind}_{month}_{self.numbers[group]:02d}.md'
            state = self.groups[group] = {'file': fn, 'size': 0}
            self.files.append(fn)
        if self.current != state['file'] or new:
            if self.handle:
                self.handle.close()
            path = BASE / state['file']
            path.parent.mkdir(exist_ok=True)
            self.handle = path.open('w' if new else 'a', encoding='utf-8', newline='\n')
            if new:
                self.handle.write(f'# {"웹 대화" if kind == "web" else "로컬 작업"} · {month} 시작 기록\n\n[통합 마스터](../BOOK_CONVERSATION_MASTER.md) · 모든 시각은 한국 표준시입니다.\n\n')
            self.current = state['file']
        self.handle.write(body + '\n\n')
        state['size'] += len((body + '\n\n').encode('utf-8'))
        return state['file'] + '#' + event_id.lower()

    def close(self):
        if self.handle:
            self.handle.close()


def build():
    convs, sessions, web, local = load_inputs()
    mask = masker()
    segs = finalize_segments(convs, web)
    for stale in (BASE / 'parts').glob('*.md'):
        stale.unlink()
    write_json(STATE / 'segments_final.json', [s for ss in segs.values() for s in ss])
    counts = collections.Counter()
    transcripts = {}
    for c in convs:
        key = (c['platform'], c['conv_id'])
        transcripts[key] = transcript(ARCH / 'per_conversation_fulltext' / f'{key[0]}_{key[1]}.txt', c['title'], web[key])
    for s in sessions:
        key = (s['platform'], s['conv_id'])
        if s['class'] != 'WORK' and key in local:
            transcripts[key] = transcript(ARCH / 'per_local_session_fulltext' / f'{key[0]}_{key[1]}.txt', s.get('title'), local[key])
    events = []
    for c in convs:
        key = (c['platform'], c['conv_id'])
        for s in segs[c['conv_id']]:
            counts['web_class_' + s['class']] += 1
            counts['web_class_messages_' + s['class']] += s['end'] - s['start'] + 1
            if s['class'] not in INCLUDED:
                continue
            ms = web[key][s['start'] - 1:s['end']]
            times = [r['t'] for r in ms if r['t']]
            events.append(dict(kind='web', key=key, segment=s,
                               start=min(times) if times else c['created'], end=max(times) if times else c['updated'],
                               lo=s['start'], hi=s['end'], title=mask(s['label']),
                               source_title=mask(c['title']), classification=s['class'], project=s.get('project') or 'OTHER'))
    for s in sessions:
        key = (s['platform'], s['conv_id'])
        if s['class'] not in ('LOCAL_PROJECT', 'AUTOMATION'):
            continue
        ms = local[key]
        times = [r['t'] for r in ms if r['t']]
        title = mask(s.get('title') or '로컬 작업 세션')
        events.append(dict(kind='local', key=key, session=s, lo=1, hi=len(ms),
                           start=min(times) if times else s.get('created'), end=max(times) if times else s.get('updated'),
                           title=title, source_title=title, classification='PROJECT', project='OTHER'))
    events.sort(key=lambda e: (e['start'] or '', e['key'], e['lo']))
    d_hits = {tuple(k): v for k, v in read_json(STATE / 'd_manuscript_hits.json')}
    ledger, event_meta = [], []
    parts = Parts()
    web_ev = collections.defaultdict(list)
    local_ev = {}
    message_events = {}
    for i, e in enumerate(events, 1):
        e['id'] = eid = f'E{i:05d}'
        platform, cid = e['key']
        ms = (web if e['kind'] == 'web' else local)[e['key']]
        ti = transcripts[e['key']]
        count = e['hi'] - e['lo'] + 1
        intro = [f'<a id="{eid.lower()}"></a>', f'## {eid} · {e["title"]}', '',
                 f'- 플랫폼: {PLAT[platform]} / 대화·세션 ID: `{cid}`',
                 f'- 시기: {e["start"] or "확인 불가"} ~ {e["end"] or "확인 불가"}. 마지막 기록 시각이며 사건 종료를 뜻하지 않음.',
                 f'- 분류: {CLASS_KO[e["classification"]]} / {PROJECT_KO.get(e["project"], "기타")}',
                 f'- 원문 범위: #{e["lo"]}~#{e["hi"]}, 메시지 {count}개. 추론·도구 등은 보관본을 참조.',
                 f'- 원문 텍스트 보관: [`{ti["file"]}`](../{ti["file"]}) {ti["lines"].get(str(e["lo"]), 1)}행부터.',
                 f'- 대화 제목(가림 적용): {e["source_title"]}', '']
        if e['kind'] == 'web':
            s = e['segment']
            intro += [f'- 정리 방식: {s["method"]}.',
                      f'- 정리자 메모(원문 아님) · 시작 배경: {mask(s.get("background") or "확인 불가")}',
                      f'- 정리자 메모(원문 아님) · 구간 안의 보고: {mask(s.get("outcome") or "확인 불가")}',
                      '- AI의 완료·검증 보고는 해당 발언의 내용이며, 실제 실행을 별도로 입증한 것으로 간주하지 않음.', '']
            if s.get('note'):
                intro += ['정리자 메모: ' + mask(s['note']), '']
            web_ev[cid].append(eid)
        else:
            s = e['session']
            intro += ['- 구간 연결: 이 세션을 독립 기록으로 유지. 다른 세션과의 사건 동일성은 추정하지 않음.',
                      '- 역할 표시는 로그에 기록된 역할. 사용자 역할에도 전달된 지시서·자동 입력이 포함될 수 있음.',
                      f'- 보존 상태: {"원본 유실; 정규화 텍스트만 보존" if s.get("vanished") else "원본 JSONL 사본 보존"}.',
                      '- 결과: 실제 실행 결과·사건 종료 여부를 추정하지 않음. 아래 도구의 보고와 원본 로그를 직접 확인.', '']
            local_ev[e['key']] = eid
        chapters = set()
        for n in range(e['lo'], e['hi'] + 1):
            r = ms[n - 1]
            message_events[(platform, cid, r['msg_id'])] = eid
            chapters.update(d_hits.get((platform, cid, r['msg_id']), []))
            intro.append(render_message(r, n, eid, mask, ledger, counts))
        # Existing manuscript comparison is a tag only; it never controls inclusion.
        body = '\n'.join(intro)
        target = parts.add(e['kind'], (e['start'] or 'unknown')[:7], eid, body)
        event_meta.append(dict(id=eid, platform=platform, conv_id=cid, start=e['start'], end=e['end'],
                               lo=e['lo'], hi=e['hi'], classification=e['classification'], project=e['project'],
                               title=e['title'], target=target, d_chapters=sorted(chapters),
                               method=e['segment']['method'] if e['kind'] == 'web' else '독립 로컬 세션'))
    parts.close()
    links = []
    uncertain_time = 0
    for x in read_json(STATE / 'crosslinks.json'):
        a, b = message_events.get(tuple(x['src'])), message_events.get(tuple(x['dst']))
        if not a or not b or a == b:
            continue
        order_ok = bool(x.get('src_t') and x.get('dst_t') and x['src_t'] <= x['dst_t'])
        uncertain_time += not order_ok
        links.append(dict(source_event=a, target_event=b, source_platform=x['src'][0],
                          source_conversation=x['src'][1], source_message=x['src'][2],
                          target_platform=x['dst'][0], target_conversation=x['dst'][1], target_message=x['dst'][2],
                          shared_lines=x['shared_lines'], time_order_consistent=order_ok,
                          status='동일 문장 기반 연결 후보; 동일 사건·실제 전달은 미확정'))
    write_json(BASE / 'EVENTS.json', event_meta)
    write_json(BASE / 'MESSAGE_LEDGER.json', ledger)
    write_json(BASE / 'CROSS_LINKS.json', links)
    counts.update(web_conversations=len(convs), local_sessions=len(sessions), events=len(event_meta),
                  web_events=sum(e['platform'] in ('chatgpt', 'claude_web') for e in event_meta),
                  local_events=len(local_ev), web_messages=sum(map(len, web.values())),
                  local_messages=sum(map(len, local.values())), connections=len(links),
                  connection_time_uncertain=uncertain_time,
                  machine_split_web_events=sum(e['method'].startswith('사용자') for e in event_meta))
    write_json(STATE / 'build_counts.json', dict(counts))
    write_json(STATE / 'transcript_index_final.json', [dict(platform=k[0], conv_id=k[1], **v) for k, v in transcripts.items()])
    rows = ['# MASTER INDEX · 전체 대화 및 로컬 세션', '',
            '[통합 마스터](BOOK_CONVERSATION_MASTER.md) · [검증 보고서](MASTER_AUDIT.md)', '',
            '모든 시각은 한국 표준시. 날짜는 메시지 자체의 최소·최대 시각이며, 메시지 시각이 전혀 없을 때만 대화 메타데이터를 사용합니다. 메시지 수는 현재 분기·이전 분기·추론 등을 포함한 원본 메시지 레코드 수입니다. 제목과 발언은 업무·사생활 제외 및 가림 정책을 적용합니다.', '',
            '| 플랫폼 | ID | 제목·처리 | 최초 메시지 | 최종 메시지 | 원본 메시지 수 | 구간·분류 | 파싱 | 원본 참조 |',
            '|---|---|---|---|---|---:|---|---|---|']
    for c in sorted(convs, key=lambda c: (c['created'] or '', c['conv_id'])):
        key = (c['platform'], c['conv_id'])
        ms = web[key]
        times = [r['t'] for r in ms if r['t']]
        classes = collections.Counter(s['class'] for s in segs[c['conv_id']])
        included = web_ev.get(c['conv_id'], [])
        title = mask(c['title']) if included else ('회사 업무 제외' if 'WORK' in classes else '사생활 제외' if 'PRIVATE' in classes else '빈 대화·본문 없음')
        source = original_web_path(c).relative_to(BASE).as_posix()
        first = min(times) if times else c['created']
        last = max(times) if times else c['updated']
        class_text = ', '.join(f'{CLASS_KO[k]} {v}' for k, v in classes.items()) or '메시지 없음'
        rows.append('| ' + ' | '.join(map(table, [PLAT[key[0]], key[1], title, first or '없음', last or '없음', len(ms), class_text, '성공', source + ' · conv_id=' + key[1]])) + ' |')
    rows += ['', '## 로컬 작업 기록', '',
             '진행 중이던 조사 세션 1개는 자기 참조를 피하려고 제외했습니다. 회사 업무 기록은 제목·경로를 공개하지 않습니다. `원본 유실` 표시는 메시지 텍스트 전개본만 남았다는 뜻입니다. 빈 세션도 목록에서 제거하지 않습니다.', '',
             '| 플랫폼 | 세션 ID | 제목·처리 | 최초 메시지 | 최종 메시지 | 원본 메시지 수 | 프로젝트 관련 | 파싱 | 보관 상태·참조 |',
             '|---|---|---|---|---|---:|---|---|---|']
    for s in sorted(sessions, key=lambda s: (s.get('created') or '', s['platform'], s['conv_id'])):
        key = (s['platform'], s['conv_id'])
        if s.get('excluded'):
            title, source = '진행 중인 조사 세션 제외', '의도적 제외'
        elif s['class'] == 'WORK':
            title, source = '회사 업무 제외', '원래 위치 보존; 경로 비공개'
        else:
            title = mask(s.get('title') or '제목 없음')
            source = transcripts.get(key, {}).get('file') or '보관본 없음'
            if s.get('vanished'):
                source = '원본 유실; 정규화 텍스트: ' + transcripts.get(key, {}).get('file', '없음')
            else:
                source += ' · 원본 JSONL 위치는 비공개 매니페스트에서 세션 ID로 참조'
        times = [r['t'] for r in local.get(key, []) if r['t']]
        rows.append('| ' + ' | '.join(map(table, [PLAT[key[0]], key[1], title,
                    min(times) if times else s.get('created') or '없음',
                    max(times) if times else s.get('updated') or '없음', s.get('messages_raw', 0),
                    s['class'], '제외' if s.get('excluded') else '성공' if not s.get('parse_errors') else '오류', source])) + ' |')
    (BASE / 'MASTER_INDEX.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    main = ['# BOOK CONVERSATION MASTER V1', '',
            '[전체 대화 인덱스](MASTER_INDEX.md) · [누락·무결성 검증](MASTER_AUDIT.md) · [원본 보관](SOURCE_ARCHIVE/README.md)', '',
            '이 자료는 원문 보존·조사용입니다. 목차, 에피소드 중요도, 성공·실패의 평가, 출판 원고를 새로 작성하지 않았습니다. 기존 원고는 수정하지 않았습니다.', '',
            '웹 대화 전체와 접근 가능한 로컬 기록을 목록화했습니다. 아래 사건은 시간순이며, 확실하지 않은 경계는 독립 보존 구간으로 유지했습니다. 원문 파일은 크기 때문에 약 7MB 단위로 나누었고 각 사건은 한 파일 안에 보존합니다.', '',
            '가림 없는 원문은 로컬 SOURCE_ARCHIVE에 보존합니다. 이 저장소에는 가림 처리된 발언을 싣고, 업무·사생활·내부 추론·자동 주입·도구 결과는 원본 위치를 참조합니다. `⟦…⟧`만 가림 표식입니다. 발언의 말투·맞춤법·오타를 고치지 않았으며, 설명문과 실제 발언을 분리했습니다. 이미지 포인터는 이미지 내용의 복구를 뜻하지 않습니다.', '',
            '플랫폼별 발언자를 분리했습니다. 특히 다른 AI의 보고서를 사용자가 붙여넣은 경우 실제 원본의 사용자 역할을 유지합니다. AI가 보고한 성공·테스트 통과와 실제 독립 검증을 구분해야 합니다.', '',
            f'보존 구간 {counts["events"]:,}개: 웹 {counts["web_events"]:,}개, 로컬 세션 {counts["local_events"]:,}개. 웹 원본 메시지 {counts["web_messages"]:,}개, 로컬 정규화 메시지 {counts["local_messages"]:,}개. 원본 유실·첨부 한계는 감사 보고서 참조.', '',
            '## 시간순 사건·보존 구간', '',
            '| ID | 시작 | 플랫폼 | 분류 | 중립 구간명·원문 | 기존 원고 인용 태그 |', '|---|---|---|---|---|---|']
    for e in event_meta:
        ch = ', '.join(e['d_chapters']) or '문자 대조에서 확인 안 됨'
        main.append('| ' + ' | '.join(map(table, [e['id'], e['start'] or '시각 없음', PLAT[e['platform']],
                    PROJECT_KO.get(e['project'], '기타'), f'[{e["title"]}]({e["target"]})', ch])) + ' |')
    main += ['', '## 세션 간 연결', '',
             f'[CROSS_LINKS.json](CROSS_LINKS.json)에 {len(links):,}개 후보를 기록했습니다. 서로 다른 세션에서 긴 문장 3개 이상이 겹치는 기계적 대조 결과입니다. 같은 사건·붙여넣기 방향·실제 수행을 확정하지 않습니다. 반복 템플릿도 일치할 수 있습니다. 시간 순서가 맞지 않거나 시각이 없는 후보 {uncertain_time:,}개는 별도 표기했습니다.', '',
             '후속 대화는 연결 후보의 source_event / target_event 및 원본 메시지 ID로 추적할 수 있습니다. 원문 언급 없이 주제가 비슷하다는 이유로 사건을 합치지 않았습니다.', '',
             '## 기계 판독용 자료', '',
             '- [EVENTS.json](EVENTS.json): 모든 사건·보존 구간의 범위와 원문 파일 위치.',
             '- [MESSAGE_LEDGER.json](MESSAGE_LEDGER.json): 실제 전재 메시지의 원문·가림 적용 후 텍스트 SHA-256.',
             '- [ARTIFACT_MANIFEST.json](ARTIFACT_MANIFEST.json): 저장소 결과물의 파일 크기·SHA-256.', '']
    (BASE / 'BOOK_CONVERSATION_MASTER.md').write_text('\n'.join(main), encoding='utf-8')
    print(json.dumps(dict(counts), ensure_ascii=False, indent=2))


def table(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', '').replace('<', '&lt;').replace('>', '&gt;')


def original_web_path(c):
    if c['platform'] == 'chatgpt':
        return ARCH / 'original_exports/chatgpt_20261022' / Path(c['src']).name
    return ARCH / 'original_exports/claude_web_20261019/extracted/conversations.json'


def artifact_files():
    return sorted(p for p in BASE.rglob('*') if p.is_file()
                  and 'SOURCE_ARCHIVE' not in p.relative_to(BASE).parts
                  and '__pycache__' not in p.parts and p.name != 'ARTIFACT_MANIFEST.json')


def manifest():
    # Repository-level files (README.md, CLAUDE.md, .git*, manuscript/) change independently of the archive.
    files = artifact_files() + [ARCH / 'README.md']
    write_json(BASE / 'ARTIFACT_MANIFEST.json', [dict(path=p.relative_to(REPO).as_posix(), bytes=p.stat().st_size,
                                                    sha256=file_sha(p)) for p in sorted(files)])


def check_files():
    entries = read_json(BASE / 'ARTIFACT_MANIFEST.json')
    problems = []
    for e in entries:
        p = REPO / e['path']
        if not p.is_file() or p.stat().st_size != e['bytes'] or file_sha(p) != e['sha256']:
            problems.append(e['path'])
    expected = {e['path'] for e in entries}
    for p in artifact_files():
        if p.relative_to(REPO).as_posix() not in expected:
            problems.append('미등록 ' + p.relative_to(REPO).as_posix())
    if problems:
        raise ValueError('결과 파일 검사 실패: ' + repr(problems))
    print(f'결과 파일 해시 검사 통과: {len(entries)}개')


def verify():
    convs, sessions, web, local = load_inputs()
    errors, limitations = [], []
    counts = read_json(STATE / 'build_counts.json')
    normalize = load_module('preserved_normalizer', STATE / 'normalize.py')
    expected = {}
    raw_stats = collections.Counter()
    raw_files = set()
    # Compare independently loaded raw JSON against every normalized message, including branches.
    for file in sorted((ARCH / 'original_exports/chatgpt_20261022').glob('conversations-*.json')):
        raw_files.add(file)
        for c in read_json(file):
            raw_stats['chatgpt_conversations'] += 1
            key = ('chatgpt', c['conversation_id'])
            expected[key] = {}
            for node, value in c['mapping'].items():
                m = value.get('message')
                if not m:
                    continue
                raw_stats['chatgpt_messages'] += 1
                expected[key][node] = dict(id=m['id'], role=m['author']['role'],
                                           text=normalize.gpt_content(m['content'])[1],
                                           t=time_iso(m.get('create_time')), parent=value.get('parent'))
    claude_file = ARCH / 'original_exports/claude_web_20261019/extracted/conversations.json'
    raw_files.add(claude_file)
    for c in read_json(claude_file):
        raw_stats['claude_web_conversations'] += 1
        key = ('claude_web', c['uuid'])
        expected[key] = {}
        for m in c['chat_messages']:
            raw_stats['claude_web_messages'] += 1
            visible = [x.get('text') or '' for x in m['content'] if x['type'] == 'text']
            expected[key][m['uuid']] = dict(id=m['uuid'], role='user' if m['sender'] == 'human' else 'assistant',
                                           text='\n'.join(visible) if visible else (m.get('text') or ''),
                                           t=time_iso(m['created_at']), parent=m['parent_message_uuid'])
    if set(expected) != set(web):
        # Empty conversations exist in metadata but do not produce a JSONL message.
        absent = set(expected) - set(web)
        extra = set(web) - set(expected)
        if any(expected[k] for k in absent) or extra:
            errors.append('웹 대화 집합 불일치')
    for c in convs:
        key = (c['platform'], c['conv_id'])
        actual = web[key]
        refs = expected[key]
        if len(actual) != len(refs) or c['messages_raw'] != len(refs):
            errors.append('웹 메시지 수 불일치: ' + c['conv_id'])
        seen = set()
        for r in actual:
            node = r['node_id']
            v = refs.get(node)
            if node in seen or not v or any([v['id'] != r['msg_id'], v['role'] != r['role'],
                                            v['text'] != r['text'], v['t'] != r['t'], v['parent'] != r['parent']]):
                errors.append('웹 메시지 본문·ID·부모·시각 불일치: ' + c['conv_id'])
            seen.add(node)
    del expected
    integrity = []
    original_root = ARCH / 'original_exports'
    for dest in sorted(p for p in original_root.rglob('*') if p.is_file()):
        rel = dest.relative_to(original_root)
        if rel.parts[0] == 'chatgpt_20261022':
            source = REPO / 'sources/raw/chatgpt_20261022/extracted' / Path(*rel.parts[1:])
        else:
            source = REPO / 'sources/raw' / rel
        h = file_sha(dest)
        same = source.is_file() and file_sha(source) == h
        if not same:
            errors.append('웹 원본 사본 불일치: ' + str(rel))
        integrity.append(dict(archive=dest.relative_to(BASE).as_posix(), source=str(source), sha256=h, identical=same))
    local_raw_messages = 0
    vanished = []
    for s in sessions:
        if s.get('excluded'):
            continue
        key = (s['platform'], s['conv_id'])
        if s.get('parse_errors'):
            errors.append('로컬 파싱 오류: ' + s['conv_id'])
        if len(local[key]) != s['messages_raw']:
            errors.append('로컬 메시지 수 불일치: ' + s['conv_id'])
        if s.get('vanished'):
            vanished.append(dict(platform=s['platform'], id=s['conv_id'], messages=s['messages_raw']))
            continue
        if not s.get('archive'):
            # Work records are intentionally not copied; validate original counts without publishing paths.
            path = Path(s['src'])
        else:
            path = BASE / s['archive']
            if not path.exists():
                errors.append('로컬 보관 사본 없음: ' + s['conv_id'])
                continue
            h = file_sha(path)
            source = Path(s['src'])
            identical = source.exists() and file_sha(source) == h
            # Active source logs may append after the recorded snapshot. Compare exact snapshot prefix.
            prefix_equal = False
            if source.exists() and not identical:
                with source.open('rb') as f:
                    prefix_equal = hashlib.sha256(f.read(path.stat().st_size)).hexdigest() == h
            if not identical and not prefix_equal:
                errors.append('로컬 원본 사본 불일치: ' + s['conv_id'])
            integrity.append(dict(archive=s['archive'], source=str(source), sha256=h,
                                  identical=identical, identical_snapshot_prefix=prefix_equal))
        if not path.exists():
            errors.append('로컬 원본 확인 불가: ' + s['conv_id'])
            continue
        records = {}
        record_n = 0
        with path.open(encoding='utf-8') as f:
            for line_no, line in enumerate(f, 1):
                r = json.loads(line)
                if s['platform'].startswith('claude_code'):
                    if r.get('type') not in ('user', 'assistant'):
                        continue
                    content = (r.get('message') or {}).get('content') or []
                    if isinstance(content, str):
                        text = content
                    else:
                        text = '\n'.join(x.get('text') or '' for x in content if x.get('type') == 'text')
                    role = r['type']
                    mid = r.get('uuid')
                else:
                    payload = r.get('payload') or {}
                    if r.get('type') != 'response_item' or payload.get('type') != 'message':
                        continue
                    text = '\n'.join(x.get('text', '') for x in payload.get('content') or [] if isinstance(x, dict))
                    role = payload.get('role')
                    role = 'system' if role == 'developer' else role
                    mid = payload.get('id') or f'L{line_no}'
                record_n += 1
                records[line_no] = (text, role, mid)
        # An original company log may have grown; the originally observed lines still must agree.
        for r in local[key]:
            if records.get(r['line']) != (r['text'], r['role'], r['msg_id']):
                errors.append('로컬 원문 텍스트·역할·ID 불일치: ' + s['conv_id'])
        if s.get('archive') and record_n != s['messages_raw']:
            errors.append('로컬 사본 레코드 수 불일치: ' + s['conv_id'])
        local_raw_messages += s['messages_raw']
    segs = finalize_segments(convs, web)
    if sum(s['end'] - s['start'] + 1 for ss in segs.values() for s in ss) != sum(map(len, web.values())):
        errors.append('웹 구간 전체 커버리지 불일치')
    mask = masker()
    ledger = read_json(BASE / 'MESSAGE_LEDGER.json')
    seen = set()
    for e in ledger:
        key = (e['platform'], e['conv_id'])
        r = (web if key[0] in ('chatgpt', 'claude_web') else local)[key][e['n'] - 1]
        identity = (key, e['n'])
        if identity in seen:
            errors.append('전재 메시지 중복: ' + e['conv_id'])
        seen.add(identity)
        if sha(r['text'] or '') != e['source_sha256'] or sha(mask(r['text'] or '')) != e['rendered_sha256']:
            errors.append('전재 원문·가림 대조 불일치: ' + e['conv_id'])
    # Read every emitted fenced block independently and check its exact text against the ledger.
    rendered = {}
    for part in sorted((BASE / 'parts').glob('*.md')):
        message, fence, body = None, None, []
        with part.open(encoding='utf-8', newline='') as f:
            for line in f:
                if fence is not None:
                    if line == fence + '\n':
                        text = ''.join(body)
                        if not text.endswith('\n') or message is None:
                            raise ValueError('잘못된 출력 원문 블록: ' + str(part))
                        rendered.setdefault(message, []).append(sha(text[:-1]))
                        fence, body = None, []
                    else:
                        body.append(line)
                    continue
                match = re.match(r'^#### \[(\d+)\].*?메시지 `([^`]+)`', line)
                if match:
                    message = (match.group(2), int(match.group(1)))
                match = re.fullmatch(r'(`{3,})text\n', line)
                if match:
                    fence = match.group(1)
            if fence is not None:
                errors.append('닫히지 않은 출력 원문 블록: ' + part.name)
    # Message IDs can recur in different sessions; match multiplicities rather than silently deduplicating.
    expected_rendered = collections.Counter((e['msg_id'] or e['node_id'] or f'record-{e["n"]}', e['n'], e['rendered_sha256']) for e in ledger)
    actual_rendered = collections.Counter((mid, n, h) for (mid, n), hs in rendered.items() for h in hs)
    if actual_rendered != expected_rendered:
        errors.append(f'출력 원문 블록 대조 불일치: 기대 {sum(expected_rendered.values())}, 실제 {sum(actual_rendered.values())}')
    write_json(ARCH / 'archive_integrity.json', integrity)
    reconciled = []
    before_path = STATE / 'norm/before_snapshot_reconcile_local_sessions.json'
    if before_path.exists():
        before = {(s['platform'], s['conv_id']): s for s in read_json(before_path)}
        for s in sessions:
            old = before.get((s['platform'], s['conv_id']), {})
            if old.get('messages_raw', 0) != s.get('messages_raw', 0):
                reconciled.append(dict(platform=s['platform'], id=s['conv_id'],
                                       messages_before=old.get('messages_raw', 0), messages_after=s.get('messages_raw', 0)))
    report = dict(scope='2026-10-22 기존 조사 스냅샷', counts=counts, raw_counts=dict(raw_stats),
                  local_raw_messages_verified=local_raw_messages,
                  reconciled_local_sessions=reconciled,
                  vanished_local_sessions=vanished, original_files_compared=len(integrity),
                  errors=sorted(set(errors)), lossless_original_archive_complete=False,
                  limitations=['로컬 세션 5개는 원본 사본 생성 전에 유실; 정규화 텍스트만 보존',
                               'ChatGPT 내보내기 ZIP의 첨부 구간 손상; 대화 JSON 전체와 첨부 실물 보존은 별개',
                               '기계 분할 보존 구간의 의미상 사건 경계 및 문장 대조 연결의 인과관계는 미확정',
                               '가림 처리는 출판 승인이나 간접 식별 위험의 전수 검토를 뜻하지 않음'])
    write_json(BASE / 'AUDIT_DATA.json', report)
    audit_markdown(report, sessions)
    manifest()
    check_files()
    if errors:
        raise SystemExit(json.dumps(report['errors'], ensure_ascii=False, indent=2))
    print(json.dumps(dict(raw_stats, local_raw_messages_verified=local_raw_messages,
                          original_files_compared=len(integrity), vanished_sessions=len(vanished), errors=0), ensure_ascii=False, indent=2))


def audit_markdown(r, sessions):
    c = r['counts']
    text = ['# MASTER AUDIT · 2026-10-22', '',
            '[전체 인덱스](MASTER_INDEX.md) · [통합 마스터](BOOK_CONVERSATION_MASTER.md) · [검증 데이터](AUDIT_DATA.json)', '',
            '**자료 생성과 누락 대조를 실시했습니다. 완전한 원본 보존은 확인하지 못했습니다.** 원본이 이미 유실된 로컬 세션 5개와 내보내기 첨부 손상이 남아 있습니다. 이를 복구되거나 무손실 보존된 것으로 보고하지 않습니다.', '',
            '## 조사 수와 메시지 수', '',
            '| 원본 | 대화·세션 수 | 원본 메시지 레코드 수 |', '|---|---:|---:|',
            f'| ChatGPT | {r["raw_counts"]["chatgpt_conversations"]:,} | {r["raw_counts"]["chatgpt_messages"]:,} |',
            f'| Claude 웹 | {r["raw_counts"]["claude_web_conversations"]:,} | {r["raw_counts"]["claude_web_messages"]:,} |',
            f'| 로컬 코딩 도구 | {c["local_sessions"]:,} (현재 조사 1개 제외) | {c["local_messages"]:,} |', '',
            '웹 원본은 ChatGPT 8개 JSON과 Claude 웹 JSON을 독립적으로 다시 읽고 현재·이전 분기를 모두 대조했습니다. 메시지 식별자, 노드 식별자, 역할, 부모, 시각, 텍스트가 정규화 기록과 일치하는지 검사했습니다. 멀티모달의 비문자 파트는 텍스트 전개본의 포인터가 아니라 원본 JSON 구조가 정본입니다.', '',
            '로컬 메시지 수는 Claude Code의 user/assistant 레코드와 Codex의 response_item/message 레코드 기준입니다. 도구 호출·도구 결과·기타 이벤트까지 포함한 JSONL 전체 줄 수와 다릅니다. 원본 JSONL을 통째로 보관하며 전개본이 모든 도구 입출력을 대신한다고 주장하지 않습니다.', '',
            '## 분류·전재', '',
            f'- 시간순 사건·보존 구간: {c["events"]:,}개(웹 {c["web_events"]:,}, 로컬 {c["local_events"]:,}).',
            f'- 실제 발언 전재: {c["rendered_messages"]:,}개. 가림 적용 메시지 {c["masked_messages"]:,}개.',
            f'- 내용 분류 결과가 없던 구간은 사용자 역할 요청 경계로 분리: {c["machine_split_web_events"]:,}개. 의미상 사건 경계는 미확정.',
            f'- 기업·사생활 포함 가능 발언 별도 보관: {c.get("privacy_blocked_messages", 0):,}개.',
            f'- 연결 후보: {c["connections"]:,}개. 시각 방향 미확정 {c["connection_time_uncertain"]:,}개.', '',
            '| 웹 분류 | 구간 수 | 메시지 수 |', '|---|---:|---:|']
    for name, label in CLASS_KO.items():
        text.append(f'| {label} | {c.get("web_class_" + name, 0):,} | {c.get("web_class_messages_" + name, 0):,} |')
    local_counts = collections.Counter(s['class'] for s in sessions)
    text += ['', f'로컬 분류: 프로젝트 {local_counts["LOCAL_PROJECT"]:,}개, 자동화 {local_counts["AUTOMATION"]:,}개, 회사 업무 제외 {local_counts["WORK"]:,}개, 현재 조사 제외 {local_counts["EXCLUDED_SELF"]:,}개.', '',
             f'추출 후 사본 생성 전 메시지가 추가된 로컬 세션 {len(r["reconciled_local_sessions"])}개를 발견해 사본의 전체 메시지를 다시 추출했습니다. 최초 정규화 입력은 별도 백업으로 남겼고, 추가 메시지도 본문·역할·ID 대조에 포함했습니다.', '',
             '회사·사생활은 제목이나 내용의 요약을 공개 자료에 복사하지 않았습니다. 모든 웹 대화는 제외 이유와 건수를 인덱스에 남기고 원본 JSON을 로컬에 보관합니다. 초기 분류의 날짜 기준 제외(PRE)는 폐기하고, 과거 대화도 제목·내용에 따라 업무/사생활/투자/개발 배경으로 목록화했습니다. 일반 개발 배경과 실제 프로젝트 연결이 확인되지 않는 기록은 별도 경계 자료로 유지했습니다.', '',
             '기존 D원고의 문자 대조 태그는 이력 확인용이며 포함·배제 기준이 아닙니다. 인용 태그가 없는 구간도 같은 방식으로 보존합니다. 기존 원고의 모든 문장이 원문 인용이라는 뜻은 아니며, 대조에서 안 잡힌 것을 사건이 없었다는 근거로 삼지 않습니다.', '',
             '## 보존 예외', '',
             '| 플랫폼 | 세션 ID | 정규화 메시지 수 | 상태 |', '|---|---|---:|---|']
    for s in r['vanished_local_sessions']:
        text.append(f'| {PLAT[s["platform"]]} | `{s["id"]}` | {s["messages"]:,} | 원본 JSONL 유실, 정규화 텍스트만 보존 |')
    text += ['', '유실 원인은 확인 불가입니다. 이전 작업 기록은 자동 삭제 가능성을 제시했지만 이 보고서는 이를 확정하지 않습니다. 정규화 텍스트가 남아 있어도 도구 호출·도구 결과 등의 원본 전체를 복구할 수 없으므로, 위 세션의 완전 보존은 미확인입니다.', '',
             'ChatGPT 내보내기 ZIP은 이전 조사에서 첨부 구간 손상이 보고됐습니다. 현재 보관된 대화 JSON 전체의 메시지는 읽고 대조했으나 이미지·첨부 파일 전체의 존재와 ZIP의 완전성은 입증하지 못했습니다. 이미지 포인터·첨부 이름·추출 텍스트는 이미지·첨부 실물과 구분했습니다.', '',
             '분류·원문 검증은 보존된 10월 22일 스냅샷을 기준으로 합니다. 이후 생성된 대화나 이 마무리 세션을 자동으로 조사 범위에 추가하지 않았습니다.', '',
             '## 검증 결과', '',
             f'- 웹 메시지 수 대조: {c["web_messages"]:,}개. 구간 공백·겹침 없이 포함 또는 명시적 제외로 처리.',
             f'- 실제 로컬 원문과 대조한 메시지: {r["local_raw_messages_verified"]:,}개. 유실 5개는 별도 예외.',
             f'- 원본 사본·원래 파일의 해시 대조: {r["original_files_compared"]:,}개. 기록 후 추가된 세션은 스냅샷 길이까지 바이트 비교.',
             '- 전재 원문은 원본 텍스트 및 가림 후 텍스트의 SHA-256과 출력 코드 블록 본문을 대조. 문장 재작성·오타 교정 없음.',
             '- 식별자와 메시지 순서는 원문 추적용으로 유지. 메시지 내부의 자격정보·직접 식별정보는 가림 표식 적용.',
             '- 텍스트 전개본의 메시지 행 번호는 실제 개행 수로 계산.',
             f'- 검사 오류: {len(r["errors"])}건.', '']
    if r['errors']:
        text += ['오류가 남아 있으므로 검증 통과로 보고할 수 없습니다.', ''] + ['- ' + e for e in r['errors']]
    else:
        text += ['접근·보존된 메시지와 생성 파일의 기술 검사는 통과했습니다. 위 원본 유실·첨부·의미상 경계 한계가 해소됐다는 뜻은 아닙니다.', '']
    text += ['## 저장소와 출판 범위', '',
             'Git에는 가림 처리 마스터·인덱스·검증 결과·재생성 도구만 포함합니다. 가림 없는 원본, 업무·사생활, 운영 증거, 기존 원고와 임시 복구 입력은 디스크에 유지하고 Git에서 제외합니다. 출판 원고 작성·수정·배포는 하지 않았습니다. 새 출판물로 사용하기 전에는 간접 식별 가능성 및 맥락을 별도 검토해야 합니다.', '']
    (BASE / 'MASTER_AUDIT.md').write_text('\n'.join(text), encoding='utf-8')


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    if action == 'build':
        build()
    elif action == 'verify':
        verify()
    elif action == 'check-files':
        check_files()
    else:
        raise SystemExit('usage: archive.py build|verify|check-files')
