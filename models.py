from tortoise import Tortoise, fields, models
from pydantic import BaseModel, EmailStr

class User(models.Model):
    id = fields.IntField(pk=True) #ID uživatele
    username = fields.CharField(max_length=50, unique=True) #jmeno uživatele
    password = fields.CharField(max_length=128) # heslo 
    email = fields.CharField(max_length=100) # email
    equipped_skin = fields.CharField(max_length=50, default="Classical Cat") # vzbraný oblek dané kočky
    hunger = fields.IntField(default=100) # sytost
    thirst = fields.IntField(default=100) # žižen
    sleep = fields.IntField(default=100) #únava
    cleanliness = fields.BooleanField(default=True) # čistota
    health = fields.IntField(default=100) # zdraví
    happiness = fields.IntField(default=100) # štěstí
    isLoggedIn = fields.BooleanField(default=False) # jestli uživatel je online
    age = fields.DatetimeField()    # věk kočky
    mood = fields.IntField(default=100) 
    isnewuser = fields.BooleanField(default=True)# využívano pro zobrazení uvítacího oznámení
    energy = fields.IntField(default=100)#energie
    money = fields.IntField(default=20)#penize
    isAdmin = fields.BooleanField(default=False)#jestli uživatel je administrator
    title = fields.CharField(max_length=100, default="Newborn Bundle")#úroveň hrače
    isSleeping = fields.BooleanField(default=False)#jestli kočka spí
    sleep_start_time = fields.DatetimeField(null=True)#začatek spanku
    sleep_stored_val = fields.FloatField(default=0.0)#únava na žačatku spankuSSS


async def init_db():
    await Tortoise.init(db_url='sqlite://db.sqlite3', modules={'models': ['models']})
    await Tortoise.generate_schemas()