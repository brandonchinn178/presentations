#!/usr/bin/env python3

import contextlib
import shutil
import subprocess
from pathlib import Path

CWD = Path.cwd()
TALKS = CWD / "talks"
DEST = CWD / "site"


def main() -> None:
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True, exist_ok=True)

    # Generate output files
    subprocess.run(
        ["marp", "--html", "-I", TALKS, "-o", DEST],
        check=True,
    )

    # Generate index.html
    index_html = TEMPLATE.format(
        items="\n".join(
            f"""<li><a href="{file.relative_to(DEST)}">{file.name}</a></li>"""
            for file in DEST.rglob("*.html")
        )
    )
    dest = DEST / "index.html"
    dest.write_text(index_html)
    print(f"Generated: {dest}")


TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Presentations</title>
</head>
<body>
    <h1>Presentations</h1>
    <ul>
        {items}
    </ul>
</body>
</html>
"""


if __name__ == "__main__":
    main()
