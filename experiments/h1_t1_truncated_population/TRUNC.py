 #For truncation variant:
    #for node in graph.nodes():
    #    rho =  graph.nodes[node][x_col] / graph.nodes[node][tot_col]
    #    graph.nodes[node][tot_col] = 1000
    #    graph.nodes[node][x_col] = int(1000 * rho)
    #   graph.nodes[node][y_col] = 1000 - graph.nodes[node][x_col]
    #for node in graph.nodes():
    #    threshold = (graph.nodes[node][x_col] + graph.nodes[node][y_col]) / 2
    #    if graph.nodes[node][x_col] >= threshold: #so ties break in favor of x_col
    #        graph.nodes[node][x_col] = graph.nodes[node]["TOTPOP"]
    #        graph.nodes[node][y_col] = 0
    #    else: 
    #        graph.nodes[node][x_col] = 0
    #        graph.nodes[node][y_col] = graph.nodes[node]["TOTPOP"]

