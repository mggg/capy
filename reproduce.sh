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

# Subsection tracts
fd "shp" cbsas/defs/ | parallel --bar python pipeline/intersection.py processed/2020_tracts.shp {} cbsas/2020/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ | parallel --bar python pipeline/intersection.py processed/2010_tracts.shp {} cbsas/2010/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ | parallel --bar python pipeline/intersection.py processed/2000_tracts.shp {} cbsas/2000/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ | parallel --bar python pipeline/intersection.py processed/1990_tracts.shp {} cbsas/1990/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ | parallel --bar python pipeline/intersection.py processed/1980_tracts.shp {} cbsas/1980/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ | parallel --bar python pipeline/intersection.py processed/1970_tracts.shp {} cbsas/1970/{/.}_cbsa_tracts.shp

# Generate dual graphs
fd _cbsa_tracts.shp cbsas/ | parallel --bar python3 pipeline/gen-duals.py {} {.}_orig.json {.}_connected.json

# Calculate metrics, need to gen headers
# TODO: change CSV output to also slice by def year
python pipeline/calculate_metrics.py cbsas/2010/668921_19660_cbsa_tracts_connected.json WHITE BLACK TOTPOP --headers-only > outputs/white_black.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} WHITE BLACK TOTPOP >> outputs/white_black.csv

python pipeline/calculate_metrics.py cbsas/2010/668921_19660_cbsa_tracts_connected.json WHITE BLACK TOTPOP --headers-only > outputs/white_poc.csv
fd connected.json cbsas/ | parallel --bar python pipeline/calculate_metrics.py {} WHITE POC TOTPOP >> outputs/white_poc.csv

python scripts/parse_output.py outputs/white_black.csv outputs/white_black_parsed.csv
python scripts/parse_output.py outputs/white_poc.csv outputs/white_poc_parsed.csv
