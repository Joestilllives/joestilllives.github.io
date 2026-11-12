/* lib.c - tiny C library */
#include "os.h"
#include <stdarg.h>

u32 strlen(const char *s) { u32 n = 0; while (s[n]) n++; return n; }
int strcmp(const char *a, const char *b) { while (*a && *a == *b) a++, b++; return (u8)*a - (u8)*b; }
int strncmp(const char *a, const char *b, u32 n) {
    while (n && *a && *a == *b) a++, b++, n--;
    return n ? (u8)*a - (u8)*b : 0;
}
void strcpy(char *d, const char *s) { while ((*d++ = *s++)); }
void strncpy0(char *d, const char *s, u32 n) { u32 i = 0; while (i + 1 < n && s[i]) { d[i] = s[i]; i++; } d[i] = 0; }
void *memset(void *d, int c, u32 n) { u8 *p = d; while (n--) *p++ = (u8)c; return d; }
void *memcpy(void *d, const void *s, u32 n) { u8 *a = d; const u8 *b = s; while (n--) *a++ = *b++; return d; }
void *memmove(void *d, const void *s, u32 n) {
    u8 *a = d; const u8 *b = s;
    if (a < b) while (n--) *a++ = *b++;
    else { a += n; b += n; while (n--) *--a = *--b; }
    return d;
}
int atoi(const char *s) {
    int n = 0, neg = 0;
    while (*s == ' ') s++;
    if (*s == '-') neg = 1, s++;
    while (*s >= '0' && *s <= '9') n = n * 10 + (*s++ - '0');
    return neg ? -n : n;
}
void itoa(i32 v, char *buf) {
    char tmp[12]; int i = 0; u32 u = v < 0 ? -(u32)v : (u32)v;
    do tmp[i++] = '0' + u % 10; while (u /= 10);
    if (v < 0) *buf++ = '-';
    while (i) *buf++ = tmp[--i];
    *buf = 0;
}
static void put_hex(u32 v) { puts("0x"); for (int i = 28; i >= 0; i -= 4) putc("0123456789ABCDEF"[(v >> i) & 15]); }

/* supports %s %d %u %x %c %% */
void printf(const char *fmt, ...) {
    va_list ap; va_start(ap, fmt); char buf[16];
    for (; *fmt; fmt++) {
        if (*fmt != '%') { putc(*fmt); continue; }
        switch (*++fmt) {
        case 's': puts(va_arg(ap, const char *)); break;
        case 'd': itoa(va_arg(ap, i32), buf); puts(buf); break;
        case 'u': { u32 u = va_arg(ap, u32); int i = 15; buf[i] = 0; do buf[--i] = '0' + u % 10; while (u /= 10); puts(buf + i); break; }
        case 'x': put_hex(va_arg(ap, u32)); break;
        case 'c': putc((char)va_arg(ap, int)); break;
        case '%': putc('%'); break;
        case 0: va_end(ap); return;
        }
    }
    va_end(ap);
}
