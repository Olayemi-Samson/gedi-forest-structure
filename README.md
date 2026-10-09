# gedi-forest-structure

[![tests](https://github.com/Olayemi-Samson/gedi-forest-structure/actions/workflows/tests.yml/badge.svg)](https://github.com/Olayemi-Samson/gedi-forest-structure/actions/workflows/tests.yml)

Tropical forest **structure, disturbance and regrowth** from NASA **GEDI**
spaceborne lidar, with built-in **cross-country comparison** (Nigeria vs. other
tropical regions).

GEDI measures the vertical structure of forests, which drives carbon storage and
is a key observation for process-based ecosystem models. This toolkit turns raw
GEDI Level 2A footprints into answers to five concrete questions:

| Question | Command | Output |
|---|---|---|
| What does canopy height look like, and how does it change in time? | `report` | height maps, yearly stats, vertical profiles, change map |
| How does Nigeria compare with other tropical regions? | `compare` | per-state and per-country medians with honest confidence intervals |
| How much shorter is forest near clearings (edge effects)? | `disturbance` | canopy height vs distance to edge |
| How fast does forest recover after clearing? | `disturbance` | canopy height vs years since loss |
| Can simple predictors explain canopy height, tested without spatial leakage? | `model` | spatially cross-validated gradient-boosting baseline |

It works anywhere GEDI flies (roughly 51.6 degrees N to S). Nigeria and Brazil
state boundaries are bundled; any other country is one command away.

## What is this, in plain English?

**GEDI** (Global Ecosystem Dynamics Investigation) is a NASA laser instrument
(lidar) mounted on the International Space Station since 2019. It fires laser
pulses at the ground and times how long the light takes to return from the
treetops and from the forest floor. The difference gives the **height and layered
structure of the forest**, which tells scientists how much carbon the forest holds.

Taller, denser forest generally stores more carbon. When forest is cleared, burned
or logged, that carbon is lost; when it regrows, carbon is slowly regained. Seeing
this from space, in many countries at once, is hard. This toolkit does the
practical part: it reads the raw GEDI files, removes unreliable measurements,
and answers questions such as how tall forest is, how it differs between countries,
how clearings affect nearby forest, and how fast cleared land recovers.

Plain-language glossary:

| Term | Meaning |
|---|---|
| Lidar | Measuring distance with laser light |
| Canopy height (RH98) | Height below which 98% of the returned laser energy sits; a practical measure of tree-top height |
| Granule | One GEDI data file covering one stretch of orbit |
| Shot / footprint | One laser pulse landing on a circle about 25 m wide |
| Edge effect | Forest next to a clearing behaves differently from forest deep inside |
| Regrowth | Recovery of height after clearing |
| Cross-validation | Testing a model on data it has not seen, to avoid fooling ourselves |

## Status (read this first)

| Item | State |
|---|---|
| Code and command-line tool | Complete |
| Automated tests | 48 passing (unit, integration and an end-to-end chain) |
| Boundary data | **Real**: geoBoundaries Nigeria and Brazil, bundled with licences |
| Test shots and rasters | Fabricated, for tests only (see `tests/conftest.py`) |
| Run on real GEDI / Hansen data | Pending; results will be added to `results/` with the exact command and date |

No number or figure in this repository comes from fabricated data.

## Quick start

Requires Python 3.10+ and a free [NASA Earthdata](https://urs.earthdata.nasa.gov) account
(anyone can register; no NASA affiliation needed). Full step-by-step, including
Windows and how to check that real data looks right: **[docs/RUNNING.md](docs/RUNNING.md)**.

```bash
git clone https://github.com/Olayemi-Samson/gedi-forest-structure.git
cd gedi-forest-structure
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest                                   # confirm everything works on your machine

# Nigeria (Cross River) vs Brazil (Rondonia), end to end:
MAX=8 bash scripts/run_nigeria_vs_brazil.sh
```

Or step by step:

```bash
python -m gedi_forest bbox --iso NGA --region "Cross River"     # box from the real polygon
python -m gedi_forest download --bbox <W S E N> --max-granules 8 --dry-run   # preview count and size first
python -m gedi_forest download --bbox <W S E N> --max-granules 8 --out data/raw/nga
python -m gedi_forest process  --raw data/raw
python -m gedi_forest check                                     # sanity-check the real data
python -m gedi_forest report
python -m gedi_forest compare  --iso NGA BRA                    # add COD, IDN ... after regions-fetch
python -m gedi_forest regions-fetch --iso COD IDN               # more countries, on demand
```

GEDI granules are large (the download step prints the total size; use `--dry-run` to
check first). With `--max-granules N`, granules are spread evenly across the date
range, so a small sample still covers all years. Start with a small N.

## Edge effects and regrowth

These steps need forest-loss history from the Hansen et al. Global Forest Change
dataset (30 m, CC BY 4.0). Download the `treecover2000` and `lossyear` tiles
covering your area from the dataset's download page (tile names encode the tile
corner), then:

```bash
python -m gedi_forest disturbance --shots data/processed/shots.csv.gz \
    --lossyear  Hansen_..._lossyear_*.tif \
    --treecover Hansen_..._treecover2000_*.tif
python -m gedi_forest model
```

Key design choices:

- **Time-aware matching.** A shot from 2020 only sees loss up to 2020. A pixel
  cleared in 2022 is still intact forest for that shot, so each shot is
  classified at its own acquisition date.
- **Cluster-aware uncertainty.** GEDI shots along a track are strongly
  correlated, so confidence intervals come from resampling whole ground-track
  segments, not individual shots (verified in `tests/test_compare.py`).
- **Spatial cross-validation.** `model` reports spatial-block and random CV side
  by side; a large gap means random CV overstates skill.

## Layout

```
gedi_forest/
  io.py           read GEDI L2A HDF5 (schema-checked against NASA's tutorial layout)
  filters.py      quality filters, time conversion
  analysis.py     gridding, yearly stats, vertical profiles, change maps
  regions.py      real admin boundaries, point-in-polygon, bounding boxes
  compare.py      cluster-bootstrap medians and differences
  disturbance.py  regrowth age and edge distance from forest-loss tiles
  model.py        spatially cross-validated RH98 baseline
  cli.py          command line
data/boundaries/  bundled Nigeria and Brazil boundaries + licence metadata
docs/             METHODS.md, DATA_SOURCES.md
tests/            48 tests
```

## Limitations

- GEDI samples footprints along orbit tracks; it is not wall-to-wall, and
  coverage over Nigeria is thinner than over some regions. Per-cell change is
  exploratory.
- Hansen loss captures stand-replacement clearing, not selective logging or
  subtle degradation, so "intact" means no detected clearing, not undisturbed.
- Edge distances are approximate (pixel size scaled to metres at the window
  centre) and are capped at `--max-edge-m` (default 1000 m).
- Quality-filter thresholds are analysis choices; report them with any result.
- Associations in `model` are descriptive, not causal.

See [docs/METHODS.md](docs/METHODS.md) and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Background

A 2023 study of Nigerian oil-palm plantations found that global canopy-height
products had mean absolute errors of 4.2 to 6.2 m, versus 2.5 m for locally
trained models, and noted relatively sparse GEDI coverage in the region
(Tsao et al., *Remote Sensing* 15(21):5162). This toolkit is a general,
region-agnostic starting point for the kind of local evaluation that finding
motivates.

MIT licensed. Boundary data carry their own licences (see DATA_SOURCES.md).
