CC      = gcc
CFLAGS  = -m32 -ffreestanding -fno-pie -fno-stack-protector -nostdlib -O2 -Wall -Wextra -fno-builtin
LDFLAGS = -m elf_i386 -T linker.ld -nostdlib -z noexecstack
OBJS    = boot.o kernel.o screen.o keyboard.o shell.o fs.o snake.o pet.o lib.o

all: myos.iso

boot.o: boot.asm
	nasm -f elf32 $< -o $@

%.o: %.c os.h
	$(CC) $(CFLAGS) -c $< -o $@

myos.bin: $(OBJS) linker.ld
	ld $(LDFLAGS) -o $@ $(OBJS)

myos.iso: myos.bin grub.cfg
	rm -rf iso && mkdir -p iso/boot/grub
	cp myos.bin iso/boot/ && cp grub.cfg iso/boot/grub/
	grub-mkrescue -o $@ iso 2>/dev/null

run: myos.iso
	qemu-system-i386 -cdrom myos.iso -m 128

clean:
	rm -rf *.o myos.bin myos.iso iso
