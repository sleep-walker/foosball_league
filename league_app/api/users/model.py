from enum import Enum

from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from league_app.database import Base
from sqlalchemy.orm import Mapped


class Role(Enum):
    user = "user"
    tournament_organizer = "tournament_organizer"
    league_organizer = "league_organizer"
    admin = "admin"


from sqlalchemy.orm import mapped_column

class User(SQLAlchemyBaseUserTableUUID, Base):
    role: Mapped[Role] = mapped_column(default=Role.user)


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    pass
