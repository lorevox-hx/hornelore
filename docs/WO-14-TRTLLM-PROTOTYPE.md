# WO-14: TensorRT-LLM Prototype for Hornelore

**Status:** FINAL (Claude Execution Version)  
**Created:** 2026-04-12  
**Target hardware:** RTX 5080 Blackwell (GB203, SM120), 16 GB VRAM  
**Prerequisite:** WO-13 testing complete, baseline stability confirmed

---

## Objective

Prototype a TensorRT-LLM inference backend for Hornelore using the **same current Llama-family model** before changing any model family, prompt format, or application behavior.

This work order is a **runtime-performance experiment**, not a model-behavior experiment.

The goal is to determine whether TensorRT-LLM can materially improve:

- Time to first token (TTFT)
- Sustained token generation speed (tok/s)
- VRAM efficiency
- Long-session stability under growing context
- Backend reliability on RTX 5080 Blackwell hardware

While preserving:

- Current Hornelore prompt behavior
- Current runtime71 flow
- Narrator isolation
- Truth / projection / review boundaries
- API to WebSocket to UI streaming contract

---

## Scope

### In scope

- Parallel TensorRT-LLM prototype backend
- Same model family first: Llama 3.1 8B Instruct
- Same Hornelore UI and same application behavior
- Benchmarking against current HuggingFace backend
- Containerized deployment path
- Single-GPU RTX 5080 testing

### Out of scope

- No Hermes migration
- No ChatML migration
- No model-family swap
- No UI rewrite
- No production cutover in this work order
- No assumption that FP4 KV cache is required or production-ready

---

## Non-negotiable rules

1. **Same brain, new engine.** Keep the same Llama-family model first. Do not replace the current backend during the prototype.
2. **Current backend stays on port 8000. TRT prototype runs on port 8010.**
3. **Container-first approach.** Use a pinned container tag rather than ad hoc pip installs.
4. **Do not depend on FP4 for baseline success.** FP4 is an optional later experiment.
5. **Context target for prototype: 16K-32K.** Do not design WO-14 around full 128K local context.

---

## Baseline assumptions

| Parameter | Value |
|-----------|-------|
| Model family | `meta-llama/Llama-3.1-8B-Instruct` |
| Backend | HuggingFace `AutoModelForCausalLM.from_pretrained(...)` |
| Current API port | 8000 |
| GPU | RTX 5080 laptop, 16 GB VRAM |
| Streaming | WebSocket, existing Hornelore UI path |

WO-14 treats this as the gold baseline.

---

## Required folder layout

Create all TRT work under a separate prototype root:

```bash
mkdir -p ~/hornelore-trt/{env,logs,models,hf-cache,engines,scripts,benchmarks,reports}
mkdir -p ~/hornelore-trt/engines/llama31-8b/{ckpt,engine}
```

Layout:

```
~/hornelore-trt/
  env/
    wo14.env
  logs/
    trtllm_api.log
    trtllm_bench.log
  models/
    llama31-8b/                 # optional local HF model mirror
  hf-cache/
  engines/
    llama31-8b/
      ckpt/
      engine/
      config.yml                # warm cache config (Phase 3.3)
  scripts/
    run_trtllm_container.sh
    build_engine_llama31.sh
    serve_engine_llama31.sh
    benchmark_trtllm.sh
    rollback_wo14.sh
  benchmarks/
    prompts_short.json
    prompts_memory.json
    prompts_identity.json
    prompts_long.json
  reports/
    wo14_baseline.md
    wo14_results.md
```

Build and run everything inside the Linux filesystem under WSL, not inside a mounted Windows project path. TensorRT engines are not cross-platform portable.

---

## Version pinning

Pin the container explicitly:

```
nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc11
```

Use that as the default pin unless you have already validated a newer Blackwell-safe tag in your own environment.

---

## Environment file

Create `~/hornelore-trt/env/wo14.env`:

```bash
# ---- WO-14 base environment ----
export TRTLLM_IMAGE="nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc11"
export TRTLLM_CONTAINER_NAME="hornelore-trtllm"
export TRTLLM_HOST_PORT="8010"
export TRTLLM_CONTAINER_PORT="8000"

export HF_MODEL_ID="meta-llama/Llama-3.1-8B-Instruct"
export ENGINE_ROOT="$HOME/hornelore-trt/engines/llama31-8b"
export CKPT_DIR="$ENGINE_ROOT/ckpt"
export ENGINE_DIR="$ENGINE_ROOT/engine"

export TRT_WORK_ROOT="$HOME/hornelore-trt"
export TRT_LOG_DIR="$TRT_WORK_ROOT/logs"
export HF_HOME="$TRT_WORK_ROOT/hf-cache"

# Keep baseline Hornelore untouched on 8000
export HORNELORE_BASELINE_PORT="8000"
export HORNELORE_TRT_PORT="8010"

# Initial practical target for WO-14
export MAX_INPUT_LEN="16384"
export MAX_SEQ_LEN="16384"
export MAX_BATCH_SIZE="1"
export MAX_NUM_SEQS="1"

# Optional WSL2 / NIM note:
# Only use if you test via NVIDIA NIM on WSL2 or hit WSL2 memory-allocation spikes
# export NIM_RELAX_MEM_CONSTRAINTS=1
```

`NIM_RELAX_MEM_CONSTRAINTS=1` is documented by NVIDIA for NIM on WSL2 with Docker on RTX GPUs. It should remain optional here unless you are explicitly running a NIM path or encounter that specific class of WSL2 memory issue.

---

## Phase 1 — Freeze the baseline

### 1.1 Confirm current Hornelore stability

Run:

```bash
bash scripts/test_stack_health.sh
bash scripts/test_startup_matrix.sh
bash scripts/test_all.sh
```

Then manually verify: API healthy, UI healthy, TTS healthy, narrator switch clean, no narrator bleed, no unexpected startup narrator, no session corruption, no drift across repeated runs.

### 1.2 Record baseline environment

```bash
mkdir -p ~/hornelore-trt/reports

{
  echo "=== DATE ===";       date
  echo "=== GPU ===";        nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
  echo "=== CUDA ===";       nvcc --version || true
  echo "=== PYTHON ===";     python --version
  echo "=== DOCKER ===";     docker --version || true
  echo "=== WSL ===";        uname -a
  echo "=== GIT COMMIT ==="; git -C ~/hornelore rev-parse HEAD
} > ~/hornelore-trt/reports/wo14_environment_baseline.txt
```

### 1.3 Baseline benchmark snapshot

Record a manual baseline before touching TRT:

- One short Lori prompt
- One memory-interview turn
- One narrator identity turn
- One 10-20 turn long-session run

Log: TTFT, tok/s, peak VRAM, WebSocket errors, narrator correctness, long-session drift.

---

## Phase 2 — Safe parallel TRT prototype

### 2.1 Start a dedicated TRT container

Create `~/hornelore-trt/scripts/run_trtllm_container.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/hornelore-trt/env/wo14.env"

docker rm -f "$TRTLLM_CONTAINER_NAME" >/dev/null 2>&1 || true

docker run --rm -it \
  --name "$TRTLLM_CONTAINER_NAME" \
  --gpus all \
  --ipc host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -p "${TRTLLM_HOST_PORT}:${TRTLLM_CONTAINER_PORT}" \
  -v "$TRT_WORK_ROOT":"$TRT_WORK_ROOT" \
  -e HF_HOME="$HF_HOME" \
  "$TRTLLM_IMAGE" \
  bash
```

```bash
chmod +x ~/hornelore-trt/scripts/run_trtllm_container.sh
~/hornelore-trt/scripts/run_trtllm_container.sh
```

This follows NVIDIA's container-first path and keeps the prototype isolated from your existing Hornelore process.

---

## Phase 3 — Build the TensorRT-LLM engine

### 3.1 Convert checkpoint (with runtime path detection)

**CRITICAL:** NVIDIA moves the checkpoint conversion path between releases. The build script must detect which path exists inside the container.

Create `~/hornelore-trt/scripts/build_engine_llama31.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/hornelore-trt/env/wo14.env"

docker exec -it "$TRTLLM_CONTAINER_NAME" bash -lc "
  source /etc/profile || true
  mkdir -p $CKPT_DIR $ENGINE_DIR

  echo '[WO-14] Detecting convert_checkpoint path...'

  if python -c 'import tensorrt_llm.models.llama.convert_checkpoint' 2>/dev/null; then
    echo '[WO-14] Using core-library convert_checkpoint'
    python -m tensorrt_llm.models.llama.convert_checkpoint \
      --model_dir $HF_MODEL_ID \
      --output_dir $CKPT_DIR \
      --dtype float16
  elif [ -f /app/tensorrt_llm/examples/llama/convert_checkpoint.py ]; then
    echo '[WO-14] Using legacy examples convert_checkpoint'
    python /app/tensorrt_llm/examples/llama/convert_checkpoint.py \
      --model_dir $HF_MODEL_ID \
      --output_dir $CKPT_DIR \
      --dtype float16
  else
    echo '[WO-14] FATAL: No convert_checkpoint path found. Check container version.'
    exit 1
  fi

  echo '[WO-14] Building engine...'

  trtllm-build \
    --checkpoint_dir $CKPT_DIR \
    --output_dir $ENGINE_DIR \
    --max_input_len $MAX_INPUT_LEN \
    --max_seq_len $MAX_SEQ_LEN \
    --max_batch_size $MAX_BATCH_SIZE \
    --max_num_seqs $MAX_NUM_SEQS

  echo '[WO-14] Engine build complete.'
"
```

```bash
chmod +x ~/hornelore-trt/scripts/build_engine_llama31.sh
~/hornelore-trt/scripts/build_engine_llama31.sh
```

### 3.2 Verify engine artifacts

After build completes, confirm:

```bash
docker exec -it "$TRTLLM_CONTAINER_NAME" ls -lh "$ENGINE_DIR"
```

You should see `.engine` files and `config.json`.

### 3.3 Warm cache config

**This is the biggest real-world win for Hornelore.** Because Hornelore reopens narrators, resumes sessions, and reloads context frequently, warm cache restoration (`enable_block_reuse`) dramatically reduces TTFT on session reopen.

Create the serving config inside the engine directory:

```bash
docker exec -it "$TRTLLM_CONTAINER_NAME" bash -lc "
cat > $ENGINE_DIR/config.yml <<'CONFIGEOF'
kv_cache_config:
  free_gpu_memory_fraction: 0.9
  enable_block_reuse: true

cuda_graph_config:
  enable_padding: true

disable_overlap_scheduler: true
CONFIGEOF
echo '[WO-14] Warm cache config written to $ENGINE_DIR/config.yml'
"
```

This gives you: fast session resume, reduced TTFT on narrator reopen, better memory reuse across turns.

### 3.4 Optional later experiments (NOT baseline)

Do not make these baseline requirements for WO-14 success:

- FP8 model or checkpoint
- FP4 checkpoint
- FP4 KV cache
- Host offload
- Alternate quantization passes

Those can be tested later if the baseline TRT engine is stable.

---

## Phase 4 — Serve the engine on alternate port

Create `~/hornelore-trt/scripts/serve_engine_llama31.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$HOME/hornelore-trt/env/wo14.env"

docker exec -it "$TRTLLM_CONTAINER_NAME" bash -lc "
  source /etc/profile || true
  trtllm-serve $ENGINE_DIR \
    --host 0.0.0.0 \
    --port $TRTLLM_CONTAINER_PORT \
    --backend tensorrt \
    --config $ENGINE_DIR/config.yml
"
```

```bash
chmod +x ~/hornelore-trt/scripts/serve_engine_llama31.sh
~/hornelore-trt/scripts/serve_engine_llama31.sh
```

The `--backend tensorrt` and `--config` flags are made explicit. Some TRT-LLM versions infer the backend, some require it. Being explicit prevents version-drift breakage.

---

## Phase 5 — Smoke test the served engine

From a second shell:

```bash
curl -X POST "http://localhost:8010/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "model": "'"$ENGINE_DIR"'",
    "messages": [
      {"role":"system","content":"You are Lori, a calm interviewer."},
      {"role":"user","content":"Say hello in one sentence."}
    ],
    "max_tokens": 32,
    "temperature": 0
  }'
```

A successful response proves: engine loaded, server listening, OpenAI-compatible endpoint responding.

---

## Phase 6 — Hornelore integration adapter

Do not point Hornelore directly at the TRT prototype until the smoke test passes.

### 6.1 Add a runtime-selectable backend target

Use an environment variable in Hornelore's backend adapter layer:

```bash
export HORNELORE_LLM_BACKEND="hf"          # baseline
# or
export HORNELORE_LLM_BACKEND="trtllm"
export HORNELORE_TRT_BASE_URL="http://127.0.0.1:8010/v1"
```

### 6.2 Adapter requirements

The Hornelore adapter must:

- Preserve current prompt payload generation
- Preserve current stop conditions
- Preserve token caps
- Preserve session and narrator IDs
- Preserve runtime71 routing
- Preserve token streaming shape toward the UI

**No ChatML migration is allowed in WO-14. No model-family change is allowed in WO-14.**

### 6.3 Integration approach — Proxy pattern

Keep `api.py` as the entry point. Replace the model loading path with an HTTP client that forwards to the TRT-LLM container on port 8010. This means:

- `api.py` still owns prompt construction, narrator state, and streaming
- The TRT-LLM container is a dumb inference engine
- Rollback = stop the container, flip `HORNELORE_LLM_BACKEND` back to `hf`

---

## Phase 7 — Benchmark scripts

Create `~/hornelore-trt/scripts/benchmark_trtllm.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

URL="${1:-http://localhost:8010/v1/chat/completions}"
LABEL="${2:-trtllm}"
OUT="${3:-$HOME/hornelore-trt/logs/trtllm_bench.log}"

PROMPT='{
  "model":"benchmark",
  "messages":[
    {"role":"system","content":"You are Lori, a calm interviewer."},
    {"role":"user","content":"Tell me in two sentences how you would begin a life-story interview."}
  ],
  "max_tokens":128,
  "temperature":0
}'

START_NS=$(date +%s%N)
RESP=$(curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "$PROMPT")
END_NS=$(date +%s%N)

ELAPSED_MS=$(( (END_NS - START_NS)/1000000 ))

{
  echo "[WO-14][backend=$LABEL] elapsed_ms=$ELAPSED_MS"
  echo "$RESP"
  echo
} >> "$OUT"

echo "backend=$LABEL elapsed_ms=$ELAPSED_MS"
```

```bash
chmod +x ~/hornelore-trt/scripts/benchmark_trtllm.sh
```

Run baseline and TRT:

```bash
~/hornelore-trt/scripts/benchmark_trtllm.sh http://localhost:8000/v1/chat/completions current_hf
~/hornelore-trt/scripts/benchmark_trtllm.sh http://localhost:8010/v1/chat/completions trtllm
```

---

## Phase 8 — Metrics to log

For both HF baseline and TRT backend, log:

- Cold start model load time
- Warm start model load time
- TTFT (time to first token)
- Full response completion time
- Average tok/s
- Peak VRAM during first response
- Peak VRAM during long session
- VRAM after repeated turns
- GPU utilization during generation
- WebSocket disconnects
- Malformed outputs
- Repeated-token loops
- Frozen generation events
- Narrator identity correctness
- runtime71 behavior correctness
- Long-session degradation threshold

GPU monitoring:

```bash
nvidia-smi --query-gpu=timestamp,name,utilization.gpu,utilization.memory,memory.used,memory.total --format=csv -l 1
```

---

## Phase 9 — Context budget rules

For WO-14 baseline testing, use these context buckets:

| Bucket | Token range |
|--------|-------------|
| Short | 2K-4K |
| Medium | 8K |
| Long | 16K |
| Stretch | 32K |

Do not design initial success criteria around 64K or 128K. If you later test host offload or advanced cache options, record them as separate sub-experiments, not baseline WO-14 pass criteria.

---

## Phase 10 — Success criteria

WO-14 succeeds only if **all** of these hold:

### Functional

- TRT backend starts reliably
- Engine builds successfully
- OpenAI-compatible endpoint responds
- Hornelore UI works without structural rewrite
- Session flow still works
- runtime71 still routes correctly
- No narrator contamination introduced
- No truth-boundary violations introduced

### Performance

Compared to current HF backend, TRT backend shows meaningful measurable improvement in **at least three** of:

- Lower TTFT
- Higher tok/s
- Lower or more stable VRAM usage
- Better long-session stability under deeper context

### Adoption threshold

Recommend follow-up only if one or more of:

- At least ~25% better TTFT
- At least ~25% better tok/s
- Materially better VRAM stability
- Materially better long-session resume behavior

---

## Phase 11 — Rollback plan

The current Hornelore backend remains the default path throughout WO-14.

Create `~/hornelore-trt/scripts/rollback_wo14.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

docker rm -f hornelore-trtllm >/dev/null 2>&1 || true

unset HORNELORE_LLM_BACKEND || true
unset HORNELORE_TRT_BASE_URL || true

echo "WO-14 TRT prototype stopped."
echo "Baseline Hornelore remains on port 8000."
```

```bash
chmod +x ~/hornelore-trt/scripts/rollback_wo14.sh
~/hornelore-trt/scripts/rollback_wo14.sh
bash scripts/test_stack_health.sh
bash scripts/test_startup_matrix.sh
```

TensorRT engines are not portable across platforms. Do not assume you can build on one platform and drop the engine onto another without rebuilding.

---

## Report format

At completion, produce:

1. **Baseline** — current backend path, model, environment, confirmed pre-WO stability status
2. **Prototype** — TensorRT-LLM image tag, engine build method, exact commands used, backend adapter summary, files changed
3. **Functional results** — startup, smoke test, UI streaming, narrator/session integrity
4. **Performance results** — TTFT comparison, tok/s comparison, VRAM comparison, long-session comparison
5. **Stability results** — restart behavior, crash count, session errors, degradation patterns
6. **Go / no-go** — one of: GO (pursue production hardening), NO-GO (retain current HF backend), PARTIAL GO (keep as experimental branch only)
7. **Rollback verification** — rollback steps tested, baseline restored successfully: yes or no

---

## Final operator note

**Do not let WO-14 turn into a stealth model-migration project.**

If the prototype begins requiring prompt-template redesign, ChatML migration, Hermes migration, behavior retuning, or UI protocol rewrites — **stop and split that into a separate work order.**

WO-14 is only about proving whether TensorRT-LLM improves Hornelore as currently designed.
