import json
import re
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.email import ResendEmailBackend

FORGOT = "/api/auth/password/forgot/"
RESET = "/api/auth/password/reset/"
pytestmark = pytest.mark.django_db

LINK_RE = re.compile(r"/reset-password/(?P<uid>[^/\s]+)/(?P<token>[^/\s]+)/")


@pytest.fixture(autouse=True)
def fresh_throttle():
    # The forgot-password throttle counts in the cache; start every test at zero.
    cache.clear()


@pytest.fixture
def alice(django_user_model):
    return django_user_model.objects.create_user(
        email="alice@example.com",
        username="alice",
        display_name="Alice",
        password="old-password-1",
    )


def _forgot(email, **extra):
    return APIClient().post(FORGOT, {"email": email}, format="json", **extra)


def _link_from_outbox():
    match = LINK_RE.search(mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match["uid"], match["token"]


def _reset(uid, token, password="new-password-1"):
    return APIClient().post(
        RESET, {"uid": uid, "token": token, "password": password}, format="json"
    )


# -- Forgot ------------------------------------------------------------------


def test_forgot_sends_a_one_hour_link(alice, settings):
    settings.SITE_URL = "https://chat.example.com"
    res = _forgot("Alice@Example.com")
    assert res.status_code == 200

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["alice@example.com"]
    assert "https://chat.example.com/reset-password/" in msg.body
    assert "60 minutes" in msg.body
    html = msg.alternatives[0][0]
    assert "https://chat.example.com/reset-password/" in html

    uid, token = _link_from_outbox()
    check = APIClient().get(RESET, {"uid": uid, "token": token})
    assert check.json() == {"valid": True}


def test_forgot_builds_the_link_from_the_request_without_site_url(alice, settings):
    settings.SITE_URL = ""
    _forgot("alice@example.com")
    assert "http://testserver/reset-password/" in mail.outbox[0].body


def test_forgot_does_not_reveal_who_has_an_account(alice, django_user_model):
    known = _forgot("alice@example.com").json()
    unknown = _forgot("nobody@example.com").json()
    assert known == unknown
    assert len(mail.outbox) == 1  # only the real account got mail

    alice.is_active = False
    alice.save()
    _forgot("alice@example.com")
    assert len(mail.outbox) == 1  # disabled accounts get nothing


def test_forgot_rejects_a_malformed_email():
    res = _forgot("not-an-email")
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_email"


def test_forgot_is_rate_limited(alice):
    for _ in range(5):
        assert _forgot("alice@example.com").status_code == 200
    assert _forgot("alice@example.com").status_code == 429


# -- Reset -------------------------------------------------------------------


def test_reset_sets_the_password_and_signs_in(alice):
    _forgot("alice@example.com")
    uid, token = _link_from_outbox()

    res = _reset(uid, token)
    assert res.status_code == 200
    body = res.json()
    assert body["access"] and body["refresh"]
    assert body["user"]["username"] == "alice"

    alice.refresh_from_db()
    assert alice.check_password("new-password-1")
    assert not alice.check_password("old-password-1")


def test_reset_link_works_only_once(alice):
    _forgot("alice@example.com")
    uid, token = _link_from_outbox()
    assert _reset(uid, token).status_code == 200

    again = _reset(uid, token, password="another-password-2")
    assert again.status_code == 400
    assert again.json()["code"] == "invalid_link"
    assert APIClient().get(RESET, {"uid": uid, "token": token}).json() == {
        "valid": False
    }


def test_reset_link_expires_after_an_hour(alice):
    _forgot("alice@example.com")
    uid, token = _link_from_outbox()

    later = datetime.now() + timedelta(hours=1, minutes=1)
    with mock.patch.object(default_token_generator, "_now", return_value=later):
        res = _reset(uid, token)
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_link"


def test_reset_rejects_a_tampered_link(alice):
    _forgot("alice@example.com")
    uid, token = _link_from_outbox()
    assert _reset(uid, token[:-1] + "x").json()["code"] == "invalid_link"
    assert _reset("garbage", token).json()["code"] == "invalid_link"


def test_reset_rejects_a_short_password_and_keeps_the_link(alice):
    _forgot("alice@example.com")
    uid, token = _link_from_outbox()

    res = _reset(uid, token, password="short")
    assert res.status_code == 400
    assert res.json()["code"] == "invalid_password"
    assert _reset(uid, token).status_code == 200  # still usable


def test_reset_signs_out_every_other_session(alice):
    other_device = RefreshToken.for_user(alice)
    _forgot("alice@example.com")
    uid, token = _link_from_outbox()
    _reset(uid, token)

    res = APIClient().post(
        "/api/auth/token/refresh/", {"refresh": str(other_device)}, format="json"
    )
    assert res.status_code == 401


# -- Resend backend ----------------------------------------------------------


def _message():
    msg = EmailMultiAlternatives(
        subject="Hi", body="plain", from_email="Solo <a@x.com>", to=["b@y.com"]
    )
    msg.attach_alternative("<p>html</p>", "text/html")
    return msg


def test_resend_backend_posts_the_message(settings):
    settings.RESEND_API_KEY = "re_test"
    with mock.patch("accounts.email.urllib.request.urlopen") as urlopen:
        sent = ResendEmailBackend().send_messages([_message()])

    assert sent == 1
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.resend.com/emails"
    assert request.get_header("Authorization") == "Bearer re_test"
    assert json.loads(request.data) == {
        "from": "Solo <a@x.com>",
        "to": ["b@y.com"],
        "subject": "Hi",
        "text": "plain",
        "html": "<p>html</p>",
    }


def test_resend_backend_failures(settings):
    settings.RESEND_API_KEY = "re_test"
    error = urllib.error.URLError("down")
    with mock.patch("accounts.email.urllib.request.urlopen", side_effect=error):
        assert ResendEmailBackend(fail_silently=True).send_messages([_message()]) == 0
        with pytest.raises(urllib.error.URLError):
            ResendEmailBackend().send_messages([_message()])
