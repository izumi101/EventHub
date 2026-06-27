import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToastService } from '../../../services/toast.service';
import { LucideAngularModule, CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-angular';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  imports: [CommonModule, LucideAngularModule],
  template: `
    <div
      class="fixed bottom-5 right-4 z-[9999] flex flex-col gap-2.5 max-w-sm w-full pointer-events-none"
      aria-live="polite"
      aria-atomic="true"
    >
      @for (toast of toastService.toasts(); track toast.id) {
        <div
          class="flex items-center gap-3 px-4 py-3 rounded-lg border shadow-lg text-sm font-medium animate-slide-up pointer-events-auto"
          [class]="toastClass(toast.type)"
          role="alert"
        >
          <lucide-icon [img]="getIcon(toast.type)" class="w-4 h-4 flex-shrink-0" aria-hidden="true"></lucide-icon>
          <span class="flex-1">{{ toast.message }}</span>
          <button
            (click)="toastService.dismiss(toast.id)"
            class="flex-shrink-0 opacity-60 hover:opacity-100 transition-opacity p-0.5 rounded"
            aria-label="Dismiss"
          >
            <lucide-icon [img]="icons.X" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
          </button>
        </div>
      }
    </div>
  `,
})
export class ToastContainerComponent {
  readonly icons = { X };

  constructor(public toastService: ToastService) {}

  toastClass(type: string): string {
    const map: Record<string, string> = {
      success: 'bg-white border-transparent text-[color:var(--pine-600)]',
      error:   'bg-white border-transparent text-[color:var(--destructive)]',
      warning: 'bg-white border-transparent text-warning',
      info:    'bg-white border-blue-200 text-blue-700',
    };
    return map[type] ?? 'bg-white border-border text-foreground';
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getIcon(type: string): any {
    const map: Record<string, any> = {
      success: CheckCircle,
      error: XCircle,
      warning: AlertTriangle,
      info: Info,
    };
    return map[type] ?? Info;
  }
}
