from uuid import UUID

from fastapi import APIRouter

from app.deps import SessionDep, StaffDep
from app.http import dump
from app.modules.catalogue import service
from app.modules.catalogue.schemas import (
    ActivePatch,
    DoctorBody,
    HospitalBody,
    PackageBody,
    ProcedureBody,
    TariffBody,
)

router = APIRouter(tags=["catalogue"])


@router.get("/v1/staff/hospitals")
async def hospitals(actor: StaffDep, session: SessionDep):
    return dump(await service.list_hospitals(session, actor))


@router.post("/v1/staff/hospitals", status_code=201)
async def add_hospital(body: HospitalBody, actor: StaffDep, session: SessionDep):
    return dump(await service.create_hospital(session, actor, body))


@router.patch("/v1/staff/hospitals/{hospital_id}")
async def hospital_active(hospital_id: UUID, body: ActivePatch, actor: StaffDep, session: SessionDep):
    return dump(await service.patch_hospital_active(session, actor, hospital_id, body.active))


@router.get("/v1/staff/doctors")
async def doctors(actor: StaffDep, session: SessionDep):
    return dump(await service.list_doctors(session, actor))


@router.post("/v1/staff/doctors", status_code=201)
async def add_doctor(body: DoctorBody, actor: StaffDep, session: SessionDep):
    return dump(await service.create_doctor(session, actor, body))


@router.get("/v1/staff/procedures")
async def procedures(actor: StaffDep, session: SessionDep):
    return dump(await service.list_procedures(session, actor))


@router.post("/v1/staff/procedures", status_code=201)
async def add_procedure(body: ProcedureBody, actor: StaffDep, session: SessionDep):
    return dump(await service.create_procedure(session, actor, body))


@router.get("/v1/staff/packages")
async def packages(actor: StaffDep, session: SessionDep):
    return dump(await service.list_packages(session, actor))


@router.post("/v1/staff/packages", status_code=201)
async def add_package(body: PackageBody, actor: StaffDep, session: SessionDep):
    return dump(await service.create_package(session, actor, body))


@router.get("/v1/staff/tariffs")
async def tariffs(actor: StaffDep, session: SessionDep):
    return dump(await service.list_tariffs(session, actor))


@router.post("/v1/staff/tariffs", status_code=201)
async def add_tariff(body: TariffBody, actor: StaffDep, session: SessionDep):
    return dump(await service.create_tariff(session, actor, body))


@router.put("/v1/staff/tariffs/{tariff_id}")
async def replace_tariff(tariff_id: UUID, body: TariffBody, actor: StaffDep, session: SessionDep):
    return dump(await service.replace_tariff(session, actor, tariff_id, body))
