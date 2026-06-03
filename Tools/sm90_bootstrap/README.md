# sm_90 (Hopper / H100) bootstrap tooling

Regenerates `CuAsm/InsAsmRepos/DefaultInsAsmRepos.sm_90.txt` and validates the
sm_90 round-trip. The repo is already committed; these scripts let you rebuild it.

## How the sm_90 repo was built
1. Dump sm_90 SASS corpus from the CUDA libraries:
     cuobjdump -sass -arch sm_90 <lib.so> > corpus/<name>.sm90.sass
   Libraries used: curand, nvjpeg, nvjpeg2k, nvtiff, nppif, nppig, nppidei,
   nppist, nppicc (~4.0M instructions).
2. `bootstrap_sm90.py`: parse the corpus, dedup samples by (vals,modi,code),
   and robust-build each InsKey's encoder (`robust_build.py`, RANSAC-style:
   tolerant of relocated/placeholder outliers).

## Hopper-specific CuAssembler changes (this branch)
- CuInsFeeder.__switchArch: route major 9 -> 7x/8x state machine.
- CuInsParser: split the relative BRANCH offset into two scalar values
  (low 10 bits + 48-bit unsigned high) — Hopper bit-splits it across
  code[18:24) and code[34:82). This is THE key encoding change.
- CuInsAssembler.push: reject+revert samples that break integral solvability.
- CubinFile: inject `.sectioninfo @"SHI_REGISTERS=N"` (nvdisasm omits it on sm_90).
- CuAsmParser: classify data-symbol relocations as RELA when a `.rela<sec>`
  section exists (fixes .debug_frame); accept 3-arg `.size`; tolerate duplicate
  empty-named symbols.

## Validate
    python3 validate_14.py     # all 14 workload hot kernels, byte-compare .text
Result: 14/14 byte-identical sm_90 round-trip.

## Known non-integral keys (unused by the 14 workload kernels)
- BRX_R_II (indexed/jump-table branch), HFMA2_R_R_R_FI_FI (half-float dual-imm FMA).
  Would need their own field-split handling if a target kernel used them.
