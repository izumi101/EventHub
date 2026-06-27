import { Component } from '@angular/core';
import { AppShellComponent } from './layout/app-shell.component';
import { ConfirmModalComponent } from './components/shared/confirm-modal/confirm-modal.component';
import { ToastContainerComponent } from './components/shared/toast-container/toast-container.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [AppShellComponent, ConfirmModalComponent, ToastContainerComponent],
  template: `
    <app-shell />
    <app-confirm-modal />
    <app-toast-container />
  `,
})
export class AppComponent {
  title = 'EventHub';
}
