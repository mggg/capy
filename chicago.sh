set -euxo pipefail

python3 pipeline/overlaps.py "../data.mggg.org/census-2020/il/il_cousub.shp" "cbsas/defs/9618502_16980_march_2020.shp" chicago-maup --prefix "cousub_"
python3 pipeline/overlaps.py "../data.mggg.org/census-2020/il/il_tract.shp" "cbsas/defs/9618502_16980_march_2020.shp" chicago-maup --prefix "tract_"
python3 pipeline/overlaps.py "../data.mggg.org/census-2020/il/il_block.shp" "cbsas/defs/9618502_16980_march_2020.shp" chicago-maup --prefix "block_"
python3 pipeline/overlaps.py "../data.mggg.org/census-2020/il/il_bg.shp" "cbsas/defs/9618502_16980_march_2020.shp" chicago-maup --prefix "bg_"

fd .shp chicago-maup/ | parallel --bar python3 pipeline/gen_duals.py {} {.}_orig.json {.}_connected.json --attr GEOID

python3 pipeline/calculate_metrics.py chicago-maup/il_bg_cbsa_tracts_connected.json BLACK WHITE TOTPOP --headers-only > outputs/white_black_chicago.csv
fd connected.json chicago-maup/ | parallel --bar python3 pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP >> outputs/white_black_chicago.csv

python3 pipeline/calculate_metrics.py chicago-maup/il_bg_cbsa_tracts_connected.json POC WHITE TOTPOP --headers-only > outputs/white_poc_chicago.csv
fd connected.json chicago-maup/ | parallel --bar python3 pipeline/calculate_metrics.py {} POC WHITE TOTPOP >> outputs/white_poc_chicago.csv
