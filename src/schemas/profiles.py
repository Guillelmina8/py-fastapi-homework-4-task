from datetime import date

from fastapi import UploadFile, Form, File, HTTPException
from pydantic import BaseModel, field_validator, HttpUrl, Field
from pydantic_core import PydanticCustomError

from validation import (
    validate_name,
    validate_image,
    validate_gender,
    validate_birth_date,
    validate_info
)

from database.models.accounts import GenderEnum


class ProfileCreate(BaseModel):
    first_name: str
    last_name: str
    gender: GenderEnum
    date_of_birth: date
    info: str
    avatar: UploadFile

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str):
        validate_name(value)
        return value.lower()

    @field_validator("gender", mode="before")
    @classmethod
    def validate_gender(cls, value: str):
        validate_gender(value)
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date):
        validate_birth_date(value)
        return value

    @field_validator("info")
    @classmethod
    def validate_info(cls, value: str):
        validate_info(value)
        return value

    @field_validator("avatar")
    @classmethod
    def validate_avatar(cls, value: UploadFile) -> UploadFile:
        if not hasattr(value, "file"):
            return value

        validate_image(value)
        return value


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    first_name: str
    last_name: str
    gender: str
    date_of_birth: date
    info: str
    avatar: HttpUrl
