"""The world page's shell (alf-demo step 3b): web/vendor/shell.css + shell.js are this repo's copies of the
consoles' common web style (metis-loop console/lib/shell.*, metis-agent console/shell.*; the copies rule of
shell-copy s-7c739dd7). Each copy's first comment names its own repo; the code below it is the same. A
console checkout not beside this one is skipped."""
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]


def sibling(*parts):
    d = WEB
    for _ in range(5):
        d = d.parent
        c = d.joinpath(*parts)
        if c.exists():
            return c
    return None


def code(p):
    """The file past its first comment block."""
    text = Path(p).read_text()
    return text[text.index("*/") + 2:] if text.lstrip().startswith("/*") else text


@pytest.mark.parametrize("name", ["shell.css", "shell.js"])
@pytest.mark.parametrize("console", [("metis-loop", "console", "lib"), ("metis-agent", "console")])
def test_the_shell_is_the_consoles(name, console):
    other = sibling(*console, name)
    if other is None:
        pytest.skip("no %s checkout beside this one" % console[0])
    assert code(WEB / "vendor" / name) == code(other), "web/vendor/%s differs from %s past its header: copy the consoles' code" % (name, other)


def test_the_world_page_loads_the_shell():
    html = (WEB / "world.html").read_text()
    assert 'href="vendor/shell.css"' in html and 'src="vendor/shell.js"' in html
    for d in ("talk", "hierarchy", "journal"):
        assert re.search(r'class="dock" id="dock-%s" data-dock="%s"' % (d, d), html) and 'data-strip="%s"' % d in html
