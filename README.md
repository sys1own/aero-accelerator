# accelerator

Graph-based Python to Rust JIT compiler.

`accelerate` takes a slow Python math function, turns it into a small
interaction-net graph, proves simple precision facts about it, and emits a
compiled PyO3 extension module. The result is the same function running as
native Rust called directly from Python.

## Install

```bash
pip install ./accelerator
```

## Quick example

```bash
# slow.py
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

accelerate build --entry slow.py --function fib --output ./libs
python - <<'PY'
import time, slow

t0 = time.perf_counter()
slow.fib(35)
print("rust:", time.perf_counter() - t0)
PY
```

`./libs/slow.cpython-<platform>.so` is produced. Import it like a normal
Python module; `slow.fib` is the compiled Rust version of the original
function.

## Supported Python

Only pure numeric logic is accepted: arithmetic, comparisons, `if`/`while`,
`return`, and recursive calls to the function being compiled. If the code
calls I/O such as `open()` or `requests.get()`, the tool aborts with the
error:

```
Unsupported I/O operation detected. Aborting.
```

## CLI

```
accelerate build --entry FILE --function NAME --output DIR
```

- `--entry`   Python source file to compile.
- `--function` Name of the function to compile.
- `--output`  Directory where the shared library will be written.

## Development

```bash
python -m pip install -e ./accelerator
python -m pytest
```
