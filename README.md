# Aero Accelerator

**Graph-based Python to Rust JIT compiler** – compile pure numeric Python functions into optimized native Rust extensions with a single command.

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![Rust](https://img.shields.io/badge/rust-1.70+-orange.svg)](https://rustup.rs)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](https://github.com/sys1own/aero-accelerator/actions)

---

## Overview

Aero Accelerator is a **production‑grade JIT compiler** that transforms pure numeric Python functions into compiled Rust extensions with zero boilerplate. It uses a graph‑rewriting pipeline (UAST → HIN → Precision Shield → Scaffold → Cargo) to generate idiomatic, optimized Rust code with PyO3 bindings.

**Key benefits:**
- **10–100× speedup** on CPU‑bound numeric workloads
- **No manual Rust or FFI code** – just Python
- **Sandboxed compilation** – all builds happen in isolated temporary directories
- **Smart caching** – subsequent builds are nearly instant
- **Fallback mode** – pure Python wrapper if compilation fails
- **Multi‑function support** – compile entire modules at once

---

## Installation

### Prerequisites

| Dependency | Version | Installation |
|------------|---------|--------------|
| Python | 3.9+ | [python.org](https://python.org) |
| Rust toolchain | 1.70+ | [rustup.rs](https://rustup.rs) |
| `m4` macro processor | latest | `sudo apt-get install m4` (Debian/Ubuntu), `brew install m4` (macOS) |
| `libgmp-dev` | latest | `sudo apt-get install libgmp-dev` (Debian/Ubuntu) |

### Install from PyPI (coming soon)

```bash
pip install aero-accelerator
```

### Install from source

```bash
git clone https://github.com/sys1own/aero-accelerator.git
cd aero-accelerator
pip install -e .
```

### Verify installation

```bash
accelerate --help
```

---

## Quick Start

```bash
# 1. Create a Python file with a slow numeric function
cat > fib.py <<'EOF'
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
EOF

# 2. Compile it to a native extension
accelerate build --entry fib.py --function fib --output ./libs

# 3. Use it in Python
python -c "
import sys
sys.path.insert(0, './libs')
import fib
print(fib.fib(35))  # 9227465, computed almost instantly
"
```

**Expected output:**
```
✅ Build succeeded! Compiled fib -> ./libs/fib.cpython-39-x86_64-linux-gnu.so
📊 Performance:
   Python: 2.34s
   Rust:   0.05s
   Speedup: 46.8x
```

---

## Architecture

The compilation pipeline transforms Python source into native machine code through several stages:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. Python Source (fib.py)                                                   │
│    def fib(n):                                                              │
│        if n <= 1: return n                                                  │
│        return fib(n-1) + fib(n-2)                                           │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 2. UAST (Universal Abstract Syntax Tree)                                   │
│    Language-agnostic, linearized representation.                           │
│    Nodes: FunctionDef, If, Return, BinOp, Call, Name, Constant             │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 3. HIN (Hierarchical Interaction Net)                                     │
│    Graph of typed nodes connected by ports.                               │
│    * `Int` / `Float` nodes for literals                                   │
│    * `Add`, `Sub`, `Mul`, `Div` for arithmetic                            │
│    * `If` node with condition and branch edges                            │
│    * `Call` node with function reference                                  │
│    * `Return` node for function output                                    │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 4. Precision Shield                                                       │
│    Scans the graph for numeric types and operations.                      │
│    Injects high-performance traits:                                       │
│    * `AeroNegMutExt` – zero-allocation negative mutation                  │
│    * `AeroNthRootExt` – nth-root operations                              │
│    * Optional `rug::Float` for arbitrary precision                       │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 5. Scaffold Engine                                                        │
│    Generates a complete Rust crate:                                       │
│    ```                                                                    │
│    Cargo.toml                                                             │
│      [package] name = "fib"                                               │
│      [dependencies] pyo3 = "0.20", rug = "1.24"                          │
│    src/lib.rs                                                             │
│      #[pyfunction] fn fib(n: i64) -> i64 { ... }                         │
│      #[pymodule(name = "fib")]                                           │
│      fn py_module(_py: Python, m: &PyModule) -> PyResult<()> { ... }    │
│    ```                                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 6. Sandboxed Build                                                       │
│    * Temporary directory: `/tmp/accelerator-crate-XXXX/`                  │
│    * `cargo fmt` – formats generated code                                │
│    * `cargo build --release` – compiles to shared library                │
│    * Cache stored in `.accelerate-cache/` (keyed by source hash)         │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 7. Artifact Delivery                                                     │
│    * Shared library copied to `--output` directory                       │
│    * Benchmark runs (Rust vs Python)                                     │
│    * Temp directory cleaned (unless `--no-clean`)                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## CLI Reference

### `build` – compile a Python function to a Rust extension

```bash
accelerate build --entry FILE --function NAME [OPTIONS]
```

#### Required arguments

| Option | Description |
|--------|-------------|
| `--entry` | Path to the Python source file |
| `--function` | Name of a single function to compile (use with `--functions` or alone) |
| `--functions` | Comma-separated list of functions to compile into one module |

#### Optional arguments

| Option | Description | Default |
|--------|-------------|---------|
| `--output` | Output directory for the shared library | `./libs` or `[build].output` from config |
| `--fallback` | On failure, generate a pure‑Python wrapper module | `false` |
| `--no-cache` | Force a rebuild; ignore `.accelerate-cache/` | `false` |
| `--no-clean` | Keep the temporary Rust crate for debugging | `false` |
| `--no-benchmark` | Skip the Rust vs Python speed comparison | `false` |
| `--benchmark-args` | Arguments for the benchmark (e.g., `35` or `(10, 2.5)`) | `None` |
| `--verbose` | Print full `cargo` output | `false` |
| `--ci` | Suppress non‑essential output for CI/CD | `false` |
| `--target` | Cargo target triple (e.g., `aarch64-apple-darwin`) | host triple |
| `--config` | Path to an `accelerate.toml` config file | auto‑discover |
| `-h, --help` | Show help message | — |

#### Examples

```bash
# Single function
accelerate build --entry math_utils.py --function fib --output ./libs

# Multiple functions
accelerate build --entry math_utils.py --functions fib,factorial,sqrt --output ./libs

# With fallback and verbose output
accelerate build --entry risky.py --function unsafe --fallback --verbose

# Cross‑compile for ARM64
accelerate build --entry fib.py --function fib --target aarch64-apple-darwin
```

---

## Configuration (`accelerate.toml`)

Project-level configuration file. The tool looks for `accelerate.toml` in the current directory and its parents.

### Full example

```toml
[build]
output = "./libs"          # Default output directory
cache = true               # Enable caching
verbose = false            # Suppress cargo output by default
clean = true               # Clean temp directories after build

[precision_shield]
enable_rug = true          # Enable arbitrary precision via rug
default_float = "double"   # double, quad, arbitrary

[benchmark]
enabled = true             # Run benchmark after build
args = "35"                # Default arguments for benchmark

[fallback]
enabled = true             # Generate Python wrapper on failure

[ci]
mode = "production"        # production, test, dev
```

### Precedence order

1. **Command-line flags** (highest)
2. **Environment variables** (`ACCELERATE_*`)
3. **`accelerate.toml` config**
4. **Built-in defaults** (lowest)

---

## Supported Python Features

### ✅ Fully supported

| Construct | Example | Notes |
|-----------|---------|-------|
| Arithmetic | `a + b`, `a * b`, `a / b`, `a // b`, `a % b`, `a ** b` | Integer and float |
| Comparisons | `a < b`, `a > b`, `a <= b`, `a >= b`, `a == b`, `a != b` | |
| Logical | `a and b`, `a or b`, `not a` | Short-circuit evaluated |
| Conditionals | `if a < b: return a else: return b` | `elif` supported |
| Loops | `while i < n: i += 1` | |
| For loops | `for i in range(n): ...` | Only `range()` supported |
| Recursion | `def fib(n): return fib(n-1) + fib(n-2)` | Self‑recursion only |
| Return | `return expr` | Single or multiple |
| Built-in functions | `abs()`, `round()`, `pow()`, `min()`, `max()` | |
| Math functions | `math.sqrt()`, `math.sin()`, `math.cos()`, `math.tan()` | Requires `import math` |
| Math functions | `math.exp()`, `math.log()`, `math.log10()` | |
| Math functions | `math.ceil()`, `math.floor()`, `math.trunc()` | |
| Local variables | `x = 5; y = x * 2` | Type-inferred |

### ❌ Not supported (compilation aborts)

| Construct | Reason | Error message |
|-----------|--------|---------------|
| I/O | `open()`, `requests.get()`, `with open(...)` | "Unsupported I/O operation detected. Aborting." |
| Imports | `import pandas`, `from numpy import *` | "Import statements not supported" |
| Comprehensions | `[x*x for x in range(10)]` | "List comprehension not supported" |
| Generators | `def gen(): yield x` | "Generator functions not supported" |
| Lambdas | `lambda x: x + 1` | "Lambda functions not supported" |
| Classes | `class MyClass:` | "Classes not supported" |
| Strings | `"hello" + "world"` | "String operations not supported" |
| Function calls (external) | `helper(x)` (not defined in same file) | "Only recursive calls supported" |

---

## Performance Considerations

### What makes a function a good candidate?

- **CPU‑bound** – spends most time in arithmetic, not I/O
- **Numeric** – uses integers, floats, and math operations
- **Predictable** – no dynamic dispatch or string manipulation
- **Recursive or iterative** – loops and recursion work well
- **Pure** – no side effects, mutable state, or global variables

### Expected speedups

| Workload | Typical speedup | Best case |
|----------|----------------|-----------|
| Recursive Fibonacci | **20–50×** | 100×+ |
| Mandelbrot set | **15–40×** | 80× |
| Monte Carlo simulation | **30–60×** | 120×+ |
| N‑body simulation | **25–50×** | 90× |
| Neural network training loops | **10–30×** | 60× |

### Why Rust?

- **Zero-cost abstractions** – no runtime overhead
- **LLVM optimizations** – aggressive inlining, vectorization, unrolling
- **No GIL** – true parallelism possible
- **Memory safety** – no segmentation faults or buffer overflows
- **FFI efficiency** – PyO3 bindings are fast and safe

---

## Error Handling & Debugging

### Common error messages

| Error | Cause | Solution |
|-------|-------|----------|
| `No function named 'foo' found` | Function not defined in file | Check spelling and scope |
| `entry file not found: foo.py` | File doesn't exist | Provide absolute path |
| `Unsupported I/O operation detected` | `open()` or `requests.get()` used | Remove I/O or use `--fallback` |
| `cargo build failed` | Rust compilation error | Run with `--verbose` to see details |
| `name collision in Rust code` | File name == function name | Fixed in v0.2.0 – now uses separate names |

### Debugging a failed build

```bash
# 1. Run with verbose output
accelerate build --entry fib.py --function fib --verbose

# 2. Keep the temporary crate
accelerate build --entry fib.py --function fib --no-clean

# 3. Inspect the generated Rust code
cat /tmp/accelerator-crate-*/src/lib.rs

# 4. Manually build the crate to see full errors
cd /tmp/accelerator-crate-*
cargo build --release
```

### Runtime errors in the compiled module

If the compiled function panics or returns incorrect results:

```bash
# 1. Generate a pure‑Python fallback for comparison
accelerate build --entry fib.py --function fib --fallback

# 2. Compare Rust vs Python results
python -c "
import sys; sys.path.insert(0, './libs')
import fib_rust, fib_fallback
assert fib_rust.fib(35) == fib_fallback.fib(35)
print('Match!')"
```

---

## CI/CD Integration

### GitHub Actions example

```yaml
name: Build and Test
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - uses: actions-rs/toolchain@v1
        with:
          toolchain: stable
      - run: sudo apt-get install -y m4 libgmp-dev
      - run: pip install aero-accelerator
      - run: accelerate build --entry fib.py --function fib --ci
      - run: python -c "import sys; sys.path.insert(0, './libs'); import fib; fib.fib(35)"
```

### Docker image

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl m4 libgmp-dev build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y -q
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install aero-accelerator

WORKDIR /app
```

---

## Development

### Setting up a development environment

```bash
git clone https://github.com/sys1own/aero-accelerator.git
cd aero-accelerator
python -m venv venv
source venv/bin/activate
pip install -e .[dev]
```

### Running tests

```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_name_collision.py

# Run with coverage
pytest --cov=accelerator tests/
```

### Code structure

```
aero-accelerator/
├── src/
│   └── accelerator/
│       ├── __init__.py       # Package exports
│       ├── cli.py            # Command-line interface
│       ├── aero_frontend.py  # UAST generation (Python AST → UAST)
│       ├── translator.py     # UAST → HIN translation
│       ├── hin_vm.py         # HIN graph representation
│       ├── shield.py         # Precision Shield (type detection, trait injection)
│       ├── errors.py         # Error classification and messaging
│       └── scaffold/
│           └── engine.py     # Rust crate generator
├── tests/
│   ├── test_basic.py
│   ├── test_name_collision.py
│   ├── test_multi_function.py
│   ├── test_fallback.py
│   ├── test_cache.py
│   └── test_config.py
├── pyproject.toml
├── accelerate.toml
└── README.md
```

### Contributing

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/awesome`
3. **Commit** your changes: `git commit -m 'Add awesome feature'`
4. **Push** to the branch: `git push origin feature/awesome`
5. **Open** a Pull Request

Please ensure:
- All tests pass (`pytest`)
- Code is formatted (`black` for Python, `rustfmt` for Rust templates)
- Documentation is updated
- New features include tests

---

## Frequently Asked Questions

### Q: Why is my compiled function slower than Python?

**A:** Make sure the function is:
- **CPU‑bound** (not I/O or memory‑bound)
- **Using numeric types** (integers, floats)
- **Not calling external libraries** (numpy, pandas)
- **Using loops or recursion** (overhead is amortized)

### Q: Can I compile functions that use `numpy`?

**A:** No – `numpy` operations are C‑optimized. Aero Accelerator is for pure Python numeric code.

### Q: Why do I need Rust installed?

**A:** The tool doesn't provide a pre‑compiled binary; it generates Rust source and compiles it on your machine for maximum optimization.

### Q: Does it work on Windows?

**A:** Yes, but you need:
- **Rust** – install via `rustup`
- **Visual Studio C++ Build Tools** (for linking)
- **m4** – via `choco install m4` or similar

### Q: What about pyproject.toml support?

**A:** Planned for v0.3.0. You'll be able to define accelerators in your `pyproject.toml`.

### Q: Can I customize the generated Rust code?

**A:** Not directly, but you can:
- Use `--no-clean` to inspect and modify the temp crate
- Add a template directory (future feature)

### Q: Is there a limit on function size?

**A:** No hard limit, but very large functions (>10,000 nodes) may take longer to compile. Use the `--verbose` flag to monitor progress.

---

## License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

---

## Acknowledgements

- Built on the foundations of **Geometry of Interaction** and **Interaction Nets** research
- Uses **PyO3** for Rust/Python bindings
- Uses **rug** for arbitrary‑precision arithmetic
- Inspired by the Aero Topos project

---
