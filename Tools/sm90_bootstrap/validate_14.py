#!/usr/bin/env python3
"""Definitive objective check: for each of the 14 distinct workload hot kernels,
locate its sm_90 cubin (searching all extracted cubins per library), round-trip,
and byte-compare that kernel's .text section."""
import sys, os, subprocess, glob, json, tempfile
sys.path.insert(0,"/net/netscratch/hpu8/sm90_port/work")
from roundtrip_check import sections
LOOP="/net/netscratch/hpu8/sass_llm_loop"; CUDA=f"{LOOP}/external/cuda-12.6"
os.environ["CUDA_HOME"]=CUDA; CUASM=f"{LOOP}/tools/cuasm"; W="/net/netscratch/hpu8/sm90_port"
L=f"{CUDA}/targets/x86_64-linux/lib"

# pull the 14 distinct >10% kernels from manifests, map to candidate libs
libs = {
 "curand": glob.glob(f"{L}/libcurand.so.10.*")[0],
 "nvjpeg": glob.glob(f"{L}/libnvjpeg.so.12.*")[0],
 "nvjpeg2k": f"{LOOP}/workload/nvjpeg2k/lib/libnvjpeg2k.so.0",
 "nvtiff": f"{LOOP}/workload/nvtiff/lib/libnvtiff.so.0",
 "nppif": glob.glob(f"{L}/libnppif.so.12.*")[0],
 "nppig": glob.glob(f"{L}/libnppig.so.12.*")[0],
}
def extract(libname):
    od=f"{W}/ex_{libname}"; os.makedirs(od,exist_ok=True)
    if not glob.glob(f"{od}/*sm_90*.cubin"):
        subprocess.run([f"{CUDA}/bin/cuobjdump","-xelf","all",libs[libname]],cwd=od,capture_output=True)
    return sorted(glob.glob(f"{od}/*sm_90*.cubin"))
# all sm_90 cubins across all libs
ALLCUBS=[]
for ln in libs: ALLCUBS += [(ln,c) for c in extract(ln)]

kernels=[]
for m in sorted(glob.glob(f"{LOOP}/workload/*/samples/*/manifest.json")):
    d=json.load(open(m))
    for k in d.get("kernels_fired",[]):
        if k.get("share",0)>0.10 and k["mangled"] not in [x[0] for x in kernels]:
            kernels.append((k["mangled"], k["share"]))

# cache: cubin -> roundtripped sections (round-trip each cubin at most once)
rt_cache={}
def get_rt(cub):
    if cub in rt_cache: return rt_cache[cub]
    d=tempfile.mkdtemp(); asm,rt=d+"/k.cuasm",d+"/k.cubin"
    r1=subprocess.run([CUASM,cub,"-o",asm,"--bin2asm"],capture_output=True,text=True)
    if r1.returncode: rt_cache[cub]=("bin2asm_fail",None); return rt_cache[cub]
    r2=subprocess.run([CUASM,asm,"-o",rt,"--asm2bin","--preserve-desc-from",cub],capture_output=True,text=True)
    if r2.returncode: rt_cache[cub]=("asm2bin_fail",(r2.stderr or r2.stdout)); return rt_cache[cub]
    rt_cache[cub]=("ok",(sections(cub),sections(rt))); return rt_cache[cub]

def find_and_check(mangled):
    short=".text."+mangled
    for ln,cub in ALLCUBS:
        names=subprocess.run([f"{CUDA}/bin/cuobjdump","-elf",cub],capture_output=True,text=True).stdout
        if (".text."+mangled) in names:
            st,data=get_rt(cub)
            if st!="ok": return f"{st} ({ln})", None
            a,b=data
            sec=".text."+mangled
            if sec not in a: return "section-name-mismatch", ln
            ok = sec in b and a[sec]==b[sec]
            return ("PASS" if ok else "DIFF"), ln
    return "NOT-FOUND", None

npass=0
for mangled, share in kernels:
    v,ln = find_and_check(mangled)
    if v=="PASS": npass+=1
    print(f"[{v:14}] {share*100:5.1f}%  {ln or '?':8}  {mangled[:58]}")
print(f"\n=== {npass}/{len(kernels)} distinct workload kernels byte-identical sm_90 round-trip ===")
