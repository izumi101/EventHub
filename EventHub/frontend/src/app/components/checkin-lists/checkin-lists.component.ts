import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { EventService } from '../../services/event.service';
import { ToastService } from '../../services/toast.service';
import { CheckInList, CheckInAttendee, CheckInLogEntry } from '../../models/models';
import {
  LucideAngularModule,
  Plus,
  Trash2,
  CircleCheck,
  CircleX,
  Users,
  ClipboardList,
  Clock,
  ChevronRight,
  ScanLine,
  RefreshCw,
  Pencil,
  Check,
  X,
} from 'lucide-angular';
import { apiErrorMessage } from '../../api/api-error';
import { TranslocoPipe } from '@jsverse/transloco';
import { LocalDatePipe } from '../../i18n/locale.pipes';
import { LanguageService } from '../../i18n/language.service';

@Component({
  selector: 'app-checkin-lists',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    FormsModule,
    LucideAngularModule,
    TranslocoPipe,
    LocalDatePipe,
  ],
  template: `
    <div class="page-root">
      <div class="container max-w-5xl py-8">
        <!-- Breadcrumb -->
        <nav class="flex items-center gap-1.5 text-sm text-muted-foreground mb-6">
          <a routerLink="/organizer/dashboard" class="hover:text-foreground transition-colors">{{
            'nav.dashboard' | transloco
          }}</a>
          <span>/</span>
          <a
            [routerLink]="['/organizer/events', eventId, 'attendees']"
            class="hover:text-foreground transition-colors"
            >{{ 'nav.attendees' | transloco }}</a
          >
          <span>/</span>
          <span class="text-foreground font-medium">{{ 'checkin.checkInLists' | transloco }}</span>
        </nav>

        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 class="text-2xl font-bold text-foreground">
              {{ 'checkin.checkInLists' | transloco }}
            </h1>
            <p class="text-sm text-muted-foreground mt-1">
              {{ 'checkin.createNamedEntrancesAnd' | transloco }}
            </p>
          </div>
          <button (click)="showCreateForm = true" class="btn btn-primary flex items-center gap-2">
            <lucide-icon [img]="icons.Plus" class="w-4 h-4" />
            {{ 'checkin.newList' | transloco }}
          </button>
        </div>

        <!-- Create list form -->
        @if (showCreateForm) {
          <div class="card p-4 mb-6 border-primary/30 bg-primary/5 animate-fade-in">
            <h3 class="text-sm font-semibold text-foreground mb-3">
              {{ 'checkin.newCheckInList' | transloco }}
            </h3>
            <div class="flex flex-wrap gap-3">
              <input
                [(ngModel)]="newName"
                [placeholder]="'checkin.eGGeneralEntrance' | transloco"
                class="input flex-1 min-w-40"
                maxlength="120"
              />
              <input
                [(ngModel)]="newDescription"
                [placeholder]="'checkin.descriptionOptional' | transloco"
                class="input flex-1 min-w-40"
                maxlength="300"
              />
              <div class="flex items-center gap-2">
                <label for="checkin-lists-new-color" class="text-xs text-muted-foreground">{{
                  'checkin.color' | transloco
                }}</label>
                <input
                  id="checkin-lists-new-color"
                  type="color"
                  [(ngModel)]="newColor"
                  class="w-9 h-9 rounded cursor-pointer border border-border"
                />
              </div>
              <button
                (click)="createList()"
                [disabled]="creating || !newName.trim()"
                class="btn btn-primary"
              >
                {{ (creating ? 'checkin.creating' : 'common.create') | transloco }}
              </button>
              <button (click)="showCreateForm = false" class="btn btn-secondary">
                {{ 'common.cancel' | transloco }}
              </button>
            </div>
          </div>
        }

        @if (loading) {
          <div class="flex items-center justify-center py-20 gap-3 text-muted-foreground">
            <span class="spinner"></span>
            <span class="text-sm">{{ 'checkin.loadingLists' | transloco }}</span>
          </div>
        } @else if (lists.length === 0) {
          <div class="card p-12 flex flex-col items-center text-center">
            <lucide-icon
              [img]="icons.ClipboardList"
              class="w-10 h-10 text-muted-foreground/30 mb-4"
            />
            <p class="text-foreground font-semibold mb-1">
              {{ 'checkin.noCheckInLists' | transloco }}
            </p>
            <p class="text-sm text-muted-foreground mb-4">
              {{ 'checkin.createYourFirstList' | transloco }}
            </p>
            <button (click)="showCreateForm = true" class="btn btn-primary">
              <lucide-icon [img]="icons.Plus" class="w-4 h-4 mr-1.5" />
              {{ 'checkin.createAList' | transloco }}
            </button>
          </div>
        } @else {
          <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- Left: list sidebar -->
            <div class="lg:col-span-1 space-y-2">
              @for (list of lists; track list.id) {
                <div
                  class="card p-4 cursor-pointer transition-all"
                  [class.ring-2]="selectedList?.id === list.id"
                  [style.--ring-color]="list.color"
                  [style.border-color]="selectedList?.id === list.id ? list.color : ''"
                  tabindex="0"
                  (click)="selectList(list)"
                  (keydown.enter)="onListKeydown($event, list)"
                  (keydown.space)="onListKeydown($event, list)"
                >
                  <div class="flex items-center gap-3">
                    <div
                      class="w-3 h-3 rounded-full flex-shrink-0"
                      [style.background]="list.color"
                    ></div>
                    <div class="flex-1 min-w-0">
                      @if (editingListId === list.id) {
                        <input
                          [(ngModel)]="editName"
                          (keydown.enter)="saveEdit(list)"
                          (keydown.escape)="editingListId = null"
                          class="input text-sm py-0.5 w-full"
                          (click)="$event.stopPropagation()"
                        />
                      } @else {
                        <p class="font-medium text-foreground text-sm truncate">
                          {{ list.name }}
                          @if (list.is_default) {
                            <span
                              class="ml-1.5 text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-semibold uppercase"
                              >{{ 'checkin.default' | transloco }}</span
                            >
                          }
                        </p>
                      }
                      <p class="text-xs text-muted-foreground mt-0.5">
                        {{
                          'checkin.checkedincountCheckedInLogcount'
                            | transloco
                              : { checkedInCount: list.checked_in_count, logCount: list.log_count }
                        }}
                      </p>
                    </div>
                    <!-- Keeps clicks on the row actions from also selecting the list. -->
                    <div
                      class="flex items-center gap-1 ml-auto"
                      role="presentation"
                      (click)="$event.stopPropagation()"
                    >
                      @if (editingListId === list.id) {
                        <button
                          (click)="saveEdit(list)"
                          class="p-1 text-[color:var(--pine-600)] hover:text-[color:var(--pine-600)]"
                        >
                          <lucide-icon [img]="icons.Check" class="w-4 h-4" />
                        </button>
                        <button
                          (click)="editingListId = null"
                          class="p-1 text-muted-foreground hover:text-foreground"
                        >
                          <lucide-icon [img]="icons.X" class="w-4 h-4" />
                        </button>
                      } @else {
                        <button
                          (click)="startEdit(list)"
                          class="p-1 text-muted-foreground hover:text-foreground"
                          [title]="'checkin.rename' | transloco"
                        >
                          <lucide-icon [img]="icons.Pencil" class="w-3.5 h-3.5" />
                        </button>
                        @if (!list.is_default) {
                          <button
                            (click)="setDefault(list)"
                            class="p-1 text-muted-foreground hover:text-primary"
                            [title]="'checkin.setAsDefault' | transloco"
                          >
                            <lucide-icon [img]="icons.Check" class="w-3.5 h-3.5" />
                          </button>
                          <button
                            (click)="deleteList(list)"
                            class="p-1 text-muted-foreground hover:text-[color:var(--destructive)]"
                            [title]="'common.delete' | transloco"
                          >
                            <lucide-icon [img]="icons.Trash2" class="w-3.5 h-3.5" />
                          </button>
                        }
                      }
                    </div>
                  </div>
                </div>
              }

              <!-- Log panel -->
              <div class="card p-4 mt-4">
                <div class="flex items-center justify-between mb-3">
                  <h3 class="text-sm font-semibold text-foreground flex items-center gap-2">
                    <lucide-icon [img]="icons.Clock" class="w-4 h-4 text-muted-foreground" />
                    {{ 'checkin.scanLog' | transloco }}
                  </h3>
                  <button
                    (click)="loadLogs()"
                    class="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                  >
                    <lucide-icon [img]="icons.RefreshCw" class="w-3 h-3" />
                    {{ 'common.refresh' | transloco }}
                  </button>
                </div>
                @if (logsLoading) {
                  <div class="flex items-center gap-2 text-muted-foreground text-xs">
                    <span class="spinner spinner-sm"></span> {{ 'common.loading' | transloco }}
                  </div>
                } @else if (logs.length === 0) {
                  <p class="text-xs text-muted-foreground">
                    {{ 'checkin.noScansYet' | transloco }}
                  </p>
                } @else {
                  <div class="space-y-2 max-h-64 overflow-y-auto">
                    @for (log of logs; track log.id) {
                      <div class="flex items-start gap-2 text-xs">
                        <lucide-icon
                          [img]="log.action === 'check_in' ? icons.CircleCheck : icons.CircleX"
                          class="w-3.5 h-3.5 flex-shrink-0 mt-0.5"
                          [class.text-[color:var(--pine-600)]]="log.action === 'check_in'"
                          [class.text-ember]="log.action === 'undo'"
                        />
                        <div>
                          <span class="font-medium text-foreground">{{
                            log.attendee.full_name
                          }}</span>
                          <span class="text-muted-foreground">
                            · {{ log.created_at | localDate: 'HH:mm' }}</span
                          >
                          @if (log.scanned_by_username) {
                            <span class="text-muted-foreground">
                              {{
                                'checkin.byScannedbyusername'
                                  | transloco: { scannedByUsername: log.scanned_by_username }
                              }}</span
                            >
                          }
                        </div>
                      </div>
                    }
                  </div>
                }
              </div>
            </div>

            <!-- Right: attendees for selected list -->
            <div class="lg:col-span-2">
              @if (!selectedList) {
                <div class="card p-12 flex flex-col items-center text-center h-full">
                  <lucide-icon
                    [img]="icons.ChevronRight"
                    class="w-8 h-8 text-muted-foreground/30 mb-3"
                  />
                  <p class="text-sm text-muted-foreground">
                    {{ 'checkin.selectAListOn' | transloco }}
                  </p>
                </div>
              } @else {
                <div class="card overflow-hidden">
                  <div class="p-4 border-b border-border flex items-center justify-between">
                    <div class="flex items-center gap-2">
                      <div
                        class="w-3 h-3 rounded-full"
                        [style.background]="selectedList.color"
                      ></div>
                      <h2 class="font-semibold text-foreground">{{ selectedList.name }}</h2>
                    </div>
                    <div class="flex items-center gap-3 text-sm text-muted-foreground">
                      <span>{{
                        'checkin.checkedincountAttendeeslengthCheckedIn'
                          | transloco
                            : { checkedInCount: checkedInCount, attendeesLength: attendees.length }
                      }}</span>
                      <button (click)="loadAttendees()" class="hover:text-foreground">
                        <lucide-icon [img]="icons.RefreshCw" class="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  <!-- Quick scan -->
                  <div class="p-4 border-b border-border bg-muted/30">
                    <label
                      for="checkin-lists-scan-uuid"
                      class="text-xs font-medium text-muted-foreground mb-1.5 block"
                      >{{ 'checkin.quickScanByTicket' | transloco }}</label
                    >
                    <div class="flex gap-2">
                      <input
                        id="checkin-lists-scan-uuid"
                        [(ngModel)]="scanUuid"
                        [placeholder]="'checkin.pasteTicketUuid' | transloco"
                        class="input flex-1 text-sm"
                        (keydown.enter)="quickScan()"
                      />
                      <button
                        (click)="quickScan()"
                        [disabled]="!scanUuid.trim() || scanning"
                        class="btn btn-primary btn-sm"
                      >
                        <lucide-icon [img]="icons.ScanLine" class="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  <!-- Attendee list -->
                  @if (attendeesLoading) {
                    <div class="flex items-center justify-center py-12 gap-3 text-muted-foreground">
                      <span class="spinner"></span>
                      <span class="text-sm">{{ 'checkin.loadingAttendees' | transloco }}</span>
                    </div>
                  } @else if (attendees.length === 0) {
                    <div class="flex flex-col items-center py-12 text-muted-foreground">
                      <lucide-icon [img]="icons.Users" class="w-8 h-8 mb-3 opacity-30" />
                      <p class="text-sm">{{ 'checkin.noAttendeesYet' | transloco }}</p>
                    </div>
                  } @else {
                    <div class="divide-y divide-border max-h-[520px] overflow-y-auto">
                      @for (att of attendees; track att.id) {
                        <div
                          class="flex items-center gap-3 px-4 py-3 hover:bg-muted/30 transition-colors"
                          [class.bg-[color:var(--pine-50)]]="att.is_checked_in"
                        >
                          <div
                            class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary flex-shrink-0"
                          >
                            {{ att.full_name.charAt(0).toUpperCase() }}
                          </div>
                          <div class="flex-1 min-w-0">
                            <p class="text-sm font-medium text-foreground truncate">
                              {{ att.full_name }}
                            </p>
                            <p class="text-xs text-muted-foreground truncate">{{ att.email }}</p>
                            @if (att.is_checked_in && att.checked_in_at) {
                              <p class="text-xs text-[color:var(--pine-600)]">
                                {{
                                  'checkin.checkedInCheckedinat'
                                    | transloco
                                      : { checkedInAt: (att.checked_in_at | localDate: 'HH:mm') }
                                }}
                                @if (att.scanned_by) {
                                  {{
                                    'checkin.byScannedby' | transloco: { scannedBy: att.scanned_by }
                                  }}
                                }
                              </p>
                            }
                          </div>
                          <div class="flex items-center gap-2">
                            @if (att.is_checked_in) {
                              <lucide-icon
                                [img]="icons.CircleCheck"
                                class="w-5 h-5 text-[color:var(--pine-500)]"
                              />
                              <button
                                (click)="undoCheckIn(att)"
                                class="btn btn-secondary btn-sm text-xs"
                              >
                                {{ 'checkin.undo' | transloco }}
                              </button>
                            } @else {
                              <lucide-icon
                                [img]="icons.CircleX"
                                class="w-5 h-5 text-muted-foreground/40"
                              />
                              <button
                                (click)="doCheckIn(att)"
                                class="btn btn-primary btn-sm text-xs"
                              >
                                {{ 'checkin.checkIn' | transloco }}
                              </button>
                            }
                          </div>
                        </div>
                      }
                    </div>
                  }
                </div>
              }
            </div>
          </div>
        }
      </div>
    </div>
  `,
})
export class CheckinListsComponent implements OnInit {
  private i18n = inject(LanguageService);
  private route = inject(ActivatedRoute);
  private eventService = inject(EventService);
  private toastService = inject(ToastService);

  eventId: number | null = null;
  lists: CheckInList[] = [];
  selectedList: CheckInList | null = null;
  attendees: CheckInAttendee[] = [];
  logs: CheckInLogEntry[] = [];
  loading = true;
  attendeesLoading = false;
  logsLoading = false;
  creating = false;
  scanning = false;

  showCreateForm = false;
  newName = '';
  newDescription = '';
  newColor = '#E8552D';

  editingListId: number | null = null;
  editName = '';

  scanUuid = '';

  readonly icons = {
    Plus,
    Trash2,
    CircleCheck,
    CircleX,
    Users,
    ClipboardList,
    Clock,
    ChevronRight,
    ScanLine,
    RefreshCw,
    Pencil,
    Check,
    X,
  };

  get checkedInCount(): number {
    return this.attendees.filter((a) => a.is_checked_in).length;
  }

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.eventId = +id;
      this.loadLists();
      this.loadLogs();
    }
  }

  loadLists(): void {
    if (!this.eventId) return;
    this.loading = true;
    this.eventService.getCheckInLists(this.eventId).subscribe({
      next: (lists) => {
        this.lists = lists;
        this.loading = false;
        if (!this.selectedList && lists.length > 0) this.selectList(lists[0]);
        else if (this.selectedList) {
          const selectedId = this.selectedList.id;
          const updated = lists.find((l) => l.id === selectedId);
          if (updated) this.selectedList = updated;
        }
      },
      error: () => {
        this.loading = false;
        this.toastService.error(this.i18n.t('checkin.failedToLoadLists'));
      },
    });
  }

  loadLogs(): void {
    if (!this.eventId) return;
    this.logsLoading = true;
    this.eventService.getCheckInLogs(this.eventId).subscribe({
      next: (logs) => {
        this.logs = logs.slice(0, 50);
        this.logsLoading = false;
      },
      error: () => {
        this.logsLoading = false;
      },
    });
  }

  selectList(list: CheckInList): void {
    this.selectedList = list;
    this.loadAttendees();
  }

  /** Keyboard selection of a list card; keys pressed in its inputs/buttons are theirs. */
  onListKeydown(event: Event, list: CheckInList): void {
    if (event.target !== event.currentTarget) return;
    event.preventDefault();
    this.selectList(list);
  }

  loadAttendees(): void {
    if (!this.selectedList) return;
    this.attendeesLoading = true;
    this.eventService.getCheckInListAttendees(this.selectedList.id).subscribe({
      next: (atts) => {
        this.attendees = atts;
        this.attendeesLoading = false;
      },
      error: () => {
        this.attendeesLoading = false;
        this.toastService.error(this.i18n.t('checkin.failedToLoadAttendees'));
      },
    });
  }

  createList(): void {
    if (!this.eventId || !this.newName.trim()) return;
    this.creating = true;
    this.eventService
      .createCheckInList(this.eventId, {
        name: this.newName.trim(),
        description: this.newDescription.trim(),
        color: this.newColor,
      })
      .subscribe({
        next: () => {
          this.creating = false;
          this.showCreateForm = false;
          this.newName = '';
          this.newDescription = '';
          this.newColor = '#E8552D';
          this.loadLists();
          this.toastService.success(this.i18n.t('checkin.listCreated'));
        },
        error: () => {
          this.creating = false;
          this.toastService.error(this.i18n.t('checkin.failedToCreateList'));
        },
      });
  }

  startEdit(list: CheckInList): void {
    this.editingListId = list.id;
    this.editName = list.name;
  }

  saveEdit(list: CheckInList): void {
    if (!this.editName.trim()) {
      this.editingListId = null;
      return;
    }
    this.eventService.updateCheckInList(list.id, { name: this.editName.trim() }).subscribe({
      next: () => {
        this.editingListId = null;
        this.loadLists();
        this.toastService.success(this.i18n.t('checkin.renamed'));
      },
      error: () => this.toastService.error(this.i18n.t('checkin.failedToRename')),
    });
  }

  setDefault(list: CheckInList): void {
    this.eventService.updateCheckInList(list.id, { is_default: true }).subscribe({
      next: () => {
        this.loadLists();
        this.toastService.success(this.i18n.t('checkin.listnameIsNowThe', { listName: list.name }));
      },
      error: () => this.toastService.error(this.i18n.t('checkin.failedToUpdate')),
    });
  }

  deleteList(list: CheckInList): void {
    if (!confirm(this.i18n.t('checkin.deleteListConfirm', { name: list.name }))) return;
    this.eventService.deleteCheckInList(list.id).subscribe({
      next: () => {
        if (this.selectedList?.id === list.id) {
          this.selectedList = null;
          this.attendees = [];
        }
        this.loadLists();
        this.toastService.success(this.i18n.t('checkin.listDeleted'));
      },
      error: () => this.toastService.error(this.i18n.t('checkin.failedToDeleteList')),
    });
  }

  quickScan(): void {
    if (!this.selectedList || !this.scanUuid.trim()) return;
    this.scanning = true;
    this.eventService.checkInByList(this.selectedList.id, this.scanUuid.trim()).subscribe({
      next: (res) => {
        this.scanning = false;
        this.scanUuid = '';
        this.toastService.success(
          this.i18n.t('checkin.attendeeCheckedIn', { attendee: res.attendee }),
        );
        this.loadAttendees();
        this.loadLogs();
        this.loadLists();
      },
      error: (err) => {
        this.scanning = false;
        this.toastService.error(apiErrorMessage(err, this.i18n.t('checkin.scanFailed'), 'error'));
      },
    });
  }

  doCheckIn(att: CheckInAttendee): void {
    if (!this.selectedList) return;
    this.eventService.checkInByList(this.selectedList.id, att.ticket_uuid).subscribe({
      next: () => {
        att.is_checked_in = true;
        att.checked_in_at = new Date().toISOString();
        this.loadLogs();
        this.loadLists();
      },
      error: (err) =>
        this.toastService.error(
          apiErrorMessage(err, this.i18n.t('checkin.checkInFailed'), 'error'),
        ),
    });
  }

  undoCheckIn(att: CheckInAttendee): void {
    if (!this.selectedList) return;
    this.eventService.checkInByList(this.selectedList.id, att.ticket_uuid, 'undo').subscribe({
      next: () => {
        att.is_checked_in = false;
        att.checked_in_at = null;
        this.loadLogs();
        this.loadLists();
      },
      error: (err) =>
        this.toastService.error(apiErrorMessage(err, this.i18n.t('checkin.undoFailed'), 'error')),
    });
  }
}
