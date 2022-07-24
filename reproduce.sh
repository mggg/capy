set -euxo pipefail

# Download NHGIS data

# Preprocess data; join pop vals to shapefile
python scripts/preprocess.py

# Generate different dual graphs based on the various CBSA defs
python scripts/filter_cbsas.py --filename configs/list1_february_2013.xls --definition-tracts processed/2010_tracts.shp
python scripts/filter_cbsas.py --filename configs/list1_july_2015.xls --definition-tracts processed/2010_tracts.shp
python scripts/filter_cbsas.py --filename configs/list1_august_2017.xls --definition-tracts processed/2010_tracts.shp
python scripts/filter_cbsas.py --filename configs/list1_april_2018.xls --definition-tracts processed/2010_tracts.shp
python scripts/filter_cbsas.py --filename configs/list1_september_2018.xls --definition-tracts processed/2010_tracts.shp
python scripts/filter_cbsas.py --filename configs/list1_march_2020.xls --definition-tracts processed/2020_tracts.shp

# Subsection tracts by computing intersections
cat scripts/overlaps.sh | parallel --bar

# Generate dual graphs
fd _cbsa_tracts.shp cbsas/ | parallel --bar python3 pipeline/gen-duals.py {} {.}_orig.json {.}_connected.json

# Calculate metrics, need to gen headers
# TODO: change CSV output to also slice by def year
python pipeline/calculate_metrics.py cbsas/2010/154834_27980_september_2018_cbsa_tracts_connected.json WHITE BLACK TOTPOP --headers-only > outputs/white_black.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} WHITE BLACK TOTPOP >> outputs/white_black.csv

python pipeline/calculate_metrics.py cbsas/2010/154834_27980_september_2018_cbsa_tracts_connected.json WHITE BLACK TOTPOP --headers-only > outputs/white_poc.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} WHITE POC TOTPOP >> outputs/white_poc.csv

python scripts/parse_output.py outputs/white_black.csv outputs/white_black_parsed.csv
python scripts/parse_output.py outputs/white_poc.csv outputs/white_poc_parsed.csv
