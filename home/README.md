# The home world has moved

Since 2026-11-24 the home world lives in [nina-live](https://github.com/ibnHatab/nina-live), under
`catalog/` (moved with its history by `git subtree`). Nina's Metis domains are there in one place:
the director, the interface packages, and every tool family's specialist, the home's packages among
them, all in one composition.

- The packages (lights, air, media, scenes, comfort, shared), the map (`world/home.map.json`), the
  tests and the NUC deploy files are at `nina-live/catalog/`.
- The semantic world's library stays here, in `libs/semantic-world/go`.
- metis-agent's tests look for the home world at `nina-live/catalog` first.
