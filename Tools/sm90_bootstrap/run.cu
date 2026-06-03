#include <cuda.h>
#include <cstdio>
#include <cstdlib>
#define CK(x) do{CUresult r=(x); if(r!=CUDA_SUCCESS){const char*s;cuGetErrorString(r,&s);printf("ERR %s @%d: %s\n",#x,__LINE__,s);exit(1);} }while(0)
int main(int argc,char**argv){
    const int N=256;
    CK(cuInit(0)); CUdevice d; CK(cuDeviceGet(&d,0)); CUcontext c; CK(cuCtxCreate(&c,0,d));
    CUmodule m; CK(cuModuleLoadData(&m, [](const char*p){FILE*f=fopen(p,"rb");fseek(f,0,SEEK_END);long s=ftell(f);fseek(f,0,SEEK_SET);char*b=(char*)malloc(s+1);fread(b,1,s,f);fclose(f);return b;}(argv[1])));
    CUfunction fn; CK(cuModuleGetFunction(&fn,m,"compute"));
    unsigned *din,*dout; CK(cuMemAlloc((CUdeviceptr*)&din,N*4)); CK(cuMemAlloc((CUdeviceptr*)&dout,N*4));
    unsigned hin[N]; for(int i=0;i<N;i++)hin[i]=i*2654435761u+1; CK(cuMemcpyHtoD((CUdeviceptr)din,hin,N*4));
    int n=1000; void*args[]={&dout,&din,&n};
    CK(cuLaunchKernel(fn,1,1,1, N,1,1, 0,0,args,0)); CK(cuCtxSynchronize());
    unsigned hout[N]; CK(cuMemcpyDtoH(hout,(CUdeviceptr)dout,N*4));
    unsigned long long sum=0; for(int i=0;i<N;i++) sum=sum*131+hout[i];
    printf("CHECKSUM %016llx\n", sum);
    return 0;
}
