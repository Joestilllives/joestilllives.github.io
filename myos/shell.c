/* shell.c - the command line */
#include "os.h"
extern char kernel_end[];

#define HIST 16
static char history[HIST][128];
static int hist_count;

static const struct { const char *name; u32 fg, bg; } themes[] = {
    {"default", 0xD0D0D0, 0x101828}, {"matrix", 0x33FF66, 0x000000}, {"amber", 0xFFB000, 0x140C00},
    {"ocean", 0xE0F4FF, 0x003366}, {"light", 0x202020, 0xF2F2EA}, {"retro", 0xFFFFFF, 0x0000AA} };

static void readline(char *out, int max) {
    int len = 0, h = hist_count;
    for (;;) {
        int k = getkey();
        if (k == '\n') { putc('\n'); out[len] = 0; break; }
        if (k == '\b') { if (len) { len--; putc('\b'); } continue; }
        if (k == 3) { puts("^C\n"); len = 0; out[0] = 0; return; }
        if (k == KEY_UP || k == KEY_DOWN) {
            if (k == KEY_UP && h > 0) h--;
            else if (k == KEY_DOWN && h < hist_count) h++;
            else continue;
            while (len) { putc('\b'); len--; }
            const char *src = h < hist_count ? history[h % HIST] : "";
            while (src[len] && len < max - 1) putc(out[len] = src[len]), len++;
            continue;
        }
        if (k >= 32 && k < 127 && len < max - 1) { out[len++] = k; putc(k); }
    }
    if (len) { strcpy(history[hist_count % HIST], out); hist_count++; }
}

static u8 cmos(u8 reg) { outb(0x70, reg); return inb(0x71); }
static int bcd(u8 v, int is_bcd) { return is_bcd ? (v & 15) + (v >> 4) * 10 : v; }

static void cmd_date(void) {
    while (cmos(0x0A) & 0x80);
    int b = !(cmos(0x0B) & 4);
    int s = bcd(cmos(0), b), m = bcd(cmos(2), b), h = bcd(cmos(4) & 0x7F, b);
    int d = bcd(cmos(7), b), mo = bcd(cmos(8), b), y = bcd(cmos(9), b);
    printf("  20%d%d-%d%d-%d%d %d%d:%d%d:%d%d (hardware clock, usually UTC)\n",
           y / 10, y % 10, mo / 10, mo % 10, d / 10, d % 10, h / 10, h % 10, m / 10, m % 10, s / 10, s % 10);
}

static void cmd_calc(const char *e) {
    int a = atoi(e);
    while (*e == ' ') e++;
    if (*e == '-') e++;
    while (*e >= '0' && *e <= '9') e++;
    while (*e == ' ') e++;
    char op = *e++; int b = atoi(e), r;
    switch (op) {
    case '+': r = a + b; break; case '-': r = a - b; break; case '*': case 'x': r = a * b; break;
    case '/': if (!b) { puts("  can't divide by zero\n"); return; } r = a / b; break;
    case '%': if (!b) { puts("  can't divide by zero\n"); return; } r = a % b; break;
    default: puts("  usage: calc 12 * 7   (operators: + - * / %)\n"); return;
    }
    printf("  = %d\n", r);
}

static void banner(void) {
    u32 fg, bg; screen_get_color(&fg, &bg);
    screen_set_color(0x66CCFF, bg);
    puts("\n   __  __        ___  ____  \n"
         "  |  \\/  |_   _ / _ \\/ ___| \n"
         "  | |\\/| | | | | | | \\___ \\ \n"
         "  | |  | | |_| | |_| |___) |\n"
         "  |_|  |_|\\__, |\\___/|____/ \n"
         "          |___/              \n\n");
    screen_set_color(fg, bg);
    puts("  Built from scratch. Type 'help' for a list of commands.\n");
    screen_set_color(0x55FF88, bg);
    puts("  Something stirs in the top-right corner... Bit is awake! Type 'pet' to say hi.\n\n");
    screen_set_color(fg, bg);
}

static void help(void) {
    puts("  help              show this list\n"
         "  clear             clear the screen\n"
         "  about             about this OS\n"
         "  echo <text>       print text\n"
         "  ls                list files\n"
         "  cat <file>        show a file\n"
         "  write <f> <text>  create/overwrite a file\n"
         "  append <f> <text> add a line to a file\n"
         "  rm <file>         delete a file\n"
         "  calc <a> <op> <b> calculator, e.g. calc 6 * 7\n"
         "  date              show the hardware clock\n"
         "  uptime            time since boot\n"
         "  mem               memory info\n"
         "  theme [name]      change colors\n"
         "  pet               visit Bit, the creature living in this OS\n"
         "  feed              give Bit a snack\n"
         "  snake             play a game (arrow keys, q to quit)\n"
         "  reboot            restart the computer\n"
         "  shutdown          power off (works in VMs) / halt\n");
}

static const char *arg(const char *line) {   /* skip command word */
    while (*line && *line != ' ') line++;
    while (*line == ' ') line++;
    return line;
}

void shell_run(void) {
    char line[128];
    banner();
    for (;;) {
        u32 fg, bg; screen_get_color(&fg, &bg);
        screen_set_color(0x55FF88, bg); puts("myos");
        screen_set_color(fg, bg); puts(":");
        screen_set_color(0x66AAFF, bg); puts("/");
        screen_set_color(fg, bg); puts("$ ");
        readline(line, sizeof line);
        const char *a = arg(line);
        #define IS(c) (!strncmp(line, c, strlen(c)) && (line[strlen(c)] == ' ' || !line[strlen(c)]))
        if (!line[0]) continue;
        else if (IS("help")) help();
        else if (IS("clear") || IS("cls")) screen_clear();
        else if (IS("echo")) { puts(a); putc('\n'); }
        else if (IS("about")) printf("  MyOS 0.1 - a hobby operating system written from scratch.\n"
                                     "  32-bit x86 kernel, booted by GRUB via Multiboot.\n  Display: %s\n", screen_mode());
        else if (IS("ls")) fs_list();
        else if (IS("cat")) { const char *d = fs_read(a); if (d) puts(d); else printf("  cat: %s: no such file\n", a); }
        else if (IS("write") || IS("append")) {
            char name[32]; int i = 0;
            while (a[i] && a[i] != ' ' && i < 31) { name[i] = a[i]; i++; }
            name[i] = 0;
            const char *text = arg(a);
            if (!name[0]) { puts("  usage: write <file> <text>\n"); continue; }
            char buf[130]; strncpy0(buf, text, 128); strcpy(buf + strlen(buf), "\n");
            if (fs_write(name, buf, line[0] == 'a') < 0) puts("  disk full (32 files max)\n");
        }
        else if (IS("rm")) { if (fs_remove(a) < 0) printf("  rm: %s: no such file\n", a); }
        else if (IS("calc")) cmd_calc(a);
        else if (IS("date")) cmd_date();
        else if (IS("uptime")) { u32 s = ticks / 100; printf("  up %u min %u sec\n", s / 60, s % 60); }
        else if (IS("mem")) printf("  RAM detected: %u MB\n  Kernel ends at: %x\n", mem_kb / 1024, (u32)kernel_end);
        else if (IS("theme")) {
            int n = sizeof themes / sizeof themes[0], found = 0;
            for (int i = 0; i < n; i++)
                if (!strcmp(a, themes[i].name)) { screen_set_color(themes[i].fg, themes[i].bg); screen_clear(); found = 1; }
            if (!found) { puts("  themes:"); for (int i = 0; i < n; i++) printf(" %s", themes[i].name); puts("\n"); }
        }
        else if (IS("snake")) snake_run();
        else if (IS("pet") || IS("bit") || IS("talk")) pet_room();
        else if (IS("feed")) pet_feed_quick();
        else if (IS("reboot")) reboot();
        else if (IS("shutdown") || IS("halt")) shutdown();
        else printf("  %s: command not found (try 'help')\n", line);
        pet_comment();
    }
}
