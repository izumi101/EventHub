import {
  Component,
  OnDestroy,
  AfterViewInit,
  ViewChild,
  ElementRef,
  NgZone,
  inject,
  PLATFORM_ID,
} from '@angular/core';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { RouterModule } from '@angular/router';
import jsQR from 'jsqr';
import { EventService } from '../../services/event.service';
import { CheckInResponse } from '../../models/models';
import {
  LucideAngularModule,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Camera,
  RefreshCw,
  ChevronLeft,
} from 'lucide-angular';

type ScanState =
  | 'requesting'   // запрашиваем доступ к камере
  | 'scanning'     // активное сканирование
  | 'checking'     // декодировали QR, обращаемся к API
  | 'result'       // показываем результат check-in
  | 'denied'       // пользователь отклонил доступ
  | 'nocamera'     // камера не найдена
  | 'insecure';    // getUserMedia недоступен (не https)

@Component({
  selector: 'app-scan',
  standalone: true,
  imports: [CommonModule, RouterModule, LucideAngularModule],
  template: `
    <div class="page-root">
      <div class="container max-w-md py-8">

        <!-- Back -->
        <a routerLink="/organizer/dashboard" class="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-5">
          <lucide-icon [img]="icons.ChevronLeft" class="w-3.5 h-3.5" aria-hidden="true"></lucide-icon>
          Dashboard
        </a>

        <h1 class="text-2xl font-bold text-foreground mb-1">Scan tickets</h1>
        <p class="text-sm text-muted-foreground mb-6">Point the camera at an attendee's QR code to check them in.</p>

        <div class="card overflow-hidden shadow-card">

          <!-- ── Camera viewport ── -->
          <div class="relative bg-gray-900 aspect-square" [class.hidden]="state === 'result'">
            <!-- Video всегда в DOM, пока работает камера -->
            <video
              #video
              class="w-full h-full object-cover"
              [class.opacity-40]="state === 'checking'"
              playsinline
              muted
            ></video>
            <canvas #canvas class="hidden"></canvas>

            <!-- Рамка наведения -->
            @if (state === 'scanning') {
              <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div class="w-2/3 aspect-square rounded-2xl border-2 border-[color:var(--ember-500)] shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]"></div>
              </div>
              <p class="absolute bottom-4 inset-x-0 text-center text-white/90 text-sm font-medium">
                Searching for QR code...
              </p>
            }

            @if (state === 'checking') {
              <div class="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <span class="spinner spinner-lg" style="border-top-color:#fff;border-color:rgba(255,255,255,0.3)"></span>
                <p class="text-white text-sm font-medium">Verifying ticket...</p>
              </div>
            }

            @if (state === 'requesting') {
              <div class="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/90">
                <lucide-icon [img]="icons.Camera" class="w-8 h-8" aria-hidden="true"></lucide-icon>
                <p class="text-sm font-medium">Requesting camera access...</p>
              </div>
            }
          </div>

          <!-- ── Camera error states ── -->
          @if (state === 'denied' || state === 'nocamera' || state === 'insecure') {
            <div class="p-8 text-center">
              <div class="w-14 h-14 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center mx-auto mb-4">
                <lucide-icon [img]="icons.XCircle" class="w-7 h-7 text-[color:var(--destructive)]" aria-hidden="true"></lucide-icon>
              </div>
              <h2 class="text-base font-semibold text-foreground mb-1">
                @switch (state) {
                  @case ('denied') { Camera access denied }
                  @case ('nocamera') { No camera found }
                  @case ('insecure') { Camera unavailable }
                }
              </h2>
              <p class="text-sm text-muted-foreground mb-5">
                @switch (state) {
                  @case ('denied') { Allow camera access in your browser settings and try again. }
                  @case ('nocamera') { This device doesn't have an available camera. }
                  @case ('insecure') { The camera requires a secure connection (HTTPS or localhost). }
                }
              </p>
              <button (click)="startCamera()" class="btn btn-secondary btn-sm">
                <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                Try again
              </button>
            </div>
          }

          <!-- ── Result panel ── -->
          @if (state === 'result') {
            <div class="p-8 text-center">
              @if (resultStatus === 'success') {
                <div class="w-16 h-16 rounded-full bg-[color:var(--pine-50)] flex items-center justify-center mx-auto mb-4">
                  <lucide-icon [img]="icons.CheckCircle" class="w-8 h-8 text-[color:var(--pine-600)]" aria-hidden="true"></lucide-icon>
                </div>
                <h2 class="text-xl font-bold text-foreground mb-1">Access granted</h2>
                <p class="text-sm text-muted-foreground mb-5">Ticket valid · checked in</p>
              } @else if (resultStatus === 'used') {
                <div class="w-16 h-16 rounded-full bg-[color:var(--warning-50)] flex items-center justify-center mx-auto mb-4">
                  <lucide-icon [img]="icons.AlertTriangle" class="w-8 h-8 text-warning" aria-hidden="true"></lucide-icon>
                </div>
                <h2 class="text-xl font-bold text-foreground mb-1">Already scanned</h2>
                <p class="text-sm text-muted-foreground mb-5">This ticket has been used</p>
              } @else {
                <div class="w-16 h-16 rounded-full bg-[color:var(--destructive-50)] flex items-center justify-center mx-auto mb-4">
                  <lucide-icon [img]="icons.XCircle" class="w-8 h-8 text-[color:var(--destructive)]" aria-hidden="true"></lucide-icon>
                </div>
                <h2 class="text-xl font-bold text-foreground mb-1">Invalid ticket</h2>
                <p class="text-sm text-muted-foreground mb-5">{{ errorMessage }}</p>
              }

              <!-- Details -->
              @if (result && resultStatus !== 'error') {
                <div class="rounded-lg border border-border bg-muted/40 divide-y divide-border text-sm mb-5 text-left">
                  <div class="px-4 py-3 flex justify-between gap-3">
                    <span class="text-muted-foreground flex-shrink-0">Attendee</span>
                    <span class="font-medium text-foreground text-right">{{ result.attendee }}</span>
                  </div>
                  @if (result.event) {
                    <div class="px-4 py-3 flex justify-between gap-3">
                      <span class="text-muted-foreground flex-shrink-0">Event</span>
                      <span class="font-medium text-foreground text-right">{{ result.event }}</span>
                    </div>
                  }
                  @if (resultStatus === 'used' && result.checked_in_at) {
                    <div class="px-4 py-3 flex justify-between gap-3">
                      <span class="text-muted-foreground flex-shrink-0">First scan</span>
                      <span class="font-medium text-foreground">{{ result.checked_in_at | date:'HH:mm, MMM d' }}</span>
                    </div>
                  }
                </div>
              }

              <button (click)="scanNext()" class="btn btn-primary btn-full btn-lg">
                <lucide-icon [img]="icons.Camera" class="w-4 h-4" aria-hidden="true"></lucide-icon>
                Scan next ticket
              </button>
            </div>
          }
        </div>

        <p class="text-xs text-muted-foreground text-center mt-4">
          Only event organizers can check in tickets.
        </p>
      </div>
    </div>
  `,
})
export class ScanComponent implements AfterViewInit, OnDestroy {
  @ViewChild('video') videoRef!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvas') canvasRef!: ElementRef<HTMLCanvasElement>;

  state: ScanState = 'requesting';
  result: CheckInResponse | null = null;
  resultStatus: 'success' | 'used' | 'error' = 'error';
  errorMessage = '';

  readonly icons = { CheckCircle, AlertTriangle, XCircle, Camera, RefreshCw, ChevronLeft };

  private stream: MediaStream | null = null;
  private rafId: number | null = null;
  private readonly platformId = inject(PLATFORM_ID);

  constructor(private eventService: EventService, private zone: NgZone) {}

  ngAfterViewInit(): void {
    if (isPlatformBrowser(this.platformId)) {
      this.startCamera();
    }
  }

  ngOnDestroy(): void {
    this.stopCamera();
  }

  async startCamera(): Promise<void> {
    this.state = 'requesting';
    this.result = null;

    if (!navigator.mediaDevices?.getUserMedia) {
      this.state = 'insecure';
      return;
    }

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });

      const video = this.videoRef.nativeElement;
      video.srcObject = this.stream;
      await video.play();

      this.state = 'scanning';
      this.zone.runOutsideAngular(() => this.tick());
    } catch (err: unknown) {
      const name = (err as DOMException)?.name;
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        this.state = 'denied';
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        this.state = 'nocamera';
      } else {
        this.state = 'denied';
      }
    }
  }

  private stopCamera(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = null;
  }

  /** Кадр-цикл декодирования — работает вне Angular зоны для производительности. */
  private tick(): void {
    if (this.state !== 'scanning') return;

    const video = this.videoRef?.nativeElement;
    const canvas = this.canvasRef?.nativeElement;
    if (!video || !canvas || video.readyState !== video.HAVE_ENOUGH_DATA) {
      this.rafId = requestAnimationFrame(() => this.tick());
      return;
    }

    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = jsQR(imageData.data, imageData.width, imageData.height, {
      inversionAttempts: 'dontInvert',
    });

    if (code?.data) {
      const uuid = this.extractUuid(code.data);
      if (uuid) {
        this.zone.run(() => this.onDecoded(uuid));
        return;
      }
    }

    this.rafId = requestAnimationFrame(() => this.tick());
  }

  /** Достаёт ticket uuid из строки QR (полный URL или сырой uuid). */
  private extractUuid(data: string): string | null {
    const urlMatch = data.match(/\/validate\/([0-9a-fA-F-]{6,})/);
    if (urlMatch) return urlMatch[1];
    const trimmed = data.trim();
    if (/^[0-9a-fA-F-]{6,}$/.test(trimmed)) return trimmed;
    return null;
  }

  private onDecoded(uuid: string): void {
    this.state = 'checking';
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }

    this.eventService.checkIn(uuid).subscribe({
      next: res => {
        this.result = res;
        this.resultStatus = res.status === 'used' ? 'used' : 'success';
        this.vibrate(res.status === 'used' ? [60, 40, 60] : [120]);
        this.state = 'result';
      },
      error: err => {
        this.result = null;
        this.resultStatus = 'error';
        this.errorMessage = err.error?.error || 'Invalid ticket or insufficient permissions.';
        this.vibrate([200]);
        this.state = 'result';
      },
    });
  }

  scanNext(): void {
    this.result = null;
    this.state = 'scanning';
    this.zone.runOutsideAngular(() => this.tick());
  }

  private vibrate(pattern: number[]): void {
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      navigator.vibrate(pattern);
    }
  }
}
