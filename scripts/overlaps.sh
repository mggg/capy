echo "filename, target_name, source_area, overlap_area, overlap_percentage" > outputs/coverage_stats.csv
python3 pipeline/overlaps.py processed/2020_tracts.shp 'cbsas/defs/*.shp' cbsas/2020 >> outputs/coverage_stats.csv
python3 pipeline/overlaps.py processed/2010_tracts.shp 'cbsas/defs/*.shp' cbsas/2010 >> outputs/coverage_stats.csv
python3 pipeline/overlaps.py processed/2000_tracts.shp 'cbsas/defs/*.shp' cbsas/2000 >> outputs/coverage_stats.csv
python3 pipeline/overlaps.py processed/1990_tracts.shp 'cbsas/defs/*.shp' cbsas/1990 >> outputs/coverage_stats.csv
python3 pipeline/overlaps.py processed/1980_tracts.shp 'cbsas/defs/*.shp' cbsas/1980 >> outputs/coverage_stats.csv
python3 pipeline/overlaps.py processed/1970_tracts.shp 'cbsas/defs/*.shp' cbsas/1970 >> outputs/coverage_stats.csv
