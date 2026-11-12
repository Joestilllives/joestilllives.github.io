/* kernel.c - interrupts, timer, and the kernel entry point */
#include "os.h"

volatile u32 ticks;          /* 100 Hz timer ticks since boot */
u32 mem_kb;

struct idt_entry { u16 lo, sel; u8 zero, flags; u16 hi; } __attribute__((packed));
static struct idt_entry idt[48];
static struct { u16 limit; u32 base; } __attribute__((packed)) idt_ptr;
extern u32 isr_table[];

static const char *exceptions[] = {
    "Divide by zero", "Debug", "NMI", "Breakpoint", "Overflow", "Bound range", "Invalid opcode",
    "Device not available", "Double fault", "Coprocessor overrun", "Invalid TSS", "Segment not present",
    "Stack fault", "General protection fault", "Page fault", "Reserved", "x87 FPU error",
    "Alignment check", "Machine check", "SIMD error" };

void isr_handler(regs_t *r) {
    if (r->int_no < 32) {
        screen_set_color(0xFFFFFF, 0xAA0000);
        screen_clear();
        printf("\n  *** KERNEL PANIC ***\n\n  %s (exception %d)\n  error code: %x\n  EIP: %x\n\n  System halted. Press the power button to restart.",
               r->int_no < 20 ? exceptions[r->int_no] : "Reserved", r->int_no, r->err, r->eip);
        for (;;) __asm__ volatile("cli; hlt");
    }
    if (r->int_no == 32) ticks++;
    else if (r->int_no == 33) keyboard_irq();
    if (r->int_no >= 40) outb(0xA0, 0x20);
    outb(0x20, 0x20);
}

static void pic_remap(void) {
    outb(0x20, 0x11); io_wait(); outb(0xA0, 0x11); io_wait();
    outb(0x21, 32);   io_wait(); outb(0xA1, 40);   io_wait();
    outb(0x21, 4);    io_wait(); outb(0xA1, 2);    io_wait();
    outb(0x21, 1);    io_wait(); outb(0xA1, 1);    io_wait();
    outb(0x21, 0xFC); outb(0xA1, 0xFF);           /* enable only timer + keyboard */
}

static void idt_init(void) {
    for (int i = 0; i < 48; i++)
        idt[i] = (struct idt_entry){ isr_table[i] & 0xFFFF, 0x08, 0, 0x8E, isr_table[i] >> 16 };
    idt_ptr.limit = sizeof(idt) - 1; idt_ptr.base = (u32)idt;
    __asm__ volatile("lidt %0" :: "m"(idt_ptr));
}

static void pit_init(void) {        /* 100 Hz */
    u32 div = 1193182 / 100;
    outb(0x43, 0x36); outb(0x40, div & 0xFF); outb(0x40, div >> 8);
}

void sleep_ms(u32 ms) {
    u32 end = ticks + (ms + 9) / 10;
    while (ticks < end) __asm__ volatile("hlt");
}

void reboot(void) {
    while (inb(0x64) & 2);
    outb(0x64, 0xFE);                               /* pulse CPU reset line */
    struct { u16 l; u32 b; } __attribute__((packed)) z = {0, 0};
    __asm__ volatile("lidt %0; int $3" :: "m"(z));  /* fallback: triple fault */
}

void shutdown(void) {
    outw(0x604, 0x2000);   /* QEMU */
    outw(0xB004, 0x2000);  /* Bochs / older QEMU */
    outw(0x4004, 0x3400);  /* VirtualBox */
    __asm__ volatile("cli");
    screen_set_color(0xFFB000, 0x000000); screen_clear();
    puts("\n  It is now safe to turn off your computer.");
    for (;;) __asm__ volatile("hlt");
}

void kmain(u32 magic, u32 mbinfo) {
    if (magic != 0x2BADB002) mbinfo = 0;
    screen_init(mbinfo);
    if (mbinfo && (*(u32 *)mbinfo & 1)) mem_kb = ((u32 *)mbinfo)[2] + 1024;
    idt_init();
    pic_remap();
    pit_init();
    keyboard_init();
    fs_init();
    __asm__ volatile("sti");
    shell_run();
}
