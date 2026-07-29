import re,sys
POOL=['t3','t4','t5','t6','t7','t8','t9']
REGN={11:'t3',12:'t4',13:'t5',14:'t6',15:'t7',24:'t8',25:'t9'}

def parse(path):
    ops=[]
    init=None
    for l in open(path):
        m=re.match(r'POOL (\d+) p(\d+) i(-?\d+)\s+d(\d+)\s+(\S+)\s*(.*)$', l.rstrip())
        if not m: continue
        seq,proc,i,d,ev,rest=m.groups(); seq=int(seq); i=int(i)
        if ev=='GET<':
            r=rest.split('->')[1].split()[0]
            if init is None:
                pass
            ops.append((seq,i,'GET',r))
        elif ev=='FREE<':
            r=rest.split()[0]
            if r in POOL: ops.append((seq,i,'FREE',r))
        elif ev=='GET>' and init is None:
            mm=re.search(r'free=\[([^\]]*)\]',rest)
            if mm: init=[x for x in mm.group(1).split(',') if x]
        elif ev=='EMIT':
            mm=re.match(r'(f_\S+)\s+n=(\S+) ord=(-?\d+)(.*)$',rest)
            if not mm: continue
            fn,n,ordv,tail=mm.groups()
            if 'op=17' not in tail: continue
            args={k:int(v,16) for k,v in re.findall(r'(a\d)=([0-9a-f]{8})',tail)}
            ops.append((seq,i,'EMIT',(fn,int(ordv),args)))
    return init,ops

def candidate_pass(ops):
    """assign vids and record, per EMIT ord, the vid of dst/operands that are pool regs"""
    live={}; vid=0; vops=[]; emitvid={}
    for seq,i,k,p in ops:
        if k=='GET':
            vid+=1; live[p]=vid; vops.append(('GET',vid,seq,i))
        elif k=='FREE':
            v=live.pop(p,None); vops.append(('FREE',v,seq,i))
        else:
            fn,ordv,args=p
            mapped={}
            for key in ('a1','a2','a3'):
                if key in args and args[key] in REGN:
                    r=REGN[args[key]]
                    mapped[key]=live.get(r)
            emitvid[ordv]=(fn,args,mapped)
            vops.append(('EMIT',ordv,seq,i))
    return vops,emitvid

def replay(vops,init,inserts=()):
    """inserts: iterable of vops-indices; after processing that index, do one GET+FREE"""
    free=list(init); phys={}
    ins=set(inserts)
    for idx,(k,v,seq,i) in enumerate(vops):
        if k=='GET':
            phys[v]=free.pop(0)
        elif k=='FREE':
            if v in phys: free.append(phys[v])
        if idx in ins:
            r=free.pop(0); free.append(r)
    return phys

TARGET={187:'t6',188:'t5',189:'t4',192:'t8',198:'t5',199:'t4',200:'t7',
        208:'t4',209:'t3',210:'t6',214:'t5',219:'t8',225:'t4',229:'t7',235:'t3'}
CAND  ={187:'t7',188:'t6',189:'t5',192:'t4',198:'t6',199:'t5',200:'t8',
        208:'t4',209:'t5',210:'t8',214:'t9',219:'t6',225:'t4',229:'t3',235:'t5'}

if __name__=='__main__':
    init,ops=parse(sys.argv[1])
    vops,emitvid=candidate_pass(ops)
    base=replay(vops,init)
    def dsts(phys):
        out={}
        for ordv,(fn,args,mapped) in emitvid.items():
            v=mapped.get('a1')
            if v is not None: out[ordv]=phys.get(v)
        return out
    b=dsts(base)
    print("sanity (no insert) reproduces candidate:", all(b.get(k)==CAND[k] for k in CAND), {k:(b.get(k),CAND[k]) for k in CAND if b.get(k)!=CAND[k]})
    # sweep insertion points
    hits=[]
    for idx in range(len(vops)):
        p=replay(vops,init,[idx])
        d=dsts(p)
        score=sum(1 for k in TARGET if d.get(k)==TARGET[k])
        hits.append((score,idx))
    hits.sort(reverse=True)
    print("best insertion points (score/%d):"%len(TARGET))
    for score,idx in hits[:8]:
        k,v,seq,i=vops[idx]
        print(f"   score={score}  idx={idx}  after {k} v={v} seq={seq} i={i}")
    best=hits[0][1]
    p=replay(vops,init,[best]); d=dsts(p)
    print("\nord  cand  target  predicted")
    for k in sorted(TARGET):
        mark='' if d.get(k)==TARGET[k] else '   <-- MISS'
        print(f"{k:4d} {CAND[k]:5s} {TARGET[k]:6s} {str(d.get(k)):9s}{mark}")
