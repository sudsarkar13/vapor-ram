/* VaporRAM streaming inspector.
 *
 * What this is: a measurement tool. It streams the real byte ranges of a
 * GGUF's transformer blocks through the O_DIRECT reader and reports what the
 * device actually delivered.
 *
 * What this is not: the token path. Generation runs through llama.cpp.
 * The previous version of this file claimed otherwise -- it looped over a
 * hardcoded 32 layers (the model has 42), ran `avx2_vec_dot(x, x, 8) * 0.001f`
 * on a zeroed buffer, and printed a fixed sentence as if it were model output.
 * None of that computed anything. Layer ranges now come from the caller, which
 * resolves them from the GGUF tensor directory.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdint.h>
#include "streaming_io.h"

#define VAPOR_VERSION "1.0.7-beta.3"
#define MAX_LAYERS 512

typedef struct {
    int index;
    uint64_t offset;
    uint64_t nbytes;
} LayerRange;

static double now_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

/* Plan file: one "index offset nbytes" triple per line, produced from the
   GGUF tensor directory. Comments and blank lines are ignored. */
static int read_plan(const char *path, LayerRange *out, int max_items) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char line[256];
    int n = 0;
    while (n < max_items && fgets(line, sizeof(line), f)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        LayerRange r;
        if (sscanf(line, "%d %llu %llu", &r.index,
                   (unsigned long long*)&r.offset,
                   (unsigned long long*)&r.nbytes) == 3) {
            out[n++] = r;
        }
    }
    fclose(f);
    return n;
}

static void usage(const char *argv0) {
    fprintf(stderr, "VaporRAM streaming inspector v" VAPOR_VERSION "\n");
    fprintf(stderr, "Usage: %s <model.gguf> <plan-file>\n", argv0);
    fprintf(stderr, "  plan-file: lines of \"<layer_index> <byte_offset> <byte_length>\"\n");
    fprintf(stderr, "Emits one JSON object per line with measured read timings.\n");
}

int main(int argc, char **argv) {
    if (argc < 3) {
        usage(argv[0]);
        return 1;
    }

    const char *model_path = argv[1];
    const char *plan_path = argv[2];

    LayerRange plan[MAX_LAYERS];
    int n_layers = read_plan(plan_path, plan, MAX_LAYERS);
    if (n_layers <= 0) {
        fprintf(stderr, "[Error] Could not read a usable plan from %s\n", plan_path);
        return 1;
    }

    uint64_t max_chunk = 0;
    for (int i = 0; i < n_layers; i++)
        if (plan[i].nbytes > max_chunk) max_chunk = plan[i].nbytes;

    StreamingReader *streamer = streaming_io_init(model_path, (size_t)max_chunk);
    if (!streamer) {
        fprintf(stderr, "[Error] Failed to open %s for streaming\n", model_path);
        return 1;
    }

    printf("{\"event\":\"start\",\"version\":\"" VAPOR_VERSION "\",\"layers\":%d,"
           "\"o_direct\":%s,\"max_chunk_bytes\":%llu}\n",
           n_layers, streamer->direct ? "true" : "false",
           (unsigned long long)max_chunk);
    fflush(stdout);

    double run_start = now_seconds();
    uint64_t total_bytes = 0;
    int failures = 0;

    for (int i = 0; i < n_layers; i++) {
        /* Tell the kernel about the next range while this one is in flight. */
        if (i + 1 < n_layers)
            streaming_io_prefetch(streamer, plan[i + 1].offset, (size_t)plan[i + 1].nbytes);

        double t0 = now_seconds();
        void *data = streaming_io_read_range(streamer, plan[i].offset,
                                             (size_t)plan[i].nbytes);
        double elapsed = now_seconds() - t0;

        if (!data) {
            failures++;
            printf("{\"event\":\"layer\",\"layer\":%d,\"ok\":false}\n", plan[i].index);
            fflush(stdout);
            continue;
        }

        /* Touch the buffer so the read cannot be optimised away and the pages
           are genuinely resident; also a cheap checksum over the first words. */
        uint64_t checksum = 0;
        const unsigned char *bytes = (const unsigned char*)data;
        size_t step = plan[i].nbytes > 4096 ? plan[i].nbytes / 4096 : 1;
        for (size_t k = 0; k < plan[i].nbytes; k += step)
            checksum += bytes[k];

        total_bytes += plan[i].nbytes;
        double mb = (double)plan[i].nbytes / (1024.0 * 1024.0);
        printf("{\"event\":\"layer\",\"layer\":%d,\"ok\":true,\"bytes\":%llu,"
               "\"ms\":%.3f,\"mb_per_s\":%.2f,\"checksum\":%llu}\n",
               plan[i].index, (unsigned long long)plan[i].nbytes,
               elapsed * 1000.0, elapsed > 0 ? mb / elapsed : 0.0,
               (unsigned long long)checksum);
        fflush(stdout);
    }

    double total = now_seconds() - run_start;
    double total_mb = (double)total_bytes / (1024.0 * 1024.0);
    printf("{\"event\":\"done\",\"layers_read\":%d,\"failures\":%d,"
           "\"total_bytes\":%llu,\"total_ms\":%.3f,\"mb_per_s\":%.2f,"
           "\"peak_buffer_bytes\":%llu}\n",
           n_layers - failures, failures, (unsigned long long)total_bytes,
           total * 1000.0, total > 0 ? total_mb / total : 0.0,
           (unsigned long long)(streamer->buf_size * 2));
    fflush(stdout);

    streaming_io_free(streamer);
    return failures ? 2 : 0;
}
