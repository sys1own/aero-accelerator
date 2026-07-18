use pyo3::prelude::*;
{shield_imports}

{function_code}

#[pymodule]
fn {module_name}(_py: Python, m: &PyModule) -> PyResult<()> {{
    m.add_wrapped(wrap_pyfunction!({function_name}))?;
    Ok(())
}}
