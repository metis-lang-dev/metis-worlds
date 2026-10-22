"""world_ui's host (alf-demo step 3b): the world page, through the ui host beside it
(ui_host.py, a copy of metis-loop's domains/ui/ui_host.py: COPIES.md), with world_ui.llp's
entry/2 (the task card's entry is its close button). The ui host's card activation follows the
loop console's REPL widgets, which this page has none of, so it activates nothing here."""
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("world_ui_base_host", HERE / "ui_host.py")
ui_host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui_host)

OUTCOMES, WAITS = ui_host.OUTCOMES, ui_host.WAITS


def make(case):
    return ui_host.UiHost(case, entries=dict(re.findall(r"^entry\((\w+),\s*(\w+)\)\.", (HERE / "world_ui.llp").read_text(), re.M)))
