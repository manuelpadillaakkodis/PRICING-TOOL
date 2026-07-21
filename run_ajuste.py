import os
import sys

# Asegurar que el directorio actual está en el path
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from AJUSTE.app import main

if __name__ == "__main__":
    main()
