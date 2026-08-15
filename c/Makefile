# VaporRAM C engine build.
#
# Flags are selected per architecture and toolchain. The previous rules
# hard-coded -mavx2 -mfma -fopenmp, which Apple clang rejects outright on
# arm64 ("unsupported option"), so the engine could not be built on the
# Apple Silicon Macs the project claims to support.
#
# The sources already guard their SIMD and OpenMP use with
# #if defined(__AVX2__) and #ifdef _OPENMP, so omitting a flag degrades
# to the portable scalar/single-threaded path rather than failing.

CC ?= cc

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)

CFLAGS = -O3 -Wall -Wextra -std=c11
LDFLAGS = -lm

# --- Vector ISA -------------------------------------------------------------
# x86_64 gets AVX2 + FMA. ARMv8 has NEON in the base ISA, so it needs no flag
# (and -mavx2 is not a valid option there).
ifeq ($(UNAME_M),x86_64)
  CFLAGS += -mavx2 -mfma
endif

# --- OpenMP -----------------------------------------------------------------
# GCC accepts -fopenmp for both compile and link. Apple clang needs libomp,
# normally from Homebrew; when it is absent we build single-threaded rather
# than failing the build.
ifeq ($(UNAME_S),Darwin)
  LIBOMP := $(shell brew --prefix libomp 2>/dev/null)
  ifneq ($(LIBOMP),)
    CFLAGS += -Xpreprocessor -fopenmp -I$(LIBOMP)/include
    LDFLAGS += -L$(LIBOMP)/lib -lomp
  endif
else
  CFLAGS += -fopenmp -D_GNU_SOURCE
  LDFLAGS += -fopenmp
endif

TARGET = vapor_engine
OBJS = vapor_engine.o streaming_io.o kv_cache.o
BENCH_SRC = ../tools/simd_bench.c
TOOLS = $(if $(wildcard $(BENCH_SRC)),simd_bench,)

all: $(TARGET) $(TOOLS)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDFLAGS)

simd_bench: $(BENCH_SRC)
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# Report the configuration the build will use; handy when diagnosing a host
# that silently lost AVX2 or OpenMP.
info:
	@echo "system : $(UNAME_S) $(UNAME_M)"
	@echo "CC     : $(CC)"
	@echo "CFLAGS : $(CFLAGS)"
	@echo "LDFLAGS: $(LDFLAGS)"

clean:
	rm -f $(OBJS) $(TARGET) simd_bench

.PHONY: all clean info
