# road's image (spec/17 §7; linker s-5908724a step 2): `make` runs `metisc build .`, which compiles the members whose
# source (or '#' directives) changed since the last build, reuses the rest, links, and records build/road.build.
# METISC: metis-lang's metisc (default: the workspace sibling); METIS_HOME: the iface/ packages (metispy's catalog).
METISC ?= ../../../metis-lang/src/metisc
METIS_HOME ?= ../../../metispy/metis/catalog
export METIS_HOME

build/road.build: composition.yaml $(wildcard *.llp) $(wildcard */*.llp) $(wildcard */domain.yaml)
	$(METISC) build .

check:
	$(METISC) check .

.PHONY: check
