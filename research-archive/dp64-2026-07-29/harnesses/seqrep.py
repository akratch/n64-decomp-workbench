import sys; sys.path.insert(0,'.')
exec(open('win.py').read())
from gen import *
from gen2 import *
TARGET_SEQ='t5 t8 t6 t3 t4 t9 t7 t5 t8'
def seqof(nm):
    d=dis(W+'/objs/'+nm+'.o'); out=[]
    for x in d[105:]:
        p=x.split()
        if len(p)<2: continue
        op=p[0]; dst=p[1].split(',')[0]
        if op in ('sw','sb','sh','beq','bne','bnez','beqz','blez','bgtz','bnel','beql','b','j','jal','jr','nop','multu','mult','slt','sltu'): continue
        if dst in ('sp','ra','v0','v1','a0','a1','a2','a3','s0','s1','t0','t1','t2','at'): continue
        out.append(dst)
    return ' '.join(out)
def rep(nm, b):
    r=sig(nm,b,quiet=True)
    if r['verdict']=='COMPILE_FAIL': print('%-26s COMPILE_FAIL'%nm); return r
    s=seqof(nm); r['seq']=s
    mark='  <<<< MATCH' if s==TARGET_SEQ else ''
    print('%-26s v=%-22s w=%-4s i=%-4s seq=%-32s%s'%(nm,r['verdict'],r['words'],r['insns'],s,mark))
    return r
