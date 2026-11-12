; boot.asm - Multiboot entry point, GDT, and interrupt stubs.
; GRUB loads us in 32-bit protected mode and jumps to _start.

MB_MAGIC  equ 0x1BADB002
MB_FLAGS  equ (1<<0) | (1<<1) | (1<<2)   ; page-align, memory info, video mode
section .multiboot
align 4
    dd MB_MAGIC
    dd MB_FLAGS
    dd -(MB_MAGIC + MB_FLAGS)
    dd 0, 0, 0, 0, 0          ; address fields (unused)
    dd 0                      ; mode_type: 0 = linear framebuffer
    dd 1024, 768, 32          ; preferred width, height, depth

section .bss
align 16
stack_bottom: resb 65536
stack_top:

section .data
align 8
gdt:
    dq 0
    dq 0x00CF9A000000FFFF     ; 0x08: kernel code
    dq 0x00CF92000000FFFF     ; 0x10: kernel data
gdt_ptr:
    dw gdt_ptr - gdt - 1
    dd gdt

section .text
global _start
extern kmain
_start:
    cli
    mov esp, stack_top
    push ebx                  ; multiboot info pointer
    push eax                  ; multiboot magic
    lgdt [gdt_ptr]
    jmp 0x08:.reload
.reload:
    mov cx, 0x10
    mov ds, cx
    mov es, cx
    mov fs, cx
    mov gs, cx
    mov ss, cx
    call kmain
.hang:
    cli
    hlt
    jmp .hang

; ---- interrupt stubs ----
extern isr_handler
%macro ISR_NOERR 1
global isr%1
isr%1:
    push dword 0
    push dword %1
    jmp isr_common
%endmacro
%macro ISR_ERR 1
global isr%1
isr%1:
    push dword %1
    jmp isr_common
%endmacro

%assign i 0
%rep 48
  %if i = 8 || (i >= 10 && i <= 14) || i = 17
    ISR_ERR i
  %else
    ISR_NOERR i
  %endif
%assign i i+1
%endrep

isr_common:
    pusha
    push esp                  ; pointer to saved registers
    call isr_handler
    add esp, 4
    popa
    add esp, 8                ; pop int number + error code
    iret

section .data
global isr_table
isr_table:
%assign i 0
%rep 48
    dd isr %+ i
%assign i i+1
%endrep
