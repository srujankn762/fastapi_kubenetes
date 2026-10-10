from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate
from fastapi import HTTPException

# Similar to Django's URL routing for a group of endpoints
router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
):
    # Convert validated request data into SQLAlchemy model
    customer = Customer(**payload.model_dump())

    # Add customer to the database session
    db.add(customer)

    # Commit INSERT transaction to MySQL
    db.commit()

    # Refresh object to retrieve generated ID
    db.refresh(customer)

    return {
        "id": customer.id,
        "name": customer.name,
        "age": customer.age,
        "gender": customer.gender,
    }

from sqlalchemy import select
from app.schemas.customer import CustomerResponse


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    db: Session = Depends(get_db),
):
    # SELECT * FROM customers
    statement = select(Customer)

    # Execute query and get Customer objects
    customers = db.scalars(statement).all()

    return customers



@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
):
    # Find customer using primary key
    customer = db.get(Customer, customer_id)

    # Return 404 if customer doesn't exist
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    return customer

from app.schemas.customer import CustomerUpdate


@router.patch("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
):
    # Find existing customer
    customer = db.get(Customer, customer_id)

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    # Extract only fields provided in the request
    update_data = payload.model_dump(exclude_unset=True)

    # Update provided fields
    for field, value in update_data.items():
        if value is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field} cannot be null",
            )

        setattr(customer, field, value)

    # Save changes to MySQL
    db.commit()

    # Fetch updated values
    db.refresh(customer)

    return customer

from fastapi import HTTPException, status


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
):
    # Find customer using primary key
    customer = db.get(Customer, customer_id)

    # Customer doesn't exist
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    # Mark customer for deletion
    db.delete(customer)

    # Commit DELETE operation to MySQL
    db.commit()