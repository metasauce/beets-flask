# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = build

DIAGRAMCMD    = paracelsus graph beets_flask.database.models.base:Base \
					--config ../backend/pyproject.toml \
					--column-sort preserve-order

# the grep breaks the charts, causing a slow down, but they still render and are cleaner
DIGRAMGREP    = | grep -vE "created_at|updated_at"

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: diagrams

# to do exact filtering we need to use e.g. --include-tables "^track_info$$"
diagrams:
	@$(DIAGRAMCMD) \
		> ./diagrams/all.mmd

	@$(DIAGRAMCMD) \
		--include-tables "task" \
		--include-tables "folder" \
		--include-tables "session" \
		--include-tables "candidate" \
		--include-tables "^matches$$" \
		--include-tables "^items$$" \
		$(DIGRAMGREP) \
		> ./diagrams/high_level.mmd

	@$(DIAGRAMCMD) \
		--include-tables "candidate" \
		--include-tables "matches" \
		$(DIGRAMGREP) \
		> ./diagrams/matches_overview.mmd

	@$(DIAGRAMCMD) \
		--include-tables "matches_album" \
		--include-tables "matches_track" \
		--include-tables "distance" \
		--include-tables "penalties" \
		--include-tables "album" \
		--include-tables "track" \
		--include-tables "^items$$" \
		$(DIGRAMGREP) \
		> ./diagrams/matches_types.mmd

clean:
	rm -rf $(BUILDDIR)/*
	rm -rf $(SOURCEDIR)/_autosummary/*
