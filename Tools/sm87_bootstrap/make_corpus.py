#!/usr/bin/env python3
"""Generate the sm_87 bootstrap corpus: for every extracted sm_87 cubin,
apply CuAssembler's desc-hack (fixCubinDesc) and dump `cuobjdump -sass` text.

This is the ONLY corpus format that works for repos learning on sm_8x:
- `cuobjdump -sass` on the raw .so omits the descriptor operand
  (`LDG.E.64 R8, [R6.64]`) while bin2asm/asm2bin work in desc-hacked form
  (`LDG.E.64 R8, desc[UR4][R8.64]`, key LDG_R_dARI) -> wrong keys learned.
- dsass output has the right operands but DROPS the second 64-bit code word
  (codeonly_line_mode='none'), so encodings can't be learned from it.
Desc-hacked cubin + cuobjdump -sass gives both: desc operand forms AND full
128-bit codes in the 2-line format CuInsFeeder parses natively.

Usage: python3 make_corpus.py <extract_dir> <corpus_out_dir>
  extract_dir: tree of *.sm_87.cubin (from `cuobjdump --extract-elf all` on the
               L4T container's CUDA libs — see bootstrap_sm87.py docstring)
Requires cuobjdump on PATH. Set TMPDIR somewhere roomy (desc-hack temp cubins).
"""
import os, sys, subprocess
from pathlib import Path
from multiprocessing import Pool

CUASM = "/net/netscratch/hpu8/sass_llm_loop/external/CuAssembler"
sys.path.insert(0, CUASM)
from CuAsm.utils.CubinUtils import fixCubinDesc
from CuAsm.common import getTempFileName
from CuAsm.CuAsmLogger import CuAsmLogger
CuAsmLogger.initLogger(log_file=None, stdout_level=60)


def one(args):
    cubin, out = args
    try:
        tmp = getTempFileName(suffix='cubin')
        hacked = fixCubinDesc(str(cubin), tmp)
        src = tmp if hacked else str(cubin)
        sass = subprocess.check_output(["cuobjdump", "-sass", src], timeout=900)
        if hacked:
            os.unlink(tmp)
        if sass.count(b"\n") < 10:          # kernel-less stub cubin — skip
            return f"skip  {cubin.name} (no SASS)"
        Path(out).write_bytes(sass)
        return f"ok    {cubin.name} -> {Path(out).name}{' (desc-hacked)' if hacked else ''}"
    except Exception as e:
        return f"FAIL  {cubin.name}: {e}"


def main():
    extract, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for cubin in sorted(extract.rglob("*.sm_87.cubin")):
        lib = cubin.parent.name
        out = outdir / f"{lib}__{cubin.stem}.sm87.sass"
        if not out.exists():
            jobs.append((cubin, out))
    print(f"{len(jobs)} cubins to dump")
    with Pool(6) as p:
        for r in p.imap_unordered(one, jobs):
            if not r.startswith("ok"):
                print(r)
    n = len(list(outdir.glob("*.sm87.sass")))
    print(f"== corpus: {n} files in {outdir}")


if __name__ == "__main__":
    main()
