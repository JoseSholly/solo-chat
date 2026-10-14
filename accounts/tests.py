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
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

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


@pytest.fixture
def bob(django_user_model):
    return django_user_model.objects.create_user(
        email="bob@example.com",
        username="bob",
        display_name="Bob",
        password="old-password-2",
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


# -- Cached authentication ----------------------------------------------------
# The logged-in user is cached so a request doesn't spend a database round trip
# on it. The cache must never outlive a change to the user.


def _authed(user):
    client = APIClient()
    token = str(AccessToken.for_user(user))
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _query_count(fn):
    with CaptureQueriesContext(connection) as ctx:
        res = fn()
    return res, len(ctx.captured_queries)


def test_user_is_read_once_then_served_from_cache(alice):
    client = _authed(alice)
    first, queries = _query_count(lambda: client.get("/api/auth/me/"))
    assert first.status_code == 200 and queries == 1  # the user lookup

    second, queries = _query_count(lambda: client.get("/api/auth/me/"))
    assert second.status_code == 200 and queries == 0


def test_profile_edit_is_visible_on_the_next_request(alice):
    client = _authed(alice)
    client.get("/api/auth/me/")  # cached
    res = client.patch("/api/auth/me/", {"display_name": "Alicia"}, format="json")
    assert res.status_code == 200
    assert client.get("/api/auth/me/").json()["display_name"] == "Alicia"


def test_saving_a_deactivated_user_locks_them_out_at_once(alice):
    client = _authed(alice)
    assert client.get("/api/auth/me/").status_code == 200  # cached

    alice.is_active = False
    alice.save()
    assert client.get("/api/auth/me/").status_code == 401


def test_bulk_update_locks_them_out_at_once(alice, django_user_model):
    client = _authed(alice)
    assert client.get("/api/auth/me/").status_code == 200  # cached

    # update() sends no signals; the manager clears the cache itself
    django_user_model.objects.filter(pk=alice.pk).update(is_active=False)
    assert client.get("/api/auth/me/").status_code == 401


def test_bulk_update_method_is_covered_too(alice, django_user_model):
    client = _authed(alice)
    client.get("/api/auth/me/")
    alice.display_name = "Changed"
    django_user_model.objects.bulk_update([alice], ["display_name"])
    assert client.get("/api/auth/me/").json()["display_name"] == "Changed"


def test_deleting_a_user_locks_them_out_at_once(alice):
    client = _authed(alice)
    assert client.get("/api/auth/me/").status_code == 200  # cached
    alice.delete()
    assert client.get("/api/auth/me/").status_code == 401


def test_password_reset_clears_the_cached_user(alice):
    from accounts.authentication import user_cache_key

    _authed(alice).get("/api/auth/me/")
    assert cache.get(user_cache_key(alice.pk)) is not None
    alice.set_password("something-new-1")
    alice.save()
    assert cache.get(user_cache_key(alice.pk)) is None


def test_group_and_permission_changes_clear_the_cached_user(alice, bob):
    from django.contrib.auth.models import Group, Permission

    from accounts.authentication import user_cache_key

    group = Group.objects.create(name="staff-ish")
    perm = Permission.objects.first()

    def cached(user):
        cache.set(user_cache_key(user.pk), user, 60)

    def is_cached(user):
        return cache.get(user_cache_key(user.pk)) is not None

    cached(alice)
    alice.groups.add(group)  # from the user's side
    assert not is_cached(alice)

    cached(alice)
    cached(bob)
    group.user_set.add(bob)  # from the group's side
    assert not is_cached(bob) and is_cached(alice)

    cached(alice)
    alice.user_permissions.add(perm)
    assert not is_cached(alice)

    cached(alice)
    cached(bob)
    group.user_set.clear()  # reverse clear: ids unknown, looked up
    assert not is_cached(alice) and not is_cached(bob)


def test_a_change_never_outlives_the_ttl_even_if_nothing_cleared_it(alice, monkeypatch):
    """Backstop for edits made behind Django's back (raw SQL): the cached copy
    is dropped by the cache itself after USER_CACHE_SECONDS."""
    from accounts import authentication

    seen = []
    real_set = cache.set
    monkeypatch.setattr(
        cache,
        "set",
        lambda key, value, timeout=None: (
            seen.append(timeout),
            real_set(key, value, timeout),
        ),
    )
    _authed(alice).get("/api/auth/me/")
    assert seen == [authentication.USER_CACHE_SECONDS]
    assert authentication.USER_CACHE_SECONDS <= 60


def test_requests_still_work_when_the_cache_is_down(alice, monkeypatch):
    def broken(*args, **kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(cache, "get", broken)
    monkeypatch.setattr(cache, "set", broken)
    monkeypatch.setattr(cache, "delete", broken)

    client = _authed(alice)
    assert client.get("/api/auth/me/").status_code == 200  # read from the database
    alice.display_name = "Still saves"
    alice.save()  # clearing the cache fails quietly
    assert client.get("/api/auth/me/").json()["display_name"] == "Still saves"
