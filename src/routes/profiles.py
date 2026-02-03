from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status, Form
from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from config.dependencies import get_jwt_auth_manager, get_s3_storage_client
from database.models.accounts import UserModel, UserGroupEnum, UserProfileModel, GenderEnum
from exceptions.security import TokenExpiredError, InvalidTokenError, BaseSecurityError
from exceptions.storage import S3FileUploadError
from schemas.profiles import ProfileResponse, ProfileCreate
from security.http import get_token
from security.interfaces import JWTAuthManagerInterface
from database import get_db
from storages.interfaces import S3StorageInterface

router = APIRouter()


async def get_user(
        token: Annotated[str, Depends(get_token)],
        jwt_manager: Annotated[
            JWTAuthManagerInterface, Depends(get_jwt_auth_manager)
        ],
        db: Annotated[AsyncSession, Depends(get_db)],
) -> UserModel:
    try:
        payload = jwt_manager.decode_access_token(token)
        token_user_id = payload.get("user_id")
    except BaseSecurityError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    user = await db.get(UserModel, token_user_id, options=[joinedload(UserModel.group)])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    return user


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponse,
    summary="Create user profile",
    status_code=status.HTTP_201_CREATED
)
async def create_profile(
        user_id: int,
        profile_data: Annotated[ProfileCreate, Form()],
        db: Annotated[AsyncSession, Depends(get_db)],
        token: str = Depends(get_token),
        jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
        s3_client: S3StorageInterface = Depends(get_s3_storage_client),
) -> ProfileResponse:

    authorized_user = await get_user(token, jwt_manager, db)

    if user_id != authorized_user.id and not authorized_user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile."
        )

    if user_id == authorized_user.id:
        user = authorized_user
    else:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await db.execute(stmt)
        user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    stmt_profile = select(UserProfileModel).where(
        UserProfileModel.user_id == user.id
    )
    existing_profile = await db.scalar(stmt_profile)
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile."
        )
    content = await profile_data.avatar.read()
    avatar_key = f"avatars/{user.id}_{profile_data.avatar.filename}"
    try:
        await s3_client.upload_file(
            file_name=avatar_key,
            file_data=content
        )
    except S3FileUploadError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )
    new_profile = UserProfileModel(
        user_id=cast(int, user.id),
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=cast(GenderEnum, profile_data.gender),
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_key
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)
    avatar_url = await s3_client.get_file_url(new_profile.avatar)
    return ProfileResponse(
        id=cast(int, new_profile.id),
        user_id=new_profile.user_id,
        first_name=new_profile.first_name,
        last_name=new_profile.last_name,
        gender=new_profile.gender,
        date_of_birth=new_profile.date_of_birth,
        info=new_profile.info,
        avatar=cast(HttpUrl, avatar_url)
    )
