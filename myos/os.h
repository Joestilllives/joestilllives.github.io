/* os.h - shared declarations for MyOS */
#ifndef OS_H
#define OS_H

typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;
typedef unsigned long long u64;
typedef int i32;

static inline void outb(u16 p, u8 v) { __asm__ volatile("outb %0,%1" :: "a"(v), "Nd"(p)); }
static inline u8 inb(u16 p) { u8 v; __asm__ volatile("inb %1,%0" : "=a"(v) : "Nd"(p)); return v; }
static inline void outw(u16 p, u16 v) { __asm__ volatile("outw %0,%1" :: "a"(v), "Nd"(p)); }
static inline void io_wait(void) { outb(0x80, 0); }

typedef struct { u32 edi, esi, ebp, esp, ebx, edx, ecx, eax, int_no, err; u32 eip, cs, eflags; } regs_t;

/* lib.c */
u32  strlen(const char *s);
int  strcmp(const char *a, const char *b);
int  strncmp(const char *a, const char *b, u32 n);
void strcpy(char *d, const char *s);
void strncpy0(char *d, const char *s, u32 n);
void *memset(void *d, int c, u32 n);
void *memcpy(void *d, const void *s, u32 n);
void *memmove(void *d, const void *s, u32 n);
int  atoi(const char *s);
void itoa(i32 v, char *buf);
void printf(const char *fmt, ...);

/* screen.c */
void screen_init(u32 mbinfo);
void putc(char c);
void puts(const char *s);
void screen_clear(void);
void screen_set_color(u32 fg, u32 bg);
void screen_get_color(u32 *fg, u32 *bg);
void screen_fill_cell(int col, int row, u32 color);
void screen_put_at(int col, int row, char c, u32 fg, u32 bg);
int  screen_cols(void);
int  screen_rows(void);
void screen_cursor(int show);
const char *screen_mode(void);

/* kernel.c */
extern volatile u32 ticks;
extern u32 mem_kb;
void sleep_ms(u32 ms);
void reboot(void);
void shutdown(void);

/* keyboard.c */
#define KEY_UP    0x80
#define KEY_DOWN  0x81
#define KEY_LEFT  0x82
#define KEY_RIGHT 0x83
void keyboard_init(void);
void keyboard_irq(void);
int  getkey(void);      /* blocking */
int  trykey(void);      /* -1 if none */

/* fs.c */
int  fs_write(const char *name, const char *data, int append);
const char *fs_read(const char *name);
int  fs_remove(const char *name);
void fs_list(void);
void fs_init(void);

/* shell.c / snake.c */
void shell_run(void);
void snake_run(void);

/* pet.c - Bit, the companion */
void pet_idle(void);
void pet_room(void);
void pet_comment(void);
void pet_feed_quick(void);
const char *pet_name(void);

#endif
