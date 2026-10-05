"""Values the catalogue knows about. Shared by the parsers, the API schema and the seed script."""
from typing import Literal

BodyType = Literal["Hatchback", "Sedan", "SUV", "MUV"]
FuelType = Literal["Petrol", "Diesel", "CNG", "Electric", "Hybrid"]
Transmission = Literal["Manual", "Automatic"]
SortKey = Literal["price_asc", "price_desc", "km_asc", "year_desc", "safety_desc"]

MAKES = ["Maruti Suzuki", "Hyundai", "Tata", "Mahindra", "Kia", "Honda", "Toyota", "Skoda", "Volkswagen", "MG", "Renault"]
CITIES = ["Delhi", "Gurgaon", "Noida", "Mumbai", "Pune", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Jaipur"]
