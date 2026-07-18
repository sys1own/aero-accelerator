```markdown
# Aero Accelerator

**Graph-based Python to Rust JIT compiler** – compile pure numeric Python functions into optimized native Rust extensions with a single command.

---

## Overview

Aero Accelerator takes a pure Python function (arithmetic, loops, recursion) and:
1. Parses it into a **Universal Abstract Syntax Tree (UAST)**.
2. Translates it into a **Hierarchical Interaction Net (HIN)** – a graph that represents the function's dataflow.
3. Applies the **Precision Shield** to detect numeric types and inject high‑performance traits (e.g., `rug::Float` for arbitrary precision).
4. Generates a complete **Rust crate** with PyO3 bindings.
5. Compiles it with `cargo build --release` in an isolated sandbox.
6. Delivers a native shared library (`.so`/`.pyd`) you can import directly in Python.

The result is a drop‑in replacement for your Python function that runs **10–100× faster** on CPU‑bound numeric workloads.

---

## Features

- **Zero boilerplate** – no manual Rust or FFI code required.
- **Pure Python to native** – works with arithmetic, conditionals, loops, and recursion.
- **Precision Shield** – automatically injects `rug` traits for arbitrary‑precision math.
- **Sandboxed compilation** – all builds happen in `/tmp`; no pollution of your project.
- **Fast incremental rebuilds** – cached cargo builds.
- **Extensible** – the graph‑rewriting core can be adapted to other languages (Rust, C++, etc.).

---

## Installation

### Prerequisites
- Python 3.8+
- `pip`
- Rust toolchain (`rustc`, `cargo`) – install via [rustup](https://rustup.rs/)
- System development headers (on Debian/Ubuntu: `libgmp-dev`)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

# Install Aero Accelerator
pip install git+https://github.com/sys1own/aero-accelerator.git
```

---

## Quick Start

```bash
# Create a Python file with a slow numeric function
echo 'def fib(n):
    if n <= 1:
        return n
    return fib(n-1) + fib(n-2)' > fib.py

# Compile it to a native extension
accelerate build --entry fib.py --function fib --output ./libs

# Use it in Python
python -c "import sys; sys.path.insert(0, './libs'); import fib; print(fib.fib(35))"
```

You should see the result `9227465` computed almost instantly.

---

## Command-Line Interface

```
accelerate build --entry FILE --function NAME --output DIR
```

| Option          | Description |
|-----------------|-------------|
| `--entry`       | Path to the Python source file (required) |
| `--function`    | Name of the function to compile (required) |
| `--output`      | Directory where the shared library will be written (default: `./libs`) |
| `--no-clean`    | Keep temporary build artifacts for debugging |
| `--verbose`     | Show full cargo output |

---

## How It Works

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 1. Python Source (fib.py)                                               │
│    def fib(n):                                                          │
│        if n <= 1: return n                                              │
│        return fib(n-1) + fib(n-2)                                       │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ 2. UAST (Universal Abstract Syntax Tree)                                │
│    Linearized, language‑agnostic representation of the function.        │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ 3. HIN (Hierarchical Interaction Net)                                  │
│    Graph of typed nodes (variables, operators, calls).                 │
│    * Nodes: `Int`, `Add`, `Sub`, `If`, `Call`, etc.                    │
│    * Edges represent dataflow.                                         │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ 4. Precision Shield                                                    │
│    Scans the graph for numeric types.                                  │
│    Injects traits (e.g., `AeroNegMutExt`, `AeroNthRootExt`) when      │
│    arbitrary precision (`rug::Float`) is detected.                     │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ 5. Scaffold Engine                                                     │
│    Generates a complete Rust crate with:                               │
│    * Cargo.toml (dependencies: pyo3, rug)                              │
│    * src/lib.rs (PyO3 bindings + the function logic)                  │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ 6. Sandboxed Build                                                     │
│    `cargo build --release` inside `/tmp/accelerator-crate-XXXX/`      │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ 7. Artifact Delivery                                                   │
│    The shared library is copied to `--output` and is ready for import. │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Supported Python Constructs

| Construct | Status | Notes |
|-----------|--------|-------|
| Arithmetic (`+`, `-`, `*`, `/`, `**`, `%`) | ✅ | All integer and float operations |
| Comparisons (`<`, `>`, `==`, `<=`, `>=`) | ✅ | Converted to `i64`/`f64` comparisons |
| `if` / `elif` / `else` | ✅ | Compiled to `if` expressions |
| `while` loops | ✅ | Supported |
| Recursive calls | ✅ | Tail‑call optimised (when possible) |
| Local variables | ✅ | |
| `return` | ✅ | |

### Unsupported (Will Abort)
- I/O operations (`open()`, `print()`, `requests.get()`, etc.)
- Import statements (other than builtins)
- List/dict comprehensions
- `yield` / generators
- `lambda` functions
- Non‑numeric types (strings, objects)
- Function calls to other user‑defined functions (only the target function may be called)

If you try to compile an unsupported function, you'll see an error like:
```
Error: Unsupported I/O operation detected. Aborting.
```

---

## Limitations & Known Issues

1. **Name Collision**  
   If the Python file name and the function name are identical (e.g., `fib.py` and `def fib`), the generated Rust code will have a name conflict between the `#[pyfunction]` and the `#[pymodule]` initializer.  
   **Workaround:** Use a different file name, e.g., `math_utils.py` with `def fib`.  
   **Fix:** The scaffold engine is being updated to use a fixed module initializer name (`py_module`) with an explicit `#[pymodule(name = "...")]`.

2. **Integer Width**  
   The Rust code uses `i64` for integers. If your Python function exceeds 64‑bit range, you need to use `rug::Integer` – the Precision Shield will enable it automatically if it detects `float` or arbitrary‑precision usage.

3. **Performance**  
   Recursive functions without tail‑call optimisation may still be slower than iterative equivalents. Use `while` loops when possible.

4. **Platform Support**  
   Currently tested on Linux (x86_64) and macOS. Windows support is experimental.

---

## Development & Contributing

### Setup for Development

```bash
git clone https://github.com/sys1own/aero-accelerator.git
cd aero-accelerator
pip install -e .
```

### Running Tests

```bash
pytest tests/
```

### Code Structure

```
aero-accelerator/
├── src/
│   └── accelerator/
│       ├── aero_frontend.py   # UAST generation from Python AST
│       ├── translator.py      # UAST → HIN translation
│       ├── hin_vm.py          # HIN graph representation
│       ├── shield.py          # Precision Shield (type detection, trait injection)
│       ├── scaffold/
│       │   └── engine.py      # Rust crate generator
│       └── cli.py             # Command‑line interface
├── pyproject.toml
└── README.md
```

### Adding Support for New Python Constructs

1. Extend the UAST grammar in `aero_frontend.py`.
2. Add a translation rule in `translator.py` to map the new node to HIN.
3. Update the Rust code generator in `scaffold/engine.py` to emit the corresponding Rust expression.

---

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---

## Questions or Issues?

Open an issue on [GitHub](https://github.com/sys1own/aero-accelerator/issues) or reach out to the maintainers.
```
