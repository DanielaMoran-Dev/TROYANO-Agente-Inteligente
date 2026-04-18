"""
Clinic router — registro, consulta y edición de clínicas.
Relación 1:N (una clínica, varios doctores).
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pymongo import ReturnDocument

import re

from schemas.clinic import (
    ClinicDoctorInfo,
    ClinicDoctorLink,
    ClinicFromPlace,
    ClinicPublic,
    ClinicRegister,
    ClinicSearchResult,
    ClinicUpdate,
)
from services import mongo_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clinics", tags=["clinics"])


def _doctor_ids_from_doc(doc: dict) -> list[ObjectId]:
    """Normaliza: acepta `doctor_ids` (nuevo) o `doctor_id` (legacy)."""
    ids = doc.get("doctor_ids")
    if ids is None:
        legacy = doc.get("doctor_id")
        return [legacy] if legacy else []
    return [oid for oid in ids if oid]


def _to_public(doc: dict) -> ClinicPublic:
    doctor_ids = [str(oid) for oid in _doctor_ids_from_doc(doc)]
    return ClinicPublic(
        clinic_id=str(doc["_id"]),
        name=doc.get("name", ""),
        phone=doc.get("phone"),
        address=doc.get("address", ""),
        lat=doc.get("lat"),
        lng=doc.get("lng"),
        specialty=doc.get("specialty", "medicina_general"),
        unit_type=doc.get("unit_type", "general"),
        insurances=doc.get("insurances") or [],
        price_level=doc.get("price_level", 2),
        services=doc.get("services") or [],
        state=doc.get("state"),
        municipality=doc.get("municipality"),
        doctor_ids=doctor_ids,
        maps_place_id=doc.get("maps_place_id"),
        formatted_address=doc.get("formatted_address"),
    )


def _parse_oid(value: str, field: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, Exception):
        raise HTTPException(400, f"{field} inválido")


async def _verify_doctors_exist(doctor_oids: list[ObjectId]) -> None:
    if not doctor_oids:
        return
    count = await mongo_service.doctors().count_documents(
        {"_id": {"$in": doctor_oids}}
    )
    if count != len(set(doctor_oids)):
        raise HTTPException(404, "Uno o más doctores no existen")


# ── Endpoints ────────────────────────────────────────────────────────────────────

@router.post("", response_model=ClinicPublic, status_code=201)
async def register_clinic(body: ClinicRegister):
    """Registra una clínica. Puede crearse sin doctores o con varios."""
    doctor_oids = [_parse_oid(d, "doctor_id") for d in body.doctor_ids]
    # dedupe
    doctor_oids = list({oid: None for oid in doctor_oids}.keys())

    await _verify_doctors_exist(doctor_oids)

    now = datetime.now(timezone.utc)
    doc = {
        "name": body.name,
        "phone": body.phone,
        "address": body.address,
        "lat": body.lat,
        "lng": body.lng,
        "specialty": body.specialty,
        "unit_type": body.unit_type,
        "insurances": body.insurances,
        "price_level": body.price_level,
        "services": body.services,
        "state": body.state,
        "municipality": body.municipality,
        "doctor_ids": doctor_oids,
        "maps_place_id": body.maps_place_id,
        "formatted_address": body.formatted_address,
        "embedding": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await mongo_service.clinics().insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(
        "Clinic registered: %s (doctors=%d)",
        result.inserted_id,
        len(doctor_oids),
    )
    return _to_public(doc)


@router.get("/mine", response_model=ClinicPublic | None)
async def get_my_clinic(doctor_id: str):
    """Devuelve la primera clínica vinculada al médico, o null si no tiene."""
    doc_oid = _parse_oid(doctor_id, "doctor_id")
    # Busca en array nuevo o en campo legacy
    doc = await mongo_service.clinics().find_one(
        {"$or": [{"doctor_ids": doc_oid}, {"doctor_id": doc_oid}]}
    )
    return _to_public(doc) if doc else None


@router.get("/by-doctor/{doctor_id}", response_model=list[ClinicPublic])
async def list_clinics_by_doctor(doctor_id: str):
    """Todas las clínicas donde trabaja el médico."""
    doc_oid = _parse_oid(doctor_id, "doctor_id")
    cursor = mongo_service.clinics().find(
        {"$or": [{"doctor_ids": doc_oid}, {"doctor_id": doc_oid}]}
    )
    return [_to_public(d) async for d in cursor]


@router.get("/search", response_model=list[ClinicSearchResult])
async def search_clinics(q: str = "", limit: int = 20):
    """
    Busca clínicas por nombre (regex case-insensitive). Si q está vacío devuelve
    las más recientes. Pensado para que un doctor elija dónde trabaja.
    """
    limit = max(1, min(limit, 50))
    query: dict = {}
    if q:
        # Escape regex specials, case-insensitive substring match
        query["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}

    projection = {
        "name": 1, "address": 1, "formatted_address": 1,
        "lat": 1, "lng": 1, "specialty": 1, "unit_type": 1,
        "doctor_ids": 1, "doctor_id": 1,
        "maps_place_id": 1, "clues_id": 1,
    }

    cursor = mongo_service.clinics().find(query, projection).limit(limit)
    docs = await cursor.to_list(length=limit)

    # Identify clinics with an active network doctor (to flag chat-ready ones)
    all_doc_ids: list[ObjectId] = []
    for d in docs:
        all_doc_ids.extend(_doctor_ids_from_doc(d))
    network_ids: set[ObjectId] = set()
    if all_doc_ids:
        async for d in mongo_service.doctors().find(
            {"_id": {"$in": all_doc_ids}, "is_active": True, "is_network": True},
            {"_id": 1},
        ):
            network_ids.add(d["_id"])

    out: list[ClinicSearchResult] = []
    for d in docs:
        doc_ids = _doctor_ids_from_doc(d)
        out.append(ClinicSearchResult(
            clinic_id=str(d["_id"]),
            name=d.get("name", ""),
            address=d.get("formatted_address") or d.get("address") or "",
            lat=d.get("lat"),
            lng=d.get("lng"),
            specialty=d.get("specialty"),
            unit_type=d.get("unit_type"),
            doctor_count=len(doc_ids),
            has_network_doctor=any(did in network_ids for did in doc_ids),
            maps_place_id=d.get("maps_place_id"),
            source="clues" if d.get("clues_id") else "db",
        ))
    return out


@router.get("/by-place/{maps_place_id}", response_model=ClinicPublic | None)
async def get_clinic_by_place(maps_place_id: str):
    """Devuelve la clínica asociada a un Google Place ID, o null si no existe."""
    doc = await mongo_service.clinics().find_one({"maps_place_id": maps_place_id})
    return _to_public(doc) if doc else None


@router.post("/from-place", response_model=ClinicPublic, status_code=200)
async def clinic_from_place(body: ClinicFromPlace):
    """
    Crea una clínica a partir de un Google Place (si no existe ya por place_id)
    y opcionalmente vincula a un doctor. Si ya existe, sólo vincula.
    Idempotente para el mismo place_id + doctor_id.
    """
    doctor_oid: ObjectId | None = None
    if body.doctor_id:
        doctor_oid = _parse_oid(body.doctor_id, "doctor_id")
        await _verify_doctors_exist([doctor_oid])

    now = datetime.now(timezone.utc)
    existing = await mongo_service.clinics().find_one({"maps_place_id": body.maps_place_id})

    if existing:
        if doctor_oid:
            await mongo_service.clinics().update_one(
                {"_id": existing["_id"]},
                {
                    "$addToSet": {"doctor_ids": doctor_oid},
                    "$set": {"updated_at": now},
                },
            )
            existing = await mongo_service.clinics().find_one({"_id": existing["_id"]})
        return _to_public(existing)

    doc = {
        "name": body.name,
        "phone": body.phone,
        "address": body.formatted_address,
        "formatted_address": body.formatted_address,
        "lat": body.lat,
        "lng": body.lng,
        "specialty": "medicina_general",
        "unit_type": "general",
        "insurances": [],
        "price_level": 2,
        "services": [],
        "state": body.state,
        "municipality": body.municipality,
        "doctor_ids": [doctor_oid] if doctor_oid else [],
        "maps_place_id": body.maps_place_id,
        "embedding": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await mongo_service.clinics().insert_one(doc)
    doc["_id"] = result.inserted_id
    logger.info(
        "Clinic from-place: %s (place=%s, doctors=%d)",
        result.inserted_id,
        body.maps_place_id,
        1 if doctor_oid else 0,
    )
    return _to_public(doc)


@router.get("/{clinic_id}", response_model=ClinicPublic)
async def get_clinic(clinic_id: str):
    """Obtiene una clínica por su ID."""
    doc = await mongo_service.clinics().find_one({"_id": _parse_oid(clinic_id, "clinic_id")})
    if not doc:
        raise HTTPException(404, "Clínica no encontrada")
    return _to_public(doc)


@router.get("/{clinic_id}/doctors", response_model=list[ClinicDoctorInfo])
async def list_clinic_doctors(clinic_id: str):
    """Lista los doctores vinculados a una clínica."""
    oid = _parse_oid(clinic_id, "clinic_id")
    clinic = await mongo_service.clinics().find_one({"_id": oid})
    if not clinic:
        raise HTTPException(404, "Clínica no encontrada")

    doctor_oids = _doctor_ids_from_doc(clinic)
    if not doctor_oids:
        return []

    cursor = mongo_service.doctors().find(
        {"_id": {"$in": doctor_oids}},
        {"_id": 1, "name": 1, "last_name": 1, "specialty": 1, "is_network": 1, "is_active": 1},
    )
    results: list[ClinicDoctorInfo] = []
    async for d in cursor:
        full_name = " ".join(filter(None, [d.get("name"), d.get("last_name")])).strip()
        results.append(ClinicDoctorInfo(
            doctor_id=str(d["_id"]),
            name=full_name or "(sin nombre)",
            specialty=d.get("specialty"),
            is_network=bool(d.get("is_network")),
            is_active=bool(d.get("is_active", True)),
        ))
    return results


@router.get("/{clinic_id}/doctors/network", response_model=list[ClinicDoctorInfo])
async def list_network_doctors(clinic_id: str):
    """Doctores en red activos vinculados a una clínica (para tarjeta del paciente)."""
    oid = _parse_oid(clinic_id, "clinic_id")
    clinic = await mongo_service.clinics().find_one({"_id": oid})
    if not clinic:
        raise HTTPException(404, "Clínica no encontrada")
    doctor_oids = _doctor_ids_from_doc(clinic)
    if not doctor_oids:
        return []
    cursor = mongo_service.doctors().find(
        {"_id": {"$in": doctor_oids}, "is_network": True, "is_active": True},
        {"_id": 1, "name": 1, "last_name": 1, "specialty": 1, "is_network": 1, "is_active": 1},
    )
    results: list[ClinicDoctorInfo] = []
    async for d in cursor:
        full_name = " ".join(filter(None, [d.get("name"), d.get("last_name")])).strip()
        results.append(ClinicDoctorInfo(
            doctor_id=str(d["_id"]),
            name=full_name or "(sin nombre)",
            specialty=d.get("specialty"),
            is_network=True,
            is_active=True,
        ))
    return results


@router.put("/{clinic_id}", response_model=ClinicPublic)
async def update_clinic(clinic_id: str, body: ClinicUpdate):
    """Actualiza los datos básicos de una clínica (no modifica vínculos con doctores)."""
    oid = _parse_oid(clinic_id, "clinic_id")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No hay campos para actualizar")
    updates["updated_at"] = datetime.now(timezone.utc)

    doc = await mongo_service.clinics().find_one_and_update(
        {"_id": oid},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(404, "Clínica no encontrada")
    return _to_public(doc)


@router.post("/{clinic_id}/doctors", response_model=ClinicPublic)
async def link_doctor(clinic_id: str, body: ClinicDoctorLink):
    """Vincula un doctor a la clínica."""
    oid = _parse_oid(clinic_id, "clinic_id")
    doc_oid = _parse_oid(body.doctor_id, "doctor_id")

    await _verify_doctors_exist([doc_oid])

    doc = await mongo_service.clinics().find_one_and_update(
        {"_id": oid},
        {
            "$addToSet": {"doctor_ids": doc_oid},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(404, "Clínica no encontrada")
    return _to_public(doc)


@router.delete("/{clinic_id}/doctors/{doctor_id}", response_model=ClinicPublic)
async def unlink_doctor(clinic_id: str, doctor_id: str):
    """Desvincula un doctor de la clínica."""
    oid = _parse_oid(clinic_id, "clinic_id")
    doc_oid = _parse_oid(doctor_id, "doctor_id")

    doc = await mongo_service.clinics().find_one_and_update(
        {"_id": oid},
        {
            "$pull": {"doctor_ids": doc_oid},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(404, "Clínica no encontrada")
    return _to_public(doc)


@router.delete("/{clinic_id}", status_code=204)
async def delete_clinic(clinic_id: str, doctor_id: str):
    """Elimina una clínica. Solo un doctor vinculado puede eliminarla."""
    oid = _parse_oid(clinic_id, "clinic_id")
    doc_oid = _parse_oid(doctor_id, "doctor_id")

    result = await mongo_service.clinics().delete_one({
        "_id": oid,
        "$or": [{"doctor_ids": doc_oid}, {"doctor_id": doc_oid}],
    })
    if result.deleted_count == 0:
        raise HTTPException(404, "Clínica no encontrada o no autorizado")
