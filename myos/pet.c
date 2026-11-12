/* pet.c - Bit, the creature that lives inside MyOS.
 * Bit has needs (food, energy, fun) that change over time, a mood that
 * follows from them, a face that blinks and breathes, and a simple
 * rule-based chat. It is not real AI - just a lot of little rules. */
#include "os.h"

static char name[16] = "Bit", owner[24];
static int food = 80, energy = 90, fun = 70, asleep;
static u32 last_tick, born, last_face_draw;
static u32 seed = 7;

static int rnd(int n) { seed = seed * 1103515245 + 12345 + ticks; return (seed >> 16) % n; }
static int clamp(int v) { return v < 0 ? 0 : v > 100 ? 100 : v; }
static const char *pick(const char **list, int n) { return list[rnd(n)]; }

/* ---------- needs and mood ---------- */
enum { HAPPY, OK, HUNGRY, TIRED, SAD, SLEEPING };

static void update(void) {
    if (!last_tick) last_tick = born = ticks;
    while (ticks - last_tick >= 300) {          /* every 3 seconds */
        last_tick += 300;
        u32 t = (last_tick - born) / 300;
        if (t % 2 == 0) food = clamp(food - 1);
        if (t % 3 == 0) fun = clamp(fun - 1);
        if (asleep) { energy = clamp(energy + 3); if (energy >= 100) asleep = 0; }
        else if (t % 4 == 0) energy = clamp(energy - 1);
        if (food == 0) fun = clamp(fun - 1);
        if (energy == 0) asleep = 1;            /* falls asleep on its own */
    }
}

static int mood(void) {
    if (asleep) return SLEEPING;
    if (food < 25) return HUNGRY;
    if (energy < 25) return TIRED;
    if (fun < 25) return SAD;
    if (food > 60 && fun > 60 && energy > 50) return HAPPY;
    return OK;
}
static const char *mood_word[] = {"happy", "okay", "hungry", "sleepy", "lonely", "asleep"};
static const u32 mood_color[] = {0x55FF88, 0xFFFFAA, 0xFFAA44, 0xAAAAFF, 0x88AACC, 0x7777CC};

static int blinking(void) { return !asleep && (ticks % 400) < 15; }
static const char *eyes(int m) {
    if (blinking()) return "- -";
    switch (m) { case HAPPY: return "^ ^"; case HUNGRY: return "O O"; case TIRED: return "= =";
                 case SAD: return "; ;"; case SLEEPING: return "- -"; default: return "o o"; }
}
static const char *mouth(int m) {
    switch (m) { case HAPPY: return "\\_/"; case HUNGRY: return " o "; case TIRED: return " ~ ";
                 case SAD: return "/-\\"; case SLEEPING: return " . "; default: return "---"; }
}

/* ---------- small face in the shell's corner ---------- */
void pet_idle(void) {
    update();
    if (ticks - last_face_draw < 10) return;      /* redraw ~10x per second */
    last_face_draw = ticks;
    u32 fg, bg; screen_get_color(&fg, &bg);
    int m = mood();
    char buf[40];
    /* build "(e_e)" from the eyes, e.g. (^_^) */
    char face[8] = {'(', eyes(m)[0], m == SLEEPING ? '.' : '_', eyes(m)[2], ')', 0};
    strcpy(buf, " "); strcpy(buf + 1, name); strcpy(buf + strlen(buf), " "); strcpy(buf + strlen(buf), face);
    if (m == SLEEPING) strcpy(buf + strlen(buf), (ticks / 50) % 2 ? " z" : " Z");
    else strcpy(buf + strlen(buf), "  ");
    strcpy(buf + strlen(buf), " ");
    int x = screen_cols() - strlen(buf);
    for (int i = 0; buf[i]; i++) screen_put_at(x + i, 0, buf[i], mood_color[m], bg == 0x000000 ? 0x111111 : bg);
}

/* ---------- chat ---------- */
static int has(const char *s, const char *word) {
    for (int n = strlen(word); *s; s++) {
        int i = 0;
        while (i < n && s[i] && (s[i] | 32) == (word[i] | 32)) i++;
        if (i == n) return 1;
    }
    return 0;
}
static char reply[160];
static void say(const char *a) { strncpy0(reply, a, sizeof reply); }
static void say2(const char *a, const char *b) { say(a); strncpy0(reply + strlen(reply), b, sizeof reply - strlen(reply)); }
static void say3(const char *a, const char *b, const char *c) { say2(a, b); strncpy0(reply + strlen(reply), c, sizeof reply - strlen(reply)); }

static void grab_word_after(const char *s, const char *key, char *out, int max) {
    for (; *s; s++) {
        if (!strncmp(s, key, strlen(key))) {
            s += strlen(key);
            while (*s == ' ') s++;
            int i = 0;
            while (s[i] && s[i] != ' ' && s[i] != '.' && s[i] != '!' && i < max - 1) { out[i] = s[i]; i++; }
            out[i] = 0;
            if (out[0] >= 'a' && out[0] <= 'z') out[0] -= 32;
            return;
        }
    }
}

static void respond(const char *in) {
    update();
    const char *you = owner[0] ? owner : "friend";
    if (asleep && !has(in, "wake")) {
        static const char *z[] = {"Zzz... zzz...", "*snores softly*", "mmh... five more minutes... zzz",
                                  "*mumbles something about electric sheep*"};
        say(pick(z, 4)); return;
    }
    if (has(in, "wake")) {
        if (!asleep) { say("I'm already awake, silly!"); return; }
        asleep = 0; fun = clamp(fun - 10); say("*yawns* ...you woke me up. I was dreaming in binary."); return;
    }
    if (has(in, "my name is") || has(in, "i am ") || has(in, "i'm ") || has(in, "call me")) {
        char tmp[24] = "";
        if (has(in, "my name is")) grab_word_after(in, "my name is", tmp, 24);
        else if (has(in, "call me")) grab_word_after(in, "call me", tmp, 24);
        else if (has(in, "i'm ")) grab_word_after(in, "i'm ", tmp, 24);
        else grab_word_after(in, "i am ", tmp, 24);
        if (tmp[0]) { strcpy(owner, tmp); fun = clamp(fun + 10); say3("Nice to meet you, ", owner, "! I'll remember that (until you reboot me)."); return; }
    }
    if (has(in, "your name is") || has(in, "call you") || has(in, "rename")) {
        char tmp[16] = "";
        if (has(in, "your name is")) grab_word_after(in, "your name is", tmp, 16);
        else if (has(in, "call you")) grab_word_after(in, "call you", tmp, 16);
        else grab_word_after(in, "rename", tmp, 16);
        if (tmp[0]) { strcpy(name, tmp); say3("Ooh, ", name, "! I love my new name!"); return; }
    }
    if (has(in, "feed") || has(in, "food") || has(in, "eat") || has(in, "hungry") || has(in, "snack")) {
        if (food > 90) { say("I'm stuffed! Not one more byte."); return; }
        food = clamp(food + 35); fun = clamp(fun + 5);
        static const char *f[] = {"*munch munch* Delicious bytes!", "Yum! Fresh bits, just how I like them.",
                                  "Mmm, tastes like 0x1BADB002.", "*nom nom* Thank you!"};
        say(pick(f, 4)); return;
    }
    if (has(in, "play") || has(in, "game") || has(in, "fun")) {
        if (energy < 15) { say("Too tired to play... maybe after a nap?"); return; }
        fun = clamp(fun + 30); energy = clamp(energy - 10); food = clamp(food - 5);
        static const char *p[] = {"Wheee! *bounces around the framebuffer*", "Tag, you're it! ...wait, you can't leave the keyboard.",
                                  "That was fun! Try the 'snake' command, it's my cousin.", "*does a backflip over the cursor*"};
        say(pick(p, 4)); return;
    }
    if (has(in, "sleep") || has(in, "nap") || has(in, "bed") || has(in, "tired")) {
        if (energy > 85) { say("But I'm not sleepy at all!"); return; }
        asleep = 1; say("Okay... goodnight... *curls up* zzz"); return;
    }
    if (has(in, "pet") || has(in, "hug") || has(in, "love") || has(in, "cuddle") || has(in, "good")) {
        fun = clamp(fun + 15);
        static const char *l[] = {"*purrs in 8-bit*", "Aww! I love you too!", "*happy wiggle*", "You're my favorite user."};
        say(pick(l, 4)); return;
    }
    if (has(in, "stupid") || has(in, "hate") || has(in, "bad") || has(in, "dumb") || has(in, "shut up")) {
        fun = clamp(fun - 20); say("...that hurt my feelings. :("); return;
    }
    if (has(in, "how are you") || has(in, "how do you feel") || has(in, "you ok")) {
        int m = mood();
        if (m == HAPPY) say2("I feel great! Thanks for asking, ", you);
        else if (m == HUNGRY) say("Honestly? Really hungry. Could you feed me?");
        else if (m == TIRED) say("Sleepy... my eyes keep closing.");
        else if (m == SAD) say("A bit lonely. Play with me?");
        else say("I'm doing okay! Just living in your RAM.");
        if (reply[strlen(reply) - 1] != '.' && reply[strlen(reply) - 1] != '?' && reply[strlen(reply) - 1] != '!') strcpy(reply + strlen(reply), "!");
        return;
    }
    if (has(in, "alive") || has(in, "who are you") || has(in, "what are you") || has(in, "real")) {
        say2(name, " here! I'm a little creature made of rules and numbers. Am I alive? I eat, sleep and feel... sort of!");
        return;
    }
    if (has(in, "joke")) {
        static const char *j[] = {"Why do programmers prefer dark mode? Because light attracts bugs!",
            "I'd tell you a UDP joke, but you might not get it.", "There are 10 kinds of people: those who get binary and those who don't.",
            "My kernel has no networking. So no, I can't 'stay connected'.", "Why was the computer cold? It left its Windows open."};
        say(pick(j, 5)); fun = clamp(fun + 5); return;
    }
    if (has(in, "what's my name") || has(in, "who am i") || has(in, "my name?")) {
        if (owner[0]) say3("You're ", owner, "! I could never forget you. (Unless you reboot.)");
        else say("I don't know yet! Tell me: 'my name is ...'");
        return;
    }
    if (has(in, "your name")) { say3("I'm ", name, "! You can rename me: 'your name is ...'"); return; }
    if (has(in, "age") || has(in, "old")) {
        char n[12]; itoa((ticks - born) / 6000, n);
        say3("I was born when the computer started, ", n, " minutes ago. Still a baby!"); return;
    }
    if (has(in, "thank")) { say("You're welcome! <3"); return; }
    if (has(in, "hi") || has(in, "hello") || has(in, "hey") || has(in, "yo")) {
        static const char *h[] = {"Hi hi! ", "Hello, ", "Hey there, ", "Oh! Hi, "};
        say3(pick(h, 4), you, "!"); fun = clamp(fun + 3); return;
    }
    static const char *d[] = {"Hmm? I don't understand, but I like hearing from you.", "*tilts head*",
        "Interesting... tell me more!", "I'm just a small creature. Try: feed, play, sleep, joke, or 'my name is ...'",
        "Beep boop? (That means 'what?')"};
    say(pick(d, 5));
}

/* ---------- Bit's room (full screen) ---------- */
static char log[8][80];
static u32 logcol[8];
static void log_add(const char *who, const char *msg, u32 color) {
    for (int i = 0; i < 7; i++) { strcpy(log[i], log[i + 1]); logcol[i] = logcol[i + 1]; }
    strncpy0(log[7], who, 80); strncpy0(log[7] + strlen(log[7]), msg, 80 - strlen(log[7]));
    logcol[7] = color;
}

/* add "who: msg" to the chat log, wrapping long messages onto extra lines */
static void log_say(const char *who, const char *msg, u32 color) {
    char line[80]; int width = 74 - strlen(who) - 2, first = 1;
    while (*msg) {
        int n = strlen(msg);
        if (n > width) { n = width; while (n > 10 && msg[n] != ' ') n--; }
        strcpy(line, first ? who : ""); if (!first) for (int i = 0; i < (int)strlen(who); i++) line[i] = ' ', line[i + 1] = 0;
        strcpy(line + strlen(line), "  "); if (first) line[strlen(line) - 2] = ':';
        int o = strlen(line); for (int i = 0; i < n; i++) line[o + i] = msg[i]; line[o + n] = 0;
        log_add(line, "", color);
        msg += n; while (*msg == ' ') msg++; first = 0;
    }
}

static void text(int x, int y, const char *s, u32 fg, u32 bg, int width) {
    int i = 0;
    for (; s[i] && (width <= 0 || i < width); i++) screen_put_at(x + i, y, s[i], fg, bg);
    for (; i < width; i++) screen_put_at(x + i, y, ' ', fg, bg);
}
static void bar(int x, int y, const char *label, int v, u32 color, u32 bg) {
    text(x, y, label, 0xCCCCCC, bg, 8);
    for (int i = 0; i < 20; i++) screen_put_at(x + 8 + i, y, i < v / 5 ? '#' : '.', i < v / 5 ? color : 0x444444, bg);
    char n[8]; itoa(v, n); strcpy(n + strlen(n), "% "); text(x + 29, y, n, 0xCCCCCC, bg, 5);
}

static void draw_room(int bob, const char *input, u32 bg) {
    int m = mood(); u32 c = mood_color[m];
    int W = screen_cols() < 80 ? screen_cols() : 80, ox = (screen_cols() - W) / 2;
    char title[60]; strcpy(title, "  "); strcpy(title + 2, name); strcpy(title + strlen(title), "'s room   (type to talk, Esc to leave)");
    text(ox, 0, title, 0xFFFFFF, 0x333355, W);

    const char *e = eyes(m), *mo = mouth(m);
    char l2[20] = "  |  e   e  |", l4[20] = "   \\  mmm  /";
    l2[5] = e[0]; l2[9] = e[2]; l4[6] = mo[0]; l4[7] = mo[1]; l4[8] = mo[2];
    const char *body[] = {"    .-\"\"\"-.", "   /       \\", l2, "  |    *    |", l4, "    '-...-'",
                          bob ? "    /|   |\\" : "    \\|   |/", "     |___|", bob ? "     ^   ^" : "    _/   \\_"};
    if (m != HAPPY) body[6] = "    /|   |\\";
    int cy = 3;
    for (int i = 0; i < 11; i++) text(ox + 4, cy - 1 + i, "", c, bg, 16);
    for (int i = 0; i < 9; i++) text(ox + 4, cy + (bob && m != SLEEPING ? 0 : 1) + i, body[i], c, bg, 16);
    text(ox + 18, cy, m == SLEEPING ? ((ticks / 60) % 2 ? " z Z" : "Z z ") : "    ", 0x9999FF, bg, 4);

    text(ox + 32, 3, name, 0xFFFFFF, bg, 20);
    char ms[40]; strcpy(ms, "Feeling: "); strcpy(ms + 9, mood_word[m]);
    text(ox + 32, 4, ms, c, bg, 30);
    bar(ox + 32, 6, "Food", food, 0xFFAA44, bg);
    bar(ox + 32, 7, "Energy", energy, 0x66AAFF, bg);
    bar(ox + 32, 8, "Fun", fun, 0xFF66CC, bg);
    text(ox + 32, 10, "Try: feed, play, sleep, wake up,", 0x888888, bg, 40);
    text(ox + 32, 11, "joke, how are you, my name is ...", 0x888888, bg, 40);

    for (int i = 0; i < 8; i++) text(ox + 1, 14 + i, log[i], logcol[i], bg, W - 2);
    char in[90] = "> "; strncpy0(in + 2, input, 76);
    if ((ticks / 50) % 2) strcpy(in + strlen(in), "_");
    text(ox + 1, 23, in, 0xFFFFFF, bg, W - 2);
}

void pet_room(void) {
    u32 fg, bg; screen_get_color(&fg, &bg);
    screen_cursor(0); screen_clear();
    char input[70] = ""; int len = 0;
    char greet[100]; strcpy(greet, owner[0] ? "Yay, it's you, " : "Oh! A visitor! Hi there");
    if (owner[0]) { strcpy(greet + strlen(greet), owner); strcpy(greet + strlen(greet), "!"); }
    else strcpy(greet + strlen(greet), "! What's your name?");
    if (asleep) strcpy(greet, "Zzz... (Bit is sleeping. Say 'wake up'.)");
    log_say(name, greet, mood_color[mood()]);

    u32 last = 0;
    for (;;) {
        update();
        int k = trykey();
        if (k == 27) break;
        if (k == '\b' && len) input[--len] = 0;
        else if (k == '\n' && len) {
            if (!strcmp(input, "bye") || !strcmp(input, "exit") || !strcmp(input, "quit")) break;
            log_say(owner[0] ? owner : "You", input, 0xFFFFFF);
            respond(input);
            log_say(name, reply, mood_color[mood()]);
            len = 0; input[0] = 0;
        }
        else if (k >= 32 && k < 127 && len < 68) { input[len++] = k; input[len] = 0; }
        if (k >= 0 || ticks - last >= 5) { last = ticks; draw_room((ticks / (asleep ? 150 : 60)) % 2, input, bg); }
        if (k < 0) __asm__ volatile("hlt");
    }
    screen_set_color(fg, bg); screen_clear(); screen_cursor(1);
    printf("  %s waves goodbye. (It keeps living in the top-right corner.)\n", name);
}

/* Called by the shell after each command: Bit sometimes speaks up. */
void pet_comment(void) {
    update();
    if (rnd(4)) return;
    int m = mood(); const char *msg = 0;
    if (m == HUNGRY) msg = "I'm hungry... (type 'pet' and feed me?)";
    else if (m == TIRED) msg = "*yawn* I could use a nap.";
    else if (m == SAD) msg = "Psst... come play with me? ('pet')";
    else if (m == HAPPY && !rnd(3)) msg = owner[0] ? "I like it when you're here." : "Having fun! Tell me your name sometime.";
    if (!msg) return;
    u32 fg, bg; screen_get_color(&fg, &bg);
    screen_set_color(mood_color[m], bg); printf("  %s: %s\n", name, msg); screen_set_color(fg, bg);
}

void pet_feed_quick(void) { respond("feed"); printf("  %s: %s\n", name, reply); }
const char *pet_name(void) { return name; }
