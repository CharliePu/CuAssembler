extern "C" __global__ void compute(unsigned* out, const unsigned* in, int n){
    int t = blockIdx.x*blockDim.x + threadIdx.x;
    unsigned acc = in[t];
    for (int i=0;i<n;i++){               // data loop -> BRA
        acc = acc*1664525u + 1013904223u;
        if (acc & 1u) acc ^= in[(acc>>3)%256];   // branch -> conditional BRA
    }
    out[t] = acc;
}
