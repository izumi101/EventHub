import { Injectable, signal } from '@angular/core';
import { Subject } from 'rxjs';

export interface ModalConfig {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  isDestructive?: boolean;
}

@Injectable({ providedIn: 'root' })
export class ModalService {
  isOpen = signal(false);
  config = signal<ModalConfig | null>(null);
  
  private responseSubject: Subject<boolean> | null = null;

  open(config: ModalConfig): Promise<boolean> {
    this.config.set(config);
    this.isOpen.set(true);
    
    // Complete previous subject if it exists
    if (this.responseSubject) {
      this.responseSubject.next(false);
      this.responseSubject.complete();
    }
    
    this.responseSubject = new Subject<boolean>();
    
    return new Promise<boolean>((resolve) => {
      const sub = this.responseSubject!.subscribe((result) => {
        sub.unsubscribe();
        this.isOpen.set(false);
        resolve(result);
      });
    });
  }

  confirm() {
    if (this.responseSubject) {
      this.responseSubject.next(true);
      this.responseSubject.complete();
      this.responseSubject = null;
    }
  }

  cancel() {
    if (this.responseSubject) {
      this.responseSubject.next(false);
      this.responseSubject.complete();
      this.responseSubject = null;
    }
  }
}
