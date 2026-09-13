from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.routing import HospitalList, HospitalPublic
from app.services import doctor_routing

router = APIRouter()


@router.get("", response_model=HospitalList)
def hospitals(db: Session = Depends(get_db)):
    return HospitalList(items=[HospitalPublic.model_validate(item) for item in doctor_routing.list_active_hospitals(db)])
