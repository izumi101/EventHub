"""Static content of `manage.py seed_demo_kz` (docs/DEMO_DATA.md): name pools,
cities, review comments, check-in staff and the 60 hand-written events.

Data only: no database access, no randomness. The command and its removal
share `EVENTS` (the removal finds the events by these titles).
"""

# ruff: noqa: RUF001 - the review comments are real Russian and Kazakh text

from datetime import timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

SEED = 20261112
# Kazakhstan has one time zone, UTC+5, since 1 March 2024.
KZ_TZ = dt_timezone(timedelta(hours=5), 'Asia/Almaty')
USERNAME_PREFIX = 'kz_'

CATEGORIES = [
    ('Music', 'Concerts, jam sessions, and live performances.', 'music'),
    ('Technology', 'Conferences, meetups, and hands-on workshops.', 'laptop'),
    ('Business', 'Networking, startup, and finance events.', 'briefcase'),
    ('Education', 'Lectures, bootcamps, and learning sessions.', 'book'),
    ('Sports', 'Tournaments, outdoor activities, and fitness events.', 'trophy'),
    ('Theatre', 'Opera, ballet, drama and stand-up.', 'theater'),
]

# username suffix, first name, last name, city, bio
ORGANIZERS = [
    ('dana.abenova', 'Dana', 'Abenova', 'Almaty', 'Qazaq Live Agency: concerts and festivals in Almaty.'),
    ('nurlan.zhakupov', 'Nurlan', 'Zhakupov', 'Astana', 'Tech community lead: conferences, meetups and bootcamps.'),
    ('yerlan.ospanov', 'Yerlan', 'Ospanov', 'Almaty', 'Steppe Run Club: running races and sports events.'),
    ('saule.tulegenova', 'Saule', 'Tulegenova', 'Astana', 'Producer at an independent theatre company.'),
    ('arman.bekov', 'Arman', 'Bekov', 'Almaty', 'Business forums and startup pitch days.'),
    ('aliya.kassymova', 'Aliya', 'Kassymova', 'Astana', 'Family, science and education events.'),
]

# Check-in staff (role `check_in` on the events with gates): first name, last name, city.
STAFF = [
    ('Madi', 'Sarsenov', 'Almaty'), ('Aigul', 'Rakhimova', 'Almaty'), ('Dias', 'Kuanyshev', 'Almaty'),
    ('Zarina', 'Myrzakhmetova', 'Almaty'), ('Alibek', 'Tleubayev', 'Astana'), ('Karina', 'Pak', 'Astana'),
    ('Ruslan', 'Orazbayev', 'Astana'), ('Nazerke', 'Utegenova', 'Astana'), ('Samat', 'Kalibekov', 'Shymkent'),
    ('Alua', 'Suleimenova', 'Shymkent'), ('Berik', 'Zhunusov', 'Karaganda'), ('Meruert', 'Amanova', 'Karaganda'),
    ('Timur', 'Kim', 'Almaty'), ('Aida', 'Ermekova', 'Astana'),
]  # fmt: skip

FEMALE_FIRST = [
    'Aigerim', 'Aruzhan', 'Dana', 'Madina', 'Aliya', 'Kamila', 'Zhanna', 'Asel', 'Dinara', 'Gulnaz', 'Saule',
    'Ainur', 'Togzhan', 'Inkar', 'Akbota', 'Aizhan', 'Balnur', 'Zarina', 'Moldir', 'Anel', 'Yelena', 'Olga',
    'Anastasia', 'Viktoria', 'Diana', 'Aisha', 'Tomiris', 'Zhuldyz', 'Aida', 'Alua', 'Amina', 'Ayim', 'Bota',
    'Gaukhar', 'Karina', 'Laura', 'Meruert', 'Nazerke', 'Rauza', 'Symbat', 'Zere', 'Natalya', 'Svetlana',
    'Irina', 'Ekaterina', 'Marina', 'Polina', 'Tatyana', 'Yulia', 'Sofia', 'Milana', 'Alina', 'Ksenia',
    'Soyeon', 'Minji', 'Yuna', 'Jisoo', 'Lyudmila', 'Raushan', 'Sabina',
]  # fmt: skip
MALE_FIRST = [
    'Daniyar', 'Nurlan', 'Yerlan', 'Arman', 'Askar', 'Bauyrzhan', 'Yerzhan', 'Timur', 'Alikhan', 'Dias',
    'Rustam', 'Azamat', 'Sanzhar', 'Miras', 'Olzhas', 'Nursultan', 'Aibek', 'Marat', 'Ruslan', 'Dmitry',
    'Sergey', 'Andrey', 'Alexei', 'Maxim', 'Ilyas', 'Temirlan', 'Abylai', 'Zhandos', 'Alibek', 'Ansar',
    'Arystan', 'Bekzat', 'Dauren', 'Galym', 'Kairat', 'Madi', 'Nurzhan', 'Rinat', 'Samat', 'Talgat', 'Yeldos',
    'Zhasulan', 'Kanat', 'Baurzhan', 'Berik', 'Aslan', 'Alexander', 'Vladimir', 'Pavel', 'Nikita', 'Roman',
    'Denis', 'Anton', 'Igor', 'Oleg', 'Viktor', 'Minjun', 'Jiho', 'Dongwook', 'Sanghyun',
]  # fmt: skip
# (male form, female form)
SURNAMES = [
    ('Nurlanov', 'Nurlanova'), ('Abenov', 'Abenova'), ('Seitkali', 'Seitkali'), ('Zhakupov', 'Zhakupova'),
    ('Ospanov', 'Ospanova'), ('Bekov', 'Bekova'), ('Tulegenov', 'Tulegenova'), ('Akhmetov', 'Akhmetova'),
    ('Serikbayev', 'Serikbayeva'), ('Omarov', 'Omarova'), ('Kassymov', 'Kassymova'), ('Ibrayev', 'Ibrayeva'),
    ('Sadykov', 'Sadykova'), ('Iskakov', 'Iskakova'), ('Mukhametov', 'Mukhametova'),
    ('Zhumabayev', 'Zhumabayeva'), ('Smagulov', 'Smagulova'), ('Baimukhanov', 'Baimukhanova'),
    ('Yesenov', 'Yesenova'), ('Dzhaksybekov', 'Dzhaksybekova'), ('Alimov', 'Alimova'), ('Amanov', 'Amanova'),
    ('Dauletov', 'Dauletova'), ('Ermekov', 'Ermekova'), ('Zhunusov', 'Zhunusova'), ('Kalibekov', 'Kalibekova'),
    ('Kenzhebayev', 'Kenzhebayeva'), ('Kuanyshev', 'Kuanysheva'), ('Myrzakhmetov', 'Myrzakhmetova'),
    ('Nurgaliyev', 'Nurgaliyeva'), ('Orazbayev', 'Orazbayeva'), ('Rakhimov', 'Rakhimova'),
    ('Sagyndykov', 'Sagyndykova'), ('Seilkhanov', 'Seilkhanova'), ('Suleimenov', 'Suleimenova'),
    ('Tleubayev', 'Tleubayeva'), ('Utegenov', 'Utegenova'), ('Zhaksylykov', 'Zhaksylykova'),
    ('Ivanov', 'Ivanova'), ('Petrov', 'Petrova'), ('Sokolov', 'Sokolova'), ('Smirnov', 'Smirnova'),
    ('Kuznetsov', 'Kuznetsova'), ('Popov', 'Popova'), ('Volkov', 'Volkova'), ('Morozov', 'Morozova'),
    ('Novikov', 'Novikova'), ('Fedorov', 'Fedorova'), ('Mikhailov', 'Mikhailova'), ('Lebedev', 'Lebedeva'),
    ('Kozlov', 'Kozlova'), ('Pavlov', 'Pavlova'),
    ('Kim', 'Kim'), ('Tsoi', 'Tsoi'), ('Pak', 'Pak'), ('Li', 'Li'), ('Khan', 'Khan'), ('Nam', 'Nam'),
    ('Shin', 'Shin'), ('Yun', 'Yun'), ('Tyan', 'Tyan'), ('Khvan', 'Khvan'),
]  # fmt: skip

# City of an attendee, by weight (roughly their share of the population).
CITIES = [
    ('Almaty', 30), ('Astana', 24), ('Shymkent', 14), ('Karaganda', 8),
    ('Aktobe', 7), ('Atyrau', 6), ('Pavlodar', 5), ('Oskemen', 6),
]  # fmt: skip
# Real Kazakh mobile operator prefixes.
PHONE_PREFIXES = ['700', '701', '702', '705', '707', '708', '747', '771', '775', '776', '777', '778']

# Local hour of day -> weight of a purchase: evenings and lunch breaks are
# busy, nights are quiet.
HOUR_WEIGHTS = [
    0.15, 0.08, 0.05, 0.04, 0.05, 0.1, 0.3, 0.6, 1.0, 1.3, 1.5, 1.6,
    2.2, 2.4, 1.8, 1.6, 1.5, 1.7, 2.2, 2.6, 2.8, 2.4, 1.6, 0.6,
]  # fmt: skip

# rating -> comments in Russian, Kazakh and English.
REVIEW_COMMENTS = {
    5: [
        'Fantastic evening, will come again!',
        'Perfect organisation and great sound.',
        'One of the best events this season.',
        'Great atmosphere, friendly staff, smooth entry.',
        'Отличный вечер, обязательно придём ещё!',
        'Организация на высоте, звук великолепный.',
        'Очень душевно, спасибо организаторам!',
        'Лучшее мероприятие этого сезона.',
        'Керемет кеш болды, міндетті түрде тағы келемін!',
        'Ұйымдастыру өте жақсы, дыбыс тамаша.',
        'Бәрі ұнады, ұйымдастырушыларға рахмет!',
        'Өте қызықты болды, достарыма да ұсынамын.',
    ],
    4: [
        'Very good, the queue at the entrance was a bit long.',
        'Great program, parking was hard to find.',
        'Хорошо, но на входе была небольшая очередь.',
        'Отличная программа, только с парковкой было сложно.',
        'Жақсы өтті, тек кіре берісте кезек ұзақ болды.',
        'Бағдарлама ұнады, бірақ көлік қоятын орын табу қиын болды.',
    ],
    3: [
        'Okay, but it started 30 minutes late.',
        'Good content, the hall was too warm.',
        'Нормально, но начало задержали на полчаса.',
        'Интересно, но в зале было душно.',
        'Жаман емес, бірақ басталуы 30 минутқа кешікті.',
    ],
    2: [
        'Sound quality was poor in the back rows.',
        'Too crowded for the venue size.',
        'Плохо слышно на задних рядах.',
        'Артқы қатарларда дыбыс нашар болды.',
    ],
    1: [
        'Disappointing, not what was advertised.',
        'Разочарован: это не то, что обещали в анонсе.',
        'Көңілім толмады, жарнамадағыдай емес екен.',
    ],
}
REVIEW_RATING_WEIGHTS = {5: 55, 4: 30, 3: 8, 2: 4, 1: 3}


def tier(name, kind, price, quantity, description='', sale_end_days=None):
    """A ticket tier. `sale_end_days`: the sale closes this many days before the
    event starts (an early-bird window); None keeps it open."""
    return {
        'name': name,
        'kind': kind,
        'price': Decimal(price),
        'quantity': quantity,
        'description': description,
        'sale_end_days': sale_end_days,
    }


# Per event:
#   key        stable id of the event's random generator
#   days/hour  start, in days from today (Almaty date) and local hour; negative days = already happened
#   offset_minutes  start relative to the moment of seeding (events happening today)
#   fill       share of the capacity sold (0 = no sales)
#   mine       owned by `--organizer` when given (20 of the 60)
#   coorg      key of a demo organizer who is a co-organizer; owner_coorg: `--organizer` is one
#   lead       days before the start that the sale opened (default by layout)
EVENTS = [
    # ── The first 24 ──────────────────────────────────────────────────────────
    {
        'key': 'almaty-symphony', 'title': 'Kazakh Classics Symphony Night', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Zhambyl State Philharmonic',
        'address': 'Kaldayakov St 35, Almaty', 'days': 12, 'hour': 19, 'hours': 2.5,
        'layout': 'seated', 'rows': 12, 'cols': 20, 'premium_rows': 2, 'vip_rows': 3, 'price': '8000',
        'fill': 0.7, 'bookings': 6, 'owner_coorg': True,
    },
    {
        'key': 'almaty-jazz', 'title': 'Almaty Jazz Festival 2026', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Republic Palace',
        'address': 'Dostyk Ave 56, Almaty', 'days': 20, 'hour': 18, 'hours': 5,
        'layout': 'tiers', 'tiers': [
            tier('Early Bird', 'paid', '12000', 200, 'Limited first release', sale_end_days=25),
            tier('Standard', 'paid', '18000', 600),
            tier('VIP', 'paid', '45000', 80, 'Front rows, lounge access'),
        ],
        'fill': 0.5, 'promo': ('JAZZ15', 'percent', '15', 50), 'mine': True,
        'affiliate': ('Instagram @almaty.jazz', 'IGJAZZ', 1240),
    },
    {
        'key': 'almaty-qpop', 'title': 'Q-pop Night Live', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Almaty Arena',
        'address': 'Momyshuly St 37, Almaty', 'days': 9, 'hour': 19, 'hours': 3,
        'layout': 'tiers', 'tiers': [
            tier('Fan zone', 'paid', '15000', 150),
            tier('Seated', 'paid', '25000', 100),
            tier('VIP', 'paid', '60000', 20, 'Meet & greet'),
        ],
        'fill': 1.0, 'waitlist': {'waiting': 18, 'expired': 4, 'converted': 3}, 'coorg': 'arman.bekov',
    },
    {
        'key': 'almaty-opera-kyz-zhibek', 'title': 'Opera "Kyz Zhibek"', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Almaty', 'venue': 'Abai Opera and Ballet Theatre',
        'address': 'Kabanbay Batyr St 110, Almaty', 'days': -14, 'hour': 19, 'hours': 3,
        'layout': 'seated', 'rows': 10, 'cols': 18, 'premium_rows': 1, 'vip_rows': 3, 'price': '6000',
        'fill': 0.85, 'bookings': 4, 'mine': True,
    },
    {
        'key': 'almaty-run-10k', 'title': 'Almaty Autumn Run 10K / 21K', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Almaty', 'venue': 'Republic Square start area',
        'address': 'Zheltoksan St 115, Almaty', 'days': -30, 'hour': 8, 'hours': 5,
        'layout': 'tiers', 'tiers': [
            tier('10K', 'paid', '10000', 300),
            tier('21K Half marathon', 'paid', '15000', 150),
            tier('Kids 2K', 'paid', '3000', 60),
        ],
        'fill': 0.85, 'mine': True,
    },
    {
        'key': 'almaty-tech-summit', 'title': 'Kazakhstan Tech Summit', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Almaty', 'venue': 'Hotel Kazakhstan Conference Hall',
        'address': 'Abay Ave 52, Almaty', 'days': 25, 'hour': 10, 'hours': 8,
        'layout': 'tiers', 'tiers': [
            tier('Student', 'paid', '5000', 100, 'Student ID at the entrance'),
            tier('Standard', 'paid', '25000', 300),
            tier('Business', 'paid', '60000', 50, 'Networking dinner included'),
        ],
        'fill': 0.55, 'service_fee': '5', 'coorg': 'arman.bekov',
    },
    {
        'key': 'almaty-python-meetup', 'title': 'Almaty Python Meetup #42', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Almaty', 'venue': 'SmArt.Point',
        'address': 'Baizakov St 280, Almaty', 'days': 6, 'hour': 19, 'hours': 2.5,
        'layout': 'free', 'capacity': 120, 'fill': 0.8, 'mine': True,
    },
    {
        'key': 'almaty-standup', 'title': 'Almaty Stand-up Night: Fresh Material', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Almaty', 'venue': 'Comedy Bar on Panfilov',
        'address': 'Panfilov St 98, Almaty', 'days': 4, 'hour': 20, 'hours': 2,
        'layout': 'ga', 'price': '7000', 'capacity': 150, 'fill': 0.9,
        'promo': ('FRIENDS20', 'percent', '20', 30),
    },
    {
        'key': 'almaty-cup-football', 'title': 'Kazakhstan Cup Quarter-final: Almaty vs Shymkent', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Almaty', 'venue': 'Central Stadium',
        'address': 'Satpayev St 29/3, Almaty', 'days': 15, 'hour': 18, 'hours': 2,
        'layout': 'tiers', 'tiers': [
            tier('East stand', 'paid', '3000', 400),
            tier('West stand', 'paid', '5000', 300),
            tier('VIP box', 'paid', '20000', 30),
        ],
        'fill': 0.5, 'refundable': False,
    },
    {
        'key': 'almaty-medeu-ice-show', 'title': 'Medeu Ice Show', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Almaty', 'venue': 'Medeu Skating Rink',
        'address': 'Gornaya St 548, Almaty', 'days': 40, 'hour': 18, 'hours': 2,
        'layout': 'ga', 'price': '9000', 'capacity': 200, 'fill': 0.3, 'status': 'cancelled',
        'cancelled_days_ago': 4, 'mine': True,
    },
    {
        'key': 'almaty-pitch-day', 'title': 'Almaty Startup Pitch Day', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Almaty', 'venue': 'Esentai Tower Hall',
        'address': 'Al-Farabi Ave 77/7, Almaty', 'days': -7, 'hour': 14, 'hours': 4,
        'layout': 'ga', 'price': '5000', 'capacity': 200, 'fill': 0.75, 'mine': True,
    },
    {
        'key': 'almaty-shymbulak-opening', 'title': 'Shymbulak Winter Opening Party', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Shymbulak Resort',
        'address': 'Shymbulak Mountain Resort, Almaty', 'days': 60, 'hour': 16, 'hours': 6,
        'layout': 'ga', 'price': '15000', 'capacity': 500, 'fill': 0, 'status': 'draft', 'mine': True,
    },
    {
        'key': 'astana-swan-lake', 'title': 'Ballet "Swan Lake"', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Astana', 'venue': 'Astana Opera',
        'address': 'Kunayev St 1, Astana', 'days': 18, 'hour': 19, 'hours': 3,
        'layout': 'seated', 'rows': 14, 'cols': 24, 'premium_rows': 2, 'vip_rows': 4, 'price': '10000',
        'fill': 0.65, 'bookings': 10, 'mine': True,
    },
    {
        'key': 'astana-mozart', 'title': 'Mozart Evening at the Philharmonic', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Astana', 'venue': 'Kazakhconcert Hall',
        'address': 'Tauelsizdik Ave 50, Astana', 'days': -10, 'hour': 19, 'hours': 2,
        'layout': 'seated', 'rows': 8, 'cols': 16, 'premium_rows': 0, 'vip_rows': 2, 'price': '5000',
        'fill': 0.9, 'bookings': 5, 'mine': True,
    },
    {
        'key': 'astana-digital-forum', 'title': 'Digital Steppe Forum', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Astana', 'venue': 'Astana Hub',
        'address': 'Mangilik El Ave 55/8, Astana', 'days': 30, 'hour': 9, 'hours': 9,
        'layout': 'tiers', 'tiers': [
            tier('Startup', 'paid', '10000', 120),
            tier('Standard', 'paid', '30000', 400),
            tier('Premium', 'paid', '60000', 60, 'Speakers dinner'),
        ],
        'fill': 0.5, 'mine': True,
    },
    {
        'key': 'astana-comedy', 'title': 'Astana Comedy Club Live', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Astana', 'venue': 'Kerwen Hall',
        'address': 'Kabanbay Batyr Ave 62, Astana', 'days': 3, 'hour': 20, 'hours': 2,
        'layout': 'ga', 'price': '6000', 'capacity': 180, 'fill': 0.85,
        'promo': ('ASTANA1000', 'fixed', '1000', None),
    },
    {
        'key': 'astana-half-marathon', 'title': 'Astana Half Marathon 2026', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Astana', 'venue': 'Expo 2017 area',
        'address': 'Mangilik El Ave 53/1, Astana', 'days': -21, 'hour': 8, 'hours': 4,
        'layout': 'tiers', 'tiers': [tier('5K', 'paid', '5000', 200), tier('21K', 'paid', '12000', 250)],
        'fill': 0.85, 'mine': True,
    },
    {
        'key': 'astana-hockey', 'title': 'Hockey Night at Barys Arena', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Astana', 'venue': 'Barys Arena',
        'address': 'Turan Ave 57, Astana', 'days': 11, 'hour': 19, 'hours': 3,
        'layout': 'tiers', 'tiers': [
            tier('Upper tier', 'paid', '3000', 500),
            tier('Lower tier', 'paid', '7000', 300),
            tier('VIP lodge', 'paid', '25000', 20),
        ],
        'fill': 0.4, 'coorg': 'aliya.kassymova',
    },
    {
        'key': 'astana-charity-run', 'title': "Charity Run for the Children's Hospital", 'category': 'Sports',
        'organizer': 'aliya.kassymova', 'city': 'Astana', 'venue': 'Central Park',
        'address': 'Turan Ave 1, Astana', 'days': 14, 'hour': 9, 'hours': 3,
        'layout': 'tiers', 'tiers': [tier('Runner (pay what you want)', 'donation', '2000', 300)],
        'fill': 0.5,
    },
    {
        'key': 'astana-pm-bootcamp', 'title': 'Product Management Bootcamp', 'category': 'Education',
        'organizer': 'nurlan.zhakupov', 'city': 'Astana', 'venue': 'Nazarbayev University, Block C3',
        'address': 'Kabanbay Batyr Ave 53, Astana', 'days': 8, 'hour': 10, 'hours': 7,
        'layout': 'ga', 'price': '35000', 'capacity': 40, 'fill': 1.0,
        'waitlist': {'waiting': 12, 'expired': 2, 'converted': 2, 'offered': 1},
    },
    {
        'key': 'astana-science-show', 'title': 'Family Science Show', 'category': 'Education',
        'organizer': 'aliya.kassymova', 'city': 'Astana', 'venue': 'Palace of Schoolchildren',
        'address': 'Respublika Ave 34, Astana', 'days': 5, 'hour': 11, 'hours': 2,
        'layout': 'tiers', 'tiers': [tier('Child', 'paid', '3000', 100), tier('Adult', 'paid', '4500', 100)],
        'fill': 0.6,
    },
    {
        'key': 'astana-food-festival', 'title': 'Astana Food Festival', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Astana', 'venue': 'Khan Shatyr',
        'address': 'Turan Ave 37, Astana', 'days': 45, 'hour': 12, 'hours': 8,
        'layout': 'ga', 'price': '3000', 'capacity': 800, 'fill': 0, 'status': 'pending', 'mine': True,
    },
    {
        'key': 'astana-js-meetup', 'title': 'Astana JS Meetup', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Astana', 'venue': 'Astana Hub',
        'address': 'Mangilik El Ave 55/8, Astana', 'days': -3, 'hour': 19, 'hours': 2,
        'layout': 'free', 'capacity': 80, 'fill': 0.9, 'mine': True,
    },
    {
        'key': 'astana-chamber-seagull', 'title': 'Chamber Theatre: "The Seagull"', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Astana', 'venue': 'Chamber Stage',
        'address': 'Beibitshilik St 10, Astana', 'days': 7, 'hour': 19, 'hours': 2.5,
        'layout': 'chamber', 'price': '4000', 'fill': 0.8,
    },
    # ── Past, 19 more ─────────────────────────────────────────────────────────
    {
        'key': 'almaty-auezov-enlik-kebek', 'title': 'Auezov Theatre: "Enlik-Kebek"', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Almaty', 'venue': 'Auezov Kazakh Drama Theatre',
        'address': 'Abay Ave 103, Almaty', 'days': -2, 'hour': 19, 'hours': 2.5,
        'layout': 'seated', 'rows': 9, 'cols': 16, 'premium_rows': 1, 'vip_rows': 2, 'price': '5500',
        'fill': 0.75, 'bookings': 4,
        'about': 'A classic of Kazakh drama in a new staging by the theatre company.',
    },
    {
        'key': 'almaty-kbtu-hackathon', 'title': 'KBTU Open Hackathon: 24 Hours', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Almaty', 'venue': 'Kazakh-British Technical University',
        'address': 'Tole Bi St 59, Almaty', 'days': -5, 'hour': 10, 'hours': 24,
        'layout': 'free', 'capacity': 150, 'fill': 0.95,
        'about': 'Teams of up to four build a product in 24 hours; mentors from local tech companies.',
    },
    {
        'key': 'astana-nu-energy-lecture', 'title': 'Public Lecture: Energy of the Steppe', 'category': 'Education',
        'organizer': 'aliya.kassymova', 'city': 'Astana', 'venue': 'Nazarbayev University, Auditorium 1',
        'address': 'Kabanbay Batyr Ave 53, Astana', 'days': -9, 'hour': 17, 'hours': 2,
        'layout': 'free', 'capacity': 220, 'fill': 0.8,
        'about': 'Researchers on wind, solar and the future of the Kazakh power grid. Q&A at the end.',
    },
    {
        'key': 'almaty-steppe-light-expo', 'title': 'Steppe Light: Photography Exhibition', 'category': 'Education',
        'organizer': 'aliya.kassymova', 'city': 'Almaty', 'venue': 'Kasteev State Museum of Arts',
        'address': 'Satpayev St 30A, Almaty', 'days': -12, 'hour': 11, 'hours': 8,
        'layout': 'ga', 'price': '1500', 'capacity': 300, 'fill': 0.6,
        'about': 'Sixty landscape and portrait photographs from the steppe, the Altai and the Caspian coast.',
    },
    {
        'key': 'shymkent-city-run', 'title': 'Shymkent City Run 5K / 10K', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Shymkent', 'venue': 'Ordabasy Square start area',
        'address': 'Tauke Khan Ave, Shymkent', 'days': -17, 'hour': 8, 'hours': 4,
        'layout': 'tiers', 'tiers': [
            tier('5K', 'paid', '4000', 250),
            tier('10K', 'paid', '7000', 200),
            tier('Kids 1K', 'paid', '2000', 80),
        ],
        'fill': 0.8, 'mine': True,
        'about': 'A flat city route with timing chips and a medal for every finisher.',
    },
    {
        'key': 'karaganda-brass-gala', 'title': 'Karaganda Brass & Strings Gala', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Karaganda', 'venue': 'Karaganda Philharmonic Hall',
        'address': 'Bukhar-Zhyrau Ave, Karaganda', 'days': -24, 'hour': 18, 'hours': 2.5,
        'layout': 'seated', 'rows': 8, 'cols': 14, 'premium_rows': 0, 'vip_rows': 2, 'price': '4000',
        'fill': 0.7, 'bookings': 3,
        'about': 'The city orchestra and guest soloists play film music and Kazakh kuis.',
    },
    {
        'key': 'almaty-design-week', 'title': 'Almaty Design Week Talks', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Almaty', 'venue': 'Dostyk Plaza Event Hall',
        'address': 'Al-Farabi Ave 111, Almaty', 'days': -33, 'hour': 10, 'hours': 9,
        'layout': 'tiers', 'tiers': [
            tier('Early Bird', 'paid', '9000', 60, 'First release', sale_end_days=30),
            tier('Student', 'paid', '3000', 60),
            tier('Standard', 'paid', '12000', 200),
            tier('Studio pass', 'paid', '30000', 40, 'Workshops included'),
        ],
        'fill': 0.65, 'promo': ('DESIGN10', 'percent', '10', 40), 'coorg': 'dana.abenova',
        'about': 'Talks and portfolio reviews from product and brand designers.',
    },
    {
        'key': 'astana-kids-robotics', 'title': "Kids' Robotics Festival", 'category': 'Education',
        'organizer': 'aliya.kassymova', 'city': 'Astana', 'venue': 'Astana IT University',
        'address': 'Mangilik El Ave 55/11, Astana', 'days': -40, 'hour': 11, 'hours': 6,
        'layout': 'tiers', 'tiers': [
            tier('Child', 'paid', '2500', 150),
            tier('Family (2 adults + 2 children)', 'paid', '8000', 60),
        ],
        'fill': 0.85, 'mine': True,
        'about': 'Build and race a robot, meet student teams and try a 3D printer. Ages 6-14.',
    },
    {
        'key': 'almaty-rock-legends', 'title': 'Rock Legends: Tribute Night', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Republic Palace',
        'address': 'Dostyk Ave 56, Almaty', 'days': -48, 'hour': 19, 'hours': 3,
        'layout': 'seated', 'rows': 16, 'cols': 24, 'premium_rows': 2, 'vip_rows': 4, 'price': '9000',
        'fill': 0.8, 'bookings': 8, 'coorg': 'arman.bekov',
        'about': 'Four tribute bands play the songs everyone knows.',
    },
    {
        'key': 'shymkent-comedy-gala', 'title': 'Shymkent Comedy Gala', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Shymkent', 'venue': 'Shymkent Palace of Culture',
        'address': 'Tauke Khan Ave, Shymkent', 'days': -55, 'hour': 19, 'hours': 2,
        'layout': 'ga', 'price': '5000', 'capacity': 400, 'fill': 0.75, 'owner_coorg': True,
        'affiliate': ('Telegram @shymkent.events', 'TGSHYM', 640),
        'about': 'Comedians from Shymkent, Almaty and Astana in one show.',
    },
    {
        'key': 'astana-chess-open', 'title': 'Astana Open Chess Cup', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Astana', 'venue': 'Palace of Peace and Reconciliation',
        'address': 'Tauelsizdik Ave 57, Astana', 'days': -63, 'hour': 10, 'hours': 8,
        'layout': 'tiers', 'tiers': [tier('Player', 'paid', '6000', 120), tier('Spectator', 'paid', '1000', 150)],
        'fill': 0.7,
        'about': 'A rapid tournament open to all ratings, with a spectator gallery.',
    },
    {
        'key': 'almaty-startup-grind', 'title': 'Startup Grind Almaty: Fundraising Night', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Almaty', 'venue': 'Esentai Tower Hall',
        'address': 'Al-Farabi Ave 77/7, Almaty', 'days': -72, 'hour': 18, 'hours': 3,
        'layout': 'ga', 'price': '3500', 'capacity': 120, 'fill': 0.85, 'mine': True,
        'promo': ('GRIND20', 'percent', '20', 25),
        'about': 'Three founders and two investors on raising a first round in Central Asia.',
    },
    {
        'key': 'astana-jazz-evenings', 'title': 'Astana Jazz Evenings', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Astana', 'venue': 'Astana Opera Foyer Hall',
        'address': 'Kunayev St 1, Astana', 'days': -84, 'hour': 20, 'hours': 2.5,
        'layout': 'ga', 'price': '7500', 'capacity': 150, 'fill': 0.9,
        'about': 'A trio, a quartet and a late jam session in the opera foyer.',
    },
    {
        'key': 'online-data-analytics-webinar', 'title': 'Online Webinar: Data Analytics from Scratch',
        'category': 'Education', 'organizer': 'nurlan.zhakupov', 'city': 'Online', 'venue': 'Online',
        'address': '', 'days': -96, 'hour': 19, 'hours': 2, 'online': True, 'link': 'https://meet.example.com/da-101',
        'layout': 'free', 'capacity': 500, 'fill': 0.6, 'mine': True,
        'about': 'SQL, spreadsheets and a first dashboard in two hours. The link arrives with your ticket.',
    },
    {
        'key': 'karaganda-mining-forum', 'title': 'Karaganda Mining Technology Forum', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Karaganda', 'venue': 'Buketov Karaganda University Hall',
        'address': 'Universitetskaya St 28, Karaganda', 'days': -110, 'hour': 9, 'hours': 8,
        'layout': 'tiers', 'tiers': [
            tier('Early delegate', 'paid', '12000', 80, 'First release', sale_end_days=35),
            tier('Delegate', 'paid', '15000', 200),
            tier('Student', 'paid', '3000', 100),
        ],
        'fill': 0.6, 'service_fee': '3',
        'about': 'Automation, safety and ore processing: talks and a supplier exhibition.',
    },
    {
        'key': 'almaty-winter-ballet-gala', 'title': 'Winter Ballet Gala', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Almaty', 'venue': 'Abai Opera and Ballet Theatre',
        'address': 'Kabanbay Batyr St 110, Almaty', 'days': -128, 'hour': 19, 'hours': 3,
        'layout': 'seated', 'rows': 12, 'cols': 20, 'premium_rows': 2, 'vip_rows': 3, 'price': '7000',
        'fill': 0.92, 'bookings': 6, 'mine': True,
        'about': 'Excerpts from the ballet repertoire danced by the theatre soloists.',
    },
    {
        'key': 'shymkent-craft-fair', 'title': 'Shymkent Autumn Craft Fair', 'category': 'Business',
        'organizer': 'aliya.kassymova', 'city': 'Shymkent', 'venue': 'Shymkent Exhibition Hall',
        'address': 'Tauke Khan Ave, Shymkent', 'days': -150, 'hour': 11, 'hours': 8,
        'layout': 'ga', 'price': '1000', 'capacity': 700, 'fill': 0.5,
        'about': 'Ceramics, felt, leather and food from sixty makers of the south.',
    },
    {
        'key': 'almaty-charity-concert', 'title': 'Concert for the Flood Relief Fund', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Zhambyl State Philharmonic',
        'address': 'Kaldayakov St 35, Almaty', 'days': -185, 'hour': 18, 'hours': 2.5,
        'layout': 'tiers', 'tiers': [tier('Donation ticket (pay what you want)', 'donation', '3000', 300)],
        'fill': 0.7,
        'about': 'Every tenge goes to the relief fund; the artists play without a fee.',
    },
    {
        'key': 'astana-night-run', 'title': 'Astana Night Run', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Astana', 'venue': 'Expo 2017 area',
        'address': 'Mangilik El Ave 53/1, Astana', 'days': -230, 'hour': 21, 'hours': 3,
        'layout': 'tiers', 'tiers': [tier('5K', 'paid', '4500', 200), tier('10K', 'paid', '7000', 150)],
        'fill': 0.85,
        'about': 'A lit route through the Expo grounds; glow sticks at the start.',
    },
    # ── Happening today, 3 ────────────────────────────────────────────────────
    {
        'key': 'almaty-ux-workshop', 'title': 'UX Research Workshop', 'category': 'Education',
        'organizer': 'nurlan.zhakupov', 'city': 'Almaty', 'venue': 'AlmaU Auditorium',
        'address': 'Rozybakiev St 227, Almaty', 'offset_minutes': -90, 'hours': 4,
        'layout': 'ga', 'price': '8000', 'capacity': 60, 'fill': 0.9, 'mine': True,
        'about': 'Interviews, synthesis and a usability test on a real product, in small groups.',
    },
    {
        'key': 'online-finance-webinar', 'title': 'Live Webinar: Personal Finance Basics', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Online', 'venue': 'Online', 'address': '',
        'offset_minutes': -30, 'hours': 2, 'online': True, 'link': 'https://meet.example.com/finance-basics',
        'layout': 'free', 'capacity': 300, 'fill': 0.7,
        'about': 'Budgeting, saving and the first steps in investing. Live questions in the chat.',
    },
    {
        'key': 'almaty-piano-evening', 'title': 'Sunset Piano Evening', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Kasteev State Museum of Arts',
        'address': 'Satpayev St 30A, Almaty', 'offset_minutes': 180, 'hours': 2,
        'layout': 'ga', 'price': '6000', 'capacity': 80, 'fill': 1.0,
        'waitlist': {'waiting': 9, 'expired': 2, 'converted': 1},
        'about': 'Chopin, Rachmaninov and Kazakh composers in the museum hall, at sunset.',
    },
    # ── Upcoming, 7 more ──────────────────────────────────────────────────────
    {
        'key': 'shymkent-music-fest', 'title': 'Shymkent Spring Music Fest', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Shymkent', 'venue': 'Kazhymukan Stadium',
        'address': 'Tauke Khan Ave, Shymkent', 'days': 35, 'hour': 17, 'hours': 6,
        'layout': 'tiers', 'tiers': [
            tier('Early Bird', 'paid', '8000', 300, 'Limited first release', sale_end_days=20),
            tier('Standard', 'paid', '12000', 700),
            tier('VIP', 'paid', '30000', 60, 'Front zone, lounge'),
        ],
        'fill': 0.35, 'coorg': 'yerlan.ospanov', 'affiliate': ('Instagram @shymkent.fest', 'IGSHYM', 910),
        'about': 'A day of live music on the stadium lawn with local and national artists.',
    },
    {
        'key': 'astana-startup-weekend', 'title': 'Astana Startup Weekend', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Astana', 'venue': 'Astana Hub',
        'address': 'Mangilik El Ave 55/8, Astana', 'days': 42, 'hour': 18, 'hours': 48,
        'layout': 'tiers', 'tiers': [
            tier('Participant', 'paid', '5000', 80, 'Food and workspace included'),
            tier('Mentor', 'free', '0', 20, 'By invitation'),
        ],
        'fill': 0.5,
        'about': 'Pitch on Friday, build over the weekend, present to a jury on Sunday.',
    },
    {
        'key': 'almaty-verdi-gala', 'title': 'Verdi Gala Evening', 'category': 'Theatre',
        'organizer': 'saule.tulegenova', 'city': 'Almaty', 'venue': 'Abai Opera and Ballet Theatre',
        'address': 'Kabanbay Batyr St 110, Almaty', 'days': 50, 'hour': 19, 'hours': 3,
        'layout': 'seated', 'rows': 14, 'cols': 22, 'premium_rows': 2, 'vip_rows': 4, 'price': '9500',
        'fill': 0.4, 'bookings': 5,
        'about': 'Arias and ensembles from La Traviata, Rigoletto and Aida.',
    },
    {
        'key': 'karaganda-magic-show', 'title': "Karaganda Children's Magic Show", 'category': 'Education',
        'organizer': 'aliya.kassymova', 'city': 'Karaganda', 'venue': 'Karaganda State Circus',
        'address': 'Karaganda', 'days': 58, 'hour': 12, 'hours': 2,
        'layout': 'ga', 'price': '2500', 'capacity': 250, 'fill': 0.3,
        'about': 'Illusions, balloons and a surprise guest for the whole family.',
    },
    {
        'key': 'astana-art-expo', 'title': 'Contemporary Art Expo Astana', 'category': 'Education',
        'organizer': 'aliya.kassymova', 'city': 'Astana', 'venue': 'National Museum of the Republic of Kazakhstan',
        'address': 'Tauelsizdik Ave 54, Astana', 'days': 66, 'hour': 11, 'hours': 8,
        'layout': 'ga', 'price': '2000', 'capacity': 500, 'fill': 0.2,
        'about': 'Thirty artists from Kazakhstan and Central Asia: painting, video and installation.',
    },
    {
        'key': 'almaty-trail-race', 'title': 'Kok-Zhailau Trail Race', 'category': 'Sports',
        'organizer': 'yerlan.ospanov', 'city': 'Almaty', 'venue': 'Medeu Valley trailhead',
        'address': 'Gornaya St 548, Almaty', 'days': 75, 'hour': 7, 'hours': 8,
        'layout': 'tiers', 'tiers': [tier('15K', 'paid', '9000', 200), tier('30K', 'paid', '14000', 120)],
        'fill': 0.25,
        'about': 'A mountain route above the city, with aid stations and a finisher shirt.',
    },
    {
        'key': 'online-django-workshop', 'title': 'Online Workshop: Django for Beginners', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Online', 'venue': 'Online', 'address': '',
        'days': 85, 'hour': 19, 'hours': 3, 'online': True, 'link': 'https://meet.example.com/django-101',
        'layout': 'ga', 'price': '6000', 'capacity': 200, 'fill': 0.3,
        'about': 'Build and deploy a small web app. Recordings are shared with every participant.',
    },
    # ── Drafts, pending and rejected ──────────────────────────────────────────
    {
        'key': 'astana-new-year-gala', 'title': 'New Year Charity Gala', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Astana', 'venue': 'Astana Opera',
        'address': 'Kunayev St 1, Astana', 'days': 75, 'hour': 19, 'hours': 3,
        'layout': 'ga', 'price': '12000', 'capacity': 600, 'fill': 0, 'status': 'draft',
        'about': 'A charity concert and dinner. Programme to be announced.',
    },
    {
        'key': 'almaty-ai-bootcamp', 'title': 'AI Engineering Bootcamp', 'category': 'Education',
        'organizer': 'nurlan.zhakupov', 'city': 'Almaty', 'venue': 'Satbayev University',
        'address': 'Satbayev St 22, Almaty', 'days': 100, 'hour': 10, 'hours': 8,
        'layout': 'ga', 'price': '80000', 'capacity': 30, 'fill': 0, 'status': 'draft',
        'about': 'Four weekends on applied machine learning. Draft: the curriculum is being finalised.',
    },
    {
        'key': 'shymkent-tech-meetup', 'title': 'Shymkent Tech Meetup #1', 'category': 'Technology',
        'organizer': 'nurlan.zhakupov', 'city': 'Shymkent', 'venue': 'Auezov South Kazakhstan University',
        'address': 'Tauke Khan Ave 5, Shymkent', 'days': 21, 'hour': 18, 'hours': 3,
        'layout': 'free', 'capacity': 100, 'fill': 0, 'status': 'pending',
        'about': 'The first developer meetup in Shymkent: two talks and networking.',
    },
    {
        'key': 'almaty-street-food', 'title': 'Almaty Street Food Weekend', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Almaty', 'venue': 'Panfilov Park',
        'address': 'Panfilov Park, Almaty', 'days': 30, 'hour': 12, 'hours': 10,
        'layout': 'ga', 'price': '1500', 'capacity': 1000, 'fill': 0, 'status': 'pending',
        'about': 'Forty food trucks and stalls, live music and a cooking stage.',
    },
    {
        'key': 'almaty-open-air-night', 'title': 'Open Air Night Fest', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Almaty', 'venue': 'Panfilov Park',
        'address': 'Panfilov Park, Almaty', 'days': 50, 'hour': 18, 'hours': 6,
        'layout': 'ga', 'price': '5000', 'capacity': 1500, 'fill': 0, 'status': 'rejected', 'mine': True,
        'about': 'An open-air concert. Rejected: no venue permit was attached.',
    },
    {
        'key': 'astana-motor-show', 'title': 'Astana Motor Show', 'category': 'Business',
        'organizer': 'arman.bekov', 'city': 'Astana', 'venue': 'Expo 2017 area',
        'address': 'Mangilik El Ave 53/1, Astana', 'days': 65, 'hour': 11, 'hours': 8,
        'layout': 'ga', 'price': '4000', 'capacity': 2000, 'fill': 0, 'status': 'rejected',
        'about': 'New cars and motorcycles. Rejected: the description was incomplete.',
    },
    # ── Cancelled, with refunds ───────────────────────────────────────────────
    {
        'key': 'karaganda-rock-night', 'title': 'Karaganda Rock Night', 'category': 'Music',
        'organizer': 'dana.abenova', 'city': 'Karaganda', 'venue': 'Shakhtyor Stadium',
        'address': 'Karaganda', 'days': 23, 'hour': 19, 'hours': 4,
        'layout': 'tiers', 'tiers': [tier('General', 'paid', '5000', 300), tier('VIP', 'paid', '12000', 40)],
        'fill': 0.4, 'status': 'cancelled', 'cancelled_days_ago': 5,
        'about': 'Cancelled by the organizer after the headliner withdrew. All tickets were refunded.',
    },
]  # fmt: skip

TITLES = {spec['title'] for spec in EVENTS}
