""" 
Edge and vertex elimination functions for Cross-Country elimination 
that are totally jit-compilable. For an in-depth discussion of Cross-Country 
Elimination and the methods described here see the book 
`Evaluating Derivatives` by Griewank et al., 2008,
https://doi.org/10.1137/1.9780898717761
"""
from typing import NamedTuple, Tuple

import jax
import jax.lax as lax
import jax.numpy as jnp

import chex


class GraphInfo(NamedTuple):
    """
    Meta-information about the computational graph
    """
    num_inputs: int
    num_intermediates: int
    num_outputs: int
    num_edges: int


def make_empty_edges(info: GraphInfo) -> chex.Array:
    num_i = info.num_inputs
    num_v = info.num_intermediates
    num_o = info.num_outputs
    return jnp.zeros((num_i+num_v, num_v+num_o))


def make_graph_info(info: chex.Array) -> GraphInfo:
    num_i = info[0]
    num_v = info[1]
    num_o = info[2]
    num_edges = (num_i+num_v)*(num_v+num_o) - num_v*(num_v-1)//2
    num_edges = int(.5*num_edges)
    return GraphInfo(num_inputs=info[0],
                    num_intermediates=info[1],
                    num_outputs=info[2],
                    num_edges=num_edges)


def add_edge(edges: chex.Array, 
            pos: Tuple[int, int], 
            info: GraphInfo) -> Tuple[chex.Array, GraphInfo]:
    """TODO refine documentation
    Jittable function to add a new edge to a GraphState object, i.e. a new
    entry to the `edges` matrix.

    Input vertices range from `-num_inputs+1` to 0, while the last `num_output` 
    vertices are the output vertices.

    Arguments:
        - edges (GraphState): GraphState object where we want to add the edge.
        - pos (Tuple[int, int]): Tuple that describes which two vertices are 
                                connected, i.e. pos = (from, to).
        - info (Array): Contains meta data about the computational graph.
    """
    num_inputs = info.num_inputs
    return edges.at[pos[0]+num_inputs-1, pos[1]-1].set(1)


def front_eliminate(edges: chex.Array, 
                    edge: Tuple[int, int],
                    info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements the front-elimination procedure
    on the edges of a GraphState object.

    Arguments:
        - edges (chex.Array): Edges contained in a GraphState object that 
                                describes the computational graph where we want 
                                to front-eliminate the given edge.
        - edge (Tuple[int, int]): Tuple of integers describing the edge we want
                                to eliminate.
        - info (chex.Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_inputs = info.num_inputs
    num_edges = info.num_edges
    
    e0 = edge[0] + num_inputs - 1
    e1 = edge[1] - 1
    
    edge_val = edges[e0, e1]
    edges = edges.at[e0, e1].set(0.)

    def front_update_edge(carry, nonzeros):
        _edges, nops = carry
        i = nonzeros[0] - num_inputs + 1
        j = nonzeros[1] + 1
        val = edges.at[nonzeros[0], nonzeros[1]].get()
        _edges, ops = lax.cond(i == edge[1], 
                            lambda x, m, n, val: (x.at[m, n].set(val), 1), 
                            lambda x, m, n, val: (x, 0), 
                            _edges, e0, nonzeros[1], val*edge_val)
        nops += ops
        carry = (_edges, nops)
        return carry, None
    nonzeros = jnp.stack(jnp.nonzero(edges, 
                                    size=num_edges,
                                    fill_value=-num_edges)).T
    output, _ = lax.scan(front_update_edge, (edges, 0), nonzeros)
    return output
 

def back_eliminate(edges: chex.Array, 
                   edge: Tuple[int, int],
                   info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements the back-elimination procedure
    on the edges of a GraphState object.

    Arguments:
        - edges (chex.Array): Edges contained in a GraphState object that 
                                describes the computational graph where we want 
                                to front-eliminate the given edge.
        - edge (Tuple[int, int]): Tuple of integers describing the edge we want
                                to eliminate.
        - info (chex.Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_inputs = info.num_inputs
    num_edges = info.num_edges
    
    e0 = edge[0] + num_inputs - 1
    e1 = edge[1] - 1
    
    edge_val = edges[e0, e1]
    edges = edges.at[e0, e1].set(0.)

    def back_update_edge(carry, nonzeros):
        _edges, nops = carry
        i = nonzeros[0] - num_inputs + 1
        j = nonzeros[1] + 1
        val = edges.at[nonzeros[0], nonzeros[1]].get()
        _edges, ops = lax.cond(j == edge[0], 
                            lambda x, m, n, val: (x.at[m, n].set(val), 1), 
                            lambda x, m, n, val: (x, 0), 
                            _edges, nonzeros[0], e1, val*edge_val)
        nops += ops
        carry = (_edges, nops)
        return carry, None
    
    nonzeros = jnp.stack(jnp.nonzero(edges, 
                                    size=num_edges, 
                                    fill_value=-num_edges)).T
    output, _ = lax.scan(back_update_edge, (edges, 0), nonzeros)
    return output


def vertex_eliminate(edges: chex.Array, 
                    vertex: int, 
                    info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements the vertex-elimination procedure
    on a GraphState object. Vertex elimination means that we front-eliminate
    all incoming edges and back-eliminate all outgoing edges of a given vertex.

    Arguments:
        - gs_edges (GraphState): GraphState that describes the computational graph 
                            where we want to front-eliminate the given edge.
        - vertex (int): Vertex we want to eliminate.
        - info (Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_inputs = info.num_inputs
    num_edges = info.num_edges
    
    def update_edges(carry, nonzeros):
        _edges, nops = carry
        i = nonzeros[0] - num_inputs + 1
        j = nonzeros[1] + 1
                        
        _edges, fops = lax.cond(j == vertex,
                                lambda x, m, n: front_eliminate(x, (m, n), info), 
                                lambda x, m, n: (x, 0), 
                                _edges, i, j)

        _edges, bops = lax.cond(i == vertex, 
                                lambda x, m, n: back_eliminate(x, (m, n), info), 
                                lambda x, m, n: (x, 0), 
                                _edges, i, j)
        
        nops += (fops + bops)
        carry = (_edges, nops)
        return carry, None
        
    nonzeros = jnp.stack(jnp.nonzero(edges, 
                                    size=num_edges, 
                                    fill_value=-num_edges)).T
    output, _ = lax.scan(update_edges, (edges, 0), nonzeros)
    return output


def vertex_eliminate_gpu(edges: chex.Array, 
                        vertex: int, 
                        info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements the vertex-elimination procedure
    on a GraphState object. Vertex elimination means that we front-eliminate
    all incoming edges and back-eliminate all outgoing edges of a given vertex.

    Arguments:
        - gs_edges (GraphState): GraphState that describes the computational graph 
                            where we want to front-eliminate the given edge.
        - vertex (int): Vertex we want to eliminate.
        - info (Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_inputs = info.num_inputs
    num_edges = info.num_edges
    num_intermediates = info.num_intermediates
    num_outputs = info.num_outputs

    col = edges.at[:, vertex-1].get()
    ops = col.sum()
    
    def update_edges(carry, nonzero):
        _edges, nops = carry

        _edges = _edges.at[:, nonzero].add(col, mode="drop")     
        
        nops = lax.cond(nonzero > -1, lambda x: x+ops, lambda x: x, nops)
        carry = (_edges, nops)
        return carry, None
        
    nonzeros = jnp.nonzero(edges.at[num_inputs+vertex-1, :].get(), 
                                    size=num_intermediates+num_outputs, 
                                    fill_value=-num_edges)[0]
    output, _ = lax.scan(update_edges, (edges, 0.), nonzeros)
    edges, nops = output
    edges = edges.at[num_inputs+vertex-1, :].set(0)
    edges = edges.at[:, vertex-1].set(0)
    # this is very costly!
    edges = jnp.bool_(edges).astype(jnp.float32)
    return edges, nops


def forward(edges: chex.Array, info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements forward-mode AD by 
    eliminating the vertices in sequential order 1,2,3,...,n-1,n.

    Arguments:
        - gs (GraphState): GraphState that describes the computational graph 
                            where we want to differntiate.
        - info (Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_intermediates = info.num_intermediates
    
    def fwd(carry, vertex):
        _edges, nops = carry
        _edges, ops = vertex_eliminate(_edges, vertex, info)
        nops += ops
        carry = (_edges, nops)
        return carry, None
    vertices = jnp.arange(1, num_intermediates+1)
    output, _ = lax.scan(fwd, (edges, 0.), vertices)
    return output


def forward_gpu(edges: chex.Array, info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements forward-mode AD by 
    eliminating the vertices in sequential order 1,2,3,...,n-1,n.

    Arguments:
        - gs (GraphState): GraphState that describes the computational graph 
                            where we want to differntiate.
        - info (Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_intermediates = info.num_intermediates
    
    def fwd(carry, vertex):
        _edges, nops = carry
        _edges, ops = vertex_eliminate_gpu(_edges, vertex, info)
        nops += ops
        carry = (_edges, nops)
        return carry, None
    vertices = jnp.arange(1, num_intermediates+1)
    output, _ = lax.scan(fwd, (edges, 0.), vertices)
    return output


def reverse(edges: chex.Array, info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements reverse-mode AD by 
    eliminating the vertices in sequential order n,n-1,...,2,1.

    Arguments:
        - gs (GraphState): GraphState that describes the computational graph 
                            where we want to differntiate.
        - info (Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_intermediates = info.num_intermediates
    
    def rev(carry, vertex):
        _edges, nops = carry
        _edges, ops = vertex_eliminate(_edges, vertex, info)
        nops += ops
        carry = (_edges, nops)
        return carry, None
    vertices = jnp.arange(1, num_intermediates+1)[::-1]
    output, _ = lax.scan(rev, (edges, 0.), vertices)
    return output


def reverse_gpu(edges: chex.Array, info: GraphInfo) -> Tuple[chex.Array, int]:
    """TODO fix docstring
    Fully jit-compilable function that implements reverse-mode AD by 
    eliminating the vertices in sequential order n,n-1,...,2,1.

    Arguments:
        - gs (GraphState): GraphState that describes the computational graph 
                            where we want to differntiate.
        - info (Array): Meta-information about the computational graph.

    Returns:
        A tuple that contains a new GraphState object with updated edges and 
        an integer containing the number of multiplications necessary to 
        eliminate the given edge. 
    """
    num_intermediates = info.num_intermediates
    
    def rev(carry, vertex):
        _edges, nops = carry
        _edges, ops = vertex_eliminate_gpu(_edges, vertex, info)
        nops += ops
        carry = (_edges, nops)
        return carry, None
    vertices = jnp.arange(1, num_intermediates+1)[::-1]
    output, _ = lax.scan(rev, (edges, 0.), vertices)
    return output


def scan(f, init, xs, length=None):
    if xs is None:
        xs = [None] * length
    carry = init
    ys = []
    for x in xs:
        carry, y = f(carry, x)
        ys.append(y)
    return carry, jnp.stack(ys)


# TODO introduce "safe preeliminations" to reduce problem complexity!
def safe_pre_eliminations_gpu(edges: chex.Array, info: GraphInfo) -> Tuple[chex.Array, int]:
    """
    Function that runs a safe-preelimination routing that eliminates all vertices
    with only one input and one output.
    WARNING: This changes the shape of the edges array and the number of intermediate variables!
    """
    num_intermediates = info.num_intermediates
    num_inputs = info.num_inputs
    
    def update_edges(carry, vertex):
        _edges = carry
        row_flag = jnp.sum(_edges[vertex+num_inputs, :]) == 1
        col_flag = jnp.sum(_edges[:, vertex]) == 1
        
        _edges, idx = lax.cond(jnp.logical_and(row_flag, col_flag),
                            lambda x: (vertex_eliminate_gpu(x, vertex+1, info)[0], vertex+1), 
                            lambda x: (x, 0), 
                            _edges)
        
        carry = _edges
        return carry, idx
    
    vertices = jnp.arange(0, num_intermediates)
    output, idxs = lax.scan(update_edges, edges, vertices)
    idxs = jnp.trim_zeros(idxs)
    for idx in idxs[::-1]:
        output = jnp.delete(output, idx-1+num_inputs, axis=0)
        output = jnp.delete(output, idx-1, axis=1)
    new_info = make_graph_info([info.num_inputs, output.shape[0]-info.num_inputs, info.num_outputs])
    return output, new_info, len(idxs)

