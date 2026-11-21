# the home's images (spec/17 §2, one-member images): the five packages are served side by side, so there is no
# composition (no director, no tick protocol; metisc refuses a director over go, and metis-home is go): each package
# links to its own image under <pkg>/build/, and images.golden pins the five hashes (`make golden` writes it again).
# METISC: metis-lang's metisc (default: the workspace sibling).
METISC ?= $(abspath ../../../metis-lang/src/metisc)
PACKAGES := lights air media scenes comfort

all: $(PACKAGES:%=%/build/image.txt)

# a package's image: its rules, its manifest and the shared units it includes
.SECONDEXPANSION:
%/build/image.txt: $$(wildcard $$*/*.llp) $$*/domain.yaml $(wildcard shared/*.llp)
	@mkdir -p $*/build
	$(METISC) --link $* > $@.tmp || { cat $@.tmp; rm -f $@.tmp; exit 1; }
	@mv $@.tmp $@
	@grep '^image ' $@

check:
	@for p in $(PACKAGES); do $(METISC) --link $$p --check | grep '^image '; done | diff images.golden - \
	  && echo "images.golden: the five images as pinned"

golden:
	@for p in $(PACKAGES); do $(METISC) --link $$p --check | grep '^image '; done > images.golden
	@cat images.golden

.PHONY: all check golden
