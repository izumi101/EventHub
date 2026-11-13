import { DestroyRef, inject, signal } from '@angular/core';

/**
 * A seconds countdown for "resend code in N s". Create it in an injection
 * context (a component field): the timer stops when the component goes away.
 */
export class Countdown {
  readonly seconds = signal(0);
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.stop());
  }

  start(seconds: number): void {
    this.stop();
    this.seconds.set(Math.max(0, Math.ceil(seconds)));
    if (this.seconds() === 0) return;
    this.timer = setInterval(() => {
      const next = this.seconds() - 1;
      this.seconds.set(Math.max(next, 0));
      if (next <= 0) this.stop();
    }, 1000);
  }

  stop(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
