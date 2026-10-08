# Running the toolkit on real data

This page takes you from a fresh clone to results you can trust. Nothing here
needs a NASA job: GEDI data is public and only requires a free login.

## 1. Install and self-test

```bash
git clone https://github.com/<owner>/gedi-forest-structure.git
cd gedi-forest-structure
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest                             # expect all tests to pass
```

The tests use small made-up shots to check the code logic. They say nothing about
real forests; that is what the next steps are for.

## 2. Get GEDI data (free account)

1. Register at <https://urs.earthdata.nasa.gov> and approve the "NASA GESDISC DATA ARCHIVE" or default applications if prompted.
2. Choose a box. The tool derives one from real boundaries:

```bash
python -m gedi_forest bbox --iso NGA --region "Cross River"
python -m gedi_forest bbox --iso BRA --region Rondonia
```

3. Preview, then download. The first download asks for your Earthdata login.

```bash
python -m gedi_forest download --bbox <W S E N> --max-granules 8 --dry-run
python -m gedi_forest download --bbox <W S E N> --max-granules 8 --out data/raw/nga
```

Each granule can be hundreds of MB. `--max-granules` spreads the sample evenly
over the date range. If login fails, set the environment variables
`EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` and add `--env-login`.

## 3. Process and check

```bash
python -m gedi_forest process --raw data/raw
python -m gedi_forest check
```

`check` prints shot counts, years, and canopy-height percentiles and warns about
values that look wrong. In humid tropical forest, median RH98 is typically well
above 10 m. Heights near zero or above 120 m mean a wrong box or a data problem.

## 4. Analyse

```bash
python -m gedi_forest report
python -m gedi_forest compare --iso NGA BRA
```

Outputs go to `results/`. Read `results/compare/summary.json`; the confidence
intervals account for correlation along GEDI ground tracks.

## 5. Edge effects and regrowth

Download the Hansen Global Forest Change `treecover2000` and `lossyear` tiles
(same version, 30 m, free, no login) covering your area from the dataset's
download page. Tile names give the upper-left corner. Then:

```bash
python -m gedi_forest disturbance --lossyear <lossyear tiles> --treecover <treecover2000 tiles>
python -m gedi_forest model
```

## 6. Other countries

```bash
python -m gedi_forest regions-fetch --iso COD IDN
python -m gedi_forest compare --iso NGA BRA COD IDN
```

Boundary licences differ by country; see [DATA_SOURCES.md](DATA_SOURCES.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| Login fails | Check credentials at the Earthdata site; try `--env-login` |
| `SchemaError` | The file is not a GEDI L2A granule (short name `GEDI02_A`) |
| Pixel-limit error in `disturbance` | Use a smaller box in `process --bbox W S E N` |
| Few shots in a region | GEDI is sparse; download more granules or widen the dates |
