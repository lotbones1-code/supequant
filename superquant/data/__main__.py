"""
Module entry point for: python -m superquant.data.download
"""

import sys
from .download import main

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code if exit_code is not None else 0)

