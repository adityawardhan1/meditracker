from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import jwt
from passlib.context import CryptContext
# Email functionality can be added later
# import smtplib
# from email.mime.text import MimeText  
# from email.mime.multipart import MimeMultipart
import pandas as pd
from io import BytesIO
import base64

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "pharma_secret_key_2024"  # In production, use environment variable
ALGORITHM = "HS256"

# Order Stages
ORDER_STAGES = [
    "Order Received",
    "Raw Material Ordered", 
    "Raw Material Received",
    "Batch in Production",
    "Packaging",
    "Ready for Delivery",
    "Delivered & Payment Received"
]

# User Roles
USER_ROLES = ["Admin", "Manager", "Employee"]

# Pydantic Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    email: str
    full_name: str
    role: str  # Admin, Manager, Employee
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: str
    role: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: User

class Customer(BaseModel):
    name: str
    email: str
    phone: str
    address: str
    company: str

class Product(BaseModel):
    name: str
    description: str
    quantity: int
    unit: str
    batch_size: str

class OrderActivity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    action: str
    stage_from: Optional[str] = None
    stage_to: Optional[str] = None
    comment: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_number: str
    customer: Customer
    product: Product
    current_stage: str = "Order Received"
    assigned_employees: List[str] = []
    deadline: Optional[datetime] = None
    priority: str = "Medium"  # High, Medium, Low
    activities: List[OrderActivity] = []
    internal_comments: List[Dict[str, Any]] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCreate(BaseModel):
    customer: Customer
    product: Product
    assigned_employees: List[str] = []
    deadline: Optional[datetime] = None
    priority: str = "Medium"

class OrderUpdate(BaseModel):
    stage: str
    comment: Optional[str] = None

class Comment(BaseModel):
    user_id: str
    user_name: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Helper Functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    # Truncate password to 72 bytes for bcrypt compatibility
    if len(password.encode('utf-8')) > 72:
        password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        
        user = await db.users.find_one({"id": user_id})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return User(**user)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

def prepare_for_mongo(data):
    """Convert datetime objects to ISO strings for MongoDB storage"""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, list):
                data[key] = [prepare_for_mongo(item) if isinstance(item, dict) else item for item in value]
            elif isinstance(value, dict):
                data[key] = prepare_for_mongo(value)
    return data

def parse_from_mongo(item):
    """Convert ISO strings back to datetime objects from MongoDB"""
    if isinstance(item, dict):
        for key, value in item.items():
            if key.endswith('_at') or key == 'deadline' or key == 'timestamp':
                if isinstance(value, str):
                    try:
                        item[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except:
                        pass
            elif isinstance(value, list):
                item[key] = [parse_from_mongo(subitem) if isinstance(subitem, dict) else subitem for subitem in value]
            elif isinstance(value, dict):
                item[key] = parse_from_mongo(value)
    return item

# Auth Routes
@api_router.post("/auth/signup", response_model=User)
async def signup(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"$or": [{"username": user_data.username}, {"email": user_data.email}]})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username or email already registered")
    
    # Hash password
    hashed_password = get_password_hash(user_data.password)
    
    # Create user
    user_dict = user_data.dict()
    user_dict.pop("password")
    user = User(**user_dict)
    
    user_doc = prepare_for_mongo(user.dict())
    user_doc["hashed_password"] = hashed_password
    
    await db.users.insert_one(user_doc)
    return user

@api_router.post("/auth/login", response_model=Token)
async def login(user_credentials: UserLogin):
    user = await db.users.find_one({"username": user_credentials.username})
    if not user or not verify_password(user_credentials.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    user = parse_from_mongo(user)
    access_token = create_access_token(data={"sub": user["id"]})
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=User(**user)
    )

@api_router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# Order Routes
@api_router.post("/orders", response_model=Order)
async def create_order(order_data: OrderCreate, current_user: User = Depends(get_current_user)):
    if current_user.role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Not authorized to create orders")
    
    # Generate order number
    order_count = await db.orders.count_documents({}) + 1
    order_number = f"PH{order_count:05d}"
    
    order_dict = order_data.dict()
    order_dict["order_number"] = order_number
    order = Order(**order_dict)
    
    # Add creation activity
    activity = OrderActivity(
        user_id=current_user.id,
        user_name=current_user.full_name,
        action="Order Created",
        stage_to="Order Received"
    )
    order.activities.append(activity)
    
    order_doc = prepare_for_mongo(order.dict())
    await db.orders.insert_one(order_doc)
    return order

@api_router.get("/orders", response_model=List[Order])
async def get_orders(current_user: User = Depends(get_current_user)):
    orders = await db.orders.find().to_list(1000)
    parsed_orders = [parse_from_mongo(order) for order in orders]
    return [Order(**order) for order in parsed_orders]

@api_router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str, current_user: User = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = parse_from_mongo(order)
    return Order(**order)

@api_router.put("/orders/{order_id}/stage")
async def update_order_stage(order_id: str, update_data: OrderUpdate, current_user: User = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check permissions
    if current_user.role == "Employee" and current_user.id not in order.get("assigned_employees", []):
        raise HTTPException(status_code=403, detail="Not assigned to this order")
    
    if update_data.stage not in ORDER_STAGES:
        raise HTTPException(status_code=400, detail="Invalid stage")
    
    # Create activity
    activity = OrderActivity(
        user_id=current_user.id,
        user_name=current_user.full_name,
        action="Stage Updated",
        stage_from=order["current_stage"],
        stage_to=update_data.stage,
        comment=update_data.comment
    )
    
    # Update order
    update_doc = {
        "current_stage": update_data.stage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "$push": {"activities": prepare_for_mongo(activity.dict())}
    }
    
    await db.orders.update_one({"id": order_id}, {"$set": update_doc})
    
    return {"message": "Stage updated successfully"}

@api_router.post("/orders/{order_id}/comments")
async def add_comment(order_id: str, content: str, current_user: User = Depends(get_current_user)):
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    comment = Comment(
        user_id=current_user.id,
        user_name=current_user.full_name,
        content=content
    )
    
    await db.orders.update_one(
        {"id": order_id},
        {"$push": {"internal_comments": prepare_for_mongo(comment.dict())}}
    )
    
    return {"message": "Comment added successfully"}

# Dashboard Routes
@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    total_orders = await db.orders.count_documents({})
    orders_in_progress = await db.orders.count_documents({"current_stage": {"$nin": ["Delivered & Payment Received"]}})
    completed_orders = await db.orders.count_documents({"current_stage": "Delivered & Payment Received"})
    
    # Orders by stage
    stage_counts = {}
    for stage in ORDER_STAGES:
        count = await db.orders.count_documents({"current_stage": stage})
        stage_counts[stage] = count
    
    # Recent activities
    recent_orders = await db.orders.find().sort("updated_at", -1).limit(10).to_list(10)
    recent_activities = []
    
    for order in recent_orders:
        if order.get("activities"):
            latest_activity = order["activities"][-1]
            latest_activity["order_number"] = order["order_number"]
            recent_activities.append(latest_activity)
    
    return {
        "total_orders": total_orders,
        "orders_in_progress": orders_in_progress,
        "completed_orders": completed_orders,
        "stage_counts": stage_counts,
        "recent_activities": recent_activities[:5]
    }

# User Management Routes
@api_router.get("/users", response_model=List[User])
async def get_users(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    users = await db.users.find({}, {"hashed_password": 0}).to_list(1000)
    parsed_users = [parse_from_mongo(user) for user in users]
    return [User(**user) for user in parsed_users]

# Export Routes
@api_router.get("/export/orders")
async def export_orders(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    orders = await db.orders.find().to_list(1000)
    
    # Prepare data for export
    export_data = []
    for order in orders:
        export_data.append({
            "Order Number": order["order_number"],
            "Customer": order["customer"]["name"],
            "Product": order["product"]["name"],
            "Quantity": order["product"]["quantity"],
            "Current Stage": order["current_stage"],
            "Priority": order["priority"],
            "Created At": order["created_at"],
            "Updated At": order["updated_at"]
        })
    
    # Create Excel file
    df = pd.DataFrame(export_data)
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Orders')
    
    excel_data = base64.b64encode(excel_buffer.getvalue()).decode()
    
    return {
        "filename": f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        "data": excel_data
    }

# Demo Data Routes
@api_router.post("/demo/create-sample-data")
async def create_sample_data(current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Create sample users
    sample_users = [
        {"username": "manager1", "email": "manager@pharma.com", "full_name": "John Manager", "role": "Manager", "password": "manager123"},
        {"username": "employee1", "email": "employee1@pharma.com", "full_name": "Alice Employee", "role": "Employee", "password": "employee123"},
        {"username": "employee2", "email": "employee2@pharma.com", "full_name": "Bob Employee", "role": "Employee", "password": "employee123"}
    ]
    
    created_user_ids = []
    for user_data in sample_users:
        existing = await db.users.find_one({"username": user_data["username"]})
        if not existing:
            password = user_data.pop("password")
            user = User(**user_data)
            user_doc = prepare_for_mongo(user.dict())
            user_doc["hashed_password"] = get_password_hash(password)
            await db.users.insert_one(user_doc)
            created_user_ids.append(user.id)
    
    # Create sample orders
    sample_orders = [
        {
            "customer": {"name": "MedCorp Pharmaceuticals", "email": "orders@medcorp.com", "phone": "+1-555-0123", "address": "123 Medical Plaza, NY", "company": "MedCorp"},
            "product": {"name": "Amoxicillin 500mg", "description": "Antibiotic capsules", "quantity": 10000, "unit": "capsules", "batch_size": "1000 units"},
            "current_stage": "Batch in Production",
            "priority": "High"
        },
        {
            "customer": {"name": "HealthFirst Pharmacy", "email": "supply@healthfirst.com", "phone": "+1-555-0456", "address": "456 Health St, CA", "company": "HealthFirst"},
            "product": {"name": "Ibuprofen 200mg", "description": "Pain relief tablets", "quantity": 5000, "unit": "tablets", "batch_size": "500 units"},
            "current_stage": "Raw Material Received",
            "priority": "Medium"
        },
        {
            "customer": {"name": "CityMed Hospital", "email": "pharmacy@citymed.com", "phone": "+1-555-0789", "address": "789 City Center, TX", "company": "CityMed"},
            "product": {"name": "Aspirin 81mg", "description": "Low-dose aspirin", "quantity": 20000, "unit": "tablets", "batch_size": "2000 units"},
            "current_stage": "Order Received",
            "priority": "Low"
        }
    ]
    
    for i, order_data in enumerate(sample_orders):
        order_count = await db.orders.count_documents({}) + 1
        order_data["order_number"] = f"PH{order_count:05d}"
        order_data["assigned_employees"] = created_user_ids[:2] if created_user_ids else []
        
        order = Order(**order_data)
        
        # Add sample activities
        activity = OrderActivity(
            user_id=current_user.id,
            user_name=current_user.full_name,
            action="Order Created (Demo Data)",
            stage_to=order.current_stage
        )
        order.activities.append(activity)
        
        order_doc = prepare_for_mongo(order.dict())
        await db.orders.insert_one(order_doc)
    
    return {"message": "Sample data created successfully"}

@api_router.delete("/demo/clear-sample-data")
async def clear_sample_data(current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Delete sample users (except current user)
    await db.users.delete_many({"username": {"$in": ["manager1", "employee1", "employee2"]}})
    
    # Delete all orders (in a real app, you might want to be more selective)
    await db.orders.delete_many({})
    
    return {"message": "Sample data cleared successfully"}

# Search Routes
@api_router.get("/search/orders")
async def search_orders(
    query: Optional[str] = None,
    stage: Optional[str] = None,
    priority: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    filter_criteria = {}
    
    if query:
        filter_criteria["$or"] = [
            {"order_number": {"$regex": query, "$options": "i"}},
            {"customer.name": {"$regex": query, "$options": "i"}},
            {"product.name": {"$regex": query, "$options": "i"}}
        ]
    
    if stage:
        filter_criteria["current_stage"] = stage
        
    if priority:
        filter_criteria["priority"] = priority
    
    orders = await db.orders.find(filter_criteria).to_list(1000)
    parsed_orders = [parse_from_mongo(order) for order in orders]
    return [Order(**order) for order in parsed_orders]

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()