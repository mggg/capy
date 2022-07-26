set -euxo pipefail

# Download NHGIS data

# Set up folder structure
bash scripts/setup.sh

# Preprocess data to produce shapefile; join pop vals to shapefile
python scripts/preprocess.py

# Generate CBSA definition shapefiles for each configured year
cat scripts/filter.sh | parallel --bar

# Select tracts that overlap with CBSA definition shapefiles
cat scripts/overlaps.sh | parallel --bar

# Generate dual graphs
fd _cbsa_tracts.shp cbsas/ | parallel --bar python3 pipeline/gen_duals.py {} {.}_orig.json {.}_connected.json

# Calculate metrics, but first generate headers
python pipeline/calculate_metrics.py cbsas/2020/186847_39460_march_2020_cbsa_tracts_connected.json BLACK WHITE TOTPOP --headers-only > outputs/white_black.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP >> outputs/white_black.csv

python pipeline/calculate_metrics.py cbsas/2020/186847_39460_march_2020_cbsa_tracts_connected.json POC WHITE TOTPOP --headers-only > outputs/white_poc.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP >> outputs/white_poc.csv

# Parse CSVs and add metadata
python scripts/parse_output.py outputs/white_black.csv outputs/white_black_parsed.csv
python scripts/parse_output.py outputs/white_poc.csv outputs/white_poc_parsed.csv

# Generate figures
python scripts/generate_figures.py
