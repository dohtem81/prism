from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from services.api.app.auth import dependencies
from services.api.app.auth.dependencies import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    resolve_authenticated_user_id,
)
from services.api.app.auth.token_store import RefreshState, TokenStore, TokenStoreUnavailable
from services.api.app.infra.settings import settings
from services.api.app.main import app
from tests.support.fake_redis import FakeRedis


@pytest.fixture()
def store():
    fake = FakeRedis()
    token_store = TokenStore(fake)
    token_store.fake = fake  # type: ignore[attr-defined]
    with patch.object(dependencies, "token_store", token_store):
        yield token_store


@pytest.fixture()
def client(store):
    return TestClient(app)


def _claims(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


def test_access_token_carries_required_claims(store) -> None:
    claims = _claims(create_access_token("user_1"))

    assert claims["sub"] == "user_1"
    assert claims["type"] == "access"
    assert claims["jti"] and claims["iat"] and claims["exp"] > claims["iat"]
    assert claims["exp"] - claims["iat"] <= settings.access_token_ttl_minutes * 60


def test_access_tokens_have_unique_jti(store) -> None:
    assert _claims(create_access_token("u"))["jti"] != _claims(create_access_token("u"))["jti"]


def test_refresh_token_is_long_lived_and_registered(store) -> None:
    token = create_refresh_token("user_1")
    claims = _claims(token)

    assert claims["type"] == "refresh"
    assert claims["exp"] - claims["iat"] == settings.refresh_token_ttl_days * 86400
    assert store.fake.hashes[f"auth:refresh:{claims['jti']}"]["user_id"] == "user_1"
    assert store.fake.ttls[f"auth:refresh:{claims['jti']}"] == settings.refresh_token_ttl_days * 86400


def test_token_types_are_not_interchangeable(store) -> None:
    with pytest.raises(HTTPException) as exc:
        resolve_authenticated_user_id(create_refresh_token("user_1"))
    assert exc.value.status_code == 401

    client = TestClient(app)
    response = client.post("/v1/auth/refresh", json={"refresh_token": create_access_token("user_1")})
    assert response.status_code == 401


def test_logout_revokes_access_token(client, store) -> None:
    access = create_access_token("user_1")
    assert resolve_authenticated_user_id(access) == "user_1"

    response = client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {access}"})

    assert response.status_code == 204
    assert f"auth:revoked:{_claims(access)['jti']}" in store.fake.strings
    with pytest.raises(HTTPException) as exc:
        resolve_authenticated_user_id(access)
    assert exc.value.status_code == 401


def test_logout_with_refresh_token_blocks_later_refresh(client, store) -> None:
    access = create_access_token("user_1")
    refresh = create_refresh_token("user_1")

    response = client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": refresh},
    )

    assert response.status_code == 204
    assert client.post("/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_logout_without_valid_token_is_rejected(client) -> None:
    assert client.post("/v1/auth/logout").status_code == 401
    assert client.post("/v1/auth/logout", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_rotates_tokens(client, store) -> None:
    old_refresh = create_refresh_token("user_1")

    response = client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user_1"
    assert resolve_authenticated_user_id(body["access_token"]) == "user_1"
    assert body["refresh_token"] != old_refresh
    assert _claims(body["refresh_token"])["type"] == "refresh"

    # The new refresh token works exactly once more.
    assert client.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 200


def test_reusing_rotated_refresh_token_is_rejected(client, store) -> None:
    old_refresh = create_refresh_token("user_1")
    assert client.post("/v1/auth/refresh", json={"refresh_token": old_refresh}).status_code == 200

    response = client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})

    assert response.status_code == 401


def test_unregistered_refresh_token_is_rejected(client, store) -> None:
    forged_but_signed = create_refresh_token("user_1")
    store.fake.hashes.clear()

    assert client.post("/v1/auth/refresh", json={"refresh_token": forged_but_signed}).status_code == 401


def test_validation_fails_closed_when_redis_is_unavailable(store) -> None:
    access = create_access_token("user_1")

    with patch.object(store, "is_revoked", side_effect=TokenStoreUnavailable):
        with pytest.raises(HTTPException) as exc:
            resolve_authenticated_user_id(access)

    assert exc.value.status_code == 401


def test_refresh_fails_closed_when_redis_is_unavailable(client, store) -> None:
    refresh = create_refresh_token("user_1")

    with patch.object(store, "consume_refresh", side_effect=TokenStoreUnavailable):
        response = client.post("/v1/auth/refresh", json={"refresh_token": refresh})

    assert response.status_code == 401


def test_token_store_consume_refresh_is_single_use(store) -> None:
    store.store_refresh("abc", "user_1", 60)

    assert store.consume_refresh("abc") == (RefreshState.OK, "user_1")
    assert store.consume_refresh("abc") == (RefreshState.REUSED, "user_1")
    assert store.consume_refresh("missing") == (RefreshState.UNKNOWN, None)


def test_token_store_revoke_sets_ttl_and_is_revoked(store) -> None:
    assert store.is_revoked("jti1") is False

    store.revoke("jti1", 120)

    assert store.is_revoked("jti1") is True
    assert store.fake.ttls["auth:revoked:jti1"] == 120
