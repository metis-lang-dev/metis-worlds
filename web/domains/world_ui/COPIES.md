# world_ui's copies (copies, not dependencies)

| file | source | at |
|---|---|---|
| `ui_domain.llp` | metis-loop `domains/ui/ui_domain.llp` (the lifted base, v6.5) | `console-nav-page` ac97d1b (b675d34's base; console-nav merges it to master) |
| `ui_host.py` | metis-loop `domains/ui/ui_host.py` (the page-host adapter) | the same |

`web/tests/test_world_ui.py` checks they are byte-equal to the source when a metis-loop
checkout beside metis-worlds has it (it skips otherwise). A new base version: copy both
again, rerun the cases.
