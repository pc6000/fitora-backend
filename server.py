from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, Header, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import json
from gym_exercises_database import GYM_EXERCISES_DATABASE, get_exercise_with_image

ROOT_DIR = Path(__file__).parent
FRONTEND_DIR = ROOT_DIR.parent / 'frontend'
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'test_database')]

# Google Play Billing Configuration
GOOGLE_PLAY_PACKAGE_NAME = os.environ.get('GOOGLE_PLAY_PACKAGE_NAME', 'com.fitora.training')

# Create the main app
app = FastAPI(title="Fitora Training API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class UserBase(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None

class UserProfile(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None  # male, female
    fitness_level: Optional[str] = None  # beginner, intermediate, advanced
    goal: Optional[str] = None  # weight_loss, muscle_gain, toning, general_fitness
    workout_mode: Optional[str] = "home"  # home (casa), gym (palestra)
    questionnaire_completed: bool = False
    questionnaire_score: Optional[int] = None
    calculated_level: Optional[str] = None
    subscription_plan: Optional[str] = None  # basic, pro, elite
    subscription_status: Optional[str] = None  # active, cancelled, expired
    subscription_expires: Optional[datetime] = None
    language: str = "it"  # it, en
    free_workouts_used: int = 0  # Track free workouts for paywall
    first_use_date: Optional[datetime] = None  # Track first app usage for paywall
    # Trial system
    trial_start_date: Optional[datetime] = None  # When trial started
    trial_expires_at: Optional[datetime] = None  # When trial expires (7 days after start)
    trial_used: bool = False  # Whether user has already used their trial
    # Daily progression system
    current_training_day: int = 1  # Current day in training program (1-based)
    last_training_date: Optional[datetime] = None  # Last date user completed a workout
    # Level progression system
    level_start_date: Optional[datetime] = None  # When user started current level
    level_up_available: bool = False  # Whether user can level up
    level_up_declined_at: Optional[datetime] = None  # When user declined level up (can ask again after 30 days)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OnboardingData(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    fitness_level: Optional[str] = None
    goal: Optional[str] = None
    workout_mode: Optional[str] = None  # home, gym

class QuestionnaireAnswer(BaseModel):
    question_id: int
    answer: int  # 1-5 scale

class QuestionnaireSubmission(BaseModel):
    answers: List[QuestionnaireAnswer]

class WorkoutProgress(BaseModel):
    user_id: str
    workout_id: str
    workout_name: str
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_minutes: int
    calories_burned: Optional[int] = None
    exercises_completed: int

class UserStats(BaseModel):
    user_id: str
    total_workouts: int = 0
    total_minutes: int = 0
    total_calories: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    last_workout_date: Optional[datetime] = None

class SubscriptionPlan(BaseModel):
    plan_id: str
    name: str
    price: float
    currency: str = "EUR"
    features: List[str]
    period: str = "month"

class PaymentCreate(BaseModel):
    plan_id: str

# ==================== TRIAL HELPER ====================

def get_trial_status(user: UserProfile) -> dict:
    """Calculate trial status for a user"""
    is_premium = user.subscription_status == "active"
    
    # If user is premium, no trial needed
    if is_premium:
        return {
            "has_trial": False,
            "trial_active": False,
            "trial_days_remaining": 0,
            "is_premium": True,
            "has_full_access": True
        }
    
    # Check trial status
    trial_expires = user.trial_expires_at
    trial_used = user.trial_used or False
    
    if trial_expires:
        if isinstance(trial_expires, str):
            trial_expires = datetime.fromisoformat(trial_expires)
        if trial_expires.tzinfo is None:
            trial_expires = trial_expires.replace(tzinfo=timezone.utc)
        
        now = datetime.now(timezone.utc)
        
        if now < trial_expires:
            # Trial is still active
            days_remaining = (trial_expires - now).days
            return {
                "has_trial": True,
                "trial_active": True,
                "trial_days_remaining": max(1, days_remaining),  # At least 1 day if active
                "trial_expires_at": trial_expires.isoformat(),
                "is_premium": False,
                "has_full_access": True  # Full access during trial
            }
        else:
            # Trial has expired
            return {
                "has_trial": True,
                "trial_active": False,
                "trial_days_remaining": 0,
                "trial_expired": True,
                "is_premium": False,
                "has_full_access": False
            }
    
    # No trial set (legacy user) - they don't have trial
    return {
        "has_trial": False,
        "trial_active": False,
        "trial_days_remaining": 0,
        "is_premium": False,
        "has_full_access": False
    }

# ==================== AUTH HELPERS ====================

async def get_current_user(request: Request) -> Optional[UserProfile]:
    """Get current authenticated user from session token"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    
    if not session_token:
        return None
    
    session = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session:
        return None
    
    # Check expiry
    expires_at = session.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return None
    
    user = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    
    if user:
        return UserProfile(**user)
    return None

async def require_auth(request: Request) -> UserProfile:
    """Require authentication - raises 401 if not authenticated"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

# ==================== DOWNLOAD ENDPOINT ====================

@api_router.get("/download/build")
async def download_build():
    """Download the latest build package"""
    file_path = Path("/app/backend/downloads/fitora-build-1.0.14.zip")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Build not found")
    return FileResponse(
        path=str(file_path),
        filename="fitora-build-1.0.14.zip",
        media_type="application/zip"
    )

# ==================== AUTH ENDPOINTS ====================

@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Exchange session_id for session_token"""
    try:
        body = await request.json()
        session_id = body.get("session_id")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")
        
        # Call Emergent Auth to get user data
        async with httpx.AsyncClient() as client:
            auth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            
            if auth_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session")
            
            user_data = auth_response.json()
        
        email = user_data.get("email")
        name = user_data.get("name")
        picture = user_data.get("picture")
        session_token = user_data.get("session_token")
        
        # Check if user exists
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user["user_id"]
            # Update user data
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "name": name,
                    "picture": picture,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
        else:
            # Create new user with 15-day free trial
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            trial_start = datetime.now(timezone.utc)
            trial_expires = trial_start + timedelta(days=15)  # 15 days free trial
            
            new_user = {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "questionnaire_completed": False,
                "language": "it",
                "free_workouts_used": 0,
                "first_use_date": datetime.now(timezone.utc),
                # Trial system - 10 days free for all new users
                "trial_start_date": trial_start,
                "trial_expires_at": trial_expires,
                "trial_used": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            await db.users.insert_one(new_user)
            
            # Create initial stats
            initial_stats = {
                "user_id": user_id,
                "total_workouts": 0,
                "total_minutes": 0,
                "total_calories": 0,
                "current_streak": 0,
                "longest_streak": 0,
                "last_workout_date": None
            }
            await db.user_stats.insert_one(initial_stats)
        
        # Store session
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc)
        })
        
        # Set cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            path="/",
            max_age=7 * 24 * 60 * 60
        )
        
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/auth/me")
async def get_me(request: Request):
    """Get current authenticated user"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user.dict()

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user and clear session"""
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out successfully"}

# ==================== EMAIL/PASSWORD AUTH ====================

import hashlib
import secrets

def hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with salt using SHA-256"""
    if salt is None:
        salt = secrets.token_hex(32)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return hashed.hex(), salt

def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify password against hash"""
    new_hash, _ = hash_password(password, salt)
    return new_hash == hashed

class EmailSignUpRequest(BaseModel):
    email: str
    password: str
    confirm_password: str
    name: Optional[str] = None

class EmailLoginRequest(BaseModel):
    email: str
    password: str

@api_router.post("/auth/signup")
async def email_signup(data: EmailSignUpRequest, response: Response):
    """Register a new user with email and password"""
    try:
        # Validate email format
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, data.email):
            raise HTTPException(status_code=400, detail="Formato email non valido")
        
        # Validate password length
        if len(data.password) < 8:
            raise HTTPException(status_code=400, detail="La password deve contenere almeno 8 caratteri")
        
        # Check passwords match
        if data.password != data.confirm_password:
            raise HTTPException(status_code=400, detail="Le password non corrispondono")
        
        # Check if user already exists
        existing_user = await db.users.find_one({"email": data.email.lower()})
        if existing_user:
            raise HTTPException(status_code=409, detail="Email già registrata")
        
        # Hash password
        password_hash, salt = hash_password(data.password)
        
        # Create new user with 15-day free trial
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        trial_start = datetime.now(timezone.utc)
        trial_expires = trial_start + timedelta(days=15)
        
        new_user = {
            "user_id": user_id,
            "email": data.email.lower(),
            "name": data.name or data.email.split('@')[0],
            "password_hash": password_hash,
            "password_salt": salt,
            "auth_provider": "email",
            "questionnaire_completed": False,
            "language": "it",
            "free_workouts_used": 0,
            "first_use_date": datetime.now(timezone.utc),
            "trial_start_date": trial_start,
            "trial_expires_at": trial_expires,
            "subscription_status": None,
            "subscription_plan": None,
            "subscription_expires": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.users.insert_one(new_user)
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=15)
        
        await db.user_sessions.insert_one({
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc)
        })
        
        # Set session cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=15 * 24 * 60 * 60  # 15 days
        )
        
        # Return user data (without password) - convert datetime to ISO strings, exclude ObjectId
        user_response = {}
        for k, v in new_user.items():
            if 'password' not in k and k != '_id':
                if isinstance(v, datetime):
                    user_response[k] = v.isoformat()
                else:
                    user_response[k] = v
        user_response["session_token"] = session_token
        
        logger.info(f"New user registered: {data.email}")
        
        return {
            "success": True,
            "message": "Registrazione completata",
            "user": user_response,
            "session_token": session_token
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la registrazione")

@api_router.post("/auth/login")
async def email_login(data: EmailLoginRequest, response: Response):
    """Login with email and password"""
    try:
        # Find user by email
        user = await db.users.find_one({"email": data.email.lower()})
        
        if not user:
            raise HTTPException(status_code=401, detail="Email o password non corretti")
        
        # Check if user has password auth
        if not user.get("password_hash"):
            raise HTTPException(
                status_code=401, 
                detail="Questo account usa Google Login. Accedi con Google."
            )
        
        # Verify password
        if not verify_password(data.password, user["password_hash"], user["password_salt"]):
            raise HTTPException(status_code=401, detail="Email o password non corretti")
        
        # Create new session
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=15)
        
        await db.user_sessions.insert_one({
            "user_id": user["user_id"],
            "session_token": session_token,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc)
        })
        
        # Set session cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=30 * 24 * 60 * 60
        )
        
        # Return user data (without password)
        user_response = {k: v for k, v in user.items() if 'password' not in k and k != '_id'}
        user_response["session_token"] = session_token
        
        logger.info(f"User logged in: {data.email}")
        
        return {
            "success": True,
            "message": "Login effettuato",
            "user": user_response,
            "session_token": session_token
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il login")

# ==================== USER ENDPOINTS ====================

@api_router.get("/users/profile")
async def get_user_profile(user: UserProfile = Depends(require_auth)):
    """Get current user's full profile"""
    return user.dict()

@api_router.put("/users/profile")
async def update_user_profile(data: OnboardingData, user: UserProfile = Depends(require_auth)):
    """Update user profile with onboarding data"""
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc)
    
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": update_data}
    )
    
    updated_user = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    return updated_user

@api_router.put("/users/language")
async def update_language(request: Request, user: UserProfile = Depends(require_auth)):
    """Update user language preference"""
    body = await request.json()
    language = body.get("language", "it")
    
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"language": language, "updated_at": datetime.now(timezone.utc)}}
    )
    
    return {"message": "Language updated", "language": language}

# ==================== LEVEL PROGRESSION ENDPOINTS ====================

def check_level_progression(user: UserProfile) -> dict:
    """
    Check if user can progress to next level based on time.
    - Beginner → Intermediate: 3 months (90 days)
    - Intermediate → Advanced: 6 months (180 days)
    """
    current_level = user.calculated_level or user.fitness_level or "beginner"
    level_start_date = getattr(user, 'level_start_date', None)
    level_up_declined_at = getattr(user, 'level_up_declined_at', None)
    
    # If no level start date, use account creation date
    if not level_start_date:
        level_start_date = user.created_at
    
    # Convert string to datetime if needed
    if isinstance(level_start_date, str):
        try:
            level_start_date = datetime.fromisoformat(level_start_date.replace('Z', '+00:00'))
        except:
            level_start_date = datetime.now(timezone.utc)
    
    # Ensure timezone awareness
    if level_start_date.tzinfo is None:
        level_start_date = level_start_date.replace(tzinfo=timezone.utc)
    
    now = datetime.now(timezone.utc)
    days_at_level = (now - level_start_date).days
    
    # Check if user declined recently (within 30 days)
    if level_up_declined_at:
        if isinstance(level_up_declined_at, str):
            level_up_declined_at = datetime.fromisoformat(level_up_declined_at.replace('Z', '+00:00'))
        days_since_decline = (now - level_up_declined_at).days
        if days_since_decline < 30:
            return {
                "can_level_up": False,
                "current_level": current_level,
                "days_at_level": days_at_level,
                "next_level": None,
                "days_until_next": None,
                "message": "Hai rifiutato la promozione di recente. Potrai riprovare tra {} giorni.".format(30 - days_since_decline)
            }
    
    # Determine required days and next level
    if current_level == "beginner":
        required_days = 90  # 3 months
        next_level = "intermediate"
        level_name_it = "Intermedio"
    elif current_level == "intermediate":
        required_days = 180  # 6 months
        next_level = "advanced"
        level_name_it = "Avanzato"
    else:  # Already advanced
        return {
            "can_level_up": False,
            "current_level": current_level,
            "days_at_level": days_at_level,
            "next_level": None,
            "days_until_next": None,
            "message": "Sei già al livello massimo! Continua così!"
        }
    
    can_level_up = days_at_level >= required_days
    days_until_next = max(0, required_days - days_at_level)
    
    if can_level_up:
        message = f"Complimenti! Dopo {days_at_level} giorni di allenamento, sei pronto per passare al livello {level_name_it}!"
    else:
        message = f"Ancora {days_until_next} giorni per sbloccare il livello {level_name_it}."
    
    return {
        "can_level_up": can_level_up,
        "current_level": current_level,
        "days_at_level": days_at_level,
        "next_level": next_level if can_level_up else None,
        "days_until_next": days_until_next,
        "required_days": required_days,
        "message": message
    }

@api_router.get("/users/level-status")
async def get_level_status(user: UserProfile = Depends(require_auth)):
    """Get user's current level progression status"""
    return check_level_progression(user)

@api_router.post("/users/level-up")
async def level_up_user(user: UserProfile = Depends(require_auth)):
    """Accept level progression to next level"""
    progression = check_level_progression(user)
    
    if not progression["can_level_up"]:
        raise HTTPException(
            status_code=400,
            detail=progression["message"]
        )
    
    next_level = progression["next_level"]
    now = datetime.now(timezone.utc)
    
    # Update user level and reset level start date
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "calculated_level": next_level,
            "fitness_level": next_level,
            "level_start_date": now,
            "current_training_day": 1,  # Reset to day 1 for new level
            "level_up_available": False,
            "updated_at": now
        }}
    )
    
    level_names = {
        "intermediate": {"it": "Intermedio", "en": "Intermediate"},
        "advanced": {"it": "Avanzato", "en": "Advanced"}
    }
    
    return {
        "success": True,
        "new_level": next_level,
        "message_it": f"Congratulazioni! Sei passato al livello {level_names[next_level]['it']}! I tuoi allenamenti sono stati aggiornati.",
        "message_en": f"Congratulations! You've advanced to {level_names[next_level]['en']} level! Your workouts have been updated."
    }

@api_router.post("/users/decline-level-up")
async def decline_level_up(user: UserProfile = Depends(require_auth)):
    """Decline level progression for now"""
    now = datetime.now(timezone.utc)
    
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "level_up_declined_at": now,
            "updated_at": now
        }}
    )
    
    return {
        "success": True,
        "message_it": "Nessun problema! Ti chiederemo di nuovo tra 30 giorni.",
        "message_en": "No problem! We'll ask you again in 30 days."
    }

# ==================== QUESTIONNAIRE ENDPOINTS ====================

@api_router.get("/questionnaire/questions")
async def get_questionnaire_questions():
    """Get the 15 fitness assessment questions"""
    questions = [
        {
            "id": 1,
            "question_it": "Quanta esperienza hai con l'allenamento?",
            "question_en": "How much training experience do you have?",
            "options_it": ["Nessuna", "Meno di 6 mesi", "6-12 mesi", "1-3 anni", "Oltre 3 anni"],
            "options_en": ["None", "Less than 6 months", "6-12 months", "1-3 years", "More than 3 years"]
        },
        {
            "id": 2,
            "question_it": "Quante volte ti alleni a settimana?",
            "question_en": "How many times do you train per week?",
            "options_it": ["Mai", "1-2 volte", "3-4 volte", "5-6 volte", "Tutti i giorni"],
            "options_en": ["Never", "1-2 times", "3-4 times", "5-6 times", "Every day"]
        },
        {
            "id": 3,
            "question_it": "Come valuteresti la tua resistenza fisica?",
            "question_en": "How would you rate your physical endurance?",
            "options_it": ["Molto bassa", "Bassa", "Media", "Buona", "Eccellente"],
            "options_en": ["Very low", "Low", "Average", "Good", "Excellent"]
        },
        {
            "id": 4,
            "question_it": "Come valuteresti la tua forza attuale?",
            "question_en": "How would you rate your current strength?",
            "options_it": ["Molto bassa", "Bassa", "Media", "Buona", "Eccellente"],
            "options_en": ["Very low", "Low", "Average", "Good", "Excellent"]
        },
        {
            "id": 5,
            "question_it": "Che attrezzatura hai a disposizione?",
            "question_en": "What equipment do you have available?",
            "options_it": ["Nessuna", "Solo tappetino", "Manubri leggeri", "Palestra casalinga", "Palestra completa"],
            "options_en": ["None", "Mat only", "Light dumbbells", "Home gym", "Full gym"]
        },
        {
            "id": 6,
            "question_it": "Come descriveresti il tuo livello di energia quotidiano?",
            "question_en": "How would you describe your daily energy level?",
            "options_it": ["Molto basso", "Basso", "Normale", "Alto", "Molto alto"],
            "options_en": ["Very low", "Low", "Normal", "High", "Very high"]
        },
        {
            "id": 7,
            "question_it": "Quali difficoltà riscontri di più durante l'allenamento?",
            "question_en": "What difficulties do you encounter most during training?",
            "options_it": ["Mi stanco subito", "Mancanza di motivazione", "Dolori articolari", "Poco tempo", "Nessuna particolare"],
            "options_en": ["I get tired quickly", "Lack of motivation", "Joint pain", "Little time", "None in particular"]
        },
        {
            "id": 8,
            "question_it": "Qual è il tuo obiettivo estetico principale?",
            "question_en": "What is your main aesthetic goal?",
            "options_it": ["Perdere grasso", "Aumentare muscoli", "Tonificare", "Migliorare postura", "Mantenermi in forma"],
            "options_en": ["Lose fat", "Build muscle", "Tone up", "Improve posture", "Stay fit"]
        },
        {
            "id": 9,
            "question_it": "Quanto sei motivato a raggiungere i tuoi obiettivi?",
            "question_en": "How motivated are you to reach your goals?",
            "options_it": ["Poco", "Abbastanza", "Motivato", "Molto motivato", "Estremamente motivato"],
            "options_en": ["Little", "Somewhat", "Motivated", "Very motivated", "Extremely motivated"]
        },
        {
            "id": 10,
            "question_it": "Preferisci cardio o allenamento di forza?",
            "question_en": "Do you prefer cardio or strength training?",
            "options_it": ["Solo cardio", "Più cardio", "Entrambi equamente", "Più forza", "Solo forza"],
            "options_en": ["Cardio only", "More cardio", "Both equally", "More strength", "Strength only"]
        },
        {
            "id": 11,
            "question_it": "Quanto tempo puoi dedicare all'allenamento?",
            "question_en": "How much time can you dedicate to training?",
            "options_it": ["15 minuti", "20-30 minuti", "30-45 minuti", "45-60 minuti", "Oltre 60 minuti"],
            "options_en": ["15 minutes", "20-30 minutes", "30-45 minutes", "45-60 minutes", "Over 60 minutes"]
        },
        {
            "id": 12,
            "question_it": "Hai problemi fisici o infortuni?",
            "question_en": "Do you have any physical problems or injuries?",
            "options_it": ["Gravi limitazioni", "Alcune limitazioni", "Lievi fastidi", "Fastidi occasionali", "Nessun problema"],
            "options_en": ["Severe limitations", "Some limitations", "Minor discomfort", "Occasional discomfort", "No problems"]
        },
        {
            "id": 13,
            "question_it": "Quanto sei costante con gli impegni?",
            "question_en": "How consistent are you with commitments?",
            "options_it": ["Per niente", "Poco", "Abbastanza", "Molto", "Estremamente"],
            "options_en": ["Not at all", "Little", "Somewhat", "Very", "Extremely"]
        },
        {
            "id": 14,
            "question_it": "Che tipo di allenamento preferisci?",
            "question_en": "What type of training do you prefer?",
            "options_it": ["Rilassante", "Leggero", "Moderato", "Intenso", "Molto intenso"],
            "options_en": ["Relaxing", "Light", "Moderate", "Intense", "Very intense"]
        },
        {
            "id": 15,
            "question_it": "Quanto sei disciplinato con la dieta e il riposo?",
            "question_en": "How disciplined are you with diet and rest?",
            "options_it": ["Per niente", "Poco", "Abbastanza", "Molto", "Estremamente"],
            "options_en": ["Not at all", "Little", "Somewhat", "Very", "Extremely"]
        }
    ]
    return questions

@api_router.post("/questionnaire/submit")
async def submit_questionnaire(submission: QuestionnaireSubmission, user: UserProfile = Depends(require_auth)):
    """Submit questionnaire answers and calculate fitness level"""
    total_score = sum(answer.answer for answer in submission.answers)
    max_score = 15 * 5  # 15 questions, max 5 points each
    
    # Calculate level based on score percentage
    percentage = (total_score / max_score) * 100
    
    if percentage < 40:
        calculated_level = "beginner"
    elif percentage < 70:
        calculated_level = "intermediate"
    else:
        calculated_level = "advanced"
    
    # Store answers and update user
    await db.questionnaire_answers.insert_one({
        "user_id": user.user_id,
        "answers": [a.dict() for a in submission.answers],
        "total_score": total_score,
        "calculated_level": calculated_level,
        "submitted_at": datetime.now(timezone.utc)
    })
    
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "questionnaire_completed": True,
            "questionnaire_score": total_score,
            "calculated_level": calculated_level,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    return {
        "total_score": total_score,
        "calculated_level": calculated_level,
        "percentage": percentage
    }

# ==================== WORKOUT ENDPOINTS ====================

# Exercise database with descriptions and images - COMPLETE DATABASE
# Using specific exercise images from Unsplash
EXERCISE_DATABASE = {
    # === PUSH EXERCISES ===
    "push-up": {
        "description_it": "Posizione prona, mani alla larghezza delle spalle. Spingi verso l'alto mantenendo il corpo dritto. Contrai gli addominali durante tutto il movimento.",
        "description_en": "Prone position, hands shoulder-width apart. Push up while keeping your body straight. Keep abs engaged throughout.",
        "image": "push-up",
        "muscle_groups": ["chest", "triceps", "shoulders"]
    },
    "push-up modificat": {
        "description_it": "Versione facilitata con ginocchia a terra. Mantieni il busto dritto e scendi fino a sfiorare il pavimento con il petto.",
        "description_en": "Easier version with knees on ground. Keep torso straight and lower until chest nearly touches floor.",
        "image": "push-up-modificati",
        "muscle_groups": ["chest", "triceps"]
    },
    "push-up esplosiv": {
        "description_it": "Flessione esplosiva: spingi con forza per staccare le mani dal pavimento. Atterra morbidamente e ripeti.",
        "description_en": "Explosive push-up: push hard to lift hands off floor. Land softly and repeat.",
        "image": "push-up-esplosivi",
        "muscle_groups": ["chest", "triceps", "power"]
    },
    "pike push-up": {
        "description_it": "Posizione a V invertita con i fianchi in alto. Abbassa la testa verso il pavimento piegando i gomiti. Ottimo per le spalle.",
        "description_en": "Inverted V position with hips high. Lower head toward floor by bending elbows. Great for shoulders.",
        "image": "pike-push-up",
        "muscle_groups": ["shoulders", "triceps"]
    },
    
    # === SQUAT EXERCISES ===
    "squat": {
        "description_it": "Piedi alla larghezza delle spalle, scendi piegando le ginocchia come se ti sedessi. Mantieni la schiena dritta e il peso sui talloni.",
        "description_en": "Feet shoulder-width apart, lower by bending knees as if sitting. Keep back straight and weight on heels.",
        "image": "squat",
        "muscle_groups": ["quadriceps", "glutes", "hamstrings"]
    },
    "squat jump": {
        "description_it": "Esegui uno squat profondo e salta esplosivamente verso l'alto. Atterra morbidamente sulle punte e scendi subito nel prossimo squat.",
        "description_en": "Perform a deep squat and jump explosively upward. Land softly on toes and immediately go into next squat.",
        "image": "squat-jump",
        "muscle_groups": ["quadriceps", "glutes", "cardio"]
    },
    "squat leggero": {
        "description_it": "Squat con range di movimento ridotto, ideale per principianti. Scendi fino a metà e risali controllando il movimento.",
        "description_en": "Squat with reduced range of motion, ideal for beginners. Go halfway down and rise controlling the movement.",
        "image": "squat-leggero",
        "muscle_groups": ["quadriceps", "glutes"]
    },
    "squat con salto": {
        "description_it": "Squat seguito da un salto verticale. Usa le braccia per darti slancio. Atterra con le ginocchia leggermente piegate.",
        "description_en": "Squat followed by a vertical jump. Use arms for momentum. Land with knees slightly bent.",
        "image": "squat-jump",
        "muscle_groups": ["quadriceps", "glutes", "power"]
    },
    "sumo squat": {
        "description_it": "Piedi larghi con punte verso l'esterno. Scendi mantenendo le ginocchia allineate con le punte dei piedi. Lavora interno coscia e glutei.",
        "description_en": "Wide stance with toes pointing out. Lower while keeping knees aligned with toes. Works inner thighs and glutes.",
        "image": "sumo-squat",
        "muscle_groups": ["inner_thighs", "glutes", "quadriceps"]
    },
    "sumo squat pulse": {
        "description_it": "Mantieni la posizione di sumo squat e fai piccoli movimenti su e giù. Brucia i glutei e le cosce interne.",
        "description_en": "Hold sumo squat position and make small up and down movements. Burns glutes and inner thighs.",
        "image": "sumo-squat-pulse",
        "muscle_groups": ["inner_thighs", "glutes"]
    },
    "pistol squat": {
        "description_it": "Squat su una gamba sola con l'altra gamba estesa in avanti. Esercizio avanzato per forza e equilibrio.",
        "description_en": "Single leg squat with other leg extended forward. Advanced exercise for strength and balance.",
        "image": "pistol-squat",
        "muscle_groups": ["quadriceps", "glutes", "balance"]
    },
    
    # === LUNGE EXERCISES ===
    "affond": {
        "description_it": "Fai un passo avanti e piega entrambe le ginocchia a 90 gradi. Il ginocchio posteriore sfiora il pavimento. Alterna le gambe.",
        "description_en": "Step forward and bend both knees to 90 degrees. Back knee nearly touches floor. Alternate legs.",
        "image": "lunge",
        "muscle_groups": ["quadriceps", "glutes", "hamstrings"]
    },
    "affondi lateral": {
        "description_it": "Fai un passo laterale e piega il ginocchio della gamba che si muove. L'altra gamba resta tesa. Ottimo per gli adduttori.",
        "description_en": "Step to the side and bend the moving leg's knee. Other leg stays straight. Great for adductors.",
        "image": "affondi-laterali",
        "muscle_groups": ["inner_thighs", "glutes", "quadriceps"]
    },
    "affondi saltat": {
        "description_it": "Affondo con salto per cambiare gamba in aria. Esercizio esplosivo per potenza e cardio.",
        "description_en": "Lunge with jump to switch legs in air. Explosive exercise for power and cardio.",
        "image": "affondi-saltati",
        "muscle_groups": ["quadriceps", "glutes", "cardio"]
    },
    "affondi bulgar": {
        "description_it": "Piede posteriore appoggiato su una superficie rialzata. Scendi piegando il ginocchio anteriore. Intenso per quadricipiti e glutei.",
        "description_en": "Back foot elevated on a surface. Lower by bending front knee. Intense for quads and glutes.",
        "image": "affondi-bulgari",
        "muscle_groups": ["quadriceps", "glutes"]
    },
    
    # === PLANK EXERCISES ===
    "plank": {
        "description_it": "Posizione prona sui gomiti, corpo dritto dalla testa ai talloni. Mantieni gli addominali contratti e non far cadere i fianchi.",
        "description_en": "Prone position on elbows, body straight from head to heels. Keep abs tight and don't let hips drop.",
        "image": "plank",
        "muscle_groups": ["core", "shoulders"]
    },
    "plank lateral": {
        "description_it": "Sul fianco, appoggiato su un gomito. Solleva i fianchi per creare una linea dritta. Lavora gli obliqui.",
        "description_en": "On your side, supported by one elbow. Lift hips to create a straight line. Works obliques.",
        "image": "plank-lateral",
        "muscle_groups": ["obliques", "core"]
    },
    "plank dinamic": {
        "description_it": "Alterna tra plank sui gomiti e plank sulle mani. Mantieni il core stabile durante la transizione.",
        "description_en": "Alternate between elbow plank and hand plank. Keep core stable during transition.",
        "image": "plank-dinamico",
        "muscle_groups": ["core", "shoulders", "triceps"]
    },
    "plank up-down": {
        "description_it": "Parti sui gomiti, sali sulle mani una alla volta, poi scendi. Mantieni i fianchi stabili.",
        "description_en": "Start on elbows, push up to hands one at a time, then lower. Keep hips stable.",
        "image": "plank-up-down",
        "muscle_groups": ["core", "shoulders", "triceps"]
    },
    "plank con rotazione": {
        "description_it": "Da plank, ruota il corpo aprendo un braccio verso il soffitto. Alterna i lati.",
        "description_en": "From plank, rotate body opening one arm toward ceiling. Alternate sides.",
        "image": "plank-con-rotazione",
        "muscle_groups": ["core", "obliques", "shoulders"]
    },
    
    # === BURPEE VARIATIONS ===
    "burpee": {
        "description_it": "Squat, mani a terra, salto indietro in plank, flessione opzionale, salto in avanti e salto verticale con braccia in alto.",
        "description_en": "Squat, hands down, jump back to plank, optional push-up, jump forward and vertical jump with arms up.",
        "image": "burpee",
        "muscle_groups": ["full_body", "cardio"]
    },
    "burpees complet": {
        "description_it": "Burpee con flessione completa. Il movimento più intenso per bruciare calorie e costruire resistenza.",
        "description_en": "Burpee with full push-up. Most intense movement for burning calories and building endurance.",
        "image": "burpees-completi",
        "muscle_groups": ["full_body", "cardio"]
    },
    "burpees modificat": {
        "description_it": "Versione semplificata: step indietro invece di saltare, senza flessione. Ideale per principianti.",
        "description_en": "Simplified version: step back instead of jumping, no push-up. Ideal for beginners.",
        "image": "burpees-modificati",
        "muscle_groups": ["full_body", "cardio"]
    },
    "burpee box jump": {
        "description_it": "Burpee seguito da un salto su una box o superficie rialzata. Esercizio avanzato per potenza esplosiva.",
        "description_en": "Burpee followed by a jump onto a box or elevated surface. Advanced exercise for explosive power.",
        "image": "burpee-box-jump",
        "muscle_groups": ["full_body", "power"]
    },
    
    # === GLUTE EXERCISES ===
    "ponte glute": {
        "description_it": "Sdraiato sulla schiena, piedi a terra. Solleva i fianchi contraendo i glutei. Tieni la posizione in alto per un secondo.",
        "description_en": "Lying on back, feet on floor. Lift hips by squeezing glutes. Hold position at top for one second.",
        "image": "ponte-glutei",
        "muscle_groups": ["glutes", "hamstrings"]
    },
    "hip thrust": {
        "description_it": "Schiena appoggiata su panca o divano, piedi a terra. Solleva i fianchi fino a formare una linea retta dalle spalle alle ginocchia.",
        "description_en": "Back against bench or couch, feet on floor. Lift hips until forming straight line from shoulders to knees.",
        "image": "hip-thrust",
        "muscle_groups": ["glutes", "hamstrings"]
    },
    "hip thrust esplosiv": {
        "description_it": "Hip thrust con movimento esplosivo verso l'alto. Contrai forte i glutei al picco del movimento.",
        "description_en": "Hip thrust with explosive upward movement. Squeeze glutes hard at peak of movement.",
        "image": "hip-thrust-esplosivo",
        "muscle_groups": ["glutes", "power"]
    },
    "donkey kick": {
        "description_it": "A quattro zampe, calcia una gamba verso l'alto mantenendo il ginocchio piegato a 90 gradi. Contrai il gluteo.",
        "description_en": "On all fours, kick one leg up keeping knee bent at 90 degrees. Squeeze the glute.",
        "image": "donkey-kick",
        "muscle_groups": ["glutes"]
    },
    "fire hydrant": {
        "description_it": "A quattro zampe, solleva il ginocchio lateralmente mantenendo l'angolo di 90 gradi. Lavora i glutei laterali.",
        "description_en": "On all fours, lift knee to the side keeping 90 degree angle. Works lateral glutes.",
        "image": "fire-hydrant",
        "muscle_groups": ["glutes", "hip_abductors"]
    },
    "clamshell": {
        "description_it": "Sdraiato sul fianco, ginocchia piegate. Apri il ginocchio superiore come una conchiglia mantenendo i piedi uniti.",
        "description_en": "Lying on side, knees bent. Open top knee like a clamshell while keeping feet together.",
        "image": "clamshell",
        "muscle_groups": ["glutes", "hip_abductors"]
    },
    "frog jump": {
        "description_it": "Squat profondo con salto in avanti come una rana. Atterra morbidamente e ripeti.",
        "description_en": "Deep squat with forward jump like a frog. Land softly and repeat.",
        "image": "frog-jump",
        "muscle_groups": ["glutes", "quadriceps", "cardio"]
    },
    
    # === CORE EXERCISES ===
    "crunch": {
        "description_it": "Sdraiato sulla schiena, ginocchia piegate. Solleva le spalle contraendo gli addominali. Non tirare il collo.",
        "description_en": "Lying on back, knees bent. Lift shoulders by contracting abs. Don't pull on neck.",
        "image": "crunch",
        "muscle_groups": ["abs"]
    },
    "crunch bicicletta": {
        "description_it": "Crunch con rotazione, portando il gomito verso il ginocchio opposto mentre estendi l'altra gamba.",
        "description_en": "Crunch with rotation, bringing elbow toward opposite knee while extending other leg.",
        "image": "crunch-bicicletta",
        "muscle_groups": ["abs", "obliques"]
    },
    "dead bug": {
        "description_it": "Sdraiato sulla schiena, braccia e gambe in aria. Estendi braccio e gamba opposti mantenendo la schiena a terra.",
        "description_en": "Lying on back, arms and legs in air. Extend opposite arm and leg while keeping back on floor.",
        "image": "dead-bug",
        "muscle_groups": ["core", "stability"]
    },
    "superman": {
        "description_it": "Sdraiato a pancia in giù, solleva braccia e gambe contemporaneamente. Tieni la posizione per 2 secondi.",
        "description_en": "Lying face down, lift arms and legs simultaneously. Hold position for 2 seconds.",
        "image": "superman",
        "muscle_groups": ["lower_back", "glutes"]
    },
    "mountain climber": {
        "description_it": "In posizione di plank, porta alternativamente le ginocchia verso il petto velocemente come se corressi.",
        "description_en": "In plank position, alternately bring knees toward chest quickly as if running.",
        "image": "mountain-climber",
        "muscle_groups": ["core", "cardio", "shoulders"]
    },
    
    # === CARDIO EXERCISES ===
    "jumping jack": {
        "description_it": "Salta aprendo gambe e braccia lateralmente, poi torna alla posizione iniziale. Mantieni un ritmo costante.",
        "description_en": "Jump while spreading legs and arms to sides, then return to starting position. Keep steady rhythm.",
        "image": "jumping-jack",
        "muscle_groups": ["cardio", "full_body"]
    },
    "high knee": {
        "description_it": "Corri sul posto portando le ginocchia alte verso il petto. Mantieni un ritmo veloce.",
        "description_en": "Run in place bringing knees high toward chest. Keep a fast pace.",
        "image": "high-knee",
        "muscle_groups": ["cardio", "hip_flexors"]
    },
    "sprint sul posto": {
        "description_it": "Corri sul posto il più velocemente possibile. Pompa le braccia e solleva le ginocchia.",
        "description_en": "Run in place as fast as possible. Pump arms and lift knees.",
        "image": "sprint-sul-posto",
        "muscle_groups": ["cardio", "full_body"]
    },
    
    # === OTHER EXERCISES ===
    "dip": {
        "description_it": "Mani su una sedia dietro di te, gambe estese. Abbassa il corpo piegando i gomiti a 90 gradi, poi spingi verso l'alto.",
        "description_en": "Hands on chair behind you, legs extended. Lower body bending elbows to 90 degrees, then push up.",
        "image": "dip",
        "muscle_groups": ["triceps", "chest", "shoulders"]
    },
    "step-up": {
        "description_it": "Sali su una superficie rialzata con una gamba, porta su l'altra, poi scendi. Alterna la gamba che inizia.",
        "description_en": "Step onto elevated surface with one leg, bring other up, then step down. Alternate starting leg.",
        "image": "box-step-up",
        "muscle_groups": ["quadriceps", "glutes"]
    },
    "box step-up": {
        "description_it": "Step-up su una box più alta. Spingi attraverso il tallone e contrai il gluteo in cima.",
        "description_en": "Step-up onto a higher box. Push through heel and squeeze glute at top.",
        "image": "box-step-up",
        "muscle_groups": ["quadriceps", "glutes"]
    },
    "single leg deadlift": {
        "description_it": "In piedi su una gamba, inclinati in avanti estendendo l'altra gamba indietro. Mantieni la schiena dritta.",
        "description_en": "Standing on one leg, hinge forward extending other leg back. Keep back straight.",
        "image": "single-leg-deadlift",
        "muscle_groups": ["hamstrings", "glutes", "balance"]
    },
    "muscle-up": {
        "description_it": "Trazione alla sbarra seguita da un dip sopra la sbarra. Esercizio avanzato che richiede forza e tecnica.",
        "description_en": "Pull-up followed by dip above the bar. Advanced exercise requiring strength and technique.",
        "image": "muscle-up-modificati",
        "muscle_groups": ["back", "chest", "triceps"]
    },
    "jump squat": {
        "description_it": "Squat seguito da un salto esplosivo. Atterra morbidamente e scendi subito nel prossimo squat.",
        "description_en": "Squat followed by explosive jump. Land softly and immediately go into next squat.",
        "image": "squat-jump",
        "muscle_groups": ["quadriceps", "glutes", "cardio"]
    },
    
    # === DEFAULT FALLBACK ===
    "default": {
        "description_it": "Esegui l'esercizio seguendo la tecnica corretta. Mantieni il controllo del movimento e respira regolarmente.",
        "description_en": "Perform the exercise with correct technique. Maintain control of movement and breathe regularly.",
        "image": "squat",
        "muscle_groups": ["full_body"]
    }
}

def enrich_exercise(exercise: Dict, base_url: str = "") -> Dict:
    """Add description and image to exercise based on name"""
    name = (exercise.get("name_it") or exercise.get("name_en") or "").lower()
    
    # Mapping from Italian exercise names to image file names - ALL 46 EXERCISES
    IMAGE_NAME_MAP = {
        # Push-up variants
        "pike push-up": "pike-push-up",
        "push-up esplosiv": "push-up-esplosivi",
        "push-up modificat": "push-up-modificati",
        "push-up": "push-up",
        # Squat variants
        "squat jump": "squat-jump",
        "squat leggero": "squat-leggero",
        "squat con salto": "squat-jump",
        "squat a corpo libero": "squat-corpo-libero",
        "squat corpo libero": "squat-corpo-libero",
        "sumo squat pulse": "sumo-squat-pulse",
        "sumo squat": "sumo-squat",
        "pistol squat": "pistol-squat",
        "jump squat": "squat-jump",
        "squat": "squat",
        # Plank variants
        "plank lateral": "plank-lateral",
        "plank dinamic": "plank-dinamico",
        "plank up-down": "plank-up-down",
        "plank con rotazione": "plank-con-rotazione",
        "plank": "plank",
        # Lunge/Affondi variants
        "affondi bulgar": "affondi-bulgari",
        "affondi alternati": "affondi-alternati",
        "affondi lateral": "affondi-laterali",
        "affondi saltat": "affondi-saltati",
        "affond": "lunge",
        # Burpee variants
        "burpees complet": "burpees-completi",
        "burpees modificat": "burpees-modificati",
        "burpee box jump": "burpee-box-jump",
        "burpee": "burpee",
        # Glute exercises
        "ponte glute": "ponte-glutei",
        "hip thrust esplosiv": "hip-thrust-esplosivo",
        "hip thrust": "hip-thrust",
        "donkey kick": "donkey-kick",
        "fire hydrant": "fire-hydrant",
        "clamshell": "clamshell",
        "frog jump": "frog-jump",
        "glute bridge": "glute-bridge",
        # Core exercises
        "crunch bicicletta": "crunch-bicicletta",
        "crunch": "crunch",
        "dead bug": "dead-bug",
        "superman": "superman",
        "mountain climber": "mountain-climber",
        # Cardio
        "jumping jack": "jumping-jack",
        "high knee": "high-knee",
        "sprint sul posto": "sprint-sul-posto",
        # Other exercises
        "dips su sedia": "dips-su-sedia",
        "dip": "dip",
        "box step-up": "box-step-up",
        "step-up": "box-step-up",
        "single leg deadlift": "single-leg-deadlift",
        "muscle-up modificat": "muscle-up-modificati",
        "muscle-up": "muscle-up-modificati",
    }
    
    # Find matching exercise in database
    exercise_info = EXERCISE_DATABASE.get("default")
    matched_key = "default"
    for key, info in EXERCISE_DATABASE.items():
        if key in name:
            exercise_info = info
            matched_key = key
            break
    
    # Enrich exercise with description and image
    enriched = exercise.copy()
    if "description_it" not in enriched:
        enriched["description_it"] = exercise_info["description_it"]
    if "description_en" not in enriched:
        enriched["description_en"] = exercise_info["description_en"]
    
    # Find the correct image file
    image_file = None
    for key, img_name in IMAGE_NAME_MAP.items():
        if key in name:
            image_file = img_name
            break
    
    if image_file:
        local_image_path = FRONTEND_DIR / "assets" / "images" / "exercises" / f"{image_file}.png"
        if local_image_path.exists():
            enriched["image"] = f"/api/exercises/images/{image_file}"
        else:
            enriched["image"] = exercise_info.get("image", "")
    elif "image" not in enriched:
        enriched["image"] = exercise_info.get("image", "")
    
    if "muscle_groups" not in enriched:
        enriched["muscle_groups"] = exercise_info.get("muscle_groups", [])
    
    return enriched

def enrich_gym_exercise(exercise_key_or_dict, sets: int = 3, reps: int = 12, rest: int = 60, duration: int = None) -> Dict:
    """
    Arricchisce un esercizio con descrizione e immagine dal database.
    Se l'input è già un dict (esercizio vecchio formato), lo restituisce con immagine aggiunta.
    Se l'esercizio non è nel database, ritorna i dati base.
    """
    # Se è già un dizionario, aggiungi solo l'immagine se manca
    if isinstance(exercise_key_or_dict, dict):
        ex = exercise_key_or_dict
        # Cerca l'immagine nel database basandosi sul nome
        name_key = ex.get("name_it", "").lower().replace(" ", "-")
        for db_key, db_ex in GYM_EXERCISES_DATABASE.items():
            if name_key in db_key or db_key in name_key:
                if "image" not in ex:
                    ex["image"] = f"/api/exercises/images/{db_ex['image']}"
                if "description_it" not in ex:
                    ex["description_it"] = db_ex.get("description_it", "")
                    ex["description_en"] = db_ex.get("description_en", "")
                break
        return ex
    
    exercise_key = exercise_key_or_dict
    if exercise_key in GYM_EXERCISES_DATABASE:
        ex = GYM_EXERCISES_DATABASE[exercise_key]
        result = {
            "name_it": ex["name_it"],
            "name_en": ex["name_en"],
            "description_it": ex["description_it"],
            "description_en": ex["description_en"],
            "muscles_it": ex.get("muscles_it", ""),
            "muscles_en": ex.get("muscles_en", ""),
            "equipment": ex.get("equipment", ""),
            "image": f"/api/exercises/images/{ex['image']}",
            "sets": sets,
            "rest": rest
        }
        if duration:
            result["duration"] = duration
        else:
            result["reps"] = reps
        return result
    # Fallback per esercizi non nel database
    return {
        "name_it": exercise_key.replace("-", " ").title(),
        "name_en": exercise_key.replace("-", " ").title(),
        "sets": sets,
        "reps": reps if not duration else None,
        "duration": duration,
        "rest": rest
    }

def get_gym_workouts(gender: str, level: str, goal: str) -> List[Dict]:
    """Generate gym workout programs with dumbbells, barbells and bodyweight exercises - con descrizioni e immagini"""
    workouts = []
    
    if gender == "male":
        if level == "beginner":
            workouts = [
                {
                    "id": "gym_m_beg_1",
                    "name_it": "Petto & Tricipiti - Giorno 1",
                    "name_en": "Chest & Triceps - Day 1",
                    "description_it": "Allenamento petto e tricipiti con manubri e bilanciere. Focus sulla costruzione di forza base per la parte superiore del corpo.",
                    "description_en": "Chest and triceps workout with dumbbells and barbell. Focus on building base strength for the upper body.",
                    "duration": 45,
                    "difficulty": "beginner",
                    "category": "strength",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("panca-piana-bilanciere", sets=4, reps=10, rest=90),
                        enrich_gym_exercise("panca-inclinata-manubri", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("croci-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("french-press", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("pushdown-tricipiti", sets=3, reps=12, rest=45)
                    ]
                },
                {
                    "id": "gym_m_beg_2",
                    "name_it": "Schiena & Bicipiti - Giorno 2",
                    "name_en": "Back & Biceps - Day 2",
                    "description_it": "Allenamento schiena e bicipiti con rematore e trazioni. Costruisci una schiena forte e braccia definite.",
                    "description_en": "Back and biceps workout with rows and pulldowns. Build a strong back and defined arms.",
                    "duration": 45,
                    "difficulty": "beginner",
                    "category": "strength",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("rematore-manubrio", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("lat-machine", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("curl-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("curl-martello", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_m_beg_3",
                    "name_it": "Gambe - Giorno 3",
                    "name_en": "Legs - Day 3",
                    "description_it": "Allenamento gambe completo con squat, affondi e stacco. Sviluppa forza e potenza nelle gambe.",
                    "description_en": "Complete leg workout with squats, lunges and deadlifts. Build strength and power in your legs.",
                    "duration": 50,
                    "difficulty": "beginner",
                    "category": "strength",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("squat-bilanciere", sets=4, reps=10, rest=90),
                        enrich_gym_exercise("affondi-manubri", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("stacco-rumeno-manubri", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("calf-raises-manubri", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_m_beg_4",
                    "name_it": "Spalle & Core - Giorno 4",
                    "name_en": "Shoulders & Core - Day 4",
                    "description_it": "Allenamento spalle con military press e alzate. Addominali per un core forte.",
                    "description_en": "Shoulder workout with military press and raises. Core work for a strong midsection.",
                    "duration": 45,
                    "difficulty": "beginner",
                    "category": "strength",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("shoulder-press-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("alzate-laterali", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("alzate-frontali", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("croci-inverse", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("scrollate-manubri", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_m_beg_5",
                    "name_it": "Full Body - Giorno 5",
                    "name_en": "Full Body - Day 5",
                    "description_it": "Allenamento total body con pesi liberi. Lavora tutti i gruppi muscolari in una sessione.",
                    "description_en": "Full body workout with free weights. Hit all muscle groups in one session.",
                    "duration": 50,
                    "difficulty": "beginner",
                    "category": "strength",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("squat-goblet", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("panca-piana-bilanciere", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("rematore-manubrio", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("shoulder-press-manubri", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("curl-bilanciere", sets=3, reps=12, rest=45)
                    ]
                },
                {
                    "id": "gym_m_beg_6",
                    "name_it": "Upper Body - Giorno 6",
                    "name_en": "Upper Body - Day 6",
                    "description_it": "Parte superiore del corpo con focus su braccia e petto.",
                    "description_en": "Upper body focus targeting arms and chest.",
                    "duration": 45,
                    "difficulty": "beginner",
                    "category": "strength",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("panca-inclinata-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("rematore-bilanciere", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("curl-bilanciere", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("french-press-manubrio", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("concentration-curl", sets=3, reps=10, rest=30)
                    ]
                },
                {
                    "id": "gym_m_beg_7",
                    "name_it": "Recupero Attivo - Giorno 7",
                    "name_en": "Active Recovery - Day 7",
                    "description_it": "Stretching e mobilità per favorire il recupero muscolare.",
                    "description_en": "Stretching and mobility for muscle recovery.",
                    "duration": 30,
                    "difficulty": "beginner",
                    "category": "recovery",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=3, reps=15, rest=30),
                        enrich_gym_exercise("good-morning", sets=3, reps=10, rest=30),
                        enrich_gym_exercise("pullover-manubrio", sets=3, reps=12, rest=30),
                        {"name_it": "Stretching generale", "name_en": "General stretching", "sets": 1, "duration": 300, "rest": 0}
                    ]
                }
            ]
        elif level == "intermediate":
            workouts = [
                {
                    "id": "gym_m_int_1",
                    "name_it": "Forza Intermedia - Giorno 1 (Push)",
                    "name_en": "Intermediate Strength - Day 1 (Push)",
                    "description_it": "Push day intenso: petto, spalle, tricipiti con bilanciere e manubri.",
                    "description_en": "Intense push day: chest, shoulders, triceps with barbell and dumbbells.",
                    "duration": 55,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("panca-piana-bilanciere", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("panca-inclinata-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("military-press", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("croci-cavi", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("french-press", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("pushdown-tricipiti", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_m_int_2",
                    "name_it": "Forza Intermedia - Giorno 2 (Pull)",
                    "name_en": "Intermediate Strength - Day 2 (Pull)",
                    "description_it": "Pull day intenso: schiena, bicipiti con stacco e trazioni.",
                    "description_en": "Intense pull day: back, biceps with deadlifts and pull-ups.",
                    "duration": 55,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("stacco-da-terra", sets=4, reps=6, rest=120),
                        enrich_gym_exercise("trazioni-alla-sbarra", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("rematore-bilanciere", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=45),
                        enrich_gym_exercise("curl-bilanciere", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("curl-martello", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_m_int_3",
                    "name_it": "Forza Intermedia - Giorno 3 (Gambe)",
                    "name_en": "Intermediate Strength - Day 3 (Legs)",
                    "description_it": "Leg day completo con squat, stacco rumeno e pressa.",
                    "description_en": "Complete leg day with squat, Romanian deadlift and leg press.",
                    "duration": 55,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("squat-bilanciere", sets=4, reps=8, rest=120),
                        enrich_gym_exercise("leg-press", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("stacco-rumeno", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("leg-extension", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("calf-raises-manubri", sets=4, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_m_int_4",
                    "name_it": "Forza Intermedia - Giorno 4 (Push 2)",
                    "name_en": "Intermediate Strength - Day 4 (Push 2)",
                    "description_it": "Secondo push day con focus su petto alto e spalle.",
                    "description_en": "Second push day with focus on upper chest and shoulders.",
                    "duration": 50,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("panca-inclinata-bilanciere", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("arnold-press", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("croci-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("alzate-laterali", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("dips-parallele", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("overhead-tricep-extension", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_m_int_5",
                    "name_it": "Forza Intermedia - Giorno 5 (Pull 2)",
                    "name_en": "Intermediate Strength - Day 5 (Pull 2)",
                    "description_it": "Secondo pull day con focus su dorsali e bicipiti.",
                    "description_en": "Second pull day with focus on lats and biceps.",
                    "duration": 50,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("lat-machine", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("rematore-cavi", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("pullover-manubrio", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("scrollate-manubri", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("preacher-curl", sets=3, reps=10, rest=45),
                        enrich_gym_exercise("concentration-curl", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_m_int_6",
                    "name_it": "Forza Intermedia - Giorno 6 (Gambe 2)",
                    "name_en": "Intermediate Strength - Day 6 (Legs 2)",
                    "description_it": "Secondo leg day con focus su glutei e femorali.",
                    "description_en": "Second leg day with focus on glutes and hamstrings.",
                    "duration": 50,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("split-squat-bulgaro", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("stacco-rumeno-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("affondi-manubri", sets=3, reps=10, rest=45),
                        enrich_gym_exercise("step-up-manubri", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_m_int_7",
                    "name_it": "Forza Intermedia - Giorno 7 (Recupero)",
                    "name_en": "Intermediate Strength - Day 7 (Recovery)",
                    "description_it": "Recupero attivo con esercizi leggeri e stretching.",
                    "description_en": "Active recovery with light exercises and stretching.",
                    "duration": 35,
                    "difficulty": "intermediate",
                    "category": "recovery",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("good-morning", sets=3, reps=12, rest=30),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=30),
                        {"name_it": "Cyclette", "name_en": "Stationary bike", "sets": 1, "duration": 600, "rest": 60},
                        {"name_it": "Stretching completo", "name_en": "Full stretching", "sets": 1, "duration": 600, "rest": 0}
                    ]
                }
            ]
        else:  # advanced
            workouts = [
                {
                    "id": "gym_m_adv_1",
                    "name_it": "Potenza Avanzata - Giorno 1 (Petto)",
                    "name_en": "Advanced Power - Day 1 (Chest)",
                    "description_it": "Petto ad alta intensità con carichi pesanti. Costruisci massa e forza.",
                    "description_en": "High intensity chest with heavy loads. Build mass and strength.",
                    "duration": 60,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("panca-piana-bilanciere", sets=5, reps=5, rest=120),
                        enrich_gym_exercise("panca-inclinata-manubri", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("dips-parallele", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("croci-manubri", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("croci-cavi", sets=3, reps=15, rest=45),
                        enrich_gym_exercise("panca-presa-stretta", sets=3, reps=10, rest=60)
                    ]
                },
                {
                    "id": "gym_m_adv_2",
                    "name_it": "Potenza Avanzata - Giorno 2 (Schiena)",
                    "name_en": "Advanced Power - Day 2 (Back)",
                    "description_it": "Schiena massiccia con stacco e trazioni pesanti.",
                    "description_en": "Massive back with heavy deadlifts and pull-ups.",
                    "duration": 60,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("stacco-da-terra", sets=5, reps=5, rest=180),
                        enrich_gym_exercise("trazioni-alla-sbarra", sets=4, reps=6, rest=120),
                        enrich_gym_exercise("rematore-bilanciere", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("t-bar-row", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("pullover-manubrio", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=45)
                    ]
                },
                {
                    "id": "gym_m_adv_3",
                    "name_it": "Potenza Avanzata - Giorno 3 (Gambe)",
                    "name_en": "Advanced Power - Day 3 (Legs)",
                    "description_it": "Leg day devastante con squat e stacchi pesanti.",
                    "description_en": "Devastating leg day with heavy squats and deadlifts.",
                    "duration": 65,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("squat-bilanciere", sets=5, reps=5, rest=180),
                        enrich_gym_exercise("front-squat", sets=4, reps=8, rest=120),
                        enrich_gym_exercise("stacco-rumeno", sets=4, reps=10, rest=90),
                        enrich_gym_exercise("leg-press", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("calf-raises-manubri", sets=4, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_m_adv_4",
                    "name_it": "Potenza Avanzata - Giorno 4 (Spalle)",
                    "name_en": "Advanced Power - Day 4 (Shoulders)",
                    "description_it": "Spalle da boulder con military press e alzate.",
                    "description_en": "Boulder shoulders with military press and raises.",
                    "duration": 55,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("military-press", sets=5, reps=6, rest=120),
                        enrich_gym_exercise("arnold-press", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("alzate-laterali", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("croci-inverse", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("scrollate-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_m_adv_5",
                    "name_it": "Potenza Avanzata - Giorno 5 (Braccia)",
                    "name_en": "Advanced Power - Day 5 (Arms)",
                    "description_it": "Braccia esplosive con focus su bicipiti e tricipiti.",
                    "description_en": "Explosive arms with focus on biceps and triceps.",
                    "duration": 50,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("curl-bilanciere", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("french-press", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("curl-martello", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("pushdown-tricipiti", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("concentration-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("overhead-tricep-extension", sets=3, reps=12, rest=30),
                        enrich_gym_exercise("preacher-curl", sets=3, reps=10, rest=45)
                    ]
                },
                {
                    "id": "gym_m_adv_6",
                    "name_it": "Potenza Avanzata - Giorno 6 (Full Body)",
                    "name_en": "Advanced Power - Day 6 (Full Body)",
                    "description_it": "Total body ad alta intensità con movimenti composti.",
                    "description_en": "High intensity full body with compound movements.",
                    "duration": 60,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("stacco-sumo", sets=4, reps=6, rest=120),
                        enrich_gym_exercise("squat-goblet", sets=4, reps=10, rest=90),
                        enrich_gym_exercise("panca-inclinata-bilanciere", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("rematore-manubrio", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("shoulder-press-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=3, reps=12, rest=60)
                    ]
                },
                {
                    "id": "gym_m_adv_7",
                    "name_it": "Potenza Avanzata - Giorno 7 (Recupero)",
                    "name_en": "Advanced Power - Day 7 (Recovery)",
                    "description_it": "Recupero attivo e mobilità per favorire la crescita muscolare.",
                    "description_en": "Active recovery and mobility to enhance muscle growth.",
                    "duration": 40,
                    "difficulty": "advanced",
                    "category": "recovery",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("good-morning", sets=3, reps=12, rest=30),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=30),
                        enrich_gym_exercise("step-up-manubri", sets=3, reps=10, rest=30),
                        {"name_it": "Stretching completo", "name_en": "Full body stretching", "sets": 1, "duration": 600, "rest": 0}
                    ]
                }
            ]
    else:  # female gym workouts
        if level == "beginner":
            workouts = [
                {
                    "id": "gym_f_beg_1",
                    "name_it": "Palestra Donna - Giorno 1 (Lower Body)",
                    "name_en": "Women's Gym - Day 1 (Lower Body)",
                    "description_it": "Allenamento gambe e glutei con focus sulla tonificazione. Ideale per costruire forza di base nella parte inferiore del corpo.",
                    "description_en": "Legs and glutes workout with focus on toning. Ideal for building base strength in the lower body.",
                    "duration": 45,
                    "difficulty": "beginner",
                    "category": "toning",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("leg-press", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("affondi-manubri", sets=3, reps=10, rest=45),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("calf-raises-manubri", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_f_beg_2",
                    "name_it": "Palestra Donna - Giorno 2 (Upper Body)",
                    "name_en": "Women's Gym - Day 2 (Upper Body)",
                    "description_it": "Braccia e schiena toniche con esercizi mirati. Costruisci definizione senza ingrossare.",
                    "description_en": "Toned arms and back with targeted exercises. Build definition without bulk.",
                    "duration": 40,
                    "difficulty": "beginner",
                    "category": "toning",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("lat-machine", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("panca-inclinata-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("curl-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("pushdown-tricipiti", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_f_beg_3",
                    "name_it": "Palestra Donna - Giorno 3 (Glutei Focus)",
                    "name_en": "Women's Gym - Day 3 (Glute Focus)",
                    "description_it": "Sessione intensiva per glutei rotondi e forti. Esercizi mirati per massimizzare l'attivazione muscolare.",
                    "description_en": "Intensive session for round and strong glutes. Targeted exercises to maximize muscle activation.",
                    "duration": 45,
                    "difficulty": "beginner",
                    "category": "toning",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("squat-goblet", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("stacco-rumeno-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("split-squat-bulgaro", sets=3, reps=10, rest=45),
                        enrich_gym_exercise("step-up-manubri", sets=3, reps=10, rest=30)
                    ]
                },
                {
                    "id": "gym_f_beg_4",
                    "name_it": "Palestra Donna - Giorno 4 (Spalle & Core)",
                    "name_en": "Women's Gym - Day 4 (Shoulders & Core)",
                    "description_it": "Spalle definite e core forte per una postura perfetta.",
                    "description_en": "Defined shoulders and strong core for perfect posture.",
                    "duration": 40,
                    "difficulty": "beginner",
                    "category": "core",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("shoulder-press-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("alzate-laterali", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("croci-inverse", sets=3, reps=12, rest=45),
                        {"name_it": "Plank", "name_en": "Plank", "sets": 3, "duration": 30, "rest": 30},
                        {"name_it": "Crunch", "name_en": "Crunches", "sets": 3, "reps": 15, "rest": 30}
                    ]
                },
                {
                    "id": "gym_f_beg_5",
                    "name_it": "Palestra Donna - Giorno 5 (Full Body)",
                    "name_en": "Women's Gym - Day 5 (Full Body)",
                    "description_it": "Allenamento total body per tonificare tutto il corpo in una sessione.",
                    "description_en": "Full body workout to tone the entire body in one session.",
                    "duration": 45,
                    "difficulty": "beginner",
                    "category": "toning",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("squat-bilanciere", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("rematore-cavi", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("shoulder-press-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("leg-extension", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("curl-manubri", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_f_beg_6",
                    "name_it": "Palestra Donna - Giorno 6 (Lower Focus 2)",
                    "name_en": "Women's Gym - Day 6 (Lower Focus 2)",
                    "description_it": "Secondo allenamento gambe della settimana per massimizzare i risultati.",
                    "description_en": "Second leg workout of the week to maximize results.",
                    "duration": 40,
                    "difficulty": "beginner",
                    "category": "toning",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("front-squat", sets=3, reps=12, rest=60),
                        enrich_gym_exercise("leg-press", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("calf-raises-manubri", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_f_beg_7",
                    "name_it": "Palestra Donna - Giorno 7 (Recupero)",
                    "name_en": "Women's Gym - Day 7 (Recovery)",
                    "description_it": "Stretching e mobilità per favorire il recupero muscolare.",
                    "description_en": "Stretching and mobility for muscle recovery.",
                    "duration": 30,
                    "difficulty": "beginner",
                    "category": "recovery",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("good-morning", sets=3, reps=12, rest=30),
                        {"name_it": "Stretching completo", "name_en": "Full stretching", "sets": 1, "duration": 600, "rest": 0}
                    ]
                }
            ]
        elif level == "intermediate":
            workouts = [
                {
                    "id": "gym_f_int_1",
                    "name_it": "Sculpting - Giorno 1 (Glutei & Gambe)",
                    "name_en": "Sculpting - Day 1 (Glutes & Legs)",
                    "description_it": "Scolpisci glutei e gambe con hip thrust e squat. Costruisci curve definite.",
                    "description_en": "Sculpt glutes and legs with hip thrust and squats. Build defined curves.",
                    "duration": 50,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("split-squat-bulgaro", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("stacco-rumeno", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("calf-raises-manubri", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_f_int_2",
                    "name_it": "Sculpting - Giorno 2 (Upper Body)",
                    "name_en": "Sculpting - Day 2 (Upper Body)",
                    "description_it": "Braccia toniche e schiena definita. Esercizi mirati per una silhouette perfetta.",
                    "description_en": "Toned arms and defined back. Targeted exercises for a perfect silhouette.",
                    "duration": 45,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("lat-machine", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("rematore-manubrio", sets=4, reps=10, rest=45),
                        enrich_gym_exercise("panca-inclinata-manubri", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("shoulder-press-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("pushdown-tricipiti", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_f_int_3",
                    "name_it": "Sculpting - Giorno 3 (Booty Blast)",
                    "name_en": "Sculpting - Day 3 (Booty Blast)",
                    "description_it": "Focus intenso sui glutei per massimizzare volume e definizione.",
                    "description_en": "Intense glute focus to maximize volume and definition.",
                    "duration": 50,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("squat-goblet", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("step-up-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("affondi-manubri", sets=3, reps=10, rest=45),
                        enrich_gym_exercise("stacco-rumeno-manubri", sets=3, reps=12, rest=45)
                    ]
                },
                {
                    "id": "gym_f_int_4",
                    "name_it": "Sculpting - Giorno 4 (Spalle & Braccia)",
                    "name_en": "Sculpting - Day 4 (Shoulders & Arms)",
                    "description_it": "Spalle definite e braccia toniche per un look atletico.",
                    "description_en": "Defined shoulders and toned arms for an athletic look.",
                    "duration": 45,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("arnold-press", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("alzate-laterali", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("croci-inverse", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("curl-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("french-press-manubrio", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_f_int_5",
                    "name_it": "Sculpting - Giorno 5 (Gambe Complete)",
                    "name_en": "Sculpting - Day 5 (Complete Legs)",
                    "description_it": "Gambe snelle e forti con esercizi completi.",
                    "description_en": "Lean and strong legs with complete exercises.",
                    "duration": 50,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("leg-press", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("squat-bilanciere", sets=4, reps=10, rest=90),
                        enrich_gym_exercise("leg-extension", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("calf-raises-manubri", sets=4, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_f_int_6",
                    "name_it": "Sculpting - Giorno 6 (Full Body)",
                    "name_en": "Sculpting - Day 6 (Full Body)",
                    "description_it": "Total body per tonificare tutti i muscoli.",
                    "description_en": "Full body to tone all muscles.",
                    "duration": 50,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("stacco-da-terra", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("panca-piana-bilanciere", sets=3, reps=10, rest=60),
                        enrich_gym_exercise("rematore-cavi", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("shoulder-press-manubri", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_f_int_7",
                    "name_it": "Sculpting - Giorno 7 (Recupero)",
                    "name_en": "Sculpting - Day 7 (Recovery)",
                    "description_it": "Recupero attivo e mobilità per favorire la rigenerazione muscolare.",
                    "description_en": "Active recovery and mobility for muscle regeneration.",
                    "duration": 35,
                    "difficulty": "intermediate",
                    "category": "recovery",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("good-morning", sets=3, reps=12, rest=30),
                        enrich_gym_exercise("pullover-manubrio", sets=3, reps=12, rest=30),
                        {"name_it": "Stretching completo", "name_en": "Full stretching", "sets": 1, "duration": 600, "rest": 0}
                    ]
                }
            ]
        else:  # female advanced gym
            workouts = [
                {
                    "id": "gym_f_adv_1",
                    "name_it": "Elite Donna - Giorno 1 (Glutei Power)",
                    "name_en": "Elite Women - Day 1 (Glute Power)",
                    "description_it": "Glutei al massimo livello con carichi pesanti. Costruisci volume e forza.",
                    "description_en": "Maximum level glutes with heavy loads. Build volume and strength.",
                    "duration": 55,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=5, reps=8, rest=90),
                        enrich_gym_exercise("squat-bilanciere", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("stacco-sumo", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("split-squat-bulgaro", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("leg-curl", sets=3, reps=12, rest=45)
                    ]
                },
                {
                    "id": "gym_f_adv_2",
                    "name_it": "Elite Donna - Giorno 2 (Upper Power)",
                    "name_en": "Elite Women - Day 2 (Upper Power)",
                    "description_it": "Upper body potente per una silhouette atletica e definita.",
                    "description_en": "Powerful upper body for an athletic and defined silhouette.",
                    "duration": 50,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("panca-piana-bilanciere", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("trazioni-alla-sbarra", sets=4, reps=6, rest=90),
                        enrich_gym_exercise("military-press", sets=4, reps=8, rest=60),
                        enrich_gym_exercise("rematore-bilanciere", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=45)
                    ]
                },
                {
                    "id": "gym_f_adv_3",
                    "name_it": "Elite Donna - Giorno 3 (Legs Extreme)",
                    "name_en": "Elite Women - Day 3 (Legs Extreme)",
                    "description_it": "Gambe estreme con squat frontale e stacchi. Potenza massima.",
                    "description_en": "Extreme legs with front squats and deadlifts. Maximum power.",
                    "duration": 55,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("front-squat", sets=4, reps=8, rest=90),
                        enrich_gym_exercise("leg-press", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("stacco-rumeno", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("affondi-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("calf-raises-manubri", sets=4, reps=15, rest=30)
                    ]
                },
                {
                    "id": "gym_f_adv_4",
                    "name_it": "Elite Donna - Giorno 4 (Braccia & Spalle)",
                    "name_en": "Elite Women - Day 4 (Arms & Shoulders)",
                    "description_it": "Braccia scolpite e spalle da modella fitness.",
                    "description_en": "Sculpted arms and fitness model shoulders.",
                    "duration": 45,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("arnold-press", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("alzate-laterali", sets=4, reps=12, rest=45),
                        enrich_gym_exercise("curl-bilanciere", sets=4, reps=10, rest=45),
                        enrich_gym_exercise("french-press", sets=4, reps=10, rest=45),
                        enrich_gym_exercise("croci-inverse", sets=3, reps=12, rest=30),
                        enrich_gym_exercise("concentration-curl", sets=3, reps=10, rest=30)
                    ]
                },
                {
                    "id": "gym_f_adv_5",
                    "name_it": "Elite Donna - Giorno 5 (Glute Builder)",
                    "name_en": "Elite Women - Day 5 (Glute Builder)",
                    "description_it": "Costruisci i glutei perfetti con hip thrust e stacchi.",
                    "description_en": "Build perfect glutes with hip thrusts and deadlifts.",
                    "duration": 50,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("stacco-da-terra", sets=4, reps=6, rest=120),
                        enrich_gym_exercise("hip-thrust-bilanciere", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("squat-goblet", sets=4, reps=12, rest=60),
                        enrich_gym_exercise("step-up-manubri", sets=3, reps=10, rest=45),
                        enrich_gym_exercise("good-morning", sets=3, reps=12, rest=45)
                    ]
                },
                {
                    "id": "gym_f_adv_6",
                    "name_it": "Elite Donna - Giorno 6 (Full Body Power)",
                    "name_en": "Elite Women - Day 6 (Full Body Power)",
                    "description_it": "Total body ad alta intensità per massimizzare la definizione.",
                    "description_en": "High intensity full body to maximize definition.",
                    "duration": 55,
                    "difficulty": "advanced",
                    "category": "strength",
                    "mode": "gym",
                    "premium": True,
                    "exercises": [
                        enrich_gym_exercise("squat-bilanciere", sets=4, reps=6, rest=120),
                        enrich_gym_exercise("panca-inclinata-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("rematore-manubrio", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("shoulder-press-manubri", sets=4, reps=10, rest=60),
                        enrich_gym_exercise("curl-martello", sets=3, reps=12, rest=45),
                        enrich_gym_exercise("pushdown-tricipiti", sets=3, reps=12, rest=30)
                    ]
                },
                {
                    "id": "gym_f_adv_7",
                    "name_it": "Elite Donna - Giorno 7 (Recupero)",
                    "name_en": "Elite Women - Day 7 (Recovery)",
                    "description_it": "Recupero attivo e stretching per favorire la rigenerazione muscolare.",
                    "description_en": "Active recovery and stretching for muscle regeneration.",
                    "duration": 40,
                    "difficulty": "advanced",
                    "category": "recovery",
                    "mode": "gym",
                    "premium": False,
                    "exercises": [
                        enrich_gym_exercise("pullover-manubrio", sets=3, reps=12, rest=30),
                        enrich_gym_exercise("face-pull", sets=3, reps=15, rest=30),
                        {"name_it": "Stretching completo", "name_en": "Full stretching", "sets": 1, "duration": 900, "rest": 0}
                    ]
                }
            ]
    
    return workouts

def get_workouts_for_user(gender: str, level: str, goal: str, workout_mode: str = "home") -> List[Dict]:
    """Generate workout programs based on user profile and workout mode (home/gym)"""
    
    # Base exercises by category
    warmup_exercises = {
        "it": [
            {"name": "Rotazione spalle", "duration": 30, "type": "warmup"},
            {"name": "Rotazione fianchi", "duration": 30, "type": "warmup"},
            {"name": "Jumping jacks leggeri", "duration": 45, "type": "warmup"},
            {"name": "Marcia sul posto", "duration": 45, "type": "warmup"}
        ],
        "en": [
            {"name": "Shoulder rotations", "duration": 30, "type": "warmup"},
            {"name": "Hip rotations", "duration": 30, "type": "warmup"},
            {"name": "Light jumping jacks", "duration": 45, "type": "warmup"},
            {"name": "Marching in place", "duration": 45, "type": "warmup"}
        ]
    }
    
    cooldown_exercises = {
        "it": [
            {"name": "Stretching quadricipiti", "duration": 30, "type": "cooldown"},
            {"name": "Stretching femorali", "duration": 30, "type": "cooldown"},
            {"name": "Stretching spalle", "duration": 30, "type": "cooldown"},
            {"name": "Respirazione profonda", "duration": 60, "type": "cooldown"}
        ],
        "en": [
            {"name": "Quad stretch", "duration": 30, "type": "cooldown"},
            {"name": "Hamstring stretch", "duration": 30, "type": "cooldown"},
            {"name": "Shoulder stretch", "duration": 30, "type": "cooldown"},
            {"name": "Deep breathing", "duration": 60, "type": "cooldown"}
        ]
    }
    
    # Workouts by gender, level, and mode
    workouts = []
    
    # ==== MODALITÀ PALESTRA (GYM) ====
    if workout_mode == "gym":
        return get_gym_workouts(gender, level, goal)
    
    # ==== MODALITÀ CASA (HOME) - Default ====
    if gender == "male":
        if level == "beginner":
            workouts = [
                {
                    "id": "m_beg_1",
                    "name_it": "Forza Base - Giorno 1",
                    "name_en": "Basic Strength - Day 1",
                    "description_it": "Focus su forza base e massa magra",
                    "description_en": "Focus on basic strength and lean mass",
                    "duration": 20,
                    "difficulty": "beginner",
                    "category": "strength",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Push-up modificati", "name_en": "Modified push-ups", "sets": 3, "reps": 10, "rest": 45},
                        {"name_it": "Squat a corpo libero", "name_en": "Bodyweight squats", "sets": 3, "reps": 12, "rest": 45},
                        {"name_it": "Plank", "name_en": "Plank", "sets": 3, "duration": 20, "rest": 30},
                        {"name_it": "Affondi alternati", "name_en": "Alternating lunges", "sets": 3, "reps": 10, "rest": 45}
                    ]
                },
                {
                    "id": "m_beg_2",
                    "name_it": "Forza Base - Giorno 2",
                    "name_en": "Basic Strength - Day 2",
                    "description_it": "Lavoro su upper body e core",
                    "description_en": "Upper body and core work",
                    "duration": 25,
                    "difficulty": "beginner",
                    "category": "strength",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Dips su sedia", "name_en": "Chair dips", "sets": 3, "reps": 8, "rest": 45},
                        {"name_it": "Mountain climbers", "name_en": "Mountain climbers", "sets": 3, "duration": 30, "rest": 45},
                        {"name_it": "Crunch", "name_en": "Crunches", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Superman", "name_en": "Superman", "sets": 3, "reps": 10, "rest": 30}
                    ]
                },
                {
                    "id": "m_beg_3",
                    "name_it": "Forza Base - Giorno 3",
                    "name_en": "Basic Strength - Day 3",
                    "description_it": "Focus su gambe e glutei",
                    "description_en": "Focus on legs and glutes",
                    "duration": 25,
                    "difficulty": "beginner",
                    "category": "strength",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Squat leggero", "name_en": "Light squats", "sets": 3, "reps": 15, "rest": 45},
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Affondi laterali", "name_en": "Side lunges", "sets": 3, "reps": 10, "rest": 45},
                        {"name_it": "Clamshell", "name_en": "Clamshell", "sets": 3, "reps": 12, "rest": 30}
                    ]
                },
                {
                    "id": "m_beg_4",
                    "name_it": "Forza Base - Giorno 4",
                    "name_en": "Basic Strength - Day 4",
                    "description_it": "Allenamento full body leggero",
                    "description_en": "Light full body workout",
                    "duration": 20,
                    "difficulty": "beginner",
                    "category": "strength",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Jumping jacks", "name_en": "Jumping jacks", "sets": 3, "duration": 30, "rest": 30},
                        {"name_it": "Push-up modificati", "name_en": "Modified push-ups", "sets": 3, "reps": 8, "rest": 45},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 10, "rest": 30},
                        {"name_it": "Squat a corpo libero", "name_en": "Bodyweight squats", "sets": 3, "reps": 10, "rest": 45}
                    ]
                },
                {
                    "id": "m_beg_5",
                    "name_it": "Forza Base - Giorno 5",
                    "name_en": "Basic Strength - Day 5",
                    "description_it": "Core e stabilità",
                    "description_en": "Core and stability",
                    "duration": 20,
                    "difficulty": "beginner",
                    "category": "core",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Plank", "name_en": "Plank", "sets": 3, "duration": 25, "rest": 30},
                        {"name_it": "Crunch bicicletta", "name_en": "Bicycle crunches", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Superman", "name_en": "Superman", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Plank laterale", "name_en": "Side plank", "sets": 2, "duration": 20, "rest": 30}
                    ]
                },
                {
                    "id": "m_beg_6",
                    "name_it": "Forza Base - Giorno 6",
                    "name_en": "Basic Strength - Day 6",
                    "description_it": "Cardio leggero e tonificazione",
                    "description_en": "Light cardio and toning",
                    "duration": 25,
                    "difficulty": "beginner",
                    "category": "cardio",
                    "premium": False,
                    "exercises": [
                        {"name_it": "High knees", "name_en": "High knees", "sets": 3, "duration": 30, "rest": 30},
                        {"name_it": "Burpees modificati", "name_en": "Modified burpees", "sets": 3, "reps": 8, "rest": 45},
                        {"name_it": "Mountain climbers", "name_en": "Mountain climbers", "sets": 3, "duration": 25, "rest": 30},
                        {"name_it": "Squat a corpo libero", "name_en": "Bodyweight squats", "sets": 3, "reps": 12, "rest": 45}
                    ]
                },
                {
                    "id": "m_beg_7",
                    "name_it": "Forza Base - Giorno 7",
                    "name_en": "Basic Strength - Day 7",
                    "description_it": "Recupero attivo e stretching dinamico",
                    "description_en": "Active recovery and dynamic stretching",
                    "duration": 15,
                    "difficulty": "beginner",
                    "category": "recovery",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Donkey kick", "name_en": "Donkey kicks", "sets": 2, "reps": 12, "rest": 30},
                        {"name_it": "Fire hydrant", "name_en": "Fire hydrants", "sets": 2, "reps": 12, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 2, "reps": 10, "rest": 30},
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 2, "reps": 15, "rest": 30}
                    ]
                }
            ]
        elif level == "intermediate":
            workouts = [
                {
                    "id": "m_int_1",
                    "name_it": "Upper Body Power - Giorno 1",
                    "name_en": "Upper Body Power - Day 1",
                    "description_it": "Split upper/lower con pesi e corpo libero",
                    "description_en": "Upper/lower split with weights and bodyweight",
                    "duration": 40,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Push-up", "name_en": "Push-ups", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Pike push-up", "name_en": "Pike push-ups", "sets": 3, "reps": 10, "rest": 60},
                        {"name_it": "Dips", "name_en": "Dips", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Plank laterale", "name_en": "Side plank", "sets": 3, "duration": 30, "rest": 30},
                        {"name_it": "Burpees", "name_en": "Burpees", "sets": 3, "reps": 10, "rest": 60}
                    ]
                },
                {
                    "id": "m_int_2",
                    "name_it": "Lower Body Power - Giorno 2",
                    "name_en": "Lower Body Power - Day 2",
                    "description_it": "Lavoro intenso su gambe e glutei",
                    "description_en": "Intense leg and glute work",
                    "duration": 40,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 4, "reps": 12, "rest": 60},
                        {"name_it": "Affondi bulgari", "name_en": "Bulgarian lunges", "sets": 3, "reps": 10, "rest": 45},
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 4, "reps": 15, "rest": 30},
                        {"name_it": "Box step-up", "name_en": "Box step-ups", "sets": 3, "reps": 12, "rest": 45}
                    ]
                },
                {
                    "id": "m_int_3",
                    "name_it": "Core Blast - Giorno 3",
                    "name_en": "Core Blast - Day 3",
                    "description_it": "Allenamento intenso per addominali e core",
                    "description_en": "Intense abs and core workout",
                    "duration": 35,
                    "difficulty": "intermediate",
                    "category": "core",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Plank", "name_en": "Plank", "sets": 4, "duration": 45, "rest": 30},
                        {"name_it": "Crunch bicicletta", "name_en": "Bicycle crunches", "sets": 4, "reps": 20, "rest": 30},
                        {"name_it": "Plank con rotazione", "name_en": "Plank with rotation", "sets": 3, "reps": 12, "rest": 45},
                        {"name_it": "Mountain climbers", "name_en": "Mountain climbers", "sets": 4, "duration": 40, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 15, "rest": 30}
                    ]
                },
                {
                    "id": "m_int_4",
                    "name_it": "Full Body HIIT - Giorno 4",
                    "name_en": "Full Body HIIT - Day 4",
                    "description_it": "Circuito ad alta intensità total body",
                    "description_en": "High intensity full body circuit",
                    "duration": 30,
                    "difficulty": "intermediate",
                    "category": "hiit",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Burpees", "name_en": "Burpees", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Push-up", "name_en": "Push-ups", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "High knees", "name_en": "High knees", "sets": 4, "duration": 30, "rest": 30}
                    ]
                },
                {
                    "id": "m_int_5",
                    "name_it": "Push Day - Giorno 5",
                    "name_en": "Push Day - Day 5",
                    "description_it": "Focus su petto, spalle e tricipiti",
                    "description_en": "Focus on chest, shoulders and triceps",
                    "duration": 40,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Push-up", "name_en": "Push-ups", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Pike push-up", "name_en": "Pike push-ups", "sets": 4, "reps": 10, "rest": 60},
                        {"name_it": "Dips su sedia", "name_en": "Chair dips", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Plank up-down", "name_en": "Plank up-downs", "sets": 3, "reps": 10, "rest": 45},
                        {"name_it": "Push-up esplosivi", "name_en": "Explosive push-ups", "sets": 3, "reps": 8, "rest": 60}
                    ]
                },
                {
                    "id": "m_int_6",
                    "name_it": "Pull & Posterior - Giorno 6",
                    "name_en": "Pull & Posterior - Day 6",
                    "description_it": "Schiena, bicipiti e catena posteriore",
                    "description_en": "Back, biceps and posterior chain",
                    "duration": 40,
                    "difficulty": "intermediate",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Superman", "name_en": "Superman", "sets": 4, "reps": 15, "rest": 30},
                        {"name_it": "Hip thrust", "name_en": "Hip thrust", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Single leg deadlift", "name_en": "Single leg deadlift", "sets": 3, "reps": 10, "rest": 45},
                        {"name_it": "Glute bridge", "name_en": "Glute bridge", "sets": 4, "reps": 15, "rest": 30},
                        {"name_it": "Plank laterale", "name_en": "Side plank", "sets": 3, "duration": 30, "rest": 30}
                    ]
                },
                {
                    "id": "m_int_7",
                    "name_it": "Recupero Attivo - Giorno 7",
                    "name_en": "Active Recovery - Day 7",
                    "description_it": "Mobilità e recupero muscolare",
                    "description_en": "Mobility and muscle recovery",
                    "duration": 25,
                    "difficulty": "intermediate",
                    "category": "recovery",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Donkey kick", "name_en": "Donkey kicks", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Fire hydrant", "name_en": "Fire hydrants", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Clamshell", "name_en": "Clamshell", "sets": 3, "reps": 12, "rest": 30}
                    ]
                }
            ]
        else:  # advanced
            workouts = [
                {
                    "id": "m_adv_1",
                    "name_it": "Ipertrofia Totale - Giorno 1",
                    "name_en": "Total Hypertrophy - Day 1",
                    "description_it": "Allenamento avanzato per ipertrofia + HIIT",
                    "description_en": "Advanced hypertrophy training + HIIT",
                    "duration": 50,
                    "difficulty": "advanced",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Push-up esplosivi", "name_en": "Explosive push-ups", "sets": 5, "reps": 15, "rest": 45},
                        {"name_it": "Pistol squat", "name_en": "Pistol squats", "sets": 4, "reps": 8, "rest": 60},
                        {"name_it": "Muscle-up modificati", "name_en": "Modified muscle-ups", "sets": 4, "reps": 6, "rest": 90},
                        {"name_it": "Plank dinamico", "name_en": "Dynamic plank", "sets": 4, "duration": 45, "rest": 30},
                        {"name_it": "Burpee box jump", "name_en": "Burpee box jumps", "sets": 4, "reps": 10, "rest": 60}
                    ]
                },
                {
                    "id": "m_adv_2",
                    "name_it": "HIIT Infernale - Giorno 2",
                    "name_en": "Infernal HIIT - Day 2",
                    "description_it": "Circuito ad alta intensità",
                    "description_en": "High intensity circuit",
                    "duration": 45,
                    "difficulty": "advanced",
                    "category": "hiit",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Sprint sul posto", "name_en": "Sprints in place", "sets": 5, "duration": 30, "rest": 15},
                        {"name_it": "Burpees completi", "name_en": "Full burpees", "sets": 5, "reps": 15, "rest": 20},
                        {"name_it": "Mountain climbers", "name_en": "Mountain climbers", "sets": 5, "duration": 45, "rest": 15},
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 5, "reps": 20, "rest": 20}
                    ]
                },
                {
                    "id": "m_adv_3",
                    "name_it": "Potenza Esplosiva - Giorno 3",
                    "name_en": "Explosive Power - Day 3",
                    "description_it": "Movimenti esplosivi per potenza massima",
                    "description_en": "Explosive movements for maximum power",
                    "duration": 45,
                    "difficulty": "advanced",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Affondi saltati", "name_en": "Jump lunges", "sets": 5, "reps": 12, "rest": 45},
                        {"name_it": "Push-up esplosivi", "name_en": "Explosive push-ups", "sets": 5, "reps": 12, "rest": 45},
                        {"name_it": "Frog jump", "name_en": "Frog jumps", "sets": 4, "reps": 10, "rest": 60},
                        {"name_it": "Hip thrust esplosivo", "name_en": "Explosive hip thrust", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Burpee box jump", "name_en": "Burpee box jumps", "sets": 4, "reps": 8, "rest": 60}
                    ]
                },
                {
                    "id": "m_adv_4",
                    "name_it": "Upper Body Beast - Giorno 4",
                    "name_en": "Upper Body Beast - Day 4",
                    "description_it": "Push e pull avanzati per upper body",
                    "description_en": "Advanced push and pull for upper body",
                    "duration": 50,
                    "difficulty": "advanced",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Push-up", "name_en": "Push-ups", "sets": 5, "reps": 20, "rest": 45},
                        {"name_it": "Pike push-up", "name_en": "Pike push-ups", "sets": 5, "reps": 12, "rest": 60},
                        {"name_it": "Dips", "name_en": "Dips", "sets": 5, "reps": 15, "rest": 45},
                        {"name_it": "Plank up-down", "name_en": "Plank up-downs", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Superman", "name_en": "Superman", "sets": 4, "reps": 20, "rest": 30}
                    ]
                },
                {
                    "id": "m_adv_5",
                    "name_it": "Lower Body Destroyer - Giorno 5",
                    "name_en": "Lower Body Destroyer - Day 5",
                    "description_it": "Gambe e glutei al massimo",
                    "description_en": "Legs and glutes at maximum",
                    "duration": 50,
                    "difficulty": "advanced",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 5, "reps": 15, "rest": 45},
                        {"name_it": "Pistol squat", "name_en": "Pistol squats", "sets": 4, "reps": 8, "rest": 60},
                        {"name_it": "Affondi bulgari", "name_en": "Bulgarian lunges", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Sumo squat pulse", "name_en": "Sumo squat pulses", "sets": 4, "duration": 30, "rest": 30},
                        {"name_it": "Single leg deadlift", "name_en": "Single leg deadlifts", "sets": 4, "reps": 10, "rest": 45}
                    ]
                },
                {
                    "id": "m_adv_6",
                    "name_it": "Core Inferno - Giorno 6",
                    "name_en": "Core Inferno - Day 6",
                    "description_it": "Allenamento core estremo",
                    "description_en": "Extreme core workout",
                    "duration": 40,
                    "difficulty": "advanced",
                    "category": "core",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Plank", "name_en": "Plank", "sets": 4, "duration": 60, "rest": 30},
                        {"name_it": "Plank con rotazione", "name_en": "Plank with rotation", "sets": 4, "reps": 15, "rest": 30},
                        {"name_it": "Mountain climbers", "name_en": "Mountain climbers", "sets": 5, "duration": 45, "rest": 20},
                        {"name_it": "Crunch bicicletta", "name_en": "Bicycle crunches", "sets": 4, "reps": 25, "rest": 30},
                        {"name_it": "Plank laterale", "name_en": "Side plank", "sets": 3, "duration": 45, "rest": 30}
                    ]
                },
                {
                    "id": "m_adv_7",
                    "name_it": "Recupero Attivo - Giorno 7",
                    "name_en": "Active Recovery - Day 7",
                    "description_it": "Mobilità e deload",
                    "description_en": "Mobility and deload",
                    "duration": 30,
                    "difficulty": "advanced",
                    "category": "recovery",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Donkey kick", "name_en": "Donkey kicks", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Fire hydrant", "name_en": "Fire hydrants", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 3, "reps": 20, "rest": 30}
                    ]
                }
            ]
    else:  # female
        if level == "beginner":
            workouts = [
                {
                    "id": "f_beg_1",
                    "name_it": "Tonificazione Dolce - Giorno 1",
                    "name_en": "Gentle Toning - Day 1",
                    "description_it": "Tonificazione glutei e core a basso impatto",
                    "description_en": "Low impact glute and core toning",
                    "duration": 20,
                    "difficulty": "beginner",
                    "category": "toning",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Squat leggero", "name_en": "Light squats", "sets": 3, "reps": 12, "rest": 45},
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Crunch bicicletta", "name_en": "Bicycle crunches", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Affondi laterali", "name_en": "Side lunges", "sets": 3, "reps": 10, "rest": 45}
                    ]
                },
                {
                    "id": "f_beg_2",
                    "name_it": "Core & Glutei Base - Giorno 2",
                    "name_en": "Basic Core & Glutes - Day 2",
                    "description_it": "Lavoro mirato su addome e glutei",
                    "description_en": "Targeted work on abs and glutes",
                    "duration": 25,
                    "difficulty": "beginner",
                    "category": "toning",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Clamshell", "name_en": "Clamshells", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Donkey kick", "name_en": "Donkey kicks", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Plank", "name_en": "Plank", "sets": 3, "duration": 20, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 10, "rest": 30}
                    ]
                },
                {
                    "id": "f_beg_3",
                    "name_it": "Gambe Snelle - Giorno 3",
                    "name_en": "Slim Legs - Day 3",
                    "description_it": "Focus su gambe e interno coscia",
                    "description_en": "Focus on legs and inner thighs",
                    "duration": 25,
                    "difficulty": "beginner",
                    "category": "toning",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Sumo squat", "name_en": "Sumo squats", "sets": 3, "reps": 12, "rest": 40},
                        {"name_it": "Affondi alternati", "name_en": "Alternating lunges", "sets": 3, "reps": 10, "rest": 45},
                        {"name_it": "Fire hydrant", "name_en": "Fire hydrants", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Glute bridge", "name_en": "Glute bridge", "sets": 3, "reps": 15, "rest": 30}
                    ]
                },
                {
                    "id": "f_beg_4",
                    "name_it": "Addome Piatto - Giorno 4",
                    "name_en": "Flat Abs - Day 4",
                    "description_it": "Allenamento core per addome tonico",
                    "description_en": "Core workout for toned abs",
                    "duration": 20,
                    "difficulty": "beginner",
                    "category": "core",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Crunch", "name_en": "Crunches", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Plank", "name_en": "Plank", "sets": 3, "duration": 25, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Superman", "name_en": "Superman", "sets": 3, "reps": 10, "rest": 30}
                    ]
                },
                {
                    "id": "f_beg_5",
                    "name_it": "Braccia Toniche - Giorno 5",
                    "name_en": "Toned Arms - Day 5",
                    "description_it": "Tonificazione braccia e spalle",
                    "description_en": "Arms and shoulders toning",
                    "duration": 20,
                    "difficulty": "beginner",
                    "category": "toning",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Push-up modificati", "name_en": "Modified push-ups", "sets": 3, "reps": 8, "rest": 45},
                        {"name_it": "Dips su sedia", "name_en": "Chair dips", "sets": 3, "reps": 8, "rest": 45},
                        {"name_it": "Plank laterale", "name_en": "Side plank", "sets": 2, "duration": 15, "rest": 30},
                        {"name_it": "Plank up-down", "name_en": "Plank up-downs", "sets": 3, "reps": 8, "rest": 45}
                    ]
                },
                {
                    "id": "f_beg_6",
                    "name_it": "Cardio Leggero - Giorno 6",
                    "name_en": "Light Cardio - Day 6",
                    "description_it": "Cardio a basso impatto per bruciare calorie",
                    "description_en": "Low impact cardio to burn calories",
                    "duration": 25,
                    "difficulty": "beginner",
                    "category": "cardio",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Jumping jack", "name_en": "Jumping jacks", "sets": 3, "duration": 30, "rest": 30},
                        {"name_it": "High knee", "name_en": "High knees", "sets": 3, "duration": 25, "rest": 30},
                        {"name_it": "Mountain climber", "name_en": "Mountain climbers", "sets": 3, "duration": 20, "rest": 30},
                        {"name_it": "Squat", "name_en": "Squats", "sets": 3, "reps": 12, "rest": 40}
                    ]
                },
                {
                    "id": "f_beg_7",
                    "name_it": "Recupero Attivo - Giorno 7",
                    "name_en": "Active Recovery - Day 7",
                    "description_it": "Stretching e mobilità",
                    "description_en": "Stretching and mobility",
                    "duration": 15,
                    "difficulty": "beginner",
                    "category": "recovery",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 2, "reps": 15, "rest": 30},
                        {"name_it": "Clamshell", "name_en": "Clamshell", "sets": 2, "reps": 12, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 2, "reps": 10, "rest": 30},
                        {"name_it": "Superman", "name_en": "Superman", "sets": 2, "reps": 10, "rest": 30}
                    ]
                }
            ]
        elif level == "intermediate":
            workouts = [
                {
                    "id": "f_int_1",
                    "name_it": "Glutei & Gambe Circuit - Giorno 1",
                    "name_en": "Glutes & Legs Circuit - Day 1",
                    "description_it": "Circuit training gambe e glutei + cardio",
                    "description_en": "Leg and glute circuit training + cardio",
                    "duration": 35,
                    "difficulty": "intermediate",
                    "category": "circuit",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Sumo squat", "name_en": "Sumo squats", "sets": 4, "reps": 15, "rest": 30},
                        {"name_it": "Hip thrust", "name_en": "Hip thrusts", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Box step-up", "name_en": "Step-ups", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Fire hydrant", "name_en": "Fire hydrants", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Jumping jack", "name_en": "Jumping jacks", "sets": 3, "duration": 45, "rest": 20}
                    ]
                },
                {
                    "id": "f_int_2",
                    "name_it": "Total Body Burn - Giorno 2",
                    "name_en": "Total Body Burn - Day 2",
                    "description_it": "Allenamento completo con focus cardio",
                    "description_en": "Complete workout with cardio focus",
                    "duration": 40,
                    "difficulty": "intermediate",
                    "category": "circuit",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Burpees modificati", "name_en": "Modified burpees", "sets": 4, "reps": 10, "rest": 45},
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Plank up-down", "name_en": "Plank up-downs", "sets": 3, "reps": 10, "rest": 30},
                        {"name_it": "Mountain climber", "name_en": "Mountain climbers", "sets": 3, "duration": 30, "rest": 30}
                    ]
                },
                {
                    "id": "f_int_3",
                    "name_it": "Core Sculpt - Giorno 3",
                    "name_en": "Core Sculpt - Day 3",
                    "description_it": "Scolpisci gli addominali",
                    "description_en": "Sculpt your abs",
                    "duration": 30,
                    "difficulty": "intermediate",
                    "category": "core",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Plank", "name_en": "Plank", "sets": 4, "duration": 40, "rest": 30},
                        {"name_it": "Crunch bicicletta", "name_en": "Bicycle crunches", "sets": 4, "reps": 20, "rest": 30},
                        {"name_it": "Plank con rotazione", "name_en": "Plank with rotation", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 15, "rest": 30}
                    ]
                },
                {
                    "id": "f_int_4",
                    "name_it": "Booty Builder - Giorno 4",
                    "name_en": "Booty Builder - Day 4",
                    "description_it": "Focus intenso sui glutei",
                    "description_en": "Intense glute focus",
                    "duration": 35,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Hip thrust", "name_en": "Hip thrusts", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Affondi bulgari", "name_en": "Bulgarian lunges", "sets": 3, "reps": 10, "rest": 45},
                        {"name_it": "Donkey kick", "name_en": "Donkey kicks", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Sumo squat pulse", "name_en": "Sumo squat pulses", "sets": 3, "duration": 30, "rest": 30},
                        {"name_it": "Clamshell", "name_en": "Clamshell", "sets": 3, "reps": 15, "rest": 30}
                    ]
                },
                {
                    "id": "f_int_5",
                    "name_it": "Upper Body Tone - Giorno 5",
                    "name_en": "Upper Body Tone - Day 5",
                    "description_it": "Tonifica braccia e schiena",
                    "description_en": "Tone arms and back",
                    "duration": 30,
                    "difficulty": "intermediate",
                    "category": "toning",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Push-up", "name_en": "Push-ups", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Dips su sedia", "name_en": "Chair dips", "sets": 4, "reps": 10, "rest": 45},
                        {"name_it": "Pike push-up", "name_en": "Pike push-ups", "sets": 3, "reps": 8, "rest": 45},
                        {"name_it": "Superman", "name_en": "Superman", "sets": 3, "reps": 15, "rest": 30}
                    ]
                },
                {
                    "id": "f_int_6",
                    "name_it": "HIIT Express - Giorno 6",
                    "name_en": "HIIT Express - Day 6",
                    "description_it": "Cardio intenso brucia grassi",
                    "description_en": "Intense fat burning cardio",
                    "duration": 25,
                    "difficulty": "intermediate",
                    "category": "hiit",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Burpees", "name_en": "Burpees", "sets": 4, "reps": 10, "rest": 30},
                        {"name_it": "High knee", "name_en": "High knees", "sets": 4, "duration": 30, "rest": 20},
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 4, "reps": 12, "rest": 30},
                        {"name_it": "Mountain climber", "name_en": "Mountain climbers", "sets": 4, "duration": 30, "rest": 20}
                    ]
                },
                {
                    "id": "f_int_7",
                    "name_it": "Recupero Attivo - Giorno 7",
                    "name_en": "Active Recovery - Day 7",
                    "description_it": "Mobilità e stretching",
                    "description_en": "Mobility and stretching",
                    "duration": 20,
                    "difficulty": "intermediate",
                    "category": "recovery",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Fire hydrant", "name_en": "Fire hydrants", "sets": 3, "reps": 12, "rest": 30},
                        {"name_it": "Clamshell", "name_en": "Clamshell", "sets": 3, "reps": 12, "rest": 30}
                    ]
                }
            ]
        else:  # advanced
            workouts = [
                {
                    "id": "f_adv_1",
                    "name_it": "Shaping Intenso - Giorno 1",
                    "name_en": "Intense Shaping - Day 1",
                    "description_it": "Shaping + HIIT + forza per risultati visibili",
                    "description_en": "Shaping + HIIT + strength for visible results",
                    "duration": 45,
                    "difficulty": "advanced",
                    "category": "shaping",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 5, "reps": 15, "rest": 30},
                        {"name_it": "Hip thrust esplosivo", "name_en": "Explosive hip thrusts", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Affondi saltati", "name_en": "Jumping lunges", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Plank con rotazione", "name_en": "Plank with rotation", "sets": 4, "duration": 30, "rest": 20},
                        {"name_it": "Burpees completi", "name_en": "Full burpees", "sets": 4, "reps": 12, "rest": 45}
                    ]
                },
                {
                    "id": "f_adv_2",
                    "name_it": "HIIT Booty Blast - Giorno 2",
                    "name_en": "HIIT Booty Blast - Day 2",
                    "description_it": "Circuito esplosivo per glutei definiti",
                    "description_en": "Explosive circuit for defined glutes",
                    "duration": 40,
                    "difficulty": "advanced",
                    "category": "hiit",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Frog jump", "name_en": "Frog jumps", "sets": 5, "reps": 15, "rest": 20},
                        {"name_it": "Sumo squat pulse", "name_en": "Sumo squat pulses", "sets": 5, "duration": 30, "rest": 15},
                        {"name_it": "Single leg deadlift", "name_en": "Single leg deadlifts", "sets": 4, "reps": 10, "rest": 30},
                        {"name_it": "High knee", "name_en": "High knees", "sets": 4, "duration": 45, "rest": 15}
                    ]
                },
                {
                    "id": "f_adv_3",
                    "name_it": "Legs of Steel - Giorno 3",
                    "name_en": "Legs of Steel - Day 3",
                    "description_it": "Gambe potenti e definite",
                    "description_en": "Powerful and defined legs",
                    "duration": 45,
                    "difficulty": "advanced",
                    "category": "strength",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Pistol squat", "name_en": "Pistol squats", "sets": 4, "reps": 6, "rest": 60},
                        {"name_it": "Affondi bulgari", "name_en": "Bulgarian lunges", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Box step-up", "name_en": "Box step-ups", "sets": 4, "reps": 15, "rest": 45},
                        {"name_it": "Sumo squat", "name_en": "Sumo squats", "sets": 4, "reps": 15, "rest": 40},
                        {"name_it": "Glute bridge", "name_en": "Glute bridge", "sets": 4, "reps": 20, "rest": 30}
                    ]
                },
                {
                    "id": "f_adv_4",
                    "name_it": "Core Power - Giorno 4",
                    "name_en": "Core Power - Day 4",
                    "description_it": "Core forte e definito",
                    "description_en": "Strong and defined core",
                    "duration": 35,
                    "difficulty": "advanced",
                    "category": "core",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Plank", "name_en": "Plank", "sets": 4, "duration": 60, "rest": 30},
                        {"name_it": "Plank laterale", "name_en": "Side plank", "sets": 3, "duration": 45, "rest": 30},
                        {"name_it": "Mountain climber", "name_en": "Mountain climbers", "sets": 5, "duration": 40, "rest": 20},
                        {"name_it": "Crunch bicicletta", "name_en": "Bicycle crunches", "sets": 4, "reps": 25, "rest": 30},
                        {"name_it": "Plank dinamico", "name_en": "Dynamic plank", "sets": 3, "duration": 30, "rest": 30}
                    ]
                },
                {
                    "id": "f_adv_5",
                    "name_it": "Total Body Burn - Giorno 5",
                    "name_en": "Total Body Burn - Day 5",
                    "description_it": "Allenamento completo ad alta intensità",
                    "description_en": "Complete high intensity workout",
                    "duration": 45,
                    "difficulty": "advanced",
                    "category": "hiit",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Burpees completi", "name_en": "Full burpees", "sets": 5, "reps": 12, "rest": 30},
                        {"name_it": "Push-up esplosivi", "name_en": "Explosive push-ups", "sets": 4, "reps": 10, "rest": 45},
                        {"name_it": "Squat jump", "name_en": "Jump squats", "sets": 5, "reps": 15, "rest": 30},
                        {"name_it": "Dips", "name_en": "Dips", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Sprint sul posto", "name_en": "Sprints in place", "sets": 4, "duration": 30, "rest": 20}
                    ]
                },
                {
                    "id": "f_adv_6",
                    "name_it": "Glute Goddess - Giorno 6",
                    "name_en": "Glute Goddess - Day 6",
                    "description_it": "Focus totale sui glutei",
                    "description_en": "Total glute focus",
                    "duration": 40,
                    "difficulty": "advanced",
                    "category": "toning",
                    "premium": True,
                    "exercises": [
                        {"name_it": "Hip thrust esplosivo", "name_en": "Explosive hip thrusts", "sets": 5, "reps": 15, "rest": 40},
                        {"name_it": "Donkey kick", "name_en": "Donkey kicks", "sets": 4, "reps": 20, "rest": 30},
                        {"name_it": "Fire hydrant", "name_en": "Fire hydrants", "sets": 4, "reps": 20, "rest": 30},
                        {"name_it": "Frog jump", "name_en": "Frog jumps", "sets": 4, "reps": 12, "rest": 45},
                        {"name_it": "Clamshell", "name_en": "Clamshell", "sets": 4, "reps": 20, "rest": 30}
                    ]
                },
                {
                    "id": "f_adv_7",
                    "name_it": "Recupero Attivo - Giorno 7",
                    "name_en": "Active Recovery - Day 7",
                    "description_it": "Mobilità e recupero",
                    "description_en": "Mobility and recovery",
                    "duration": 25,
                    "difficulty": "advanced",
                    "category": "recovery",
                    "premium": False,
                    "exercises": [
                        {"name_it": "Ponte glutei", "name_en": "Glute bridge", "sets": 3, "reps": 20, "rest": 30},
                        {"name_it": "Dead bug", "name_en": "Dead bug", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Superman", "name_en": "Superman", "sets": 3, "reps": 15, "rest": 30},
                        {"name_it": "Clamshell", "name_en": "Clamshell", "sets": 3, "reps": 15, "rest": 30}
                    ]
                }
            ]
    
    return workouts

@api_router.get("/workouts/today")
async def get_today_workout(user: UserProfile = Depends(require_auth)):
    """Get today's recommended workout based on training day progression"""
    gender = user.gender or "male"
    level = user.calculated_level or user.fitness_level or "beginner"
    goal = user.goal or "general_fitness"
    workout_mode = getattr(user, 'workout_mode', 'home') or 'home'
    
    # Get all workouts for user
    workouts = get_workouts_for_user(gender, level, goal, workout_mode)
    
    if not workouts:
        return {"workout": None, "message": "No workouts available"}
    
    # Get current training day (1-based index)
    current_day = getattr(user, 'current_training_day', 1) or 1
    last_training_date = getattr(user, 'last_training_date', None)
    
    # Check if user trained today already
    today = datetime.now(timezone.utc).date()
    trained_today = False
    if last_training_date:
        if hasattr(last_training_date, 'date'):
            trained_today = last_training_date.date() == today
        elif isinstance(last_training_date, str):
            trained_today = datetime.fromisoformat(last_training_date).date() == today
    
    # Calculate workout index (cycle through available workouts)
    workout_index = (current_day - 1) % len(workouts)
    today_workout = workouts[workout_index]
    
    # Enrich exercises
    if "exercises" in today_workout:
        today_workout["exercises"] = [enrich_exercise(ex) for ex in today_workout["exercises"]]
    
    # Check trial and subscription status
    trial_status = get_trial_status(user)
    has_full_access = trial_status["has_full_access"]
    
    if not has_full_access and today_workout.get("premium"):
        today_workout["locked"] = True
    
    # Add day_number to workout for frontend
    today_workout["day_number"] = current_day
    today_workout["is_completed_today"] = trained_today
    
    return {
        "workout": today_workout,
        "current_day": current_day,
        "day_number": current_day,
        "total_workouts": len(workouts),
        "trained_today": trained_today,
        "is_completed_today": trained_today,
        "level": level,
        "next_day": (current_day % len(workouts)) + 1,
        # Return the workout directly for the frontend
        **today_workout
    }

@api_router.get("/workouts/history")
async def get_workout_history(user: UserProfile = Depends(require_auth)):
    """Get user's completed workout history for archive view"""
    try:
        # Get completed workouts from workout_progress collection
        history = await db.workout_progress.find(
            {"user_id": user.user_id},
            {"_id": 0}
        ).sort("completed_at", -1).limit(50).to_list(50)
        
        # Format history for frontend
        formatted_history = []
        for item in history:
            formatted_history.append({
                "id": str(item.get("_id", "")),
                "workout_id": item.get("workout_id", ""),
                "workout_name_it": item.get("workout_name", "Allenamento"),
                "workout_name_en": item.get("workout_name", "Workout"),
                "completed_at": item.get("completed_at", datetime.now(timezone.utc)).isoformat() if hasattr(item.get("completed_at"), 'isoformat') else str(item.get("completed_at", "")),
                "day_number": item.get("day_number", 1),
                "duration_minutes": item.get("duration_minutes", 0),
                "calories_burned": item.get("calories_burned", 0)
            })
        
        return formatted_history
    except Exception as e:
        logger.error(f"Error fetching workout history: {e}")
        return []

@api_router.get("/workouts")
async def get_workouts(user: UserProfile = Depends(require_auth)):
    """Get personalized workouts for the user"""
    gender = user.gender or "male"
    level = user.calculated_level or user.fitness_level or "beginner"
    goal = user.goal or "general_fitness"
    workout_mode = getattr(user, 'workout_mode', 'home') or 'home'
    
    workouts = get_workouts_for_user(gender, level, goal, workout_mode)
    
    # Enrich exercises with descriptions and images
    for workout in workouts:
        if "exercises" in workout:
            workout["exercises"] = [enrich_exercise(ex) for ex in workout["exercises"]]
    
    # Check trial and subscription status
    trial_status = get_trial_status(user)
    has_full_access = trial_status["has_full_access"]
    
    if not has_full_access:
        # Mark premium workouts as locked
        for workout in workouts:
            if workout.get("premium"):
                workout["locked"] = True
    
    return workouts

@api_router.get("/workouts/{workout_id}")
async def get_workout_detail(workout_id: str, user: UserProfile = Depends(require_auth)):
    """Get specific workout details"""
    gender = user.gender or "male"
    level = user.calculated_level or user.fitness_level or "beginner"
    goal = user.goal or "general_fitness"
    workout_mode = getattr(user, 'workout_mode', 'home') or 'home'
    
    workouts = get_workouts_for_user(gender, level, goal, workout_mode)
    
    workout = next((w for w in workouts if w["id"] == workout_id), None)
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    
    # Enrich exercises with descriptions and images
    if "exercises" in workout:
        workout["exercises"] = [enrich_exercise(ex) for ex in workout["exercises"]]
    
    # Check trial and subscription status
    trial_status = get_trial_status(user)
    has_full_access = trial_status["has_full_access"]
    
    if workout.get("premium") and not has_full_access:
        raise HTTPException(status_code=403, detail="Premium subscription or active trial required")
    
    return workout

@api_router.post("/workouts/{workout_id}/complete")
async def complete_workout(workout_id: str, request: Request, user: UserProfile = Depends(require_auth)):
    """Mark a workout as completed and update stats"""
    body = await request.json()
    duration = body.get("duration_minutes", 30)
    exercises_completed = body.get("exercises_completed", 0)
    
    # Calculate estimated calories (rough estimate)
    calories = int(duration * 7)  # ~7 calories per minute for moderate exercise
    
    # Save workout progress
    progress = {
        "user_id": user.user_id,
        "workout_id": workout_id,
        "workout_name": body.get("workout_name", ""),
        "completed_at": datetime.now(timezone.utc),
        "duration_minutes": duration,
        "calories_burned": calories,
        "exercises_completed": exercises_completed
    }
    await db.workout_progress.insert_one(progress)
    
    # Update user stats
    stats = await db.user_stats.find_one({"user_id": user.user_id}, {"_id": 0})
    if not stats:
        stats = {
            "user_id": user.user_id,
            "total_workouts": 0,
            "total_minutes": 0,
            "total_calories": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "last_workout_date": None
        }
    
    # Update totals
    stats["total_workouts"] = stats.get("total_workouts", 0) + 1
    stats["total_minutes"] = stats.get("total_minutes", 0) + duration
    stats["total_calories"] = stats.get("total_calories", 0) + calories
    
    # Update streak
    today = datetime.now(timezone.utc).date()
    last_workout = stats.get("last_workout_date")
    
    if last_workout:
        if isinstance(last_workout, str):
            last_workout = datetime.fromisoformat(last_workout)
        if hasattr(last_workout, 'date'):
            last_date = last_workout.date()
        else:
            last_date = last_workout
        
        days_diff = (today - last_date).days
        
        if days_diff == 1:
            stats["current_streak"] = stats.get("current_streak", 0) + 1
        elif days_diff > 1:
            stats["current_streak"] = 1
    else:
        stats["current_streak"] = 1
    
    if stats["current_streak"] > stats.get("longest_streak", 0):
        stats["longest_streak"] = stats["current_streak"]
    
    stats["last_workout_date"] = datetime.now(timezone.utc)
    
    await db.user_stats.update_one(
        {"user_id": user.user_id},
        {"$set": stats},
        upsert=True
    )
    
    # === ADVANCE TRAINING DAY ===
    # Get all available workouts to know total count
    gender = user.gender or "male"
    level = user.calculated_level or user.fitness_level or "beginner"
    goal = user.goal or "general_fitness"
    workout_mode = getattr(user, 'workout_mode', 'home') or 'home'
    workouts = get_workouts_for_user(gender, level, goal, workout_mode)
    total_workouts = len(workouts)
    
    # Get current training day and advance to next
    current_day = getattr(user, 'current_training_day', 1) or 1
    next_day = (current_day % total_workouts) + 1  # Cycle back to 1 after completing all
    
    # Update user's training day
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {
            "current_training_day": next_day,
            "last_training_date": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    # Get trial status - no longer using free_workouts_used logic
    trial_status = get_trial_status(user)
    
    return {
        "message": "Workout completed!",
        "calories_burned": calories,
        "current_streak": stats["current_streak"],
        "trial_active": trial_status.get("trial_active", False),
        "trial_days_remaining": trial_status.get("trial_days_remaining", 0),
        "show_paywall": not trial_status["has_full_access"],
        "training_day_completed": current_day,
        "next_training_day": next_day
    }

# ==================== STATS ENDPOINTS ====================

@api_router.get("/stats")
async def get_user_stats(user: UserProfile = Depends(require_auth)):
    """Get user's workout statistics with 10-day trial info"""
    stats = await db.user_stats.find_one({"user_id": user.user_id}, {"_id": 0})
    
    if not stats:
        stats = {
            "user_id": user.user_id,
            "total_workouts": 0,
            "total_minutes": 0,
            "total_calories": 0,
            "current_streak": 0,
            "longest_streak": 0,
            "last_workout_date": None
        }
    
    # Get recent workouts
    recent_workouts = await db.workout_progress.find(
        {"user_id": user.user_id},
        {"_id": 0}
    ).sort("completed_at", -1).limit(10).to_list(10)
    
    stats["recent_workouts"] = recent_workouts
    
    # Use centralized trial status for 10-day free trial
    trial_status = get_trial_status(user)
    
    stats["is_premium"] = trial_status["is_premium"]
    stats["has_full_access"] = trial_status["has_full_access"]
    stats["trial_active"] = trial_status.get("trial_active", False)
    stats["trial_days_remaining"] = trial_status.get("trial_days_remaining", 0)
    stats["trial_expired"] = trial_status.get("trial_expired", False)
    stats["show_paywall"] = not trial_status["has_full_access"]
    
    # Add daily motivation message
    today_workout = None
    if stats.get("last_workout_date"):
        last_date = stats["last_workout_date"]
        if isinstance(last_date, str):
            last_date = datetime.fromisoformat(last_date)
        if hasattr(last_date, 'date'):
            if last_date.date() == datetime.now(timezone.utc).date():
                today_workout = True
    
    stats["has_workout_today"] = today_workout or False
    stats["should_remind"] = not today_workout
    
    return stats

@api_router.get("/paywall/status")
async def get_paywall_status(user: UserProfile = Depends(require_auth)):
    """Check if paywall should be shown - 15-day free trial system"""
    # Use the centralized trial status function
    trial_status = get_trial_status(user)
    
    return {
        "is_premium": trial_status["is_premium"],
        "show_paywall": not trial_status["has_full_access"],
        "has_full_access": trial_status["has_full_access"],
        "trial_active": trial_status.get("trial_active", False),
        "trial_days_remaining": trial_status.get("trial_days_remaining", 0),
        "trial_expired": trial_status.get("trial_expired", False),
        "subscription_plan": user.subscription_plan,
        "subscription_status": user.subscription_status
    }

# ==================== SUBSCRIPTION ENDPOINTS ====================

SUBSCRIPTION_PLANS = [
    {
        "plan_id": "basic",
        "name_it": "Basic",
        "name_en": "Basic",
        "price": 4.99,
        "currency": "EUR",
        "features_it": ["Accesso a tutti gli allenamenti", "Programmi personalizzati", "Statistiche di base"],
        "features_en": ["Access to all workouts", "Personalized programs", "Basic statistics"],
        "period": "month",
        "trial_text_it": "15 Giorni Gratis",
        "trial_text_en": "15 Days Free",
        "color": "#4ECDC4"
    },
    {
        "plan_id": "pro",
        "name_it": "Pro",
        "name_en": "Pro",
        "price": 9.99,
        "currency": "EUR",
        "features_it": ["Tutto di Basic +", "Allenamenti avanzati", "Statistiche dettagliate", "Supporto prioritario"],
        "features_en": ["Everything in Basic +", "Advanced workouts", "Detailed statistics", "Priority support"],
        "period": "month",
        "trial_text_it": "15 Giorni Gratis",
        "trial_text_en": "15 Days Free",
        "color": "#FFD700",
        "recommended": True
    },
    {
        "plan_id": "elite",
        "name_it": "Elite",
        "name_en": "Elite",
        "price": 14.99,
        "currency": "EUR",
        "features_it": ["Tutto di Pro +", "Allenamenti esclusivi Elite", "Accesso anticipato nuove funzioni", "Badge esclusivo Elite"],
        "features_en": ["Everything in Pro +", "Exclusive Elite workouts", "Early access to new features", "Exclusive Elite badge"],
        "period": "month",
        "trial_text_it": "15 Giorni Gratis",
        "trial_text_en": "15 Days Free",
        "color": "#FF6B6B"
    }
]

@api_router.get("/subscriptions/plans")
async def get_subscription_plans():
    """Get available subscription plans with Google Play product IDs"""
    # Add Google Play product IDs to each plan
    plans_with_google = []
    for plan in SUBSCRIPTION_PLANS:
        plan_copy = dict(plan)
        plan_copy["google_play_product_id"] = f"{plan['plan_id']}_monthly"
        plans_with_google.append(plan_copy)
    return plans_with_google

# ==================== GOOGLE PLAY BILLING ====================

class GooglePlayPurchase(BaseModel):
    """Model for Google Play purchase verification"""
    product_id: str  # e.g., "basic_monthly", "pro_monthly", "elite_monthly"
    purchase_token: str
    order_id: Optional[str] = None

class GooglePlayPurchaseResult(BaseModel):
    """Result of purchase verification"""
    success: bool
    plan_id: Optional[str] = None
    message: str

def get_plan_from_product_id(product_id: str) -> Optional[dict]:
    """Map Google Play product ID to subscription plan"""
    product_to_plan = {
        "basic_monthly": "basic",
        "pro_monthly": "pro",
        "elite_monthly": "elite"
    }
    plan_id = product_to_plan.get(product_id)
    if plan_id:
        return next((p for p in SUBSCRIPTION_PLANS if p["plan_id"] == plan_id), None)
    return None

@api_router.post("/subscriptions/google-play/verify")
async def verify_google_play_purchase(
    purchase: GooglePlayPurchase,
    user: UserProfile = Depends(require_auth)
):
    """
    Verify a Google Play purchase and activate subscription.
    
    This endpoint should be called after a successful purchase from the app.
    In production, you should verify the purchase with Google Play Developer API.
    
    For now, we trust the client and activate the subscription.
    In production, add server-side verification using Google Play Developer API.
    """
    try:
        # Get plan from product ID
        plan = get_plan_from_product_id(purchase.product_id)
        if not plan:
            raise HTTPException(status_code=400, detail=f"Invalid product ID: {purchase.product_id}")
        
        plan_id = plan["plan_id"]
        
        logger.info(f"Processing Google Play purchase for user {user.user_id}: {purchase.product_id}")
        
        # Store the purchase record
        purchase_record = {
            "user_id": user.user_id,
            "product_id": purchase.product_id,
            "purchase_token": purchase.purchase_token,
            "order_id": purchase.order_id,
            "plan_id": plan_id,
            "status": "active",
            "platform": "google_play",
            "created_at": datetime.now(timezone.utc)
        }
        await db.purchases.insert_one(purchase_record)
        
        # Update user subscription to premium
        expires_at = datetime.now(timezone.utc) + timedelta(days=15)
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {
                "subscription_plan": plan_id,
                "subscription_status": "active",
                "subscription_expires": expires_at,
                "subscription_platform": "google_play",
                "google_play_purchase_token": purchase.purchase_token,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        logger.info(f"User {user.user_id} upgraded to {plan_id} via Google Play")
        
        return {
            "success": True,
            "plan_id": plan_id,
            "plan_name": plan["name_en"],
            "expires_at": expires_at.isoformat(),
            "message": "Subscription activated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google Play purchase verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/subscriptions/google-play/restore")
async def restore_google_play_purchases(
    request: Request,
    user: UserProfile = Depends(require_auth)
):
    """
    Restore purchases from Google Play.
    Called when user reinstalls app or logs in on new device.
    
    The app should pass the list of active subscriptions from Google Play.
    """
    try:
        body = await request.json()
        purchases = body.get("purchases", [])
        
        if not purchases:
            return {
                "success": True,
                "restored": False,
                "message": "No active subscriptions found"
            }
        
        # Find the best (highest tier) active subscription
        tier_order = {"elite": 3, "pro": 2, "basic": 1}
        best_plan = None
        best_purchase = None
        
        for p in purchases:
            product_id = p.get("productId") or p.get("product_id")
            plan = get_plan_from_product_id(product_id)
            if plan:
                plan_tier = tier_order.get(plan["plan_id"], 0)
                if best_plan is None or plan_tier > tier_order.get(best_plan["plan_id"], 0):
                    best_plan = plan
                    best_purchase = p
        
        if best_plan:
            # Update user subscription
            expires_at = datetime.now(timezone.utc) + timedelta(days=15)
            await db.users.update_one(
                {"user_id": user.user_id},
                {"$set": {
                    "subscription_plan": best_plan["plan_id"],
                    "subscription_status": "active",
                    "subscription_expires": expires_at,
                    "subscription_platform": "google_play",
                    "google_play_purchase_token": best_purchase.get("purchaseToken") or best_purchase.get("purchase_token"),
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            
            logger.info(f"Restored subscription for user {user.user_id}: {best_plan['plan_id']}")
            
            return {
                "success": True,
                "restored": True,
                "plan_id": best_plan["plan_id"],
                "plan_name": best_plan["name_en"],
                "message": "Subscription restored successfully"
            }
        
        return {
            "success": True,
            "restored": False,
            "message": "No valid subscriptions to restore"
        }
        
    except Exception as e:
        logger.error(f"Google Play restore error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/subscriptions/google-play/cancel")
async def cancel_google_play_subscription(user: UserProfile = Depends(require_auth)):
    """
    Handle subscription cancellation from Google Play.
    Note: The actual cancellation happens on Google Play side.
    This endpoint just updates our database when notified.
    """
    try:
        await db.users.update_one(
            {"user_id": user.user_id},
            {"$set": {
                "subscription_status": "cancelled",
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        logger.info(f"Subscription cancelled for user {user.user_id}")
        
        return {
            "success": True,
            "message": "Subscription marked as cancelled"
        }
        
    except Exception as e:
        logger.error(f"Subscription cancellation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/subscriptions/status")
async def get_subscription_status(user: UserProfile = Depends(require_auth)):
    """Get user's subscription status"""
    return {
        "plan": user.subscription_plan,
        "status": user.subscription_status,
        "expires": user.subscription_expires.isoformat() if user.subscription_expires else None,
        "is_premium": user.subscription_status == "active",
        "platform": getattr(user, 'subscription_platform', None) or "google_play"
    }

# ==================== HEALTH CHECK ====================

@api_router.get("/")
async def root():
    return {"message": "Fitora Training API", "status": "healthy"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# ==================== EXERCISE IMAGES ====================

@api_router.get("/exercises/images/{exercise_name}")
async def get_exercise_image(exercise_name: str):
    """Serve exercise illustration images"""
    # Sanitize filename
    safe_name = exercise_name.lower().replace(" ", "-").replace("_", "-")
    image_path = FRONTEND_DIR / "assets" / "images" / "exercises" / f"{safe_name}.png"
    
    if image_path.exists():
        return FileResponse(image_path, media_type="image/png")
    
    # Try without extension
    if not safe_name.endswith(".png"):
        image_path = FRONTEND_DIR / "assets" / "images" / "exercises" / f"{safe_name}.png"
        if image_path.exists():
            return FileResponse(image_path, media_type="image/png")
    
    raise HTTPException(status_code=404, detail="Exercise image not found")

@api_router.get("/exercises/images")
async def list_exercise_images():
    """List all available exercise images"""
    images_dir = FRONTEND_DIR / "assets" / "images" / "exercises"
    if not images_dir.exists():
        return {"images": []}
    
    images = [f.stem for f in images_dir.glob("*.png")]
    return {"images": images, "count": len(images)}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
