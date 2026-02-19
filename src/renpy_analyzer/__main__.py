"""Allow running with: python -m renpy_analyzer"""

import sys

if len(sys.argv) > 1:
    from .cli import analyze

    analyze()
else:
    from .app import main

    main()
