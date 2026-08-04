def generate_graph(df, node_name, edge_name, nodes_of_interest=[]):
    """ Generates a NetworkX undirected connectivity graph from a Dataframe object.
        The Dataframe contains "node_name" and "edge_name" columns.
        Any unique "edge_name" item can have multiple entries, one per "node_name" it's associated with.
        The resulting graph contains "node_name" nodes, with edges between any with common "edge_name" entries.
        
        e.g. "Repo" is the node_name, "User Id" is the edge_name.
                Each node is a unique repo. Edges show repos that share the same users.

        Can limit which nodes in the DataFrame are graphed by providing a "nodes_of_interest" list.
        If provided, any "node_of_interest" that shares a "edge_name" with a "node" not of interest will be counted and returned in a dict.
        
        The 'weight' attribute is set for both nodes and edges:
            - Node weight = number of unique "edge_names" it appears with. (i.e. number of Users in the Repo)
            - Edge weight = number of unique connections between the nodes. (i.e. number of Users in the connected Repos)

        Inputs: (df, node_name, edge_name, nodes_of_interest)
                df: Dataframe to turn into Graph.
                node_name: Name of the node column. Defaults to "Repo".
                edge_name: Name of the connectivity column. Defaults to "User Id".
                nodes_of_interest: Optional -- List of nodes to include in graph.

        Returns: ( graph, has_other_edges )
                 graph: Resulting NetworkX Graph.
                 has_other_edges: Returns a dictionary of nodes that have connections outside "nodes_of_interest". 
                 
        Future Notes: Return the matrix created to complete the calculation? """

    import pandas as pd, networkx as nx, numpy as np
    
    other_label = "External"
    calc_other_edges = bool(nodes_of_interest)
    
    list_of_edges = df[edge_name].unique()
    if nodes_of_interest:
        nodes_of_interest.append(other_label)
    else:
        nodes_of_interest = df[node_name].unique()

    conn_matrix = pd.DataFrame(index=nodes_of_interest, columns=nodes_of_interest, dtype='int32')
    conn_matrix.fillna(0, inplace=True)

    # Each row is a potential "end" of an edge
    for end in list_of_edges:
        my_node_list = (df[df[edge_name].str.fullmatch(end)])[node_name].unique()
        #my_node_list.sort()
        my_node_list = np.sort(my_node_list)
        for nodeA in my_node_list:
            for nodeB in my_node_list:
                if (not (nodeA in nodes_of_interest) and not (nodeB in nodes_of_interest)):
                    conn_matrix.loc[other_label, other_label] += 1
                elif (not (nodeA in nodes_of_interest)):
                    conn_matrix.loc[nodeB, other_label] += 1
                elif (not (nodeB in nodes_of_interest)):
                    conn_matrix.loc[nodeA, other_label] += 1
                elif (nodeA <= nodeB):
                    # As this is undirected, only need one half of the matrix.
                    conn_matrix.loc[nodeA, nodeB] += 1

    graph_nodes = []
    graph_edges = []
    
    for repoA in nodes_of_interest:
        for repoB in nodes_of_interest:
            if ((repoA != other_label) and (repoB != other_label)):
                if (repoA == repoB):
                    graph_nodes.append((repoA, {"weight": conn_matrix.loc[repoA, repoA]}))
                elif (repoA < repoB):
                    if (conn_matrix.loc[repoA, repoB] > 0):
                        graph_edges.append((repoA, repoB, {"weight": conn_matrix.loc[repoA, repoB]}))

    # Add this as key in attribute dictionary instead.
    has_other_edges = {}
    if (calc_other_edges):
        for node in nodes_of_interest:
            if (conn_matrix.loc[node, other_label] > 0):
                has_other_edges[node] = conn_matrix.loc[node, other_label]
                        
    my_graph = nx.Graph()
    my_graph.add_nodes_from(graph_nodes)
    my_graph.add_edges_from(graph_edges)
    
    return my_graph, has_other_edges




def generate_graph_distance(df, node_name, edge_name, nodes_of_interest, ndegrees=1):

    import collections, pandas as pd, networkx as nx
    
    nodes_by_degree = []
    nodes_by_degree.append(nodes_of_interest)
    users_by_degree = []
    users_by_degree.append([])

    graph_nodes = collections.defaultdict(dict)
    graph_edges = collections.defaultdict(dict)

    degree = 0

    while ( (len(nodes_of_interest) != 0) and (degree <= ndegrees) ):

        user_list = []
        node_list = []
    
        for node in nodes_of_interest:
            user_list_node = (df[df[node_name].str.fullmatch(node)])[edge_name].to_list()
            node_size = len(user_list_node)
        
            # Remove previous degree's users & previous users found on this degree
            # Prevents duplicate connections. Total # of users for this node saved in node_size
            user_list_trimmed = [i for i in user_list_node if i not in users_by_degree[-1]]
            user_list_new = [i for i in user_list_trimmed if i not in user_list]
            user_list.extend(user_list_new)

            # Add this node to the list
            graph_nodes[node]["weight"] = node_size
            graph_nodes[node]["degree"] = degree
        
            if (len(user_list_new) == 0):
                continue

            node_list_new = []
            for edge in user_list_new:
                node_list_new.extend( (df[df[edge_name].str.fullmatch(edge)])[node_name].to_list() )

            node_counts = pd.Series(node_list_new).value_counts()
        
            # Build edges
            # Guarantee an order of the edge tuples to prevent duplication: non-directed graph
            # Ignore (node == item) -- graph_nodes set above
            for item,count in node_counts.items():
                # After desired degrees completed, one more iteration for that level's connections,
                # hence ignoring anything not on the level.
                if ((degree < ndegrees) or (item in nodes_by_degree[-1])):
                    if (node < item):
                        this_edge = (node, item)
                        graph_edges[this_edge]["weight"] = graph_edges.get(this_edge, {}).get("weight", 0) + count
                    elif (item < node):
                        this_edge = (item, node)
                        graph_edges[this_edge]["weight"] = graph_edges.get(this_edge, {}).get("weight", 0) + count
        
            node_list.extend( list(set(node_list_new)) )
    
        # Prepare for next degree. (Remove this degree from next degree nodes)
        if (degree < ndegrees):
            node_list_trimmed = [i for i in node_list if i not in nodes_by_degree[-1]]
            nodes_of_interest = list(set(node_list_trimmed))
            nodes_by_degree.append(nodes_of_interest)

        users_by_degree.append(user_list)
    
        degree = degree + 1

    users_by_degree.pop(0)
    list_of_nodes = [(k,v) for k, v in graph_nodes.items()]
    list_of_edges = [(k[0], k[1] ,v) for k, v in graph_edges.items()]

    my_graph = nx.Graph()
    my_graph.add_nodes_from(list_of_nodes)
    my_graph.add_edges_from(list_of_edges)
    
    return my_graph, nodes_by_degree







def calc_pos(graph, xstart=0, ystart=0, xbuffer=0, ybuffer=0, nshells=5, kk_weight='weight', nodes_by_set=None):
    """ Calculates a position layout from a NetworkX graph for graphing in Plotly.
        Separates connected graphs to avoid overlapping.
        Starting at (xstart,ystart), places graphs from smallest to largest size in the +x direction,
                                     stacking same sized graphs in the +y direction.
        Combines degree(0) nodes into a single shell layout graph (placed first).
        Remaining connected subgraphs use kamada_kawai layout with optional weight.

        Inputs: graph -- networkX graph to calc positions for visualization
                xstart, ystart -- lower left bound of pos
                xbuffer, ybuffer -- space between subgraphs
                nshells -- number of shells created with the degree(0) graph, default 5.
                kk_weight -- name of the node attribute used to weight the kamada_kawai layout, default 'weight'.

        Outputs: return -- (pos, list_of_subgraphs)
                 pos: dictionary of (x, y) position, keyed by node name
                 list_of_subgraphs: subgraph views of graph, broken down by size of each component
                 
        Future Note: Lambda function for scale? """

    import math, networkx as nx
    
    # Calculate and create connected subgraphs of the graph.
    # Separate into list of lists of number of nodes in each component for visualization math.
    subgraphs = [graph.subgraph(c) for c in sorted(nx.connected_components(graph), key=len)]
    subgraph_lists = []
    
    prev = 0
    start = 0
    ng = len(subgraphs)
    if (ng == 0):
        return dict(), list()
    elif (ng == 1):
        subgraph_lists.append(subgraphs)
    else:
        for index, sg in enumerate(subgraphs):
            if (index == 0):
                prev = len(sg)
                continue
            if (len(sg) != prev):
                subgraph_lists.append(subgraphs[start:index])
                start = index
                prev = len(sg)
            if (index == ng-1):
                subgraph_lists.append(subgraphs[start:index+1])

    # Combine subgraphs with only one node into one big subgraph.
    # Should be ordered, so only need to check if first list has length one.
    # Will replace first list with a single, large graph.
    if (len(subgraph_lists[0][0]) == 1):
        single_nodes = []
        for sg in subgraph_lists[0]:
            single_nodes.append(list(sg.nodes)[0])

        single_subgraph = graph.subgraph(single_nodes)
        subgraph_lists[0].clear()
        subgraph_lists[0].append(single_subgraph)
        
    # Generate positions using a layout for transfer to plotly.
    # For each, adjust the positions to separate connected_graphs to make all visible.
    # This method stacks graphs of the same size together for visibility. Can be changed later.

    # Position is keyed to node, so concatenating into one giant list.
    graph_pos = {}

    xcurr = xstart
    ycurr = ystart

    for group in subgraph_lists:
        ycurr = ystart
        scale = math.sqrt(group[0].number_of_nodes())
        for graph in group:
            center = [xcurr+scale, ycurr+scale]
            if (nodes_by_set != None):
                this_pos = nx.shell_layout(graph, nlist=nodes_by_set, scale=scale, center=center)
            else:
                if (nx.number_connected_components(graph) == len(graph)):   # This is the disconnected graph.
                    # Shell layout for now. Adjustable.
                    size = int(len(graph.nodes)/nshells)+1
                    node_sets = [list(graph.nodes)[x:x+size] for x in range(0, len(graph.nodes), size)]
                    this_pos = nx.shell_layout(graph, nlist=node_sets, scale=scale, center=center)
                else:
                    this_pos = nx.kamada_kawai_layout(graph, weight=kk_weight, scale=scale, center=center)

            graph_pos.update(this_pos)
            ycurr = ycurr + 2*scale + ybuffer
        xcurr = xcurr + 2*scale + xbuffer

    return graph_pos, subgraph_lists





def draw_graph(graph, pos, node_color=[],
               node_text=None, edge_text=None, marker_symbols="circle",
               
               bg_graph=None, bg_pos=None, bg_node_color=[],
               bg_node_text=None, bg_edge_text=None, bg_marker_symbols="circle",
               
               color_min=None, color_max=None, colorbar_title="", plot_title="Title goes here!",
               height=720, width=1028,
               x_range=None, y_range=None, x_margin_percent=6, y_margin_percent=6):

    """ Create a Plotly figure from the NetworkX graph and a dictionary of (x,y) positions.
        Creates using Plotly Scatter graphs, with a "marker"-based node Scatter and a "line"-based edge Scatter.
        Can also include an optional edge-centered marker Scatter for edge hover text.
        
        Inputs: graph -- NetworkX graph to plot.
                pos -- Dictionary of node positions, keyed by node name matching graph node names.

                node_color -- Optional node color. Can be single string, or graph.nodes() ordered list of values for a scale.
                node_text -- Optional hover text for nodes. Can be a single string, or graph.nodes() ordered list of strings.
                edge_text -- Optional hover text for edges. Can be a single string, or graph.edges() ordered list of strings.
                marker_symbols -- Optional marker symbol type. Can be a single valid Plotly marker type, or a graph.nodes() ordered list.
                
                color_min -- Optional minimum value for colored scale. 
                color_max -- Optional maximum value for colored scale.
                colorbar_title -- Optional title for the color bar.
                height -- Height of graph in pixels. Default is 720.
                width -- Width of graph in pixels. Default is 1028.
                x_range -- x range of the printed domain, as (lo, hi) tuple. Default is None (calculated based on pos range).
                y_range -- y range of the printed domain, as (lo, hi) tuple. Default is None (calculated based on pos range).
                x_margin_percent -- Size of the x-direction space margin in percentage of total x_domain.
                y_margin_percent -- Size of the y-direction space margin in percentage of total y_domain.
        
        Outputs: Returns Plotly Figure of graph.
        
        Future Notes: Continue to add inputs and conditionals as other Figure options become flushed out.
    """

    import plotly.graph_objects as go
    
    # Calc x-y domain, if not provided.
    if (x_range == None):
        x_range = (min(pos.items(), key=lambda i : i[1][0])[1][0], max(pos.items(), key=lambda i : i[1][0])[1][0])
        x_adjust = (x_range[1] - x_range[0])*(x_margin_percent/100)
        x_range = (x_range[0]-x_adjust, x_range[1]+x_adjust)
    if (y_range == None):
        y_range = (min(pos.items(), key=lambda i : i[1][1])[1][1], max(pos.items(), key=lambda i : i[1][1])[1][1])
        y_adjust = (y_range[1] - y_range[0])*(y_margin_percent/100)
        y_range = (y_range[0]-y_adjust, y_range[1]+y_adjust)

    # Calc color, if not provided.
    if (color_min == None):
        color_min = min(node_color)
    if (color_max == None):
        color_max = max(node_color)

    figure_elements = []
    
    # Background graph elements
    # ==========================================
    
    if (bg_graph and bg_pos):

        bg_node_x = []
        bg_node_y = []
        for node in bg_graph.nodes():
            x, y = bg_pos[node]
            bg_node_x.append(x)
            bg_node_y.append(y)

        bg_edge_x = []
        bg_edge_y = []
        bg_edge_cx = []
        bg_edge_cy = []
        for edge in bg_graph.edges():
            x0, y0 = bg_pos[edge[0]]
            x1, y1 = bg_pos[edge[1]]
            bg_edge_x.append(x0)
            bg_edge_x.append(x1)
            bg_edge_x.append(None)
            bg_edge_y.append(y0)
            bg_edge_y.append(y1)
            bg_edge_y.append(None)
            bg_edge_cx.append((x0+x1)/2)
            bg_edge_cy.append((y0+y1)/2)

        bg_edge_trace = go.Scatter(
            x=bg_edge_x, y=bg_edge_y,
            line=dict(width=0.5, color='#888'),
            hoverinfo='none',
            mode='lines')

        # Ordering of elements is important. Edge first = lowest in the figure.
        figure_elements.append(bg_edge_trace)

        bg_node_trace = go.Scatter(
            x=bg_node_x, y=bg_node_y,
            mode='markers',
            hoverinfo='text',
            text=bg_node_text,
            marker=dict(
                showscale=True,
                # https://plotly.com/python-api-reference/generated/plotly.graph_objects.Scatter.html
                # Search for: "property colorscale"
                colorscale='Rainbow',
                reversescale=True,
                color=bg_node_color,
                size=8,
                symbol=bg_marker_symbols,
                cmin=color_min,
                cmax=color_max,
                opacity=0.2,
                # SCRAP BG COLOR BAR FOR REGULAR COLOR BAR?
                colorbar=dict(
                    thickness=15,
                    title=colorbar_title,
                    xanchor='left',
                    titleside='right'
                ),
                line_width=2))

        figure_elements.append(bg_node_trace)

        if bg_edge_text:
            bg_edge_center = go.Scatter(
                                 x=bg_edge_cx, y=bg_edge_cy,
                                 mode='markers',
                                 hoverinfo='text',
                                 text=bg_edge_text,
                                 marker=dict(
                                     opacity=0,
                                     color="black",
                                     size=5
                                 ),
                                 line_width=2)

            figure_elements.append(bg_edge_center)
    
    # Standard graph elements
    # ==========================================
    
    node_x = []
    node_y = []
    for node in graph.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
    
    edge_x = []
    edge_y = []
    edge_cx = []
    edge_cy = []
    for edge in graph.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.append(x0)
        edge_x.append(x1)
        edge_x.append(None)
        edge_y.append(y0)
        edge_y.append(y1)
        edge_y.append(None)
        edge_cx.append((x0+x1)/2)
        edge_cy.append((y0+y1)/2)
    
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines')

    # Ordering of elements is important. Edge first = lowest in the figure.
    figure_elements.append(edge_trace)

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(
            showscale=True,
            # https://plotly.com/python-api-reference/generated/plotly.graph_objects.Scatter.html
            # Search for: "property colorscale"
            colorscale='Rainbow',
            reversescale=True,
            color=node_color,
            size=10,
            symbol=marker_symbols,
            cmin=color_min,
            cmax=color_max,
            colorbar=dict(
                thickness=15,
                title=colorbar_title,
                xanchor='left'#,
#                titleside='right'
            ),
            line_width=2))
    
    figure_elements.append(node_trace)
    
    if edge_text:
        edge_center = go.Scatter(
                        x=edge_cx, y=edge_cy,
                        mode='markers',
                        hoverinfo='text',
                        text=edge_text,
                        marker=dict(
                            opacity=0,
                            color="black",
                            size=5
                        ),
                        line_width=2)
        
        figure_elements.append(edge_center)

    # Generate the Figure from the elements
    # ==========================================        
        
    fig = go.Figure(data=figure_elements,
                    layout=go.Layout(
                    title='<br>',
#                    titlefont_size=16,
                    showlegend=False,
                    hovermode='closest',
                    margin=dict(b=20,l=5,r=5,t=40),
                    annotations=[ dict(
                        text=plot_title,
                        showarrow=False,
                        xref="paper", yref="paper",
                        x=0.005, y=-0.002 ) ],
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=x_range),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=y_range),
                    height=height,
                    width=width)
                    )
    
    return fig




def draw_graph_new(graph, pos, node_color=[], node_opacity=[],
                   node_text=[], edge_text=[], marker_symbols=[],

#                   bg_graph=None, bg_pos=None, bg_node_color=[],
#                   bg_node_text=None, bg_edge_text=None, bg_marker_symbols="circle",

                   color_min=None, color_max=None, title="", colorbar_title="",
                   height=720, width=1028,
                   x_range=None, y_range=None, x_margin_percent=6, y_margin_percent=6):

    """ Create a Plotly figure from the NetworkX graph and a dictionary of (x,y) positions.
        Creates using Plotly Scatter graphs, with a "marker"-based node Scatter and a "line"-based edge Scatter.
        Can also include an optional edge-centered marker Scatter for edge hover text.
        
        Inputs: graph -- NetworkX graph to plot.
                pos -- Dictionary of node positions, keyed by node name matching graph node names.

                node_color -- Optional node color. Can be single string, or graph.nodes() ordered list of values for a scale.
                node_text -- Optional hover text for nodes. Can be a single string, or graph.nodes() ordered list of strings.
                edge_text -- Optional hover text for edges. Can be a single string, or graph.edges() ordered list of strings.
                marker_symbols -- Optional marker symbol type. Can be a single valid Plotly marker type, or a graph.nodes() ordered list.
                
                color_min -- Optional minimum value for colored scale. 
                color_max -- Optional maximum value for colored scale.
                colorbar_title -- Optional title for the color bar.
                height -- Height of graph in pixels. Default is 720.
                width -- Width of graph in pixels. Default is 1028.
                x_range -- x range of the printed domain, as (lo, hi) tuple. Default is None (calculated based on pos range).
                y_range -- y range of the printed domain, as (lo, hi) tuple. Default is None (calculated based on pos range).
                x_margin_percent -- Size of the x-direction space margin in percentage of total x_domain.
                y_margin_percent -- Size of the y-direction space margin in percentage of total y_domain.
        
        Outputs: Returns Plotly Figure of graph.
        
        Future Notes: Continue to add inputs and conditionals as other Figure options become flushed out.
    """

    import plotly.graph_objects as go
    import plotly.subplots

    # Check if lists are the same size
    # Change individual items to lists
    
    # Build subplots
    # Add scatters in order (add row, column options?)
    # Build layout
    # Return result.
    
    # Calc x-y domain, if not provided.
    if (x_range == None) or (y_range == None):
        pos_flat = [i for my_pos in pos for i in my_pos.items()]
        if (x_range == None):
            x_range = (min(pos_flat, key=lambda i : i[1][0])[1][0], max(pos_flat, key=lambda i : i[1][0])[1][0])
            x_adjust = (x_range[1] - x_range[0])*(x_margin_percent/100)
            x_range = (x_range[0]-x_adjust, x_range[1]+x_adjust)
        if (y_range == None):
            y_range = (min(pos_flat, key=lambda i : i[1][1])[1][1], max(pos_flat, key=lambda i : i[1][1])[1][1])
            y_adjust = (y_range[1] - y_range[0])*(y_margin_percent/100)
            y_range = (y_range[0]-y_adjust, y_range[1]+y_adjust)
        del pos_flat

    # Calc color range, if not provided.
    if (color_min == None) or (color_max == None):
        color_flat = [i for my_color in node_color for i in my_color]
        if (color_min == None):
            color_min = min(color_flat)
        if (color_max == None):
            color_max = max(color_flat)
        del color_flat

    figure_elements = []
    
    for i in range(len(graph)):
    
        node_x = []
        node_y = []
        for node in graph[i].nodes():
            x, y = pos[i][node]
            node_x.append(x)
            node_y.append(y)
    
        edge_x = []
        edge_y = []
        edge_cx = []
        edge_cy = []
        for edge in graph[i].edges():
            x0, y0 = pos[i][edge[0]]
            x1, y1 = pos[i][edge[1]]
            edge_x.append(x0)
            edge_x.append(x1)
            edge_x.append(None)
            edge_y.append(y0)
            edge_y.append(y1)
            edge_y.append(None)
            edge_cx.append((x0+x1)/2)
            edge_cy.append((y0+y1)/2)
    
        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=0.5, color='#888'),
            hoverinfo='none',
            mode='lines')

        # Ordering of elements is important. Edge first = lowest in the figure.
        figure_elements.append(edge_trace)

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers',
            hoverinfo='text',
            text=node_text[i],
            marker=dict(
                showscale=True,
                # https://plotly.com/python-api-reference/generated/plotly.graph_objects.Scatter.html
                # Search for: "property colorscale"
                colorscale='Rainbow',
                reversescale=True,
                color=node_color[i],
                size=10,
                symbol=marker_symbols[i],
                cmin=color_min,
                cmax=color_max,
                opacity=node_opacity[i],
                colorbar=dict(
                    thickness=15,
                    title=colorbar_title,
                    xanchor='left',
                    titleside='right'
                ),
                line_width=2))
    
        figure_elements.append(node_trace)
    
        if edge_text[i]:
            edge_center = go.Scatter(
                            x=edge_cx, y=edge_cy,
                            mode='markers',
                            hoverinfo='text',
                            text=edge_text[i],
                            marker=dict(
                                opacity=0,
                                color="black",
                                size=5
                            ),
                            line_width=2)
        
        figure_elements.append(edge_center)

    # Generate the Figure from the elements
    # ==========================================        
        
    fig = go.Figure(data=figure_elements,
                    layout=go.Layout(
                    title='<br>',
                    titlefont_size=16,
                    showlegend=False,
                    hovermode='closest',
                    margin=dict(b=20,l=5,r=5,t=40),
                    annotations=[ dict(
                        text=title,
                        showarrow=False,
                        xref="paper", yref="paper",
                        x=0.005, y=-0.002 ) ],
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=x_range),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=y_range),
                    height=height,
                    width=width)
                    )

    return fig





def draw_graph_subplots(graph, pos, node_color=[], node_opacity=[],
                        node_text=[], edge_text=[], marker_symbols=[],
                        color_min=[], color_max=[], title=[], colorbar_title=[],
                        
                        height=720, width=1028,
                        x_range=None, y_range=None, x_margin_percent=6, y_margin_percent=6):

    """ Create a Plotly figure from the NetworkX graph and a dictionary of (x,y) positions.
        Creates using Plotly Scatter graphs, with a "marker"-based node Scatter and a "line"-based edge Scatter.
        Can also include an optional edge-centered marker Scatter for edge hover text.
        
        Inputs: graph -- NetworkX graph to plot.
                pos -- Dictionary of node positions, keyed by node name matching graph node names.

                node_color -- Optional node color. Can be single string, or graph.nodes() ordered list of values for a scale.
                node_text -- Optional hover text for nodes. Can be a single string, or graph.nodes() ordered list of strings.
                edge_text -- Optional hover text for edges. Can be a single string, or graph.edges() ordered list of strings.
                marker_symbols -- Optional marker symbol type. Can be a single valid Plotly marker type, or a graph.nodes() ordered list.
                
                color_min -- Optional minimum value for colored scale. 
                color_max -- Optional maximum value for colored scale.
                colorbar_title -- Optional title for the color bar.
                height -- Height of graph in pixels. Default is 720.
                width -- Width of graph in pixels. Default is 1028.
                x_range -- x range of the printed domain, as (lo, hi) tuple. Default is None (calculated based on pos range).
                y_range -- y range of the printed domain, as (lo, hi) tuple. Default is None (calculated based on pos range).
                x_margin_percent -- Size of the x-direction space margin in percentage of total x_domain.
                y_margin_percent -- Size of the y-direction space margin in percentage of total y_domain.
        
        Outputs: Returns Plotly Figure of graph.
        
        Future Notes: Continue to add inputs and conditionals as other Figure options become flushed out.
    """

    import collections
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
        
    fig = make_subplots(rows=len(graph), cols=1, vertical_spacing=0.06)

    for i in range(len(graph)):

        # Calc color range, if not provided.
        if (color_min == None) or (color_max == None):
            if (color_min == None):
                color_min = min(node_color[i])
            if (color_max == None):
                color_max = max(node_color[i])

        node_x = []
        node_y = []
        for node in graph[i].nodes():
            x, y = pos[i][node]
            node_x.append(x)
            node_y.append(y)
    
        edge_x = []
        edge_y = []
        edge_cx = []
        edge_cy = []
        for edge in graph[i].edges():
            x0, y0 = pos[i][edge[0]]
            x1, y1 = pos[i][edge[1]]
            edge_x.append(x0)
            edge_x.append(x1)
            edge_x.append(None)
            edge_y.append(y0)
            edge_y.append(y1)
            edge_y.append(None)
            edge_cx.append((x0+x1)/2)
            edge_cy.append((y0+y1)/2)
            
        # Ordering of elements is important. Edge first = lowest in the figure.
        fig.add_scatter(
            x=edge_x, y=edge_y,
            line=dict(width=0.5, color='#888'),
            hoverinfo='none',
            mode='lines',
            row=i+1, col=1)

        fig.add_scatter(
            x=node_x, y=node_y,
            mode='markers',
            hoverinfo='text',
            text=node_text[i],
            marker=dict(
                showscale=True,
                # https://plotly.com/python-api-reference/generated/plotly.graph_objects.Scatter.html
                # Search for: "property colorscale"
                colorscale='Rainbow',
                reversescale=True,
                color=node_color[i],
                size=10,
                symbol=marker_symbols[i],
                cmin=color_min,
                cmax=color_max,
                opacity=node_opacity[i],
                colorbar=dict(
                    thickness=15,
                    title=colorbar_title,
                    xanchor='left',
                    titleside='right'
                ),
                line_width=2),
            row=i+1, col=1)

        fig.add_scatter(x=edge_cx, y=edge_cy,
                        mode='markers',
                        hoverinfo='text',
                        text=edge_text[i],
                        marker=dict(
                            opacity=0,
                            color="black",
                            size=5
                            ),
                        line_width=2,
                        row=i+1, col=1)

    fig.update_layout(dict1= dict(title='<br>',
                                  titlefont_size=16,
                                  showlegend=False,
                                  hovermode='closest',
                                  margin=dict(b=20,l=5,r=5,t=20),
                                  annotations=[ dict(
                                    text=title,
                                    showarrow=False,
                                    xref="paper", yref="paper",
                                    x=0.005, y=-0.002 ) ],
                                  xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=x_range),
                                  yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=y_range),
                                  height=height,
                                  width=width),
                      overwrite=False)

    return fig



def graph_difference(graphA, graphB):

    """ Calculate the graph difference, including NetworkX attributes. Any missing edge or node attribute is assumed = 0.
    
        First, deletes all fully equal edges, including attributes.
            Any edges with different attributes remain, with their values being subtracted: (graphA_attr - graphB_attr).
            Any missing attribute (including any entirely missing edge) is assumed to have a value of zero.
        Then, deletes any fully equal nodes, including attributes, that also have degree(0) after edge removal.
            This leaves any nodes needed to contextualize the corresponding edges.

        Attributes across all nodes and edges are consolidated and differenced, so attributes that only appear on some
        nodes/edges will be added to all remaining nodes/edges.

        Inputs: (graphA, graphB) -- NetworkX graphs to difference.
        Outputs: returns resulting graph of (graphA - graphB).
        """

    import networkx as nx
    
    diff_graph = nx.compose(graphA, graphB)

    attrs_n = set([k for n in diff_graph.nodes for k in diff_graph.nodes[n].keys()])
    attrs_e = set([k for n in diff_graph.edges for k in diff_graph.edges[n].keys()])

    remove = []

    for e in diff_graph.edges.data():
        if (graphA.has_edge(e[0], e[1])) and (graphB.has_edge(e[0], e[1])):
            if not (graphA[e[0]][e[1]] == graphB[e[0]][e[1]]):
                for key in attrs_e:
                    diff_graph[e[0]][e[1]][key] = graphA[e[0]][e[1]].get(key,0) - graphB[e[0]][e[1]].get(key, 0)
                    #print("///", diff_graph[e[0]][e[1]][key], graphA[e[0]][e[1]].get(key,0), graphB[e[0]][e[1]].get(key, 0))
            else:
                remove.append((e[0], e[1]))
        elif graphB.has_edge(e[0], e[1]):
            for key in attrs_e:
                diff_graph[e[0]][e[1]][key] = -graphB[e[0]][e[1]].get(key, 0)
        else:
            for key in attrs_e:
                diff_graph[e[0]][e[1]][key] = graphA[e[0]][e[1]].get(key, 0)
            
    diff_graph.remove_edges_from(remove)
    remove.clear()

    for n in diff_graph.nodes.data():
        if (graphA.has_node(n[0]) and graphB.has_node(n[0])):
            if not (graphA.nodes[n[0]] == graphB.nodes[n[0]]):
                for key in attrs_n:
                    diff_graph.nodes[n[0]][key] = graphA.nodes[n[0]].get(key, 0) - graphB.nodes[n[0]].get(key, 0)
                    #print(diff_graph.nodes[n[0]][key])
            elif not (diff_graph.degree(n[0]) == 0):
                # node is identical, but edges remain -- set all attrs to 0 and leave the node
                for key in attrs_n:
                    diff_graph.nodes[n[0]][key] = 0
            else:
                #print(n[0])
                remove.append(n[0])
        elif (graphB.has_node(n[0])):
            for key in attrs_n:
                diff_graph.nodes[n[0]][key] = -graphB.nodes[n[0]].get(key, 0)
        else:
            for key in attrs_n:
                diff_graph.nodes[n[0]][key] = -graphA.nodes[n[0]].get(key, 0)

    diff_graph.remove_nodes_from(remove)
    return diff_graph