/* Plain C -- no compile_commands.json here on purpose, to prove
 * `codecheck run-rules --lang c` works standalone via its fallback
 * parse args, exactly the situation a small embedded firmware module
 * without a generated compilation database is often in. */
#include <stdio.h>

#define GPIO_BASE ((volatile unsigned int *)0x40020000u)

// TODO: make the pin count configurable via Kconfig
void gpio_init(void)
{
    *GPIO_BASE = 0;
}

void gpio_log_state(int pin, int value)
{
    char buf[32];
    sprintf(buf, "pin=%d value=%d", pin, value); /* banned: unbounded sprintf */
    puts(buf);
}

int main(void) {
    gpio_init();
    gpio_log_state(3, 1);
    return 0;
}
