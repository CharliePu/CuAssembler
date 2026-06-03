"""Robust per-InsKey basis builder: tolerant of relocated/placeholder outliers.

Greedy push is order-sensitive — a relocated branch seeding the basis rejects the
real majority. Strategy: build greedily; if acceptance is low, the consistent set
is among the *rejected* samples, so reseed from them. Iterate, keep the basis with
the most acceptances.
"""
import sys
CUASM="/net/netscratch/hpu8/sass_llm_loop/external/CuAssembler"
sys.path.insert(0, CUASM)
from CuAsm.CuInsAssembler import CuInsAssembler

def build_one(key, arch, samples):
    """samples: list of (vals, modi, code, info). Returns (asm, accepted_list, rejected_list)."""
    asm = CuInsAssembler(key, arch=arch)
    acc, rej = [], []
    for vals, modi, code, info in samples:
        flag, _ = asm.push(list(vals), list(modi), code, info)
        (acc if flag else rej).append((vals, modi, code, info))
    return asm, acc, rej

def robust_build(key, arch, samples, max_iter=6):
    order = samples
    best = None
    for _ in range(max_iter):
        asm, acc, rej = build_one(key, arch, order)
        if best is None or len(acc) > best[1]:
            best = (asm, len(acc), len(rej))
        if len(rej) <= 0.02 * max(1, len(samples)):
            break
        if len(acc) >= len(rej):
            break                       # majority already accepted; remaining are true outliers
        order = rej + acc               # reseed from the (larger) rejected set
    return best  # (asm, n_acc, n_rej)

if __name__ == "__main__":
    import glob, collections
    from CuAsm.CuInsFeeder import CuInsFeeder
    from CuAsm.CuInsParser import CuInsParser
    from CuAsm.CuSMVersion import CuSMVersion
    from CuAsm.CuAsmLogger import CuAsmLogger
    CuAsmLogger.initLogger(log_file=None, stdout_level=60)
    arch='sm_90'; parser=CuInsParser(arch)
    samples=[]
    for corpus in sorted(glob.glob("/net/netscratch/hpu8/sm90_port/corpus/*.sm90.sass")):
        f=CuInsFeeder(corpus, archfilter=arch)
        for addr,code,s,ctrl in f:
            toks=s.strip().split(); opn=next((t for t in toks if not t.startswith('@')),'')
            if opn=='BRA':
                key,vals,modi=parser.parse(s,addr,code)
                if key=='BRA_II':
                    samples.append((tuple(vals),tuple(modi),code,(addr,code,s.strip())))
        if len(samples)>=7000: break
    asm,nacc,nrej = robust_build('BRA_II', CuSMVersion(arch), samples)
    print(f"BRA_II robust: accepted={nacc} rejected={nrej} of {len(samples)}  m_PSolFac={asm.m_PSolFac}")
    # reproduce check
    ok=bad=0
    for vals,modi,code,info in samples:
        try: c=asm.buildCode(list(vals),list(modi))
        except Exception: c=None
        if c==code: ok+=1
        else: bad+=1
    print(f"reproduce: ok={ok} bad={bad} ({100*ok/len(samples):.1f}% encode correctly)")
