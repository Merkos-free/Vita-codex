from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "bridge"))
from codex_vita.__main__ import main
if __name__ == "__main__":
    main()
