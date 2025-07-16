#!/usr/bin/env python
import sys
from pathlib import Path

# opcionalmente añade src/ al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from prevalidador.main import main

if __name__ == "__main__":
    main()
