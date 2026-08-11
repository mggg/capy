python pipeline/gen_duals.py \
    "ia_files/sh_joined_2010/sh_joined_2010.shp" \
    "ia_files/iowa_graph_2010_orig.json" \
    "ia_files/iowa_graph_2010.json"22\
    --attr "GEOID10"

python pipeline/gen_duals.py \
    "ia_files/sh_joined_2020/sh_joined_2020.shp" \
    "ia_files/iowa_graph_2020_orig.json" \
    "ia_files/iowa_graph_2020.json"22\
    --attr "GEOID"