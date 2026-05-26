from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),

    # API
    path("api/auth/", include("accounts.urls")),
    path("api/",      include("chat.urls")),

    # Pages
    path("",          TemplateView.as_view(template_name="landing.html"),             name="page-landing"),
    path("signup/",    TemplateView.as_view(template_name="accounts/signup.html"),    name="page-signup"),
    path("login/",     TemplateView.as_view(template_name="accounts/login.html"),     name="page-login"),
    path("dashboard/", TemplateView.as_view(template_name="chat/dashboard.html"),     name="page-dashboard"),
    path("profile/",   TemplateView.as_view(template_name="accounts/profile.html"),   name="page-profile"),
    path("join/<uuid:slug>/", TemplateView.as_view(template_name="chat/join.html"),   name="page-join"),

    # Legacy chat template
    path("", include("chat.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
