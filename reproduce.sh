set -euxo pipefail

# Download NHGIS data

# Set up folder structure
bash scripts/setup.sh

# Preprocess data to produce shapefile; join pop vals to shapefile
python scripts/preprocess.py

# Generate different dual graphs based on the various CBSA defs
cat scripts/filter.sh | parallel --bar

# Subsection tracts by computing overlaps
cat scripts/overlaps.sh | parallel --bar

# Generate dual graphs
fd _cbsa_tracts.shp cbsas/ | parallel --bar python3 pipeline/gen-duals.py {} {.}_orig.json {.}_connected.json

# Calculate metrics, but first generate headers
python pipeline/calculate_metrics.py cbsas/2010/154834_27980_september_2018_cbsa_tracts_connected.json WHITE BLACK TOTPOP --headers-only > outputs/white_black.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} WHITE BLACK TOTPOP >> outputs/white_black.csv

python pipeline/calculate_metrics.py cbsas/2010/154834_27980_september_2018_cbsa_tracts_connected.json WHITE BLACK TOTPOP --headers-only > outputs/white_poc.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} WHITE POC TOTPOP >> outputs/white_poc.csv

# Parse CSVs and add metadata
python scripts/parse_output.py outputs/white_black.csv outputs/white_black_parsed.csv
python scripts/parse_output.py outputs/white_poc.csv outputs/white_poc_parsed.csv
