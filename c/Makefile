CC = gcc
CFLAGS = -O3 -Wall -Wextra -mavx2 -mfma -fopenmp -std=c11 -D_GNU_SOURCE
LDFLAGS = -lm -fopenmp

TARGET = vapor_engine
OBJS = vapor_engine.o streaming_io.o kv_cache.o

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
