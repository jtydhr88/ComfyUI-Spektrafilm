import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
GUI_FILES = ("options.py", "param_manifest.py")


def main():
    parser = argparse.ArgumentParser(description="Copy the spektrafilm runtime from an upstream checkout into vendor/ and re-apply patches/.")
    parser.add_argument("upstream", type=Path, help="path to a clone of https://github.com/andreavolpato/spektrafilm")
    args = parser.parse_args()
    src = args.upstream.resolve() / "src"

    target = VENDOR / "spektrafilm"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(src / "spektrafilm", target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in GUI_FILES:
        shutil.copy2(src / "spektrafilm_gui" / name, VENDOR / "spektrafilm_gui" / name)

    for patch in sorted((ROOT / "patches").glob("*.patch")):
        subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)], cwd=ROOT, check=True)

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.upstream, check=True, capture_output=True, text=True).stdout.strip()
    (VENDOR / "UPSTREAM").write_text(commit + "\n")
    print(f"vendored spektrafilm {commit}")


if __name__ == "__main__":
    main()
