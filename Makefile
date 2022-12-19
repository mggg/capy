.PHONY: all

CHICAGO_REF := 9618502_16980_march_2020
OUTPUT_DIR := chicago-maup

../data.mggg.org/census-2020/il/il_%.shp: cbsas/defs/$(CHICAGO_REF).shp
	python3 pipeline/overlaps.py $@ "cbsas/defs/$(CHICAGO_REF).shp" $(OUTPUT_DIR) --prefix "$*_"
	python3 pipeline/gen_duals.py $(OUTPUT_DIR)/$*_$(CHICAGO_REF)_cbsa_tracts.shp $(OUTPUT_DIR)/$*_$(CHICAGO_REF)_orig.json $(OUTPUT_DIR)/$*_$(CHICAGO_REF)_connected.json --attr GEOID20 --pop-col TOTPOP20

chicago_duals: $(wildcard ../data.mggg.org/census-2020/il/il_*.shp)

chicago_black_header: chicago_duals
	python3 pipeline/calculate_metrics.py $(OUTPUT_DIR)/il_bg_cbsa_tracts_connected.json BLACK WHITE TOTPOP --headers-only > outputs/white_black_chicago.csv
chicago_poc_header: chicago_duals
	python3 pipeline/calculate_metrics.py $(OUTPUT_DIR)/il_bg_cbsa_tracts_connected.json POC WHITE TOTPOP --headers-only > outputs/white_poc_chicago.csv

chicago-maup/%connected.json: chicago_black_header
	python3 pipeline/calculate_metrics.py $@ BLACK WHITE TOTPOP >> outputs/white_black_chicago.csv
	python3 pipeline/calculate_metrics.py $@ POC WHITE TOTPOP >> outputs/white_poc_chicago.csv

chicago_black_csv: chicago_black_header $(wildcard chicago-maup/*connected.json)
chicago_poc_csv: chicago_poc_header $(wildcard chicago-maup/*connected.json)

chicago: chicago_black_csv chicago_poc_csv

all: chicago

clean: 
	rm chicago-maup/*
