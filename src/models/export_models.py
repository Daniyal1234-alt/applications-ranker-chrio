import uuid
from typing import List
from pydantic import BaseModel, Field

class Education(BaseModel):
    degree: str
    institute: str
    startYear: str
    endYear: str


class Experience(BaseModel):
    company: str
    role: str
    duration: str
    location: str
    type: str
    description: str


class Project(BaseModel):
    title: str
    tech: List[str]
    description: str
    githubURL: str


class Applicant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    imp_id: str
    name: str
    about: str
    skills: List
    matched_skills: List
    education: List[Education]
    experience: List[Experience]
    projects: List[Project]
    
