# Installing the metis stack (for the worlds)

Status: written from the repos' READMEs, scripts and CI on 2026-10-30. **Not yet run end to end**: pascal-env (s-694ed091) is its first run; correct this file from that report. Where this and a repo's own README or script disagree, they win.

All repositories are sibling checkouts in one workspace directory; the tools find each other as siblings. Python 3.12 is required (metispy: `requires-python >= 3.12`). Disk: about 2.3 GB of ALFWorld games, 3.1 GB for the E2B model, plus builds.

## Three venvs, on purpose
| venv | what | who needs it |
|---|---|---|
| `metis-agent/py/.venv` | the agent service, llama-cpp-python | `alfworld/demo.sh` looks for it here |
| `metis-worlds/alfworld/.venv` | ALFWorld 0.4.2, metispy, semantic-world, metis_agent | `alfworld/setup.sh` makes it |
| `.venv` at the workspace root | the editable packages and the model download | repo tests |

## 1. Repositories
```
git clone https://github.com/metis-lang-dev/metis-lang.git     # master
git clone https://github.com/metis-lang-dev/metispy.git        # master
git clone https://github.com/metis-lang-dev/metis-catalog.git  # master
git clone https://github.com/metis-lang-dev/metis-loop.git     # master
git clone https://github.com/metis-lang-dev/metis-worlds.git   # main
git clone --recurse-submodules https://github.com/metis-lang-dev/metis-agent.git   # main; third_party/llama.cpp at 0c1e570
git clone https://github.com/metis-lang-dev/fsttm-web.git      # master (only for the root venv's tests)
```

## 2. System packages and the compiler
```
sudo apt install ocaml-nox g++ cmake make git pkg-config python3.12 python3.12-venv
make -C metis-lang metisc
```
`make -C metis-lang && make -C metis-lang check` builds and runs all gates. Go 1.24 (from go.dev if apt is older) is only needed for `metis-agent/go`.

## 3. The agent
```
cd metis-agent/py && python3.12 -m venv .venv
# NVIDIA only, before requirements.txt (set the architecture to your card; 120 is the reference host's):
CUDACXX=/usr/local/cuda/bin/nvcc CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=120" .venv/bin/pip install llama-cpp-python==0.3.36
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e ../../metispy -e ../../metis-catalog -e ../../metis-loop/sdk -e ../../metis-worlds/libs/semantic-world
.venv/bin/pip install --no-deps -e .
cd ../..
```

## 4. The models (`metis-agent/go/models/gemma4/`, gitignored)
```
python3.12 -m venv .venv && .venv/bin/pip install huggingface_hub
.venv/bin/python -c "from huggingface_hub import hf_hub_download as d; print(d('unsloth/gemma-4-E2B-it-GGUF','gemma-4-E2B-it-Q4_K_M.gguf',local_dir='metis-agent/go/models/gemma4'))"
sha256sum metis-agent/go/models/gemma4/*.gguf
```
| file | repository | bytes | sha256 |
|---|---|---|---|
| `gemma-4-E2B-it-Q4_K_M.gguf` (the live model) | `unsloth/gemma-4-E2B-it-GGUF` | 3106738272 | `740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8` |
| `gemma-4-E4B-it-Q5_K_M.gguf` (experiments) | `unsloth/gemma-4-E4B-it-GGUF` | 5481798784 | `a5d6e634db151368d2caa4270fd32ab604d96c2d1291950586989f46d8e17d36` |

A mismatch means another build: do not use the file.

## 5. ALFWorld
```
cd metis-worlds/alfworld
python3.12 -m venv .venv     # setup.sh keeps an existing venv; its own `python3` may be older than 3.12
./setup.sh                   # alfworld[full]==0.4.2, its games into data/
./setup.sh --check
.venv/bin/pip install pytest
ALFWORLD_DATA=$PWD/data METISC=<workspace>/metis-lang/src/metisc .venv/bin/python -m pytest -q tests
```
The demo defaults to `.worlds/alf` and `.worlds/alfworld-data`, so point it at what `setup.sh` made:
```
export ALFWORLD_DATA=$PWD/data METIS_ALF_PY=$PWD/.venv/bin/python METIS_AGENT=<workspace>/metis-agent
./demo.sh --tw               # http://127.0.0.1:8398/world.html?live=1
```
Say "put the tomato in the microwave". See `alfworld/docs/DEMO.md`.

## 6. The root venv and the rest
```
.venv/bin/pip install -e metispy -e metis-catalog -e metis-loop -e metis-loop/sdk -e fsttm-web -e metis-worlds/libs/semantic-world
cd metispy && ../.venv/bin/python -m pytest -q --deselect tests/road/test_sumo.py --deselect tests/fw/test_evaluator.py::test_sumo_closed_loop_through_framework --ignore=tests/kitchen
cd ../metis-catalog && ../.venv/bin/python -m pytest -q
cd ../metis-worlds/libs/semantic-world && ../../../.venv/bin/python -m pytest -q
```
Agent: `cd metis-agent/go && METIS_LANG_DIR=../../metis-lang ./build.sh test`, and from `metis-agent`, `py/.venv/bin/python -m pytest py -q`. Other worlds: `minihack/setup.sh`, `scienceworld/setup.sh`, each with its own layout.
