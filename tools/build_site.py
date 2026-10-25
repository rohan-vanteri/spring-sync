"""Copy the engine into docs/py so the static site runs the same code.

The site (docs/index.html) loads these files into Pyodide in the browser.
Run after changing anything in spring_sync/:  python3 tools/build_site.py
tests/test_site.py fails if the copies drift from spring_sync/.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "spring_sync")
DST = os.path.join(ROOT, "docs", "py", "spring_sync")

# The engine only: no server, eval, or model clients.
FILES = ["__init__.py", "data.py", "gate.py", "agent.py", "session.py", "narrate.py", "runner.py"]


def main():
    os.makedirs(DST, exist_ok=True)
    for name in FILES:
        shutil.copyfile(os.path.join(SRC, name), os.path.join(DST, name))
    # GitHub Pages runs Jekyll by default, which drops files starting with "_"
    # (like __init__.py). This empty file turns Jekyll off for docs/.
    open(os.path.join(ROOT, "docs", ".nojekyll"), "w").close()
    print("copied %d files to %s" % (len(FILES), os.path.relpath(DST, ROOT)))


if __name__ == "__main__":
    main()
