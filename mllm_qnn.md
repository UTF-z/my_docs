# MLLM+QNN梳理

## QNN Backend

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
    cd /home/junming/software/mllm
    source /home/junming/software/qcom-wayland_sdk/environment-setup-armv8-2a-qcom-linux #交叉编译工具链
    export QAIRT_SDK_ROOT=/home/junming/software/qairt/2.42.0.251225
    export PATH="$QAIRT_SDK_ROOT/.venv/bin:$PATH"

    cmake -S /home/junming/software/mllm \
    -B /home/junming/software/mllm/build-linux-oe-aarch64-qnn \
    -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE=$OE_CMAKE_TOOLCHAIN_FILE \
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