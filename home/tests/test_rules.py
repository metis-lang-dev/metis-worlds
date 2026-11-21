"""The packages: they compile, their lint has no error, the map's generated files are current, and
each package's golden day and intents are written again byte for byte (the catalog's rule)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOME = Path(__file__).resolve().parent.parent
WS = HOME.parent.parent
METISC = os.environ.get("METISC") or str(WS / "metis-lang" / "src" / "metisc")
PACKAGES = ["lights", "air", "media", "scenes", "comfort"]


def run(*a, cwd=HOME, env=None):
    return subprocess.run(list(a), cwd=cwd, capture_output=True, text=True, env=env)


def test_map_files_are_current():
    r = run(sys.executable, "world/gen_map.py", "--check")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("pkg", PACKAGES)
def test_compiles_and_lints_clean(pkg):
    if not Path(METISC).exists():
        pytest.skip("no metisc (METISC)")
    d = HOME / "domains" / pkg
    r = run(METISC, "%s.llp" % pkg, cwd=d)
    assert r.returncode == 0 and r.stdout.startswith("ok"), r.stdout + r.stderr
    r = run(METISC, "--lint", "%s.llp" % pkg, "--manifest", "domain.yaml", cwd=d)
    errors = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith("error")]
    assert not errors, errors


@pytest.mark.parametrize("pkg", PACKAGES)
def test_goldens_written_again_byte_for_byte(pkg, tmp_path):
    copy = tmp_path / "home"
    shutil.copytree(HOME, copy, ignore=shutil.ignore_patterns(".metis", "__pycache__", "records"))
    env = dict(os.environ, METISC=METISC)
    env.pop("METIS_HOME_HA", None)
    r = run(sys.executable, "-m", "metis.catalog", "golden", pkg, cwd=copy, env=env)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    for f in ("day.out.jsonl", "intents.out.jsonl"):
        assert (copy / "domains" / pkg / "goldens" / f).read_text() == \
            (HOME / "domains" / pkg / "goldens" / f).read_text(), "%s/%s moved: write the golden again" % (pkg, f)
