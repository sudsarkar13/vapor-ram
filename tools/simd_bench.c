#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#if defined(__AVX2__) || defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#endif
#ifdef _OPENMP
#include <omp.h>
#endif

/* gemma-4-E4B-it's real hidden size, read from the GGUF metadata key
 * gemma4.embedding_length. This said 3072 and called it "Gemma hidden size";
 * it is 2560 for this model. */
#define DIM 2560
/* Enough work that the timer resolution is not the thing being measured.
 * At 1000 iterations both loops finished in under a millisecond and the
 * derived figure was ~200,000 GFLOPS -- about a thousand times this class of
 * CPU's real peak, because the results were unused and the compiler deleted
 * the loops outright. */
#define ITERATIONS 200000

/* Forces the compiler to re-read a[] and b[] on every iteration.
 *
 * Both dot products are pure functions of unchanging arguments, so GCC hoists
 * the call out of the timing loop and multiplies the single result -- the
 * scalar case then "ran" 200,000 iterations in 0.0003 s and reported 3045
 * GFLOPS, which is not a number this CPU can produce. The memory clobber makes
 * the compiler assume the inputs may have changed and issue a real call. */
#define COMPILER_BARRIER() __asm__ __volatile__("" ::: "memory")

static double get_wtime(void) {
#ifdef _OPENMP
    return omp_get_wtime();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

/* Scalar GEMV.
 *
 * The no-vectorize attribute is load-bearing. This file is compiled -O3
 * -mavx2 -mfma, so without it the compiler auto-vectorises this loop into the
 * very instructions the "AVX2" case uses by hand -- the benchmark then
 * compares AVX2 against AVX2 and reported the hand-written kernel as *slower*
 * (0.83x), since it also pays for a horizontal reduction per call.
 * Pinning the baseline to genuinely scalar code makes the comparison mean something. */
#if defined(__GNUC__) && !defined(__clang__)
__attribute__((optimize("no-tree-vectorize")))
#endif
float scalar_dot(const float *a, const float *b, int size) {
    float sum = 0.0f;
    for (int i = 0; i < size; i++) {
        sum += a[i] * b[i];
    }
    return sum;
}

// AVX2 GEMV
float avx2_dot(const float *a, const float *b, int size) {
#if defined(__AVX2__)
    __m256 sum = _mm256_setzero_ps();
    int i = 0;
    for (; i <= size - 8; i += 8) {
        __m256 va = _mm256_loadu_ps(&a[i]);
        __m256 vb = _mm256_loadu_ps(&b[i]);
        sum = _mm256_fmadd_ps(va, vb, sum);
    }
    float buffer[8];
    _mm256_storeu_ps(buffer, sum);
    float total = buffer[0] + buffer[1] + buffer[2] + buffer[3] +
                  buffer[4] + buffer[5] + buffer[6] + buffer[7];
    for (; i < size; i++) {
        total += a[i] * b[i];
    }
    return total;
#else
    return scalar_dot(a, b, size);
#endif
}

int main() {
    printf("=== VaporRAM AVX2 SIMD Core Benchmark ===\n");
    printf(" Vector Dimension: %d floats (gemma-4-E4B-it hidden size)\n", DIM);
    printf(" Iterations       : %d runs\n", ITERATIONS);
    /* Both kernels are single-threaded: there is no `#pragma omp` anywhere in
     * this file. The header used to print omp_get_max_threads() here, which
     * read as "this benchmark used 16 threads" when it used one. */
    printf(" Threads          : 1 (both kernels are single-threaded)\n");
    printf("------------------------------------------\n");

    float *a = (float*)aligned_alloc(32, DIM * sizeof(float));
    float *b = (float*)aligned_alloc(32, DIM * sizeof(float));

    for (int i = 0; i < DIM; i++) {
        a[i] = (float)rand() / RAND_MAX;
        b[i] = (float)rand() / RAND_MAX;
    }

    /* `sink` is volatile so the accumulated result is observable and the
     * optimiser cannot discard the calls. Without it -O3 removes both loops
     * and the benchmark reports the speed of doing nothing. */
    volatile float sink = 0.0f;
    float acc;

    /* Warm the caches so the first loop measured is not also the one paying
     * for the first touch of a[] and b[]. */
    acc = 0.0f;
    for (int iter = 0; iter < 1000; iter++) {
        COMPILER_BARRIER();
        acc += scalar_dot(a, b, DIM);
    }
    sink = acc;

    // Benchmark Scalar
    acc = 0.0f;
    double start_scalar = get_wtime();
    for (int iter = 0; iter < ITERATIONS; iter++) {
        COMPILER_BARRIER();
        acc += scalar_dot(a, b, DIM);
    }
    COMPILER_BARRIER();
    double time_scalar = get_wtime() - start_scalar;
    sink = acc;

    // Benchmark AVX2
    acc = 0.0f;
    double start_avx2 = get_wtime();
    for (int iter = 0; iter < ITERATIONS; iter++) {
        COMPILER_BARRIER();
        acc += avx2_dot(a, b, DIM);
    }
    COMPILER_BARRIER();
    double time_avx2 = get_wtime() - start_avx2;
    sink = acc;
    (void)sink;

    double gflops_scalar = (2.0 * DIM * ITERATIONS) / (time_scalar * 1e9);
    double gflops_avx2 = (2.0 * DIM * ITERATIONS) / (time_avx2 * 1e9);

    printf(" Scalar Time : %.4f s (%.2f GFLOPS)\n", time_scalar, gflops_scalar);
    printf(" AVX2 Time   : %.4f s (%.2f GFLOPS)\n", time_avx2, gflops_avx2);
    printf(" Speedup     : \033[1;32m%.2fx faster\033[0m with AVX2 SIMD\n", time_scalar / time_avx2);
    printf("------------------------------------------\n");
    printf(" This measures this CPU's dot-product throughput only.\n");
    printf(" Token generation runs on llama.cpp and does not use this kernel.\n");

    free(a);
    free(b);
    return 0;
}
