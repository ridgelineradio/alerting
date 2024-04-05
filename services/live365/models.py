from typing import Any, Literal

from pydantic import BaseModel


class Live365StationAttributes(BaseModel):
    twitter_url: Any
    mount_password: str
    ls_hostname: str
    source: str
    status: str
    logo_extension: str
    timezone: str
    mount_username: str
    website: str
    name: str
    description: str
    on_air: bool
    slug: str
    cover_uuid: str
    in_beta_program: bool
    is_being_migrated: bool
    genres: list[int]
    organization_id: str
    ftp_password: str
    ingest_hostname: str
    media_service_uuid: str
    logo_file_size_bytes: int
    cover_file_size_bytes: int
    facebook_url: Any
    cover_extension: str
    logo_uuid: str
    ftp_username: str
    mount_id: str
    instagram_url: Any


class Live365Station(BaseModel):
    id: str
    links: Any
    type: Literal["stations"]
    attributes: Live365StationAttributes


class Live365Stations(BaseModel):
    data: list[Live365Station]
    jsonapi: Any
    links: Any
    meta: Any
