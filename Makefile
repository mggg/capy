.PHONY: all

CHICAGO_REF := 9618502_16980_march_2020
OUTPUT_DIR := chicago-maup

../data.mggg.org/census-2020/il/il_%.shp: cbsas/defs/$(CHICAGO_REF).shp
	python3 pipeline/overlaps.py $@ "cbsas/defs/$(CHICAGO_REF).shp" $(OUTPUT_DIR) --prefix "$*_"
	python3 pipeline/gen_duals.py $(OUTPUT_DIR)/$*_$(CHICAGO_REF)_cbsa_tracts.shp $(OUTPUT_DIR)/$*_$(CHICAGO_REF)_orig.json $(OUTPUT_DIR)/$*_$(CHICAGO_REF)_connected.json --attr GEOID20 --pop-col TOTPOP20

chicago_duals: $(wildcard ../data.mggg.org/census-2020/il/il_*.shp)

chicago_black_header: ../data.mggg.org/census-2020/il/il_sldl.shp
	python3 pipeline/calculate_metrics.py $(OUTPUT_DIR)/il_tract_cbsa_sldl_connected.json BLACK WHITE TOTPOP --headers-only > outputs/white_black_chicago.csv
chicago_poc_header: ../data.mggg.org/census-2020/il/il_sldl.shp
	python3 pipeline/calculate_metrics.py $(OUTPUT_DIR)/il_tract_cbsa_sldl_connected.json POC WHITE TOTPOP --headers-only > outputs/white_poc_chicago.csv

chicago-maup/%_$(CHCIAGO_REF)_connected.json: chicago_black_header chicago_poc_header ../data.mggg.org/census-2020/il/il_%.shp
	python3 pipeline/calculate_metrics.py $@ BLACK WHITE TOTPOP >> outputs/white_black_chicago.csv
	python3 pipeline/calculate_metrics.py $@ POC WHITE TOTPOP >> outputs/white_poc_chicago.csv

outputs/white_black_chicago.csv: chicago_black_header chicago_duals $(wildcard chicago-maup/*connected.json)
outputs/white_poc_chicago.csv: chicago_poc_header chicago_duals $(wildcard chicago-maup/*connected.json)

chicago: outputs/white_black_chicago.csv outputs/white_poc_chicago.csv

all: chicago

clean: 
	rm chicago-maup/*
