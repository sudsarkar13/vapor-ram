#include "kv_cache.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

KVCache* kv_cache_init(int max_seq_len, int num_layers, int num_heads, int head_dim) {
    KVCache *cache = (KVCache*)malloc(sizeof(KVCache));
    if (!cache) return NULL;

    cache->max_seq_len = max_seq_len;
    cache->num_layers = num_layers;
    cache->num_heads = num_heads;
    cache->head_dim = head_dim;

    size_t total_elements = (size_t)max_seq_len * num_layers * num_heads * head_dim;

    cache->k_cache = (int8_t*)calloc(total_elements, sizeof(int8_t));
    cache->v_cache = (int8_t*)calloc(total_elements, sizeof(int8_t));
    cache->k_scales = (float*)calloc((size_t)max_seq_len * num_layers * num_heads, sizeof(float));
    cache->v_scales = (float*)calloc((size_t)max_seq_len * num_layers * num_heads, sizeof(float));

    if (!cache->k_cache || !cache->v_cache || !cache->k_scales || !cache->v_scales) {
        kv_cache_free(cache);
        return NULL;
    }

    return cache;
}

void kv_cache_store(KVCache *cache, int layer_idx, int pos, const float *k, const float *v) {
    if (!cache || pos >= cache->max_seq_len) return;

    int dim = cache->num_heads * cache->head_dim;
    size_t offset = ((size_t)layer_idx * cache->max_seq_len + pos) * dim;

    // Find max absolute values for int8 scaling
    float max_k = 1e-5f, max_v = 1e-5f;
    for (int i = 0; i < dim; i++) {
        if (fabsf(k[i]) > max_k) max_k = fabsf(k[i]);
        if (fabsf(v[i]) > max_v) max_v = fabsf(v[i]);
    }

    float scale_k = max_k / 127.0f;
    float scale_v = max_v / 127.0f;

    size_t scale_offset = ((size_t)layer_idx * cache->max_seq_len + pos) * cache->num_heads;
    cache->k_scales[scale_offset] = scale_k;
    cache->v_scales[scale_offset] = scale_v;

    // Quantize and store
    for (int i = 0; i < dim; i++) {
        cache->k_cache[offset + i] = (int8_t)roundf(k[i] / scale_k);
        cache->v_cache[offset + i] = (int8_t)roundf(v[i] / scale_v);
    }
}

void kv_cache_free(KVCache *cache) {
    if (!cache) return;
    if (cache->k_cache) free(cache->k_cache);
    if (cache->v_cache) free(cache->v_cache);
    if (cache->k_scales) free(cache->k_scales);
    if (cache->v_scales) free(cache->v_scales);
    free(cache);
}
