import sys, os, re, json, subprocess
sys.path.insert(0,'/private/tmp/claude-501/-Users-adamkratch-Desktop-dev-dp64/b12cb2b8-7601-43f3-b97b-92a43143a5a1/scratchpad/texDPT_oracle')
import olib
from concurrent.futures import ThreadPoolExecutor

WEBS=[46,43,16,157,122,20,126,137,149,234,241,210,97,227,181,185,207,23,103,0,26,104,277,278,35,32,162,3,275,18]
COLORS=list(range(1,11))
C2R={1:'v0',2:'v1',3:'a0',4:'a1',5:'a2',6:'a3',7:'t0',8:'t1',9:'t2',10:'t3',11:'t4',12:'t5'}
IDX=[8,10,17,19,20,25,28,86,90,92,94,144,152,172,173,174,175,177,180,182,193,194,196,197,204,259,264,280,289]

def run(w,c):
    name=f'I{w}_{c}'
    log=olib.LOGS+f'/{name}.log'
    b=olib.build(name, env_extra={'CDX_PROC':'11','CDX_FORCE':f'w{w}=c{c}','CDX_LOG':'1','CDX_OUT':log}, cdx=True)
    if not b['o']: return None
    cm={}
    for line in open(log):
        m=re.search(r'p1color proc=11 web=(\d+) sym=\d+ color=(\d+)', line)
        if m: cm[int(m.group(1))]=int(m.group(2))
    d=[olib._norm(x) for x in olib.disasm(b['o'])]
    if len(d)!=303: return None
    regs={i: re.findall(r'\b(zero|v[01]|a[0-3]|t[0-9]|s[0-8])\b', d[i]) for i in IDX}
    return {'w':w,'c':c,'cm':cm,'regs':regs,'insns':{i:d[i] for i in IDX}}

if __name__=='__main__':
    items=[(w,c) for w in WEBS for c in COLORS]
    with ThreadPoolExecutor(10) as ex:
        res=[r for r in ex.map(lambda t: run(*t), items) if r]
    json.dump(res, open('ident.json','w'))
    print('collected', len(res))
