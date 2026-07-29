import sys, os, re
W="/private/tmp/claude-501/-Users-adamkratch-Desktop-dev-dp64/b12cb2b8-7601-43f3-b97b-92a43143a5a1/scratchpad/intersect_full"
sys.path.insert(0,W)
from eval import sig, build, cmp, dis, tdis, REPO

BASE=open(W+"/orig_body.c").read()

def patch(base, *pairs):
    s=base
    for old,new in pairs:
        assert old in s, "MISSING: "+old[:120]
        assert s.count(old)==1, "AMBIG: "+old[:80]
        s=s.replace(old,new)
    return s

def V(name, body, note=""):
    return sig(name, body, note=note)

import subprocess as _sp, json as _json
def view(name):
    o=W+"/objs/"+name+".o"
    r=_sp.run([REPO+"/.venv/bin/decomp-workbench","view",REPO+"/build/src/intersect.o",o,
               "--symbol","func_80053B24","--json"],cwd=REPO,capture_output=True,text=True)
    j=_json.loads(r.stdout)
    return {k:j.get(k) for k in ("verdict","structural","schedule","register","constant","commutative",
            "relocation","displacement","aligned_rows","match","words")} | {"hunks": len(j.get("hunks") or [])}
def VV(name, body, note=""):
    r=V(name,body,note)
    if r.get("verdict")=="COMPILE_FAIL": return r
    v=view(name)
    print("      -> aligned: struct=%s sched=%s reg=%s const=%s hunks=%s match=%s/%s" % (
        v["structural"],v["schedule"],v["register"],v["constant"],v["hunks"],v["match"],v["aligned_rows"]))
    r["view"]=v
    return r
