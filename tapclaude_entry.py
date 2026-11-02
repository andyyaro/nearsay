"""Entry point used by the installed wrappers in ~/.tapclaude/bin.

The wrappers run Python with -I (isolated mode: ignores PYTHON* environment
variables and the user site-packages folder), which also stops Python from adding
this file's folder to the import path, so it is added here explicitly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from tapclaude.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
