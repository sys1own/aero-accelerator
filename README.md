# Aero-Accelerator

**Aero-Accelerator** is a high-performance, graph-based JIT compiler designed to bridge the gap between Python and Rust[cite: 2]. It transpiles numeric Python functions into native Rust extension modules, giving your code a significant speed boost while maintaining the familiar Python interface[cite: 2].

The generated artifacts (`.so`, `.dylib`, or `.pyd`) act as drop-in replacements for your original modules, allowing for seamless integration into existing pipelines[cite: 2].

---

## Quick Start

Getting started is straightforward. To compile a numeric function, point the `accelerate` CLI to your Python entry file[cite: 2].

```bash
# Example: Compiling a Fibonacci function
cat > slow.py <<'PY'
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
PY

# Build the Rust extension
accelerate build --entry slow.py --function fib --output ./libs

```

Now, import it as you would any normal Python module:

```python
import sys
sys.path.insert(0, './libs')
import slow
print(slow.fib(35))

```

---

## Installation

Aero-Accelerator requires a standard Rust and C toolchain.

1. **System Requirements:**
* Python 3.9+


* Rust toolchain (get it at [rustup.rs](https://rustup.rs/)).


* A C toolchain (`gcc` or `clang`) for linking.


* `m4` (required for GMP/MPFR support).




2. **Installation Commands:**

```bash
git clone [https://github.com/sys1own/aero-accelerator.git](https://github.com/sys1own/aero-accelerator.git)
cd aero-accelerator
# Install in editable mode
pip install -e .

```

---

## Configuration (`accelerate.toml`)

You can customize the compilation profile and precision handling by placing an `accelerate.toml` configuration file in your project root:

```toml
[build]
output = "./libs"

[precision_shield]
default_float = "f64"  # Force default float precision scaling

```

---

## How it Works

Aero-Accelerator follows a robust, multi-stage compilation pipeline to ensure both performance and safety:

1. **Analysis:** It parses the Python `ast` and normalizes it into a universal AST.


2. **Graph Construction:** It builds a graph-based intermediate representation.


3. **Precision Shield:** It performs type inference, choosing between `i64` and `f64` types based on usage.


4. **Codegen & Build:** It generates a Rust crate, formats it, and builds it in release mode.


5. **Caching:** Results are cached by SHA-256 hash to ensure repeat builds are nearly instantaneous.



---

## Command Line Reference

| Option | Description |
| --- | --- |
| `--entry` | Path to the source file (Required).

 |
| `--function` | Single function to compile.

 |
| `--functions` | Comma-separated list for multi-function modules.

 |
| `--output` | Output directory (default `./libs`).

 |
| `--fallback` | If compilation fails, generate a pure-Python wrapper instead.

 |
| `--no-cache` | Force a full rebuild, ignoring the `.accelerate-cache/`.

 |
| `--no-clean` | Preserve temporary generated Rust source crates for debugging. |
| `--verbose` | Print detailed internal AST transformation and lowering logs. |

---

## Best Practices & Supported Syntax

Aero-Accelerator is optimized for numeric Python.

### Supported Constructs

* **Statements:** `def` with positional args, `if`/`elif`/`else`, `while` loops, `for` loops (with `range`), assignments, and augmented assignments (`+=`, etc.).


* **Math:** Native arithmetic, bitwise operators, and common functions like `abs`, `round`, `pow`, `min`, `max`.


* **Library Support:** Standard `math.*` functions (e.g., `sin`, `sqrt`, `exp`) are fully supported when `import math` is present at the module level.



### Type Inference

By default, functions use `i64`. The **Precision Shield** automatically promotes to `f64` if it detects float literals, division, or scientific math functions. You can also force `f64` mode via the `accelerate.toml` configuration file.

---

## Important Considerations

* **I/O Safety:** To ensure performance and safety, I/O operations (e.g., `print()`, `open()`, `requests.get()`) are not supported and will abort the build. Use `--fallback` if you need to maintain compatibility while keeping the original file structure.


* **Boolean Logic Constraints:** The generated Rust return type must evaluate strictly to a numeric scalar value (`i64`/`f64`). Convert conditional statements directly into integer states instead of returning raw booleans:


```python
# Avoid this:
def is_positive(x):
    return x > 0

# Do this:
def check_positive(x):
    if x > 0:
        return 1
    return 0

```

* **Scope:** User-defined function calls are currently restricted; stick to built-ins, `math.*`, and recursive calls.


---

## CI/CD Integration

Aero-Accelerator is designed for automated environments. Use the `--ci` flag to suppress non-essential output and ensure clean exit codes.

**Example GitHub Actions Setup:**

```yaml
- run: sudo apt-get update && sudo apt-get install -y m4
- run: pip install -e '.[dev]'
- run: pytest -q

```

---

## License

MIT – See the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

---
