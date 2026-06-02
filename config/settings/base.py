from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent



INSTALLED_APPS = [
    "daphne",  # must be first — enables ASGI runserver
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "channels",
    "chat",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

REST_FRAMEWORK = {
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}

JAZZMIN_SETTINGS = {
    # ── Branding ──────────────────────────────────────────────────────────
    "site_title":        "ChatRooms Admin",
    "site_header":       "ChatRooms",
    "site_brand":        "ChatRooms",
    "site_logo_classes": "img-circle",
    "welcome_sign":      "Welcome to ChatRooms Admin",
    "copyright":         "ChatRooms",

    # ── Top-bar search ────────────────────────────────────────────────────
    "search_model": ["accounts.User", "chat.Room"],

    # ── User avatar ───────────────────────────────────────────────────────
    "user_avatar": None,

    # ── Top menu links ────────────────────────────────────────────────────
    "topmenu_links": [
        {"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "Site", "url": "/",           "new_window": True},
    ],

    # ── Sidebar custom links ──────────────────────────────────────────────
    "usermenu_links": [
        {"name": "View Site", "url": "/", "new_window": True, "icon": "fas fa-globe"},
    ],

    # ── Sidebar icons (Font Awesome 5) ────────────────────────────────────
    "icons": {
        "accounts":                            "fas fa-users-cog",
        "accounts.User":                       "fas fa-user-circle",
        "auth":                                "fas fa-shield-alt",
        "auth.Group":                          "fas fa-layer-group",
        "chat":                                "fas fa-comments",
        "chat.Room":                           "fas fa-hashtag",
        "chat.Message":                        "fas fa-comment-dots",
        "chat.RoomMembership":                 "fas fa-door-open",
        "token_blacklist":                     "fas fa-lock",
        "token_blacklist.BlacklistedToken":    "fas fa-ban",
        "token_blacklist.OutstandingToken":    "fas fa-key",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",

    # ── Sidebar app/model ordering ────────────────────────────────────────
    "order_with_respect_to": [
        "accounts",
        "chat",
        "auth",
        "token_blacklist",
    ],

    # ── Hide clutter ──────────────────────────────────────────────────────
    "hide_apps":   [],
    "hide_models": [],

    # ── UI ────────────────────────────────────────────────────────────────
    "show_ui_builder":      False,
    "changeform_format":    "horizontal_tabs",
    "language_chooser":     False,
    "related_modal_active": True,
    "default_theme_mode":   "light",
}

JAZZMIN_UI_TWEAKS = {
    # ── Text sizes ────────────────────────────────────────────────────────
    "navbar_small_text":         False,
    "footer_small_text":         False,
    "body_small_text":           False,
    "brand_small_text":          False,

    # ── Colours ───────────────────────────────────────────────────────────
    "brand_colour":              "navbar-primary",
    "accent":                    "accent-primary",
    "navbar":                    "navbar-dark navbar-navy",
    "navbar_fixed":              True,
    "no_navbar_border":          True,

    # ── Sidebar ───────────────────────────────────────────────────────────
    "sidebar":                   "sidebar-dark-primary",
    "sidebar_fixed":             True,
    "sidebar_nav_small_text":    False,
    "sidebar_disable_expand":    False,
    "sidebar_nav_child_indent":  True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style":  False,
    "sidebar_nav_flat_style":    False,

    # ── Layout ────────────────────────────────────────────────────────────
    "layout_boxed":  False,
    "footer_fixed":  False,

    # ── Theme — light content area, dark sidebar (matches screenshot) ─────
    "theme": "default",

    # ── Buttons ───────────────────────────────────────────────────────────
    "button_classes": {
        "primary":   "btn-primary",
        "secondary": "btn-outline-secondary",
        "info":      "btn-info",
        "warning":   "btn-warning",
        "danger":    "btn-danger",
        "success":   "btn-success",
    },
}