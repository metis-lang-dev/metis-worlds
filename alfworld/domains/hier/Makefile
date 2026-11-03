# alfworld's image (alf-bundle s-b53cc7ab; spec/17 §7, as road/domains/Makefile): `make` derives the members' tree bases
# from the plain ones (tree/, world/gen_hier.py tree: the one copy of the rules is ./<spec>_domain.llp), then runs
# `metisc build .`, which compiles the members whose source changed since the last build, reuses the rest, links, and
# records build/alfworld.build. `make golden` records the image's hash in image.golden.
# METISC: metis-lang's metisc (default: the workspace sibling). METIS_HOME: metispy's catalog (iface/: the protocol and
# the tree director's units). PYTHON: one with metispy (metis.catalog.protocol_stub).
METISC ?= ../../../../metis-lang/src/metisc
export METIS_HOME ?= ../../../../metispy/metis/catalog
PYTHON ?= python3
GEN = ../../world/gen_hier.py

build/alfworld.build: tree composition.yaml $(wildcard *.llp) $(wildcard */*.llp) $(wildcard */domain.yaml)
	$(METISC) build .

tree: $(wildcard *_domain.llp) iface/alfworld.llp $(GEN)
	$(PYTHON) $(GEN) tree
	@touch tree

check: tree
	$(METISC) check .

golden: build/alfworld.build
	sed -n 's/^image alfworld.image.v-//p' build/alfworld.build > image.golden

.PHONY: check golden
