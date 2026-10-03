"""Source and PyInstaller entry point. Does not start the bridge on import."""
from pathlib import Path
import sys
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'bridge'))
from codex_vita.gui import main
if __name__ == '__main__':
    main()
