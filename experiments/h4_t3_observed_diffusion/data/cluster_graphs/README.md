These json files contain cluster graphs selected in Chicago and Philadelphia. Clusters are defined using 2020 graphs of these cities:

1. In 2020 find the two largest components with the share of the Black population over the city's mean share
2. Then apply these definitions to previous years. Since the nodes often don't match by id (due to merges and splits and other changes over time), they are matched by overlapping the areas: a tract is included if its overlap with the 2020 city polygon is over 50%.

Node attributes:
`black_pop` is the count of Black residents, `white_pop` the the count of White residents, `total_pop` is total population count, which may be more than the sum of Black and White populations.

`centroid_x` and `centroid_y` are lat/lon of the tract centroid and are useful for plotting.