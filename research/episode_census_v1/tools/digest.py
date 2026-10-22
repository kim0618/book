import json,re,collections,sys
P=json.load(open('parsed.json'))
E={e['id']:e for e in json.load(open('/home/user/book/conversation_master_v1/EVENTS.json'))}
def cut(t,h,tl):
    t=re.sub(r'^`{3,}text\n|\n`{3,}$','',t).strip()
    t=re.sub(r'\n{3,}','\n\n',t)
    return t if len(t)<=h+tl+40 else t[:h]+f' …[{len(t)-h-tl}자 생략]… '+t[-tl:]
WHO={'사용자 역할':'U','시스템':'S','ChatGPT':'GPT','Claude 웹':'CW','Claude Code (WSL)':'CC','Claude Code (Windows)':'CC','Codex (WSL)':'CX'}
def digest(k):
    e=P[k];ev=E[k];ms=[m for m in e['msgs'] if not m['text'].startswith('원본 보관본 참조')]
    title=re.search(r'대화 제목\(가림 적용\): (.*)',e['meta']) or re.search(r'세션 제목[^:]*: (.*)',e['meta'])
    out=[f"### {k} | {ev['platform']} | {ev['start'][:16]}~{ev['end'][:16]} | {ev['classification']}/{ev['project']} | title={(title.group(1) if title else ev['title'])[:80]}"]
    for i,m in enumerate(ms):
        w=WHO.get(m['who'],m['who'])
        nxt=ms[i+1]['who'] if i+1<len(ms) else None
        if w=='U': s=cut(m['text'],450,120)
        elif nxt in (None,'사용자 역할'): s=cut(m['text'],260,120)
        else: s=cut(m['text'],90,0)
        out.append(f"[{m['n']}|{w}] {s}")
    return '\n'.join(out)
if __name__=='__main__':
    D={k:digest(k) for k in sorted(P)}
    json.dump(D,open('digest.json','w'),ensure_ascii=False)
    print(sum(len(v) for v in D.values()))
    c=collections.Counter()
    for k,v in D.items(): c[E[k]['platform']]+=len(v)
    print(c)
