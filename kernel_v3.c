/*
 * PROOF OF SIMULATION — C Numerical Kernel V3
 * Non-autonomous Julia set iteration with prime-arithmetic forcing.
 * V3 additions over V2: explicit --driver-file injection so V3 can supply
 *   externally computed (and independently testable) forcing sequences while
 *   reusing the frozen V2 iteration, metrics and target machinery.
 *   No V2 behaviour is changed; driver_from_string stays strict (unknown
 *   driver => error, never a silent V0 fallback).
 * Compile: gcc -O3 -std=c11 -Wall -Wextra -Wpedantic kernel_v3.c -lm -o kernel_v3
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include <time.h>
#include <stdint.h>
#include <ctype.h>
#include <errno.h>

/* ================================================================
 * CONSTANTS
 * ================================================================ */
#define KERNEL_VERSION "3.0.0"
static const double PI_VAL = 3.141592653589793238462643383279502884;
static const double EULER_GAMMA = 0.577215664901532860606512090082402431;
#define MAX_W    512
#define MAX_H    512
#define MAX_CELLS (MAX_W * MAX_H)
#define ESCAPE_R2 4.0
#define MAX_DRIVER_LEN 20010
#define MAX_DCT_MODES 16
#define ENTROPY_BINS 16
#define ACORR_RANGE 4
#define ACORR_SIZE (2*ACORR_RANGE+1)
#define ACORR_TOTAL (ACORR_SIZE*ACORR_SIZE - 1)
#define ASCII_PALETTE " .:-=+*#%@"
#define ASCII_PAL_LEN 10
#define MAX_LINE 4096

/* ================================================================
 * SPLITMIX64 PRNG
 * ================================================================ */
typedef struct { uint64_t state; } SM64;
static void sm64_seed(SM64 *r, uint64_t s) { r->state = s; }
static uint64_t sm64_next(SM64 *r) {
    r->state += 0x9E3779B97F4A7C15ULL;
    uint64_t z = r->state;
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}
static double sm64_double(SM64 *r) {
    return (double)(sm64_next(r) >> 11) / (double)(1ULL << 53);
}

/* ================================================================
 * PRIME SIEVE AND PI FUNCTION
 * ================================================================ */
static int  *g_pi_prefix = NULL;
static int   g_pi_len    = 0;

static void sieve_build(int n) {
    if (g_pi_prefix && g_pi_len >= n + 1) return;
    free(g_pi_prefix);
    g_pi_len = n + 1;
    g_pi_prefix = (int *)calloc((size_t)g_pi_len, sizeof(int));
    if (!g_pi_prefix) { fprintf(stderr, "sieve: OOM\n"); exit(1); }
    char *is_p = (char *)calloc((size_t)g_pi_len, 1);
    if (!is_p) { fprintf(stderr, "sieve: OOM\n"); exit(1); }
    for (int i = 2; i <= n; i++) is_p[i] = 1;
    for (int i = 2; (long long)i * i <= n; i++)
        if (is_p[i]) for (int j = i * i; j <= n; j += i) is_p[j] = 0;
    g_pi_prefix[0] = 0;
    if (g_pi_len > 1) g_pi_prefix[1] = 0;
    for (int k = 2; k <= n; k++)
        g_pi_prefix[k] = g_pi_prefix[k - 1] + is_p[k];
    free(is_p);
}
static int pi_func(int k) {
    if (k < 0) return 0;
    if (k < g_pi_len) return g_pi_prefix[k];
    return g_pi_prefix[g_pi_len - 1];
}
static int is_prime_check(int k) {
    if (k < 2) return 0;
    if (k < 4) return 1;
    if (k % 2 == 0 || k % 3 == 0) return 0;
    for (int d = 5; (long long)d * d <= k; d += 6)
        if (k % d == 0 || k % (d + 2) == 0) return 0;
    return 1;
}

/* ================================================================
 * DRIVER COMPUTATION
 * ================================================================ */
typedef enum {
    DRV_V0_NONE = 0, DRV_V1_INV_PI, DRV_V2_SMOOTH, DRV_V3_CENTERED_INV_PI,
    DRV_V4_PRIME_RESIDUAL, DRV_V5_SHUFFLED, DRV_V6_REVERSED, DRV_V7_IMAGINARY,
    DRV_V8_PHASE_RANDOMIZED, DRV_V9_PRIME_EVENT, DRV_V10_PRIME_RESIDUAL,
    DRV_S1_ANALYTIC, DRV_S2_DATA_SMOOTHED,
    DRV_V11_MATCHED_EVENT, DRV_V12_SHIFTED_EVENT, DRV_V13_GAP_MATCHED,
    DRV_COUNT
} DriverID;

static const char *driver_name(DriverID d) {
    switch (d) {
        case DRV_V0_NONE:             return "V0_NONE";
        case DRV_V1_INV_PI:           return "V1_INV_PI";
        case DRV_V2_SMOOTH:           return "V2_SMOOTH";
        case DRV_V3_CENTERED_INV_PI:  return "V3_CENTERED_INV_PI";
        case DRV_V4_PRIME_RESIDUAL:   return "V4_PRIME_RESIDUAL";
        case DRV_V5_SHUFFLED:         return "V5_SHUFFLED";
        case DRV_V6_REVERSED:         return "V6_REVERSED";
        case DRV_V7_IMAGINARY:        return "V7_IMAGINARY";
        case DRV_V8_PHASE_RANDOMIZED: return "V8_PHASE_RANDOMIZED";
        case DRV_V9_PRIME_EVENT:      return "V9_PRIME_EVENT";
        case DRV_V10_PRIME_RESIDUAL:  return "V10_PRIME_RESIDUAL";
        case DRV_S1_ANALYTIC:         return "S1_ANALYTIC";
        case DRV_S2_DATA_SMOOTHED:    return "S2_DATA_SMOOTHED";
        case DRV_V11_MATCHED_EVENT:   return "V11_MATCHED_EVENT";
        case DRV_V12_SHIFTED_EVENT:   return "V12_SHIFTED_EVENT";
        case DRV_V13_GAP_MATCHED:     return "V13_GAP_MATCHED";
        default:                      return "UNKNOWN";
    }
}

/* Strict parsing: returns 1 on success, 0 on unknown name */
static int driver_from_string(const char *s, DriverID *out) {
    if (!strcmp(s, "V0_NONE")       || !strcmp(s, "NONE") || !strcmp(s, "V0")) { *out = DRV_V0_NONE; return 1; }
    if (!strcmp(s, "V1_INV_PI")     || !strcmp(s, "V1"))  { *out = DRV_V1_INV_PI; return 1; }
    if (!strcmp(s, "V2_SMOOTH")     || !strcmp(s, "V2"))  { *out = DRV_V2_SMOOTH; return 1; }
    if (!strcmp(s, "V3_CENTERED_INV_PI") || !strcmp(s, "V3")) { *out = DRV_V3_CENTERED_INV_PI; return 1; }
    if (!strcmp(s, "V4_PRIME_RESIDUAL")  || !strcmp(s, "V4")) { *out = DRV_V4_PRIME_RESIDUAL; return 1; }
    if (!strcmp(s, "V5_SHUFFLED")   || !strcmp(s, "V5"))  { *out = DRV_V5_SHUFFLED; return 1; }
    if (!strcmp(s, "V6_REVERSED")   || !strcmp(s, "V6"))  { *out = DRV_V6_REVERSED; return 1; }
    if (!strcmp(s, "V7_IMAGINARY")  || !strcmp(s, "V7"))  { *out = DRV_V7_IMAGINARY; return 1; }
    if (!strcmp(s, "V8_PHASE_RANDOMIZED") || !strcmp(s, "V8")) { *out = DRV_V8_PHASE_RANDOMIZED; return 1; }
    if (!strcmp(s, "V9_PRIME_EVENT") || !strcmp(s, "V9")) { *out = DRV_V9_PRIME_EVENT; return 1; }
    if (!strcmp(s, "V10_PRIME_RESIDUAL") || !strcmp(s, "V10")) { *out = DRV_V10_PRIME_RESIDUAL; return 1; }
    if (!strcmp(s, "S1_ANALYTIC")   || !strcmp(s, "S1"))  { *out = DRV_S1_ANALYTIC; return 1; }
    if (!strcmp(s, "S2_DATA_SMOOTHED") || !strcmp(s, "S2")) { *out = DRV_S2_DATA_SMOOTHED; return 1; }
    if (!strcmp(s, "V11_MATCHED_EVENT") || !strcmp(s, "V11")) { *out = DRV_V11_MATCHED_EVENT; return 1; }
    if (!strcmp(s, "V12_SHIFTED_EVENT") || !strcmp(s, "V12")) { *out = DRV_V12_SHIFTED_EVENT; return 1; }
    if (!strcmp(s, "V13_GAP_MATCHED") || !strcmp(s, "V13")) { *out = DRV_V13_GAP_MATCHED; return 1; }
    return 0;
}

/* Raw 1/pi(k) */
static void compute_raw_inv_pi(double *out, int max_iter) {
    for (int k = 1; k <= max_iter; k++) {
        int pk = pi_func(k);
        if (pk < 1) pk = 1;
        out[k] = 1.0 / (double)pk;
    }
}

/* Exponential integral Ei(x) via convergent series for x>0 */
static double ei_series(double x) {
    if (x <= 0) return -1e300;
    if (x > 50) { /* asymptotic */ double s = 1.0, t = 1.0;
        for (int k = 1; k < 60; k++) { t *= (double)k / x; if (t < 1e-15) break; s += t; }
        return exp(x) / x * s; }
    double sum = EULER_GAMMA + log(x);
    double term = 1.0;
    for (int m = 1; m < 120; m++) {
        term *= x / (double)m;
        double add = term / (double)m;
        sum += add;
        if (fabs(add) < 1e-15 * fabs(sum)) break;
    }
    return sum;
}
static double li_func(double x) {
    if (x < 2.0) return 0.0;
    return ei_series(log(x));
}

/* S1_ANALYTIC: smooth approximation to 1/pi(k) using logarithmic integral */
static void compute_s1_analytic(double *out, int max_iter) {
    double li2 = li_func(2.0); /* ~0.3786 */
    for (int k = 1; k <= max_iter; k++) {
        double s;
        if (k <= 2) s = 1.0; /* protected */
        else { double lik = li_func((double)k); s = lik - li2 + 1.0; if (s < 1.0) s = 1.0; }
        out[k] = 1.0 / s;
    }
}

/* S2_DATA_SMOOTHED: centered moving average of P(k) */
static void compute_s2_smoothed(double *out, const double *raw, int max_iter, int window) {
    int hw = window / 2;
    for (int k = 1; k <= max_iter; k++) {
        double sum = 0; int cnt = 0;
        for (int j = k - hw; j <= k + hw; j++) {
            int jj = j < 1 ? 1 : (j > max_iter ? max_iter : j);
            sum += raw[jj]; cnt++;
        }
        out[k] = sum / cnt;
    }
}

/* V2: match raw to ref statistics over first 200 elements */
static void match_to_ref(double *out, const double *vals, const double *ref, int max_iter) {
    int nref = max_iter < 200 ? max_iter : 200;
    double mr = 0, mv = 0;
    for (int k = 1; k <= nref; k++) { mr += ref[k]; mv += vals[k]; }
    mr /= nref; mv /= nref;
    double vr = 0, vv = 0;
    for (int k = 1; k <= nref; k++) { vr += (ref[k]-mr)*(ref[k]-mr); vv += (vals[k]-mv)*(vals[k]-mv); }
    vr /= nref; vv /= nref;
    double sr = sqrt(vr), sv = sqrt(vv);
    if (sv < 1e-15) { for (int k = 1; k <= max_iter; k++) out[k] = 0.0; return; }
    for (int k = 1; k <= max_iter; k++)
        out[k] = mr + sr * (vals[k] - mv) / sv;
}

/* Collect nonzero E(k) positions and amplitudes */
static int collect_events(const double *E, int max_iter, int *pos, double *amp, int maxev) {
    int n = 0;
    for (int k = 1; k <= max_iter && n < maxev; k++)
        if (fabs(E[k]) > 1e-18) { pos[n] = k; amp[n] = E[k]; n++; }
    return n;
}

/* Fisher-Yates shuffle with SM64 */
static void fy_shuffle(int *arr, int n, SM64 *rng) {
    for (int i = n - 1; i >= 1; i--) {
        int j = (int)(sm64_double(rng) * (double)(i + 1));
        if (j > i) j = i;
        int tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
    }
}

static void compute_driver(double *drv, DriverID id, int max_iter,
                           uint64_t shuffle_seed, int window) {
    double raw[MAX_DRIVER_LEN];
    memset(raw, 0, sizeof(raw));
    memset(drv, 0, sizeof(double) * (size_t)(max_iter + 1));
    if (id == DRV_V0_NONE) return;

    compute_raw_inv_pi(raw, max_iter);

    switch (id) {
    case DRV_V1_INV_PI:
        for (int k = 1; k <= max_iter; k++) drv[k] = raw[k];
        break;
    case DRV_V2_SMOOTH: {
        double s1[MAX_DRIVER_LEN]; compute_s1_analytic(s1, max_iter);
        match_to_ref(drv, s1, raw, max_iter);
        break;
    }
    case DRV_V3_CENTERED_INV_PI: {
        int nref = max_iter < 200 ? max_iter : 200;
        double mean = 0;
        for (int k = 1; k <= nref; k++) mean += raw[k];
        mean /= nref;
        for (int k = 1; k <= max_iter; k++) drv[k] = raw[k] - mean;
        break;
    }
    case DRV_V4_PRIME_RESIDUAL: {
        double s1[MAX_DRIVER_LEN]; compute_s1_analytic(s1, max_iter);
        double resid[MAX_DRIVER_LEN];
        int nref = max_iter < 200 ? max_iter : 200;
        double sum = 0;
        for (int k = 1; k <= max_iter; k++) { resid[k] = raw[k] - s1[k]; if (k <= nref) sum += resid[k]; }
        double mean = sum / nref;
        double var = 0;
        for (int k = 1; k <= nref; k++) var += (resid[k] - mean) * (resid[k] - mean);
        var /= nref;
        double std = sqrt(var);
        if (std < 1e-15) { for (int k = 1; k <= max_iter; k++) drv[k] = 0; break; }
        for (int k = 1; k <= max_iter; k++) drv[k] = (resid[k] - mean) / std;
        break;
    }
    case DRV_V5_SHUFFLED: {
        SM64 rng; sm64_seed(&rng, shuffle_seed);
        for (int k = 1; k <= max_iter; k++) drv[k] = raw[k];
        for (int k = max_iter; k >= 2; k--) {
            int j = 1 + (int)(sm64_double(&rng) * k);
            if (j > k) j = k;
            double tmp = drv[k]; drv[k] = drv[j]; drv[j] = tmp;
        }
        break;
    }
    case DRV_V6_REVERSED:
        for (int k = 1; k <= max_iter; k++) drv[k] = raw[max_iter - k + 1];
        break;
    case DRV_V7_IMAGINARY:
        for (int k = 1; k <= max_iter; k++) drv[k] = raw[k];
        break;
    case DRV_V8_PHASE_RANDOMIZED: {
        int nref = max_iter < 200 ? max_iter : 200;
        double mean = 0;
        for (int k = 1; k <= nref; k++) mean += raw[k];
        mean /= nref;
        double centered[MAX_DRIVER_LEN];
        for (int k = 1; k <= max_iter; k++) centered[k] = raw[k] - mean;
        int N = max_iter;
        double re_in[MAX_DRIVER_LEN], im_in[MAX_DRIVER_LEN];
        for (int k = 0; k < N; k++) { re_in[k] = centered[k + 1]; im_in[k] = 0.0; }
        double re_out[MAX_DRIVER_LEN], im_out[MAX_DRIVER_LEN];
        for (int m = 0; m < N; m++) {
            double sr = 0, si = 0;
            for (int k = 0; k < N; k++) {
                double angle = 2.0 * PI_VAL * m * k / N;
                sr += re_in[k] * cos(angle) + im_in[k] * sin(angle);
                si += im_in[k] * cos(angle) - re_in[k] * sin(angle);
            }
            re_out[m] = sr; im_out[m] = si;
        }
        SM64 rng; sm64_seed(&rng, shuffle_seed);
        double phases[MAX_DRIVER_LEN];
        phases[0] = 0;
        for (int m = 1; m < (N + 1) / 2; m++) phases[m] = sm64_double(&rng) * 2.0 * PI_VAL;
        if (N % 2 == 0) {
            /* Nyquist: real signed coefficient */
            double u = sm64_double(&rng);
            phases[N / 2] = (u < 0.5) ? 0.0 : PI_VAL;
        } else {
            phases[N / 2] = sm64_double(&rng) * 2.0 * PI_VAL;
        }
        for (int m = N / 2 + 1; m < N; m++) phases[m] = -phases[N - m];
        double re_r[MAX_DRIVER_LEN], im_r[MAX_DRIVER_LEN];
        for (int m = 0; m < N; m++) {
            double amp = sqrt(re_out[m] * re_out[m] + im_out[m] * im_out[m]);
            re_r[m] = amp * cos(phases[m]);
            im_r[m] = amp * sin(phases[m]);
        }
        for (int k = 0; k < N; k++) {
            double sr = 0;
            for (int m = 0; m < N; m++) {
                double angle = 2.0 * PI_VAL * m * k / N;
                sr += re_r[m] * cos(angle) - im_r[m] * sin(angle);
            }
            drv[k + 1] = sr / N;
        }
        break;
    }
    case DRV_V9_PRIME_EVENT: {
        /* E(k) = P(k) - P(k-1), P(0)=1 */
        double P[MAX_DRIVER_LEN]; P[0] = 1.0;
        for (int k = 1; k <= max_iter; k++) {
            int pk = pi_func(k); if (pk < 1) pk = 1;
            P[k] = 1.0 / (double)pk;
        }
        for (int k = 1; k <= max_iter; k++) drv[k] = P[k] - P[k - 1];
        break;
    }
    case DRV_V10_PRIME_RESIDUAL: {
        double s1[MAX_DRIVER_LEN]; compute_s1_analytic(s1, max_iter);
        double resid[MAX_DRIVER_LEN];
        int nref = max_iter < 200 ? max_iter : 200;
        double sum = 0;
        for (int k = 1; k <= max_iter; k++) { resid[k] = raw[k] - s1[k]; if (k <= nref) sum += resid[k]; }
        double mean = sum / nref;
        double var = 0;
        for (int k = 1; k <= nref; k++) var += (resid[k] - mean) * (resid[k] - mean);
        var /= nref;
        double std = sqrt(var);
        if (std < 1e-15) { for (int k = 1; k <= max_iter; k++) drv[k] = 0; break; }
        for (int k = 1; k <= max_iter; k++) drv[k] = (resid[k] - mean) / std;
        break;
    }
    case DRV_S1_ANALYTIC:
        compute_s1_analytic(drv, max_iter);
        break;
    case DRV_S2_DATA_SMOOTHED:
        compute_s2_smoothed(drv, raw, max_iter, window);
        break;
    case DRV_V11_MATCHED_EVENT: {
        /* Permute nonzero event amplitudes into random positions */
        double P[MAX_DRIVER_LEN]; P[0] = 1.0;
        for (int k = 1; k <= max_iter; k++) { int pk = pi_func(k); if (pk < 1) pk = 1; P[k] = 1.0 / (double)pk; }
        double E[MAX_DRIVER_LEN];
        for (int k = 1; k <= max_iter; k++) E[k] = P[k] - P[k - 1];
        int pos[MAX_DRIVER_LEN]; double amp[MAX_DRIVER_LEN];
        int nev = collect_events(E, max_iter, pos, amp, max_iter);
        SM64 rng; sm64_seed(&rng, shuffle_seed);
        int *perm = (int *)calloc((size_t)max_iter, sizeof(int));
        if (!perm) { fprintf(stderr, "OOM\n"); exit(1); }
        for (int i = 0; i < max_iter; i++) perm[i] = i;
        fy_shuffle(perm, max_iter, &rng);
        for (int i = 0; i < nev && i < max_iter; i++)
            drv[perm[i] + 1] = amp[i];
        free(perm);
        break;
    }
    case DRV_V12_SHIFTED_EVENT: {
        double P[MAX_DRIVER_LEN]; P[0] = 1.0;
        for (int k = 1; k <= max_iter; k++) { int pk = pi_func(k); if (pk < 1) pk = 1; P[k] = 1.0 / (double)pk; }
        double E[MAX_DRIVER_LEN];
        for (int k = 1; k <= max_iter; k++) E[k] = P[k] - P[k - 1];
        int shift = (int)shuffle_seed; /* seed encodes shift */
        for (int k = 1; k <= max_iter; k++) {
            int src = ((k - 1 + shift) % max_iter) + 1;
            drv[k] = E[src];
        }
        break;
    }
    case DRV_V13_GAP_MATCHED: {
        double P[MAX_DRIVER_LEN]; P[0] = 1.0;
        for (int k = 1; k <= max_iter; k++) { int pk = pi_func(k); if (pk < 1) pk = 1; P[k] = 1.0 / (double)pk; }
        double E[MAX_DRIVER_LEN];
        for (int k = 1; k <= max_iter; k++) E[k] = P[k] - P[k - 1];
        int pos[MAX_DRIVER_LEN]; double amp[MAX_DRIVER_LEN];
        int nev = collect_events(E, max_iter, pos, amp, max_iter);
        if (nev < 2) break;
        /* Compute circular gaps */
        int gaps[MAX_DRIVER_LEN];
        for (int i = 0; i < nev - 1; i++) gaps[i] = pos[i + 1] - pos[i];
        gaps[nev - 1] = max_iter - pos[nev - 1] + pos[0];
        /* Permute gaps deterministically */
        SM64 rng; sm64_seed(&rng, shuffle_seed);
        fy_shuffle(gaps, nev, &rng);
        /* Reconstruct positions from permuted gaps */
        int new_pos[MAX_DRIVER_LEN];
        new_pos[0] = pos[0]; /* keep starting phase */
        for (int i = 1; i < nev; i++)
            new_pos[i] = (new_pos[i - 1] + gaps[i - 1] - 1) % max_iter + 1;
        for (int i = 0; i < nev; i++) drv[new_pos[i]] = amp[i];
        break;
    }
    default: break;
    }
}

/* V3: load an externally supplied forcing sequence D(1..max_iter).
 * The file holds one finite float per line (extra lines ignored). Returns 1 on
 * success. A short file is an error: V3 never silently pads with zeros. */
static int load_driver_file(const char *path, double *out, int max_iter) {
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "driver-file: cannot open '%s'\n", path); return 0; }
    int k = 1;
    double v;
    while (k <= max_iter && fscanf(f, "%lf", &v) == 1) {
        if (!isfinite(v)) { fprintf(stderr, "driver-file: non-finite at k=%d\n", k); fclose(f); return 0; }
        out[k] = v;
        k++;
    }
    if (k <= max_iter) {
        fprintf(stderr, "driver-file: expected %d values, found %d\n", max_iter, k - 1);
        fclose(f); return 0;
    }
    fclose(f);
    return 1;
}
/* ================================================================
 * TARGET FUNCTIONS
 * ================================================================ */
typedef enum {
    TGT_A = 0, TGT_B, TGT_PHASE, TGT_EIGENMODE,
    TGT_LOW1, TGT_LOW2, TGT_LOW3, TGT_LOW4,
    TGT_COUNT
} TargetID;

static int target_from_string(const char *s, TargetID *out, int *pn, int *pm) {
    if (!strcmp(s, "TARGET_A"))     { *out = TGT_A; return 1; }
    if (!strcmp(s, "TARGET_B"))     { *out = TGT_B; return 1; }
    if (!strcmp(s, "TARGET_PHASE")) { *out = TGT_PHASE; return 1; }
    if (!strcmp(s, "LOW_MODE_1"))   { *out = TGT_LOW1; return 1; }
    if (!strcmp(s, "LOW_MODE_2"))   { *out = TGT_LOW2; return 1; }
    if (!strcmp(s, "LOW_MODE_3"))   { *out = TGT_LOW3; return 1; }
    if (!strcmp(s, "LOW_MODE_4"))   { *out = TGT_LOW4; return 1; }
    if (strncmp(s, "T_", 2) == 0) {
        int n = 0, m = 0;
        if (sscanf(s + 2, "%d_%d", &n, &m) == 2 && n >= 1 && n <= 4 && m >= 1 && m <= 4) {
            *out = TGT_EIGENMODE; *pn = n; *pm = m; return 1;
        }
    }
    return 0;
}
static const char *target_name(TargetID t, int n, int m) {
    static char buf[32];
    switch (t) {
        case TGT_A: return "TARGET_A"; case TGT_B: return "TARGET_B";
        case TGT_PHASE: return "TARGET_PHASE";
        case TGT_LOW1: return "LOW_MODE_1"; case TGT_LOW2: return "LOW_MODE_2";
        case TGT_LOW3: return "LOW_MODE_3"; case TGT_LOW4: return "LOW_MODE_4";
        case TGT_EIGENMODE: snprintf(buf, sizeof(buf), "T_%d_%d", n, m); return buf;
        default: return "UNKNOWN";
    }
}

static void compute_target(double *T, TargetID tid, int W, int H, int param_n, int param_m) {
    for (int py = 0; py < H; py++) {
        double v = (H > 1) ? (double)py / (H - 1) : 0.5;
        for (int px = 0; px < W; px++) {
            double u = (W > 1) ? (double)px / (W - 1) : 0.5;
            int idx = py * W + px;
            switch (tid) {
            case TGT_A:
                T[idx] = fabs(sin(PI_VAL * u) * cos(PI_VAL * v)); break;
            case TGT_B:
                T[idx] = sin(PI_VAL * u) * sin(PI_VAL * u) * cos(PI_VAL * v) * cos(PI_VAL * v); break;
            case TGT_PHASE: {
                double uu = u + 0.07, vv = v - 0.11;
                uu = uu - floor(uu); vv = vv - floor(vv);
                T[idx] = fabs(sin(PI_VAL * uu) * cos(PI_VAL * vv)); break;
            }
            case TGT_EIGENMODE:
                T[idx] = sin(param_n * PI_VAL * u) * sin(param_n * PI_VAL * u)
                       * sin(param_m * PI_VAL * v) * sin(param_m * PI_VAL * v); break;
            case TGT_LOW1:
                T[idx] = 0.5 + 0.3 * cos(PI_VAL * u) * cos(PI_VAL * v); break;
            case TGT_LOW2:
                T[idx] = 0.5 + 0.2 * cos(2.0 * PI_VAL * u) + 0.2 * cos(2.0 * PI_VAL * v); break;
            case TGT_LOW3:
                T[idx] = 0.5 + 0.25 * sin(PI_VAL * u) * sin(PI_VAL * v); break;
            case TGT_LOW4:
                T[idx] = 0.6 + 0.15 * cos(PI_VAL * u) + 0.1 * cos(PI_VAL * v); break;
            }
        }
    }
}

/* ================================================================
 * COMPLEX ARITHMETIC
 * ================================================================ */
static inline void complex_sq(double zr, double zi, double *or_, double *oi) {
    *or_ = zr * zr - zi * zi; *oi = 2.0 * zr * zi;
}
static inline void complex_cub(double zr, double zi, double *or_, double *oi) {
    double z2r = zr * zr - zi * zi, z2i = 2.0 * zr * zi;
    *or_ = zr * z2r - zi * z2i; *oi = zr * z2i + zi * z2r;
}

/* ================================================================
 * JULIA ITERATION WITH FORCING
 * ================================================================ */
static void iterate_julia(double cr, double ci, const double *driver,
                           double alpha, int degree, int channel,
                           int max_iter, int W, int H,
                           double *F_smooth, double *F_discrete,
                           double *escaped_frac,
                           double *tr_active, double *tr_mean_abs,
                           double *tr_std_abs, double *tr_mean_zr,
                           double *tr_mean_zi, double *tr_esc_frac,
                           double *tr_driver_val, int *tr_prime_event,
                           int do_trace,
                           /* V4 full-field temporal (§41-42) */
                           double *tr_mean_log_r, double *tr_std_log_r,
                           double *tr_mean_bounded, double *tr_var_bounded,
                           int temporal_fullfield)
{
    int NCELLS = W * H;
    double *F_s = (double *)malloc(sizeof(double) * (size_t)NCELLS);
    double *F_d = (double *)malloc(sizeof(double) * (size_t)NCELLS);
    if (!F_s || !F_d) { fprintf(stderr, "iterate_julia: OOM\n"); exit(1); }
    int escaped_count = 0;
    double x_min = -1.8, x_range = 3.6, y_min = -1.0, y_range = 2.0;
    double log_deg = log((double)degree);
    if (log_deg < 1e-15) log_deg = log(2.0);
    /* V4 full-field temporal accumulators (§41) */
    double Z_CAP = 1e6;
    double *ff_sum_log = NULL, *ff_sum_log2 = NULL;
    double *ff_sum_bnd = NULL, *ff_sum_bnd2 = NULL;
    if (temporal_fullfield && tr_mean_log_r) {
        ff_sum_log  = (double *)calloc((size_t)max_iter, sizeof(double));
        ff_sum_log2 = (double *)calloc((size_t)max_iter, sizeof(double));
        ff_sum_bnd  = (double *)calloc((size_t)max_iter, sizeof(double));
        ff_sum_bnd2 = (double *)calloc((size_t)max_iter, sizeof(double));
    }

    for (int py = 0; py < H; py++) {
        double y = y_min + y_range * ((H > 1) ? (double)py / (H - 1) : 0.5);
        for (int px = 0; px < W; px++) {
            double x = x_min + x_range * ((W > 1) ? (double)px / (W - 1) : 0.5);
            int idx = py * W + px;
            double zr = x, zi = y;
            int esc_iter = max_iter;

            for (int iter = 0; iter < max_iter; iter++) {
                double old_zr = zr, old_zi = zi;
                double sq_r, sq_i;
                if (degree == 3) complex_cub(old_zr, old_zi, &sq_r, &sq_i);
                else             complex_sq(old_zr, old_zi, &sq_r, &sq_i);

                int k = iter + 1;
                double drv_val = (k <= max_iter) ? driver[k] : 0.0;
                double real_corr = 0, imag_corr = 0;
                if (channel == 0) real_corr = alpha * drv_val;
                else              imag_corr = alpha * drv_val;

                zr = sq_r + cr + real_corr;
                zi = sq_i + ci + imag_corr;

                if (!isfinite(zr) || !isfinite(zi)) {
                    esc_iter = iter; zr = 1e10; zi = 0; break;
                }
                if (zr * zr + zi * zi > ESCAPE_R2) { esc_iter = iter; break; }
            }

            double nu;
            if (esc_iter < max_iter) {
                double mag = hypot(zr, zi);
                if (mag > 1.0 && isfinite(mag))
                    nu = (double)(esc_iter + 1) - log(log(mag)) / log_deg;
                else
                    nu = (double)esc_iter;
                escaped_count++;
            } else {
                nu = (double)max_iter;
            }
            if (nu < 0) nu = 0;
            if (nu > max_iter) nu = max_iter;
            F_s[idx] = nu / (double)max_iter;
            F_d[idx] = (double)esc_iter / (double)max_iter;
        }
    }

    if (F_smooth)      memcpy(F_smooth, F_s, sizeof(double) * (size_t)NCELLS);
    if (F_discrete)    memcpy(F_discrete, F_d, sizeof(double) * (size_t)NCELLS);
    if (escaped_frac)  *escaped_frac = (double)escaped_count / (double)NCELLS;

    /* One-pass trace: accumulate per-iteration stats in single forward pass */
    if (do_trace && tr_active) {
        /* Allocate accumulators */
        double *sum_abs  = (double *)calloc((size_t)max_iter, sizeof(double));
        double *sum_abs2 = (double *)calloc((size_t)max_iter, sizeof(double));
        double *sum_zr   = (double *)calloc((size_t)max_iter, sizeof(double));
        double *sum_zi   = (double *)calloc((size_t)max_iter, sizeof(double));
        int    *active   = (int *)calloc((size_t)max_iter, sizeof(int));
        int    *esc_cnt  = (int *)calloc((size_t)max_iter, sizeof(int));
        if (!sum_abs || !sum_abs2 || !sum_zr || !sum_zi || !active || !esc_cnt) {
            fprintf(stderr, "trace: OOM\n"); exit(1);
        }

        /* Single forward pass per pixel */
        for (int py = 0; py < H; py++) {
            double y0 = y_min + y_range * ((H > 1) ? (double)py / (H - 1) : 0.5);
            for (int px = 0; px < W; px++) {
                double x0 = x_min + x_range * ((W > 1) ? (double)px / (W - 1) : 0.5);
                double zr = x0, zi = y0;
                for (int iter = 0; iter < max_iter; iter++) {
                    double oz = zr, ozi = zi;
                    double sr, si;
                    if (degree == 3) complex_cub(oz, ozi, &sr, &si);
                    else             complex_sq(oz, ozi, &sr, &si);
                    int k = iter + 1;
                    double dv = driver[k];
                    double rc = 0, ic = 0;
                    if (channel == 0) rc = alpha * dv; else ic = alpha * dv;
                    zr = sr + cr + rc;
                    zi = si + ci + ic;
                    if (!isfinite(zr) || !isfinite(zi) || zr*zr+zi*zi > ESCAPE_R2) {
                        if (temporal_fullfield) {
                            /* Escape-safe: cap magnitude, continue (§42) */
                            double ab = hypot(zr, zi);
                            if (!isfinite(ab) || ab > Z_CAP) { zr = Z_CAP; zi = 0; ab = Z_CAP; }
                            double q = log1p(fmin(ab, Z_CAP));
                            double bnd = fmin(ab, Z_CAP) / Z_CAP;
                            if (ff_sum_log) { ff_sum_log[iter] += q; ff_sum_log2[iter] += q*q; }
                            if (ff_sum_bnd) { ff_sum_bnd[iter] += bnd; ff_sum_bnd2[iter] += bnd*bnd; }
                            if (tr_active) { /* still count as escaped for active_frac */
                                for (int t = iter+1; t < max_iter; t++) esc_cnt[t]++;
                            }
                        } else {
                            for (int t = iter; t < max_iter; t++) esc_cnt[t]++;
                            break;
                        }
                    } else {
                    double ab = hypot(zr, zi);
                    sum_abs[iter] += ab;
                    sum_abs2[iter] += ab * ab;
                    sum_zr[iter] += zr;
                    sum_zi[iter] += zi;
                    active[iter]++;
                    if (temporal_fullfield && ff_sum_log) {
                        double q = log1p(fmin(ab, Z_CAP));
                        double bnd = fmin(ab, Z_CAP) / Z_CAP;
                        ff_sum_log[iter] += q; ff_sum_log2[iter] += q*q;
                        ff_sum_bnd[iter] += bnd; ff_sum_bnd2[iter] += bnd*bnd;
                    }
                    }
                }
            }
        }

        for (int iter = 0; iter < max_iter; iter++) {
            int k = iter + 1;
            int act = active[iter];
            tr_active[iter]   = (double)act / NCELLS;
            tr_mean_abs[iter] = act > 0 ? sum_abs[iter] / act : 0;
            double m = act > 0 ? sum_abs[iter] / act : 0;
            tr_std_abs[iter]  = act > 1 ? sqrt(sum_abs2[iter]/act - m*m) : 0;
            tr_mean_zr[iter]  = act > 0 ? sum_zr[iter] / act : 0;
            tr_mean_zi[iter]  = act > 0 ? sum_zi[iter] / act : 0;
            tr_esc_frac[iter] = (double)esc_cnt[iter] / NCELLS;
            tr_driver_val[iter] = driver[k];
            tr_prime_event[iter] = is_prime_check(k);
            /* V4 full-field temporal output (§41) */
            if (temporal_fullfield && tr_mean_log_r && ff_sum_log) {
                double ml = ff_sum_log[iter] / NCELLS;
                double ml2 = ff_sum_log2[iter] / NCELLS;
                tr_mean_log_r[iter] = ml;
                tr_std_log_r[iter] = ml2 - ml*ml > 0 ? sqrt(ml2 - ml*ml) : 0;
            }
            if (temporal_fullfield && tr_mean_bounded && ff_sum_bnd) {
                double mb = ff_sum_bnd[iter] / NCELLS;
                double mb2 = ff_sum_bnd2[iter] / NCELLS;
                tr_mean_bounded[iter] = mb;
                tr_var_bounded[iter] = mb2 - mb*mb > 0 ? mb2 - mb*mb : 0;
            }
        }
        free(sum_abs); free(sum_abs2); free(sum_zr); free(sum_zi);
        free(active); free(esc_cnt);
        if (ff_sum_log) free(ff_sum_log);
        if (ff_sum_log2) free(ff_sum_log2);
        if (ff_sum_bnd) free(ff_sum_bnd);
        if (ff_sum_bnd2) free(ff_sum_bnd2);
    }
    free(F_s); free(F_d);
}

/* ================================================================
 * METRICS
 * ================================================================ */
static double metric_pearson(const double *F, const double *T, int N) {
    double sf = 0, st = 0;
    for (int i = 0; i < N; i++) { sf += F[i]; st += T[i]; }
    double mf = sf / N, mt = st / N;
    double cov = 0, vf = 0, vt = 0;
    for (int i = 0; i < N; i++) {
        double df = F[i] - mf, dt = T[i] - mt;
        cov += df * dt; vf += df * df; vt += dt * dt;
    }
    double denom = sqrt(vf * vt);
    if (denom < 1e-15) return 0.5;
    double r = cov / denom;
    double p01 = (r + 1.0) / 2.0;
    if (p01 < 0) p01 = 0; if (p01 > 1) p01 = 1;
    return p01;
}

typedef struct { double val; int idx; } ValIdx;
static int cmp_validx(const void *a, const void *b) {
    double va = ((const ValIdx *)a)->val, vb = ((const ValIdx *)b)->val;
    return (va > vb) - (va < vb);
}
static void compute_ranks(const double *vals, double *ranks, int n) {
    ValIdx *vi = (ValIdx *)malloc((size_t)n * sizeof(ValIdx));
    for (int i = 0; i < n; i++) { vi[i].val = vals[i]; vi[i].idx = i; }
    qsort(vi, (size_t)n, sizeof(ValIdx), cmp_validx);
    int i = 0;
    while (i < n) {
        int j = i;
        while (j < n && vi[j].val == vi[i].val) j++;
        double avg_rank = 0.5 * ((i + 1) + j);
        for (int k = i; k < j; k++) ranks[vi[k].idx] = avg_rank;
        i = j;
    }
    free(vi);
}
static double metric_spearman(const double *F, const double *T, int N) {
    double *rf = (double *)malloc(sizeof(double) * (size_t)N);
    double *rt = (double *)malloc(sizeof(double) * (size_t)N);
    compute_ranks(F, rf, N); compute_ranks(T, rt, N);
    double sf = 0, st = 0;
    for (int i = 0; i < N; i++) { sf += rf[i]; st += rt[i]; }
    double mf = sf / N, mt = st / N;
    double cov = 0, vf = 0, vt = 0;
    for (int i = 0; i < N; i++) {
        double df = rf[i] - mf, dt = rt[i] - mt;
        cov += df * dt; vf += df * df; vt += dt * dt;
    }
    double denom = sqrt(vf * vt);
    free(rf); free(rt);
    if (denom < 1e-15) return 0.5;
    double rho = cov / denom;
    double s01 = (rho + 1.0) / 2.0;
    if (s01 < 0) s01 = 0; if (s01 > 1) s01 = 1;
    return s01;
}
static double metric_mae(const double *F, const double *T, int N) {
    double sum = 0;
    for (int i = 0; i < N; i++) sum += fabs(F[i] - T[i]);
    double m01 = 1.0 - sum / N;
    if (m01 < 0) m01 = 0; if (m01 > 1) m01 = 1;
    return m01;
}
static double metric_gradient(const double *F, const double *T, int W, int H) {
    double dot = 0, nf = 0, nt = 0;
    for (int py = 0; py < H; py++) {
        for (int px = 0; px < W; px++) {
            int idx = py * W + px;
            double gfx, gfy, gtx, gty;
            if (px > 0 && px < W - 1) gfx = F[idx + 1] - F[idx - 1];
            else if (px == 0) gfx = F[idx + 1] - F[idx];
            else gfx = F[idx] - F[idx - 1];
            if (py > 0 && py < H - 1) gfy = F[idx + W] - F[idx - W];
            else if (py == 0) gfy = F[idx + W] - F[idx];
            else gfy = F[idx] - F[idx - W];
            if (px > 0 && px < W - 1) gtx = T[idx + 1] - T[idx - 1];
            else if (px == 0) gtx = T[idx + 1] - T[idx];
            else gtx = T[idx] - T[idx - 1];
            if (py > 0 && py < H - 1) gty = T[idx + W] - T[idx - W];
            else if (py == 0) gty = T[idx + W] - T[idx];
            else gty = T[idx] - T[idx - W];
            dot += gfx * gtx + gfy * gty;
            nf  += gfx * gfx + gfy * gfy;
            nt  += gtx * gtx + gty * gty;
        }
    }
    double denom = sqrt(nf * nt);
    if (denom < 1e-15) return 0.5;
    double g01 = (dot / denom + 1.0) / 2.0;
    if (g01 < 0) g01 = 0; if (g01 > 1) g01 = 1;
    return g01;
}
static double metric_spectral(const double *F, const double *T, int W, int H) {
    int modes = W < 8 ? W : 8;
    int modes_v = H < 8 ? H : 8;
    int total = modes * modes_v;
    if (total <= 1) return 0.5;
    double *cf = (double *)calloc((size_t)total, sizeof(double));
    double *ct = (double *)calloc((size_t)total, sizeof(double));
    if (!cf || !ct) { free(cf); free(ct); return 0.5; }
    int idx = 0;
    for (int u = 0; u < modes; u++) {
        for (int v = 0; v < modes_v; v++) {
            if (u == 0 && v == 0) { idx++; continue; }
            double sf = 0, st = 0;
            for (int py = 0; py < H; py++) {
                double cv = cos(PI_VAL * v * (2 * py + 1) / (2.0 * H));
                for (int px = 0; px < W; px++) {
                    double cu = cos(PI_VAL * u * (2 * px + 1) / (2.0 * W));
                    double basis = cu * cv;
                    int cell = py * W + px;
                    sf += F[cell] * basis; st += T[cell] * basis;
                }
            }
            cf[idx] = sf; ct[idx] = st; idx++;
        }
    }
    double nfc = 0, ntc = 0, dotc = 0;
    for (int i = 0; i < total; i++) {
        nfc += cf[i] * cf[i]; ntc += ct[i] * ct[i]; dotc += cf[i] * ct[i];
    }
    free(cf); free(ct);
    double denom = sqrt(nfc * ntc);
    if (denom < 1e-15) return 0.5;
    double s01 = (dotc / denom + 1.0) / 2.0;
    if (s01 < 0) s01 = 0; if (s01 > 1) s01 = 1;
    return s01;
}
static double metric_autocorrelation(const double *F, const double *T, int W, int H) {
    int N = W * H;
    double sf = 0, st = 0;
    for (int i = 0; i < N; i++) { sf += F[i]; st += T[i]; }
    double mf = sf / N, mt = st / N;
    double vf = 0, vt = 0;
    for (int i = 0; i < N; i++) {
        vf += (F[i] - mf) * (F[i] - mf); vt += (T[i] - mt) * (T[i] - mt);
    }
    double stdf = sqrt(vf / N), stdt = sqrt(vt / N);
    if (stdf < 1e-15 || stdt < 1e-15) return 0.5;
    double af[ACORR_TOTAL], at_[ACORR_TOTAL];
    int idx = 0;
    for (int dy = -ACORR_RANGE; dy <= ACORR_RANGE; dy++) {
        for (int dx = -ACORR_RANGE; dx <= ACORR_RANGE; dx++) {
            if (dx == 0 && dy == 0) continue;
            double cf = 0, ct = 0; int count = 0;
            for (int py = 0; py < H; py++) {
                int py2 = py + dy;
                if (py2 < 0 || py2 >= H) continue;
                for (int px = 0; px < W; px++) {
                    int px2 = px + dx;
                    if (px2 < 0 || px2 >= W) continue;
                    int i1 = py * W + px, i2 = py2 * W + px2;
                    cf += ((F[i1] - mf) / stdf) * ((F[i2] - mf) / stdf);
                    ct += ((T[i1] - mt) / stdt) * ((T[i2] - mt) / stdt);
                    count++;
                }
            }
            af[idx] = count > 0 ? cf / count : 0;
            at_[idx] = count > 0 ? ct / count : 0;
            idx++;
        }
    }
    double dot = 0, nf = 0, nt = 0;
    for (int i = 0; i < ACORR_TOTAL; i++) {
        dot += af[i] * at_[i]; nf += af[i] * af[i]; nt += at_[i] * at_[i];
    }
    double denom = sqrt(nf * nt);
    if (denom < 1e-15) return 0.5;
    double a01 = (dot / denom + 1.0) / 2.0;
    if (a01 < 0) a01 = 0; if (a01 > 1) a01 = 1;
    return a01;
}
static double compute_score(double p01, double sp01, double m01,
                             double g01, double spc01, double a01) {
    return 0.25 * p01 + 0.15 * sp01 + 0.15 * m01
         + 0.15 * g01 + 0.15 * spc01 + 0.15 * a01;
}

/* ================================================================
 * DIAGNOSTICS
 * ================================================================ */
static double diagnostic_entropy(const double *F, int N) {
    int bins[ENTROPY_BINS]; memset(bins, 0, sizeof(bins));
    for (int i = 0; i < N; i++) {
        int b = (int)(F[i] * ENTROPY_BINS);
        if (b < 0) b = 0; if (b >= ENTROPY_BINS) b = ENTROPY_BINS - 1;
        bins[b]++;
    }
    double H = 0;
    for (int i = 0; i < ENTROPY_BINS; i++)
        if (bins[i] > 0) { double p = (double)bins[i] / N; H -= p * log(p); }
    return H / log((double)ENTROPY_BINS);
}
static double diagnostic_anisotropy(const double *F, int W, int H) {
    int N = W * H;
    double sf = 0; for (int i = 0; i < N; i++) sf += F[i];
    double mf = sf / N;
    double vf = 0; for (int i = 0; i < N; i++) vf += (F[i] - mf) * (F[i] - mf);
    vf /= N; if (vf < 1e-15) return 0;
    double corr_h = 0, corr_v = 0, corr_d1 = 0, corr_d2 = 0;
    int nh = 0, nv = 0, nd = 0;
    for (int py = 0; py < H; py++) {
        for (int px = 0; px < W; px++) {
            int idx = py * W + px; double v0 = F[idx] - mf;
            if (px + 1 < W) { corr_h += v0 * (F[idx+1] - mf); nh++; }
            if (py + 1 < H) { corr_v += v0 * (F[idx+W] - mf); nv++; }
            if (px + 1 < W && py + 1 < H) { corr_d1 += v0 * (F[idx+W+1] - mf); nd++; }
            if (px > 0 && py + 1 < H) { corr_d2 += v0 * (F[idx+W-1] - mf); nd++; }
        }
    }
    if (nh > 0) corr_h /= (nh * vf);
    if (nv > 0) corr_v /= (nv * vf);
    double corr_d = 0;
    if (nd > 0) corr_d = (corr_d1 + corr_d2) / (nd * vf);
    double max_dir = corr_h;
    if (fabs(corr_v) > fabs(max_dir)) max_dir = corr_v;
    if (fabs(corr_d) > fabs(max_dir)) max_dir = corr_d;
    double mean_dir = (fabs(corr_h) + fabs(corr_v) + fabs(corr_d)) / 3.0;
    double range = fabs(max_dir) - mean_dir;
    if (range < 0) range = 0; if (range > 1) range = 1;
    return range;
}
static void diagnostic_quantization(const double *F_disc, int N, int *n_levels, double *dom_frac) {
    int *level_map = (int *)calloc((size_t)N, sizeof(int));
    int *counts = (int *)calloc((size_t)N, sizeof(int));
    if (!level_map || !counts) { free(level_map); free(counts); *n_levels = 0; *dom_frac = 0; return; }
    int n_distinct = 0, max_count = 0;
    for (int i = 0; i < N; i++) {
        int key = (int)(F_disc[i] * 100000 + 0.5);
        int found = -1;
        for (int j = 0; j < n_distinct; j++) if (level_map[j] == key) { found = j; break; }
        if (found < 0) { level_map[n_distinct] = key; found = n_distinct++; }
        counts[found]++;
        if (counts[found] > max_count) max_count = counts[found];
    }
    *n_levels = n_distinct;
    *dom_frac = n_distinct > 0 ? (double)max_count / N : 0;
    free(level_map); free(counts);
}
static double diagnostic_compression_estimate(const double *F, int N) {
    char *buf = (char *)malloc((size_t)(N + 1));
    if (!buf) return 1.0;
    for (int i = 0; i < N; i++) {
        int level = (int)(F[i] * ASCII_PAL_LEN);
        if (level >= ASCII_PAL_LEN) level = ASCII_PAL_LEN - 1;
        if (level < 0) level = 0;
        buf[i] = ASCII_PALETTE[level];
    }
    buf[N] = '\0';
    int runs = 1;
    for (int i = 1; i < N; i++) if (buf[i] != buf[i-1]) runs++;
    double ratio = (double)(runs * 2) / (double)N;
    if (ratio > 1.0) ratio = 1.0;
    free(buf);
    return ratio;
}

/* ================================================================
 * INPUT VALIDATION
 * ================================================================ */
static int parse_double_strict(const char *s, double *out) {
    if (!s || !*s) return 0;
    char *end = NULL;
    errno = 0;
    double v = strtod(s, &end);
    if (errno != 0 || end == s || *end != '\0') return 0;
    if (!isfinite(v)) return 0;
    *out = v;
    return 1;
}
static int parse_int_strict(const char *s, int *out) {
    if (!s || !*s) return 0;
    char *end = NULL;
    errno = 0;
    long v = strtol(s, &end, 10);
    if (errno != 0 || end == s || *end != '\0') return 0;
    *out = (int)v;
    return 1;
}

/* ================================================================
 * JSON HELPERS
 * ================================================================ */
static void json_double_array(FILE *f, const char *key, const double *arr, int n) {
    fprintf(f, "\"%s\":[", key);
    for (int i = 0; i < n; i++) {
        if (i > 0) fprintf(f, ",");
        if (isfinite(arr[i])) fprintf(f, "%.17g", arr[i]);
        else fprintf(f, "null");
    }
    fprintf(f, "]");
}
static void json_metrics_block(FILE *f, double score, double p01, double sp01,
                                double m01, double g01, double spc01, double a01,
                                double entropy, double aniso, double compr,
                                int ql, double df, double esc, double ms, int err) {
    fprintf(f, "\"score\":%.17g,\"pearson01\":%.17g,\"spearman01\":%.17g,"
               "\"mae01\":%.17g,\"gradient01\":%.17g,\"spectral01\":%.17g,"
               "\"autocorrelation01\":%.17g,\"entropy\":%.17g,\"anisotropy\":%.17g,"
               "\"compression_ratio\":%.17g,\"quantization_levels\":%d,"
               "\"quantization_dom_frac\":%.17g,\"escaped_fraction\":%.17g,"
               "\"runtime_ms\":%.1f,\"error_code\":%d",
            score, p01, sp01, m01, g01, spc01, a01, entropy, aniso, compr,
            ql, df, esc, ms, err);
}

/* ================================================================
 * SELF-TEST
 * ================================================================ */
static int self_test(void) {
    int pass = 1;
    int N = 60 * 30;
    sieve_build(1100);
    if (pi_func(10) != 4)  { printf("FAIL: pi(10) = %d, expected 4\n", pi_func(10)); pass = 0; }
    if (pi_func(100) != 25) { printf("FAIL: pi(100) = %d, expected 25\n", pi_func(100)); pass = 0; }
    if (pi_func(1000) != 168) { printf("FAIL: pi(1000) = %d, expected 168\n", pi_func(1000)); pass = 0; }
    for (int k = 1; k < 100; k++) {
        if (pi_func(k+1) < pi_func(k)) { printf("FAIL: pi monotonicity at %d\n", k); pass = 0; break; }
        int d = pi_func(k+1) - pi_func(k);
        if (d != 0 && d != 1) { printf("FAIL: pi step at %d = %d\n", k, d); pass = 0; break; }
    }
    double r, i_;
    complex_sq(1.0, 1.0, &r, &i_);
    if (fabs(r) > 1e-10 || fabs(i_ - 2.0) > 1e-10) { printf("FAIL: complex_sq\n"); pass = 0; }
    complex_cub(1.0, 1.0, &r, &i_);
    if (fabs(r - (-2.0)) > 1e-10 || fabs(i_ - 2.0) > 1e-10) { printf("FAIL: complex_cub\n"); pass = 0; }
    /* Heap-allocated buffers (MAX_CELLS too large for stack) */
    double *T = (double *)malloc(sizeof(double) * (size_t)N);
    double *F = (double *)malloc(sizeof(double) * (size_t)N);
    double *d1 = (double *)malloc(sizeof(double) * (size_t)N);
    double *d2 = (double *)malloc(sizeof(double) * (size_t)N);
    double *drv = (double *)calloc((size_t)201, sizeof(double));
    if (!T || !F || !d1 || !d2 || !drv) { printf("FAIL: self_test OOM\n"); pass = 0; }
    else {
        compute_target(T, TGT_A, 60, 30, 1, 1);
        for (int j = 0; j < N; j++) {
            if (T[j] < -0.01 || T[j] > 1.01) { printf("FAIL: target range\n"); pass = 0; break; }
        }
        for (int j = 0; j < N; j++) F[j] = T[j];
        double p01 = metric_pearson(F, T, N);
        double m01 = metric_mae(F, T, N);
        if (p01 < 0.99) { printf("FAIL: pearson self-match = %f\n", p01); pass = 0; }
        if (m01 < 0.99) { printf("FAIL: mae self-match = %f\n", m01); pass = 0; }
        sieve_build(210);
        compute_driver(drv, DRV_V1_INV_PI, 200, 7331, 5);
        iterate_julia(-0.7, 0.27015, drv, 1.0, 2, 0, 200, 60, 30, d1, NULL, NULL, NULL,NULL,NULL,NULL,NULL,NULL, NULL, NULL, 0, NULL,NULL,NULL,NULL, 0);
        iterate_julia(-0.7, 0.27015, drv, 1.0, 2, 0, 200, 60, 30, d2, NULL, NULL, NULL,NULL,NULL,NULL,NULL,NULL, NULL, NULL, 0, NULL,NULL,NULL,NULL, 0);
        double max_diff = 0;
        for (int j = 0; j < N; j++) { double d = fabs(d1[j] - d2[j]); if (d > max_diff) max_diff = d; }
        if (max_diff > 1e-15) { printf("FAIL: determinism, max_diff=%e\n", max_diff); pass = 0; }
    }
    /* V9 event check */
    {
        double P[11]; P[0] = 1.0;
        for (int k = 1; k <= 10; k++) { int pk = pi_func(k); if (pk < 1) pk = 1; P[k] = 1.0 / (double)pk; }
        double E[11];
        for (int k = 1; k <= 10; k++) E[k] = P[k] - P[k-1];
        if (fabs(E[2]) > 1e-15) { printf("FAIL: E(2) should be 0, got %g\n", E[2]); pass = 0; }
        if (fabs(E[3]) < 1e-15) { printf("FAIL: E(3) should be nonzero\n"); pass = 0; }
    }
    free(T); free(F); free(d1); free(d2); free(drv);
    if (pass) printf("ALL SELF-TESTS PASSED\n");
    else      printf("SOME SELF-TESTS FAILED\n");
    return pass;
}

/* ================================================================
 * ASCII RENDER
 * ================================================================ */
static void render_ascii(const double *F, int W, int H, FILE *out) {
    for (int py = 0; py < H; py++) {
        for (int px = 0; px < W; px++) {
            int idx = py * W + px;
            int level = (int)(F[idx] * ASCII_PAL_LEN);
            if (level >= ASCII_PAL_LEN) level = ASCII_PAL_LEN - 1;
            if (level < 0) level = 0;
            fputc(ASCII_PALETTE[level], out);
        }
        fputc('\n', out);
    }
}

/* ================================================================
 * COMPUTE ALL METRICS (helper)
 * ================================================================ */
typedef struct {
    double score, pearson01, spearman01, mae01, gradient01, spectral01, autocorrelation01;
    double entropy, anisotropy, compression_ratio;
    int quantization_levels; double quantization_dom_frac;
    double escaped_fraction; double runtime_ms; int error_code;
} Metrics;

static void compute_all_metrics(Metrics *m, const double *F_smooth, const double *F_discrete,
                                const double *target, int W, int H, double esc_frac, double ms) {
    int N = W * H;
    m->pearson01 = metric_pearson(F_smooth, target, N);
    m->spearman01 = metric_spearman(F_smooth, target, N);
    m->mae01 = metric_mae(F_smooth, target, N);
    m->gradient01 = metric_gradient(F_smooth, target, W, H);
    m->spectral01 = metric_spectral(F_smooth, target, W, H);
    m->autocorrelation01 = metric_autocorrelation(F_smooth, target, W, H);
    m->score = compute_score(m->pearson01, m->spearman01, m->mae01,
                             m->gradient01, m->spectral01, m->autocorrelation01);
    m->entropy = diagnostic_entropy(F_smooth, N);
    m->anisotropy = diagnostic_anisotropy(F_smooth, W, H);
    m->compression_ratio = diagnostic_compression_estimate(F_smooth, N);
    diagnostic_quantization(F_discrete, N, &m->quantization_levels, &m->quantization_dom_frac);
    m->escaped_fraction = esc_frac;
    m->runtime_ms = ms;
    m->error_code = 0;
}

/* ================================================================
 * BATCH MODE
 * ================================================================ */
typedef struct {
    int candidate_id; double cr, ci;
    DriverID driver; double alpha; int degree, channel, max_iter; uint64_t seed;
} Candidate;

static void process_batch(int W, int H, TargetID tgt_id, int pn, int pm,
                          const char *tgt_file, int window, int offset,
                          const char *drv_file) {
    char line[MAX_LINE];
    Candidate *cands = NULL; int ncand = 0, cap = 0;

    while (fgets(line, sizeof(line), stdin) && line[0] != '\0') {
        /* Skip blank lines */
        { int blank = 1; for (char *p = line; *p; p++) if (!isspace((unsigned char)*p)) { blank = 0; break; }
          if (blank) continue; }
        if (ncand >= cap) {
            cap = cap == 0 ? 1024 : cap * 2;
            cands = (Candidate *)realloc(cands, (size_t)cap * sizeof(Candidate));
            if (!cands) { fprintf(stderr, "batch: OOM\n"); exit(1); }
        }
        char drv_str[64], model_str[64];
        unsigned long long seed_ll;
        int n = sscanf(line, "%d %lf %lf %63s %63s %lf %d %d %d %llu",
                       &cands[ncand].candidate_id,
                       &cands[ncand].cr, &cands[ncand].ci,
                       model_str, drv_str,
                       &cands[ncand].alpha, &cands[ncand].degree,
                       &cands[ncand].channel, &cands[ncand].max_iter,
                       &seed_ll);
        if (n < 10) { fprintf(stderr, "batch: malformed line %d\n", ncand + 1); continue; }
        if (!driver_from_string(drv_str, &cands[ncand].driver)) {
            fprintf(stderr, "batch: unknown driver '%s' at line %d\n", drv_str, ncand + 1);
            free(cands); exit(1);
        }
        cands[ncand].seed = (uint64_t)seed_ll;
        /* Check duplicate IDs */
        for (int j = 0; j < ncand; j++) {
            if (cands[j].candidate_id == cands[ncand].candidate_id) {
                fprintf(stderr, "batch: duplicate candidate_id %d\n", cands[ncand].candidate_id);
                free(cands); exit(1);
            }
        }
        ncand++;
    }
    if (ncand == 0) { free(cands); return; }

    int max_mi = 0;
    for (int i = 0; i < ncand; i++) if (cands[i].max_iter > max_mi) max_mi = cands[i].max_iter;
    sieve_build(max_mi + 10);

    /* V3: optional externally supplied forcing sequence shared by all candidates */
    double *ext_drv = NULL;
    if (drv_file) {
        ext_drv = (double *)calloc((size_t)(max_mi + 1), sizeof(double));
        if (!ext_drv) { fprintf(stderr, "batch: OOM\n"); free(cands); exit(1); }
        if (!load_driver_file(drv_file, ext_drv, max_mi)) { free(cands); free(ext_drv); exit(1); }
    }

    int N = W * H;
    double *target = (double *)malloc(sizeof(double) * (size_t)N);
    if (!target) { fprintf(stderr, "batch: OOM\n"); free(cands); exit(1); }
    if (tgt_file) {
        FILE *tf = fopen(tgt_file, "r");
        if (!tf) { fprintf(stderr, "batch: cannot open target file\n"); free(cands); free(target); exit(1); }
        for (int i = 0; i < N; i++) { if (fscanf(tf, "%lf", &target[i]) != 1) { fprintf(stderr, "batch: short target file\n"); fclose(tf); free(cands); free(target); exit(1); } }
        fclose(tf);
    } else {
        compute_target(target, tgt_id, W, H, pn, pm);
    }

    for (int i = 0; i < ncand; i++) {
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        Metrics res; memset(&res, 0, sizeof(res));
        res.error_code = 0;
        int mi = cands[i].max_iter;
        if (mi < 1) mi = 1; if (mi >= MAX_DRIVER_LEN) mi = MAX_DRIVER_LEN - 1;
        double *drv = (double *)calloc((size_t)(mi + 1), sizeof(double));
        if (!drv) { fprintf(stderr, "batch: OOM\n"); free(cands); free(target); exit(1); }
        compute_driver(drv, cands[i].driver, mi, cands[i].seed, window);
        if (ext_drv) for (int k = 1; k <= mi; k++) drv[k] = ext_drv[k];
        double *F_smooth = (double *)malloc(sizeof(double) * (size_t)N);
        double *F_discrete = (double *)malloc(sizeof(double) * (size_t)N);
        double esc_frac = 0;
        if (!F_smooth || !F_discrete) { fprintf(stderr, "batch: OOM\n"); exit(1); }
        iterate_julia(cands[i].cr, cands[i].ci, drv,
                      cands[i].alpha, cands[i].degree, cands[i].channel,
                      mi, W, H, F_smooth, F_discrete, &esc_frac,
                      NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0,
                      NULL, NULL, NULL, NULL, 0);
        int has_nan = 0;
        for (int j = 0; j < N; j++) if (!isfinite(F_smooth[j])) { has_nan = 1; break; }
        if (has_nan) { res.error_code = 1; res.score = 0; }
        else compute_all_metrics(&res, F_smooth, F_discrete, target, W, H, esc_frac, 0);
        clock_gettime(CLOCK_MONOTONIC, &t1);
        res.runtime_ms = (t1.tv_sec - t0.tv_sec) * 1000.0 + (t1.tv_nsec - t0.tv_nsec) / 1e6;
        printf("%d\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g"
               "\t%.17g\t%.17g\t%.17g\t%d\t%.17g\t%.17g\t%.1f\t%d\n",
               cands[i].candidate_id, res.score,
               res.pearson01, res.spearman01, res.mae01,
               res.gradient01, res.spectral01, res.autocorrelation01,
               res.entropy, res.anisotropy, res.compression_ratio,
               res.quantization_levels, res.quantization_dom_frac,
               res.escaped_fraction, res.runtime_ms, res.error_code);
        fflush(stdout);
        free(drv); free(F_smooth); free(F_discrete);
    }
    free(cands); free(target);
    free(ext_drv);
}

/* ================================================================
 * EVALUATE MODE (JSON output with fields)
 * ================================================================ */
static void run_evaluate(double cr, double ci, const char *drv_name_str,
                          double alpha, int degree, int channel, int max_iter,
                          uint64_t seed, int W, int H,
                          TargetID tgt_id, int pn, int pm,
                          const char *tgt_file, int window, int offset,
                          const char *drv_file) {
    sieve_build(max_iter + 10);
    DriverID did = DRV_V0_NONE;
    if (!drv_file && !driver_from_string(drv_name_str, &did)) {
        printf("{\"error\":\"unknown driver '%s'\"}\n", drv_name_str); return;
    }
    int N = W * H;
    double *drv = (double *)calloc((size_t)(max_iter + 1), sizeof(double));
    double *target = (double *)malloc(sizeof(double) * (size_t)N);
    double *F_smooth = (double *)malloc(sizeof(double) * (size_t)N);
    double *F_discrete = (double *)malloc(sizeof(double) * (size_t)N);
    if (!drv || !target || !F_smooth || !F_discrete) { fprintf(stderr, "evaluate: OOM\n"); exit(1); }
    if (drv_file) {
        if (!load_driver_file(drv_file, drv, max_iter)) { exit(1); }
    } else {
        compute_driver(drv, did, max_iter, seed, window);
    }
    if (tgt_file) {
        FILE *tf = fopen(tgt_file, "r");
        if (!tf) { fprintf(stderr, "evaluate: cannot open target file\n"); exit(1); }
        for (int i = 0; i < N; i++) if (fscanf(tf, "%lf", &target[i]) != 1) { fprintf(stderr, "evaluate: short target\n"); fclose(tf); exit(1); }
        fclose(tf);
    } else compute_target(target, tgt_id, W, H, pn, pm);

    double esc_frac = 0;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    iterate_julia(cr, ci, drv, alpha, degree, channel, max_iter, W, H,
                  F_smooth, F_discrete, &esc_frac,
                  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0,
                  NULL, NULL, NULL, NULL, 0);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double ms = (t1.tv_sec - t0.tv_sec) * 1000.0 + (t1.tv_nsec - t0.tv_nsec) / 1e6;

    int has_nan = 0;
    for (int i = 0; i < N; i++) if (!isfinite(F_smooth[i])) { has_nan = 1; break; }

    printf("{");
    if (has_nan) {
        printf("\"error_code\":1,\"score\":0");
    } else {
        Metrics m; memset(&m, 0, sizeof(m));
        compute_all_metrics(&m, F_smooth, F_discrete, target, W, H, esc_frac, ms);
        json_metrics_block(stdout, m.score, m.pearson01, m.spearman01, m.mae01,
                           m.gradient01, m.spectral01, m.autocorrelation01,
                           m.entropy, m.anisotropy, m.compression_ratio,
                           m.quantization_levels, m.quantization_dom_frac,
                           m.escaped_fraction, m.runtime_ms, 0);
    }
    if (drv_file)
        printf(",\"driver\":\"%s\",\"driver_file\":\"%s\"", "EXTERNAL_DRIVER_FILE", drv_file);
    else
        printf(",\"driver\":\"%s\"", driver_name(did));
    printf(",\"width\":%d,\"height\":%d", W, H);
    printf(","); json_double_array(stdout, "field", F_smooth, N);
    printf(","); json_double_array(stdout, "discrete", F_discrete, N);
    printf(","); json_double_array(stdout, "target", target, N);
    printf("}\n");

    free(drv); free(target); free(F_smooth); free(F_discrete);
}

/* ================================================================
 * RENDER MODE
 * ================================================================ */
static void run_render(double cr, double ci, const char *drv_name_str,
                        double alpha, int degree, int channel, int max_iter,
                        uint64_t seed, int W, int H,
                        TargetID tgt_id, int pn, int pm,
                        const char *tgt_file, int window, int offset) {
    sieve_build(max_iter + 10);
    DriverID did;
    if (!driver_from_string(drv_name_str, &did)) {
        fprintf(stderr, "render: unknown driver '%s'\n", drv_name_str); return;
    }
    int N = W * H;
    double *drv = (double *)calloc((size_t)(max_iter + 1), sizeof(double));
    double *F_smooth = (double *)malloc(sizeof(double) * (size_t)N);
    double *F_discrete = (double *)malloc(sizeof(double) * (size_t)N);
    double *target = (double *)malloc(sizeof(double) * (size_t)N);
    if (!drv || !F_smooth || !F_discrete || !target) { fprintf(stderr, "render: OOM\n"); exit(1); }
    compute_driver(drv, did, max_iter, seed, window);
    double esc_frac = 0;
    iterate_julia(cr, ci, drv, alpha, degree, channel, max_iter, W, H,
                  F_smooth, F_discrete, &esc_frac,
                  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0,
                  NULL, NULL, NULL, NULL, 0);
    render_ascii(F_smooth, W, H, stdout);
    if (tgt_file) {
        FILE *tf = fopen(tgt_file, "r");
        if (!tf) { fprintf(stderr, "render: cannot open target file\n"); exit(1); }
        for (int i = 0; i < N; i++) if (fscanf(tf, "%lf", &target[i]) != 1) { fclose(tf); exit(1); }
        fclose(tf);
    } else compute_target(target, tgt_id, W, H, pn, pm);
    double p01 = metric_pearson(F_smooth, target, N);
    double score = compute_score(p01, metric_spearman(F_smooth, target, N),
                                  metric_mae(F_smooth, target, N),
                                  metric_gradient(F_smooth, target, W, H),
                                  metric_spectral(F_smooth, target, W, H),
                                  metric_autocorrelation(F_smooth, target, W, H));
    printf("\nScore: %.17g  Pearson01: %.17g\n", score, p01);
    free(drv); free(F_smooth); free(F_discrete); free(target);
}

/* ================================================================
 * TRACE MODE
 * ================================================================ */
static void run_trace(double cr, double ci, const char *drv_name_str,
                       double alpha, int degree, int channel, int max_iter,
                       uint64_t seed, int W, int H, int window, int offset,
                       const char *drv_file, int temporal_fullfield) {
    sieve_build(max_iter + 10);
    DriverID did = DRV_V0_NONE;
    if (!drv_file && !driver_from_string(drv_name_str, &did)) {
        fprintf(stderr, "trace: unknown driver '%s'\n", drv_name_str); return;
    }
    double *drv = (double *)calloc((size_t)(max_iter + 1), sizeof(double));
    double *F_smooth = (double *)malloc(sizeof(double) * (size_t)(W*H));
    double *F_discrete = (double *)malloc(sizeof(double) * (size_t)(W*H));
    double esc_frac;
    double *tr_active = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_mean_abs = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_std_abs = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_mean_zr = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_mean_zi = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_esc_frac = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_driver = (double *)calloc((size_t)max_iter, sizeof(double));
    int *tr_prime = (int *)calloc((size_t)max_iter, sizeof(int));
    /* V4 full-field temporal arrays (§41) */
    double *tr_mean_log_r = temporal_fullfield ? (double *)calloc((size_t)max_iter, sizeof(double)) : NULL;
    double *tr_std_log_r  = temporal_fullfield ? (double *)calloc((size_t)max_iter, sizeof(double)) : NULL;
    double *tr_mean_bnd   = temporal_fullfield ? (double *)calloc((size_t)max_iter, sizeof(double)) : NULL;
    double *tr_var_bnd    = temporal_fullfield ? (double *)calloc((size_t)max_iter, sizeof(double)) : NULL;
    if (!drv||!F_smooth||!F_discrete||!tr_active||!tr_mean_abs||!tr_std_abs||
        !tr_mean_zr||!tr_mean_zi||!tr_esc_frac||!tr_driver||!tr_prime) {
        fprintf(stderr, "trace: OOM\n"); exit(1);
    }
    if (temporal_fullfield && (!tr_mean_log_r||!tr_std_log_r||!tr_mean_bnd||!tr_var_bnd)) {
        fprintf(stderr, "trace: OOM (temporal)\n"); exit(1);
    }
    compute_driver(drv, did, max_iter, seed, window);
    if (drv_file) {
        if (!load_driver_file(drv_file, drv, max_iter)) { exit(1); }
    }
    iterate_julia(cr, ci, drv, alpha, degree, channel, max_iter, W, H,
                  F_smooth, F_discrete, &esc_frac,
                  tr_active, tr_mean_abs, tr_std_abs, tr_mean_zr, tr_mean_zi,
                  tr_esc_frac, tr_driver, tr_prime, 1,
                  tr_mean_log_r, tr_std_log_r, tr_mean_bnd, tr_var_bnd,
                  temporal_fullfield);
    if (temporal_fullfield) {
        printf("iter\tactive_frac\tmean_log_radius\tstd_log_radius\tmean_bounded_radius\tvar_bounded_radius\tesc_frac\tdriver\tprime\n");
        for (int k = 0; k < max_iter; k++) {
            printf("%d\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%d\n",
                   k + 1, tr_active[k], tr_mean_log_r[k], tr_std_log_r[k],
                   tr_mean_bnd[k], tr_var_bnd[k], tr_esc_frac[k],
                   tr_driver[k], tr_prime[k]);
        }
    } else {
        printf("iter\tactive_frac\tmean_abs_z\tstd_abs_z\tmean_zr\tmean_zi\tesc_frac\tdriver\tprime\n");
        for (int k = 0; k < max_iter; k++) {
            printf("%d\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%.17g\t%d\n",
                   k + 1, tr_active[k], tr_mean_abs[k], tr_std_abs[k],
                   tr_mean_zr[k], tr_mean_zi[k], tr_esc_frac[k],
                   tr_driver[k], tr_prime[k]);
        }
    }
    free(drv); free(F_smooth); free(F_discrete);
    free(tr_active); free(tr_mean_abs); free(tr_std_abs);
    free(tr_mean_zr); free(tr_mean_zi); free(tr_esc_frac);
    free(tr_driver); free(tr_prime);
    if (tr_mean_log_r) free(tr_mean_log_r);
    if (tr_std_log_r) free(tr_std_log_r);
    if (tr_mean_bnd) free(tr_mean_bnd);
    if (tr_var_bnd) free(tr_var_bnd);
}

/* ================================================================
 * TARGET-FIELD MODE
 * ================================================================ */
static void run_target_field(TargetID tid, int pn, int pm, int W, int H) {
    int N = W * H;
    double *T = (double *)malloc(sizeof(double) * (size_t)N);
    if (!T) { fprintf(stderr, "target-field: OOM\n"); exit(1); }
    compute_target(T, tid, W, H, pn, pm);
    printf("[");
    for (int i = 0; i < N; i++) {
        if (i > 0) printf(",");
        printf("%.17g", T[i]);
    }
    printf("]\n");
    free(T);
}

/* ================================================================
 * SCORE-FIELDS MODE
 * ================================================================ */
static void run_score_fields(int W, int H) {
    int N = W * H;
    double *F = (double *)malloc(sizeof(double) * (size_t)N);
    double *T = (double *)malloc(sizeof(double) * (size_t)N);
    if (!F || !T) { fprintf(stderr, "score-fields: OOM\n"); exit(1); }
    for (int i = 0; i < N; i++) {
        if (scanf("%lf", &F[i]) != 1) { fprintf(stderr, "score-fields: short F\n"); exit(1); }
    }
    for (int i = 0; i < N; i++) {
        if (scanf("%lf", &T[i]) != 1) { fprintf(stderr, "score-fields: short T\n"); exit(1); }
    }
    double p01 = metric_pearson(F, T, N);
    double sp01 = metric_spearman(F, T, N);
    double m01 = metric_mae(F, T, N);
    double g01 = metric_gradient(F, T, W, H);
    double spc01 = metric_spectral(F, T, W, H);
    double a01 = metric_autocorrelation(F, T, W, H);
    double sc = compute_score(p01, sp01, m01, g01, spc01, a01);
    printf("{\"score\":%.17g,\"pearson01\":%.17g,\"spearman01\":%.17g,"
           "\"mae01\":%.17g,\"gradient01\":%.17g,\"spectral01\":%.17g,"
           "\"autocorrelation01\":%.17g}\n",
           sc, p01, sp01, m01, g01, spc01, a01);
    free(F); free(T);
}

/* ================================================================
 * DRIVER-VALUES MODE
 * ================================================================ */
static void run_driver_values(const char *drv_name_str, int max_iter,
                               uint64_t seed, int window, int offset) {
    sieve_build(max_iter + 10);
    DriverID did;
    if (!driver_from_string(drv_name_str, &did)) {
        printf("{\"error\":\"unknown driver '%s'\"}\n", drv_name_str); return;
    }
    double *drv = (double *)calloc((size_t)(max_iter + 1), sizeof(double));
    int *pi_arr = (int *)malloc(sizeof(int) * (size_t)(max_iter + 1));
    if (!drv || !pi_arr) { fprintf(stderr, "driver-values: OOM\n"); exit(1); }
    compute_driver(drv, did, max_iter, seed, window);
    for (int k = 1; k <= max_iter; k++) pi_arr[k] = pi_func(k);
    printf("{\"driver\":\"%s\",", driver_name(did));
    printf("\"values\":[");
    for (int k = 1; k <= max_iter; k++) {
        if (k > 1) printf(",");
        printf("%.17g", drv[k]);
    }
    printf("],\"pi\":[");
    for (int k = 1; k <= max_iter; k++) {
        if (k > 1) printf(",");
        printf("%d", pi_arr[k]);
    }
    printf("]}\n");
    free(drv); free(pi_arr);
}

/* ================================================================
 * MAIN
 * ================================================================ */
int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: kernel_v2 [--version|--self-test|--batch|--render|--trace|--evaluate|--target-field|--score-fields|--driver-values] [options]\n");
        return 1;
    }
    if (!strcmp(argv[1], "--version")) {
        printf("PROOF OF SIMULATION kernel %s\n", KERNEL_VERSION);
        return 0;
    }
    if (!strcmp(argv[1], "--self-test")) return self_test() ? 0 : 1;

    /* Common defaults */
    int W = 60, H = 30, window = 5, offset = 1;
    TargetID tgt_id = TGT_A; int pn = 1, pm = 1;
    const char *tgt_file = NULL;

    if (!strcmp(argv[1], "--batch")) {
        /* Parse common flags after --batch */
        const char *batch_drv_file = NULL;
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--width") && i+1 < argc) { if (!parse_int_strict(argv[++i], &W)) { fprintf(stderr, "bad --width\n"); return 1; } }
            else if (!strcmp(argv[i], "--height") && i+1 < argc) { if (!parse_int_strict(argv[++i], &H)) { fprintf(stderr, "bad --height\n"); return 1; } }
            else if (!strcmp(argv[i], "--target") && i+1 < argc) { if (!target_from_string(argv[++i], &tgt_id, &pn, &pm)) { fprintf(stderr, "bad --target\n"); return 1; } }
            else if (!strcmp(argv[i], "--target-file") && i+1 < argc) tgt_file = argv[++i];
            else if (!strcmp(argv[i], "--driver-file") && i+1 < argc) batch_drv_file = argv[++i];
            else if (!strcmp(argv[i], "--window") && i+1 < argc) { if (!parse_int_strict(argv[++i], &window)) { fprintf(stderr, "bad --window\n"); return 1; } }
            else if (!strcmp(argv[i], "--offset") && i+1 < argc) { if (!parse_int_strict(argv[++i], &offset)) { fprintf(stderr, "bad --offset\n"); return 1; } }
            else { fprintf(stderr, "batch: unknown flag '%s'\n", argv[i]); return 1; }
        }
        if (W < 2 || W > MAX_W || H < 2 || H > MAX_H) { fprintf(stderr, "batch: grid out of range\n"); return 1; }
        process_batch(W, H, tgt_id, pn, pm, tgt_file, window, offset, batch_drv_file);
        return 0;
    }

    /* Modes with cr/ci/driver/alpha/degree/channel/max-iter/seed */
    if (!strcmp(argv[1], "--evaluate") || !strcmp(argv[1], "--render") || !strcmp(argv[1], "--trace")) {
        double cr = -0.7, ci = 0.27015, alpha = 1.0;
        int degree = 2, channel = 0, max_iter = 200;
        uint64_t seed = 7331;
        const char *drv = "V1_INV_PI";
        const char *drv_file = NULL;
        int temporal_fullfield = 0;
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--cr") && i+1 < argc) { if (!parse_double_strict(argv[++i], &cr)) { fprintf(stderr, "bad --cr\n"); return 1; } }
            else if (!strcmp(argv[i], "--ci") && i+1 < argc) { if (!parse_double_strict(argv[++i], &ci)) { fprintf(stderr, "bad --ci\n"); return 1; } }
            else if (!strcmp(argv[i], "--driver") && i+1 < argc) drv = argv[++i];
            else if (!strcmp(argv[i], "--driver-file") && i+1 < argc) drv_file = argv[++i];
            else if (!strcmp(argv[i], "--alpha") && i+1 < argc) { if (!parse_double_strict(argv[++i], &alpha)) { fprintf(stderr, "bad --alpha\n"); return 1; } }
            else if (!strcmp(argv[i], "--degree") && i+1 < argc) { if (!parse_int_strict(argv[++i], &degree)) { fprintf(stderr, "bad --degree\n"); return 1; } }
            else if (!strcmp(argv[i], "--channel") && i+1 < argc) { if (!parse_int_strict(argv[++i], &channel)) { fprintf(stderr, "bad --channel\n"); return 1; } }
            else if (!strcmp(argv[i], "--max-iter") && i+1 < argc) { if (!parse_int_strict(argv[++i], &max_iter)) { fprintf(stderr, "bad --max-iter\n"); return 1; } }
            else if (!strcmp(argv[i], "--seed") && i+1 < argc) { if (!parse_int_strict(argv[++i], (int*)&seed)) { fprintf(stderr, "bad --seed\n"); return 1; } }
            else if (!strcmp(argv[i], "--width") && i+1 < argc) { if (!parse_int_strict(argv[++i], &W)) { fprintf(stderr, "bad --width\n"); return 1; } }
            else if (!strcmp(argv[i], "--height") && i+1 < argc) { if (!parse_int_strict(argv[++i], &H)) { fprintf(stderr, "bad --height\n"); return 1; } }
            else if (!strcmp(argv[i], "--target") && i+1 < argc) { if (!target_from_string(argv[++i], &tgt_id, &pn, &pm)) { fprintf(stderr, "bad --target\n"); return 1; } }
            else if (!strcmp(argv[i], "--target-file") && i+1 < argc) tgt_file = argv[++i];
            else if (!strcmp(argv[i], "--window") && i+1 < argc) { if (!parse_int_strict(argv[++i], &window)) { fprintf(stderr, "bad --window\n"); return 1; } }
            else if (!strcmp(argv[i], "--offset") && i+1 < argc) { if (!parse_int_strict(argv[++i], &offset)) { fprintf(stderr, "bad --offset\n"); return 1; } }
            else if (!strcmp(argv[i], "--temporal-fullfield")) temporal_fullfield = 1;
            else { fprintf(stderr, "%s: unknown flag '%s'\n", argv[1], argv[i]); return 1; }
        }
        if (W < 2 || W > MAX_W || H < 2 || H > MAX_H) { fprintf(stderr, "grid out of range\n"); return 1; }
        if (max_iter < 1 || max_iter > 20000) { fprintf(stderr, "max-iter out of range\n"); return 1; }
        if (degree != 2 && degree != 3) { fprintf(stderr, "degree must be 2 or 3\n"); return 1; }
        if (channel != 0 && channel != 1) { fprintf(stderr, "channel must be 0 or 1\n"); return 1; }
        /* V7 always uses imaginary channel */
        DriverID test_did;
        if (driver_from_string(drv, &test_did) && test_did == DRV_V7_IMAGINARY) channel = 1;

        if (!strcmp(argv[1], "--evaluate"))
            run_evaluate(cr, ci, drv, alpha, degree, channel, max_iter, seed, W, H, tgt_id, pn, pm, tgt_file, window, offset, drv_file);
        else if (!strcmp(argv[1], "--render"))
            run_render(cr, ci, drv, alpha, degree, channel, max_iter, seed, W, H, tgt_id, pn, pm, tgt_file, window, offset);
        else
            run_trace(cr, ci, drv, alpha, degree, channel, max_iter, seed, W, H, window, offset, drv_file, temporal_fullfield);
        return 0;
    }

    if (!strcmp(argv[1], "--target-field")) {
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--target") && i+1 < argc) { if (!target_from_string(argv[++i], &tgt_id, &pn, &pm)) { fprintf(stderr, "bad --target\n"); return 1; } }
            else if (!strcmp(argv[i], "--width") && i+1 < argc) { if (!parse_int_strict(argv[++i], &W)) { fprintf(stderr, "bad --width\n"); return 1; } }
            else if (!strcmp(argv[i], "--height") && i+1 < argc) { if (!parse_int_strict(argv[++i], &H)) { fprintf(stderr, "bad --height\n"); return 1; } }
            else { fprintf(stderr, "target-field: unknown flag '%s'\n", argv[i]); return 1; }
        }
        if (W < 2 || W > MAX_W || H < 2 || H > MAX_H) { fprintf(stderr, "grid out of range\n"); return 1; }
        run_target_field(tgt_id, pn, pm, W, H);
        return 0;
    }

    if (!strcmp(argv[1], "--score-fields")) {
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--width") && i+1 < argc) { if (!parse_int_strict(argv[++i], &W)) { fprintf(stderr, "bad --width\n"); return 1; } }
            else if (!strcmp(argv[i], "--height") && i+1 < argc) { if (!parse_int_strict(argv[++i], &H)) { fprintf(stderr, "bad --height\n"); return 1; } }
            else { fprintf(stderr, "score-fields: unknown flag '%s'\n", argv[i]); return 1; }
        }
        if (W < 2 || W > MAX_W || H < 2 || H > MAX_H) { fprintf(stderr, "grid out of range\n"); return 1; }
        run_score_fields(W, H);
        return 0;
    }

    if (!strcmp(argv[1], "--driver-values")) {
        const char *drv = "V1_INV_PI";
        int max_iter = 200; uint64_t seed = 7331;
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--driver") && i+1 < argc) drv = argv[++i];
            else if (!strcmp(argv[i], "--max-iter") && i+1 < argc) { if (!parse_int_strict(argv[++i], &max_iter)) { fprintf(stderr, "bad --max-iter\n"); return 1; } }
            else if (!strcmp(argv[i], "--seed") && i+1 < argc) { if (!parse_int_strict(argv[++i], (int*)&seed)) { fprintf(stderr, "bad --seed\n"); return 1; } }
            else if (!strcmp(argv[i], "--window") && i+1 < argc) { if (!parse_int_strict(argv[++i], &window)) { fprintf(stderr, "bad --window\n"); return 1; } }
            else if (!strcmp(argv[i], "--offset") && i+1 < argc) { if (!parse_int_strict(argv[++i], &offset)) { fprintf(stderr, "bad --offset\n"); return 1; } }
            else { fprintf(stderr, "driver-values: unknown flag '%s'\n", argv[i]); return 1; }
        }
        if (max_iter < 1 || max_iter > 20000) { fprintf(stderr, "max-iter out of range\n"); return 1; }
        run_driver_values(drv, max_iter, seed, window, offset);
        return 0;
    }

    fprintf(stderr, "Unknown command: %s\n", argv[1]);
    return 1;
}
