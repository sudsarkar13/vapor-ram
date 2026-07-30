#ifndef STREAMING_IO_H
#define STREAMING_IO_H

#include <stddef.h>
#include <stdint.h>

#define ALIGNMENT 4096

typedef struct {
    int fd;
    size_t layer_size;
    void *buffer_a;
    void *buffer_b;
    int current_buf; // 0 for A, 1 for B
} StreamingReader;

StreamingReader* streaming_io_init(const char *model_path, size_t layer_size);
void* streaming_io_load_layer(StreamingReader *reader, int layer_idx);
void streaming_io_free(StreamingReader *reader);

#endif // STREAMING_IO_H
