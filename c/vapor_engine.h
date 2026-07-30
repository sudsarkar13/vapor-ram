#ifndef VAPOR_ENGINE_H
#define VAPOR_ENGINE_H

#include <stddef.h>
#include <stdint.h>
#include "streaming_io.h"
#include "kv_cache.h"

#define VAPOR_MODEL_NAME "google/gemma-4-E4B-it"
#define VAPOR_LAYERS 32
#define VAPOR_HIDDEN_DIM 3072
#define VAPOR_LAYER_BYTES (140 * 1024 * 1024)

typedef struct {
    StreamingReader *streamer;
    KVCache *kv_cache;
    float *hidden_states;
    int current_pos;
} VaporContext;

VaporContext* vapor_init(const char *model_path);
int vapor_step(VaporContext *ctx, const char *prompt, char *output_buf, size_t buf_size);
void vapor_free(VaporContext *ctx);

#endif // VAPOR_ENGINE_H
