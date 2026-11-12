/* fs.c - a tiny in-memory filesystem (contents vanish on reboot) */
#include "os.h"

#define MAXFILES 32
#define MAXSIZE  4096
static struct { char name[32]; char data[MAXSIZE]; int used; } files[MAXFILES];

static int find(const char *name) {
    for (int i = 0; i < MAXFILES; i++) if (files[i].used && !strcmp(files[i].name, name)) return i;
    return -1;
}

int fs_write(const char *name, const char *data, int append) {
    int i = find(name);
    if (i < 0) {
        for (i = 0; i < MAXFILES && files[i].used; i++);
        if (i == MAXFILES) return -1;
        files[i].used = 1; strncpy0(files[i].name, name, 32); files[i].data[0] = 0;
    }
    u32 off = append ? strlen(files[i].data) : 0;
    strncpy0(files[i].data + off, data, MAXSIZE - off);
    return 0;
}
const char *fs_read(const char *name) { int i = find(name); return i < 0 ? 0 : files[i].data; }
int fs_remove(const char *name) { int i = find(name); if (i < 0) return -1; files[i].used = 0; return 0; }
void fs_list(void) {
    int n = 0;
    for (int i = 0; i < MAXFILES; i++)
        if (files[i].used) { printf("  %s", files[i].name); for (int s = strlen(files[i].name); s < 24; s++) putc(' '); printf("%u bytes\n", strlen(files[i].data)); n++; }
    if (!n) puts("  (no files)\n");
}
void fs_init(void) {
    fs_write("readme.txt",
        "Welcome to MyOS!\n"
        "This is a tiny operating system written from scratch in C and assembly.\n"
        "Files live in RAM, so they disappear when you reboot.\n"
        "Type 'help' to see what you can do.\n", 0);
    fs_write("todo.txt", "- learn how computers boot\n- write a kernel\n- play snake\n", 0);
}
