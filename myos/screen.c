/* screen.c - text console on a graphics framebuffer (with VGA text-mode fallback) */
#include "os.h"
#include "font.h"

#define MAXC 240
#define MAXR 135
typedef struct { char ch; u32 fg, bg; } cell_t;

static cell_t cells[MAXR][MAXC];
static int cols = 80, rows = 25, cx, cy, cursor_on = 1;
static u32 cur_fg = 0xD0D0D0, cur_bg = 0x101828;

static int text_mode;                 /* 1 = legacy VGA text mode */
static u8 *fb; static u32 pitch, width, height, bpp;
static u8 rpos = 16, gpos = 8, bpos = 0;
static char mode_str[48];

static u32 pack(u32 rgb) {
    return (((rgb >> 16) & 0xFF) << rpos) | (((rgb >> 8) & 0xFF) << gpos) | ((rgb & 0xFF) << bpos);
}
static u8 vga_index(u32 rgb) {         /* nearest of the 16 VGA colors */
    static const u32 pal[16] = {0x000000,0x0000AA,0x00AA00,0x00AAAA,0xAA0000,0xAA00AA,0xAA5500,0xAAAAAA,
                                0x555555,0x5555FF,0x55FF55,0x55FFFF,0xFF5555,0xFF55FF,0xFFFF55,0xFFFFFF};
    int best = 0; u32 bd = ~0u;
    for (int i = 0; i < 16; i++) {
        int dr = ((rgb >> 16) & 255) - ((pal[i] >> 16) & 255), dg = ((rgb >> 8) & 255) - ((pal[i] >> 8) & 255), db = (rgb & 255) - (pal[i] & 255);
        u32 d = dr * dr + dg * dg + db * db;
        if (d < bd) bd = d, best = i;
    }
    return best;
}

static void draw_cell(int c, int r, int invert) {
    cell_t *k = &cells[r][c];
    u32 fg = invert ? k->bg : k->fg, bg = invert ? k->fg : k->bg;
    if (text_mode) {
        ((volatile u16 *)0xB8000)[r * cols + c] = (u8)k->ch | (vga_index(fg) | vga_index(bg) << 4) << 8;
        return;
    }
    const u8 *g = font8x16[(u8)k->ch & 127];
    u32 pf = pack(fg), pb = pack(bg);
    for (int y = 0; y < 16; y++) {
        u8 *line = fb + (r * 16 + y) * pitch + c * 8 * (bpp / 8);
        for (int x = 0; x < 8; x++) {
            u32 px = (g[y] & (0x80 >> x)) ? pf : pb;
            if (bpp == 32) ((u32 *)line)[x] = px;
            else { line[x*3] = px; line[x*3+1] = px >> 8; line[x*3+2] = px >> 16; }
        }
    }
}

static void show_cursor(int on) {
    if (!cursor_on || cy >= rows) return;
    if (text_mode) {
        u16 pos = cy * cols + cx;
        outb(0x3D4, 0x0F); outb(0x3D5, pos & 0xFF); outb(0x3D4, 0x0E); outb(0x3D5, pos >> 8);
        return;
    }
    draw_cell(cx, cy, on);
}

void screen_init(u32 mbinfo) {
    u32 *mb = (u32 *)mbinfo;
    if (mb && (mb[0] & (1 << 12)) && ((u8 *)mb)[109] == 1) {
        u8 *m = (u8 *)mb;
        fb = (u8 *)(u32)*(u64 *)(m + 88);
        pitch = *(u32 *)(m + 96); width = *(u32 *)(m + 100); height = *(u32 *)(m + 104); bpp = m[108];
        /* GRUB aligns the color info to offset 112 */
        rpos = m[112]; gpos = m[114]; bpos = m[116];
        cols = width / 8; rows = height / 16;
        if (cols > MAXC) cols = MAXC;
        if (rows > MAXR) rows = MAXR;
        char a[12], b[12], d[12]; itoa(width, a); itoa(height, b); itoa(bpp, d);
        strcpy(mode_str, a); strcpy(mode_str + strlen(mode_str), "x"); strcpy(mode_str + strlen(mode_str), b);
        strcpy(mode_str + strlen(mode_str), "x"); strcpy(mode_str + strlen(mode_str), d); strcpy(mode_str + strlen(mode_str), " framebuffer");
    } else {
        text_mode = 1; cols = 80; rows = 25; strcpy(mode_str, "80x25 VGA text mode");
    }
    screen_clear();
}

const char *screen_mode(void) { return mode_str; }
int screen_cols(void) { return cols; }
int screen_rows(void) { return rows; }
void screen_set_color(u32 fg, u32 bg) { cur_fg = fg; cur_bg = bg; }
void screen_get_color(u32 *fg, u32 *bg) { *fg = cur_fg; *bg = cur_bg; }
void screen_cursor(int show) { show_cursor(0); cursor_on = show; show_cursor(1); }

void screen_clear(void) {
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++) { cells[r][c] = (cell_t){' ', cur_fg, cur_bg}; draw_cell(c, r, 0); }
    if (!text_mode)   /* paint any leftover border pixels */
        for (u32 y = 0; y < height; y++)
            for (u32 x = (y >= (u32)rows * 16 ? 0 : cols * 8); x < width; x++) {
                u8 *p = fb + y * pitch + x * (bpp / 8); u32 v = pack(cur_bg);
                if (bpp == 32) *(u32 *)p = v; else { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; }
            }
    cx = cy = 0; show_cursor(1);
}

void screen_put_at(int c, int r, char ch, u32 fg, u32 bg) {
    if (c < 0 || r < 0 || c >= cols || r >= rows) return;
    cells[r][c] = (cell_t){ch, fg, bg}; draw_cell(c, r, 0);
}
void screen_fill_cell(int c, int r, u32 color) { screen_put_at(c, r, ' ', color, color); }

static void scroll(void) {
    /* shift text up, only redraw cells that actually changed */
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++) {
            cell_t n = r + 1 < rows ? cells[r + 1][c] : (cell_t){' ', cur_fg, cur_bg};
            cell_t *o = &cells[r][c];
            if (n.ch != o->ch || n.fg != o->fg || n.bg != o->bg) { *o = n; draw_cell(c, r, 0); }
        }
    cy = rows - 1;
}

void putc(char ch) {
    show_cursor(0);
    if (ch == '\n') { cx = 0; cy++; }
    else if (ch == '\r') cx = 0;
    else if (ch == '\b') { if (cx > 0) cx--; else if (cy > 0) cy--, cx = cols - 1; cells[cy][cx] = (cell_t){' ', cur_fg, cur_bg}; draw_cell(cx, cy, 0); }
    else if (ch == '\t') { do putc(' '); while (cx % 4); return; }
    else {
        cells[cy][cx] = (cell_t){ch, cur_fg, cur_bg}; draw_cell(cx, cy, 0);
        if (++cx >= cols) { cx = 0; cy++; }
    }
    if (cy >= rows) scroll();
    show_cursor(1);
}
void puts(const char *s) { while (*s) putc(*s++); }
