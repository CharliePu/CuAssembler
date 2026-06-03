#!/usr/bin/env python3
"""Round-trip a cubin through cuasm (bin2asm -> asm2bin) and byte-compare sections.

Verdict is driven by the .text.* sections (the executable code = correctness).
Usage: roundtrip_check.py <cubin> [kernel_substr]
"""
import sys, os, subprocess, tempfile
from elftools.elf.elffile import ELFFile

LOOP = "/net/netscratch/hpu8/sass_llm_loop"
CUASM = os.path.join(LOOP, "tools/cuasm")
os.environ.setdefault("CUDA_HOME", os.path.join(LOOP, "external/cuda-12.6"))

def sections(path):
    with open(path, "rb") as f:
        elf = ELFFile(f)
        return {s.name: s.data() for s in elf.iter_sections()}

def main():
    cubin = sys.argv[1]
    kfilter = sys.argv[2] if len(sys.argv) > 2 else None
    d = tempfile.mkdtemp(prefix="rt_")
    asm = os.path.join(d, "k.cuasm"); rt = os.path.join(d, "k.rt.cubin")

    r1 = subprocess.run([CUASM, cubin, "-o", asm, "--bin2asm"], capture_output=True, text=True)
    if r1.returncode != 0:
        print("BIN2ASM FAILED:\n", r1.stderr[-1500:]); return 2
    r2 = subprocess.run([CUASM, asm, "-o", rt, "--asm2bin", "--preserve-desc-from", cubin],
                        capture_output=True, text=True)
    if r2.returncode != 0:
        # surface the first assembler error
        err = r2.stderr or r2.stdout
        print("ASM2BIN FAILED:\n", err[-2000:]); return 3

    a, b = sections(cubin), sections(rt)
    tnames = sorted(n for n in a if n.startswith(".text."))
    if kfilter:
        tnames = [n for n in tnames if kfilter in n]
    ident = diff = missing = 0
    diffs = []
    for n in tnames:
        if n not in b:
            missing += 1; diffs.append((n, "MISSING in round-trip")); continue
        if a[n] == b[n]:
            ident += 1
        else:
            diff += 1
            # first differing byte
            off = next((i for i in range(min(len(a[n]), len(b[n]))) if a[n][i] != b[n][i]), None)
            szmsg = "" if len(a[n]) == len(b[n]) else f" SIZE {len(a[n])}->{len(b[n])}"
            diffs.append((n, f"differ at byte {off}{szmsg}"))
    print(f"cubin: {os.path.basename(cubin)}")
    print(f".text sections compared: {len(tnames)}  | identical: {ident}  diff: {diff}  missing: {missing}")
    for n, msg in diffs[:25]:
        short = n.split(".text.")[-1][:60]
        print(f"  DIFF {short}: {msg}")
    verdict = "PASS (byte-identical .text)" if (diff == 0 and missing == 0 and tnames) else "FAIL"
    print("VERDICT:", verdict)
    return 0 if verdict.startswith("PASS") else 1

if __name__ == "__main__":
    sys.exit(main())
