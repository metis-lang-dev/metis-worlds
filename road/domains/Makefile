# road's image (spec/17 §7; linker s-5908724a step 2): `make` runs `metisc build .`, which compiles the members whose
# source (or '#' directives) changed since the last build, reuses the rest, links, and records build/road.build.
# METISC: metis-lang's metisc (default: the workspace sibling); it finds its own standard units (iface/: the protocol
# and the tree director; metis-lang spec/17 amendment 5), so no METIS_HOME.
METISC ?= ../../../metis-lang/src/metisc

build/road.build: composition.yaml $(wildcard *.llp) $(wildcard */*.llp) $(wildcard */domain.yaml)
	$(METISC) build .

check:
	$(METISC) check .

.PHONY: check
