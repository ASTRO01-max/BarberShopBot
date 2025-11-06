barbershop_bot/
│
├── app/                          # Asosiy bot ilovasi (root layer)
│   ├── main.py                   # Entry point (bot.run)
│   ├── config.py                 # Config, environment, token va DB sozlamalar
│   ├── logger.py                 # Logging settings
│   ├── dependencies.py           # Bot va DB dependency'lar
│   └── __init__.py
│
├── shared/                       # Umumiy util va bazaviy klasslar
│   ├── utils/                    # Yordamchi funksiyalar
│   │   ├── formatters.py
│   │   ├── validators.py
│   │   └── time_utils.py
│   ├── keyboards/                # Inline va Reply keyboard factory'lar
│   │   ├── main_menu.py
│   │   ├── booking_menu.py
│   │   └── admin_menu.py
│   ├── middlewares/
│   │   └── auth_middleware.py
│   ├── constants/
│   │   ├── messages.py
│   │   └── texts.py
│   └── __init__.py
│
├── entities/                     # Domen obyektlari (data models)
│   ├── users/                    # OrdinaryUser modeli
│   │   ├── model.py              # SQLAlchemy modeli
│   │   └── repo.py               # ORM repository
│   ├── barbers/
│   │   ├── model.py
│   │   └── repo.py
│   ├── services/
│   │   ├── model.py
│   │   └── repo.py
│   ├── orders/
│   │   ├── model.py
│   │   └── repo.py
│   └── __init__.py
│
├── features/                     # Har bir xususiyat (feature) uchun alohida modul
│   ├── booking/                  # Soch olishni bron qilish logikasi
│   │   ├── ui/                   # Telegram interfeysi (handlers, keyboards)
│   │   │   ├── handlers.py
│   │   │   └── keyboards.py
│   │   ├── domain/               # Asosiy biznes qoidalar
│   │   │   ├── service.py
│   │   │   └── validators.py
│   │   ├── data/                 # DB bilan ishlovchi qatlam (repository)
│   │   │   └── booking_repo.py
│   │   └── __init__.py
│   │
│   ├── admin_panel/              # Admin uchun xususiyatlar
│   │   ├── ui/
│   │   │   ├── handlers.py
│   │   │   └── keyboards.py
│   │   ├── domain/
│   │   │   └── service.py
│   │   └── __init__.py
│   │
│   ├── feedback/                 # Fikr-mulohaza moduli (agar mavjud bo‘lsa)
│   │   ├── ui/
│   │   │   └── handlers.py
│   │   └── domain/
│   │       └── service.py
│   │
│   └── __init__.py
│
├── infrastructure/               # Tashqi tizimlar bilan ishlovchi qatlam
│   ├── database/                 # SQLAlchemy setup, session, metadata
│   │   ├── base.py
│   │   ├── session.py
│   │   └── migrations/
│   │       └── (alembic scripts)
│   ├── api_clients/              # Agar tashqi API’lar bo‘lsa
│   │   └── telegram_api.py
│   └── __init__.py
│
├── tests/                        # Unit va integration testlar
│   ├── test_booking.py
│   ├── test_users.py
│   └── conftest.py
│
└── requirements.txt
