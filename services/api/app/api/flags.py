import re
import time
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.api.app.infra.db import get_db
from shared.db.models import LanguageFlag
from shared.logging_utils import get_logger

router = APIRouter(prefix="/v1/flags", tags=["flags"])
logger = get_logger("prism.api.flags")

FLAG_SOURCE_URL = "https://flagcdn.com/w40/{country}.png"
MAX_FLAG_BYTES = 200_000
FETCH_RETRY_AFTER_SECONDS = 300

# A language has no single country; this picks the flag conventionally shown for it.
LANGUAGE_COUNTRY = {
    "ar": "sa", "bg": "bg", "cs": "cz", "da": "dk", "de": "de", "el": "gr", "en": "gb", "es": "es",
    "et": "ee", "fi": "fi", "fr": "fr", "he": "il", "hi": "in", "hr": "hr", "hu": "hu", "id": "id",
    "it": "it", "ja": "jp", "ko": "kr", "lt": "lt", "lv": "lv", "ms": "my", "nb": "no", "nl": "nl",
    "no": "no", "pl": "pl", "pt": "pt", "ro": "ro", "ru": "ru", "sk": "sk", "sl": "si", "sr": "rs",
    "sv": "se", "th": "th", "tr": "tr", "uk": "ua", "vi": "vn", "zh": "cn",
}

_LANG_PATTERN = re.compile(r"^[a-z]{2,3}(-[a-z]{2})?$")
_recent_failures: dict[str, float] = {}


def _country_for(lang: str) -> str | None:
    if "-" in lang:
        return lang.split("-", 1)[1]
    return LANGUAGE_COUNTRY.get(lang)


def _download_flag(country: str) -> tuple[bytes, str] | None:
    # Host is fixed and `country` comes from our map or a validated 2-letter region.
    request = urllib.request.Request(FLAG_SOURCE_URL.format(country=country), headers={"User-Agent": "prism"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read(MAX_FLAG_BYTES + 1)
    except Exception:
        logger.warning("flag_download_failed", extra={"country": country})
        return None
    if not content_type.startswith("image/") or not data or len(data) > MAX_FLAG_BYTES:
        return None
    return data, content_type


@router.get("/{lang}")
def get_flag(lang: str, db: Session = Depends(get_db)) -> Response:
    lang = lang.lower()
    if not _LANG_PATTERN.match(lang):
        raise HTTPException(status_code=404, detail="Flag not available")

    flag = db.get(LanguageFlag, lang)
    if flag is None:
        country = _country_for(lang)
        failed_at = _recent_failures.get(lang)
        if country is None or (failed_at and time.monotonic() - failed_at < FETCH_RETRY_AFTER_SECONDS):
            raise HTTPException(status_code=404, detail="Flag not available")

        downloaded = _download_flag(country)
        if downloaded is None:
            _recent_failures[lang] = time.monotonic()
            raise HTTPException(status_code=404, detail="Flag not available")

        image, content_type = downloaded
        flag = LanguageFlag(
            lang=lang,
            country_code=country,
            content_type=content_type,
            image=image,
            fetched_at=datetime.now(timezone.utc),
        )
        db.add(flag)
        try:
            db.commit()
        except IntegrityError:
            # Another request stored the same flag first.
            db.rollback()
            flag = db.get(LanguageFlag, lang)
            if flag is None:
                raise HTTPException(status_code=404, detail="Flag not available")

    return Response(
        content=flag.image,
        media_type=flag.content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
