#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#if defined(__AVX2__) || defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#endif
#ifdef _OPENMP
#include <omp.h>
#endif

#define DIM 3072
#define ITERATIONS 1000

static double get_wtime(void) {
#ifdef _OPENMP
    return omp_get_wtime();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

// Scalar GEMV
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
    printf(" Vector Dimension: %d floats (Gemma hidden size)\n", DIM);
    printf(" Iterations       : %d runs\n", ITERATIONS);
    int num_threads = 1;
#ifdef _OPENMP
    num_threads = omp_get_max_threads();
#endif
    printf(" OpenMP Threads   : %d\n", num_threads);
    printf("------------------------------------------\n");

    float *a = (float*)aligned_alloc(32, DIM * sizeof(float));
    float *b = (float*)aligned_alloc(32, DIM * sizeof(float));

    for (int i = 0; i < DIM; i++) {
        a[i] = (float)rand() / RAND_MAX;
        b[i] = (float)rand() / RAND_MAX;
    }

    // Benchmark Scalar
    double start_scalar = get_wtime();
    for (int iter = 0; iter < ITERATIONS; iter++) {
        scalar_dot(a, b, DIM);
    }
    double time_scalar = get_wtime() - start_scalar;

    // Benchmark AVX2
    double start_avx2 = get_wtime();
    for (int iter = 0; iter < ITERATIONS; iter++) {
        avx2_dot(a, b, DIM);
    }
    double time_avx2 = get_wtime() - start_avx2;

    double gflops_scalar = (2.0 * DIM * ITERATIONS) / (time_scalar * 1e9);
    double gflops_avx2 = (2.0 * DIM * ITERATIONS) / (time_avx2 * 1e9);

    printf(" Scalar Time : %.4f s (%.2f GFLOPS)\n", time_scalar, gflops_scalar);
    printf(" AVX2 Time   : %.4f s (%.2f GFLOPS)\n", time_avx2, gflops_avx2);
    printf(" Speedup     : \033[1;32m%.2fx faster\033[0m with AVX2 SIMD\n", time_scalar / time_avx2);

    free(a);
    free(b);
    return 0;
}
