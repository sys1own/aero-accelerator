# accelerator

**Graph-based Python to Rust JIT compiler.**

`accelerate` takes pure numeric Python functions and compiles them into native
Rust extension modules using PyO3. The generated `.so` (Linux), `.dylib` (macOS),
or `.pyd` (Windows) is a drop-in replacement for the original Python module.

## Installation

Requirements:

- Python 3.9+
- A Rust toolchain (`rustc` and `cargo`) from <https://rustup.rs/>
- `m4` (the `rug` crate needs it to build GMP/MPFR):  
  `sudo apt-get install m4` on Debian/Ubuntu
- A C toolchain (`gcc` or `clang`) for linking

```bash
git clone https://github.com/sys1own/aero-accelerator.git
cd aero-accelerator
pip install -e .
# or, with development/test tools:
pip install -e '.[dev]'
```

The `accelerate` command should now be available.

## Quick start

```bash
cat > slow.py <<'PY'
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)
PY

accelerate build --entry slow.py --function fib --output ./libs
python - <<'PY'
import sys
sys.path.insert(0, './libs')
import slow
print(slow.fib(35))
PY
```

This produces `./libs/slow.cpython-<platform>-<arch>.so`.

## CLI reference

```
accelerate build --entry FILE (--function NAME | --functions A,B,C) [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--entry` | required | Path to the Python source file |
| `--function` | none | Single function to compile |
| `--functions` | none | Comma-separated list of functions compiled into one module |
| `--output` | `./libs` or `build.output` from config | Output directory for the compiled extension |
| `--fallback` | false | On failure, write a pure-Python wrapper module instead |
| `--no-cache` | false | Force a full rebuild instead of reusing `.accelerate-cache/` |
| `--no-clean` | false | Keep the temporary Rust crate in `/tmp/accelerator-crate-*` for debugging |
| `--no-benchmark` | false | Skip the Rust-vs-Python benchmark after a successful build |
| `--benchmark-args` | none | Python literal passed to the benchmark function (e.g. `35` or `(10, 2.5)`). If omitted, a sensible default is used based on the argument count. |
| `--verbose` | false | Print full `cargo` output |
| `--ci` | false | Suppress non-essential output and exit with a clean status code |
| `--target` | none | Cargo target triple for cross-compilation (e.g. `x86_64-unknown-linux-gnu`) |
| `--config` | none | Explicit path to an `accelerate.toml` config file |

At least one of `--function` or `--functions` must be provided.

## Configuration

`accelerate` searches the current working directory and its parents for a file
named `accelerate.toml`. The file uses a simple `key = value` syntax. Lines
starting with `#` are comments. Lists use JSON syntax (`[1, 2, 3]`). Booleans
can be `true`/`false`/`yes`/`no`/`on`/`off`. Strings should be quoted.

Recognized sections and keys:

```toml
[build]
output = "./libs"     # default output directory
cache = true          # enable .accelerate-cache/ (default true)
verbose = false       # show full cargo output (same as --verbose)

[precision_shield]
enable_rug = true     # import rug traits (default true when config is absent)
default_float = ""    # set to "f64" or "double" to force f64 mode

[benchmark]
args = "35"           # default arguments for the benchmark
```

Command-line flags always override config values.

## How it works

1. **Parse** the entry file with the Python `ast` module.
2. **Normalize** it into a small universal AST.
3. **Build** an internal graph-based intermediate representation for analysis.
4. **Analyze** the graph with the precision shield to choose `i64` or `f64`
   types and optional `rug` traits.
5. **Generate** a temporary Rust crate from a template, with one
   `#[pyfunction(name = "<python_name>")]` per requested function and a
   `#[pymodule]` initializer named after the file stem.
6. **Format** the generated code with `cargo fmt`.
7. **Build** the crate in release mode with `cargo build --release`.
8. **Cache** the resulting shared library in `.accelerate-cache/` keyed by a
   SHA-256 hash of the source, function names, target triple, and shield config.
9. **Copy** the artifact to `--output` and run a Rust-vs-Python benchmark for
   the first requested function.

## Supported Python

The transpiler accepts a focused subset of numeric Python.

### Statements

- `def` with positional arguments
- `return <expr>`
- `if` / `elif` / `else`
- `while` loops (condition must be a comparison or boolean of comparisons)
- `for <name> in range(...)` with one or two arguments (no step argument)
- Single-target assignments and tuple/list unpacking from a tuple/list literal
- Augmented assignment (`+=`, `-=`, etc.)
- `pass` and bare expressions are accepted and ignored

### Expressions

- Integer and float literals; `True` and `False` literals
- Variables and arithmetic: `+`, `-`, `*`, `/` (always promotes to `f64`),
  `//` (floor division), `%`, `**`
- Bitwise operators: `<<`, `>>`, `|`, `^`, `&`
- Unary `+`, `-`, `~`
- Comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`
- `abs`, `round`, `pow`, `min`, `max`
- `math.sqrt`, `math.sin`, `math.cos`, `math.tan`, `math.exp`, `math.log`,
  `math.log10`, `math.ceil`, `math.floor`, `math.trunc` (requires
  `import math` at module level)
- Recursive calls to the function being compiled
- Multi-function modules via `--functions a,b`

### Type inference

Functions use `i64` by default. The precision shield switches to `f64` when it
sees a float literal, a `/` operator, or any of `pow`, `sqrt`, `sin`, `cos`,
`tan`, `exp`, `log`, or `log10`. You can also force `f64` with
`[precision_shield] default_float = "f64"`.

## Limitations and known issues

- **Boolean logic in return values**: `return a > 0`, `return a > 0 and b > 0`,
  and `return not (a > 0)` currently fail because the generator emits a Rust
  `bool` expression in a function whose return type is `i64`/`f64`. Use an
  `if`/`else` to return numeric values.
- **Boolean logic on plain variables**: `and`, `or`, and `not` work when
  applied to comparisons (e.g. `if a > 0 and b > 0:`), but not on plain numeric
  variables (e.g. `if a:` or `if not a:`).
- **`import` inside functions** is not supported. Put `import math` at module
  level if you need it.
- **`for` loops** must iterate over `range(...)` with one or two arguments.
  `for i in [1, 2, 3]` or `range(0, 10, 2)` are not supported.
- **`break` / `continue`**, list/dict/set literals (except as tuple-unpack
  sources), subscripting, comprehensions, `lambda`, `yield`, `try`/`except`,
  `with`, classes, and arbitrary function calls are not supported.
- **I/O detection**: `open()`, `print()`, `input()`, `requests.get()`,
  `socket.*`, `os.*`, `subprocess.*`, `sys.*`, and `with` statements abort the
  build with:

  ```
  Unsupported I/O operation detected. Aborting.
  ```

- **Other user-defined functions** cannot be called from the compiled function;
  only builtins, `math.*`, and recursive calls to the target function itself
  are allowed.
- **Return-without-expression** (`return`) is not supported for non-void
  functions.
- The `rug` traits are imported when `enable_rug = true`, but the current
  codegen still uses fixed-width `i64`/`f64`. Arbitrary-precision math is not
  yet generated.

## Error handling and debugging

- Missing `cargo`/`rustc` is reported as a missing-toolchain error.
- Missing `m4` is detected from Cargo output and reported with an install hint.
- Name collisions are classified from `E0428` errors.
- Generic Cargo failures print:

  ```
  Rust compilation failed. Use --verbose to see the full compiler output.
  ```

- Unsupported constructs include the source file path and line number when
  available.
- `--verbose` shows the full `cargo` output, including warnings.
- `--no-clean` leaves the temporary Rust crate behind so you can inspect
  `src/lib.rs`.

## Performance and caching

Repeated builds of the same source, function names, target triple, and shield
config use `.accelerate-cache/` and finish almost instantly. Use `--no-cache` to
force a rebuild. In `--ci` mode the cache is placed under `/tmp` to avoid
polluting the workspace.

After a successful build, `accelerate` runs the compiled function and the
original Python function with the same arguments and prints a speedup. Use
`--no-benchmark` to skip this.

## Fallback mode

If a function cannot be compiled, `--fallback` writes
`<output>/<module_name>.py`, a tiny wrapper that imports the original Python
module and re-exports the requested functions. This lets you keep the same import
path even when Rust code generation is not possible.

## CI/CD integration

Use `--ci` in automated environments to suppress progress and benchmark output.
Cross-compilation can be requested with `--target <triple>`; the target must be
installed in your Rust toolchain.

Example GitHub Actions job:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: "3.11"
- uses: dtolnay/rust-toolchain@stable
- run: sudo apt-get update && sudo apt-get install -y m4
- run: pip install -e '.[dev]'
- run: pytest -q
```

## Development

```bash
pip install -e '.[dev]'
black --target-version py310 src tests
pytest -q
```

The `accelerator` package also exposes public modules:

```python
from accelerator import aero_frontend, translator, hin_vm, shield, engine
```

## FAQ

**Can the file name and function name be the same?**  
Yes. The generated `#[pymodule]` initializer uses the file stem, while the
underlying Rust function is prefixed with `_accel_` to avoid the collision.

**Can I compile more than one function at once?**  
Yes: `accelerate build --entry file.py --functions f,g --output ./libs`.

**What if my function does I/O?**  
The build aborts with `Unsupported I/O operation detected. Aborting.`. Use
`--fallback` to generate a pure-Python wrapper instead.

**Does `accelerate.toml` support nested tables?**  
No. It is a simple `key = value` parser with section headers.

## License

MIT – see [LICENSE](LICENSE).
