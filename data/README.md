# data/

Working tables exported from BigQuery and produced by the Python scripts, in the folder layout that `python/verify_numbers.py` and
`python/make_figures_en.py` expect (run both from the repository root). The same tables, documented file by file, are the
Supporting Information of the article (`supporting_information/`, S3–S6 Table) and the Zenodo record doi:10.5281/zenodo.23282476.

- top level: monthly concentration under every definition (`concentration_all_schemes.csv`), flow composition, dyad shares, top-20 recipients, event tables, trend tests
- `dai/`: DAI under G_net_xf and the flash-mint share
- `entity/`: entity-level concentration, entity-level top-20 recipients, inflow by labelled category
- `topo/`: quarterly-snapshot metrics, degree and strength fits, preferential-attachment estimates; `topo/zip/degree_hist/` and `topo/v4/zip/strength_hist/` hold the degree and log-binned strength histograms of every snapshot
- `followup/`: the follow-up queries Q14–Q19 (round-trip decomposition, gas of direct calls, fixed-count shares)
