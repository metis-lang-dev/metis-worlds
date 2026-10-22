"""The world page's voice-navigation instance (alf-demo step 3b): web/domains/world_ui at the
program level, no model, no browser. Its cases in both toolchains (metisc and metispy's replay:
the same I/T/F lines, every query holding), the instance adds facts only, the card's generated
files are the generator's, its host is the ui host with world_ui's dialog entry, and the copies
(the base and the ui host; web/vendor/s) are their sources' when a sibling checkout has them.

    METISC=…/metis-lang/src/metisc ../.venv/bin/python -m pytest web/tests -q    (a python with metispy)
"""
import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]
WORLDS = WEB.parent
DOM = WEB / "domains" / "world_ui"
CASES = sorted((DOM / "cases").glob("*.llp"))
RULES = re.compile(r"^\s*(\w+) \[dyn\]", re.M)


def _metisc():
    return os.environ.get("METISC") or shutil.which("metisc")


def _itf(s):
    return [x for x in s.splitlines() if x[:2] in ("I ", "T ", "F ")]


@pytest.mark.skipif(not _metisc(), reason="no metisc (METISC)")
@pytest.mark.parametrize("case", CASES, ids=[c.stem for c in CASES])
def test_the_world_ui_cases_in_both_toolchains(case):
    from metis.kernel.artifact import served_doc
    from metis.lang.directives import render_run
    out = subprocess.run([_metisc(), "--run", str(case)], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    doc, c, _ = served_doc(case, [])
    assert _itf(out.stdout) == _itf(render_run(case.stem, c, doc.catalog.ground(dict(c["init"]))))
    q = [x for x in out.stdout.splitlines() if x.startswith("Q ")]
    assert q and all(x.endswith(" 1/1") for x in q), q
    assert len(CASES) >= 14


def test_the_instance_adds_facts_only_and_starts_every_widget_present():
    inst = (DOM / "world_ui.llp").read_text()
    assert not RULES.search(inst) and 'include "ui_domain.llp".' in inst
    widgets = re.search(r"^type widget \{([^}]*)\}\.", inst, re.M).group(1).split()
    for w in widgets:
        assert f"#init present({w}) 1" in inst, w
        assert (f"#init shown({w}) 1" in inst) != (f"#init hidden({w}) 1" in inst), w
    page = (WEB / "world.html").read_text()
    for w in widgets:                                           # the page has the instance's ids
        assert f'data-w="{w}"' in page or (w in ("card", "cardclose") and "world.js" in page), w


def test_the_cards_generated_files_are_the_generators():
    from metis import catalog
    files = catalog.intent_files("world_ui", (DOM / "intent.yaml").read_text(), WEB)
    for name, text in files.items():
        if text:
            assert (DOM / "intent" / name).read_text() == text, f"world_ui/intent/{name}: regenerate (python -m metis.intents gen world_ui)"


def test_the_host_is_the_ui_host_with_world_uis_entry():
    spec = importlib.util.spec_from_file_location("world_ui_host", DOM / "world_ui_host.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    h = m.make("live")
    assert h.entries == {"ctrl": "play", "card": "cardclose"}
    h.world(["+opened(card)"])
    h.tick({})
    assert h.page["focus"] == "cardclose" and h.page["modal"] == "card"


COPIES = [  # (this file, the source in a sibling checkout)
    (DOM / "ui_domain.llp", "metis-loop/domains/ui/ui_domain.llp"),
    (DOM / "ui_host.py", "metis-loop/domains/ui/ui_host.py"),
    (WEB / "vendor" / "ui-port.js", "metis-loop/console/lib/ui-port.js"),
    (WEB / "vendor" / "journal.js", "metis-agent/console/journal.js"),
] + [(WEB / "vendor" / f, "fsttm-web/lib/" + f) for f in
     ("attention.js", "dialog.js", "fsttm.js", "fsttm.json", "narrator.css", "narrator.js", "panel.css", "panel.js", "tts.js", "ws.js")]


@pytest.mark.parametrize("mine, src", COPIES, ids=[c[0].name for c in COPIES])
def test_the_copies_are_their_sources(mine, src):
    s = WORLDS.parent / src
    if not s.is_file():
        pytest.skip(f"no {src} beside metis-worlds")
    assert mine.read_bytes() == s.read_bytes(), f"{mine.relative_to(WORLDS)} differs from {src}: copy it again (COPIES.md)"
