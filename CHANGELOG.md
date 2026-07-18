# Changelog

## 0.2.0

### Fixed

- **Rust name collision**: files like `fib.py` containing `def fib` now compile correctly. The generated `#[pymodule]` uses the file stem while each `#[pyfunction]` uses a prefixed Rust function name, so Python API names remain unchanged.
- **Packaging**: `from accelerator import aero_frontend, translator, hin_vm, shield, engine` now works.
- **Error messages**: cargo output is classified; missing Rust toolchains, name conflicts, and missing `m4` produce clear guidance. I/O detection now includes the offending line number.
- **Formatting**: generated Rust code is passed through `cargo fmt` before building.
- **Cleanup**: temporary Rust crates are removed by default; `--no-clean` preserves them.

### Added

- **Build caching**: `.accelerate-cache/` stores compiled artifacts keyed by source hash, so repeated builds are near-instant. Use `--no-cache` to force a rebuild.
- **Multi-function compilation**: `--functions fib,fact` builds several functions into a single module.
- **Fallback mode**: `--fallback` writes a pure-Python wrapper module when Rust compilation cannot proceed.
- **Benchmark output**: after a successful build, Rust and Python timings are printed. Skip with `--no-benchmark` or provide arguments with `--benchmark-args`.
- **Configuration file**: `accelerate.toml` supports `[build]`, `[precision_shield]`, and `[benchmark]` sections.
- **CI mode**: `--ci` suppresses non-essential output and `--target` enables cross-compilation.
