from fastapi import APIRouter, Body, Request, Response, HTTPException, status
from fastapi.encoders import jsonable_encoder
from typing import List

from models.export_models import Applicant

router = APIRouter()

@router.post("/", response_description="Create a new applicant", status_code=status.HTTP_201_CREATED, response_model=Applicant)
def create_applicant(request: Request, applicant: Applicant = Body(...)):
    applicant = jsonable_encoder(applicant)
    new_applicant = request.app.database["applicants"].insert_one(applicant)
    created_applicant = request.app.database["applicants"].find_one(
        {"_id": new_applicant.inserted_id}
    )
    return created_applicant


@router.get("/", response_description="List all applicants", response_model=List[Applicant])
def list_applicants(request: Request):
    applicants = list(request.app.database["applicant"].find(limit=100))
    return applicants


@router.get("/{id}", response_description="Get a single applicant by id", response_model=Applicant)
def find_applicant(id: str, request: Request):
    if (applicant := request.app.database["applicants"].find_one({"_id": id})) is not None:
        return applicant
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Applicant with ID {id} not found")


@router.delete("/{id}", response_description="Delete an applicant")
def delete_applicant(id: str, request: Request, response: Response):
    delete_result = request.app.database["applicants"].delete_one({"_id": id})

    if delete_result.deleted_count == 1:
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Applicant with ID {id} not found")
