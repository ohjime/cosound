from pathlib import Path
import sys

import flet as ft


root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


from src.main import main as app_main


if __name__ == "__main__":
    ft.run(app_main)
