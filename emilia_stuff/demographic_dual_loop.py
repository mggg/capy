#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Jun  9 13:30:18 2018

@author: emiliaxochitl
"""

import os

import networkx as nx
import json

# geospatial
import geopandas as gpd
import pysal as ps
import numpy as np
import make_graph
# visualization
import matplotlib.pyplot as plt
print(os.getcwd())

mysterious_problems = [ 'Los Alamos NM', 'San Jose-Sunnyvale-Santa Clara CA','Wichita KS', ]

index_problem = ['Atlanta-Sandy Springs-Roswell GA','Atlantic City - Hammonton NJ','Charlotte-Concord-Gastonia NC', 'Chattanooga TN-GA','Cleveland-Elyra OH', 'Detroit-Warren-Dearborn MI', 'Greensboro-High Point NC','Hartford CT','Milwaukee-Waukesha-West Allis WI','Raleigh NC', 'Washington-Arlington-Alexandria DC-VA-MD-WV',]

geometry_problem = ['Albuquerque NM','Baltimore-Columbia-Towson MD','Baton Rouge LA', 'Birmingham-Hoover AL', 'Boise City ID', 'Buffalo-Cheektowaga-Niagara Falls NY', 'Champaign-Urbana IL', 'Charlottesville VA','Cincinnati OH-KY-IN', 'Corpus Christi TX', 'Dallas-Fort Worth-Arlington TX', 'Denver-Aurora-Lakewood CO', 'Durham-Chapel Hill NC', 'Eugene OR', 'Fresno CA','Houston-The Woodlands-Sugar Land TX', 'Idaho Falls ID', 'Indianapolis-Carmel-Anderson IN','Jackson MS', 'Knoxville TN', 'Little Rock-North Little Rock-Conway AR','Memphis TN-MS-AR','Merced CA', 'Minneapolis-St Paul-Bloomington MN-WI', 'Modesto CA','Montgomery AL',  'Nashville-Davidson-Murfreesboro-Franklin TN',  'Ogden-Clearfield UT', 'Omaha-Council Bluffs NE-IA','Portland-Vancouver-Hillsboro OR-WA','Provo-Orem UT', 'Richmond VA', 'Sacramento-Roseville-Arden-Arcade CA', 'San Francisco-Oakland-Hayward CA',  'Seattle-Tacoma-Bellevue WA','St Louis MO-IL', 'Tulsa OK', ]



cities = ['Albany-Schenectady-Troy', 'Ann Arbor MI', 'Athens-Clark County GA', 'Austin-Round Rock TX', 'Bloomington IN', 'Boston-Cambridge-Newton MA', 'Boulder CO', 'Bridgeport-Stamford-Norwalk CT', 'Burlington-South Burlington VT', 'Cedar Rapids IA', 'Chicago-Naperville-Elgin IL-IN-WI', 'Colorado Springs CO', 'Des Moines-West Des Moines IA', 'Duluth MN-WI', 'El Paso TX', 'Flint MI',  'Grand Rapids-Wyoming MI',  'Harrisburg-Carlisle PA', 'Huntingdon PA',  'Iowa city IA', 'Ithaca NY', 'Jacksonville FL', 'Junction City KS', 'Kansas city MO-KS', 'Lafayette-West Lafayette IN', 'Lancaster PA', 'Las Vegas-Henderson-Paradise NV', 'Lincoln NE','Madison WI',  'Los Angeles-Long Beach-Anaheim CA',  'McAllen-Edingburg-Mission TX','Miami-Fort Lauderdale-West Palm Beach FL','New Haven-Milford CT', 'New Orleans-Metairie LA', 'New York-Newark-Jersey City NY-NJ-PA',  'Oklahoma City-OK','Orlando-Kissimmee-Sanford FL', 'Philadelphia-Camden-Wilmington PA-NJ-DE-MD', 'Phoenix-Mesa-Scottsdale AZ', 'Pittsburgh PA', 'Plattsburgh NY', 'Providence-Warwick RI-MA', 'Reno NV', 'Rio Grande City TX', 'Riverside-San Bernadino-Ontario CA', 'Rochester NY',  'Salt Lake City UT', 'San Antonio-New Braunfels TX', 'San Diego-Carlsbad CA', 'Santa Cruz-Watsonville CA', 'Santa Fe NM', 'Savannah GA','Syracuse NY', 'Tallahassee FL', 'Tampa-St Petersburg-Clearwater FL', 'Toledo OH', 'Tucson AZ', 'Tuscaloosa AL','Virginia Beach-Norfolk-Newport News VA-NC', 'Youngstown-Warren-Boardman OH-PA']




#input your shape file

for city in index_problem:
    
    county_shp = "Index_problem/"+city+".shp"
    df_counties = gpd.read_file(county_shp)
    df_counties.plot()
    
    county_centroids = df_counties.centroid
    c_x = county_centroids.x
    c_y = county_centroids.y
    
    # Spatial Weights
    rW = ps.rook_from_shapefile(county_shp)
    #rW[10] # View neighbors for specific row -> note, all weights = 1.0
    #rW.neighbors # View all neighbors
    #rW.full()[0] # View full contiguity matrix

    # Would be nice to see attributes for neighbors:
    self_and_neighbors = [10]
    self_and_neighbors.extend(rW.neighbors[10])
    df_counties.iloc[self_and_neighbors, :5]

    #this just keeps track of progress
    print("at graph")
    
    #here is where we are storing desired information at each vertex. The DPXXX entries correspond to demographic information which can be found in the attributes table of the shapefile. GEOID10 is the id of the tract, and we are taking the DP1 profiles, DPSF11 (Hispanic or Latino by race). 
    #DP0110001: TOTAL
    #DP0110002: HISPANIC
    #DP0110011: NOT HISPANIC, WHITE ALONE
    #DP0110012: NOT HISPANIC, BLACK ALONE
    #DP0110013: NOT HISPANIC, AMERICAN INDIAN ALONE
    #DP0110014: NOT HISPANIC, ASIAN ALONE
    #DP0110015: NOT HISPANIC, NATIVE HAWAIIAN/PACIFIC ISLANDER ALONE
    #DP0110016: NOT HISPANIC, OTHER RACE ALONE
    #graph = make_graph.construct_graph_from_file(county_shp, 'GEOID10', ['DP0110001', 'DP0110002','DP0110011','DP0110012','DP0110013', 'DP0110014','DP0110015', 'DP0110016'])
    graph = make_graph.construct_graph(county_shp, id_col="GEOID10",  data_cols=['DP0110001', 'DP0110002','DP0110011','DP0110012','DP0110013', 'DP0110014','DP0110015', 'DP0110016'], 
                                       data_source_type="fiona")
    nx.draw(graph)
    plt.show()
    #we're saving the demographic dual graph as a json, to compute the energies from. 

    data = nx.readwrite.json_graph.adjacency_data(graph)
    
    with open("json10/"+city+"_data.json", "w") as f:
        json.dump(data, f)

        

    

