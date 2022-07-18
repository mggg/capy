# Download NHGIS data

python scripts/preprocess.py
python scripts/filter_cbsas.py

# Subsection tracts
fd "shp" cbsas/defs/ -x python pipeline/intersection.py processed/2020_tracts.shp {} cbsas/2020/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ -x python pipeline/intersection.py processed/2010_tracts.shp {} cbsas/2010/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ -x python pipeline/intersection.py processed/2000_tracts.shp {} cbsas/2000/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ -x python pipeline/intersection.py processed/1990_tracts.shp {} cbsas/1990/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ -x python pipeline/intersection.py processed/1980_tracts.shp {} cbsas/1980/{/.}_cbsa_tracts.shp
fd "shp" cbsas/defs/ -x python pipeline/intersection.py processed/1970_tracts.shp {} cbsas/1970/{/.}_cbsa_tracts.shp

# Generate dual graphs
fd _cbsa_tracts.shp cbsas/ -x python3 pipeline/gen-duals.py {} {.}_orig.json {.}_connected.json

# Calculate metrics
python pipeline/calculate_metrics.py blank blank blank blank --headers-only > outputs/white_black.csv
fd connected.json cbsas/ -x python pipeline/calculate_metrics.py {} WHITE BLACK TOTPOP >> outputs/white_black.csv

python pipeline/calculate_metrics.py blank blank blank blank --headers-only > outputs/white_poc.csv
fd connected.json cbsas/ -x python pipeline/calculate_metrics.py {} WHITE POC TOTPOP >> outputs/white_poc.csv

python scripts/parse_output.py outputs/white_black.csv outputs/white_black_parsed.csv
python scripts/parse_output.py outputs/white_poc.csv outputs/white_poc_parsed.csv
