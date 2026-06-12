set -euxo pipefail

python pipeline/overlaps.py \
    "Chicago_2020_Maup_Data/tracts/tracts_joined/tracts_joined.shp" \
    "cbsas/defs/9618502_16980_march_2020.shp" \
    chicago-maup \
    --prefix "tract_"

python pipeline/overlaps.py \
    "Chicago_2020_Maup_Data/blocks/blocks_joined/blocks_joined.shp" \
    "cbsas/defs/9618502_16980_march_2020.shp" \
    chicago-maup \
    --prefix "block_"

python pipeline/overlaps.py \
    "Chicago_2020_Maup_Data/block groups/blk_grps_joined/blk_grps_joined.shp" \
    "cbsas/defs/9618502_16980_march_2020.shp" \
    chicago-maup \
    --prefix "bg_"


fd .shp chicago-maup/ | parallel --bar python pipeline/gen_duals.py {} {.}_orig.json {.}_connected.json --attr GEOID

(
python pipeline/calculate_metrics.py chicago-maup/tract_9618502_16980_march_2020_cbsa_tracts_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "tract_9618502_16980_march_2020_cbsa_tracts_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/tract_white_black_chicago.csv

(
python pipeline/calculate_metrics.py chicago-maup/tract_9618502_16980_march_2020_cbsa_tracts_connected.json BLACK POC TOTPOP --headers-only
fd -g "tract_9618502_16980_march_2020_cbsa_tracts_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK POC TOTPOP
) > outputs/tract_white_poc_chicago.csv


(
python pipeline/calculate_metrics.py chicago-maup/bg_9618502_16980_march_2020_cbsa_tracts_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "bg_9618502_16980_march_2020_cbsa_tracts_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/bg_white_black_chicago.csv

(
python pipeline/calculate_metrics.py chicago-maup/bg_9618502_16980_march_2020_cbsa_tracts_connected.json BLACK POC TOTPOP --headers-only
fd -g "bg_9618502_16980_march_2020_cbsa_tracts_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK POC TOTPOP
) > outputs/bg_white_poc_chicago.csv


(
python pipeline/calculate_metrics.py chicago-maup/block_9618502_16980_march_2020_cbsa_tracts_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "block_9618502_16980_march_2020_cbsa_tracts_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/block_white_black_chicago.csv

(
python pipeline/calculate_metrics.py chicago-maup/block_9618502_16980_march_2020_cbsa_tracts_connected.json BLACK POC TOTPOP --headers-only
fd -g "block_9618502_16980_march_2020_cbsa_tracts_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK POC TOTPOP
) > outputs/block_white_poc_chicago.csv

