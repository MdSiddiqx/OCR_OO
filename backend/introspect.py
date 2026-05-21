"""
introspect.py — print the actual public API of the installed LensAPI class
Run: python introspect.py
"""
import inspect
from chrome_lens_py import LensAPI

api = LensAPI()
print("=== LensAPI methods ===")
for name, obj in inspect.getmembers(api):
    if not name.startswith("_"):
        sig = ""
        try:
            sig = str(inspect.signature(obj))
        except Exception:
            pass
        kind = "async" if inspect.iscoroutinefunction(obj) else "sync "
        print(f"  {kind}  {name}{sig}")
