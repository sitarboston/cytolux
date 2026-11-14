"""Entry point for the packaged application.

PyInstaller runs the script it is given as __main__, outside any package. Pointing it
at cytolux/__main__.py therefore produced a binary that died on its first line with
"attempted relative import with no known parent package": the frozen builds never
started. This file imports by absolute name, which works both frozen and from source.
"""
from cytolux.app import main

if __name__ == "__main__":
    main()
