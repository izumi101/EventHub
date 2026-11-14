import { TestBed } from '@angular/core/testing';
import { Component, inject } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { LanguageService } from './language.service';
import { LANG_STORAGE_KEY } from './languages';
import { LanguageSwitcherComponent } from './language-switcher.component';
import { I18nTestingModule } from './testing';
import { NotFoundComponent } from '../components/not-found/not-found.component';
import { provideRouter } from '@angular/router';

function setup(navigatorLanguages: string[] = ['en-US']): LanguageService {
  TestBed.configureTestingModule({ imports: [I18nTestingModule] });
  vi.spyOn(window.navigator, 'languages', 'get').mockReturnValue(navigatorLanguages);
  return TestBed.inject(LanguageService);
}

describe('LanguageService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = 'en';
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('defaults to English when nothing matches', async () => {
    const service = setup(['fr-FR', 'de']);
    await service.init();
    expect(service.lang()).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });

  it('uses the browser language when nothing is stored', async () => {
    const service = setup(['de', 'kk-KZ']);
    await service.init();
    expect(service.lang()).toBe('kk');
    expect(document.documentElement.lang).toBe('kk');
  });

  it('prefers the stored language over the browser language', async () => {
    localStorage.setItem(LANG_STORAGE_KEY, 'ru');
    const service = setup(['en-US']);
    await service.init();
    expect(service.lang()).toBe('ru');
  });

  it('ignores an unsupported stored value', async () => {
    localStorage.setItem(LANG_STORAGE_KEY, 'xx');
    const service = setup(['en-US']);
    await service.init();
    expect(service.lang()).toBe('en');
  });

  it('persists the choice, updates <html lang> and translates', async () => {
    const service = setup();
    await service.init();
    expect(service.t('nav.signIn')).toBe('Sign In');
    await service.setLang('ru');
    expect(localStorage.getItem(LANG_STORAGE_KEY)).toBe('ru');
    expect(document.documentElement.lang).toBe('ru');
    expect(service.t('nav.signIn')).toBe('Войти');
    await service.setLang('kk');
    expect(service.t('nav.signIn')).toBe('Кіру');
  });

  it('survives unavailable storage', async () => {
    const service = setup();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    await service.init();
    await service.setLang('ru');
    expect(service.lang()).toBe('ru');
  });

  it('falls back to English for a key missing in the active language', async () => {
    const service = setup();
    await service.setLang('ru');
    expect(service.tOr('does.not.exist', 'fallback')).toBe('fallback');
  });

  it('picks plural forms per language', async () => {
    const service = setup();
    await service.init();
    expect(service.plural('home.eventsFound', 1)).toBe('1 event found');
    expect(service.plural('home.eventsFound', 3)).toBe('3 events found');
    await service.setLang('ru');
    expect(service.plural('event.spotsLeft', 1)).toBe('Остался 1 билет');
    expect(service.plural('event.spotsLeft', 3)).toBe('Осталось 3 билета');
    expect(service.plural('event.spotsLeft', 5)).toBe('Осталось 5 билетов');
  });
});

@Component({
  selector: 'app-host',
  imports: [LanguageSwitcherComponent, NotFoundComponent, TranslocoPipe],
  template: `
    <app-language-switcher />
    <app-not-found />
    <span id="probe">{{ 'nav.signIn' | transloco }}</span>
  `,
})
class HostComponent {
  readonly language = inject(LanguageService);
}

describe('language switching in the UI', () => {
  it('re-renders text without reloading when a language button is clicked', async () => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [I18nTestingModule],
      providers: [provideRouter([])],
    });
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('This page has left the venue.');
    expect(root.querySelector('#probe')?.textContent).toBe('Sign In');

    root.querySelector<HTMLButtonElement>('[data-lang="ru"]')?.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Эта страница покинула площадку.');
    expect(root.querySelector('#probe')?.textContent).toBe('Войти');
    expect(root.querySelector('[data-lang="ru"]')?.getAttribute('aria-pressed')).toBe('true');
    expect(document.documentElement.lang).toBe('ru');

    root.querySelector<HTMLButtonElement>('[data-lang="kk"]')?.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.querySelector('#probe')?.textContent).toBe('Кіру');
  });
});
