import re,json,os,sys,collections
B='/home/user/book/conversation_master_v1/'
EV={e['id']:e for e in json.load(open(B+'EVENTS.json'))}
hdr=re.compile(r'^## (E\d{5}) · (.*)$')
mh=re.compile(r'^#### \[(\d+)\] (.+?) · (\S+) · 메시지 `([^`]+)`(?: · 노드 `([^`]+)`)?')
out={}
for f in sorted(os.listdir(B+'parts')):
    lines=open(B+'parts/'+f,encoding='utf-8').read().split('\n')
    cur=None;msg=None;meta=[]
    def flush():
        if msg is not None: cur['msgs'].append(msg)
    for i,l in enumerate(lines):
        m=hdr.match(l)
        if m:
            if cur: flush(); out[cur['id']]=cur
            cur={'id':m.group(1),'file':f,'line':i+1,'meta':[],'msgs':[]};msg=None;continue
        if cur is None: continue
        m=mh.match(l)
        if m:
            flush()
            msg={'n':int(m.group(1)),'who':m.group(2),'t':m.group(3),'id':m.group(4),'line':i+1,'body':[]};continue
        if msg is None: cur['meta'].append(l)
        else: msg['body'].append(l)
    if cur: flush(); out[cur['id']]=cur
print(len(out), len(set(EV)-set(out)))
# body cleanup: strip parent node lines and fences
def clean(b):
    t='\n'.join(b)
    t=re.sub(r'^- 부모 노드: `[^`]*`\n?','',t.lstrip('\n'),flags=re.M)
    return t.strip()
for e in out.values():
    for m in e['msgs']: m['text']=clean(m['body']); del m['body']
    e['meta']='\n'.join(x for x in e['meta'] if x.strip())
json.dump(out,open('parsed.json','w'),ensure_ascii=False)
c=collections.Counter(m['who'] for e in out.values() for m in e['msgs']); print(c.most_common(20))
tot=sum(len(m['text']) for e in out.values() for m in e['msgs']); print('chars',tot)
