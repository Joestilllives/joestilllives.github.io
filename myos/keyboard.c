/* keyboard.c - PS/2 keyboard driver (scancode set 1) */
#include "os.h"

static const char normal[128] = {
    0, 27, '1','2','3','4','5','6','7','8','9','0','-','=','\b','\t',
    'q','w','e','r','t','y','u','i','o','p','[',']','\n', 0,
    'a','s','d','f','g','h','j','k','l',';','\'','`', 0, '\\',
    'z','x','c','v','b','n','m',',','.','/', 0, '*', 0, ' ' };
static const char shifted[128] = {
    0, 27, '!','@','#','$','%','^','&','*','(',')','_','+','\b','\t',
    'Q','W','E','R','T','Y','U','I','O','P','{','}','\n', 0,
    'A','S','D','F','G','H','J','K','L',':','"','~', 0, '|',
    'Z','X','C','V','B','N','M','<','>','?', 0, '*', 0, ' ' };

static volatile u8 buf[64];
static volatile u32 head, tail;
static int shift, ctrl, caps, ext;

static void push(int k) { u32 n = (head + 1) % 64; if (n != tail) { buf[head] = k; head = n; } }

void keyboard_init(void) {
    while (inb(0x64) & 1) inb(0x60);   /* drain anything pending */
}

void keyboard_irq(void) {
    u8 sc = inb(0x60);
    if (sc == 0xE0) { ext = 1; return; }
    int rel = sc & 0x80; sc &= 0x7F;
    if (ext) {
        ext = 0;
        if (sc == 0x1D) { ctrl = !rel; return; }
        if (rel) return;
        if (sc == 0x48) push(KEY_UP); else if (sc == 0x50) push(KEY_DOWN);
        else if (sc == 0x4B) push(KEY_LEFT); else if (sc == 0x4D) push(KEY_RIGHT);
        else if (sc == 0x1C) push('\n');
        return;
    }
    if (sc == 0x2A || sc == 0x36) { shift = !rel; return; }
    if (sc == 0x1D) { ctrl = !rel; return; }
    if (rel) return;
    if (sc == 0x3A) { caps = !caps; return; }
    char c = shift ? shifted[sc] : normal[sc];
    if (caps && ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'))) c ^= 0x20;
    if (ctrl && c >= 'a' && c <= 'z') c = c - 'a' + 1;   /* Ctrl+C = 3, etc. */
    if (c) push((u8)c);
}

int trykey(void) {
    if (head == tail) return -1;
    int k = buf[tail]; tail = (tail + 1) % 64; return k;
}
int getkey(void) {
    int k;
    while ((k = trykey()) < 0) { pet_idle(); __asm__ volatile("hlt"); }
    return k;
}
