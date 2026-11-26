# Test data

Three FCS files from a published, public-domain dataset, checked in so a fresh clone
has something to open.

| File | Events |
|---|---|
| `5019_123.fcs` | 21,470 |
| `5019_125.fcs` | 27,755 |
| `5019_154.fcs` | 26,302 |

## Source

Good Z, et al. Post-infusion CAR TReg cells identify patients resistant to CD19-CAR
therapy. *Nature Medicine* 28, 1860–1871 (2022).
[doi:10.1038/s41591-022-01960-7](https://doi.org/10.1038/s41591-022-01960-7)

Patient samples from the Figure 6 flow cytometry cohort, acquired on a BD LSRII. The
dataset is deposited in the Stanford Digital Repository,
[purl.stanford.edu/qb215vz6111](https://purl.stanford.edu/qb215vz6111), under the
[Open Data Commons Public Domain Dedication and License 1.0](https://opendatacommons.org/licenses/pddl/1-0/).
Cite the paper, not this repository.

The files are byte-identical to the deposited `Original-FCS-Files`; nothing in the
headers or events has been changed.

    3d34f27154be92972514b0a302ea3a4ab35a45598ba20e6009ea5505d7bded55  5019_123.fcs
    24f6a1f6679e9b97ad33398fef82af52473fd94f3a5cd419e19d92840b0c5576  5019_125.fcs
    b1364d58c29ebf06f9f1ec0177aed06998d8a2b68253c830efe7ab53fd0f60c7  5019_154.fcs

## Panel, from the `$PnS` labels in the files

| Detector | Label |
|---|---|
| `R670-A` | CAR |
| `V710-A` | CD3 |
| `U379-A` | CD8 |
| `U740-A` | CD4 |
| `V780-A` | CD45 |
| `U820-A` | CD25 |
| `G585-A` | FOXP3 |
| `B525-A` | Helios |
| `V450-A` | GZMB |
| `V610-A` | CD57 |
| `G780-A` | Tbet |
| `R780-A` | DUMP |
| `V525-A` | LD (live/dead) |

## Gates

`docs/shots/CAR_T_panel_template.fgt` is a gate template for this panel (Cells,
Single cells, Live, then CAR against CD3). It was drawn on the cohort's control
tubes, so treat it as a starting point and check each gate on these files.

    cytolux testdata/
