#ifndef STREAMING_IO_H
#define STREAMING_IO_H

#include <stddef.h>
#include <stdint.h>

#define ALIGNMENT 4096

typedef struct {
    int fd;
    size_t buf_size;      /* capacity of each buffer */
    void *buffer_a;
    void *buffer_b;
    int current_buf;      /* 0 for A, 1 for B */
    int direct;           /* 1 when O_DIRECT is in force */
    uint64_t bytes_read;  /* cumulative, for measured throughput */
    uint64_t reads;
} StreamingReader;

/* `max_chunk` is the largest range that will ever be requested; both buffers
   are sized to hold it plus alignment slack. */
StreamingReader* streaming_io_init(const char *model_path, size_t max_chunk);

/* Read [offset, offset+size) into the next buffer. Returns a pointer to the
   requested bytes (which may sit inside the buffer, because O_DIRECT forces
   the read to start on an aligned boundary), or NULL on failure. */
void* streaming_io_read_range(StreamingReader *reader, uint64_t offset,
                              size_t size);

/* Ask the kernel to begin fetching a range that will be needed shortly. */
void streaming_io_prefetch(StreamingReader *reader, uint64_t offset, size_t size);

void streaming_io_free(StreamingReader *reader);

#endif // STREAMING_IO_H
