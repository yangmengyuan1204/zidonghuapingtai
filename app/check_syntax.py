import py_compile, sys
try:
    py_compile.compile(r'D:\A_zidonghuapingtai\app\main.py', doraise=True)
    print("OK: no syntax errors")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}", file=sys.stderr)
    sys.exit(1)
