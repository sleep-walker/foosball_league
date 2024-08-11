from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from league_app.database import Base
from uuid import UUID, uuid4


class Player(Base):
    __tablename__ = "players"

    uuid: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    nickname: Mapped[str] = mapped_column(unique=True)
    first_name: Mapped[str] = mapped_column()
    last_name: Mapped[str] = mapped_column()
    email: Mapped[str] = mapped_column()

    deleted: Mapped[bool] = mapped_column(default=False)
