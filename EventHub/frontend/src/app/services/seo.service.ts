import { Injectable, inject } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Event as EventModel } from '../models/models';

const SITE_NAME = 'EventHub';
const BASE_URL = 'https://eventhub.app';
const DEFAULT_DESCRIPTION =
  'Discover and book concerts, festivals, conferences, and workshops worldwide.';
const DEFAULT_IMAGE = `${BASE_URL}/assets/og-default.png`;

@Injectable({ providedIn: 'root' })
export class SeoService {
  private meta = inject(Meta);
  private title = inject(Title);
  private router = inject(Router);

  constructor() {
    // Reset to site defaults on every navigation (individual pages override after)
    this.router.events
      .pipe(
        filter(e => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.setDefault());
  }

  setDefault(): void {
    const t = `${SITE_NAME} — Discover Events That Matter`;
    this._apply({
      title: t,
      description: DEFAULT_DESCRIPTION,
      image: DEFAULT_IMAGE,
      url: `${BASE_URL}${this.router.url}`,
      type: 'website',
    });
  }

  setEvent(event: EventModel): void {
    const seoTitle = event.seo_title || event.title;
    const seoDesc =
      event.seo_description ||
      (event.description ? event.description.slice(0, 200).replace(/\s+/g, ' ').trim() : DEFAULT_DESCRIPTION);
    const image = event.image ? (event.image.startsWith('http') ? event.image : `${BASE_URL}${event.image}`) : DEFAULT_IMAGE;
    const url = `${BASE_URL}/events/${event.id}`;
    const pageTitle = `${seoTitle} — ${SITE_NAME}`;

    this._apply({ title: pageTitle, description: seoDesc, image, url, type: 'event' });

    // Event-specific structured data (JSON-LD)
    this._setJsonLd({
      '@context': 'https://schema.org',
      '@type': 'Event',
      name: event.title,
      description: seoDesc,
      startDate: event.date,
      endDate: event.end_date ?? undefined,
      location: event.is_online
        ? { '@type': 'VirtualLocation', url: event.online_link }
        : { '@type': 'Place', name: event.location },
      image,
      url,
      organizer: {
        '@type': 'Person',
        name:
          [event.organizer.first_name, event.organizer.last_name].filter(Boolean).join(' ') ||
          event.organizer.username,
      },
      offers: {
        '@type': 'Offer',
        price: event.price_from ?? event.price,
        priceCurrency: event.currency ?? 'USD',
        availability: (event.available_spots ?? 1) > 0
          ? 'https://schema.org/InStock'
          : 'https://schema.org/SoldOut',
        url,
      },
    });
  }

  private _apply(opts: { title: string; description: string; image: string; url: string; type: string }): void {
    this.title.setTitle(opts.title);

    const tags: { [key: string]: string } = {
      'description': opts.description,
      'og:title': opts.title,
      'og:description': opts.description,
      'og:image': opts.image,
      'og:url': opts.url,
      'og:type': opts.type,
      'og:site_name': SITE_NAME,
      'twitter:card': 'summary_large_image',
      'twitter:title': opts.title,
      'twitter:description': opts.description,
      'twitter:image': opts.image,
    };

    for (const [name, content] of Object.entries(tags)) {
      const isOg = name.startsWith('og:') || name.startsWith('twitter:');
      const selector = isOg ? `property='${name}'` : `name='${name}'`;
      const existing = this.meta.getTag(selector);
      if (existing) {
        this.meta.updateTag({ [isOg ? 'property' : 'name']: name, content });
      } else {
        this.meta.addTag({ [isOg ? 'property' : 'name']: name, content });
      }
    }
  }

  private _setJsonLd(data: object): void {
    const id = 'structured-data-jsonld';
    let el = document.getElementById(id) as HTMLScriptElement | null;
    if (!el) {
      el = document.createElement('script');
      el.id = id;
      el.type = 'application/ld+json';
      document.head.appendChild(el);
    }
    el.textContent = JSON.stringify(data);
  }
}
