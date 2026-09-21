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

.PHONY: all clean test self-test init benchmark auto verify v6 v7 stress

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

# Standalone research pipelines (also runnable via `python <script>`)
v6:
	python3 v6_pipeline.py

v7:
	python3 v7_lattice.py

# Long deep-validation battery over V6+V7 math & plumbing (stdlib, deterministic).
# Underscore-prefixed source => intentionally excluded from verify.py module scan.
stress:
	python3 -u _stress.py
