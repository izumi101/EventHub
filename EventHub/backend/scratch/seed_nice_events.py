"""
Одноразовый сид: удаляет все существующие события и создаёт ~20 аккуратных
ивентов от имени организатора `organizer`. Запуск:
    docker compose exec backend python scratch/seed_nice_events.py
"""
import os
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from events.models import Event, Category

organizer = User.objects.get(username='organizer')
now = timezone.now()


def cat(name):
    return Category.objects.get(name=name)


# (title, category, days_from_now, hour, duration_h, location, address, price, capacity, online, link, img_keyword, description)
EVENTS = [
    ("Almaty Tech Summit 2026", "Technology", 12, 10, 8, "Almaty, Rixos Hotel", "Seyfullin Ave 506/99",
     "25000", 400, False, "", "conference,technology",
     "The largest technology gathering in Central Asia. Two stages, 40+ speakers from leading product and engineering teams, and a full day of networking. Topics span AI, cloud infrastructure, product design, and the future of work."),

    ("AI & Machine Learning Conference", "Technology", 26, 9, 7, "Almaty, Almaty Towers", "Baizakov St 280",
     "18000", 300, False, "", "artificial,intelligence",
     "A focused day on applied machine learning: LLMs in production, MLOps, computer vision, and responsible AI. Hands-on demos and real case studies from teams shipping ML at scale."),

    ("Web3 & Blockchain Builders Meetup", "Technology", 8, 18, 3, "Almaty, SmartPoint Coworking", "Al-Farabi Ave 17",
     "0", 120, False, "", "blockchain,crypto",
     "An informal evening for builders exploring decentralized tech. Lightning talks, live coding, and open discussion on smart contracts, wallets, and the practical side of Web3. Pizza and drinks included."),

    ("Cloud Native DevOps Day", "Technology", 40, 10, 6, "Online", "",
     "9000", 500, True, "https://meet.eventhub.dev/devops-day", "server,datacenter",
     "Kubernetes, CI/CD, observability, and platform engineering — a full online day for DevOps practitioners. Live workshops you can follow along with, plus a Q&A with senior SREs."),

    ("Coffee & Code: Frontend Edition", "Technology", 5, 11, 2, "Online", "",
     "0", 200, True, "https://meet.eventhub.dev/coffee-code", "laptop,coffee",
     "A relaxed Saturday morning stream for frontend developers. We pair-program a small feature live, talk through modern patterns, and answer your questions. Bring your own coffee."),

    ("Startup Pitch Night", "Business", 15, 19, 3, "Almaty, Terricon Valley", "Dostyk Ave 136",
     "0", 150, False, "", "startup,pitch",
     "Ten early-stage founders pitch to a panel of investors and a live audience. Vote for your favorite, meet the teams afterwards, and discover what's being built right now in the local startup scene."),

    ("Founders & Investors Mixer", "Business", 33, 18, 3, "Almaty, The Ritz-Carlton", "Al-Farabi Ave 77/7",
     "12000", 100, False, "", "business,networking",
     "A curated evening connecting founders with angel investors and VCs. Structured introductions, a short fireside chat, and plenty of time to build the relationships that matter."),

    ("Digital Marketing Masterclass", "Business", 20, 10, 5, "Almaty, Coworking Plaza", "Manas St 34/1",
     "15000", 80, False, "", "marketing,office",
     "A practical full-day masterclass on performance marketing: paid acquisition, funnels, content strategy, and analytics. Leave with a concrete plan you can apply to your own product on Monday."),

    ("Python for Data Science Workshop", "Education", 18, 11, 4, "Online", "",
     "8000", 250, True, "https://meet.eventhub.dev/python-ds", "python,code",
     "Hands-on introduction to data science with Python: pandas, visualization, and your first predictive model. Designed for beginners with some coding experience. All notebooks provided."),

    ("UX/UI Design Bootcamp", "Education", 45, 10, 6, "Almaty, Designers Hub", "Gogol St 86",
     "22000", 60, False, "", "design,workspace",
     "An intensive one-day bootcamp covering the full design process: research, wireframing, prototyping in Figma, and usability testing. Small group, lots of personal feedback."),

    ("Public Speaking Intensive", "Education", 28, 14, 4, "Almaty, Open Space Hall", "Abay Ave 10",
     "11000", 40, False, "", "speaker,stage",
     "Conquer stage fright and learn to command a room. A practical workshop with live exercises, structured feedback, and techniques used by professional speakers. Everyone presents."),

    ("Almaty Jazz Nights", "Music", 10, 20, 3, "Almaty, Philharmonic Hall", "Kaldayakov St 35",
     "14000", 220, False, "", "jazz,concert",
     "An intimate evening of live jazz featuring a quartet of acclaimed local and visiting musicians. Smooth standards, original compositions, and that warm late-night club atmosphere."),

    ("Indie Rock Live: Summer Sessions", "Music", 22, 20, 4, "Almaty, EXPO Arena", "Mangilik El Ave 55",
     "17000", 600, False, "", "rock,concert",
     "Three of the most exciting indie bands of the season share one stage. Raw energy, big choruses, and a crowd that knows every word. Doors open an hour before the first set."),

    ("Electronic Music Festival", "Music", 55, 21, 6, "Almaty, Open Air Grounds", "Al-Farabi Ave 140",
     "20000", 1500, False, "", "festival,lights",
     "A night of world-class electronic music across two stages. International headliners, immersive lighting, and a production built for dancing until sunrise. 18+."),

    ("Acoustic Evening", "Music", 7, 19, 2, "Almaty, Bookcafe Lounge", "Zhibek Zholy 64",
     "0", 50, False, "", "acoustic,guitar",
     "A cozy, candle-lit acoustic set in a small bookstore cafe. Singer-songwriters performing stripped-back originals. Free entry, limited seats — come early for a good spot."),

    ("City Marathon 2026", "Sports", 60, 7, 6, "Almaty, Central Stadium", "Abay Ave 48/23",
     "7000", 2000, False, "", "marathon,running",
     "Run through the heart of the city on a certified course. Full marathon, half, and a 10K. Chip timing, hydration stations every 2.5 km, and a finisher medal for everyone who crosses the line."),

    ("Yoga in the Park", "Sports", 4, 8, 1, "Almaty, Central Park", "Gogol St 1",
     "0", 100, False, "", "yoga,park",
     "Start your weekend with a free outdoor yoga session suitable for all levels. Bring a mat and water; we provide the calm. Sessions run rain or shine under the pavilion."),

    ("Street Basketball Tournament", "Sports", 17, 12, 5, "Almaty, Sport City Court", "Satpayev St 90",
     "0", 200, False, "", "basketball,street",
     "3x3 street basketball, open registration. Bring your team or join one on the day. Bracket play, a slam-dunk contest, music, and prizes for the winning squad."),

    ("Mountain Trail Run: Kok-Zhailau", "Sports", 38, 8, 5, "Almaty, Kok-Zhailau Trailhead", "Prospekt Dostyk (upper)",
     "9000", 150, False, "", "trail,mountains",
     "A guided trail run on one of the most beautiful routes above the city. Two distances for different fitness levels, experienced trail leaders, and unforgettable views. Proper running shoes required."),

    ("Indie Film Screening & Talk", "Education", 30, 19, 3, "Almaty, Arthouse Cinema", "Tole Bi St 71",
     "6000", 90, False, "", "cinema,film",
     "A screening of an award-winning independent film, followed by a moderated discussion with a local director. A relaxed evening for anyone who loves cinema and good conversation."),
]


def fetch_image(keyword, idx):
    """Скачивает тематическое фото в media/events/. Возвращает относительный путь или ''."""
    events_dir = os.path.join(settings.MEDIA_ROOT, 'events')
    os.makedirs(events_dir, exist_ok=True)
    fname = f'seed_{idx:02d}.jpg'
    fpath = os.path.join(events_dir, fname)
    sources = [
        f'https://loremflickr.com/1200/800/{keyword}',
        f'https://picsum.photos/seed/eventhub{idx}/1200/800',
    ]
    for url in sources:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=20).read()
            if len(data) > 3000:  # отсекаем заглушки/ошибки
                with open(fpath, 'wb') as f:
                    f.write(data)
                return f'events/{fname}'
        except Exception as e:
            print(f'    img source failed ({url}): {e}')
    return ''


# ── Чистка ──
old = Event.objects.count()
Event.objects.all().delete()
print(f'Deleted {old} existing events (and their registrations).')

# ── Создание ──
created = 0
for i, (title, category, days, hour, dur, loc, addr, price, cap, online, link, kw, desc) in enumerate(EVENTS, 1):
    start = (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    img = fetch_image(kw, i)
    Event.objects.create(
        title=title,
        description=desc,
        organizer=organizer,
        category=cat(category),
        date=start,
        end_date=start + timedelta(hours=dur),
        location=loc,
        address=addr,
        image=img,
        price=price,
        max_participants=cap,
        status='published',
        is_online=online,
        online_link=link,
    )
    created += 1
    print(f'  [{i:02d}] {title:42} {category:11} img={"yes" if img else "no"}')

print(f'\nDone. Created {created} events for organizer "{organizer.username}".')
