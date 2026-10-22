"""Build research/episode_census_v1 from per-chunk census outputs.

Inputs (all relative to this directory): parsed.json, chunks/meta.json, out/*.json, merges.json (optional).
Outputs go to the repository's research/episode_census_v1/.
"""
import collections
import json
import os
import re
import sys

HERE = os.environ.get('CENSUS_WORK') or os.path.dirname(os.path.abspath(__file__))
REPO = '/home/user/book'
MASTER = f'{REPO}/conversation_master_v1'
OUT = f'{REPO}/research/episode_census_v1'

PROJECT_KO = {'SITE_CALC': '계산기 사이트', 'SITE_WELFARE': '복지 정보 사이트', 'SITE_TAROT': '타로 상담 사이트',
              'SITE_FORM': '문서 양식 사이트', 'BLOG_NAVER': '네이버 블로그', 'BLOG_PERSONAL': '개인 블로그',
              'TRADE_COIN_EARLY': '코인 자동매매 초기 기록', 'TRADE_US': '미국주식 연구·자동매매',
              'TRADE_CRYPTO': '암호화폐 매매 연구', 'GAME': '게임', 'APP': '앱', 'STRATEGY': '아이디어·기획·수익화',
              'AI_TOOLS': 'AI 도구·개발환경', 'BOOK': '책·출판', 'OTHER': '기타·연결 미확인'}
SPEAKER = {'U': '사용자', 'GPT': 'ChatGPT', 'CW': 'Claude(웹)', 'CC': 'Claude Code', 'CX': 'Codex', 'S': '시스템'}
WHO = {'사용자 역할': 'U', '시스템': 'S', 'ChatGPT': 'GPT', 'Claude 웹': 'CW', 'Claude Code (WSL)': 'CC',
       'Claude Code (Windows)': 'CC', 'Codex (WSL)': 'CX'}
EXCLUDED = ('회사 업무 가능성', '사생활 가능성')
STATUS_KO = {'EP': '에피소드 연결', 'PRESERVE': '단순 원문 보존', 'NOT_EP': '사건 아님·출판 제외',
             'UNVERIFIABLE': '원본 부족·확인 불가'}
# Strings that must never appear in new Git files (author name, account, contact patterns).
_PT = json.load(open(f'{HERE}/privacy/private_terms.json', encoding='utf-8')) if os.path.exists(f'{HERE}/privacy/private_terms.json') else {'block': [], 'scrub': []}
PRIVATE = re.compile('|'.join(_PT['block'] + [r'ntn_', r'[A-Za-z0-9._%+\-]+@⟦']) + r'|secret_[A-Za-z0-9]|[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}'
                     r'|(?<![0-9a-f\-])01[016789]-\d{3,4}-\d{4}(?![0-9a-f\-])|192\.168\.\d+\.\d+')
norm = lambda s: re.sub(r'\s+', ' ', s).strip()
# Unmasked identifiers found in the master text; replaced in researcher prose, quotes containing them are dropped.
SCRUB = [(re.compile(p), rep) for p, rep in _PT['scrub']]


PRIV_REP = {'자사명': '⟦자사 이름⟧', '인명': '⟦인명⟧', '회사': '⟦회사⟧', '계정·연락처': '⟦계정⟧', '비밀정보': '⟦비밀정보⟧'}


def load_privacy_terms():
    # Terms flagged by the privacy review (privacy/F*.json, kept out of Git); longest first.
    terms = {}
    import glob
    for p in glob.glob(f'{HERE}/privacy/F*.json'):
        for f in json.load(open(p, encoding='utf-8')).get('flags', []):
            t = (f.get('term') or '').strip()
            if len(t) >= 2 and '⟦' not in t:
                terms[t] = PRIV_REP.get(f.get('type'), '⟦가림⟧')
    for t in json.load(open(f'{HERE}/privacy/allow.json', encoding='utf-8')) if os.path.exists(f'{HERE}/privacy/allow.json') else []:
        terms.pop(t, None)
    out = []
    for t, rep in sorted(terms.items(), key=lambda kv: -len(kv[0])):
        if re.fullmatch(r'[A-Za-z0-9 ._\-]+', t):
            rx = re.compile(r'(?<![A-Za-z0-9])' + re.escape(t) + r'(?![A-Za-z0-9])')
        elif len(t) <= 2:
            rx = re.compile(r'(?<![가-힣])' + re.escape(t))  # e.g. a 2-letter name must not hit a longer word
        else:
            rx = re.compile(re.escape(t))
        out.append((rx, rep))
    return out


TERMS = load_privacy_terms()


def scrub(text):
    for rx, rep in SCRUB:
        text = rx.sub(rep, text)
    for rx, rep in TERMS:
        text = rx.sub(rep, text)
    return text


def quote_blocked(q):
    return bool(PRIVATE.search(q)) or any(rx.search(q) for rx, _ in TERMS)


def load():
    events = {e['id']: e for e in json.load(open(f'{MASTER}/EVENTS.json', encoding='utf-8'))}
    parsed = json.load(open(f'{HERE}/parsed.json', encoding='utf-8'))
    meta = json.load(open(f'{HERE}/chunks/meta.json', encoding='utf-8'))
    outs = {}
    for name in sorted(meta):
        p = f'{HERE}/out/{name}.json'
        if os.path.exists(p):
            outs[name] = json.load(open(p, encoding='utf-8'))
    import glob
    merges = {'_uncertain': []}
    for p in sorted(glob.glob(f'{HERE}/merges*.json')):
        mdata = json.load(open(p, encoding='utf-8'))
        merges.update(mdata.get('merges', {}))
        merges['_uncertain'] += mdata.get('uncertain', [])
    return events, parsed, meta, outs, merges


def build():
    events, parsed, meta, outs, merges = load()
    problems = []
    # 1. Collect chunk episodes and resolve cross-chunk merges into canonical keys.
    raw = {}
    dropped = []
    for name, o in outs.items():
        for v in o['segments'].values():
            v['label'] = scrub(v.get('label', ''))
        for ep in o['episodes']:
            kept = []
            for q in ep['key_messages']:
                if quote_blocked(q['q']):
                    dropped.append(f"{ep['key']} {q['e']}#{q['n']}")
                else:
                    kept.append(q)
            ep['key_messages'] = kept
            for f, v in list(ep.items()):
                if isinstance(v, str):
                    ep[f] = scrub(v)
            ep['links'] = [{k: scrub(x) if isinstance(x, str) else x for k, x in l.items()} for l in ep.get('links', [])]
            raw[ep['key']] = ep
    uncertain = merges.pop('_uncertain', [])
    def canon(k):
        seen = set()
        while k in merges and k not in seen:
            seen.add(k)
            k = merges[k]
        return k
    groups = collections.defaultdict(list)
    for k in raw:
        groups[canon(k)].append(k)
    episodes = []
    for root, keys in groups.items():
        parts = sorted((raw[k] for k in keys), key=lambda x: (x['start'], x['key']))
        base = dict(parts[0])
        base['source_keys'] = [p['key'] for p in parts]
        if len(parts) > 1:
            base['start'] = min(p['start'] for p in parts)
            base['end'] = max(p['end'] for p in parts)
            base['state'] = parts[-1]['state']
            base['result'] = parts[-1]['result']
            for f in ('background', 'process', 'ai_actions', 'user_reactions', 'unknowns', 'anon'):
                base[f] = ' / '.join(dict.fromkeys(p[f] for p in parts if p.get(f)))
            base['events'] = sorted({e for p in parts for e in p['events']})
            base['key_messages'] = [q for p in parts for q in p['key_messages']]
            base['links'] = [l for p in parts for l in p.get('links', [])]
            base['types'] = list(dict.fromkeys(t for p in parts for t in p.get('types', [])))
        episodes.append(base)
    for ep in episodes:
        if ep.get('publish_flag') in EXCLUDED:
            # Company/private material stays in the master only; keep IDs and sources, drop narrative and quotes.
            for f in ('background', 'goal', 'process', 'ai_actions', 'user_reactions', 'result', 'unknowns', 'anon'):
                ep[f] = '출판 제외 표시로 상세 생략(원본 구간 참조)'
            ep['title'] = f"⟦{ep['publish_flag']} — 출판 제외, 상세 생략⟧"
            ep['key_messages'] = []
            ep['links'] = []
    first_event = lambda ep: min(int(e[1:]) for e in ep['events']) if ep['events'] else 10 ** 9
    episodes.sort(key=lambda ep: (ep['start'], first_event(ep)))
    ids = {}
    complete = len(outs) == len(meta)
    for i, ep in enumerate(episodes, 1):
        ep['id'] = f'EP-{i:04d}' if complete else f'EP-W{i:04d}'
        for k in ep['source_keys']:
            ids[k] = ep['id']
    # 2. Segment table for all 4,953 master segments.
    seg = {}
    for name, o in outs.items():
        for e, v in o['segments'].items():
            seg[e] = dict(v, chunk=name, ep=[ids[k] for k in v.get('ep', []) if k in ids])
    web = [e for e in events.values() if e['platform'] in ('chatgpt', 'claude_web')]
    processed_chunks = set(outs)
    scope = events.values() if complete else web
    for e in scope:
        if e['id'] not in seg:
            problems.append(f'구간 미처리 {e["id"]}')
    # Confirmed links between episodes (e.g. a ChatGPT instruction executed in a local coding session).
    web_ids = set(events)  # any master segment may be cited as evidence
    edges = set()
    for ep in episodes:
        for l in ep.get('links', []):
            w = l.get('web_episode') or l.get('episode')
            if l.get('status') == '확정' and w:
                # A confirmed cross-session link must cite a source message (segment + message number) as evidence.
                cited = [x for x in re.findall(r'(E\d{5})\s*#\s*\d+', l.get('basis', '')) if x in web_ids]
                if not cited:
                    l['status'] = '미확정(근거 불충분)'
            if l.get('status') == '확정' and w and w in ids and ids[w] != ep['id']:
                edges.add(tuple(sorted((ep['id'], ids[w]))))
                l['target_id'] = ids[w]
    parent = {ep['id']: ep['id'] for ep in episodes}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, c in edges:
        parent[find(a)] = find(c)
    groups_of = collections.defaultdict(list)
    for ep in episodes:
        groups_of[find(ep['id'])].append(ep['id'])
    for ep in episodes:
        members = groups_of[find(ep['id'])]
        ep['group'] = members[0] if len(members) > 1 else ''
        ep['related'] = sorted({c if a == ep['id'] else a for a, c in edges if ep['id'] in (a, c)})
    # 3. Verify quotes against the full master text and map message numbers to IDs.
    for ep in episodes:
        for q in ep['key_messages']:
            ms = [m for m in parsed[q['e']]['msgs'] if m['n'] == q['n']]
            if not ms:
                problems.append(f'{ep["id"]} 메시지 없음 {q["e"]}#{q["n"]}')
                continue
            m = ms[0]
            q['msg_id'] = m['id']
            q['time'] = m['t']
            if WHO.get(m['who'], m['who']) != q['sp']:
                problems.append(f'{ep["id"]} 발언자 불일치 {q["e"]}#{q["n"]}')
            if norm(q['q']) not in norm(m['text']):
                problems.append(f'{ep["id"]} 인용 불일치 {q["e"]}#{q["n"]}')
        ep['n_quotes'] = len(ep['key_messages'])
        ep['msg_ids'] = sorted({q.get('msg_id') for q in ep['key_messages'] if q.get('msg_id')})
    # 4. Existing CROSS_LINKS re-review (web-web pairs only in this phase).
    seg_ep = {e: set(v['ep']) for e, v in seg.items()}
    cl = json.load(open(f'{MASTER}/CROSS_LINKS.json', encoding='utf-8'))
    cl_result = collections.Counter()
    cl_rows = []
    for c in cl:
        a, b = c['source_event'], c['target_event']
        if a not in seg or b not in seg:
            cl_result['로컬 구간 포함: 로컬 단계에서 재검토'] += 1
            continue
        ea, eb = seg_ep[a], seg_ep[b]
        if ea & eb:
            r = '같은 에피소드 안에서 연결됨'
        elif any(tuple(sorted((x, y))) in edges for x in ea for y in eb):
            r = '확정 연결된 에피소드 사이(원문 확인)'
        elif ea and eb:
            r = '서로 다른 에피소드: 미확정 연결 유지'
            cl_rows.append((a, b, sorted(ea), sorted(eb), c['shared_lines'], c['time_order_consistent']))
        else:
            r = '한쪽 이상이 에피소드 아님: 미확정 유지'
        cl_result[r] += 1
    return dict(events=events, parsed=parsed, meta=meta, outs=outs, episodes=episodes, seg=seg, web=web,
                problems=problems, dropped=dropped, uncertain=uncertain, cl_result=cl_result, cl_rows=cl_rows, processed_chunks=processed_chunks,
                merges=merges, ids=ids, complete=complete, edges=edges, groups_of=groups_of)


PLAT_KO = {'chatgpt': 'ChatGPT', 'claude_web': 'Claude 웹', 'claude_code_wsl': 'Claude Code', 'claude_code_win': 'Claude Code', 'codex_wsl': 'Codex'}


def platforms(ep, events):
    return '·'.join(dict.fromkeys(PLAT_KO.get(events[e]['platform'], events[e]['platform']) for e in ep['events'])) or '-'


def md_escape(s):
    return (s or '').replace('|', '\\|').replace('\n', ' ')


def write(b):
    os.makedirs(f'{OUT}/EPISODE_DETAILS', exist_ok=True)
    episodes, seg, events = b['episodes'], b['seg'], b['events']
    by_proj = collections.defaultdict(list)
    for ep in episodes:
        by_proj[ep['project'] if ep['project'] in PROJECT_KO else 'OTHER'].append(ep)
    detail_file = {}
    for proj, eps in by_proj.items():
        fn = f'EPISODE_DETAILS/{proj}.md'
        for ep in eps:
            detail_file[ep['id']] = fn
    files = {}
    # EPISODE_INDEX.md
    L = ['# EPISODE INDEX', '',
         '마스터 4,953개 구간(웹 4,150 · 로컬 803)에서 찾은 에피소드 전체 목록입니다. 순위나 선정이 아니라 발생 순서입니다. '
         '"연결"은 원문으로 확인된(확정) 다른 에피소드와의 연결로, 예를 들어 ChatGPT 대화에서 나온 지시가 Claude Code·Codex 세션에서 실행된 경우입니다.', '',
         '| ID | 제목 | 시기 | 프로젝트 | 플랫폼 | 상태 | 구간 수 | 원본 구간 | 확정 연결 | 표시 | 상세 |', '|---|---|---|---|---|---|---:|---|---|---|---|']
    for ep in episodes:
        ev = ep['events']
        span = f'{ev[0]}~{ev[-1]}' if len(ev) > 1 else (ev[0] if ev else '-')
        L.append(f"| {ep['id']} | {md_escape(ep['title'])} | {ep['start']}~{ep['end']} | {PROJECT_KO.get(ep['project'], ep['project'])} | "
                 f"{platforms(ep, events)} | {md_escape(ep['state'])} | {len(ev)} | {span} | {', '.join(ep.get('related', [])) or '-'} | "
                 f"{md_escape(ep.get('publish_flag', ''))} | [보기]({detail_file[ep['id']]}#{ep['id'].lower()}) |")
    files['EPISODE_INDEX.md'] = '\n'.join(L) + '\n'
    # EPISODE_DETAILS
    for proj, eps in by_proj.items():
        L = [f'# {PROJECT_KO.get(proj, proj)} 에피소드 상세', '',
             '[목록](../EPISODE_INDEX.md) · 인용은 마스터 원문과 글자 단위로 대조한 실제 발언입니다. 그 밖의 문장은 조사자 정리이며 원문이 아닙니다. '
             '`⟦…⟧`는 마스터의 가림 표식입니다.', '']
        for ep in eps:
            L += [f"## {ep['id']}", '', f"**{ep['title']}**", '',
                  f"- 시기: {ep['start']} ~ {ep['end']}",
                  f"- 프로젝트: {PROJECT_KO.get(ep['project'], ep['project'])} (`{ep['project']}`)",
                  f"- 유형: {', '.join(ep.get('types', [])) or '-'}",
                  f"- 상태: {ep['state']}",
                  f"- 출판 표시: {ep.get('publish_flag', '-')}",
                  f"- 플랫폼: {platforms(ep, events)}",
                  f"- 확정 연결 에피소드: {', '.join(ep.get('related', [])) or '-'}",
                  f"- 원본 구간: {', '.join(f'[{e}](../../../conversation_master_v1/{events[e]["target"]})' for e in ep['events'])}",
                  '',
                  f"**시작 배경** {ep['background']}", '',
                  f"**사용자의 목표** {ep['goal']}", '',
                  f"**진행** {ep['process']}", '',
                  f"**AI의 제안·행동** {ep['ai_actions']}", '',
                  f"**사용자 반응** {ep['user_reactions']}", '',
                  f"**확인 가능한 결과** {ep['result']}", '']
            if ep['key_messages']:
                L += ['**중요 대화(원문)**', '']
                for q in sorted(ep['key_messages'], key=lambda q: (int(q['e'][1:]), q['n'])):
                    L.append(f"- [{q.get('role', '')}] {SPEAKER.get(q['sp'], q['sp'])} · {q['e']} #{q['n']} · `{q.get('msg_id', '?')}`")
                    L.append('')
                    L.append('  > ' + q['q'].replace('\n', '\n  > '))
                    L.append('')
            links = ep.get('links', [])
            if links:
                L += ['**다른 대화·에피소드와의 연결**', '']
                for l in links:
                    L.append(f"- ({l.get('status', '미확정')}) {l.get('hint', '')} — 근거: {l.get('basis', '')}")
                L.append('')
            if len(ep['source_keys']) > 1:
                L += [f"- 묶음 경계 통합: {', '.join(ep['source_keys'])}", '']
            L += [f"**확인되지 않은 정보** {ep.get('unknowns') or '-'}", '',
                  f"**출판 시 익명화 필요** {ep.get('anon') or '-'}", '']
        files[f'EPISODE_DETAILS/{proj}.md'] = '\n'.join(L) + '\n'
    # CHRONOLOGY.md
    L = ['# CHRONOLOGY', '', '에피소드를 시작 시기순으로 나열합니다. 프로젝트별로 처음 등장한 에피소드는 **[첫 등장]**, '
         '완료가 아닌 에피소드는 상태(중단·방향 전환·진행 중·미확인)를 함께 표시합니다. → 표시는 원문으로 확인된 연결 에피소드입니다. '
         '출판 제외 표시 에피소드도 위치를 남겼습니다.', '']
    seen = set()
    month = None
    for ep in episodes:
        m = ep['start'][:7]
        if m != month:
            L += ['', f'## {m}', '']
            month = m
        tag = ''
        if ep['project'] not in seen:
            tag = '**[첫 등장]** '
            seen.add(ep['project'])
        st = '' if ep['state'] == '완료' else f" — {ep['state']}"
        rel = f" → {', '.join(ep['related'])}" if ep.get('related') else ''
        L.append(f"- {ep['start']} · {PROJECT_KO.get(ep['project'], ep['project'])} · {platforms(ep, events)} · {tag}[{ep['id']}]({detail_file[ep['id']]}#{ep['id'].lower()}) {ep['title']}{st}{rel}")
    L += ['', '## 프로젝트별 흐름', '']
    for proj, eps in sorted(by_proj.items(), key=lambda kv: kv[1][0]['start']):
        L.append(f"### {PROJECT_KO.get(proj, proj)} — 에피소드 {len(eps)}개, {eps[0]['start']} ~ {max(e['end'] for e in eps)}")
        L.append('')
        for ep in eps:
            L.append(f"- {ep['start']} [{ep['id']}] {ep['title']} ({ep['state']})")
        L.append('')
    files['CHRONOLOGY.md'] = '\n'.join(L) + '\n'
    files['COVERAGE_AUDIT.md'] = coverage(b, detail_file)
    files['REVIEW_HANDOFF.md'] = handoff(b, by_proj)
    files['CHECKPOINT.md'] = checkpoint(b)
    files['_data/episodes.json'] = json.dumps(
        [{k: ep[k] for k in ('id', 'source_keys', 'title', 'project', 'start', 'end', 'background', 'goal', 'process',
                             'ai_actions', 'user_reactions', 'result', 'state', 'types', 'events', 'key_messages',
                             'links', 'related', 'group', 'unknowns', 'anon', 'publish_flag')} for ep in episodes],
        ensure_ascii=False, indent=1) + '\n'
    files['_data/segments.json'] = json.dumps(
        {e: {'status': v['s'], 'episodes': v['ep'], 'label': v.get('label', ''), 'chunk': v['chunk']}
         for e, v in sorted(seg.items())}, ensure_ascii=False, indent=1) + '\n'
    leaks = []
    for name, text in files.items():
        for m in PRIVATE.finditer(text):
            leaks.append(f'{name}: {m.group(0)}')
        for rx, _ in TERMS:
            for m in rx.finditer(text):
                leaks.append(f'{name}: 검토 용어 {m.group(0)}')
    return files, leaks


def handoff(b, by_proj):
    episodes = b['episodes']
    flags = collections.Counter(ep.get('publish_flag', '') for ep in episodes)
    states = collections.Counter(ep['state'] for ep in episodes)
    types = collections.Counter(t for ep in episodes for t in ep.get('types', []))
    groups = [m for m in b['groups_of'].values() if len(m) > 1]
    pub = [ep for ep in episodes if ep.get('publish_flag') not in EXCLUDED]
    mixed = sum(1 for ep in episodes if ep.get('related'))
    L = ['# REVIEW HANDOFF', '',
         'ChatGPT와 사용자가 에피소드를 검토하기 위한 안내입니다. Claude는 조사만 했고, 책에 넣을 사건을 고르거나 순위를 매기지 않았습니다.', '',
         '## 범위와 수', '',
         f'- 처리: 마스터 4,953개 구간 전부(웹 4,150 · 로컬 803). 구간별 처리 결과는 `COVERAGE_AUDIT.md`.',
         f'- 에피소드 기록: {len(episodes)}개 (출판 제외 표시 {len(episodes) - len(pub)}개 포함).',
         f'- 원문으로 확인된 연결: {len(b["edges"])}쌍, {mixed}개 에피소드. 연결로 묶이는 그룹 {len(groups)}개(그룹 안 에피소드 {sum(len(g) for g in groups)}개).',
         f'- 확정 연결로 묶인 에피소드를 하나의 사건으로 보면 독립 사건은 {len(episodes) - sum(len(g) for g in groups) + len(groups)}개입니다. 연결은 같은 사건의 다른 단계(예: ChatGPT 지시 → Claude Code 실행)인 경우가 많지만, 하나의 사건으로 묶을지는 검토자가 판단합니다.', '',
         '## 파일', '',
         '- `EPISODE_INDEX.md` — 전체 목록(발생 순). 제목·시기·프로젝트·상태·원본 구간·출판 표시.',
         '- `EPISODE_DETAILS/<프로젝트>.md` — 에피소드별 배경·목표·진행·AI 행동·사용자 반응·결과·실제 인용(메시지 ID)·연결·미확인 정보·익명화 요소.',
         '- `CHRONOLOGY.md` — 시간순 연표와 프로젝트별 흐름.',
         '- `COVERAGE_AUDIT.md` — 4,953개 구간 각각의 처리 결과, 기존 CROSS_LINKS 재검토, 검증 결과.',
         '- `_data/episodes.json`, `_data/segments.json` — 같은 내용의 기계 판독용 데이터.',
         '- `tools/` — 조사·검증·생성 도구와 조사 지침(재현용).', '',
         '## 검토 순서 제안', '',
         '1. `CHRONOLOGY.md`로 전체 흐름과 프로젝트별 시작·변화·종료를 봅니다.',
         '2. `EPISODE_INDEX.md`에서 관심 에피소드를 고르고 상세 파일로 들어갑니다.',
         '3. 책에 쓸 장면은 상세 파일의 "중요 대화(원문)"의 메시지 ID로 마스터 원문(`conversation_master_v1/parts/`)을 확인합니다.',
         '4. 선정한 에피소드의 근거는 `manuscript/SOURCES.md`에 사건 ID·메시지 ID로 기록합니다.', '',
         '## 프로젝트별 에피소드 수', '', '| 프로젝트 | 에피소드 |', '|---|---:|']
    for proj, eps in sorted(by_proj.items(), key=lambda kv: -len(kv[1])):
        L.append(f'| {PROJECT_KO.get(proj, proj)} | {len(eps)} |')
    L += ['', '## 상태·표시', '', '| 상태 | 수 |', '|---|---:|'] + [f'| {k} | {v} |' for k, v in states.most_common()]
    L += ['', '| 출판 표시 | 수 |', '|---|---:|'] + [f'| {k} | {v} |' for k, v in flags.most_common()]
    L += ['', '- "회사 업무 가능성", "사생활 가능성" 표시 에피소드는 출판 대상이 아닙니다. 상세 서술과 인용을 이 저장소에 남기지 않았습니다.',
          '- "투자 개인정보 주의"는 보유 종목·금액 등 개인 투자 정보가 섞여 있어 출판 시 수치 익명화가 필요합니다.', '',
          '## 사건 유형(조사자 태그, 중복 허용)', '', '| 유형 | 에피소드 |', '|---|---:|'] + [f'| {k} | {v} |' for k, v in types.most_common(25)]
    L += ['', '## 읽는 법과 검증 한계', '',
          '- 인용은 마스터 `parts/` 원문과 글자 단위로 대조했고 메시지 ID를 함께 적었습니다. 인용 외 문장은 조사자 정리이며 원문이 아닙니다.',
          '- 조사는 원문 축약본(사용자 발언 앞 450자·뒤 120자, AI 보고 앞 260자·뒤 120자, AI 중간 메시지 앞 90자)으로 했습니다. 축약에서 빠진 세부는 원문으로 다시 확인해야 합니다.',
          '- AI가 "완료·통과"라고 말한 것은 AI의 보고이며 실제 결과로 단정하지 않았습니다.',
          '- 사용자가 붙여넣은 다른 AI의 글은 작성자가 원문으로 확인되지 않으면 "작성자 확인 불가"로 남겼습니다.',
          '- 연결(links)의 "미확정"은 증거가 부족하다는 뜻입니다. 사실로 쓰기 전에 원문을 확인해야 합니다.',
          '- 묶음(조사 단위) 경계에서 나뉜 같은 웹 사건은 별도 검토로 통합했고, 통합한 경우 상세 파일에 원래 조사 key를 남겼습니다.',
          '- 웹·로컬 연결의 "확정"은 근거에 원문 구간과 메시지 번호가 적힌 경우만 인정했습니다. 그 밖의 연결은 "미확정(근거 불충분)"으로 낮췄습니다. 확정 연결도 책에 쓰기 전에 원문을 다시 확인해야 합니다.',
          '- 로컬 세션에는 사용자 역할로 자동 주입된 지시문(하위 에이전트, 자동 승인 검토, 예약 실행)이 많습니다. 이를 사용자의 실제 발언으로 서술하지 않으려 했지만, 축약본 기준 판단이라 원문 확인이 필요합니다.',
          '- 같은 세션 안에서 여러 사건으로 나눈 로컬 에피소드는 메시지 범위로 구분했고, 시작·종료일은 세션 단위 시각이라 근사치일 수 있습니다.',
          '- 마스터 원문에는 가림이 빠진 자사명·호칭이 일부 있습니다. 이 결과물에서는 가림 표식으로 바꾸거나 해당 인용을 뺐습니다. 마스터 자체는 수정하지 않았습니다.',
          '- 첨부 이미지·파일 내용, 추론(thoughts), 도구 입출력은 마스터에 전재되지 않아 조사하지 못했습니다.']
    return '\n'.join(L) + '\n'


def checkpoint(b):
    meta = b['meta']
    done = sorted(b['processed_chunks'])
    todo = sorted(k for k in meta if k not in b['processed_chunks'])
    local = [k for k in todo if k.startswith('L')]
    L = ['# CHECKPOINT', '',
         f'- 상태: {"전체 4,953개 구간 처리 완료" if b["complete"] else "진행 중"}.',
         f'- 기준 커밋: `3aead08` (main). 마스터 `conversation_master_v1/`는 수정하지 않았습니다.',
         f'- 완료 묶음({len(done)}): {", ".join(done)}',
         f'- 남은 묶음({len(todo)}): {", ".join(todo) or "없음"}', '',
         '| 남은 묶음 | 구간 수 | 기간 | 첫 구간 | 끝 구간 |', '|---|---:|---|---|---|']
    for k in todo:
        m = meta[k]
        L.append(f"| {k} | {m['n']} | {m['first']} ~ {m['last']} | {m['events'][0]} | {m['events'][-1]} |")
    L += ['', '## 이어서 하는 방법', '',
          '1. 묶음은 구간 ID 목록으로 정의됩니다(위 표의 첫·끝 구간과 `_data/segments.json`의 처리 결과 비교). 로컬 묶음은 로컬 구간을 시작 시각순으로 약 14만 자씩 나눈 것입니다.',
          '2. 조사 도구는 `tools/`에 있습니다: `parse.py`(마스터 파싱), `digest.py`(축약본), `validate.py`(묶음 결과 검증), `build.py`(이 폴더 파일 생성), 조사 지침 `INSTRUCTIONS.md`·`INSTRUCTIONS_LOCAL.md`. 작업 폴더는 환경변수 `CENSUS_WORK`로 지정하며 Git 밖에 둡니다.',
          '3. 묶음 조사 결과(JSON)와 개인정보 검토 목록(`privacy/`)은 실명·가림 누락 문자열을 포함할 수 있어 Git에 넣지 않았습니다. 다음 세션에서는 `_data/episodes.json`·`_data/segments.json`(가림 처리본)을 기준으로 씁니다.',
          '4. 묶음 정의: 웹은 대화 단위로 시작 시각순 약 14만 자, 로컬은 세션 단위로 시작 시각순 약 14만 자. 각 묶음의 구간 목록은 `_data/segments.json`의 `chunk` 값과 같습니다.']
    return '\n'.join(L) + '\n'


def coverage(b, detail_file):
    seg, events, episodes = b['seg'], b['events'], b['episodes']
    allids = sorted(events)
    web = {e['id'] for e in b['web']}
    st = collections.Counter(v['s'] for v in seg.values())
    multi = [e for e, v in seg.items() if len(v['ep']) > 1]
    starts = {ep['events'][0] for ep in episodes if ep['events']}
    ep_segs = [e for e, v in seg.items() if v['s'] == 'EP']
    merged_eps = [ep for ep in episodes if len(ep['source_keys']) > 1]
    unconfirmed = sum(1 for ep in episodes for l in ep.get('links', []) if l.get('status') != '확정')
    L = ['# COVERAGE AUDIT', '',
         f'- 마스터 구간 전체: {len(allids):,}개 (웹 {len(web):,} · 로컬 {len(allids) - len(web):,})',
         f'- 확인한 구간: {len(seg):,}개 ({len(seg) / len(allids) * 100:.1f}%). 미처리 {len(allids) - len(seg):,}개.', '',
         '## 구간 처리 결과', '',
         '| 구분 | 구간 수 |', '|---|---:|',
         f'| 에피소드에 연결 | {st["EP"]:,} |',
         f'| └ 에피소드의 첫 구간(독립 사건으로 연결) | {len(starts & set(ep_segs)):,} |',
         f'| └ 기존 에피소드에 통합된 후속 구간 | {len(set(ep_segs) - starts):,} |',
         f'| 단순 원문 보존 | {st["PRESERVE"]:,} |',
         f'| 사건으로 분류할 수 없음(빈 대화·테스트·회사 업무·사생활 가능성) | {st["NOT_EP"]:,} |',
         f'| 원본 부족·확인 불가 | {st["UNVERIFIABLE"]:,} |',
         f'| 여러 에피소드에 다중 참조된 구간 | {len(multi):,} |', '',
         '| 처리 | 웹 구간 | 로컬 구간 |', '|---|---:|---:|'] + [
         f"| {STATUS_KO[k]} | {sum(1 for e, v in seg.items() if v['s'] == k and e in web):,} | {sum(1 for e, v in seg.items() if v['s'] == k and e not in web):,} |"
         for k in STATUS_KO] + ['',
         f'- 에피소드 기록: {len(episodes):,}개. 원문 확인 연결 {len(b["edges"]):,}쌍.',
         f'- 묶음 경계에서 통합한 에피소드: {len(merged_eps):,}개',
         f'- 에피소드에 기록된 미확정 연결: {unconfirmed:,}건', '',
         '## 기존 CROSS_LINKS.json 재검토', '', '| 결과 | 건수 |', '|---|---:|']
    for k, v in b['cl_result'].most_common():
        L.append(f'| {k} | {v:,} |')
    if b['uncertain']:
        L += ['', '## 묶음 경계 통합 미확정', '', '같은 사건일 가능성이 있으나 원문 근거가 부족해 통합하지 않은 에피소드 쌍입니다.', '']
        for u in b['uncertain']:
            L.append(f"- {', '.join(b['ids'].get(k, k) for k in u.get('keys', []))}: {scrub(u.get('why', ''))}")
    L += ['', '서로 다른 에피소드 사이의 문장 공유는 동일 사건의 증거로 확정하지 않았습니다.', '']
    if b['cl_rows']:
        L += ['| 출발 구간 | 도착 구간 | 출발 에피소드 | 도착 에피소드 | 공유 줄 | 시각 순서 일치 |', '|---|---|---|---|---:|---|']
        for a, c, ea, eb, n, t in b['cl_rows']:
            L.append(f"| {a} | {c} | {', '.join(ea)} | {', '.join(eb)} | {n} | {'예' if t else '아니오'} |")
        L.append('')
    L += ['## 검증', '',
          f'- 구간 누락: {sum(1 for e in allids if e not in seg)}개',
          f'- 인용 원문·메시지 ID·발언자 대조 오류: {len(b["problems"])}건',
          f'- 개인정보 검토로 뺀 인용: {len(b["dropped"])}건 (가림 없이 남은 자사명·호칭 등이 들어 있어 제외. 위치: {", ".join(x.split(" ", 1)[1] for x in b["dropped"]) or "-"})',
          f'- 출판 제외 표시(회사 업무·사생활 가능성) 에피소드: {sum(1 for ep in episodes if ep.get("publish_flag") in EXCLUDED)}개 — 서술과 인용을 생략하고 원본 구간만 남김',
          '- 인용은 마스터 `parts/` 원문 메시지 본문과 공백 정규화 후 글자 단위로 대조했습니다.', '',
          '## 구간별 처리 내역', '',
          '| 구간 | 플랫폼 | 시작 | 처리 | 에피소드 | 내용 라벨 |', '|---|---|---|---|---|---|']
    for e in allids:
        ev = events[e]
        if e in seg:
            v = seg[e]
            L.append(f"| {e} | {ev['platform']} | {ev['start'][:10]} | {STATUS_KO[v['s']]} | {', '.join(v['ep'])} | {md_escape(v.get('label', ''))} |")
        else:
            L.append(f"| {e} | {ev['platform']} | {ev['start'][:10]} | 미처리(로컬 단계) | | |")
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    b = build()
    files, leaks = write(b)
    print('dropped quotes', b['dropped'])
    print('episodes', len(b['episodes']), 'segments', len(b['seg']), 'problems', len(b['problems']), 'leaks', len(leaks))
    for p in b['problems'][:30]:
        print(' ', p)
    for p in leaks[:30]:
        print('  LEAK', p)
    if '--write' in sys.argv:
        for name, text in files.items():
            path = f'{OUT}/{name}'
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'w', encoding='utf-8').write(text)
        print('written', len(files))
