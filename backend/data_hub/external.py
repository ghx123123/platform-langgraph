import os
import subprocess
import sys
from pathlib import Path


def open_with_system(path: Path) -> None:
    target = path.resolve()
    if not target.exists():
        raise FileNotFoundError("本机文件或文件夹已不存在")
    if sys.platform == "win32":
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
