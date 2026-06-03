#!/usr/bin/env python3
"""Bootstrap DefaultInsAsmRepos.sm_90.txt from library SASS corpus, using a
robust per-InsKey builder that tolerates relocated/placeholder outliers
(branches/calls whose encoded offset is a linker placeholder)."""
import sys, os, glob, time, collections

CUASM = "/net/netscratch/hpu8/sass_llm_loop/external/CuAssembler"
sys.path.insert(0, CUASM)
sys.path.insert(0, "/net/netscratch/hpu8/sm90_port/work")
from CuAsm.CuInsFeeder import CuInsFeeder
from CuAsm.CuInsParser import CuInsParser
from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos
from CuAsm.CuSMVersion import CuSMVersion
from CuAsm.CuAsmLogger import CuAsmLogger
from robust_build import robust_build
CuAsmLogger.initLogger(log_file=None, stdout_level=60)

ARCH = "sm_90"
CORPUS = sorted(glob.glob("/net/netscratch/hpu8/sm90_port/corpus/*.sm90.sass"))
OUT = os.path.join(CUASM, "CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_90.txt")

repos = CuInsAssemblerRepos(arch=ARCH)
parser = repos.m_InsParser
smv = repos.m_Arch

# 1) Parse all instructions, group samples by ins_key.
#    Dedup by (vals, modi, code): keeps every distinct operand pattern (basis
#    coverage) AND any same-(vals,modi)/different-code outliers (for the robust
#    builder), while collapsing the millions of identical repeats in a 4M corpus.
t0 = time.time()
by_key = collections.defaultdict(list)
seen = collections.defaultdict(set)
n_ins = n_parse_fail = 0
for corpus in CORPUS:
    feeder = CuInsFeeder(corpus, archfilter=ARCH)
    for addr, code, s, ctrl in feeder:
        n_ins += 1
        try:
            ins_key, ins_vals, ins_modi = parser.parse(s, addr, code)
        except Exception:
            n_parse_fail += 1
            continue
        tv, tm = tuple(ins_vals), tuple(ins_modi)
        sig = (tv, tm, code)
        if sig not in seen[ins_key] and len(by_key[ins_key]) < 12000:
            seen[ins_key].add(sig)
            by_key[ins_key].append((tv, tm, code, (addr, code, s)))
    print(f"[{os.path.basename(corpus)}] parsed, running total {n_ins}, distinct samples {sum(len(v) for v in by_key.values())}")

# 2) Robust-build each key.
t1 = time.time()
tot_acc = tot_rej = 0
worst = []
for key, samples in by_key.items():
    asm, nacc, nrej = robust_build(key, smv, samples)
    repos.m_InsAsmDict[key] = asm
    tot_acc += nacc; tot_rej += nrej
    if nrej > 0:
        worst.append((key, nacc, nrej, getattr(asm, 'm_PSolFac', None)))

t2 = time.time()
print(f"\n=== bootstrap summary ===")
print(f"  parsed {n_ins} ins ({n_parse_fail} parse-fail) in {t1-t0:.0f}s; built {len(by_key)} keys in {t2-t1:.0f}s")
print(f"  total accepted {tot_acc}, rejected(outliers) {tot_rej}")
print(f"  keys with rejections (key: acc/rej, PSolFac):")
for key, nacc, nrej, fac in sorted(worst, key=lambda x: -x[2])[:15]:
    flag = "" if fac == 1 else f"  <-- PSolFac={fac} NON-INTEGRAL!"
    print(f"    {key:<22} {nacc:>6}/{nrej:<5}{flag}")

print(f"\nsaving repos -> {OUT}")
repos.save2file(OUT)
print("saved. size:", os.path.getsize(OUT), "bytes")
