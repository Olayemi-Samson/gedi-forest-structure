#!/usr/bin/env bash
# End-to-end run: GEDI canopy height in a Nigerian state vs a Brazilian state.
# Needs: a free NASA Earthdata account (you will be asked to log in once).
# Usage:  MAX=8 bash scripts/run_nigeria_vs_brazil.sh
set -euo pipefail

NG_STATE="${NG_STATE:-Cross River}"
BR_STATE="${BR_STATE:-Rondonia}"
MAX="${MAX:-8}"          # granules per region (each can be hundreds of MB)
START="${START:-2019-04-18}"
END="${END:-2023-03-01}"

NG_BOX=$(python -m gedi_forest bbox --iso NGA --region "$NG_STATE")
BR_BOX=$(python -m gedi_forest bbox --iso BRA --region "$BR_STATE")
echo "Nigeria ($NG_STATE) box: $NG_BOX"
echo "Brazil  ($BR_STATE) box: $BR_BOX"

python -m gedi_forest download --bbox $NG_BOX --start "$START" --end "$END" --max-granules "$MAX" --out data/raw/nga
python -m gedi_forest download --bbox $BR_BOX --start "$START" --end "$END" --max-granules "$MAX" --out data/raw/bra

python -m gedi_forest process --raw data/raw --out data/processed/shots.csv.gz
python -m gedi_forest report  --shots data/processed/shots.csv.gz --out results/overview
python -m gedi_forest compare --shots data/processed/shots.csv.gz --iso NGA BRA --out results/compare

echo "Done. See results/overview and results/compare."
echo "Optional next step (edge effects and regrowth): see README, section 'Edge effects and regrowth'."
