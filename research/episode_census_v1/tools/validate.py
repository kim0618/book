"""Usage: python3 -I validate.py W01  -> checks out/W01.json against the chunk and the full master text."""
import json,sys,re,os
D=os.environ.get('CENSUS_WORK') or os.path.dirname(os.path.abspath(__file__))
name=sys.argv[1]
M=json.load(open(f'{D}/chunks/meta.json'))[name]
P=json.load(open(f'{D}/parsed.json'))
WHO={'사용자 역할':'U','시스템':'S','ChatGPT':'GPT','Claude 웹':'CW','Claude Code (WSL)':'CC','Claude Code (Windows)':'CC','Codex (WSL)':'CX'}
PT=f'{D}/privacy/private_terms.json'
BLOCK=re.compile('|'.join(json.load(open(PT))['block'])) if os.path.exists(PT) else None
norm=lambda s:re.sub(r'\s+',' ',s).strip()
o=json.load(open(f'{D}/out/{name}.json'))
err=[]
seg=o.get('segments',{})
miss=[e for e in M['events'] if e not in seg]; extra=[e for e in seg if e not in M['events']]
if miss: err.append(f'segments 누락 {len(miss)}: {miss[:20]}')
if extra: err.append(f'묶음 밖 구간 {extra[:10]}')
eps={x['key']:x for x in o.get('episodes',[])}
for k,v in seg.items():
    if v.get('s') not in ('EP','PRESERVE','NOT_EP','UNVERIFIABLE'): err.append(f'{k} 상태값 {v.get("s")}')
    if v.get('s')=='EP':
        for ep in v.get('ep',[]):
            if ep not in eps: err.append(f'{k} -> 없는 에피소드 {ep}')
            elif k not in eps[ep]['events']: err.append(f'{k} 가 {ep}.events에 없음')
for key,x in eps.items():
    for ev in x.get('events',[]):
        if ev in seg and key not in seg[ev].get('ep',[]): err.append(f'{key}.events의 {ev} 가 segments에서 {key}로 연결 안 됨')
    for q in x.get('key_messages',[]):
        e,n=q.get('e'),q.get('n')
        ms=[m for m in P.get(e,{}).get('msgs',[]) if m['n']==n]
        if not ms: err.append(f'{key} 인용 메시지 없음 {e}#{n}'); continue
        m=ms[0]
        if WHO.get(m['who'],m['who'])!=q.get('sp'): err.append(f'{key} 발언자 불일치 {e}#{n}: {q.get("sp")} vs {WHO.get(m["who"])}')
        if norm(q.get('q','')) not in norm(m['text']): err.append(f'{key} 인용 불일치 {e}#{n}: {q.get("q","")[:40]}')
        if BLOCK and BLOCK.search(q.get('q','')): err.append(f'{key} 인용에 비공개 식별 문자열 {e}#{n}')
print('OK' if not err else '\n'.join(err[:80])); print(f'segments {len(seg)}/{len(M["events"])}, episodes {len(eps)}, errors {len(err)}')
