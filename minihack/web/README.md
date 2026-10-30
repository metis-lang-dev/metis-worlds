# minihack/web — NetHack's own page

The real game's page (`../demo.sh`): the map, the talk, the world card, the journal and the dialog. It is independent of
ALFWorld's page: `map.js`, `map.css`, `world.js` and `world.html` started as copies of metis-worlds `web/` and change here
alone, for this world's needs.

What the worlds share is external, the agent (metis-agent) and the dialog (fsttm-web): `vendor/` holds the copies a page
keeps of those (fsttm-web's panel, dialog, tts, ws; the consoles' shell), refreshed from their repos, never edited here.

`tiles/nethack/` is NetHack's art, under its own terms: the NetHack 3.6 tileset as MiniHack ships it
(https://github.com/facebookresearch/minihack), NetHack General Public License (https://www.nethack.org/common/license.html),
not the Apache License of metis-worlds. The game's tile numbers index the sheet directly (`tests/test_nh_tty.py`).
