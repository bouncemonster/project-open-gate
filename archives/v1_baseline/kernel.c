/*
 * PROOF OF SIMULATION — C Numerical Kernel
 * Non-autonomous Julia set iteration with prime-arithmetic forcing.
 * Compile: gcc -O3 -std=c11 -Wall -Wextra -Wpedantic kernel.c -lm -o kernel
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include <time.h>
#include <stdint.h>

/* ================================================================
 * CONSTANTS
 * ================================================================ */
#define KERNEL_VERSION "1.0.0"
static const double PI_VAL = 3.141592653589793238462643383279502884;
#define WIDTH  60
#define HEIGHT 30
#define NCELLS (WIDTH * HEIGHT)
#define ESCAPE_R2 4.0
#define MAX_DRIVER_LEN 4096
#define DCT_MODES 8
#define DCT_TOTAL (DCT_MODES * DCT_MODES - 1)
#define ENTROPY_BINS 16
#define ACORR_RANGE 4
#define ACORR_SIZE (2*ACORR_RANGE+1)
#define ACORR_TOTAL (ACORR_SIZE*ACORR_SIZE - 1)
#define ASCII_PALETTE " .:-=+*#%@"
#define ASCII_PAL_LEN 10

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
    /* g_pi_prefix[k] will hold standard pi(k): count of primes <= k */
    char *is_p = (char *)calloc((size_t)g_pi_len, 1);
    if (!is_p) { fprintf(stderr, "sieve: OOM\n"); exit(1); }
    for (int i = 2; i <= n; i++) is_p[i] = 1;
    for (int i = 2; (long long)i * i <= n; i++) {
        if (is_p[i]) for (int j = i * i; j <= n; j += i) is_p[j] = 0;
    }
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

/* ================================================================
 * DRIVER COMPUTATION
 * ================================================================ */
typedef enum {
    DRV_V0_NONE = 0,
    DRV_V1_INV_PI,
    DRV_V2_SMOOTH,
    DRV_V3_CENTERED_INV_PI,
    DRV_V4_PRIME_RESIDUAL,
    DRV_V5_SHUFFLED,
    DRV_V6_REVERSED,
    DRV_V7_IMAGINARY,
    DRV_V8_PHASE_RANDOMIZED,
    DRV_COUNT
} DriverID;

static const char *driver_name(DriverID d) {
    switch (d) {
        case DRV_V0_NONE:              return "V0_NONE";
        case DRV_V1_INV_PI:            return "V1_INV_PI";
        case DRV_V2_SMOOTH:            return "V2_SMOOTH";
        case DRV_V3_CENTERED_INV_PI:   return "V3_CENTERED_INV_PI";
        case DRV_V4_PRIME_RESIDUAL:    return "V4_PRIME_RESIDUAL";
        case DRV_V5_SHUFFLED:          return "V5_SHUFFLED";
        case DRV_V6_REVERSED:          return "V6_REVERSED";
        case DRV_V7_IMAGINARY:         return "V7_IMAGINARY";
        case DRV_V8_PHASE_RANDOMIZED:  return "V8_PHASE_RANDOMIZED";
        default:                       return "UNKNOWN";
    }
}

static DriverID driver_from_string(const char *s) {
    if (!strcmp(s, "V0_NONE"))             return DRV_V0_NONE;
    if (!strcmp(s, "V1_INV_PI"))           return DRV_V1_INV_PI;
    if (!strcmp(s, "V2_SMOOTH"))           return DRV_V2_SMOOTH;
    if (!strcmp(s, "V3_CENTERED_INV_PI"))  return DRV_V3_CENTERED_INV_PI;
    if (!strcmp(s, "V4_PRIME_RESIDUAL"))   return DRV_V4_PRIME_RESIDUAL;
    if (!strcmp(s, "V5_SHUFFLED"))         return DRV_V5_SHUFFLED;
    if (!strcmp(s, "V6_REVERSED"))         return DRV_V6_REVERSED;
    if (!strcmp(s, "V7_IMAGINARY"))        return DRV_V7_IMAGINARY;
    if (!strcmp(s, "V8_PHASE_RANDOMIZED")) return DRV_V8_PHASE_RANDOMIZED;
    return DRV_V0_NONE;
}

/* Compute raw 1/pi(k) for k=1..max_iter, using max(pi(k),1) to avoid div-by-zero */
static void compute_raw_inv_pi(double *out, int max_iter) {
    for (int k = 1; k <= max_iter; k++) {
        int pk = pi_func(k);
        if (pk < 1) pk = 1;
        out[k] = 1.0 / (double)pk;
    }
}

/* Compute smooth surrogate S_raw(k) = log(k+2)/(k+1), then scale to match mean/std of raw */
static void compute_smooth_surrogate(double *out, const double *raw, int max_iter) {
    double sum_r = 0, sum_s = 0;
    for (int k = 1; k <= max_iter; k++) {
        sum_r += raw[k];
        sum_s += log((double)(k + 2)) / (double)(k + 1);
    }
    double mean_r = sum_r / max_iter;
    double mean_s = sum_s / max_iter;
    double var_r = 0, var_s = 0;
    for (int k = 1; k <= max_iter; k++) {
        double dr = raw[k] - mean_r;
        double ds = log((double)(k + 2)) / (double)(k + 1) - mean_s;
        var_r += dr * dr;
        var_s += ds * ds;
    }
    var_r /= max_iter; var_s /= max_iter;
    double std_r = sqrt(var_r), std_s = sqrt(var_s);
    if (std_s < 1e-15) std_s = 1.0;
    for (int k = 1; k <= max_iter; k++) {
        double sv = log((double)(k + 2)) / (double)(k + 1);
        out[k] = mean_r + std_r * (sv - mean_s) / std_s;
    }
}

static void compute_driver(double *drv, DriverID id, int max_iter, uint64_t shuffle_seed) {
    double raw[MAX_DRIVER_LEN];
    memset(raw, 0, sizeof(raw));
    memset(drv, 0, sizeof(double) * (size_t)(max_iter + 1));

    if (id == DRV_V0_NONE) return;

    compute_raw_inv_pi(raw, max_iter);

    switch (id) {
    case DRV_V1_INV_PI:
        for (int k = 1; k <= max_iter; k++) drv[k] = raw[k];
        break;
    case DRV_V2_SMOOTH:
        compute_smooth_surrogate(drv, raw, max_iter);
        break;
    case DRV_V3_CENTERED_INV_PI: {
        double mean = 0;
        for (int k = 1; k <= max_iter; k++) mean += raw[k];
        mean /= max_iter;
        for (int k = 1; k <= max_iter; k++) drv[k] = raw[k] - mean;
        break;
    }
    case DRV_V4_PRIME_RESIDUAL: {
        double smooth[MAX_DRIVER_LEN];
        compute_smooth_surrogate(smooth, raw, max_iter);
        double resid[MAX_DRIVER_LEN];
        double sum = 0;
        for (int k = 1; k <= max_iter; k++) { resid[k] = raw[k] - smooth[k]; sum += resid[k]; }
        double mean = sum / max_iter;
        double var = 0;
        for (int k = 1; k <= max_iter; k++) var += (resid[k] - mean) * (resid[k] - mean);
        var /= max_iter;
        double std = sqrt(var);
        if (std < 1e-15) std = 1.0;
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
        /* Center the signal first, then randomize phases via DFT */
        double mean = 0;
        for (int k = 1; k <= max_iter; k++) mean += raw[k];
        mean /= max_iter;
        double centered[MAX_DRIVER_LEN];
        for (int k = 1; k <= max_iter; k++) centered[k] = raw[k] - mean;

        int N = max_iter;
        double re_out[MAX_DRIVER_LEN], im_out[MAX_DRIVER_LEN];
        double re_in[MAX_DRIVER_LEN], im_in[MAX_DRIVER_LEN];
        for (int k = 0; k < N; k++) { re_in[k] = centered[k + 1]; im_in[k] = 0.0; }

        /* Forward DFT */
        for (int m = 0; m < N; m++) {
            double sr = 0, si = 0;
            for (int k = 0; k < N; k++) {
                double angle = 2.0 * PI_VAL * m * k / N;
                sr += re_in[k] * cos(angle) + im_in[k] * sin(angle);
                si += im_in[k] * cos(angle) - re_in[k] * sin(angle);
            }
            re_out[m] = sr; im_out[m] = si;
        }

        /* Randomize phases with deterministic PRNG, preserving conjugate symmetry */
        SM64 rng; sm64_seed(&rng, shuffle_seed);
        double phases[MAX_DRIVER_LEN];
        phases[0] = 0;
        for (int m = 1; m <= N / 2; m++) phases[m] = sm64_double(&rng) * 2.0 * PI_VAL;
        for (int m = N / 2 + 1; m < N; m++) phases[m] = -phases[N - m];

        double re_r[MAX_DRIVER_LEN], im_r[MAX_DRIVER_LEN];
        for (int m = 0; m < N; m++) {
            double amp = sqrt(re_out[m] * re_out[m] + im_out[m] * im_out[m]);
            re_r[m] = amp * cos(phases[m]);
            im_r[m] = amp * sin(phases[m]);
        }

        /* Inverse DFT */
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
    default:
        break;
    }
}

/* ================================================================
 * TARGET FUNCTIONS
 * ================================================================ */
typedef enum {
    TGT_A = 0, TGT_B, TGT_PHASE, TGT_EIGENMODE, TGT_COUNT
} TargetID;

static void compute_target(double *T, TargetID tid, int param_n, int param_m) {
    (void)param_n; (void)param_m;
    for (int py = 0; py < HEIGHT; py++) {
        double v = (double)py / (HEIGHT - 1);
        for (int px = 0; px < WIDTH; px++) {
            double u = (double)px / (WIDTH - 1);
            int idx = py * WIDTH + px;
            switch (tid) {
            case TGT_A:
                T[idx] = fabs(sin(PI_VAL * u) * cos(PI_VAL * v));
                break;
            case TGT_B:
                T[idx] = sin(PI_VAL * u) * sin(PI_VAL * u) * cos(PI_VAL * v) * cos(PI_VAL * v);
                break;
            case TGT_PHASE: {
                double uu = u + 0.07, vv = v - 0.11;
                /* periodic wrapping */
                uu = uu - floor(uu);
                vv = vv - floor(vv);
                T[idx] = fabs(sin(PI_VAL * uu) * cos(PI_VAL * vv));
                break;
            }
            case TGT_EIGENMODE:
                T[idx] = sin(param_n * PI_VAL * u) * sin(param_n * PI_VAL * u)
                       * sin(param_m * PI_VAL * v) * sin(param_m * PI_VAL * v);
                break;
            }
        }
    }
}

/* ================================================================
 * COMPLEX ARITHMETIC
 * ================================================================ */
static inline void complex_sq(double zr, double zi, double *or_, double *oi) {
    *or_ = zr * zr - zi * zi;
    *oi = 2.0 * zr * zi;
}

static inline void complex_cub(double zr, double zi, double *or_, double *oi) {
    /* z^3 = z*z^2 = (zr+izi)(zr^2-zi^2 + 2izrzi) */
    double z2r = zr * zr - zi * zi;
    double z2i = 2.0 * zr * zi;
    *or_ = zr * z2r - zi * z2i;
    *oi = zr * z2i + zi * z2r;
}

/* ================================================================
 * JULIA ITERATION WITH FORCING
 * ================================================================ */
static void iterate_julia(double cr, double ci, const double *driver,
                           double alpha, int degree, int channel,
                           int max_iter, double *F_smooth, double *F_discrete,
                           double *escaped_frac,
                           /* trace output: arrays of size max_iter */
                           double *tr_active, double *tr_mean_abs,
                           double *tr_std_abs, double *tr_mean_zr,
                           double *tr_mean_zi, double *tr_esc_frac,
                           double *tr_driver_val, int *tr_prime_event,
                           int do_trace)
{
    double F_s[NCELLS], F_d[NCELLS];
    int escaped_count = 0;

    for (int py = 0; py < HEIGHT; py++) {
        double y = -1.0 + 2.0 * py / (HEIGHT - 1);
        for (int px = 0; px < WIDTH; px++) {
            double x = -1.8 + 3.6 * px / (WIDTH - 1);
            int idx = py * WIDTH + px;
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
                if (channel == 0) real_corr = alpha * drv_val;  /* REAL */
                else              imag_corr = alpha * drv_val;  /* IMAG */

                zr = sq_r + cr + real_corr;
                zi = sq_i + ci + imag_corr;

                if (!isfinite(zr) || !isfinite(zi)) {
                    esc_iter = iter;
                    zr = 1e10; zi = 0;
                    break;
                }

                if (zr * zr + zi * zi > ESCAPE_R2) {
                    esc_iter = iter;
                    break;
                }
            }

            double nu;
            if (esc_iter < max_iter) {
                double mag = hypot(zr, zi);
                if (mag > 1.0 && isfinite(mag)) {
                    nu = (double)(esc_iter + 1) - log(log(mag)) / log(2.0);
                } else {
                    nu = (double)esc_iter;
                }
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

    if (F_smooth)      memcpy(F_smooth, F_s, sizeof(double) * NCELLS);
    if (F_discrete)    memcpy(F_discrete, F_d, sizeof(double) * NCELLS);
    if (escaped_frac)  *escaped_frac = (double)escaped_count / (double)NCELLS;

    /* Trace output */
    if (do_trace && tr_active) {
        /* Re-run iteration collecting per-iteration stats */
        for (int iter = 0; iter < max_iter; iter++) {
            int k = iter + 1;
            double drv_val = driver[k];
            int active = 0, esc_this = 0;
            double sum_abs = 0, sum_zr = 0, sum_zi = 0;
            double sum_abs2 = 0;

            for (int py = 0; py < HEIGHT; py++) {
                double y0 = -1.0 + 2.0 * py / (HEIGHT - 1);
                for (int px = 0; px < WIDTH; px++) {
                    double x0 = -1.8 + 3.6 * px / (WIDTH - 1);
                    double zr = x0, zi = y0;
                    int is_active = 1;
                    for (int it = 0; it <= iter; it++) {
                        double oz = zr, ozi = zi;
                        double sr, si;
                        if (degree == 3) complex_cub(oz, ozi, &sr, &si);
                        else             complex_sq(oz, ozi, &sr, &si);
                        int kk = it + 1;
                        double dv = driver[kk];
                        double rc = 0, ic = 0;
                        if (channel == 0) rc = alpha * dv; else ic = alpha * dv;
                        zr = sr + cr + rc;
                        zi = si + ci + ic;
                        if (!isfinite(zr) || !isfinite(zi) || zr*zr+zi*zi > ESCAPE_R2) {
                            is_active = 0;
                            break;
                        }
                    }
                    if (is_active) {
                        active++;
                        double ab = hypot(zr, zi);
                        sum_abs += ab;
                        sum_abs2 += ab * ab;
                        sum_zr += zr;
                        sum_zi += zi;
                    } else {
                        esc_this++;
                    }
                }
            }
            tr_active[iter]     = (double)active / NCELLS;
            tr_mean_abs[iter]   = active > 0 ? sum_abs / active : 0;
            double m = active > 0 ? sum_abs / active : 0;
            tr_std_abs[iter]    = active > 1 ? sqrt(sum_abs2/active - m*m) : 0;
            tr_mean_zr[iter]    = active > 0 ? sum_zr / active : 0;
            tr_mean_zi[iter]    = active > 0 ? sum_zi / active : 0;
            tr_esc_frac[iter]   = (double)esc_this / NCELLS;
            tr_driver_val[iter] = drv_val;
            /* Check if k is prime */
            int is_prime = 0;
            if (k >= 2) {
                is_prime = 1;
                for (int d = 2; d * d <= k; d++) {
                    if (k % d == 0) { is_prime = 0; break; }
                }
            }
            tr_prime_event[iter] = is_prime;
        }
    }
}

/* ================================================================
 * METRICS
 * ================================================================ */

/* Pearson correlation -> Pearson01 */
static double metric_pearson(const double *F, const double *T) {
    double sf = 0, st = 0;
    for (int i = 0; i < NCELLS; i++) { sf += F[i]; st += T[i]; }
    double mf = sf / NCELLS, mt = st / NCELLS;
    double cov = 0, vf = 0, vt = 0;
    for (int i = 0; i < NCELLS; i++) {
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

/* Comparison function for ranking */
typedef struct { double val; int idx; } ValIdx;
static int cmp_validx(const void *a, const void *b) {
    double va = ((const ValIdx *)a)->val, vb = ((const ValIdx *)b)->val;
    return (va > vb) - (va < vb);
}

static void compute_ranks(const double *vals, double *ranks, int n) {
    ValIdx *vi = (ValIdx *)malloc((size_t)n * sizeof(ValIdx));
    for (int i = 0; i < n; i++) { vi[i].val = vals[i]; vi[i].idx = i; }
    qsort(vi, (size_t)n, sizeof(ValIdx), cmp_validx);
    /* Assign average ranks for ties */
    int i = 0;
    while (i < n) {
        int j = i;
        while (j < n && vi[j].val == vi[i].val) j++;
        double avg_rank = 0.5 * (i + j + 1); /* 1-based average */
        /* Actually: ranks from 1 to n, average for ties */
        /* i to j-1 are tied, their ranks would be i+1 to j */
        avg_rank = 0.5 * ((i + 1) + j);
        for (int k = i; k < j; k++) ranks[vi[k].idx] = avg_rank;
        i = j;
    }
    free(vi);
}

/* Spearman correlation -> Spearman01 */
static double metric_spearman(const double *F, const double *T) {
    double rf[NCELLS], rt[NCELLS];
    compute_ranks(F, rf, NCELLS);
    compute_ranks(T, rt, NCELLS);
    /* Pearson on ranks */
    double sf = 0, st = 0;
    for (int i = 0; i < NCELLS; i++) { sf += rf[i]; st += rt[i]; }
    double mf = sf / NCELLS, mt = st / NCELLS;
    double cov = 0, vf = 0, vt = 0;
    for (int i = 0; i < NCELLS; i++) {
        double df = rf[i] - mf, dt = rt[i] - mt;
        cov += df * dt; vf += df * df; vt += dt * dt;
    }
    double denom = sqrt(vf * vt);
    if (denom < 1e-15) return 0.5;
    double rho = cov / denom;
    double s01 = (rho + 1.0) / 2.0;
    if (s01 < 0) s01 = 0; if (s01 > 1) s01 = 1;
    return s01;
}

/* MAE -> MAE01 */
static double metric_mae(const double *F, const double *T) {
    double sum = 0;
    for (int i = 0; i < NCELLS; i++) sum += fabs(F[i] - T[i]);
    double mae = sum / NCELLS;
    double m01 = 1.0 - mae;
    if (m01 < 0) m01 = 0; if (m01 > 1) m01 = 1;
    return m01;
}

/* Gradient similarity -> Gradient01 */
static double metric_gradient(const double *F, const double *T) {
    double dot = 0, nf = 0, nt = 0;
    for (int py = 0; py < HEIGHT; py++) {
        for (int px = 0; px < WIDTH; px++) {
            int idx = py * WIDTH + px;
            double gfx, gfy, gtx, gty;
            /* Central differences for F */
            if (px > 0 && px < WIDTH - 1)
                gfx = F[idx + 1] - F[idx - 1];
            else if (px == 0)
                gfx = F[idx + 1] - F[idx];
            else
                gfx = F[idx] - F[idx - 1];

            if (py > 0 && py < HEIGHT - 1)
                gfy = F[idx + WIDTH] - F[idx - WIDTH];
            else if (py == 0)
                gfy = F[idx + WIDTH] - F[idx];
            else
                gfy = F[idx] - F[idx - WIDTH];

            /* Central differences for T */
            if (px > 0 && px < WIDTH - 1)
                gtx = T[idx + 1] - T[idx - 1];
            else if (px == 0)
                gtx = T[idx + 1] - T[idx];
            else
                gtx = T[idx] - T[idx - 1];

            if (py > 0 && py < HEIGHT - 1)
                gty = T[idx + WIDTH] - T[idx - WIDTH];
            else if (py == 0)
                gty = T[idx + WIDTH] - T[idx];
            else
                gty = T[idx] - T[idx - WIDTH];

            dot += gfx * gtx + gfy * gty;
            nf  += gfx * gfx + gfy * gfy;
            nt  += gtx * gtx + gty * gty;
        }
    }
    double denom = sqrt(nf * nt);
    if (denom < 1e-15) return 0.5;
    double cos_sim = dot / denom;
    double g01 = (cos_sim + 1.0) / 2.0;
    if (g01 < 0) g01 = 0; if (g01 > 1) g01 = 1;
    return g01;
}

/* Spectral similarity via DCT-II (8x8 modes, excluding DC) -> Spectral01 */
static double metric_spectral(const double *F, const double *T) {
    double cf[DCT_TOTAL], ct[DCT_TOTAL];
    int idx = 0;
    for (int u = 0; u < DCT_MODES; u++) {
        for (int v = 0; v < DCT_MODES; v++) {
            if (u == 0 && v == 0) continue;
            double sf = 0, st = 0;
            for (int py = 0; py < HEIGHT; py++) {
                for (int px = 0; px < WIDTH; px++) {
                    double cu = cos(PI_VAL * u * (2 * px + 1) / (2.0 * WIDTH));
                    double cv = cos(PI_VAL * v * (2 * py + 1) / (2.0 * HEIGHT));
                    double basis = cu * cv;
                    int cell = py * WIDTH + px;
                    sf += F[cell] * basis;
                    st += T[cell] * basis;
                }
            }
            cf[idx] = sf; ct[idx] = st;
            idx++;
        }
    }
    /* L2 normalize */
    double nf = 0, nt = 0, dot = 0;
    for (int i = 0; i < DCT_TOTAL; i++) {
        nf += cf[i] * cf[i]; nt += ct[i] * ct[i]; dot += cf[i] * ct[i];
    }
    nf = sqrt(nf); nt = sqrt(nt);
    if (nf < 1e-15 || nt < 1e-15) return 0.5;
    double cos_sim = dot / (nf * nt);
    double s01 = (cos_sim + 1.0) / 2.0;
    if (s01 < 0) s01 = 0; if (s01 > 1) s01 = 1;
    return s01;
}

/* Autocorrelation similarity -> Autocorrelation01 */
static double metric_autocorrelation(const double *F, const double *T) {
    /* Standardize both fields */
    double sf = 0, st = 0;
    for (int i = 0; i < NCELLS; i++) { sf += F[i]; st += T[i]; }
    double mf = sf / NCELLS, mt = st / NCELLS;
    double vf = 0, vt = 0;
    for (int i = 0; i < NCELLS; i++) {
        vf += (F[i] - mf) * (F[i] - mf);
        vt += (T[i] - mt) * (T[i] - mt);
    }
    double stdf = sqrt(vf / NCELLS), stdt = sqrt(vt / NCELLS);
    if (stdf < 1e-15 || stdt < 1e-15) return 0.5;

    double af[ACORR_TOTAL], at_[ACORR_TOTAL];
    int idx = 0;
    for (int dy = -ACORR_RANGE; dy <= ACORR_RANGE; dy++) {
        for (int dx = -ACORR_RANGE; dx <= ACORR_RANGE; dx++) {
            if (dx == 0 && dy == 0) continue;
            double cf = 0, ct = 0;
            int count = 0;
            for (int py = 0; py < HEIGHT; py++) {
                int py2 = py + dy;
                if (py2 < 0 || py2 >= HEIGHT) continue;
                for (int px = 0; px < WIDTH; px++) {
                    int px2 = px + dx;
                    if (px2 < 0 || px2 >= WIDTH) continue;
                    int i1 = py * WIDTH + px, i2 = py2 * WIDTH + px2;
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
    /* Cosine similarity of autocorrelation vectors */
    double dot = 0, nf = 0, nt = 0;
    for (int i = 0; i < ACORR_TOTAL; i++) {
        dot += af[i] * at_[i]; nf += af[i] * af[i]; nt += at_[i] * at_[i];
    }
    double denom = sqrt(nf * nt);
    if (denom < 1e-15) return 0.5;
    double cos_sim = dot / denom;
    double a01 = (cos_sim + 1.0) / 2.0;
    if (a01 < 0) a01 = 0; if (a01 > 1) a01 = 1;
    return a01;
}

/* ================================================================
 * COMPOSITE SCORE
 * ================================================================ */
static double compute_score(double p01, double sp01, double m01,
                             double g01, double spc01, double a01) {
    return 0.25 * p01 + 0.15 * sp01 + 0.15 * m01
         + 0.15 * g01 + 0.15 * spc01 + 0.15 * a01;
}

/* ================================================================
 * SECONDARY DIAGNOSTICS
 * ================================================================ */
static double diagnostic_entropy(const double *F) {
    int bins[ENTROPY_BINS];
    memset(bins, 0, sizeof(bins));
    for (int i = 0; i < NCELLS; i++) {
        int b = (int)(F[i] * ENTROPY_BINS);
        if (b < 0) b = 0; if (b >= ENTROPY_BINS) b = ENTROPY_BINS - 1;
        bins[b]++;
    }
    double H = 0;
    for (int i = 0; i < ENTROPY_BINS; i++) {
        if (bins[i] > 0) {
            double p = (double)bins[i] / NCELLS;
            H -= p * log(p);
        }
    }
    return H / log((double)ENTROPY_BINS);
}

static double diagnostic_anisotropy(const double *F) {
    /* Compute horizontal, vertical, diagonal correlations */
    double sf = 0, vf = 0;
    for (int i = 0; i < NCELLS; i++) sf += F[i];
    double mf = sf / NCELLS;
    for (int i = 0; i < NCELLS; i++) vf += (F[i] - mf) * (F[i] - mf);
    vf /= NCELLS;
    if (vf < 1e-15) return 0;

    double corr_h = 0, corr_v = 0, corr_d1 = 0, corr_d2 = 0;
    int nh = 0, nv = 0, nd = 0;
    for (int py = 0; py < HEIGHT; py++) {
        for (int px = 0; px < WIDTH; px++) {
            int idx = py * WIDTH + px;
            double v0 = F[idx] - mf;
            if (px + 1 < WIDTH) { corr_h += v0 * (F[idx+1] - mf); nh++; }
            if (py + 1 < HEIGHT) { corr_v += v0 * (F[idx+WIDTH] - mf); nv++; }
            if (px + 1 < WIDTH && py + 1 < HEIGHT) { corr_d1 += v0 * (F[idx+WIDTH+1] - mf); nd++; }
            if (px > 0 && py + 1 < HEIGHT) { corr_d2 += v0 * (F[idx+WIDTH-1] - mf); nd++; }
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

static void diagnostic_quantization(const double *F_disc, int *n_levels, double *dom_frac) {
    int counts[MAX_DRIVER_LEN];
    memset(counts, 0, sizeof(int) * NCELLS);
    /* F_disc values are multiples of 1/max_iter */
    int max_levels = NCELLS;
    int *lv = (int *)calloc((size_t)max_levels, sizeof(int));
    int n_distinct = 0;
    /* Map each value to a level index */
    int *level_map = (int *)calloc((size_t)NCELLS, sizeof(int));
    int next_level = 0;
    for (int i = 0; i < NCELLS; i++) {
        int key = (int)(F_disc[i] * 100000 + 0.5);
        int found = -1;
        for (int j = 0; j < next_level; j++) {
            if (level_map[j] == key) { found = j; break; }
        }
        if (found < 0) { level_map[next_level] = key; found = next_level++; }
        counts[found]++;
    }
    n_distinct = next_level;
    int max_count = 0;
    for (int i = 0; i < n_distinct; i++) if (counts[i] > max_count) max_count = counts[i];
    *n_levels = n_distinct;
    *dom_frac = n_distinct > 0 ? (double)max_count / NCELLS : 0;
    free(lv); free(level_map);
}

static double diagnostic_compression_estimate(const double *F) {
    /* Simple RLE-based compression ratio estimate */
    /* Quantize to ASCII levels */
    char buf[NCELLS + 1];
    for (int i = 0; i < NCELLS; i++) {
        int level = (int)(F[i] * ASCII_PAL_LEN);
        if (level >= ASCII_PAL_LEN) level = ASCII_PAL_LEN - 1;
        buf[i] = ASCII_PALETTE[level];
    }
    buf[NCELLS] = '\0';
    /* Count RLE runs */
    int runs = 1;
    for (int i = 1; i < NCELLS; i++) if (buf[i] != buf[i-1]) runs++;
    double raw_size = (double)NCELLS;
    double compressed = (double)(runs * 2); /* rough: char + count */
    double ratio = compressed / raw_size;
    if (ratio > 1.0) ratio = 1.0;
    return ratio;
}

/* ================================================================
 * SELF-TEST
 * ================================================================ */
static int self_test(void) {
    int pass = 1;
    /* Test pi function */
    sieve_build(1100);
    if (pi_func(10) != 4)  { printf("FAIL: pi(10) = %d, expected 4\n", pi_func(10)); pass = 0; }
    if (pi_func(100) != 25) { printf("FAIL: pi(100) = %d, expected 25\n", pi_func(100)); pass = 0; }
    if (pi_func(1000) != 168) { printf("FAIL: pi(1000) = %d, expected 168\n", pi_func(1000)); pass = 0; }

    /* Test complex arithmetic */
    double r, i_;
    complex_sq(1.0, 1.0, &r, &i_);
    if (fabs(r) > 1e-10 || fabs(i_ - 2.0) > 1e-10) { printf("FAIL: complex_sq\n"); pass = 0; }

    /* Test target generation */
    double T[NCELLS];
    compute_target(T, TGT_A, 0, 0);
    int tgt_ok = 1;
    for (int j = 0; j < NCELLS; j++) { if (T[j] < -0.01 || T[j] > 1.01) { tgt_ok = 0; break; } }
    if (!tgt_ok) { printf("FAIL: target range\n"); pass = 0; }

    /* Test score range */
    double F[NCELLS];
    for (int j = 0; j < NCELLS; j++) F[j] = T[j]; /* perfect match */
    double p01 = metric_pearson(F, T);
    double m01 = metric_mae(F, T);
    if (p01 < 0.99) { printf("FAIL: pearson self-match = %f\n", p01); pass = 0; }
    if (m01 < 0.99) { printf("FAIL: mae self-match = %f\n", m01); pass = 0; }

    /* Test determinism */
    sieve_build(210);
    double d1[NCELLS], d2[NCELLS];
    double drv[MAX_DRIVER_LEN];
    compute_driver(drv, DRV_V1_INV_PI, 200, 7331);
    iterate_julia(-0.7, 0.27015, drv, 1.0, 2, 0, 200, d1, NULL, NULL, NULL,NULL,NULL,NULL,NULL,NULL, NULL, NULL, 0);
    iterate_julia(-0.7, 0.27015, drv, 1.0, 2, 0, 200, d2, NULL, NULL, NULL,NULL,NULL,NULL,NULL,NULL, NULL, NULL, 0);
    double max_diff = 0;
    for (int j = 0; j < NCELLS; j++) { double d = fabs(d1[j] - d2[j]); if (d > max_diff) max_diff = d; }
    if (max_diff > 1e-15) { printf("FAIL: determinism, max_diff=%e\n", max_diff); pass = 0; }

    /* Test ASCII dimensions */
    if (WIDTH != 60 || HEIGHT != 30) { printf("FAIL: dimensions\n"); pass = 0; }

    if (pass) printf("ALL SELF-TESTS PASSED\n");
    else      printf("SOME SELF-TESTS FAILED\n");
    return pass;
}

/* ================================================================
 * ASCII RENDER
 * ================================================================ */
static void render_ascii(const double *F, FILE *out) {
    for (int py = 0; py < HEIGHT; py++) {
        for (int px = 0; px < WIDTH; px++) {
            int idx = py * WIDTH + px;
            int level = (int)(F[idx] * ASCII_PAL_LEN);
            if (level >= ASCII_PAL_LEN) level = ASCII_PAL_LEN - 1;
            if (level < 0) level = 0;
            fputc(ASCII_PALETTE[level], out);
        }
        fputc('\n', out);
    }
}

/* ================================================================
 * BATCH MODE
 * ================================================================ */
typedef struct {
    int candidate_id;
    double cr, ci;
    DriverID driver;
    double alpha;
    int degree;
    int channel; /* 0=REAL, 1=IMAG */
    int max_iter;
    uint64_t seed;
} Candidate;

typedef struct {
    int candidate_id;
    double score;
    double pearson01, spearman01, mae01, gradient01, spectral01, autocorrelation01;
    double entropy, anisotropy, compression_ratio;
    int quantization_levels;
    double quantization_dom_frac;
    double escaped_fraction;
    double runtime_ms;
    int error_code;
} Result;

static void process_batch(void) {
    char line[1024];
    /* Read candidates from stdin */
    Candidate cands[256];
    int ncand = 0;

    while (fgets(line, sizeof(line), stdin) && ncand < 256) {
        char drv_str[64], model_str[64];
        int n = sscanf(line, "%d %lf %lf %63s %63s %lf %d %d %d %llu",
                       &cands[ncand].candidate_id,
                       &cands[ncand].cr, &cands[ncand].ci,
                       model_str, drv_str,
                       &cands[ncand].alpha,
                       &cands[ncand].degree,
                       &cands[ncand].channel,
                       &cands[ncand].max_iter,
                       (unsigned long long *)&cands[ncand].seed);
        if (n < 10) continue;
        cands[ncand].driver = driver_from_string(drv_str);
        ncand++;
    }

    if (ncand == 0) return;

    /* Find max_iter across candidates */
    int max_mi = 0;
    for (int i = 0; i < ncand; i++)
        if (cands[i].max_iter > max_mi) max_mi = cands[i].max_iter;

    /* Build sieve and precompute target */
    sieve_build(max_mi + 10);
    double target[NCELLS];
    compute_target(target, TGT_A, 0, 0);

    /* Process each candidate */
    for (int i = 0; i < ncand; i++) {
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);

        Result res;
        memset(&res, 0, sizeof(res));
        res.candidate_id = cands[i].candidate_id;

        int mi = cands[i].max_iter;
        if (mi < 1) mi = 1;
        if (mi >= MAX_DRIVER_LEN) mi = MAX_DRIVER_LEN - 1;

        double drv[MAX_DRIVER_LEN];
        compute_driver(drv, cands[i].driver, mi, cands[i].seed);

        double F_smooth[NCELLS], F_discrete[NCELLS];
        double esc_frac = 0;

        iterate_julia(cands[i].cr, cands[i].ci, drv,
                      cands[i].alpha, cands[i].degree, cands[i].channel,
                      mi, F_smooth, F_discrete, &esc_frac,
                      NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0);

        /* Check for NaN in field */
        int has_nan = 0;
        for (int j = 0; j < NCELLS; j++) {
            if (!isfinite(F_smooth[j])) { has_nan = 1; break; }
        }

        if (has_nan) {
            res.error_code = 1;
            res.score = 0;
        } else {
            res.pearson01   = metric_pearson(F_smooth, target);
            res.spearman01  = metric_spearman(F_smooth, target);
            res.mae01       = metric_mae(F_smooth, target);
            res.gradient01  = metric_gradient(F_smooth, target);
            res.spectral01  = metric_spectral(F_smooth, target);
            res.autocorrelation01 = metric_autocorrelation(F_smooth, target);
            res.score = compute_score(res.pearson01, res.spearman01, res.mae01,
                                       res.gradient01, res.spectral01, res.autocorrelation01);
            res.entropy = diagnostic_entropy(F_smooth);
            res.anisotropy = diagnostic_anisotropy(F_smooth);
            res.compression_ratio = diagnostic_compression_estimate(F_smooth);
            int ql; double df;
            diagnostic_quantization(F_discrete, &ql, &df);
            res.quantization_levels = ql;
            res.quantization_dom_frac = df;
            res.escaped_fraction = esc_frac;
        }

        clock_gettime(CLOCK_MONOTONIC, &t1);
        res.runtime_ms = (t1.tv_sec - t0.tv_sec) * 1000.0
                       + (t1.tv_nsec - t0.tv_nsec) / 1e6;

        /* Output TSV */
        printf("%d\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f"
               "\t%.6f\t%.6f\t%.6f\t%d\t%.6f\t%.6f\t%.1f\t%d\n",
               res.candidate_id, res.score,
               res.pearson01, res.spearman01, res.mae01,
               res.gradient01, res.spectral01, res.autocorrelation01,
               res.entropy, res.anisotropy, res.compression_ratio,
               res.quantization_levels, res.quantization_dom_frac,
               res.escaped_fraction, res.runtime_ms, res.error_code);
        fflush(stdout);
    }
}

/* ================================================================
 * TRACE MODE
 * ================================================================ */
static void run_trace(double cr, double ci, const char *drv_name_str,
                       double alpha, int degree, int channel, int max_iter,
                       uint64_t seed) {
    sieve_build(max_iter + 10);
    DriverID did = driver_from_string(drv_name_str);
    double drv[MAX_DRIVER_LEN];
    compute_driver(drv, did, max_iter, seed);

    double F_smooth[NCELLS], F_discrete[NCELLS], esc_frac;
    double *tr_active = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_mean_abs = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_std_abs = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_mean_zr = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_mean_zi = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_esc_frac = (double *)calloc((size_t)max_iter, sizeof(double));
    double *tr_driver = (double *)calloc((size_t)max_iter, sizeof(double));
    int *tr_prime = (int *)calloc((size_t)max_iter, sizeof(int));

    iterate_julia(cr, ci, drv, alpha, degree, channel, max_iter,
                  F_smooth, F_discrete, &esc_frac,
                  tr_active, tr_mean_abs, tr_std_abs, tr_mean_zr, tr_mean_zi,
                  tr_esc_frac, tr_driver, tr_prime, 1);

    printf("iter\tactive_frac\tmean_abs_z\tstd_abs_z\tmean_zr\tmean_zi\tesc_frac\tdriver\tprime\n");
    for (int k = 0; k < max_iter; k++) {
        printf("%d\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%d\n",
               k, tr_active[k], tr_mean_abs[k], tr_std_abs[k],
               tr_mean_zr[k], tr_mean_zi[k], tr_esc_frac[k],
               tr_driver[k], tr_prime[k]);
    }

    free(tr_active); free(tr_mean_abs); free(tr_std_abs);
    free(tr_mean_zr); free(tr_mean_zi); free(tr_esc_frac);
    free(tr_driver); free(tr_prime);
}

/* ================================================================
 * RENDER MODE (single point)
 * ================================================================ */
static void run_render(double cr, double ci, const char *drv_name_str,
                        double alpha, int degree, int channel, int max_iter,
                        uint64_t seed, TargetID target_id) {
    sieve_build(max_iter + 10);
    DriverID did = driver_from_string(drv_name_str);
    double drv[MAX_DRIVER_LEN];
    compute_driver(drv, did, max_iter, seed);

    double F_smooth[NCELLS], F_discrete[NCELLS], esc_frac;
    iterate_julia(cr, ci, drv, alpha, degree, channel, max_iter,
                  F_smooth, F_discrete, &esc_frac,
                  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0);

    render_ascii(F_smooth, stdout);

    double target[NCELLS];
    compute_target(target, target_id, 0, 0);
    double p01 = metric_pearson(F_smooth, target);
    double score = compute_score(p01, metric_spearman(F_smooth, target),
                                  metric_mae(F_smooth, target),
                                  metric_gradient(F_smooth, target),
                                  metric_spectral(F_smooth, target),
                                  metric_autocorrelation(F_smooth, target));
    printf("\nScore: %.6f  Pearson01: %.6f\n", score, p01);
}

/* ================================================================
 * MAIN
 * ================================================================ */
int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: kernel [--version|--self-test|--batch|--render|--trace] [options]\n");
        return 1;
    }

    if (!strcmp(argv[1], "--version")) {
        printf("PROOF OF SIMULATION kernel %s\n", KERNEL_VERSION);
        return 0;
    }

    if (!strcmp(argv[1], "--self-test")) {
        return self_test() ? 0 : 1;
    }

    if (!strcmp(argv[1], "--batch")) {
        process_batch();
        return 0;
    }

    if (!strcmp(argv[1], "--render")) {
        double cr = -0.7, ci = 0.27015, alpha = 1.0;
        int degree = 2, channel = 0, max_iter = 200;
        uint64_t seed = 7331;
        const char *drv = "V1_INV_PI";
        TargetID tid = TGT_A;
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--cr") && i+1 < argc) cr = atof(argv[++i]);
            else if (!strcmp(argv[i], "--ci") && i+1 < argc) ci = atof(argv[++i]);
            else if (!strcmp(argv[i], "--driver") && i+1 < argc) drv = argv[++i];
            else if (!strcmp(argv[i], "--alpha") && i+1 < argc) alpha = atof(argv[++i]);
            else if (!strcmp(argv[i], "--degree") && i+1 < argc) degree = atoi(argv[++i]);
            else if (!strcmp(argv[i], "--channel") && i+1 < argc) channel = atoi(argv[++i]);
            else if (!strcmp(argv[i], "--max-iter") && i+1 < argc) max_iter = atoi(argv[++i]);
            else if (!strcmp(argv[i], "--seed") && i+1 < argc) seed = (uint64_t)atoll(argv[++i]);
            else if (!strcmp(argv[i], "--target") && i+1 < argc) {
                const char *tname = argv[++i];
                if (!strcmp(tname, "TARGET_B")) tid = TGT_B;
                else if (!strcmp(tname, "TARGET_PHASE")) tid = TGT_PHASE;
                else tid = TGT_A;
            }
        }
        run_render(cr, ci, drv, alpha, degree, channel, max_iter, seed, tid);
        return 0;
    }

    if (!strcmp(argv[1], "--trace")) {
        double cr = -0.7, ci = 0.27015, alpha = 1.0;
        int degree = 2, channel = 0, max_iter = 200;
        uint64_t seed = 7331;
        const char *drv = "V1_INV_PI";
        for (int i = 2; i < argc; i++) {
            if (!strcmp(argv[i], "--cr") && i+1 < argc) cr = atof(argv[++i]);
            else if (!strcmp(argv[i], "--ci") && i+1 < argc) ci = atof(argv[++i]);
            else if (!strcmp(argv[i], "--driver") && i+1 < argc) drv = argv[++i];
            else if (!strcmp(argv[i], "--alpha") && i+1 < argc) alpha = atof(argv[++i]);
            else if (!strcmp(argv[i], "--degree") && i+1 < argc) degree = atoi(argv[++i]);
            else if (!strcmp(argv[i], "--channel") && i+1 < argc) channel = atoi(argv[++i]);
            else if (!strcmp(argv[i], "--max-iter") && i+1 < argc) max_iter = atoi(argv[++i]);
            else if (!strcmp(argv[i], "--seed") && i+1 < argc) seed = (uint64_t)atoll(argv[++i]);
        }
        run_trace(cr, ci, drv, alpha, degree, channel, max_iter, seed);
        return 0;
    }

    fprintf(stderr, "Unknown command: %s\n", argv[1]);
    return 1;
}
