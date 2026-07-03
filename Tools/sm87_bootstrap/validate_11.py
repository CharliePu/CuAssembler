#!/usr/bin/env python3
"""Validate the sm_87 repos: byte-identical .text round-trip for all 11 Jetson
workload kernels + static-patch feasibility (cubin embedded uncompressed exactly
once in bin_sm87). Mirrors ../sm90_bootstrap/validate_14.py.

Run from the sass_llm_loop repo root (needs tools/cuasm + staged sm_87 workload):
    python3 external/CuAssembler/Tools/sm87_bootstrap/validate_11.py
.text-only comparison is the correct gate: the loop's compose() splices .text
sections into the ORIGINAL baseline cubin, so non-.text listing quirks never
reach a measured binary.
"""
import sys, subprocess, tempfile
from pathlib import Path

LOOP = Path("/net/netscratch/hpu8/sass_llm_loop")
sys.path.insert(0, str(LOOP / "tools"))
from _runlib import sections

CUBINS = LOOP / "workload/cubins/sm_87"
ok = fail = 0
for cub in sorted(CUBINS.glob("cs_*.cubin")):
    name = cub.stem[3:]
    asm = tempfile.mktemp(suffix=".cuasm")
    out = tempfile.mktemp(suffix=".cubin")
    r1 = subprocess.run([str(LOOP/"tools/cuasm"), "--bin2asm", str(cub), "-o", asm],
                        capture_output=True, text=True, timeout=300)
    r2 = subprocess.run([str(LOOP/"tools/cuasm"), "--asm2bin", asm, "-o", out,
                         "--preserve-desc-from", str(cub)],
                        capture_output=True, text=True, timeout=300)
    status = []
    if r1.returncode or r2.returncode or not Path(out).exists():
        tail = (r2.stdout + r2.stderr).strip().splitlines()[-1:] or ["?"]
        status.append(f"ROUNDTRIP-FAIL({tail[0][:90]})")
    else:
        a, b = cub.read_bytes(), Path(out).read_bytes()
        sa, sb = sections(cub), sections(out)
        if set(sa) != set(sb):
            status.append("ROUNDTRIP-FAIL(section set)")
        else:
            bad = [s for s in sa
                   if a[sa[s][0]:sa[s][0]+sa[s][1]] != b[sb[s][0]:sb[s][0]+sb[s][1]]]
            status.append("roundtrip-OK" if not bad else f"ROUNDTRIP-DIFF{bad}")
    for f in (asm, out):
        Path(f).unlink(missing_ok=True)
    binp = LOOP / f"workload/cuda-samples/samples/{name}/bin_sm87"
    if not binp.exists():
        status.append("NO-BIN")
    else:
        n = binp.read_bytes().count(cub.read_bytes())
        status.append(f"embed x{n} " + ("OK" if n == 1 else "BAD"))
    line_ok = "roundtrip-OK" in status and "embed x1 OK" in status
    ok, fail = ok + line_ok, fail + (not line_ok)
    print(f"{name:24} {' | '.join(status)}")
print(f"== {ok} ok, {fail} fail ==")
sys.exit(1 if fail else 0)
