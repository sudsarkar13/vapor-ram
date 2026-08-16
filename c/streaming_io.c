/* Sequential range reader for GGUF weights.
 *
 * The previous implementation read at a fixed `layer_idx * layer_size` stride
 * from byte 0, which corresponds to nothing in a real GGUF container: in
 * gemma-4-E4B-it-Q4_K_M the first transformer block starts 2.37 GB into the
 * file, after the token-embedding tables, and each block spans ~61 MB rather
 * than the assumed 140 MB. It was reading embeddings and metadata and
 * reporting them as layers.
 *
 * Ranges now come from the caller, which resolves them from the GGUF tensor
 * directory, so what is read is what is actually there.
 */
#include "streaming_io.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <dirent.h>
#include <sys/types.h>
#include <sys/stat.h>

static int resolve_target(const char *model_path, char *out, size_t out_len) {
    struct stat st;
    if (stat(model_path, &st) == 0 && S_ISDIR(st.st_mode)) {
        DIR *dir = opendir(model_path);
        if (dir) {
            struct dirent *entry;
            while ((entry = readdir(dir)) != NULL) {
                if (strstr(entry->d_name, ".gguf") != NULL) {
                    snprintf(out, out_len, "%s/%s", model_path, entry->d_name);
                    closedir(dir);
                    return 1;
                }
            }
            closedir(dir);
        }
        return 0;
    }
    snprintf(out, out_len, "%s", model_path);
    return 1;
}

StreamingReader* streaming_io_init(const char *model_path, size_t max_chunk) {
    if (max_chunk == 0) return NULL;

    StreamingReader *reader = (StreamingReader*)calloc(1, sizeof(StreamingReader));
    if (!reader) return NULL;

    char target[1024];
    if (!resolve_target(model_path, target, sizeof(target))) {
        free(reader);
        return NULL;
    }

    /* O_DIRECT bypasses the page cache, which is the point: it measures the
       device rather than what Linux happens to have cached. Not every
       filesystem supports it, so fall back rather than fail. */
    reader->direct = 1;
#ifdef O_DIRECT
    reader->fd = open(target, O_RDONLY | O_DIRECT);
    if (reader->fd < 0) {
        reader->direct = 0;
        reader->fd = open(target, O_RDONLY);
    }
#else
    reader->direct = 0;
    reader->fd = open(target, O_RDONLY);
#endif
    if (reader->fd < 0) {
        free(reader);
        return NULL;
    }

    /* O_DIRECT rejects unaligned reads, so the magic check needs an aligned
       buffer and a full-block read -- a bare 4-byte pread fails with EINVAL
       and would report every valid GGUF as headerless. */
    void *probe = NULL;
    if (posix_memalign(&probe, ALIGNMENT, ALIGNMENT) == 0) {
        ssize_t got = pread(reader->fd, probe, ALIGNMENT, 0);
        if (got < 4 || memcmp(probe, "GGUF", 4) != 0) {
            /* Not fatal: the caller may be streaming a raw weight blob. */
            fprintf(stderr, "[streaming_io] warning: %s has no GGUF magic header\n",
                    target);
        }
        free(probe);
    }

#ifdef POSIX_FADV_SEQUENTIAL
    posix_fadvise(reader->fd, 0, 0, POSIX_FADV_SEQUENTIAL);
#endif

    /* Room for the request plus the slack an aligned read needs at both ends. */
    reader->buf_size = max_chunk + 2 * ALIGNMENT;
    if (posix_memalign(&reader->buffer_a, ALIGNMENT, reader->buf_size) != 0 ||
        posix_memalign(&reader->buffer_b, ALIGNMENT, reader->buf_size) != 0) {
        close(reader->fd);
        free(reader->buffer_a);
        free(reader);
        return NULL;
    }
    return reader;
}

void streaming_io_prefetch(StreamingReader *reader, uint64_t offset, size_t size) {
#ifdef POSIX_FADV_WILLNEED
    if (reader && reader->fd >= 0)
        posix_fadvise(reader->fd, (off_t)offset, (off_t)size, POSIX_FADV_WILLNEED);
#else
    (void)reader; (void)offset; (void)size;
#endif
}

void* streaming_io_read_range(StreamingReader *reader, uint64_t offset, size_t size) {
    if (!reader || reader->fd < 0 || size == 0 || size > reader->buf_size)
        return NULL;

    void *buf = (reader->current_buf == 0) ? reader->buffer_a : reader->buffer_b;

    /* O_DIRECT requires the file offset, the buffer and the length to be
       aligned. Tensor offsets are not, so widen the read to the enclosing
       aligned window and hand back a pointer to the requested bytes inside it. */
    uint64_t aligned_off = offset & ~((uint64_t)ALIGNMENT - 1);
    size_t lead = (size_t)(offset - aligned_off);
    size_t span = lead + size;
    size_t aligned_span = (span + ALIGNMENT - 1) & ~((size_t)ALIGNMENT - 1);
    if (aligned_span > reader->buf_size) return NULL;

    size_t done = 0;
    while (done < aligned_span) {
        ssize_t n = pread(reader->fd, (char*)buf + done,
                          aligned_span - done, (off_t)(aligned_off + done));
        if (n <= 0) {
            /* A short final read at end-of-file is expected; anything else is
               a real failure and must not be reported as a successful read. */
            if (n == 0 && done >= span) break;
            if (n == 0) break;
            return NULL;
        }
        done += (size_t)n;
    }
    if (done < span) return NULL;

    reader->bytes_read += size;
    reader->reads += 1;
    reader->current_buf = 1 - reader->current_buf;
    return (char*)buf + lead;
}

void streaming_io_free(StreamingReader *reader) {
    if (!reader) return;
    if (reader->fd >= 0) close(reader->fd);
    free(reader->buffer_a);
    free(reader->buffer_b);
    free(reader);
}
