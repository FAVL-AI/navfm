"""Run unchanged synthetic component procedure with rejection diagnostics."""

from pathlib import Path

from native_provenance_diagnostic_v1 import verify_native_dependencies

source = Path(__file__).with_name("qualify_vint_interface_v1.py").read_text()
old = "from native_dependency_closure_v2 import verify_native_dependencies"
assert source.count(old) == 1
source = source.replace(old, "")
# Only the verifier binding changes; all model/input/validation instructions are retained.
exec(
    compile(source, str(Path(__file__).with_name("qualify_vint_interface_v1.py")), "exec"),
    dict(__name__="__main__", verify_native_dependencies=verify_native_dependencies),
)
