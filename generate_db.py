import asyncio
import random
import string
import bcrypt
from datetime import datetime, timedelta, timezone
from tortoise import Tortoise, fields, models, run_async

# --- CONFIGURATION ---
DB_FILE = 'db.sqlite3'
USER_COUNT = 200
DEFAULT_PASSWORD = "password123"  # All generated users will have this password

# --- MODEL DEFINITION (Matching your schema) ---
class User(models.Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    password = fields.CharField(max_length=128)
    email = fields.CharField(max_length=100)
    equipped_skin = fields.CharField(max_length=50, default="Classical Cat")
    hunger = fields.IntField(default=100)
    thirst = fields.IntField(default=100)
    sleep = fields.IntField(default=100)
    cleanliness = fields.BooleanField(default=True)
    health = fields.IntField(default=100)
    happiness = fields.IntField(default=100)
    isLoggedIn = fields.BooleanField(default=False)
    age = fields.DatetimeField()
    mood = fields.IntField(default=100)
    isnewuser = fields.BooleanField(default=True)
    energy = fields.IntField(default=100)
    money = fields.IntField(default=20)
    isAdmin = fields.BooleanField(default=False)
    title = fields.CharField(max_length=100, default="Newborn Bundle")
    isSleeping = fields.BooleanField(default=False)
    sleep_start_time = fields.DatetimeField(null=True)
    sleep_stored_val = fields.FloatField(default=0.0)

# --- GAME DATA CONSTANTS ---
SKINS = [
    "Batman Cat", "Brown Cat", "Classical Cat", "Christmas Cat",
    "Demonic Cat", "Egypt Cat", "Siamese Cat", "Three Color Cat",
    "Tiger Cat", "Black Cat", "Halloween Cat", "Goofy White Cat"
]

MILESTONES = [
    (365, "LVL 10/10, Celestial Cat"),
    (180, "LVL 9/10, Ancient Legend"),
    (100, "LVL 8/10, Wise Elder"),
    (60,  "LVL 7/10, Cozy Senior"),
    (30,  "LVL 6/10, House Master"),
    (14,  "LVL 5/10, Adult Hunter"),
    (7,   "LVL 4/10, Feisty Teen"),
    (3,   "LVL 3/10, Playful Junior"),
    (1,   "LVL 2/10, Curious Kitten"),
    (0,   "LVL 1/10, Newborn Bundle"),
]

def get_title_for_age(creation_date):
    """Calculates title based on how many days ago the user was created."""
    now = datetime.now(timezone.utc)
    diff = now - creation_date
    days_alive = diff.days
    
    for threshold, title in MILESTONES:
        if days_alive >= threshold:
            return title
    return "LVL 1/10, Newborn Bundle"

async def generate():
    print(f"Initializing {DB_FILE}...")
    await Tortoise.init(db_url=f'sqlite://{DB_FILE}', modules={'models': ['__main__']})
    await Tortoise.generate_schemas()
    
    # Check if DB is already populated
    if await User.all().count() > 0:
        print("Database already contains data. Skipping generation.")
        return

    print("Hashing default password...")
    # Pre-hash the password once to speed up generation
    hashed_pwd = bcrypt.hashpw(DEFAULT_PASSWORD.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    users_to_create = []

    # --- 1. CREATE ADMIN USER ---
    print("Creating Admin user...")
    admin_age = datetime.now(timezone.utc) - timedelta(days=400) # Old account
    users_to_create.append(User(
        username="admin",
        password=hashed_pwd,
        email="admin@tamagochi.com",
        equipped_skin="Demonic Cat",
        money=99999,
        isAdmin=True,
        age=admin_age,
        title=get_title_for_age(admin_age),
        isnewuser=False,
        hunger=100, thirst=100, sleep=100, health=100, happiness=100
    ))

    # --- 2. CREATE RANDOM USERS ---
    print(f"Generating {USER_COUNT} random users...")
    
    for i in range(USER_COUNT):
        # Random basics
        username = f"Player_{i}_{''.join(random.choices(string.ascii_lowercase, k=3))}"
        email = f"{username}@example.com"
        
        # Random Age (between 0 and 500 days ago)
        days_ago = random.randint(0, 500)
        age = datetime.now(timezone.utc) - timedelta(days=days_ago)
        
        # Random Stats
        hunger = random.randint(20, 100)
        thirst = random.randint(20, 100)
        sleep_val = random.randint(10, 100)
        happiness = random.randint(40, 100)
        health = random.randint(50, 100)
        money = random.randint(0, 5000)
        skin = random.choice(SKINS)
        
        # Sleep Logic
        is_sleeping = random.random() < 0.2 # 20% chance to be sleeping
        sleep_start = None
        stored_val = 0.0
        
        if is_sleeping:
            # Sleeping started 1-3 hours ago
            sleep_start = datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 3))
            stored_val = float(sleep_val)

        users_to_create.append(User(
            username=username,
            password=hashed_pwd,
            email=email,
            equipped_skin=skin,
            hunger=hunger,
            thirst=thirst,
            sleep=sleep_val,
            cleanliness=random.choice([True, True, True, False]), # 75% chance to be clean
            health=health,
            happiness=happiness,
            isLoggedIn=False, # Default to offline
            age=age,
            mood=happiness, # mapping mood to happiness for simplicity
            isnewuser=False,
            energy=random.randint(50, 100),
            money=money,
            isAdmin=False,
            title=get_title_for_age(age),
            isSleeping=is_sleeping,
            sleep_start_time=sleep_start,
            sleep_stored_val=stored_val
        ))

    # Bulk create for performance
    await User.bulk_create(users_to_create)
    
    print(f"Successfully created {len(users_to_create)} users!")
    print(f"Admin Login -> Username: 'admin', Password: '{DEFAULT_PASSWORD}'")
    print(f"User Logins -> Username: 'Player_0_xxx', Password: '{DEFAULT_PASSWORD}'")

if __name__ == "__main__":
    run_async(generate())