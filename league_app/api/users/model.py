from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from league_app.database import Base
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class User(SQLAlchemyBaseUserTableUUID, Base):
    username: Mapped[str] = mapped_column(unique=True, nullable=False)


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    pass
