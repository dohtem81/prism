from services.registration.app import main as main_module


def test_registration_cors_is_never_wildcard() -> None:
    for middleware in main_module.app.user_middleware:
        if middleware.cls.__name__ == "CORSMiddleware":
            assert "*" not in middleware.kwargs["allow_origins"]
            assert "*" not in middleware.kwargs["allow_headers"]
