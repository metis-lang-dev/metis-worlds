# alfworld's image (alf-bundle s-b53cc7ab; spec/17 §7, as road/domains/Makefile): `make` runs `metisc build .`, which
# compiles the members whose source changed since the last build, reuses the rest, links, and records
# build/alfworld.build. The rules are ONE copy, the one that runs (A3, ruling B): ./<spec>_domain.llp, the tree bases,
# committed; their protocol cancels are a marked block `make stub` writes in place (never edited by hand). The plain
# bases (the plain hierarchy's: demo.sh --plain, the driver, the task's eval model) are derived from them into plain/
# (`make plain`, git-ignored): the build needs them for the task's evaluate model. `make golden` records the image's
# hash in image.golden; `make check` holds the image, the marked blocks and the plain bases as generated.
# ../director_domain.llp is a prerequisite: the director includes it from outside the bundle, where the face's STALE
# cannot see it (nina, step 1 review).
# METISC: metis-lang's metisc (default: the workspace sibling). METIS_HOME: metispy's catalog (iface/: the protocol and
# the tree director's units). PYTHON: one with metispy and semantic_world (metis.catalog.protocol_stub, the semantic
# map): default the world's own venv, the one demo.sh runs (../../../../.worlds/alf, alfworld/setup.sh), else python3.
METISC ?= $(abspath ../../../../metis-lang/src/metisc)
export METIS_HOME ?= $(abspath ../../../../metispy/metis/catalog)
PYTHON ?= $(or $(wildcard $(abspath ../../../../.worlds/alf/bin/python)),python3)
GEN = ../../world/gen_hier.py
SPECS = task nav access grasp place
# the python check (A1): which python make tried, and what to set, before a generator fails on an import
PYCHECK = @$(PYTHON) -c 'import semantic_world, metis.catalog.protocol_stub' 2>/dev/null || { \
	echo "make: $(PYTHON) cannot import semantic_world and metispy (metis.catalog.protocol_stub): run alfworld/setup.sh," >&2; \
	echo "      or give one that can: make PYTHON=/path/to/python (with metispy and libs/semantic-world on its path)" >&2; exit 2; }

build/alfworld.build: plain composition.yaml ../director_domain.llp $(wildcard *.llp) $(wildcard */*.llp) $(wildcard */domain.yaml) | task/intent/card.yaml
	$(METISC) build .

# the task's card (its manifest's intent/card.yaml): a run fills it from the template (gen_hier.install_run); unfilled here
# when absent, so the package always has the spec it names
task/intent/card.yaml:
	@mkdir -p task/intent
	cp task/intent.yaml $@

plain: $(foreach s,$(SPECS),$(s)_domain.llp) iface/alfworld.llp $(GEN)
	$(PYCHECK)
	$(PYTHON) $(GEN) plain
	@touch plain

stub:
	$(PYCHECK)
	$(PYTHON) $(GEN) stub

check: plain
	$(PYCHECK)
	$(PYTHON) $(GEN) stub --check
	$(METISC) check .

golden: build/alfworld.build
	sed -n 's/^image alfworld.image.v-//p' build/alfworld.build > image.golden

.PHONY: stub check golden
