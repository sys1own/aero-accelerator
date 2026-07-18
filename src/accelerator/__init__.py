"""Graph-based Python to Rust JIT compiler."""

from . import aero_frontend
from . import hin_vm
from . import precision_shield
from . import translator
from .scaffold import engine

shield = precision_shield

__version__ = "0.2.0"
__all__ = ["aero_frontend", "translator", "hin_vm", "shield", "engine"]
