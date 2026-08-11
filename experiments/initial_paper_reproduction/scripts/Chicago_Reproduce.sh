set -euxo pipefail

python pipeline/overlaps.py \
    "Chicago_Maup_Data/tracts/tracts_joined_2010/tracts_joined_2010.shp" \
    "study_areas/definitions/cbsa_16980_march_2020.shp" \
    chicago-maup \
    --prefix "tract_2010_"

python pipeline/overlaps.py \
    "Chicago_Maup_Data/tracts/tracts_joined_2020/tracts_joined_2020.shp" \
    "study_areas/definitions/cbsa_16980_march_2020.shp" \
    chicago-maup \
    --prefix "tract_2020_"

python pipeline/overlaps.py \
    "Chicago_Maup_Data/blocks/blocks_joined_2010/blocks_joined_2010.shp" \
    "study_areas/definitions/cbsa_16980_march_2020.shp" \
    chicago-maup \
    --prefix "block_2010_"

python pipeline/overlaps.py \
    "Chicago_Maup_Data/blocks/blocks_joined_2020/blocks_joined_2020.shp" \
    "study_areas/definitions/cbsa_16980_march_2020.shp" \
    chicago-maup \
    --prefix "block_2020_"

python pipeline/overlaps.py \
    "Chicago_Maup_Data/block groups/blk_grps_joined_2010/blk_grps_joined_2010.shp" \
    "study_areas/definitions/cbsa_16980_march_2020.shp" \
    chicago-maup \
    --prefix "bg_2010_"
    
python pipeline/overlaps.py \
    "Chicago_Maup_Data/block groups/blk_grps_joined_2020/blk_grps_joined_2020.shp" \
    "study_areas/definitions/cbsa_16980_march_2020.shp" \
    chicago-maup \
    --prefix "bg_2020_"

fd -g '**.shp' chicago-maup/ \
| parallel --bar python pipeline/gen_duals.py {} {.}_orig.json {.}_connected.json --attr GEOID

(
python pipeline/calculate_metrics.py chicago-maup/tract_2010_cbsa_16980_march_2020_geographies_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "tract_2010_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/tract_white_black_chicago_2010.csv

(
python pipeline/calculate_metrics.py chicago-maup/tract_2010_cbsa_16980_march_2020_geographies_connected.json BLACK POC TOTPOP --headers-only
fd -g "tract_2010_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP
) > outputs/tract_white_poc_chicago_2010.csv


(
python pipeline/calculate_metrics.py chicago-maup/tract_2020_cbsa_16980_march_2020_geographies_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "tract_2020_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/tract_white_black_chicago_2020.csv

(
python pipeline/calculate_metrics.py chicago-maup/tract_2020_cbsa_16980_march_2020_geographies_connected.json BLACK POC TOTPOP --headers-only
fd -g "tract_2020_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP
) > outputs/tract_white_poc_chicago_2020.csv


(
python pipeline/calculate_metrics.py chicago-maup/bg_2010_cbsa_16980_march_2020_geographies_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "bg_2010_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/bg_white_black_chicago_2010.csv

(
python pipeline/calculate_metrics.py chicago-maup/bg_2010_cbsa_16980_march_2020_geographies_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "bg_2010_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP
) > outputs/bg_white_poc_chicago_2010.csv

(
python pipeline/calculate_metrics.py chicago-maup/bg_2020_cbsa_16980_march_2020_geographies_connected.json BLACK POC TOTPOP --headers-only
fd -g "bg_2020_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/bg_white_black_chicago_2020.csv


(
python pipeline/calculate_metrics.py chicago-maup/bg_2020_cbsa_16980_march_2020_geographies_connected.json BLACK POC TOTPOP --headers-only
fd -g "bg_2020_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP
) > outputs/bg_white_poc_chicago_2020.csv


(
python pipeline/calculate_metrics.py chicago-maup/block_2010_cbsa_16980_march_2020_geographies_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "block_2010_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/block_white_black_chicago_2010.csv

(
python pipeline/calculate_metrics.py chicago-maup/block_2010_cbsa_16980_march_2020_geographies_connected.json BLACK WHITE TOTPOP --headers-only
fd -g "block_2010_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP
) > outputs/block_white_poc_chicago_2010.csv



(
python pipeline/calculate_metrics.py chicago-maup/block_2020_cbsa_16980_march_2020_geographies_connected.json BLACK POC TOTPOP --headers-only
fd -g "block_2020_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP
) > outputs/block_white_black_chicago_2020.csv

(
python pipeline/calculate_metrics.py chicago-maup/block_2020_cbsa_16980_march_2020_geographies_connected.json BLACK POC TOTPOP --headers-only
fd -g "block_2020_cbsa_16980_march_2020_geographies_connected.json" chicago-maup/ \
| parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP
) > outputs/block_white_poc_chicago_2020.csv
