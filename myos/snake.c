/* snake.c - a little game to show off the framebuffer + keyboard + timer */
#include "os.h"

#define MAXLEN 512
static int sx[MAXLEN], sy[MAXLEN];

static u32 rng = 12345;
static int rnd(int n) { rng = rng * 1103515245 + 12345 + ticks; return (rng >> 16) % n; }

void snake_run(void) {
    u32 fg, bg; screen_get_color(&fg, &bg);
    int W = screen_cols(), H = screen_rows();
    if (W > 60) W = 60;
    if (H > 30) H = 30;
    int ox = (screen_cols() - W) / 2, oy = (screen_rows() - H) / 2;
    const u32 wall = 0x444466, field = 0x0A0A14, body = 0x33DD66, head = 0x99FF99, food = 0xFF4455;

    screen_cursor(0);
    screen_set_color(fg, 0x000000); screen_clear();
    for (int y = 0; y < H; y++)
        for (int x = 0; x < W; x++)
            screen_fill_cell(ox + x, oy + y, (x == 0 || y == 0 || x == W - 1 || y == H - 1) ? wall : field);

    int len = 4, dx = 1, dy = 0, fx, fy, score = 0, speed = 120;
    for (int i = 0; i < len; i++) { sx[i] = W / 2 - i; sy[i] = H / 2; }
    #define PLACE_FOOD() do { fx = 1 + rnd(W - 2); fy = 1 + rnd(H - 2); } while (0)
    PLACE_FOOD();

    for (;;) {
        char msg[40]; strcpy(msg, " Score: "); itoa(score, msg + 8); strcpy(msg + strlen(msg), "   q = quit ");
        for (int i = 0; msg[i]; i++) screen_put_at(ox + 2 + i, oy, msg[i], 0xFFFFFF, wall);
        screen_put_at(ox + fx, oy + fy, '@', 0xFFFFFF, food);
        for (int i = 0; i < len; i++) screen_fill_cell(ox + sx[i], oy + sy[i], i ? body : head);

        sleep_ms(speed);
        int k;
        while ((k = trykey()) >= 0) {
            if (k == 'q' || k == 27) goto out;
            if ((k == KEY_UP || k == 'w') && dy != 1) dx = 0, dy = -1;
            if ((k == KEY_DOWN || k == 's') && dy != -1) dx = 0, dy = 1;
            if ((k == KEY_LEFT || k == 'a') && dx != 1) dx = -1, dy = 0;
            if ((k == KEY_RIGHT || k == 'd') && dx != -1) dx = 1, dy = 0;
        }
        int nx = sx[0] + dx, ny = sy[0] + dy, dead = nx <= 0 || ny <= 0 || nx >= W - 1 || ny >= H - 1;
        for (int i = 0; i < len - 1; i++) if (sx[i] == nx && sy[i] == ny) dead = 1;
        if (dead) {
            const char *go = "  GAME OVER - press any key  ";
            for (int i = 0; go[i]; i++) screen_put_at(ox + (W - (int)strlen(go)) / 2 + i, oy + H / 2, go[i], 0xFFFFFF, 0xAA0000);
            sleep_ms(400); while (trykey() >= 0); getkey();
            goto out;
        }
        int grow = (nx == fx && ny == fy);
        if (!grow) screen_fill_cell(ox + sx[len - 1], oy + sy[len - 1], field);
        else { if (len < MAXLEN) len++; score += 10; if (speed > 50) speed -= 5; PLACE_FOOD(); }
        for (int i = len - 1; i > 0; i--) sx[i] = sx[i - 1], sy[i] = sy[i - 1];
        sx[0] = nx; sy[0] = ny;
    }
out:
    screen_set_color(fg, bg); screen_clear(); screen_cursor(1);
    printf("  Thanks for playing! Final score: %d\n", score);
}
