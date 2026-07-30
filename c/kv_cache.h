#ifndef KV_CACHE_H
#define KV_CACHE_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int max_seq_len;
    int num_layers;
    int num_heads;
    int head_dim;
    int8_t *k_cache; // Quantized int8 K cache
    int8_t *v_cache; // Quantized int8 V cache
    float *k_scales; // Scale factors per token
    float *v_scales; // Scale factors per token
} KVCache;

KVCache* kv_cache_init(int max_seq_len, int num_layers, int num_heads, int head_dim);
void kv_cache_store(KVCache *cache, int layer_idx, int pos, const float *k, const float *v);
void kv_cache_free(KVCache *cache);

#endif // KV_CACHE_H
