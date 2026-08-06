from typing import Annotated

from fastapi import Header, HTTPException, status


def get_current_user_id(x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None) -> str:
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id header")
    return x_user_id
