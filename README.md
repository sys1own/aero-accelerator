# accelerator

**Graph-based Python to Rust JIT compiler.**

`accelerate` takes a pure numeric Python function and turns it into a compiled Rust extension module using PyO3. The result is the same function running as native code and importable from Python like any other module.

## Install

```bash
pip install ./accelerator
```

Requirements:

- Python 3.9+
- Rust (`cargo` and `rustc`) from <https://rustup.rs/>
- `m4` for building the `rug` crate (Debian/Ubuntu: `sudo apt-get install m4`)

## Quick example

```bash
# slow.py
cat > slow.py <<'PY'
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
PY

accelerate build --entry slow.py --function fib --output ./libs
python - <<'PY'
import sys, time
sys.path.insert(0, './libs')
import slow
t0 = time.perf_counter()
print(slow.fib(35))
print('rust:', time.perf_counter() - t0)
PY
```

The build produces `./libs/slow.cpython-<platform>-<arch>.so`. Import it as a normal Python module.

## CLI

```
accelerate build --entry FILE --function NAME  [--output DIR]
```

| Option | Description |
|--------|-------------|
| `--entry` | Python source file (required) |
| `--function` | Single function to compile |
| `--functions` | Comma-separated list of functions to compile into one module |
| `--output` | Output directory (default: `./libs`, or `[build].output` from config) |
| `--fallback` | On failure, write a pure-Python wrapper module |
| `--no-cache` | Force a rebuild instead of reusing `.accelerate-cache/` |
| `--no-clean` | Keep the temporary Rust crate for debugging |
| `--no-benchmark` | Skip the Rust vs Python speedup comparison |
| `--benchmark-args` | Arguments for the benchmark, e.g. `35` or `(10, 2.5)` |
| `--verbose` | Print full `cargo` output |
| `--ci` | Suppress non-essential output and exit with a clean status code |
| `--target` | Cargo target triple for cross-compilation |
| `--config` | Path to an `accelerate.toml` config file |

## Supported Python

Only pure numeric logic is compiled directly:

- arithmetic (`+`, `-`, `*`, `/`, `//`, `%`, `**`)
- comparisons, `and`, `or`, `not`
- `if` / `elif` / `else`
- `while` loops
- `for` loops over `range(...)`
- `return`
- recursive calls to the function itself
- `abs`, `round`, `pow`, `min`, `max`
- `math.sqrt`, `math.sin`, `math.cos`, `math.tan`, `math.exp`, `math.log`, `math.log10`, `math.ceil`, `math.floor`, `math.trunc`

If the source contains I/O (`open()`, `requests.get()`, `with open(...)`), the tool aborts with:

```
Unsupported I/O operation detected. Aborting.
```

Use `--fallback` to generate a pure-Python wrapper instead of compiling.

## Configuration

Create an `accelerate.toml` in the project directory or any parent directory:

```toml
[build]
output = "./libs"
cache = true
verbose = false

[precision_shield]
enable_rug = true

[benchmark]
args = "35"
```

Command-line flags always override config values.

## How it works

1. Parse the Python source into an AST and a normalized graph representation.
2. Analyze the graph to choose Rust types and traits (`i64`, `f64`, optional `rug`).
3. Generate a Rust crate with `#[pyfunction]` bindings.
4. Run `cargo fmt` and `cargo build --release` in a temporary directory.
5. Cache the resulting shared library in `.accelerate-cache/` keyed by source hash.
6. Copy the library to `--output` and run a quick Rust-vs-Python benchmark.

## Development

```bash
git clone https://github.com/sys1own/aero-accelerator.git
cd aero-accelerator
pip install -e .
pytest
```

## License

MIT – see [LICENSE](LICENSE).
