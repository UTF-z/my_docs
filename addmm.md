#  CUDA AddMM算子解读 

## 原理

AddMM算子是在完成一个$\beta AB + \alpha C$的数学计算, 假设$A$的shape是$(M, K)$, $B$的shape是$(K, N)$, $C$的shape是$(M, N)$.

CUDA的这个算子实现了一个$M = N = K = 4096$的矩阵AddMM运算, $A$和$B$是half精度, $C$是float精度. 这个算子精心设计了数据搬运的模式, 充分利用了IO带宽. 此外还使用了wmma指令, 在tensor core上计算半精度矩阵乘法, 提高了计算效率. 接下来我们分析一下这个算子.

## 分块布局
一个Block中有256个线程, 由于cuda调度的基本单位是warp, 一个warp包含32个线程. 所以一个Block中包含8个warp.

一个Block用来计算一个$128 \times 128$的分块, 这个分块被细分成$8 \times 8$个tile, 一个tile是$16 \times 16$个数.

每个Block首先把一个$128 \times 128$的$C$加载进shared memory, 再转换成wmma的fragments, 然后从$A$, $B$的对应行, 列每次加载$128 \times 64$个块, 计算得到$128 \times 128$的结果累加到fragments上, 当$K$这个维度循环完毕之后就完成当前块的计算.

## 创建共享内存

```cpp
extern __shared__ half shmem[][CHUNK_K * K + SKEW_HALF]; // 4 * 16 + 16
```

这个共享内存用来存$A$和$B$每次累加计算时的大小为$128 \times 64$的矩阵分块. $K$是一个tile在$K$方向的维度, 这里是16, `CHUNK_K = 4`. 这里之所以要加16个额外的数是为了避免**bank conflict**. 

在Ampere架构上, shared memory有32个bank, 每个bank一次能传输4个字节.连续的四字节会映射到连续的bank上, 超过32个再循环回来. 

所以给一个字节地址`Addr`, 它映射到的bank序号为`Addr / 4 % 32`. 

如果两个线程访问不同的bank, 那么这两个共享内存的读取可以并行, 如果两个线程访问同一个bank但是不是同一个4字节, 那么这两个读取一定要被serialized, 这就叫做bank conflict. 

列访问的时候就容易发生bank conflict. 比如加载一个$128 \times 64$的half数组, 这里一行就有128个字节. 如果按列读取, 相邻元素相差128字节, 由于`128 / 4 % 32 == 0`, 所以`shmem[i][j]`和`shmem[i+1][j]`会被映射到同一个bank, 发生bank conflict, 即使是两个线程并行读取, 也会被线性化.

解决bank conflict的一个方法就是把数组的一行定义大一点, 这个方法叫做"skewing". 假设我们一行加入额外p个half, 那么`shmem[i][j]`和`shmem[i+1][j]`就相差$\frac{(128 + 2p)}{4} = 32 + \frac{p}{2}$个bank, 只要$p \in [2, 63]$就可以避免bank conflict.

还要考虑到后面我们需要从shmem中通过wmma读取数据进入fragment, 每一行都要按照wmma的要求进行256bits(32 Bytes)对齐, 所以我们要$2p | 32$. 综上一个最小的p就是16.

所以这里每一行有`4 \times 16 + 16`个half数据.

## 外层大循环: 确定Block范围
`block_pos`从`BlockIdx.x`开始, 每次跳跃`gridDim.x`.

每个thread根据当前的`block_pos`确定block范围.
```cpp
const unsigned int block_tile_i = ((block_pos * BLOCK_ROW_TILES) / N_TILES) * (BLOCK_COL_TILES); // 每256 增长 8
const unsigned int block_tile_j = (block_pos * BLOCK_ROW_TILES) % N_TILES; // 每次 增长 8
```

这里的`BLOCK_ROW_TILES`和`BLOCK_COL_TILES`都是8, 分别表示一个block的行方向和列方向有多少个tile.

## 加载C分块 
> 加载策略是, 每个warp加载一个16 * 128的横条. 八个warp恰好完成8 * 16 * 128的整个C的分片.

### C分块: Global Memory -> Shared Memory
对于一个warp, 它根据自己的warpId确认源数据指针
```cpp
const size_t gmem_idx =  (block_tile_i + warpId) * M * GLOBAL_MEM_STRIDE + block_tile_j * N;
const float *src_gmem_warp_stream_ptr = &C[gmem_idx]; 
```

再确定shmem中的目标指针
```cpp
float *shmem_warp_stream_ptr = (float *)&shmem[0][0] + warpId * SHMEM_STRIDE * K; // (0 ~ 8) * 128 * 16
```

接下来循环16次, 每次读取一行128个float, 共512个字节. 这一行是warp中的全部32个线程一次性读取的, 而且访问模式非常好:
- 首先充分利用了每个shmem的bank.
- 每个thread读取一个int4来coalescing全局内存的访存事务. (一个int4表示4个int, 共16个字节, 128bits).

具体而言, 每个thread根据自己的`laneId`来确定自己在当前行的位置, 然后负责一个int4的global->shmem的数据拷贝, 这样一个warp中的32个线程就可以拷贝32 * 4 * 4 = 512个字节, 刚好一行.

> 但是如果只有32个bank, 每个bank宽度为4字节, 那一次shmem访问只能获取128字节, 这里一行要向shmem传输4次. 但这里是从global memory拷贝, 这点shmem的开销不足为虑:

```cpp
for (int i = 0; i < K; i++) {
    typedef int4 copy_t; 
    *((copy_t *)(shmem_warp_stream_ptr + SHMEM_STRIDE * i) + laneId) = *((copy_t *)(src_gmem_warp_stream_ptr + GLOBAL_MEM_STRIDE * i) + laneId);
}
```
最后用一个`__syncthreads()`来同步所有warp, 这样整个128 * 128的C的分片就从Global Memory加载进shmem了.

### C分块: Shared Memory -> Register Memory

接下来我们用wmma的`load_matrix_sync`指令把shmem中的数据加载到每个thread的寄存器中. 在此之前我们先要弄清楚更细节的分块计算布局.

每个Block有256个thread, 这256个thread也可以叫做 cooperrative thread arrays, CTA. 每个CTA被分成8个warp. 这8个warp逻辑上被排布成$4 \times 2$的阵列, 然后每个warp负责$2 \times 4$个tile的计算.

一个tile就是一个$16 \times 16$的数组, 可以用tensor core一次性计算. 使用tensor core的方法就是用wmma指令.

wmma计算一个$16 \times 16$的tile的流程大致上分两步. 

首先, 声明一个`wmma::fragment<wmma::accumulator, M=16, N=16, K, float>`. 这表示, 这是一个float类型的$16 \times 16$的数组, 并且它的计算方式是, 每次完成一个$M=16 \times K$和$K \times N=16$矩阵的计算, 然后把它累加上去.

然后把这个tile的初值, 也就是C对应位置的一个tile, 加载进这个fragment. 这里要调用wmma的`load_matrix_sync`函数, 第一个参数是目标fragment的引用, 第二个是源数据的指针ptr, 第三个是源数据一行的stride, 要保证ptr + stride就跳到下一行. 第四个参数是一个layout enum, 这里设置为wmma::mem_row_major.

> 实际上, 一个fragment只是一个逻辑概念, 它并不存在于某个memory中, 而是分散在一个warp所有线程的register上面.

如前文所述, 每个warp处理$2\times 4$个tile, 所以每个warp声明了一个fragment数组:
```cpp
wmma::fragment<wmma::accumulator, M, N, K, float> c[WARP_COL_TILES][WARP_ROW_TILES];  // c[2][4]
```

然后把shmem中C的每个tile加载进入对应的fragment.

```cpp
#define SHMEM_OFFSET (N * WARP_ROW_TILES)  //shmem_offset 共享内存偏移 N * 4
float *shmem_warp_tile_ptr = (float *)&shmem[0][0] +
                            (warpId / 2) * SHMEM_STRIDE * K * 2 + 
                            (warpId % 2) * SHMEM_OFFSET; 
#pragma unroll
for (int i = 0; i < WARP_COL_TILES; i++) { 
#pragma unroll
    for (int j = 0; j < WARP_ROW_TILES; j++) {
    const float *tile_ptr =
        shmem_warp_tile_ptr + i * SHMEM_STRIDE * K + j * N;
    wmma::load_matrix_sync(c[i][j], tile_ptr, SHMEM_STRIDE, C_LAYOUT);
    }
}
```
> NOTE: 之前C的数据在shmem中是按照一行128个float排布的, 那么一行有512个字节. 由于`512 / 4 % 32 == 0`, 这里用`load_matrix_sync`加载tile的时候是会发生**bank conflict**的. 但是这里一个Block载入C的块只发生一次, 后面算AB要载入很多次(因为K维度很大), 所以只要后面不要bank conflict就好了.
---
**Shared Memory Limit**

载入$128 \times 128$的float矩阵, 共享内存占据$128 \times 128 \times 4 = 64(kB)$. 这里要注意一下, 因为Ampere显卡共享内存大小仅仅为48kB.

**Redundant or Spilling** ?
- 每个tile有256个float, 分配到一个warp中32个thread, 那么每个thread就有8个float. 
- 由于每个warp要处理8个tile, 所以每个thread就要处理64个float. 
- 4090设备(Ampere)上是32位寄存器, 所以这64个float就要占据64个寄存器.
- 一个block有256个thread, 一共要占据$64 \times 256 = 16384$个寄存器.
- 一块Ampere卡上有128个SM, 每个SM上有65536个32位寄存器. 最多容纳1536个线程.
- 从寄存器约束来看, 一个SM只能容纳$65536 / 16384 = 4$个Block; 从线程数来看, 只能容纳$1536 / 256 = 6$个Block. 那么这里的Occupancy就是4.
---

## 加载A和B

> 加载策略是, 搞一个K维度的大循环, 每次加载$128 \times 64$的$A$和$B$的分块. 计算这两个分块的乘积, 得到$128 \times 128$的结果, 累加到C上面去. 

### A和B: Global Memory -> Shared Memory

> 每个warp负责加载一个$2 \times 4$的tiles, 也就是$32 \times 64$的half数据. 四个warp加载$8 \times 4$的A块, 四个warp加载$8 \times 4$的B块, 全部加载到shmem中, 拼接成$16 \times 4$的布局, 上8个属于A, 下8个属于B.

> 和加载C一样, 每个warp中的thread负责加载一个int4. 

> 具体而言, 横向64个half一共128个字节, 一共8个int4. 所以warp里面32个thread可以一次性载入4行. 要载入32行就要循环8次.

首先设置源数据指针
```cpp
const half *warp_ptr = (warpId < 4) 
    ? (&A[block_tile_i * M * K_GLOBAL] + M * K_GLOBAL * (warpId % 4) * 2)
    : (&B[block_tile_j * N * K_GLOBAL] + N * K_GLOBAL * (warpId % 4) * 2);
int4 *lane_ptr = (int4 *)(warp_ptr + tile_k * K + (laneId / CHUNK_COPY_LINE_LANES) * K_GLOBAL) + (laneId % CHUNK_COPY_LINE_LANES);
```
其中`tile_k`是K这个维度上的循环变量, 每次+4. `CHUNK_COPY_LINE_LANES = 8`

然后设置共享内存中的目标位置并完成数据拷贝. 注意这里`shmem_idx`是行标.
```cpp
size_t shmem_idx =
    warpId < (WARPS_PER_BLOCK / 2)
        ? (M * (warpId % (WARPS_PER_BLOCK / 2)) * 2)
        : (N * (warpId % (WARPS_PER_BLOCK / 2)) * 2 + shmem_idx_b_off);
shmem_idx += laneId / CHUNK_COPY_LINE_LANES;
#pragma unroll
for (int i = 0; i < ((WARP_SIZE / 2) / CHUNK_COPY_LINES_PER_WARP) * 2; i++) { // 这里有 8 个循环
    *((int4 *)&shmem[shmem_idx][0] + (laneId % CHUNK_COPY_LINE_LANES)) =
        *lane_ptr;
    // 源指针下移4行
    lane_ptr = (int4 *)((half *)lane_ptr + K_GLOBAL * CHUNK_COPY_LINES_PER_WARP);
    // 目标指针下移4行
    shmem_idx += CHUNK_COPY_LINES_PER_WARP; // shmem_idx += 4;
}
__syncthreads();
```

这里四行四行地加载, 还是有bank conflict的, 但是因为是从global加载, 这里有conflict也无所谓. 而且避免不了了, 毕竟一行就要占据所有的banks.

### A和B: Shared Memory -> Register + mmAdd

接下来从shmem中载入数据, 完成矩阵乘法, 并累加进入C的fragments中. 我们来看看分块策略.

> 由于K方向有4个tile, 于是循环四次来做, 每次完成一个`(8 * 16, 1 * 16) @ (1 * 16 * 8 * 16) -> (8 * 16, 8 * 16)`的矩阵运算并累加到C中.

> 由于一个Warp负责一个`(2 * 16, 4 * 16)`的分块计算, 所以现在一个Warp加载一个`(2 * 16, 1 * 16)`的A(2个tileA), 一个`(1 * 16, 4 * 16)`的B(4个tileB), 把这8个tileRes算好, 完成累加.

首先声明两个tileA以及四个tileB, 注意这里的B设定了`wmma::col_major`, 因此B的fragments都是转置载入的. (B在上层的存储不需要转置)

```cpp
wmma::fragment<wmma::matrix_a, M, N, K, half, wmma::row_major> a[WARP_COL_TILES];
wmma::fragment<wmma::matrix_b, M, N, K, half, wmma::col_major> b[WARP_ROW_TILES];
```

接下来在这$(2, 4)$的tile块上一个一个计算并累加进入C, 首先循环2这个维度, 拿到当前这个Warp对应`k_step = 0 ... 3`的那个tile, 载入当前的fragmentA. 注意

```cpp
#pragma unroll
for (int i = 0; i < WARP_COL_TILES; i++) {
    size_t shmem_idx_a = (warpId / 2) * M * 2 + (i * M);
    const half *tile_ptr = &shmem[shmem_idx_a][k_step * K];
    wmma::load_matrix_sync(a[i], tile_ptr, K * CHUNK_K + SKEW_HALF);  
```

当前这个A的tile要和四个B的tile相乘, 加到对应位置的C上去. 所以再循环4这个维度. 载入之后直接把wmma的mma给做掉.

```cpp
#pragma unroll
for (int j = 0; j < WARP_ROW_TILES; j++) { // 4
    if (i == 0) {
        size_t shmem_idx_b = shmem_idx_b_off + (WARP_ROW_TILES * N) * (warpId % 2) + (j * N);
        const half *tile_ptr = &shmem[shmem_idx_b][k_step * K];
        wmma::load_matrix_sync(b[j], tile_ptr, K * CHUNK_K + SKEW_HALF);
    }
    wmma::mma_sync(c[i][j], a[i], b[j], c[i][j]);
}
```

> 之前说的shmem每一行专门加一个skewing就是在上面这里发挥作用的. 由于`shmem`一行有80个half, 一共160字节, 那么同一列上下相邻元素相差`160 / 4 % 32 = 8`个bank. 同时, 16个half共32字节, 刚好8个bank. 所以32个bank就可以一次性传输4行而不发生bank conflict. 四次shmem访问就可以完成一个tile的搬运.

在K这个维度上每做4个tile, 就要同步一次, 以进行下一次global -> shmem的载入.

## 把结果从fragmentst写回Shared Memory

每个Warp负责自己那一块$2 \times 4$tile区域的写回
```cpp
#pragma unroll
for (int i = 0; i < WARP_COL_TILES; i++) {
#pragma unroll
    for (int j = 0; j < WARP_ROW_TILES; j++) {
#pragma unroll
        for (int t = 0; t < c[i][j].num_elements; t++) c[i][j].x[t] *= alpha;
        float *tile_ptr = shmem_warp_tile_ptr + i * SHMEM_STRIDE * K + j * N;  // shmem_warp_tile_ptr + (0 ~ 2) * 8 * 16 * 16 + (0 ~ 4) * 16
        wmma::store_matrix_sync(tile_ptr, c[i][j], SHMEM_STRIDE, C_LAYOUT); // 步长 8 * 16
    }
}
```

## 把结果从Shared Memory写回Global Memory
和从Global Memory载入C操作一样, 这次逆过去.
```cpp
float *dst_gmem_warp_stream_ptr = &D[gmem_idx];
#pragma unroll
for (int i = 0; i < K; i++) {
    *((int4 *)(dst_gmem_warp_stream_ptr + GLOBAL_MEM_STRIDE * i) + laneId) =
        *((int4 *)(shmem_warp_stream_ptr + SHMEM_STRIDE * i) + laneId);
}
__syncthreads();
```

## 完整代码
```cpp
#include <assert.h>
#include <cuda.h>
#include <mma.h>
#include <stdio.h>
#ifndef CPU_DEBUG
// Set this to 1 to verify the correctness of the GPU-computed matrix.
#define CPU_DEBUG 0
#endif

#ifndef SHARED_MEMORY_LIMIT_64K
// Set this to 0 to use more than 64 Kb of shared memory to cache data, to
// improve the performance of the computations on GPU.
// Note that you need a GPU that can have more than 64 Kb of shared memory
// per multiprocessor.
#define SHARED_MEMORY_LIMIT_64K 1
#endif
#define WARP_SIZE 32
#define M 16
#define N 16
#define K 16
#define WMMA_M 16
#define WMMA_N 16
#define WMMA_K 16
#define M_TILES 256
#define N_TILES 256
#define K_TILES 256
#define M_GLOBAL (M * M_TILES) // 4096
#define N_GLOBAL (N * N_TILES) // 4096
#define K_GLOBAL (K * K_TILES)
#define C_LAYOUT wmma::mem_row_major
#define WARPS_PER_BLOCK 8
#define THREADS_PER_BLOCK (WARP_SIZE * WARPS_PER_BLOCK)
#if SHARED_MEMORY_LIMIT_64K
#define CHUNK_K 4
#else
#define CHUNK_K 8
#endif
#define CHUNK_LINE_BYTES (CHUNK_K * K * sizeof(half)) // 每个 chunk 数据占 4 * 16 * 2 = 8 * 16
#define WARP_COPY_BYTES (WARP_SIZE * sizeof(int4))    // 32 * 16
#define CHUNK_COPY_LINES_PER_WARP (WARP_COPY_BYTES / CHUNK_LINE_BYTES) // 32 * 16 / （8 * 16） = 4
#define CHUNK_COPY_LINE_LANES (WARP_SIZE / CHUNK_COPY_LINES_PER_WARP) // 32 / 4 = 8
#define BLOCK_ROW_WARPS 2
#define BLOCK_COL_WARPS 4
#define WARP_ROW_TILES 4
#define WARP_COL_TILES 2
#define BLOCK_ROW_TILES (WARP_ROW_TILES * BLOCK_ROW_WARPS) // 8
#define BLOCK_COL_TILES (WARP_COL_TILES * BLOCK_COL_WARPS) // 8
#define GLOBAL_MEM_STRIDE N_GLOBAL
#define SHMEM_STRIDE (N * BLOCK_ROW_TILES) //shmem_stride 共享内存步长 N * 8
#define SHMEM_OFFSET (N * WARP_ROW_TILES)  //shmem_offset 共享内存偏移 N * 4
#define SKEW_HALF 16  //偏移量 防止bank conflictsusing namespace nvcuda;

__global__ void compute_gemm(const half *A, const half *B, const float *C,
                             float *D, float alpha, float beta) {
  extern __shared__ half shmem[][CHUNK_K * K + SKEW_HALF]; // 4 * 16 + 16
  const unsigned int warpId = threadIdxkx / WARP_SIZE; // 0 ~ 8
  const unsigned int laneId = threadIdx.x % WARP_SIZE; // 0 ~ 32
  const size_t shmem_idx_b_off = BLOCK_COL_TILES * M; // 8 * 16
  float *shmem_warp_tile_ptr = (float *)&shmem[0][0] +
                               (warpId / 2) * SHMEM_STRIDE * K * 2 + 
                               (warpId % 2) * SHMEM_OFFSET; 
  float *shmem_warp_stream_ptr =
      (float *)&shmem[0][0] + warpId * SHMEM_STRIDE * K; // (0 ~ 8) * 8 * 16 * 16
  beta /= alpha;
  for (unsigned int block_pos = blockIdx.x;; block_pos += gridDim.x) {
    const unsigned int block_tile_i =
        ((block_pos * BLOCK_ROW_TILES) / N_TILES) * (BLOCK_COL_TILES); // 每256 增长 8
    const unsigned int block_tile_j = (block_pos * BLOCK_COL_TILES) % N_TILES; // 每次 增长 8
    // Stop when there are no more D matrix tiles to compute in this CTA.
    if (block_tile_i >= M_TILES) {  // 如果多于 256 个块，就处理完了
      break;
    }
    const size_t gmem_idx =  // (i + warpId) * 16 * 4096 + j * 16
        (block_tile_i + warpId) * M * GLOBAL_MEM_STRIDE + block_tile_j * N;
    const float *src_gmem_warp_stream_ptr = &C[gmem_idx]; //取得C矩阵中该小块的全局内存地址
#pragma unroll                  //循环 16 次 
    for (int i = 0; i < K; i++) { //每次8个warp， 一个warp一次一行，每行负责读取 8 * 16 个 float，8 * 16 * 4字节 
      typedef int4 copy_t; // sizeof(int4) = 16 , 所以下面读入 ： 16  * 32  = 8 * 16 * 4 字节
      
      *((copy_t *)(shmem_warp_stream_ptr + SHMEM_STRIDE * i) + laneId) =
          *((copy_t *)(src_gmem_warp_stream_ptr + GLOBAL_MEM_STRIDE * i) +
            laneId);
    }
    __syncthreads();
    wmma::fragment<wmma::accumulator, M, N, K, float> c[WARP_COL_TILES]
                                                       [WARP_ROW_TILES];  // c[2][4]
#pragma unroll
    for (int i = 0; i < WARP_COL_TILES; i++) { // 0 ~ 2 这里加载下一个 8 * 16 * 16 的数据
#pragma unroll
      for (int j = 0; j < WARP_ROW_TILES; j++) { // 0 ~ 4 
        const float *tile_ptr =// i *     8 * 16   *16 + j * 16 
            shmem_warp_tile_ptr + i * SHMEM_STRIDE * K + j * N;
        // 这个地方，按照道理来讲，会有bank conflicts 吧，共享内存偏移，只是给 A B的加载用的，现在是加载C
        wmma::load_matrix_sync(c[i][j], tile_ptr, SHMEM_STRIDE, C_LAYOUT);
      }
    }
    __syncthreads();
#pragma unroll
    for (int i = 0; i < WARP_COL_TILES; i++) {
#pragma unroll
      for (int j = 0; j < WARP_ROW_TILES; j++) {
#pragma unroll
        for (int t = 0; t < c[i][j].num_elements; t++) {
          c[i][j].x[t] *= beta;
        }
      }
    }
    const half *warp_ptr = (warpId < 4) ? (&A[block_tile_i * M * K_GLOBAL] +
                                           M * K_GLOBAL * (warpId % 4) * 2)
                                        : (&B[block_tile_j * N * K_GLOBAL] +
                                           N * K_GLOBAL * (warpId % 4) * 2);
#pragma unroll
    for (int tile_k = 0; tile_k < K_TILES; tile_k += CHUNK_K) { //tile_k: 0 4 8 12 ... 252
      size_t shmem_idx =
          warpId < (WARPS_PER_BLOCK / 2)
              ? (M * (warpId % (WARPS_PER_BLOCK / 2)) * 2) // load A 
              : (N * (warpId % (WARPS_PER_BLOCK / 2)) * 2 + shmem_idx_b_off);  //load B
      int4 *lane_ptr = (int4 *)(warp_ptr + tile_k * K +
                                (laneId / CHUNK_COPY_LINE_LANES) * K_GLOBAL) +
                       (laneId % CHUNK_COPY_LINE_LANES);
      shmem_idx += laneId / CHUNK_COPY_LINE_LANES;
#pragma unroll
      for (int i = 0; i < ((WARP_SIZE / 2) / CHUNK_COPY_LINES_PER_WARP) * 2;  // ((32/2)/4)*2 = 8
           i++) { // 这里有 8 个循环
        *((int4 *)&shmem[shmem_idx][0] + (laneId % CHUNK_COPY_LINE_LANES)) =
            *lane_ptr;
        lane_ptr =  // 偏移到下一个 4 行，循环 8 次， 那么一个 warp 读入 8 * 4 = 32 行，即 一个warp 处理 2 * 16行的数据  
            (int4 *)((half *)lane_ptr + K_GLOBAL * CHUNK_COPY_LINES_PER_WARP); // lane_ptr + 4 * 4096 half
        shmem_idx += CHUNK_COPY_LINES_PER_WARP; // shmem_idx += 4;
      }
      __syncthreads();
#pragma unroll
      for (int k_step = 0; k_step < CHUNK_K; k_step++) { // 4
        wmma::fragment<wmma::matrix_a, M, N, K, half, wmma::row_major>
            a[WARP_COL_TILES]; // a[2] // 每个 warp 都有一个 ，所以有 2 * 4 (A的warp) = 8 个
        wmma::fragment<wmma::matrix_b, M, N, K, half, wmma::col_major>
            b[WARP_ROW_TILES]; // b[4]
#pragma unroll
        for (int i = 0; i < WARP_COL_TILES; i++) { // 2            // 遍历 A 的 8 这个维度 
          size_t shmem_idx_a = (warpId / 2) * M * 2 + (i * M);     // shmem_idx_a = (warpId / 2) * 16 * 2 + (i * 16)
          const half *tile_ptr = &shmem[shmem_idx_a][k_step * K];  // 取得 A 的 (8 * 16) * (4 * 16) 中的某一个 (16 * 16)
          wmma::load_matrix_sync(a[i], tile_ptr, K * CHUNK_K + SKEW_HALF);  
#pragma unroll
          for (int j = 0; j < WARP_ROW_TILES; j++) { // 4
            if (i == 0) {
              size_t shmem_idx_b = shmem_idx_b_off +  // 遍历 B 的 8 这个维度 
                                   (WARP_ROW_TILES * N) * (warpId % 2) +  // （4 * 16） * （0 , 1） + (j * 16)
                                   (j * N);
              const half *tile_ptr = &shmem[shmem_idx_b][k_step * K];
              wmma::load_matrix_sync(b[j], tile_ptr, K * CHUNK_K + SKEW_HALF); // 加载 A 的 某个 16 * 16  
            }

            wmma::mma_sync(c[i][j], a[i], b[j], c[i][j]); // 大功告成 
          }
        }
      }
      __syncthreads();
    }
#pragma unroll
    for (int i = 0; i < WARP_COL_TILES; i++) {
#pragma unroll
      for (int j = 0; j < WARP_ROW_TILES; j++) {
#pragma unroll
        for (int t = 0; t < c[i][j].num_elements; t++) c[i][j].x[t] *= alpha;
        float *tile_ptr = shmem_warp_tile_ptr + i * SHMEM_STRIDE * K + j * N;  // shmem_warp_tile_ptr + (0 ~ 2) * 8 * 16 * 16 + (0 ~ 4) * 16
        wmma::store_matrix_sync(tile_ptr, c[i][j], SHMEM_STRIDE, C_LAYOUT); // 步长 8 * 16
      }
    }
    __syncthreads();
    float *dst_gmem_warp_stream_ptr = &D[gmem_idx];
#pragma unroll
    for (int i = 0; i < K; i++) {
      *((int4 *)(dst_gmem_warp_stream_ptr + GLOBAL_MEM_STRIDE * i) + laneId) =
          *((int4 *)(shmem_warp_stream_ptr + SHMEM_STRIDE * i) + laneId);
    }
    __syncthreads();
  }
}
```