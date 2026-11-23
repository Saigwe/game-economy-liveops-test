PY ?= python

.PHONY: all data report test clean charts

all: data report

data:
	$(PY) generator/simulate_test.py --db warehouse/liveops.duckdb
	$(PY) generator/simulate_test.py --db warehouse/broken.duckdb --broken-split

report:
	$(PY) -m analysis.report --db warehouse/liveops.duckdb --broken-db warehouse/broken.duckdb --out results/readout.md

test:
	$(PY) -m pytest -q

clean:
	rm -rf warehouse

charts:                                            ## README charts -> docs/charts
	$(PY) charts/make_charts.py
