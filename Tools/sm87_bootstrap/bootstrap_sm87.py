#!/usr/bin/env python3
"""Bootstrap DefaultInsAsmRepos.sm_87.txt (Jetson AGX Orin / Ampere GA10x) from a
library SASS corpus — same method as the sm_90 port (see ../sm90_bootstrap/).

Corpus: sm_87 cubins extracted from the L4T container's aarch64 CUDA 12.6
libraries (curand, nppif, nppig, nppist, nppicc, nppidei):
    in-container:  cuobjdump --extract-elf all /usr/local/cuda/lib64/<lib.so>
    on login node: make_corpus.py  (fixCubinDesc + `cuobjdump -sass` per cubin)
The desc-hacked-cubin corpus is REQUIRED. Two wrong alternatives, both tried:
- `cuobjdump -sass` on the raw .so prints memory ops WITHOUT the descriptor
  (`LDG.E.64 R8, [R6.64]`, key LDG_R_ARI) while bin2asm/asm2bin work in
  desc-hacked form (`LDG.E.64 R8, desc[UR4][R8.64]`, key LDG_R_dARI) ->
  wrong operand shape learned for every LDG/STG/ATOM/RED.
- dsass output has the right operands but DROPS the second 64-bit code word of
  each 128-bit instruction (codeonly_line_mode='none'), and its ctrl-code
  prefix doesn't match CuInsFeeder's line patterns -> nothing learnable.
fixCubinDesc + cuobjdump -sass gives desc operand forms AND full codes, and is
exactly what CubinFile disassembles, so learned encodings are consistent with
asm2bin (--preserve-desc-from then restores the real desc bits per site).
No Ampere-specific CuAssembler changes were needed — unlike Hopper, sm_87 uses
the stock 8x encoding path; the stock sm_86/80 repos were just missing
GA10x-codegen keys like BMOV_B_II.
"""
import sys, os, glob, time, collections

CUASM = "/net/netscratch/hpu8/sass_llm_loop/external/CuAssembler"
sys.path.insert(0, CUASM)
sys.path.insert(0, os.path.join(CUASM, "Tools/sm90_bootstrap"))  # reuse robust_build
from CuAsm.CuInsFeeder import CuInsFeeder
from CuAsm.CuInsAssemblerRepos import CuInsAssemblerRepos
from CuAsm.CuAsmLogger import CuAsmLogger
from robust_build import robust_build
CuAsmLogger.initLogger(log_file=None, stdout_level=60)

ARCH = "sm_87"
CORPUS = sorted(glob.glob("/net/netscratch/hpu8/sm87_port/corpus/*.sm87.sass"))
OUT = os.path.join(CUASM, "CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_87.txt")

repos = CuInsAssemblerRepos(arch=ARCH)
parser = repos.m_InsParser
smv = repos.m_Arch

# 1) Parse all instructions, group samples by ins_key (dedup by (vals,modi,code)).
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

# 3) Graft known-good encoders from the battle-tested sm_80 repos for keys the
#    corpus can't solve integrally. Same Ampere encoding; validated empirically
#    by validate_11.py byte-identity (interval's 20 QNAN FSELs re-encode exactly).
#    FSEL_R_R_FI_P goes non-integral here because nvdisasm's decimal float
#    prints don't all round-trip to the same bits, poisoning the linear solve.
#    (HFMA2_R_R_R_FI_FI is equally non-integral in sm_80/sm_90 — known, unused.)
GRAFT = ["FSEL_R_R_FI_P"]
r80 = CuInsAssemblerRepos(arch="sm_80")
r80.setToDefaultInsAsmDict()
for key in GRAFT:
    if key in r80.m_InsAsmDict and getattr(r80.m_InsAsmDict[key], "m_PSolFac", None) == 1:
        asm = r80.m_InsAsmDict[key]
        asm.m_Arch = smv
        repos.m_InsAsmDict[key] = asm
        print(f"grafted {key} from sm_80 repos (integral encoder)")

print(f"\nsaving repos -> {OUT}")
repos.save2file(OUT)
print("saved. size:", os.path.getsize(OUT), "bytes")
