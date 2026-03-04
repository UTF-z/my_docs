# MLLM+QNN梳理

##  MLLM 运行 QNN AoT 模型

在MLLM中，使用QNN作为后端跑大模型往往经历这么几个步骤：

1. 把模型进行量化和转换：
    ```python
    # 1) 在项目根目录，先装 pymllm（提供 mllm-convertor）
    cd ~/software/mllm
    uv pip install -e .

    # 2) 先做 Qwen3 量化，得到 model.safetensors
    cd pymllm/backends/qualcomm/transformers/qwen3
    python train.py \
    --model_path /path/to/Qwen3-1.7B \
    --max_length 1024 \
    --num_samples 128 \
    --output_dir /path/to/output

    # 3) 转成 .mllm
    cd ~/software/mllm
    mllm-convertor \
    --input_path /path/to/output/model.safetensors \
    --output_path /path/to/output/qwen3-1.7b.mllm \
    --model_name qwen3_1.7b \
    --verbose
    ```

2. 编译QNN AOT图编译器：

    ```cmake
    cmake -S /home/junming/software/mllm -G Ninja -B /home/junming/software/mllm/build-qnn-aot 
          -DCMAKE_BUILD_TYPE=RelWithDebInfo 
          -DHWY_ENABLE_TESTS=OFF 
          -DHWY_ENABLE_EXAMPLES=OFF 
          -DHWY_ENABLE_CONTRIB=OFF 
          -DMLLM_CPU_BACKEND_COMPILE_OPTIONS="-march=native" 
          -DMLLM_KERNEL_USE_THREADS=ON 
          -DMLLM_KERNEL_THREADS_VENDOR_OPENMP=ON 
          -DMLLM_KERNEL_USE_THREADS_VENDOR_MLLM=OFF 
          -DMLLM_QUALCOMM_QNN_AOT_ON_X86_ENABLE=ON
    
    cmake --build build-qnn-aot --target mllm-qwen3-aot-sha-c -j8
    ```

3. 用AOT图编译器进行编译，把mllm模型根据config，转成QNN的context.bin，可供QNN直接加载
   1. 首先设置aot-config:
        ```json
        {
            "target_machine": {
                "htp_arch": "V68", // =68
                "htp_chipset": "QCM6490", // =35
                "htp_try_best_performance": "HtpBurst", // 性能拉满
                "htp_security_pd_session": "HtpUnsignedPd", // 没有sign
                "htp_vtcm_capability_in_mb": 2 // 实测vtcm 容量
            },
            "graph_on_qnn": [
                "model"
            ],
            "op_on_qnn": [
                "lm_head"
            ],
            "split_graph": 1,
            "quant_recipe": {
                "llm_recipe": true,
                "layers": 28,
                "builtin_llm_pass": {
                    "model": "qwen3",
                    "lm_head": {
                        "fallback": {
                            "method": "LPBQ",
                            "sym": true,
                            "precision": "w4a16",
                            "block_size": 16
                        }
                    },
                    "linear": {
                        "fallback": {
                            "method": "LPBQ",
                            "sym": true,
                            "precision": "w4a16",
                            "block_size": 16
                        }
                    },
                    "kv_cache": {
                        "key": {
                            "method": "per-tensor",
                            "sym": true,
                            "precision": "w8a8"
                        },
                        "value": {
                            "method": "per-tensor",
                            "sym": true,
                            "precision": "w8a8"
                        }
                    }
                }
            }
        }
        ```
   2. 然后用aot编译器进行编译，形成context.bin
        ```bash
            ./build-qnn-aot/bin/mllm-qwen3-aot-sha-c \
            -m pymllm/backends/qualcomm/transformers/qwen3/mllm_model/qwen3-1.7b.mllm \
            -c ./examples/qwen3_qnn_aot/config_1.7B.json \
            --aot_config ./examples/qwen3_qnn_aot/qnn_aot_cfg_1.7B.json \
            --qnn_env_path "$QAIRT_SDK_ROOT/lib/x86_64-linux-clang/"
        ```

4. 交叉编译在target上面的runner，它负责加载模型、tokenize，启动qnn backend，加载context，执行计算图
   ```bash
    unset LD_LIBRARY_PATH
    source /home/junming/software/qcom-wayland_sdk/environment-setup-armv8-2a-qcom-linux #交叉编译工具链
    export QAIRT_SDK_ROOT=/home/junming/software/qairt/2.42.0.251225
    export PATH="$QAIRT_SDK_ROOT/.venv/bin:$PATH"

    cmake -S /home/junming/software/mllm \
    -B /home/junming/software/mllm/build-linux-oe-aarch64-qnn \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="/home/junming/software/qcom-wayland_sdk/tmp/sysroots/x86_64/usr/share/cmake/OEToolchainConfig.cmake" \
    -DMLLM_BUILD_ARM_BACKEND=ON \
    -DMLLM_BUILD_QNN_BACKEND=ON \
    -DHWY_ENABLE_TESTS=OFF \
    -DHWY_ENABLE_EXAMPLES=OFF \
    -DHWY_ENABLE_CONTRIB=OFF \
    -DMLLM_KERNEL_USE_THREADS=ON \
    -DMLLM_KERNEL_THREADS_VENDOR_OPENMP=ON \
    -DMLLM_KERNEL_USE_THREADS_VENDOR_MLLM=OFF \
    -DMLLM_CPU_BACKEND_COMPILE_OPTIONS="-march=armv8.2-a+fp16+fp16fml+dotprod+i8mm;-ffast-math"

    cmake --build /home/junming/software/mllm/build-linux-oe-aarch64-qnn \
    --target mllm-qwen3-aot-runner -j12
   ```

5. 把所有板子上要用的东西打包
    ```bash
    # 准备ship
    APP=deploy_qwen3_qnn
    mkdir -p $APP/{bin,lib,dsp,models}

    # runner + mllm so
    cp build-linux-oe-aarch64-qnn/bin/mllm-qwen3-aot-runner $APP/bin/
    cp build-linux-oe-aarch64-qnn/bin/libMllm*.so $APP/lib/

    # QNN aarch64 oe 侧 so（按你的 oe 工具链）
    QNN=/home/junming/software/qairt/2.42.0.251225
    cp $QNN/lib/aarch64-oe-linux-gcc11.2/libQnnHtp.so $APP/lib/
    cp $QNN/lib/aarch64-oe-linux-gcc11.2/libQnnSystem.so $APP/lib/
    cp $QNN/lib/aarch64-oe-linux-gcc11.2/libQnnHtpV68Stub.so $APP/lib/

    # DSP skel（unsigned + v68）
    cp $QNN/lib/hexagon-v68/unsigned/libQnnHtpV68Skel.so $APP/dsp/
    cp $QNN/lib/hexagon-v68/unsigned/libQnnSystem.so $APP/dsp/

    # 模型文件
    cp qwen3-1.7B-lpbq-sha.bin $APP/models/
    cp examples/qwen3_qnn_aot/config_1.7B.json $APP/models/
    cp /shared-cache/huggingface/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/tokenizer.json $APP/models/
    ```

6. 上传及运行
   ```bash
    #!/usr/bin/env bash
    set -euo pipefail

    APP_NAME="mllm-qwen3-aot-runner"
    REMOTE="root@localhost"
    PKG_DIR="./deploy_qwen3_qnn"          # 本地要传的一堆文件所在目录
    RDIR="/root/qwen3-aot/"            # 远程工作目录（随便）
    ENTRY="./bin/$APP_NAME -m ./models/qwen3-1.7B-lpbq-sha.bin -c ./models/config_1.7B.json -t ./models/tokenizer.json --ar_len 32"            # 远程要执行的命令
    PORT="2233"
    LOG_DIR="logs/qwen3_target_logs"
    PROMPT="${PROMPT:-}"

    if [[ -n "$PROMPT" ]]; then
    PROMPT_B64="$(printf '%s' "$PROMPT" | base64 -w0)"
    else
    PROMPT_B64=""
    fi

    mkdir -p "$LOG_DIR"

    ssh -p "$PORT" "$REMOTE" "mkdir -p '$RDIR'"
    rsync -az --delete --info=progress2 -e "ssh -p $PORT" "$PKG_DIR/" "$REMOTE:$RDIR/"

    # 2) 远程设置环境变量并执行：stdout+stderr 实时回显到本地
    #    用 bash -c 避免远端 profile 脚本在 set -u 下触发未定义变量错误
    ssh -p "$PORT" -tt "$REMOTE" "bash -c '
    set -euo pipefail
    cd \"$RDIR\"
    PROMPT_B64=\"$PROMPT_B64\"

    export LD_LIBRARY_PATH=\"$RDIR/lib:$RDIR/bin\"
    export DSP_LIBRARY_PATH=\"$RDIR/dsp;/usr/lib/rfsa/adsp;/usr/lib/dsp/cdsp;/usr/lib\"

    printf \"0x1f\n\" | tee /usr/lib/dsp/$APP_NAME.farf >/dev/null

    sep(){ echo; echo \"==================== \$1 ====================\"; }
    DSP_LOG=\$(mktemp \"/tmp/${APP_NAME}_dsp_XXXX.log\")

    setsid bash -c '\''
        journalctl -f -o cat --no-pager --since \"now\" \
        | grep --line-buffered -E \"adsprpc CDSP:\" \
        | sed -u \"s/^/[DSP] /\"
    '\'' >\"\$DSP_LOG\" 2>&1 &
    DSP_PGID=\$!

    cleanup() {
        kill -TERM -- \"-\$DSP_PGID\" >/dev/null 2>&1 || true
        sleep 0.2
        kill -KILL -- \"-\$DSP_PGID\" >/dev/null 2>&1 || true
        rm -f \"\$DSP_LOG\" >/dev/null 2>&1 || true
    }
    trap cleanup EXIT

    sep \"APP OUTPUT BEGIN\"
    chmod +x \"./bin/$APP_NAME\" || true
    set +e
    if [[ -n \"\$PROMPT_B64\" ]]; then
        {
        printf \"%s\" \"\$PROMPT_B64\" | base64 -d
        printf \"\n\"
        } | $ENTRY 2>&1 | sed -u \"s/^/[APP] /\"
    else
        $ENTRY 2>&1 | sed -u \"s/^/[APP] /\"
    fi
    app_rc=\${PIPESTATUS[0]}
    set -e
    sep \"APP OUTPUT END\"
    # 给 DSP 侧一点时间把尾巴日志刷出来
    sleep 1
    kill -TERM -- \"-\$DSP_PGID\" >/dev/null 2>&1 || true
    sleep 0.2
    kill -KILL -- \"-\$DSP_PGID\" >/dev/null 2>&1 || true
    sep \"DSP FARF BEGIN\"
    cat \"\$DSP_LOG\" || true
    sep \"DSP FARF END\"
    exit \"\$app_rc\"

    '" |& tee "$LOG_DIR/remote_run_$(date +%Y%m%d_%H%M%S).log"
    ```

## MLLM QNN 基础设施一览
### MLLM Context
context 负责维护线程池、内存管理器、各个后端的调度器，是推理引擎的单例全局入口

- 线程池：在 `session_threads_` 中维护 `system_tid` 到 `SessionTCB_ptr` 的映射；
- 内存管理器 `MemoryManager`：需往里注册具体后端的 `allocator`。使用时，根据 `Storage` 的设备调用 `allocator` 来分配/释放内存
    - `Allocator`: 虚基类，各个不同的后端继承它，实现alloca/free等方法
- 派发管理器 `DispatcherManager`：维护一个基于 `exec::static_thread_pool` 的 `thread_pool_`, 还在 `dispatchers_` 中维护多个对应不同后端的 `Dispatcher`.
    - `Dispatcher`: 虚基类，不同的后端继承它，基于 `DispatcherManager` 的 `thread_pool_` 构造，实现 `receive`、`process`、以及 `asyncReceive`等方法
- 后端列表 `backends_`：维护所有注册进来的，不同设备的 `backend`

### QNN Backend

Backend本身是各个计算平台的抽象，用于create出不同计算平台的算子，它是一个注册工厂的设计模式，初始化的时候使用 `regOpFactory` 来注册各个工厂，形成一个[opName -> opFactory]的映射。
可以调用 `createOp` 来根据opName找到对应的工厂并create算子，不同的后端（cuda，cpu，QNN）可以有单独的一套factories。每个Backend还有一个allocator实例，保存这个设备上的专用allocator。

QNN Backend 在构造的时候，会使用 `QNNAllocator`，这是使用QNN的 `rpcmem API` 进行内存管理的组件。 

此外，QNN Backend还注册有QNN各个算子的工厂，并且负责QNN runtime以及QNN图执行上下文的管理：

- `qnnHtpLibHandle_`: `dlopen("libQnnHtp.so")`出来的句柄
- `qnnSystemLibHandle_`: `dlopen("libQnnSystem.so")`出来的句柄
- `runtime_`: 整个QNN SDK的运行时，各种QNN层操作的入口
- `qnnModels_`: 这个Backend要运行的图集合

最后，它还包含一个 `QNNPerf` ，它通过QNN Interface里面的 `deviceGetInfrastructure` 拿到一个deviceInfra，然后拿到QNN perf管理的interface，之后通过它来设置各种设备性能。比如功耗模式、sleep latency等等，可参考Hexagon SDK的文档。

### QNN Runtime

每个QNN Backend有一个QNN Runtime实例 `runtime_`，可以通过它来调用QNN SDK中的各种方法。QNN 用法可以参考[QNN文档](https://docs.qualcomm.com/doc/80-63442-10/topic/api_overview.html)

`runtime_` 的构造过程如下：
1. 通过QNN的interfaceProvider拿到interface，之后都根据这个interface拿QNN 的 api进行调用(libQnnHtp.so里面就一个HTP的interface)
2.  interface.logCreate，创建日志
3. interface.backendCreate，创建QNN后端
4. interface.deviceCreate，创建QNN HPT device
5. interface.profileCreate，创建profile
6. 通过QNN的system Interface Provider拿到system interface，之后可以通过这个调用QNN system的API。

QNN runtime可以创建或者加载QNN context，这是QNN SDK中负责管理图执行的一个上下文。如果是AoT编译运行神经网络，MLLM会提前产生一个二进制的QNN context，然后runtime可以通过 `retrieveContext` 来从二进制文件恢复出QNN context用于QNN推理。

在 `retrieveContext` 中，runtime_会: 
1. 使用 `systemContextGetBinaryInfo` 来先读取二进制QNN context的元信息，包括图的个数，图的名字，每个图的输入输出向量个数，以及每个tensor的元数据（维度、形状、量化参数）。
2. 用 `contextCreateFromBinary`，在QNN的device和backend上创建该QNN Context，拿到QNN Context的句柄。
3. 最后用QNN context以及之前提取的context元信息来dump出一份图数据，构造出MLLM里面的QNNModel结构，保存在QNN Backend里面的 `qnnModels_`。每个QNNModel记录了QNN框架里面的的model句柄以及input/output Tensor的信息。

### QNNModel

`QNNModel` 是MLLM里面管理QNN Model的类，可以理解为对QNN Model的一层自定义封装。它主要包含QNN框架的interface入口、QNN backend句柄、计算图的句柄、图名、以及输入输出tensor的wrapper（`QNNTensorWrapper`）。在 `runtime_` 进行 `retrieveContext` 的时候，会先使用 `copyMetadataToGraphsInfo` 来把计算图元数据转储到MLLM自定义的图元数据结构 `GraphInfo_t` 中，然后使用再用QNN Interface的 `graphRetrieve`获取graph句柄，最后利用graph句柄、graph元数据，一张一张地使用 `initializeFromContext` 来构造 `QNNModel`.

`QNNModel`的 `initializeFromContext` 方法主要由这么几步构成：
1. 保存图名、图句柄
2. 加载图输入输出张量信息，设置input/output的tensorWrapper
3. 设置 `is_finalize` 状态。

### QNNTensorWrapper

MLLM里面使用QNNTensorWrapper来对QNN的tensor进行封装和管理。里面主要有一个QNN原生的 `qnnTensor_` 字段，一个 `name_`，和一个 `dimensions_` 字段。`QNNTensorWrapper` 还有一个 `Tensor` 类型的 `dataContainer_`, 用来存储张量的数据内容。 

在执行的时候，`QNNTensorWrapper` 可以调用alloc方法，它会让 `dataContainer_` 按照形状和dataType分配空间，底层是通过 `QNNAllocator` 调用 `rpcmem_alloc` 分配内存，然后通过 `registerQnnTensorToSharedBuffer` 往QNN框架里注册共享内存，获得句柄，然后把句柄绑定到 `qnnTensor_` 上。这样CPU端分配的内存NPU端就可以复用了。

MLLM实现 `QNNWrapper::alloc` 的时候，还考虑了缓存句柄的策略，同一个内存指针可以对应不同的mem句柄，这是由于图切换导致的，比如kv cache在prefill（s32）和decode（s1）之间切换。具体做法是用一个map，再次alloc时先找map，找到就复用，不再再注册。

### QNNDispatcher

这个结构维护了一个线程池，可以并发执行算子/图执行任务。它的异步并发功能使用了 `stdexec`，在CPU侧执行线程调度，最终会去执行 `process` 函数。在QNN后端，基本上都是做的图推理，这个 `process` 会调用 `Backend::graphExecute` 函数，在这里面完成运行时input/output张量的数据和Wrapper的绑定，和QNN HTP后端共享内存空间的注册（直接`_setContainer`+ `alloc`，后者发现已经有dataContainer的时候会直接执行注册）、以及通过 `qnnInterface` 调用 `graphExecute` API 完成图执行。

(思考：Hexagon SDK 中说，NPU后端有4个硬件线程，并且有RTOS负责NPU的线程调度。那边还有rpcQueue机制，这些是否可以用来优化现有流程？QNN 有 execution environment 选项可做 backend-allocated I/O（POPULATE_CLIENT_BUFS），或许也会有点作用，比如复用一块outputTensor)

## MLLM QNN Qwen3模型建模

### Qwen3 Tokenizer

Qwen3使用了经典的BPE分词器。它在模型仓库里定义了一个 `tokenizer.json`，包含 `model.vocab` 和 `model.merges`，前者是token到id的映射，后者是各种bigram的rank，rank越小词频越高。BPE分词是一种贪心的分词方式，首先寻找句子中rank最小的bigram，然后合并，再对合并后的句子继续贪心分词，直到无法合并或者只剩一个词元。

在实现上，`Qwen3Tokenizer`使用 `convertMessage` 方法，先提取special tokens，对其余的token用bpe进行分词，最后look up词表找到对应的id，形成input_ids返回。

### KV Cache

在MLLM里，KV cache的管理是通过 `KVCacheManager` 来实现的，这个结构包含了一个 `k_cache_` 和一个 `v_cache_`，它们都是 `std::vector<KVCache>`结构，每一层都对应一个 `KVCache`。这每一层的 `KVCache` 本质上是两个由 `Allocator` 分配的数组 `buffer` 和 `out_buffer`，字节数分别为 `max_cache_length * num_head * head_dim * sizeof T` 和 `max_ar_length * num_head * head_dim * sizeof T`。这两个buffer分别表示当前计算块前面的KV cache，以及当前计算块本身计算出的KV cache。`max_cache_length = context_length - min(prefill_chunk_size, decode_chunk_size)`.

在 `KVCacheManager` 初始化的时候，会按照config的层数确定KV cache个数，然后给每一层的KV cache分配空间。这个分配是通过Allocator完成的。__注意这里似乎并没有注册shared memory__，真正的register发生在run time。

### PromptProcessor

`PromptProcessor` 这个结构专门用来以chunk的方法做prefill，它里面保存了一个prefill的图名以及一个MLLM层自定义的 `nn::Module`。在AoT的时候，这个Module可以就当成一个图名的路由表，通过它的 `operator()`方法，可以调用到Dispatcher的 `submit`，最后调用到 `backend->executeGraph`，然后通过图名找出要执行的 `QNN Model`，拿出句柄，最后通过QNN Interface的 `graphExecute` 来执行。

`PromptProcessor` 在执行之前，会先调用 `init_io` 方法，这个方法会让他分配好所有输入输出向量的空间供运行时写入。这些向量分配好之后都保存在它的 `input_tensors_` 和 `output_tensors_` 里。 `init_io` 分为几个步骤：
1. `input_tensors`, 共有 `3 + num_layers * 2` 个：
    1. `input_ids`，形状为 `[1, ar_len]`，int32，kQNN，执行alloc。
    2. `position_ids`，形状为 `[ar_len]`，int32，kQNN，执行alloc。
    3. `attention_mask`，形状为 `[1, 1, ar_len, context_len]`，uint16, kQNN，执行alloc。
    4. `kv cache`，这里对每一层的kv都分别搞了一个empty tensor，数据类型由config决定，kQNN。对于K，形状为 `[1, num_heads, head_dims, context_len - ar_len]`，对于V，形状为 `[1, num_heads, context_len - ar_len, head_dims]`，但是没有再分配内存，直接复用了`KVCacheManager`初始化时给每一层`KVCache`分配的内存（`buffer`而不是`out_buffer`）。现在相当于一块 `buffer` 内存既有 `KVCacheManager` 里面的壳子，又有这里input_tensors的壳子。
2. `output_tensors`，共有 `1 + num_layers * 2` 个:
    1. `logits`，形状为 `[1, 1, ar_len, vocab_size]`，uint16, kQNN，执行alloc。
    2. `kv cache`，同input tensors的处理，不过这里每一层的K形状为 `[1, num_heads, head_dims, ar_len]`，V形状为 `[1, num_heads, ar_len, head_dims]`，并且绑定在之前对应层 `KVCache` 的 `output_buffer` 上.

这里K和V的形状转置一下是合理的，由 attention 公式：$O = softmax(\frac{QK^T}{\sqrt{d}})V$。这里将K转置过来有利于kernel高效按行读取内存。
   

## QNN API 表

基于 QAIRT 2.42.0.251225 头文件、QNN sample、MLLM 代码仓库整理。

## 统一调用流程

1. `dlopen("libQnnHtp.so")` / `dlopen("libQnnSystem.so")`
2. `dlsym(..., "QnnInterface_getProviders")` / `dlsym(..., "QnnSystemInterface_getProviders")`
3. 选 provider（通常按 API major 版本匹配）
4. 通过 `provider->QNN_INTERFACE_VER_NAME.xxx(...)` 或 `provider->QNN_SYSTEM_INTERFACE_VER_NAME.xxx(...)` 调用

参考：
- `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:724`
- `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:281`
- `mllm/backends/qnn/QNNUtils.cpp:24`
- `mllm/backends/qnn/QNNUtils.cpp:46`
- `mllm/backends/qnn/QNNBackend.cpp:291`
- `mllm/backends/qnn/QNNBackend.cpp:432`

## QnnInterface_getProviders
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:724`

```c
Qnn_ErrorHandle_t QnnInterface_getProviders(const QnnInterface_t*** providerList,
                                            uint32_t* numProviders);
```

作用：返回 `QnnInterface_t` provider 列表。

调用验证：
- `mllm/backends/qnn/QNNBackend.cpp:291`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/Utils/DynamicLoadUtil.cpp:55`

## QnnSystemInterface_getProviders
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:281`

```c
Qnn_ErrorHandle_t QnnSystemInterface_getProviders(const QnnSystemInterface_t*** providerList,
                                                  uint32_t* numProviders);
```

作用：返回 `QnnSystemInterface_t` provider 列表。

调用验证：
- `mllm/backends/qnn/QNNBackend.cpp:432`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/Utils/DynamicLoadUtil.cpp:140`

## 1. libQnnHtp：QnnInterface API

共 71 个 API，按 interface struct 字段顺序。

## propertyHasCapability
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:101`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProperty.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProperty.h:772:Qnn_ErrorHandle_t QnnProperty_hasCapability(QnnProperty_Key_t key);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProperty_HasCapabilityFn_t)(QnnProperty_Key_t key);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.propertyHasCapability(...)`（调用前判空）。

作用：
- 查询 capability 是否受支持。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:109:  if (runtime_->qnnInterface.propertyHasCapability(QNN_PROPERTY_TENSOR_SUPPORT_SPARSITY) == QNN_PROPERTY_SUPPORTED) {`
- `mllm/backends/qnn/QNNBackend.cpp:112:  if (runtime_->qnnInterface.propertyHasCapability(QNN_PROPERTY_TENSOR_SUPPORT_DYNAMIC_DIMENSIONS) == QNN_PROPERTY_SUPPORTED) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiGraph/src/QnnSampleApp.cpp:505:  if (m_qnnFunctionPointers.qnnInterface.propertyHasCapability(`

## backendCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:115`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:224:Qnn_ErrorHandle_t QnnBackend_create(Qnn_LogHandle_t logger,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_CreateFn_t)(Qnn_LogHandle_t logger,
                                                   const QnnBackend_Config_t** config,
                                                   Qnn_BackendHandle_t* backend);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendCreate(...)`（调用前判空）。

作用：
- 创建 backend 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:335:    if ((QNN_GET_ERROR_CODE(qnnInterface.backendCreate(logHandle, backendConfig, &backendHandle)) != QNN_SUCCESS)`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:388:  if (nullptr == m_qnnInterface.backendCreate) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:418:  Qnn_ErrorHandle_t errCode = m_qnnInterface.backendCreate(`

## backendSetConfig
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:120`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:247:Qnn_ErrorHandle_t QnnBackend_setConfig(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_SetConfigFn_t)(Qnn_BackendHandle_t backend,
                                                      const QnnBackend_Config_t** config);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendSetConfig(...)`（调用前判空）。

作用：
- 设置 backend 配置。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:2665:  if (nullptr == m_qnnInterface.backendSetConfig) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:2676:  Qnn_ErrorHandle_t err = m_qnnInterface.backendSetConfig(`

## backendGetApiVersion
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:124`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:264:Qnn_ErrorHandle_t QnnBackend_getApiVersion(Qnn_ApiVersion_t* pVersion);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_GetApiVersionFn_t)(Qnn_ApiVersion_t* pVersion);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendGetApiVersion(...)`（调用前判空）。

作用：
- 查询 backend API 版本。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## backendGetBuildId
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:127`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:281:Qnn_ErrorHandle_t QnnBackend_getBuildId(const char** id);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_GetBuildIdFn_t)(const char** id);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendGetBuildId(...)`（调用前判空）。

作用：
- 查询 backend build id。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:105:  if (QNN_SUCCESS != runtime_->qnnInterface.backendGetBuildId((const char**)&backendBuildId)) {`
- `mllm/backends/qnn/QNNBackend.hpp:82:    if (QNN_SUCCESS != qnnInterface.backendGetBuildId((const char**)&backendBuildId)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:69:      m_qnnFunctionPointers.qnnInterface.backendGetBuildId((const char**)&backendBuildId)) {`

## backendRegisterOpPackage
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:130`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:321:Qnn_ErrorHandle_t QnnBackend_registerOpPackage(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_RegisterOpPackageFn_t)(Qnn_BackendHandle_t backend,
                                                              const char* packagePath,
                                                              const char* interfaceProvider,
                                                              const char* target);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendRegisterOpPackage(...)`（调用前判空）。

作用：
- 注册自定义算子包。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:411:      if (!qnnInterface.backendRegisterOpPackage) {`
- `mllm/backends/qnn/QNNBackend.cpp:416:          != qnnInterface.backendRegisterOpPackage(backendHandle, pkg.path.c_str(), pkg.interfaceProvider.c_str(),`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:289:    if (nullptr == m_qnnFunctionPointers.qnnInterface.backendRegisterOpPackage) {`

## backendGetSupportedOperations
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:136`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:346:Qnn_ErrorHandle_t QnnBackend_getSupportedOperations(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_GetSupportedOperationsFn_t)(
    Qnn_BackendHandle_t backend,
    uint32_t* numOperations,
    const QnnBackend_OperationName_t** operations);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendGetSupportedOperations(...)`（调用前判空）。

作用：
- 查询 backend 支持的算子列表。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## backendValidateOpConfig
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:142`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:376:Qnn_ErrorHandle_t QnnBackend_validateOpConfig(Qnn_BackendHandle_t backend, Qnn_OpConfig_t opConfig);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_ValidateOpConfigFn_t)(Qnn_BackendHandle_t backend,
                                                             Qnn_OpConfig_t opConfig);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendValidateOpConfig(...)`（调用前判空）。

作用：
- 验证算子配置合法性。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## backendFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:146`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:423:Qnn_ErrorHandle_t QnnBackend_free(Qnn_BackendHandle_t backend);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_FreeFn_t)(Qnn_BackendHandle_t backend);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendFree(...)`（调用前判空）。

作用：
- 释放 backend 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:279:  CALL_QNN(qnnInterface.backendFree(backendHandle));`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:174:  if (m_isBackendInitialized && nullptr != m_qnnFunctionPointers.qnnInterface.backendFree) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:175:    if (QNN_BACKEND_NO_ERROR != m_qnnFunctionPointers.qnnInterface.backendFree(m_backendHandle)) {`

## contextCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:157`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:707:Qnn_ErrorHandle_t QnnContext_create(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_CreateFn_t)(Qnn_BackendHandle_t backend,
                                                   Qnn_DeviceHandle_t device,
                                                   const QnnContext_Config_t** config,
                                                   Qnn_ContextHandle_t* context);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextCreate(...)`（调用前判空）。

作用：
- 创建 context 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:468:      != qnnInterface.contextCreate(backendHandle, deviceHandle, (const QnnContext_Config_t**)&contextConfig, &context)) {`
- `mllm/backends/qnn/QNNBackend.cpp:538:      != qnnInterface.contextCreateFromBinary(backendHandle, deviceHandle, (const QnnContext_Config_t**)contextConfig,`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:557:      m_qnnInterface.contextCreate(m_backendHandle,`

## contextSetConfig
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:163`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:735:Qnn_ErrorHandle_t QnnContext_setConfig(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_SetConfigFn_t)(Qnn_ContextHandle_t context,
                                                      const QnnContext_Config_t** config);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextSetConfig(...)`（调用前判空）。

作用：
- 设置 context 配置。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:2696:  if (nullptr == m_qnnInterface.contextSetConfig) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:2707:    Qnn_ErrorHandle_t err = m_qnnInterface.contextSetConfig(`

## contextGetBinarySize
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:167`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:764:Qnn_ErrorHandle_t QnnContext_getBinarySize(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_GetBinarySizeFn_t)(
    Qnn_ContextHandle_t context, Qnn_ContextBinarySize_t* binaryBufferSize);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextGetBinarySize(...)`（调用前判空）。

作用：
- 查询 context binary 总大小。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:613:  runtime_->qnnInterface.contextGetBinarySize(context_, &binarySize);`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:375:  if (nullptr == m_qnnFunctionPointers.qnnInterface.contextGetBinarySize ||`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:382:      m_qnnFunctionPointers.qnnInterface.contextGetBinarySize(m_context, &requiredBufferSize)) {`

## contextGetBinary
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:171`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:800:Qnn_ErrorHandle_t QnnContext_getBinary(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_GetBinaryFn_t)(Qnn_ContextHandle_t context,
                                                      void* binaryBuffer,
                                                      Qnn_ContextBinarySize_t binaryBufferSize,
                                                      Qnn_ContextBinarySize_t* writtenBufferSize);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextGetBinary(...)`（调用前判空）。

作用：
- 导出 context binary。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:613:  runtime_->qnnInterface.contextGetBinarySize(context_, &binarySize);`
- `mllm/backends/qnn/QNNBackend.cpp:617:  runtime_->qnnInterface.contextGetBinary(context_, reinterpret_cast<void*>(binaryBuffer.get()), binarySize, &writtenSize);`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiGraph/src/QnnSampleApp.cpp:405:  if (nullptr == m_qnnFunctionPointers.qnnInterface.contextGetBinarySize ||`

## contextCreateFromBinary
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:177`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:897:Qnn_ErrorHandle_t QnnContext_createFromBinary(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_CreateFromBinaryFn_t)(
    Qnn_BackendHandle_t backend,
    Qnn_DeviceHandle_t device,
    const QnnContext_Config_t** config,
    const void* binaryBuffer,
    Qnn_ContextBinarySize_t binaryBufferSize,
    Qnn_ContextHandle_t* context,
    Qnn_ProfileHandle_t profile);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextCreateFromBinary(...)`（调用前判空）。

作用：
- 从 context binary 恢复 context。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:538:      != qnnInterface.contextCreateFromBinary(backendHandle, deviceHandle, (const QnnContext_Config_t**)contextConfig,`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:326:      nullptr == m_qnnFunctionPointers.qnnInterface.contextCreateFromBinary) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:332:      m_qnnFunctionPointers.qnnInterface.contextCreateFromBinary(`

## contextFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:187`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1505:Qnn_ErrorHandle_t QnnContext_free(Qnn_ContextHandle_t context, Qnn_ProfileHandle_t profile);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_FreeFn_t)(Qnn_ContextHandle_t context,
                                                 Qnn_ProfileHandle_t profile);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextFree(...)`（调用前判空）。

作用：
- 释放 context 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:151:  runtime_->qnnInterface.contextFree(context_, nullptr);`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:167:        m_qnnFunctionPointers.qnnInterface.contextFree(m_context, nullptr)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:254:      m_qnnFunctionPointers.qnnInterface.contextFree(m_context, m_profileBackendHandle)) {`

## graphCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:295`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:322:Qnn_ErrorHandle_t QnnGraph_create(Qnn_ContextHandle_t contextHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_CreateFn_t)(Qnn_ContextHandle_t contextHandle,
                                                 const char* graphName,
                                                 const QnnGraph_Config_t** config,
                                                 Qnn_GraphHandle_t* graphHandle);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphCreate(...)`（调用前判空）。

作用：
- 创建 graph。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## graphCreateSubgraph
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:301`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:361:Qnn_ErrorHandle_t QnnGraph_createSubgraph(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_CreateSubgraphFn_t)(Qnn_GraphHandle_t graphHandle,
                                                         const char* graphName,
                                                         Qnn_GraphHandle_t* subgraphHandle);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphCreateSubgraph(...)`（调用前判空）。

作用：
- 创建 subgraph。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## graphSetConfig
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:306`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:393:Qnn_ErrorHandle_t QnnGraph_setConfig(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_SetConfigFn_t)(Qnn_GraphHandle_t graphHandle,
                                                    const QnnGraph_Config_t** config);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphSetConfig(...)`（调用前判空）。

作用：
- 设置 graph 配置。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:140:  if (QNN_SUCCESS != m_qnnInterface.graphSetConfig(graphHandle, graphConfigsPointers.data())) {`

## graphAddNode
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:314`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:471:Qnn_ErrorHandle_t QnnGraph_addNode(Qnn_GraphHandle_t graphHandle, Qnn_OpConfig_t opConfig);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_AddNodeFn_t)(Qnn_GraphHandle_t graphHandle,
                                                  Qnn_OpConfig_t opConfig);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphAddNode(...)`（调用前判空）。

作用：
- 向 graph 添加节点。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## graphFinalize
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:318`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:523:Qnn_ErrorHandle_t QnnGraph_finalize(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_FinalizeFn_t)(Qnn_GraphHandle_t graphHandle,
                                                   Qnn_ProfileHandle_t profileHandle,
                                                   Qnn_SignalHandle_t signalHandle);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphFinalize(...)`（调用前判空）。

作用：
- 完成 graph 编译/定型。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:835:        m_qnnInterface.graphFinalize(m_graphsInfo[graphIdx]->graph, nullptr, nullptr)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:864:        m_qnnInterface.graphFinalize(m_graphsInfo[graphIdx]->graph, nullptr, nullptr)) {`

## graphRetrieve
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:323`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:549:Qnn_ErrorHandle_t QnnGraph_retrieve(Qnn_ContextHandle_t contextHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_RetrieveFn_t)(Qnn_ContextHandle_t contextHandle,
                                                   const char* graphName,
                                                   Qnn_GraphHandle_t* graphHandle);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphRetrieve(...)`（调用前判空）。

作用：
- 按图名检索 graph 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:555:    if (QNN_SUCCESS != qnnInterface.graphRetrieve(context, graphInfo->graphName, &graph)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:527:      if (nullptr == m_qnnFunctionPointers.qnnInterface.graphRetrieve) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:533:          m_qnnFunctionPointers.qnnInterface.graphRetrieve(`

## graphExecute
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:332`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:704:Qnn_ErrorHandle_t QnnGraph_execute(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_ExecuteFn_t)(Qnn_GraphHandle_t graphHandle,
                                                  const Qnn_Tensor_t* inputs,
                                                  uint32_t numInputs,
                                                  Qnn_Tensor_t* outputs,
                                                  uint32_t numOutputs,
                                                  Qnn_ProfileHandle_t profileHandle,
                                                  Qnn_SignalHandle_t signalHandle);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphExecute(...)`（调用前判空）。

作用：
- 同步执行 graph。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:811:  CALL_QNN(runtime_->qnnInterface.graphExecute(model->getQnnGraph(), qnn_inputs.data(), qnn_inputs.size(), qnn_outputs.data(),`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:2002:    ret = m_qnnInterface.graphExecute(graph_info->graph,`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:702:                m_qnnFunctionPointers.qnnInterface.graphExecute(graphInfo.graph,`

## graphExecuteAsync
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:341`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:841:Qnn_ErrorHandle_t QnnGraph_executeAsync(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_ExecuteAsyncFn_t)(Qnn_GraphHandle_t graphHandle,
                                                       const Qnn_Tensor_t* inputs,
                                                       uint32_t numInputs,
                                                       Qnn_Tensor_t* outputs,
                                                       uint32_t numOutputs,
                                                       Qnn_ProfileHandle_t profileHandle,
                                                       Qnn_SignalHandle_t signalHandle,
                                                       Qnn_NotifyFn_t notifyFn,
                                                       void* notifyParam);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphExecuteAsync(...)`（调用前判空）。

作用：
- 异步执行 graph。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppAsyncExecution/src/QnnSampleApp.cpp:799:                  m_qnnFunctionPointers.qnnInterface.graphExecuteAsync(graphInfo.graph,`

## tensorCreateContextTensor
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:360`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h:115:Qnn_ErrorHandle_t QnnTensor_createContextTensor(Qnn_ContextHandle_t context, Qnn_Tensor_t* tensor);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnTensor_CreateContextTensorFn_t)(Qnn_ContextHandle_t context,
                                                               Qnn_Tensor_t* tensor);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.tensorCreateContextTensor(...)`（调用前判空）。

作用：
- 创建 context 级张量。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## tensorCreateGraphTensor
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:364`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h:157:Qnn_ErrorHandle_t QnnTensor_createGraphTensor(Qnn_GraphHandle_t graph, Qnn_Tensor_t* tensor);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnTensor_CreateGraphTensorFn_t)(Qnn_GraphHandle_t graph,
                                                             Qnn_Tensor_t* tensor);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.tensorCreateGraphTensor(...)`（调用前判空）。

作用：
- 创建 graph 级张量。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## logCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:382`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnLog.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnLog.h:126:Qnn_ErrorHandle_t QnnLog_create(QnnLog_Callback_t callback,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnLog_CreateFn_t)(QnnLog_Callback_t callback,
                                               QnnLog_Level_t maxLogLevel,
                                               Qnn_LogHandle_t* logger);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.logCreate(...)`（调用前判空）。

作用：
- 创建日志句柄并注册回调。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:322:    if ((QNN_GET_ERROR_CODE(qnnInterface.logCreate(logCallback, qnnLogLevel, &logHandle)) != QNN_SUCCESS)`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:321:  if (nullptr != m_qnnInterface.logCreate) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:335:    if (QNN_SUCCESS != m_qnnInterface.logCreate(logCallback, logLevel, &m_logHandle)) {`

## logSetLogLevel
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:387`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnLog.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnLog.h:149:Qnn_ErrorHandle_t QnnLog_setLogLevel(Qnn_LogHandle_t logger, QnnLog_Level_t maxLogLevel);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnLog_SetLogLevelFn_t)(Qnn_LogHandle_t logger,
                                                    QnnLog_Level_t maxLogLevel);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.logSetLogLevel(...)`（调用前判空）。

作用：
- 设置日志等级。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## logFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:391`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnLog.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnLog.h:164:Qnn_ErrorHandle_t QnnLog_free(Qnn_LogHandle_t logger);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnLog_FreeFn_t)(Qnn_LogHandle_t logger);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.logFree(...)`（调用前判空）。

作用：
- 释放日志句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:282:  CALL_QNN(qnnInterface.logFree(logHandle));`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:349:  if (nullptr != m_qnnInterface.logFree && nullptr != m_logHandle) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:350:    if (QNN_SUCCESS != m_qnnInterface.logFree(m_logHandle)) {`

## profileCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:398`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h:455:Qnn_ErrorHandle_t QnnProfile_create(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProfile_CreateFn_t)(Qnn_BackendHandle_t backend,
                                                   QnnProfile_Level_t level,
                                                   Qnn_ProfileHandle_t* profile);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.profileCreate(...)`（调用前判空）。

作用：
- 创建 profiling 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:386:        if (QNN_PROFILE_NO_ERROR != qnnInterface.profileCreate(backendHandle, QNN_PROFILE_LEVEL_BASIC, &profileHandle)) {`
- `mllm/backends/qnn/QNNBackend.cpp:392:        if (QNN_PROFILE_NO_ERROR != qnnInterface.profileCreate(backendHandle, QNN_PROFILE_LEVEL_DETAILED, &profileHandle)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppAsyncExecution/src/QnnSampleApp.cpp:131:          m_qnnFunctionPointers.qnnInterface.profileCreate(`

## profileSetConfig
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:403`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h:480:Qnn_ErrorHandle_t QnnProfile_setConfig(Qnn_ProfileHandle_t profileHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProfile_SetConfigFn_t)(Qnn_ProfileHandle_t profileHandle,
                                                      const QnnProfile_Config_t** config);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.profileSetConfig(...)`（调用前判空）。

作用：
- 设置 profiling 配置。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## profileGetEvents
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:407`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h:505:Qnn_ErrorHandle_t QnnProfile_getEvents(Qnn_ProfileHandle_t profile,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProfile_GetEventsFn_t)(Qnn_ProfileHandle_t profile,
                                                      const QnnProfile_EventId_t** profileEventIds,
                                                      uint32_t* numEvents);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.profileGetEvents(...)`（调用前判空）。

作用：
- 获取 profiling 事件列表。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:887:  if (QNN_PROFILE_NO_ERROR != runtime_->qnnInterface.profileGetEvents(profileHandle, &profileEvents, &numEvents)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:426:  if (QNN_PROFILE_NO_ERROR != m_qnnFunctionPointers.qnnInterface.profileGetEvents(`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppAsyncExecution/src/QnnSampleApp.cpp:543:  if (QNN_PROFILE_NO_ERROR != m_qnnFunctionPointers.qnnInterface.profileGetEvents(`

## profileGetSubEvents
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:412`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h:530:Qnn_ErrorHandle_t QnnProfile_getSubEvents(QnnProfile_EventId_t eventId,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProfile_GetSubEventsFn_t)(QnnProfile_EventId_t eventId,
                                                         const QnnProfile_EventId_t** subEventIds,
                                                         uint32_t* numSubEvents);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.profileGetSubEvents(...)`（调用前判空）。

作用：
- 获取 profiling 子事件。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppSharedBuffer/src/QnnSampleApp.cpp:556:  if (QNN_PROFILE_NO_ERROR != m_qnnFunctionPointers.qnnInterface.profileGetSubEvents(`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:443:  if (QNN_PROFILE_NO_ERROR != m_qnnFunctionPointers.qnnInterface.profileGetSubEvents(`

## profileGetEventData
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:417`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h:556:Qnn_ErrorHandle_t QnnProfile_getEventData(QnnProfile_EventId_t eventId,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProfile_GetEventDataFn_t)(QnnProfile_EventId_t eventId,
                                                         QnnProfile_EventData_t* eventData);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.profileGetEventData(...)`（调用前判空）。

作用：
- 读取 profiling 事件数据。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:460:      m_qnnFunctionPointers.qnnInterface.profileGetEventData(profileEventId, &eventData)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppAsyncExecution/src/QnnSampleApp.cpp:577:      m_qnnFunctionPointers.qnnInterface.profileGetEventData(profileEventId, &eventData)) {`

## profileGetExtendedEventData
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:421`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h:579:Qnn_ErrorHandle_t QnnProfile_getExtendedEventData(QnnProfile_EventId_t eventId,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProfile_GetExtendedEventDataFn_t)(
    QnnProfile_EventId_t eventId, QnnProfile_ExtendedEventData_t* eventData);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.profileGetExtendedEventData(...)`（调用前判空）。

作用：
- 读取扩展 profiling 事件数据。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## profileFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:425`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnProfile.h:604:Qnn_ErrorHandle_t QnnProfile_free(Qnn_ProfileHandle_t profile);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnProfile_FreeFn_t)(Qnn_ProfileHandle_t profile);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.profileFree(...)`（调用前判空）。

作用：
- 释放 profiling 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:273:  if (profileHandle != nullptr) { CALL_QNN(qnnInterface.profileFree(profileHandle)); }`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:158:        m_qnnFunctionPointers.qnnInterface.profileFree(m_profileBackendHandle)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:71:    if (QNN_PROFILE_NO_ERROR != m_qnnInterface.profileFree(m_profileBackendHandle))`

## memRegister
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:432`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnMem.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnMem.h:215:Qnn_ErrorHandle_t QnnMem_register(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnMem_RegisterFn_t)(Qnn_ContextHandle_t context,
                                                 const Qnn_MemDescriptor_t* memDescriptors,
                                                 uint32_t numDescriptors,
                                                 Qnn_MemHandle_t* memHandles);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.memRegister(...)`（调用前判空）。

作用：
- 注册共享内存。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## memDeRegister
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:438`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnMem.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnMem.h:238:Qnn_ErrorHandle_t QnnMem_deRegister(const Qnn_MemHandle_t* memHandles, uint32_t numHandles);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnMem_DeRegisterFn_t)(const Qnn_MemHandle_t* memHandles,
                                                   uint32_t numHandles);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.memDeRegister(...)`（调用前判空）。

作用：
- 注销共享内存句柄。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## deviceGetPlatformInfo
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:446`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h:308:Qnn_ErrorHandle_t QnnDevice_getPlatformInfo(Qnn_LogHandle_t logger,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnDevice_GetPlatformInfoFn_t)(
    Qnn_LogHandle_t logger, const QnnDevice_PlatformInfo_t** platformInfo);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.deviceGetPlatformInfo(...)`（调用前判空）。

作用：
- 查询硬件平台信息。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:1207:  if (nullptr != m_qnnInterface.deviceGetPlatformInfo) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:1208:    auto qnnStatus = m_qnnInterface.deviceGetPlatformInfo(nullptr, &platformInfo);`

## deviceFreePlatformInfo
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:450`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h:332:Qnn_ErrorHandle_t QnnDevice_freePlatformInfo(Qnn_LogHandle_t logger,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnDevice_FreePlatformInfoFn_t)(
    Qnn_LogHandle_t logger, const QnnDevice_PlatformInfo_t* platformInfo);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.deviceFreePlatformInfo(...)`（调用前判空）。

作用：
- 释放平台信息对象。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## deviceGetInfrastructure
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:454`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h:354:Qnn_ErrorHandle_t QnnDevice_getInfrastructure(const QnnDevice_Infrastructure_t* deviceInfra);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnDevice_GetInfrastructureFn_t)(
    const QnnDevice_Infrastructure_t* deviceInfra);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.deviceGetInfrastructure(...)`（调用前判空）。

作用：
- 查询设备基础设施接口。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## deviceCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:458`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h:388:Qnn_ErrorHandle_t QnnDevice_create(Qnn_LogHandle_t logger,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnDevice_CreateFn_t)(Qnn_LogHandle_t logger,
                                                  const QnnDevice_Config_t** config,
                                                  Qnn_DeviceHandle_t* device);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.deviceCreate(...)`（调用前判空）。

作用：
- 创建设备句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:348:    if (nullptr != qnnInterface.deviceCreate) {`
- `mllm/backends/qnn/QNNBackend.cpp:349:      auto status = qnnInterface.deviceCreate(logHandle, nullptr, &deviceHandle);`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:629:    if (nullptr != m_qnnFunctionPointers.qnnInterface.deviceCreate) {`

## deviceSetConfig
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:463`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h:415:Qnn_ErrorHandle_t QnnDevice_setConfig(Qnn_DeviceHandle_t device, const QnnDevice_Config_t** config);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnDevice_SetConfigFn_t)(Qnn_DeviceHandle_t device,
                                                     const QnnDevice_Config_t** config);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.deviceSetConfig(...)`（调用前判空）。

作用：
- 设置设备配置。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## deviceGetInfo
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:467`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h:434:Qnn_ErrorHandle_t QnnDevice_getInfo(Qnn_DeviceHandle_t device,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnDevice_GetInfoFn_t)(Qnn_DeviceHandle_t device,
                                                   const QnnDevice_PlatformInfo_t** platformInfo);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.deviceGetInfo(...)`（调用前判空）。

作用：
- 查询设备实例信息。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:356:    if (nullptr != qnnInterface.deviceGetInfo) {`
- `mllm/backends/qnn/QNNBackend.cpp:358:      auto istatus = qnnInterface.deviceGetInfo(deviceHandle, &pinfo);`

## deviceFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:471`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnDevice.h:455:Qnn_ErrorHandle_t QnnDevice_free(Qnn_DeviceHandle_t device);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnDevice_FreeFn_t)(Qnn_DeviceHandle_t device);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.deviceFree(...)`（调用前判空）。

作用：
- 释放设备句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:276:  CALL_QNN(qnnInterface.deviceFree(deviceHandle));`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:516:  if (nullptr != m_qnnInterface.deviceFree) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:517:    auto qnnStatus = m_qnnInterface.deviceFree(m_deviceHandle);`

## signalCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:478`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h:148:Qnn_ErrorHandle_t QnnSignal_create(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSignal_CreateFn_t)(Qnn_BackendHandle_t backend,
                                                  const QnnSignal_Config_t** config,
                                                  Qnn_SignalHandle_t* signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.signalCreate(...)`（调用前判空）。

作用：
- 创建 signal。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## signalSetConfig
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:483`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h:173:Qnn_ErrorHandle_t QnnSignal_setConfig(Qnn_SignalHandle_t signal, const QnnSignal_Config_t** config);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSignal_SetConfigFn_t)(Qnn_SignalHandle_t signal,
                                                     const QnnSignal_Config_t** config);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.signalSetConfig(...)`（调用前判空）。

作用：
- 设置 signal 配置。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## signalTrigger
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:487`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h:197:Qnn_ErrorHandle_t QnnSignal_trigger(Qnn_SignalHandle_t signal);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSignal_TriggerFn_t)(Qnn_SignalHandle_t signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.signalTrigger(...)`（调用前判空）。

作用：
- 触发 signal。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## signalFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:490`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnSignal.h:213:Qnn_ErrorHandle_t QnnSignal_free(Qnn_SignalHandle_t signal);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSignal_FreeFn_t)(Qnn_SignalHandle_t signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.signalFree(...)`（调用前判空）。

作用：
- 释放 signal。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## errorGetMessage
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:497`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnError.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnError.h:77:Qnn_ErrorHandle_t QnnError_getMessage(Qnn_ErrorHandle_t errorHandle, const char** errorMessage);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnError_GetMessageFn_t)(Qnn_ErrorHandle_t errorHandle,
                                                     const char** errorMessage);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.errorGetMessage(...)`（调用前判空）。

作用：
- 把错误码转为简要错误字符串。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## errorGetVerboseMessage
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:500`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnError.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnError.h:99:Qnn_ErrorHandle_t QnnError_getVerboseMessage(Qnn_ErrorHandle_t errorHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnError_GetVerboseMessageFn_t)(Qnn_ErrorHandle_t errorHandle,
                                                            const char** errorMessage);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.errorGetVerboseMessage(...)`（调用前判空）。

作用：
- 把错误码转为详细错误字符串。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## errorFreeVerboseMessage
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:503`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnError.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnError.h:116:Qnn_ErrorHandle_t QnnError_freeVerboseMessage(const char* errorMessage);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnError_FreeVerboseMessageFn_t)(const char* errorMessage);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.errorFreeVerboseMessage(...)`（调用前判空）。

作用：
- 释放详细错误字符串。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## graphPrepareExecutionEnvironment
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:328`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:588:Qnn_ErrorHandle_t QnnGraph_prepareExecutionEnvironment(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_PrepareExecutionEnvironmentFn_t)(
    Qnn_GraphHandle_t graphHandle, QnnGraph_ExecuteEnvironment_t** envs, uint32_t envSize);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphPrepareExecutionEnvironment(...)`（调用前判空）。

作用：
- 准备 graph 执行环境。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppSharedBuffer/src/QnnSampleApp.cpp:620:  if (nullptr != m_qnnFunctionPointers.qnnInterface.graphPrepareExecutionEnvironment) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppSharedBuffer/src/QnnSampleApp.cpp:626:    if (QNN_SUCCESS != m_qnnFunctionPointers.qnnInterface.graphPrepareExecutionEnvironment(`

## graphReleaseExecutionEnvironment
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:352`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:873:Qnn_ErrorHandle_t QnnGraph_releaseExecutionEnvironment(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_ReleaseExecutionEnvironmentFn_t)(
    Qnn_GraphHandle_t graphHandle, const QnnGraph_ExecuteEnvironment_t** envs, uint32_t envSize);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphReleaseExecutionEnvironment(...)`（调用前判空）。

作用：
- 释放 graph 执行环境。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppSharedBuffer/src/QnnSampleApp.cpp:637:  if (nullptr != m_qnnFunctionPointers.qnnInterface.graphReleaseExecutionEnvironment) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppSharedBuffer/src/QnnSampleApp.cpp:643:    if (QNN_SUCCESS != m_qnnFunctionPointers.qnnInterface.graphReleaseExecutionEnvironment(`

## graphGetProperty
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:310`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGraph.h:420:Qnn_ErrorHandle_t QnnGraph_getProperty(Qnn_GraphHandle_t graphHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGraph_GetPropertyFn_t)(Qnn_GraphHandle_t graphHandle,
                                                      QnnGraph_Property_t** properties);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.graphGetProperty(...)`（调用前判空）。

作用：
- 查询 graph 属性。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextValidateBinary
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:191`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:841:Qnn_ErrorHandle_t QnnContext_validateBinary(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_ValidateBinaryFn_t)(
    Qnn_BackendHandle_t backend,
    Qnn_DeviceHandle_t device,
    const QnnContext_Config_t** config,
    const void* binaryBuffer,
    Qnn_ContextBinarySize_t binaryBufferSize);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextValidateBinary(...)`（调用前判空）。

作用：
- 校验 binary 与 backend/device 的兼容性。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextCreateFromBinaryWithSignal
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:199`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:962:Qnn_ErrorHandle_t QnnContext_createFromBinaryWithSignal(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_CreateFromBinaryWithSignalFn_t)(
    Qnn_BackendHandle_t backend,
    Qnn_DeviceHandle_t device,
    const QnnContext_Config_t** config,
    const void* binaryBuffer,
    Qnn_ContextBinarySize_t binaryBufferSize,
    Qnn_ContextHandle_t* context,
    Qnn_ProfileHandle_t profile,
    Qnn_SignalHandle_t signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextCreateFromBinaryWithSignal(...)`（调用前判空）。

作用：
- 带 signal 的从 binary 创建 context。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextCreateFromBinaryListAsync
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:210`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1031:Qnn_ErrorHandle_t QnnContext_createFromBinaryListAsync(Qnn_BackendHandle_t backend,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_CreateFromBinaryListAsyncFn_t)(
    Qnn_BackendHandle_t backend,
    Qnn_DeviceHandle_t device,
    const QnnContext_Params_t** contextParams,
    const QnnContext_Config_t** listConfig,
    Qnn_SignalHandle_t signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextCreateFromBinaryListAsync(...)`（调用前判空）。

作用：
- 异步批量从 binary/context 参数创建 context。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:1522:  if (nullptr == m_qnnInterface.contextCreateFromBinaryListAsync) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:1528:  auto errCode = m_qnnInterface.contextCreateFromBinaryListAsync(`

## tensorUpdateGraphTensors
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:373`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h:186:Qnn_ErrorHandle_t QnnTensor_updateGraphTensors(Qnn_GraphHandle_t graph,`
> 注：interface 注释写为 `QnnTensor_updateGraphTensor`，实际公开 API 是 `QnnTensor_updateGraphTensors`。

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnTensor_UpdateGraphTensorsFn_t)(Qnn_GraphHandle_t graph,
                                                              const Qnn_Tensor_t** tensor,
                                                              uint64_t numTensors);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.tensorUpdateGraphTensors(...)`（调用前判空）。

作用：
- 更新 graph 张量元信息。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## tensorUpdateContextTensors
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:368`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnTensor.h:214:Qnn_ErrorHandle_t QnnTensor_updateContextTensors(Qnn_ContextHandle_t context,`
> 注：interface 注释写为 `QnnTensor_updateContextTensor`，实际公开 API 是 `QnnTensor_updateContextTensors`。

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnTensor_UpdateContextTensorsFn_t)(Qnn_ContextHandle_t context,
                                                                const Qnn_Tensor_t** tensor,
                                                                uint64_t numTensors);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.tensorUpdateContextTensors(...)`（调用前判空）。

作用：
- 更新 context 张量元信息。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextGetBinarySectionSize
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:234`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1183:Qnn_ErrorHandle_t QnnContext_getBinarySectionSize(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_GetBinarySectionSizeFn_t)(
    Qnn_ContextHandle_t context,
    Qnn_GraphHandle_t graph,
    QnnContext_SectionType_t section,
    Qnn_ContextBinarySize_t* binaryBufferSize);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextGetBinarySectionSize(...)`（调用前判空）。

作用：
- 查询指定 binary section 的导出大小。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextGetBinarySection
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:241`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1239:Qnn_ErrorHandle_t QnnContext_getBinarySection(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_GetBinarySectionFn_t)(
    Qnn_ContextHandle_t context,
    Qnn_GraphHandle_t graph,
    QnnContext_SectionType_t section,
    const QnnContext_Buffer_t* binaryBuffer,
    Qnn_ContextBinarySize_t* writtenBufferSize,
    Qnn_ProfileHandle_t profile,
    Qnn_SignalHandle_t signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextGetBinarySection(...)`（调用前判空）。

作用：
- 导出指定 binary section。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextApplyBinarySection
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:251`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1290:Qnn_ErrorHandle_t QnnContext_applyBinarySection(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_ApplyBinarySectionFn_t)(
    Qnn_ContextHandle_t context,
    Qnn_GraphHandle_t graph,
    QnnContext_SectionType_t section,
    const QnnContext_Buffer_t* binaryBuffer,
    Qnn_ProfileHandle_t profile,
    Qnn_SignalHandle_t signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextApplyBinarySection(...)`（调用前判空）。

作用：
- 把 binary section 应用到 context/graph。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:2202:  if (nullptr != m_qnnInterface.contextApplyBinarySection) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/Genie/Genie/src/qualla/engines/qnn-api/QnnApi.cpp:2218:        m_qnnInterface.contextApplyBinarySection(contextHandle,`

## backendGetProperty
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:149`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnBackend.h:402:Qnn_ErrorHandle_t QnnBackend_getProperty(Qnn_BackendHandle_t backendHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnBackend_GetPropertyFn_t)(Qnn_BackendHandle_t backendHandle,
                                                        QnnBackend_Property_t** properties);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.backendGetProperty(...)`（调用前判空）。

作用：
- 查询 backend 属性。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextGetProperty
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:277`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1408:Qnn_ErrorHandle_t QnnContext_getProperty(Qnn_ContextHandle_t contextHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_GetPropertyFn_t)(Qnn_ContextHandle_t contextHandle,
                                                        QnnContext_Property_t** properties);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextGetProperty(...)`（调用前判空）。

作用：
- 查询 context 属性。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextGetIncrementalBinary
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:281`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1446:Qnn_ErrorHandle_t QnnContext_getIncrementalBinary(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_GetIncrementalBinaryFn_t)(
    Qnn_ContextHandle_t context,
    const void** binaryBuffer,
    Qnn_ContextBinarySize_t* startOffset,
    Qnn_ContextBinarySize_t* writtenBufferSize);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextGetIncrementalBinary(...)`（调用前判空）。

作用：
- 增量导出 context binary。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextReleaseIncrementalBinary
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:288`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1479:Qnn_ErrorHandle_t QnnContext_releaseIncrementalBinary(Qnn_ContextHandle_t context,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_ReleaseIncrementalBinaryFn_t)(
    Qnn_ContextHandle_t context, const void* binaryBuffer, Qnn_ContextBinarySize_t startOffset);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextReleaseIncrementalBinary(...)`（调用前判空）。

作用：
- 释放增量 binary 导出资源。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextFinalize
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:218`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1068:Qnn_ErrorHandle_t QnnContext_finalize(Qnn_ContextHandle_t context, Qnn_ProfileHandle_t profile);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_FinalizeFn_t)(Qnn_ContextHandle_t context,
                                                     Qnn_ProfileHandle_t profile);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextFinalize(...)`（调用前判空）。

作用：
- 完成 context 最终化。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## globalConfigSet
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:108`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGlobalConfig.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnGlobalConfig.h:77:Qnn_ErrorHandle_t QnnGlobalConfig_Set(const QnnGlobalConfig_t **config);`
> 注：interface 注释写为 `QnnConfig_Set`，实际公开 API 是 `QnnGlobalConfig_Set`。

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnGlobalConfig_SetFn_t)(const QnnGlobalConfig_t** config);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.globalConfigSet(...)`（调用前判空）。

作用：
- 设置 QNN 全局配置项。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextCreateFromBinaryWithCallback
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:222`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1137:Qnn_ErrorHandle_t QnnContext_createFromBinaryWithCallback(`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_CreateFromBinaryWithCallbackFn_t)(
    Qnn_BackendHandle_t backend,
    Qnn_DeviceHandle_t device,
    const QnnContext_Config_t** config,
    const Qnn_ContextBinaryCallback_t* callback,
    const void* binaryBuffer,
    Qnn_ContextBinarySize_t binaryBufferSize,
    Qnn_ContextHandle_t* context,
    Qnn_ProfileHandle_t profile,
    Qnn_SignalHandle_t signal);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextCreateFromBinaryWithCallback(...)`（调用前判空）。

作用：
- 通过回调方式从 binary 创建 context。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextGetBinarySectionUpdate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:260`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1349:Qnn_ErrorHandle_t QnnContext_getBinarySectionUpdate(const QnnContext_Buffer_t* binaryBuffer,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_GetBinarySectionUpdateFn_t)(
    const QnnContext_Buffer_t* binaryBuffer,
    const QnnContext_Buffer_t* auxiliaryBuffer,
    const Qnn_Tensor_t** tensors,
    uint64_t numTensors,
    uint8_t keepUpdatable,
    Qnn_LogHandle_t logger,
    Qnn_ProfileHandle_t profile,
    Qnn_SignalHandle_t signal,
    QnnContext_Buffer_t* binarySectionUpdate);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextGetBinarySectionUpdate(...)`（调用前判空）。

作用：
- 生成 binary section 的增量更新。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## contextFreeBinarySectionUpdate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnInterface.h:272`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/QnnContext.h:1381:Qnn_ErrorHandle_t QnnContext_freeBinarySectionUpdate(QnnContext_Buffer_t binarySectionUpdate,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnContext_FreeBinarySectionUpdateFn_t)(
    QnnContext_Buffer_t binarySectionUpdate,
    Qnn_LogHandle_t logger);
```

调用方式：
- `providers[i]->QNN_INTERFACE_VER_NAME.contextFreeBinarySectionUpdate(...)`（调用前判空）。

作用：
- 释放 binary section 更新缓冲。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## 2. libQnnSystem：QnnSystemInterface API

共 16 个 API，按 interface struct 字段顺序。

## systemContextCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:90`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h:445:Qnn_ErrorHandle_t QnnSystemContext_create(QnnSystemContext_Handle_t* sysCtxHandle);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemContext_CreateFn_t)(QnnSystemContext_Handle_t* sysCtxHandle);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemContextCreate(...)`（调用前判空）。

作用：
- 创建 context 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:496:  if (!qnnSystemInterface.systemContextCreate) {`
- `mllm/backends/qnn/QNNBackend.cpp:500:  if (QNN_SUCCESS != qnnSystemInterface.systemContextCreate(&sysCtxHandle)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:432:  if (nullptr == m_qnnFunctionPointers.qnnSystemInterface.systemContextCreate ||`

## systemContextGetBinaryInfo
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:93`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h:480:Qnn_ErrorHandle_t QnnSystemContext_getBinaryInfo(QnnSystemContext_Handle_t sysCtxHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemContext_GetBinaryInfoFn_t)(
    QnnSystemContext_Handle_t sysCtxHandle,
    void* binaryBuffer,
    uint64_t binaryBufferSize,
    const QnnSystemContext_BinaryInfo_t** binaryInfo,
    Qnn_ContextBinarySize_t* binaryInfoSize);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemContextGetBinaryInfo(...)`（调用前判空）。

作用：
- 解析 context binary 的图/张量信息。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:511:      != qnnSystemInterface.systemContextGetBinaryInfo(sysCtxHandle, static_cast<void*>(binaryBuffer.get()), size, &binaryInfo,`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:268:      nullptr == m_qnnFunctionPointers.qnnSystemInterface.systemContextGetBinaryInfo ||`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:306:      QNN_SUCCESS != m_qnnFunctionPointers.qnnSystemInterface.systemContextGetBinaryInfo(`

## systemContextGetMetaData
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:101`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h:514:Qnn_ErrorHandle_t QnnSystemContext_getMetadata(QnnSystemContext_Handle_t sysCtxHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemContext_GetMetaDataFn_t)(
    QnnSystemContext_Handle_t sysCtxHandle,
    const void* binaryBuffer,
    uint64_t binaryBufferSize,
    const QnnSystemContext_BinaryInfo_t** binaryInfo);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemContextGetMetaData(...)`（调用前判空）。

作用：
- 解析 context binary 元数据（新接口）。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## systemContextFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:108`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemContext.h:532:Qnn_ErrorHandle_t QnnSystemContext_free(QnnSystemContext_Handle_t sysCtxHandle);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemContext_FreeFn_t)(QnnSystemContext_Handle_t sysCtxHandle);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemContextFree(...)`（调用前判空）。

作用：
- 释放 context 句柄。

用法验证：
- `mllm/backends/qnn/QNNBackend.cpp:527:  if (QNN_SUCCESS != qnnSystemInterface.systemContextFree(sysCtxHandle)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:269:      nullptr == m_qnnFunctionPointers.qnnSystemInterface.systemContextFree) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/QnnSampleApp.cpp:322:  m_qnnFunctionPointers.qnnSystemInterface.systemContextFree(sysCtxHandle);`

## systemTensorGetMemoryFootprint
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:115`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemTensor.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemTensor.h:71:Qnn_ErrorHandle_t QnnSystemTensor_getMemoryFootprint(Qnn_Tensor_t tensor, uint64_t* footprint);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemTensor_getMemoryFootprintFn_t)(Qnn_Tensor_t tensor,
                                                                    uint64_t* footprint);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemTensorGetMemoryFootprint(...)`（调用前判空）。

作用：
- 估算张量内存占用。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## systemLogCreate
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:123`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemLog.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemLog.h:59:Qnn_ErrorHandle_t QnnSystemLog_create(QnnLog_Callback_t callback,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemLog_createFn_t)(QnnLog_Callback_t callback,
                                                     QnnLog_Level_t maxLogLevel,
                                                     Qnn_LogHandle_t* logger);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemLogCreate(...)`（调用前判空）。

作用：
- 创建 system log 句柄。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/Utils/QnnDlcUtils.cpp:32:  if (QNN_SUCCESS != systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemLogCreate(logCallback, logLevel, &logHandle)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppLPAI/src/Utils/QnnDlcUtils.cpp:32:  if (QNN_SUCCESS != systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemLogCreate(logCallback, logLevel, &logHandle)) {`

## systemLogSetLogLevel
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:128`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemLog.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemLog.h:78:Qnn_ErrorHandle_t QnnSystemLog_setLogLevel(Qnn_LogHandle_t logger, QnnLog_Level_t maxLogLevel);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemLog_setLogLevelFn_t)(Qnn_LogHandle_t logger,
                                                          QnnLog_Level_t maxLogLevel);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemLogSetLogLevel(...)`（调用前判空）。

作用：
- 设置 system log 等级。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## systemLogFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:132`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemLog.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemLog.h:93:Qnn_ErrorHandle_t QnnSystemLog_free(Qnn_LogHandle_t logger);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemLog_freeFn_t)(Qnn_LogHandle_t logger);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemLogFree(...)`（调用前判空）。

作用：
- 释放 system log 句柄。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/Utils/QnnDlcUtils.cpp:40:    systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemLogFree(logHandle);`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/Utils/QnnDlcUtils.cpp:58:    systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemLogFree(logHandle);`

## systemDlcCreateFromFile
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:140`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h:108:Qnn_ErrorHandle_t QnnSystemDlc_createFromFile(Qnn_LogHandle_t logger,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemDlc_createFromFileFn_t)(Qnn_LogHandle_t logger,
                                                             const char* dlcPath,
                                                             QnnSystemDlc_Handle_t* dlcHandle);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcCreateFromFile(...)`（调用前判空）。

作用：
- 从 DLC 文件创建 DLC 句柄。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiGraph/src/Utils/QnnDlcUtils.cpp:38:  if (QNN_SUCCESS != systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcCreateFromFile(logHandle, dlcPath.c_str(), &dlcHandle)) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppSharedBuffer/src/Utils/QnnDlcUtils.cpp:38:  if (QNN_SUCCESS != systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcCreateFromFile(logHandle, dlcPath.c_str(), &dlcHandle)) {`

## systemDlcCreateFromBinary
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:144`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h:128:Qnn_ErrorHandle_t QnnSystemDlc_createFromBinary(Qnn_LogHandle_t logger,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemDlc_createFromBinaryFn_t)(Qnn_LogHandle_t logger,
                                                               const uint8_t* buffer,
                                                               const Qnn_ContextBinarySize_t bufferSize,
                                                               QnnSystemDlc_Handle_t* dlcHandle);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcCreateFromBinary(...)`（调用前判空）。

作用：
- 从 DLC 二进制创建 DLC 句柄。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## systemDlcComposeGraphs
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:150`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h:158:Qnn_ErrorHandle_t QnnSystemDlc_composeGraphs(QnnSystemDlc_Handle_t dlcHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemDlc_composeGraphsFn_t)(QnnSystemDlc_Handle_t dlcHandle,
                                                            const QnnSystemDlc_GraphConfigInfo_t** graphConfigs,
                                                            const uint32_t numGraphConfigs,
                                                            Qnn_BackendHandle_t backend,
                                                            Qnn_ContextHandle_t context,
                                                            QnnInterface_t interface,
                                                            QnnSystemContext_GraphInfoVersion_t graphVersion,
                                                            QnnSystemContext_GraphInfo_t** graphs,
                                                            uint32_t* numGraphs);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcComposeGraphs(...)`（调用前判空）。

作用：
- 把 DLC 组合为 QNN graph。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/Utils/QnnDlcUtils.cpp:82:  auto qnnStatus = systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcComposeGraphs(`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppSharedBuffer/src/Utils/QnnDlcUtils.cpp:82:  auto qnnStatus = systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcComposeGraphs(`

## systemDlcGetOpMappings
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:160`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h:181:Qnn_ErrorHandle_t QnnSystemDlc_getOpMappings(QnnSystemDlc_Handle_t dlcHandle,`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemDlc_getOpMappingsFn_t)(QnnSystemDlc_Handle_t dlcHandle,
                                                          const Qnn_OpMapping_t** opMappings,
                                                          uint32_t* numOpMappings);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcGetOpMappings(...)`（调用前判空）。

作用：
- 获取 DLC op 到 QNN op 的映射。

用法验证：
- 未在 MLLM/QNN sample 中检索到显式调用（通常为可选能力）。

## systemDlcFree
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:165`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemDlc.h:198:Qnn_ErrorHandle_t QnnSystemDlc_free(QnnSystemDlc_Handle_t dlcHandle);`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemDlc_freeFn_t)(QnnSystemDlc_Handle_t dlcHandle);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcFree(...)`（调用前判空）。

作用：
- 释放 DLC 句柄。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppMultiCore/src/Utils/QnnDlcUtils.cpp:53:    systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcFree(dlcHandle);`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleAppLPAI/src/Utils/QnnDlcUtils.cpp:53:    systemInterface.QNN_SYSTEM_INTERFACE_VER_NAME.systemDlcFree(dlcHandle);`

## systemProfileCreateSerializationTarget
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:172`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemProfile.h:254:Qnn_ErrorHandle_t QnnSystemProfile_createSerializationTarget(`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemProfile_createSerializationTargetFn_t)(QnnSystemProfile_SerializationTarget_t serializationTargetInfo,
                                                         QnnSystemProfile_SerializationTargetConfig_t* configs,
                                                         uint32_t numConfigs,
                                                         QnnSystemProfile_SerializationTargetHandle_t* serializationTarget);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemProfileCreateSerializationTarget(...)`（调用前判空）。

作用：
- 创建 profile 序列化目标。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:149:              m_qnnFunctionPointers.qnnSystemInterface.systemProfileCreateSerializationTarget ||`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:193:          m_qnnFunctionPointers.qnnSystemInterface.systemProfileCreateSerializationTarget(`

## systemProfileSerializeEventData
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:178`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemProfile.h:268:Qnn_ErrorHandle_t QnnSystemProfile_serializeEventData(`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemProfile_serializeEventDataFn_t)(QnnSystemProfile_SerializationTargetHandle_t serializationTarget,
                                                                 const QnnSystemProfile_ProfileData_t** eventData,
                                                                 uint32_t numEvents);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemProfileSerializeEventData(...)`（调用前判空）。

作用：
- 序列化 profile 事件数据。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:150:          nullptr == m_qnnFunctionPointers.qnnSystemInterface.systemProfileSerializeEventData ||`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:665:    if (QNN_SUCCESS != m_qnnFunctionPointers.qnnSystemInterface.systemProfileSerializeEventData(`

## systemProfileFreeSerializationTarget
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemInterface.h:183`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemProfile.h`
> 参考 `/home/junming/software/qairt/2.42.0.251225/include/QNN/System/QnnSystemProfile.h:278:Qnn_ErrorHandle_t QnnSystemProfile_freeSerializationTarget(`

接口定义：
```c
typedef Qnn_ErrorHandle_t (*QnnSystemProfile_freeSerializationTargetFn_t)(QnnSystemProfile_SerializationTargetHandle_t serializationTarget);
```

调用方式：
- `providers[i]->QNN_SYSTEM_INTERFACE_VER_NAME.systemProfileFreeSerializationTarget(...)`（调用前判空）。

作用：
- 释放 profile 序列化目标。

用法验证：
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:152:              m_qnnFunctionPointers.qnnSystemInterface.systemProfileFreeSerializationTarget) {`
- `/home/junming/software/qairt/2.42.0.251225/examples/QNN/SampleApp/SampleApp/src/QnnSampleApp.cpp:235:        m_qnnFunctionPointers.qnnSystemInterface.systemProfileFreeSerializationTarget(`

## 备注

- `QNN_INTERFACE_VER_TYPE` / `QNN_SYSTEM_INTERFACE_VER_TYPE` 的函数指针可为 `NULL`，调用前必须判空。
- MLLM 当前主路径重点使用 `backend/context/graph/device/profile` 与 `systemContextGetBinaryInfo`。
- 高级接口（如 section update / incremental binary / async context list）在 sample 中可见，但在 MLLM 里不一定默认启用。