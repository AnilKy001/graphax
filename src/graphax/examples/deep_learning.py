import jax
import jax.nn as jnn
import jax.numpy as jnp


def sigmoid(x):
    return 1. / (1. + jnp.exp(-x))


def SiLU(x):
    return x*sigmoid(x)


def variance(x, axis=0):
    mu = jnp.mean(x, axis=axis)
    n = x.shape[axis]
    return jnp.sum((x - mu)**2, axis=axis)/n


def layer_norm(x, gamma, beta):
    mu = jnp.mean(x, axis=1)
    sigma = variance(x, axis=1)
    return (x - mu)/jnp.sqrt(sigma + 1e-6) * gamma + beta


def attn(q, k, v):
    a = q.T @ k
    z = jnn.softmax(a, axis=1)
    return z @ v


def Perceptron(x, y, W1, b1, W2, b2, gamma, beta):
    y1 = W1 @ x
    z1 = y1 + b1
    a1 = jnp.tanh(z1)
    
    a1 = layer_norm(a1, gamma, beta)
    
    y2 = W2 @ a1
    z2 = y2 + b2
    a2 = jnp.tanh(z2)
    d = a2 - y
    e = d**2
    return .5*jnp.sum(e)


def encoder_block(x, WQ, WK, WV, W, b, gamma, beta):
    q1 = WQ @ x
    k1 = WK @ x
    v1 = WV @ x
    
    a1 = x + attn(q1, k1, v1)
    c1 = layer_norm(a1, gamma, beta)
    return SiLU(W @ c1 + b)


def decoder_block(x, q, k, WQ1, WK1, WV1, WQ2, WK2, WV2, W, b, gamma, beta):
    q1 = WQ1 @ x
    k1 = WK1 @ x
    v1 = WV1 @ x
    
    a1 = x + attn(q1, k1, v1)
    c1 = layer_norm(a1, gamma[0], beta[0])
    
    q2 = WQ2 @ q
    k2 = WK2 @ k
    v2 = WV2 @ c1
    
    a2 = c1 + attn(q2, k2, v2)
    c2= layer_norm(a2, gamma[1], beta[1])
    return SiLU(W @ c2 + b)
    

def Encoder(x, y, WQ1, WQ2, WK1, WK2, WV1, WV2, W1, W2, b1, b2, gamma, beta):
    z1 = encoder_block(x, WQ1, WK1, WV1, W1, b1, gamma[0], beta[0])
    z2 = encoder_block(z1, WQ2, WK2, WV2, W2, b2, gamma[1], beta[1])
    return .5*(z2 - y)**2
    

def EncoderDecoder(x, y, WQ1, WQ2, WQ3, WK1, WK2, WK3, WV1, WV2, WV3,  W1, W2, b1, b2, gamma, beta):
    z1 = encoder_block(x, WQ1, WK1, WV1, W1, b1, gamma[0], beta[0])
    z2 = decoder_block(x, z1, z1, WQ2, WQ3, WK2, WK3, WV2, WV3, W2, b2, gamma[1:], beta[1:])
    
    return .5*(z2 - y)**2

