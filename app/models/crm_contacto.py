from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.crm_catalogos import CrmCiudad, CrmOrigen, CrmRubro
from app.models.crm_empresa import CrmEmpresa


class CrmContacto(Base):
    __tablename__ = "crm_contacto"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), default=None)
    telefono: Mapped[str | None] = mapped_column(String(50), default=None)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("crm_empresa.id"), default=None)
    rubro_id: Mapped[int | None] = mapped_column(ForeignKey("crm_rubro.id"), default=None)
    ciudad_id: Mapped[int | None] = mapped_column(ForeignKey("crm_ciudad.id"), default=None)
    origen_id: Mapped[int | None] = mapped_column(ForeignKey("crm_origen.id"), default=None)
    erp_cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.idcliente"), default=None)
    observaciones: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    empresa: Mapped[CrmEmpresa | None] = relationship(lazy="joined")
    rubro: Mapped[CrmRubro | None] = relationship(lazy="joined")
    ciudad: Mapped[CrmCiudad | None] = relationship(lazy="joined")
    origen: Mapped[CrmOrigen | None] = relationship(lazy="joined")

    @property
    def empresa_nombre(self) -> str | None:
        return self.empresa.nombre if self.empresa else None

    @property
    def rubro_nombre(self) -> str | None:
        return self.rubro.nombre if self.rubro else None

    @property
    def ciudad_nombre(self) -> str | None:
        return self.ciudad.nombre if self.ciudad else None

    @property
    def origen_nombre(self) -> str | None:
        return self.origen.nombre if self.origen else None
