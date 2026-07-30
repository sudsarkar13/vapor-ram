#include "streaming_io.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>

StreamingReader* streaming_io_init(const char *model_path, size_t layer_size) {
    StreamingReader *reader = (StreamingReader*)malloc(sizeof(StreamingReader));
    if (!reader) return NULL;

    reader->layer_size = layer_size;
    reader->current_buf = 0;

    // Use O_DIRECT if available for bypassing OS page cache, fall back to O_RDONLY
    #ifdef O_DIRECT
    reader->fd = open(model_path, O_RDONLY | O_DIRECT);
    if (reader->fd < 0) {
        reader->fd = open(model_path, O_RDONLY);
    }
    #else
    reader->fd = open(model_path, O_RDONLY);
    #endif

    if (reader->fd < 0) {
        perror("Failed to open model file for streaming");
        free(reader);
        return NULL;
    }

    // Hint Linux kernel for sequential NVMe reading
    #ifdef POSIX_FADV_SEQUENTIAL
    posix_fadvise(reader->fd, 0, 0, POSIX_FADV_SEQUENTIAL);
    #endif

    // Allocate 4096-byte aligned double buffers
    if (posix_memalign(&reader->buffer_a, ALIGNMENT, layer_size) != 0 ||
        posix_memalign(&reader->buffer_b, ALIGNMENT, layer_size) != 0) {
        perror("Failed aligned memory allocation for streaming buffers");
        close(reader->fd);
        free(reader);
        return NULL;
    }

    return reader;
}

void* streaming_io_load_layer(StreamingReader *reader, int layer_idx) {
    if (!reader || reader->fd < 0) return NULL;

    void *target_buf = (reader->current_buf == 0) ? reader->buffer_a : reader->buffer_b;
    off_t offset = (off_t)layer_idx * reader->layer_size;

    // Hint Linux kernel to prefetch next layer from NVMe storage into kernel buffer
    #ifdef POSIX_FADV_WILLNEED
    posix_fadvise(reader->fd, offset + reader->layer_size, reader->layer_size, POSIX_FADV_WILLNEED);
    #endif

    ssize_t bytes_read = pread(reader->fd, target_buf, reader->layer_size, offset);
    if (bytes_read < 0) {
        perror("Error reading layer from disk");
        return NULL;
    }

    // Toggle active buffer
    reader->current_buf = 1 - reader->current_buf;
    return target_buf;
}

void streaming_io_free(StreamingReader *reader) {
    if (!reader) return;
    if (reader->fd >= 0) close(reader->fd);
    if (reader->buffer_a) free(reader->buffer_a);
    if (reader->buffer_b) free(reader->buffer_b);
    free(reader);
}
