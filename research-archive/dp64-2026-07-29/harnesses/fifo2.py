import fifo, itertools
init,ops=fifo.parse("tx/cand102.pool")
vops,emitvid=fifo.candidate_pass(ops)
N=len(vops)
T={182:'t9',187:'t6',188:'t5',189:'t4',192:'t8',197:'t9',198:'t5',199:'t4',200:'t7',
   208:'t4',209:'t3',210:'t6',214:'t5',219:'t8',225:'t4',229:'t7',235:'t3'}
def replay(inserts=(),deletes=()):
    free=list(init); phys={}
    ins=set(inserts); dele=set(deletes)
    for idx,(k,v,seq,i) in enumerate(vops):
        if k=='GET':
            if v not in dele: phys[v]=free.pop(0)
        elif k=='FREE':
            if v in phys and v not in dele: free.append(phys[v])
        if idx in ins:
            r=free.pop(0); free.append(r)
    return phys
def dsts(phys): return {o:phys.get(m.get('a1')) for o,(fn,a,m) in emitvid.items()}
def score(inserts=(),deletes=()):
    d=dsts(replay(inserts,deletes))
    return sum(1 for k in T if d.get(k)==T[k]), d
