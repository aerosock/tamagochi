from tortoise import Tortoise, fields, models

class User(models.Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=50, unique=True)
    password = fields.CharField(max_length=100) 
    equipped_skin = fields.CharField(max_length=50, default="Classical Cat")
    hunger = fields.IntField(default=100)
    cleanliness = fields.IntField(default=100)
    health = fields.IntField(default=100)
    happiness = fields.IntField(default=100)
    # isLoggedIn = fields.BooleanField(default=False)

async def init_db():
    await Tortoise.init(db_url='sqlite://db.sqlite3', modules={'models': ['models']}) # Note: module name is 'models'
    await Tortoise.generate_schemas()