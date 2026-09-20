# PROOF OF SIMULATION — Makefile
# Requires GCC (gcc) or Clang (clang) in PATH, or set CC explicitly.

CC ?= gcc
CFLAGS = -O3 -std=c11 -Wall -Wextra -Wpedantic
LDFLAGS = -lm
SRC = kernel.c
OUT = kernel

# On Windows, append .exe
ifeq ($(OS),Windows_NT)
  OUT := kernel.exe
endif

.PHONY: all clean test self-test init benchmark auto verify

all: kernel

kernel: $(SRC)
	$(CC) $(CFLAGS) $(SRC) $(LDFLAGS) -o $(OUT)

clean:
ifeq ($(OS),Windows_NT)
	-if exist kernel.exe del kernel.exe
	-if exist kernel del kernel
	-if exist *.o del *.o
else
	rm -f kernel kernel.exe *.o
endif

test: kernel
	python3 agent_loop.py self-test

self-test: test

init: kernel
	python3 agent_loop.py init

benchmark: kernel
	python3 agent_loop.py benchmark

auto: kernel
	python3 agent_loop.py auto

# Consolidated repository self-check (read-only: source, deliverables, DBs)
verify:
	python3 verify.py
