import asyncio
import random
import time
import pathlib
from itertools import cycle
from PIL import Image
from nicegui import ui, app, events
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, ValidationError
import bcrypt
from collections import defaultdict
from models import User
from tortoise.functions import Count, Sum, Avg
from tortoise import Tortoise

HEALTH_DECAY_PER_TICK = 0.005
HEALTH_REGEN_PER_TICK = 0.01
hungerdecrement = 0.0027
thirstdecrement = 0.0027
sleepdecrement = 0.001
SLEEP_DURATION_HOURS = 4
cleanchance = 864000

from models import User
SPRITE_SCALE = 4
roomsize = 512
BASE = pathlib.Path(__file__).parent

skinfolderarray = [
    "Batman Cat", "Brown Cat", "Classical Cat", "Christmas Cat",
    "Demonic Cat", "Egypt Cat", "Siamese Cat", "Three Color Cat",
    "Tiger Cat", "Black Cat", "Halloween Cat", "Goofy White Cat"
]

HUNGER_HOURS = 10
THIRST_HOURS = 10
SLEEP_DECAY_HOURS = 24 
CLEAN_HOURS = 24      

def update_hunger_settings(e):
    global hungerdecrement, HUNGER_HOURS
    HUNGER_HOURS = e.value
    hungerdecrement = 100 / (HUNGER_HOURS * 3600 * 10)

def update_thirst_settings(e):
    global thirstdecrement, THIRST_HOURS
    THIRST_HOURS = e.value
    thirstdecrement = 100 / (THIRST_HOURS * 3600 * 10)

def update_sleep_decay_settings(e):
    global sleepdecrement, SLEEP_DECAY_HOURS
    SLEEP_DECAY_HOURS = e.value
    sleepdecrement = 100 / (SLEEP_DECAY_HOURS * 3600 * 10)

def update_clean_settings(e):
    global cleanchance, CLEAN_HOURS
    CLEAN_HOURS = e.value
    cleanchance = int(CLEAN_HOURS * 3600 * 10)

async def getdb_stats():
    total_users = await User.all().count()
    online_users = await User.filter(isLoggedIn=True).count()
    
    stats = await User.all().annotate(
        total_money=Sum("money"),
        avg_health=Avg("health")
    ).first()
    
    total_money = stats.total_money if stats and stats.total_money else 0
    avg_health = stats.avg_health if stats and stats.avg_health else 0

    return {
        "total_users": total_users,
        "online_users": online_users,
        "total_money": total_money,
        "avg_health": round(avg_health, 1)
    }

async def get_skin_distribution():
    data = await User.all().group_by("equipped_skin").annotate(count=Count("id")).values("equipped_skin", "count")
    return data

async def get_average_stats():
    data = await User.all().annotate(avg_hunger=Avg("hunger"), avg_thirst=Avg("thirst"), avg_sleep=Avg("sleep"), avg_happiness=Avg("happiness")).first()

    return [
        data.avg_hunger,
        data.avg_thirst,
        data.avg_sleep,
        data.avg_happiness
    ]

async def get_top_players(limit=10):
    return await User.all().order_by("-money").limit(limit).values("id", "username", "money", "title")


def get_remaining_time_str(current_val, total_hours_setting, is_filling=False):
    if is_filling:
        percent_remaining = (100 - current_val) / 100.0
    else:
        percent_remaining = current_val / 100.0
        
    total_minutes = int(percent_remaining * total_hours_setting * 60)
    
    hours = total_minutes // 60
    mins = total_minutes % 60
    
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"



def clamp(v, lo=0.5, hi=2.0):
    return max(lo, min(hi, v))

def spriteHandler(xs, ys, xe, ye, name, scale: int = 1):
    img = Image.open(BASE / 'textures' / name).crop((xs, ys, xs + xe, ys + ye))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), resample=Image.NEAREST)
    return img

def spriteCycler(x, y, step, path, scale: int = 1, ystep=32):
    x *= step
    y *= ystep
    img = Image.open(BASE / 'textures' / path).crop((x, y, x + step, y + ystep))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), resample=Image.NEAREST)
    return img

class RhythmTarget:
    def __init__(self, key_char, prog, container, x, y):
        self.el = container
        self.prog = prog
        self.key = key_char
        self.start_time = time.time()
        self.clicked = False
        self.x = x
        self.y = y 
        

class Game:
    class UserCreate(BaseModel):
        username: str
        password: str
        email: EmailStr
    
    def __init__(self, user: User, on_logout_callback):
        self.age_timer = None
        self.newuser = False
        self.stat_cache = {}
        self.hunger_ui = None
        self.thirst_ui = None
        self.sleep_ui = None
        self.user = user
        self.on_logout_callback = on_logout_callback
        self.washstart = None
        self.move_task = None   
        self.evading = None
        self.cat_layer = None
        self.canvas = None
        self.cat = None
        self.cat_visuals = None
        self.pet_timeout_task = None
        self.anim_arrays = {}           
        self.current_anim_task = None   
        self.current_visible_list = None 
        self.petState = 0    
        self.agetip_time = None           
        self.current_room = 'home'
        self.cam_x = 0.0 
        self.cam_y = 0.0
        self.cam_zoom = 1.0
        self.cam_zoom_sens = 1.0
        self.cat_x = 50.0 
        self.cat_y = 55.0
        self.pos = 55
        self.water = False
        self.readytoeat = False
        self.buttons = {}
        self.shower_task = None
        self.shower_progress_bar = None
        self.showernum = None
        self.reseticon = None
        self.changingui = None
        self.skinnamelabel = None
        self.skinnum = skinfolderarray.index(self.user.equipped_skin)
        self.isloggedin = True
        self.oscillate_task = None

        self.petting_mode = False
        self.petting_score = 0
        self.active_targets = [] 
        self.rhythm_task = None
        # self.stroke_phase_active = False
        # self.stroke_counter = 0
        # self.last_stroke_y = 0
        self.score_bar = None
        self.petting_overlay = None
        
    
    def update_transform(self):
        if self.canvas:
            self.canvas.style(f'transform: translate({self.cam_x}%, {self.cam_y}%) scale({self.cam_zoom})')

    
   
    
    def on_wheel(self, e):
        dy = e.args.get('deltaY', 0)
        zoom_factor = 1.1 ** self.cam_zoom_sens
        if dy > 0:
            self.cam_zoom = clamp(self.cam_zoom / zoom_factor)
        else:
            self.cam_zoom = clamp(self.cam_zoom * zoom_factor)
            
        self.update_transform()

    def set_cat_orientation(self, facing_right: bool):
            scale_x = 1 if facing_right else -1
            if self.cat_visuals:
                self.cat_visuals.style(f'transform: scaleX({scale_x});')


    def Preload(self, path, NofSprites, anim_name, step=32, ystep=32):

        Pics = [spriteCycler(x, 0, step, path, scale=SPRITE_SCALE, ystep=ystep) for x in range(NofSprites + 1)]
        local_frames = []
        for pic in Pics:
            img = ui.image(pic).classes('absolute w-full h-full object-contain opacity-0 transition-none')
            local_frames.append(img)
        self.anim_arrays[anim_name] = local_frames

    def decrementcalc(self, input, name):
        global hungerdecrement, thirstdecrement, sleepdecrement, cleanchance, sleepincrement
        if name == 'hunger':
            hungerdecrement = 100 / (input * 3600 * 10)
        elif name == 'thirst':
            thirstdecrement = 100 / (input * 3600 * 10)
        elif name == 'sleep-':   
            sleepdecrement = 100 / (input * 3600 * 10)
        elif name == 'cleanliness':     # 1 in 36000 once in 1h at one attempt each 0.1s
            cleanchance = input * 36000 
        elif name == 'sleep+':
            sleepincrement 
        
         
    
    
    def doAnim(self, anim_name, time, cancel_current=True):
        if self.current_anim_task and cancel_current:
            self.current_anim_task.cancel()
        
        if self.current_visible_list:
            for x in self.current_visible_list: 
                x.classes(remove='opacity-100', add='opacity-0')
        
        target_frames = self.anim_arrays.get(anim_name)
        self.current_visible_list = target_frames
        
        if target_frames:
            target_frames[0].classes(remove='opacity-0', add='opacity-100') 
            self.current_anim_task = asyncio.create_task(self.cyclingSprite(target_frames, time))
        

    async def cyclingSprite(self, frames_list, time):
        NofSprites = len(frames_list) - 1
        while True:
            sequence = list(range(NofSprites + 1)) + list(range(NofSprites - 1, 0, -1))
            for index in sequence:
                for f in frames_list:
                    f.classes(remove='opacity-100', add='opacity-0')
                frames_list[index].classes(remove='opacity-0', add='opacity-100')
                await asyncio.sleep(time)
                
    def catPet(self, coord):
        # if self.petting_mode and self.stroke_phase_active:
        #     curr_y = coord.y
        #     if self.last_stroke_y > 0.3 and curr_y < -0.3:
        #         self.stroke_counter += 1
        #         self.update_petting_score(1)
        #         self.doAnim("pet", 0.1, cancel_current=True)
        #     elif self.last_stroke_y < -0.3 and curr_y > 0.3:
        #         self.stroke_counter += 1
        #         self.update_petting_score(1)
        #         self.doAnim("pet", 0.1, cancel_current=True)
            
        #     self.last_stroke_y = curr_y
        #     return

        if self.current_room == 'home' and not self.petting_mode:
            if self.petState == 0:
                if coord.y > 0.5: 
                    self.petState = 3
                elif coord.y < -0.5: 
                    self.petState = 1
            if self.petState == 1 and coord.y > 0.5: 
                self.petAnim()
            if self.petState == 3 and coord.y < -0.5: 
                self.petAnim()

    def petAnim(self):
        if self.pet_timeout_task:
            self.pet_timeout_task.cancel()
            self.pet_timeout_task = None

        if self.petState != 2:
            self.petState = 2
            self.doAnim("pet", 0.15)

        self.pet_timeout_task = asyncio.create_task(self.petEnd())
        
    async def petEnd(self):
        await asyncio.sleep(0.2) 
        self.petState = 0
        self.pet_timeout_task = None
        if self.current_room != 'bath' and not self.petting_mode:
            self.doAnim("idle", 0.35)

    def newcommer_banner(self):
        if self.user.isnewuser == True:
            with ui.dialog() as dialog, ui.card().style('padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
                ui.label(f'Hello {self.user.username}! Welcome to Tamagochi Cat Simulator!').classes('text-2xl font-bold text-black mb-4 text-center').style('font-family: runescape;')
                ui.label('Here are some tips to get you started:').classes('text-lg text-black mb-2').style('font-family: runescape;')
                ui.label('- Use the buttons on the right to navigate between rooms.').classes('text-md text-black mb-1').style('font-family: runescape;')
                ui.label('- Take care of your cat by feeding, bathing, and playing with it!').classes('text-md text-black mb-1').style('font-family: runescape;')
                ui.button('Close', on_click=dialog.close).style('font-family: runescape; color: white; background-color: #bd9a8e; padding: 10px;').classes('pixel-border pixel-3d mt-4 w-full')
            self.user.isnewuser = False
            asyncio.create_task(self.user.save())            
            ui.timer(0.8, lambda: dialog.open(), once=True)

    async def cameraAction(self, target_x_pct, target_y_pct, target_zoom, speed=2.0):
        dist_x = target_x_pct - self.cam_x
        dist_y = target_y_pct - self.cam_y
        dist_z = target_zoom - self.cam_zoom
        
        max_dist = max(abs(dist_x), abs(dist_y))
        
        total_steps = int(max(1, max_dist * speed)) 
            
        inc_x = dist_x / total_steps
        inc_y = dist_y / total_steps
        inc_z = dist_z / total_steps
        
        for _ in range(total_steps):
            self.cam_x += inc_x
            self.cam_y += inc_y
            self.cam_zoom += inc_z
            self.update_transform()
            await asyncio.sleep(0.01)
            
        self.cam_x = target_x_pct
        self.cam_y = target_y_pct
        self.cam_zoom = target_zoom
        self.update_transform()

    async def moveCat(self, target_x_pct, target_y_pct, speed=1.0, run_anim="walk", end_anim="idle", restore_tracking=True, animtime1=0.15, animtime2=0.35, delay=0.0):
        if self.cat:
            self.cat.client.run_javascript('window.setTracking(false)')

        if target_x_pct < self.cat_x:
            self.set_cat_orientation(False)
        elif target_x_pct > self.cat_x:
            self.set_cat_orientation(True) 

        self.doAnim(run_anim, animtime1)

        await asyncio.sleep(delay)
        
        dx = target_x_pct - self.cat_x
        dy = target_y_pct - self.cat_y
        dist = (dx**2 + dy**2)**0.5
        
        step_size = 0.5 * speed
        steps = int(dist / step_size)

        if steps > 0:
            dx /= steps
            dy /= steps
            for _ in range(steps):
                self.cat_x += dx
                self.cat_y += dy
                
                if self.cat:
                    self.cat.style(f'left:{self.cat_x}%; top:{self.cat_y}%;')
                await asyncio.sleep(0.016) 

        self.cat_x = target_x_pct
        self.cat_y = target_y_pct
        if self.cat:
            self.cat.style(f'left:{self.cat_x}%; top:{self.cat_y}%;')

        self.doAnim(end_anim, animtime2)
        
        if restore_tracking and self.cat:
            self.cat.client.run_javascript('window.setTracking(true)')

    @ui.refreshable
    def changePfp(self):
        
        ui.image(spriteCycler(0, 0, 32, f"{self.user.equipped_skin}/SittingB.png", scale=SPRITE_SCALE)).classes('w-25 h-25')
            

    def hud_top_left(self):
        with ui.element('div').classes('relative pixelated'):
            ui.image("/textures/statusbar.png").classes('w-100 mb-2')
            with ui.element('div').classes('absolute left-33 top-9 w-63'):
                self.hud_health_bar = ui.linear_progress(value=1.0, color='red', show_value=False).props('instant-feedback').classes('absolute w-63 h-5')
                self.hud_health_text = ui.badge('100').classes('absolute-full flex flex-center text-black bg-transparent text-xl content-center h-5')
                ui.image("/textures/heart.png").classes('absolute w-10 h-10 -left-5 -top-5')
            with ui.element('div').classes('absolute left-33 top-17 w-63'):
                self.hud_energy_bar = ui.linear_progress(value=1.0, color='yellow', show_value=False).props('instant-feedback').classes('absolute w-63 h-5')
                self.hud_energy_text = ui.badge('100').classes('absolute-full flex flex-center text-pink bg-transparent text-xl h-5')
            with ui.element('div').classes('absolute left-30 top-24'):
                ui.image("/textures/coin.png").classes('w-12 h-12 inline-block ml-2')
                self.moneylabel = ui.label(str(self.user.money)).classes('inline-block ml-2 text-2xl font-bold').style(
                    'transform: translateY(7px); color: #f0e68c; text-shadow: 2px 2px 3px #000;')
               
            self.pfpplace = ui.element('div').classes('absolute left-4 top-8')
            with self.pfpplace:
                self.changePfp()
                
    async def get_age_title(self):
        diff = datetime.now(timezone.utc) - self.user.age
        days_alive = diff.days
        
        milestones = [
            (365, "LVL 10/10, Celestial Cat", 9),
            (180, "LVL 9/10, Ancient Legend", 8),
            (100, "LVL 8/10, Wise Elder", 7),
            (60,  "LVL 7/10, Cozy Senior", 6),
            (30,  "LVL 6/10, House Master", 5),
            (14,  "LVL 5/10, Adult Hunter", 4),
            (7,   "LVL 4/10, Feisty Teen", 3),
            (3,   "LVL 3/10, Playful Junior", 2),
            (1,   "LVL 2/10, Curious Kitten", 1),
            (0,   "LVL 1/10, Newborn Bundle", 0),
        ]

        current_text = "LVL 1/10, Newborn Bundle"
        current_idx = 0
        
        for threshold, title, idx in milestones:
            if days_alive >= threshold:
                current_text = title
                current_idx = idx
                break

        old_idx = 0
        for _, title, idx in milestones:
            if title == self.user.title:
                old_idx = idx
                break

        colors = [
            "#6B7280", "#65A30D", "#059669", "#0891B2", "#2563EB", 
            "#7C3AED", "#C026D3", "#DC2626", "#EA580C", "#B45309"
        ]
        
        if self.ranklabel:
            self.ranklabel.set_text(current_text)
            if current_idx == 9:
                self.ranklabel.classes(add='celestial-text')
            else:
                self.ranklabel.classes(remove='celestial-text')
                self.ranklabel.style(f'color: {colors[current_idx]}; text-shadow: 1px 1px 2px #fff;')

        if current_text != self.user.title:
            if current_idx > old_idx:
                reward_amount = (current_idx * 15) + 10 
                
                self.user.money += reward_amount
                
                self.show_levelup_dialog(current_text, reward_amount)

            self.user.title = current_text
            self.curtitle = current_text
            asyncio.create_task(self.user.save())
            


    def stats_left(self):
        self.stat_cache = {} 

        with ui.element('div').classes('relative top-30'):
            ui.image("/textures/stats.png").classes('absolute w-70 mb-2')
            
            with ui.element('div').classes('absolute -right-5 -top-5 z-50 hidden') as self.dirty_indicator:
                ui.label('NEEDS BATH!').classes('text-red-600 font-bold bg-white px-1 rounded pixel-border').style('font-family: runescape; font-size: 0.8rem; position: relative; top: -10px;')

            with ui.element('div').classes('absolute top-20 left-10 w-50 text-xl'):
                ui.label('Stats').classes("h-10 text-lg font-bold text-center")
                ui.separator()
                ui.label(self.user.username).classes('font-bold text-lg')
                self.age_display = ui.label(f'age: {self.age_timer}').classes('font-bold text-lg')
                with self.age_display:
                    self.agetip = ui.tooltip(f'{self.agetip_time}').style('font-family: runescape; background-color: #f0e4d7; color: #333; padding: 0.3vw; border-radius: 5px; font-size: 0.9rem;')


                with ui.element('div').classes('mt-1'):
                    ui.label('Hunger:').classes('font-bold')
                    self.hunger_container = ui.row().classes('gap-0 inline-block')
                    self.update_stat_icons(self.hunger_container, self.user.hunger, "foodsprite.png")
                    with self.hunger_container:
                        self.hunger_tooltip = ui.tooltip('...').style('font-family: runescape; font-size: 0.9rem;')
                
                with ui.element('div').classes('mt-1'):
                    ui.label('Thirst:').classes('font-bold')
                    self.thirst_container = ui.row().classes('gap-0 inline-block')
                    self.update_stat_icons(self.thirst_container, self.user.thirst, "watersprite.png")
                    with self.thirst_container:
                        self.thirst_tooltip = ui.tooltip('...').style('font-family: runescape; font-size: 0.9rem;')
                
                with ui.element('div').classes('mt-1'):
                    ui.label('Sleep:').classes('font-bold')
                    self.sleep_container = ui.row().classes('gap-0 inline-block')
                    self.update_stat_icons(self.sleep_container,  self.user.sleep,  "sleepsprite.png")
                    self.sleep_timer_label = ui.label('').classes('block text-xs font-bold text-blue-600 mt-1').style('font-family: runescape;')

                with ui.element('div').classes('mt-2'):
                    ui.label('Rank:').classes('font-bold')
                    self.ranklabel = ui.label(self.user.title).classes('inline-block ml-2 font-semibold gap-0').style('color: #333; text-shadow: 1px 1px 2px #fff;')
            
            ui.timer(1.0, self.get_age_title)
    
    def show_levelup_dialog(self, new_title, reward):
        with ui.dialog() as dialog, ui.card().style('background-color: #FFF8E1; border: 4px solid #F59E0B; min-width: 350px; text-align: center; padding: 20px;'):
            ui.label('LEVEL UP!').classes('text-4xl font-bold mb-2').style('font-family: runescape; color: #D97706; text-shadow: 2px 2px 0px #000;')
            
            ui.label('Your cat has grown into a:').classes('text-gray-700 font-semibold')
            ui.label(new_title).classes('text-xl font-bold mb-4').style('color: #B45309;')
            
            ui.separator().classes('mb-4 bg-orange-200')
            
            ui.label('Level Up Bonus:').classes('text-gray-600 font-bold')
            with ui.row().classes('justify-center items-center w-full gap-2'):
                ui.image('/textures/coin.png').classes('w-10 h-10 animate-bounce')
                ui.label(f'+{reward}').classes('text-3xl font-bold text-green-600').style('font-family: runescape;')
                
            ui.button('Collect Reward', on_click=dialog.close).classes('mt-6 w-full').style('background-color: #F59E0B; color: white; font-family: runescape; border: 2px solid #78350F;')
        
        dialog.open()
    
    def update_stat_icons(self, container, stat, spritesheet):
        if container is None or container.is_deleted:
            return

        val = int(stat)
        full = val // 20 + (1 if val % 20 >= 15 else 0)
        half = 1 if full < 5 and 5 <= val % 20 < 15 else 0
        empty = 5 - full - half
        
        current_state = (full, half)

        if self.stat_cache.get(container.id) == current_state:
            return

        self.stat_cache[container.id] = current_state

        container.clear()
        with container:
            for x in range(full):
                ui.image(spriteHandler(32, 0, 16, 16, spritesheet, scale=SPRITE_SCALE)).classes('inline-block w-6 h-6')
            
            if half:
                ui.image(spriteHandler(16, 0, 16, 16, spritesheet, scale=SPRITE_SCALE)).classes('inline-block w-6 h-6')
                
            for x in range(empty):
                ui.image(spriteHandler(0, 0, 16, 16, spritesheet, scale=SPRITE_SCALE)).classes('inline-block w-6 h-6')
            
        
    def agecheck(self, tooltip = False):
        while True:
            diff = datetime.now(timezone.utc) - self.user.age
        
            
            years = diff.days // 365
            remaining_days = diff.days % 365
            
            months = remaining_days // 30
            days = remaining_days % 30
            
            hours = diff.seconds // 3600
            remaining_seconds = diff.seconds % 3600
            
            minutes = remaining_seconds // 60
            seconds = remaining_seconds % 60
            parts = []
            if tooltip:
                limit = 10000000000000000000000
            else:
                limit = 3
            if years > 0 : 
                parts.append(f"{years}y")
            if months > 0: 
                parts.append(f"{months}m")
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0 and len(parts) < limit: 
                parts.append(f"{hours}h")
            if minutes > 0 and len(parts) < limit: 
                parts.append(f"{minutes}min")
            if seconds > 0 and len(parts) < limit:
                parts.append(f"{seconds}s")
            
            return " ".join(parts)


    async def press(self, name: str):
            prev = self.current_room
            if prev == name: return
            
            if prev in self.buttons:
                p_up, p_dn, p_icon = self.buttons[prev]
                p_up.classes(remove='opacity-0', add='opacity-100')
                p_dn.classes(remove='opacity-100', add='opacity-0')
                p_icon.style('transform: translate(-50%, -55%) perspective(600px);')
            
            if name in self.buttons:
                n_up, n_dn, n_icon = self.buttons[name]
                n_up.classes(remove='opacity-100', add='opacity-0')
                n_dn.classes(remove='opacity-0', add='opacity-100')
                n_icon.style('transform: translate(-50%, -57%) perspective(600px) scaleY(1.02);')
                
            if name == 'home': 
                await self.home()
            elif name == 'shower': 
                await self.shower()
            elif name == 'sleep': 
                await self.sleep()
            elif name == 'foodbowl': 
                await self.foodbowl()
            elif name == 'wardrobe': 
                await self.wardrobe()
            elif name == 'settings': 
                await self.settings()
            elif name == 'dashboard': 
                await self.dashboard()

    async def settings(self):
        ui.navigate.to('/settings')
        self.current_room = 'settings'
    
    async def home(self):
        if self.current_room != 'home':
            ui.navigate.to('/')
            self.current_room = 'home'
        
        await asyncio.sleep(0.2)

        if self.user.isSleeping:
            await self.cameraAction(-15, -15, 2.0, speed=2.0)
        else:
            await self.cameraAction(0, 0, 1.0, speed=2.0)
            if self.cat_x != 50 or self.cat_y != 55:
                await self.moveCat(50, 55, speed=1.5, run_anim="walk")


    async def shower(self): 
        ui.navigate.to('/bath')
        self.current_room = 'bath'
        await asyncio.sleep(0.2)
        asyncio.create_task(self.cameraAction(0, 0, 1.0, speed=2.0))
        if self.cat_x != 50 or self.cat_y != 55:
            asyncio.create_task(self.moveCat(50, 55, speed=1.5, run_anim="walk"))
    
    async def sleep(self): 
        if self.current_room != 'home' and self.current_room != 'sleep':
            ui.navigate.to('/')
            self.current_room = 'home'
        
        if self.current_room != 'sleep':
            self.current_room = 'sleep'
        
        await asyncio.sleep(0.2)
        
        if self.user.isSleeping:
            await self.cameraAction(-15, -15, 2.0, speed=2.0)
        else:
            await self.sleepbutasync()

    def setup_lifecycle_hooks(self):
        async def set_status(is_online):
            await User.filter(id=self.user.id).update(isLoggedIn=is_online)

        asyncio.create_task(set_status(True))

        ui.context.client.on_disconnect(lambda: set_status(False))
    
    async def sleepbutasync(self):
        if self.user.isSleeping: return

        self.cat.client.run_javascript('window.setTracking(false)')
        asyncio.create_task(self.cameraAction(-15, -15, 2.0, speed=3.0))
        await self.moveCat(38, 44, speed=1, run_anim="walk", restore_tracking=False)
        self.set_cat_orientation(True)
        await asyncio.sleep(0.5)
        await self.moveCat(53, 34, speed=1.0, run_anim="jump", end_anim="sleep", restore_tracking=False)
        
        self.user.isSleeping = True
        self.user.sleep_start_time = datetime.now(timezone.utc)
        self.user.sleep_stored_val = self.user.sleep 
        await self.user.save()

    def eat(self): 
        
        with ui.context.client:
            asyncio.create_task(self.foodbowl())
    
    async def eatasync(self):
        self.readytoeat = True
        self.food_mode = 'eat'
        
        await asyncio.gather(
            self.cameraAction(-15, -25, 2.0, speed=2.0),
            self.moveCat(45, 61, speed=1.5, run_anim="walk")
        )
        ui.navigate.to('/food')
    
    async def waterbowl(self):
        self.food_mode = 'drink'
        
        await asyncio.gather(
            self.cameraAction(-5, -5, 1.5, speed=2.0),
            self.moveCat(42, 60, speed=1.5, run_anim="walk")
        )
        
        ui.navigate.to('/food')

    async def wardrobe(self): 
        ui.navigate.to('/wardrobe')

    async def dashboard(self): 
        ui.navigate.to('/dashboard')
    
    def dashboard_page(self):
        self.current_room = 'dashboard'      
        self.anim_arrays = {}
        with ui.element('div').classes('fixed inset-0 pixelated').style(' overflow:hidden; height: 104vh; display: flex; align-items: center; justify-content: center; font-family: runescape; background-color: #f0e4d7; flex-direction: column;'):
            with ui.element('div').classes('absolute right-6 top-3 z-50'):
                self.toolbar_right("dashboard")
            
            ui.label('Dashboard').style('font-size: 3rem; color: #333; text-align: center; width:100vw; margin-top: 20px;')
            
            
            self.dashwrapper = ui.scroll_area().classes('w-full h-full p-10')
            with self.dashwrapper:
                asyncio.create_task(self.dashinternal())
            
    @ui.refreshable
    async def dashfetching(self):
        global values
        dbstats = await getdb_stats()
        skin_data = await get_skin_distribution()
        vital_data = await get_average_stats()
        top_players = await get_top_players(10)
        all_users = await User.all().values()
        values = [dbstats, skin_data, vital_data, top_players, all_users]
        
    
    async def dashinternal(self):
        global values
        with self.dashwrapper:    
            spinner = ui.spinner(size='3em').classes('absolute-center')
            
            await self.dashfetching()

            spinner.delete()
            
            @ui.refreshable
            async def restofthedb():
                try:
                    await self.dashfetching()
                    
                    with ui.grid(columns=2).classes('w-full gap-6').style('grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));'):

                        with ui.column().classes('w-full gap-6'):
                            
                            with ui.grid(columns=4).classes('w-full gap-4').style('grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));'):
                                def stat_card(title, value, color_class):
                                    with ui.card().classes(f'w-full p-4 shadow-sm border-4 {color_class}'):
                                        ui.label(title).classes('text-gray-500 text-lg font-bold uppercase')
                                        ui.label(str(value)).classes('text-4xl font-bold text-gray-800')

                                stat_card('Total Users', values[0]['total_users'], 'border-blue-500')
                                stat_card('Online Now', values[0]['online_users'], 'border-green-500')
                                stat_card('Economy ($)', f"${values[0]['total_money']:,}", 'border-yellow-500')
                                stat_card('Avg Health', f"{values[0]['avg_health']}%", 'border-red-500')

                            pie_data = [{"value": x['count'], "name": x['equipped_skin']} for x in values[1]]
                            chart_bg = '#bd9a8e'
                            text_color = '#3e2b26'
                            color_palette = ['#7c5a52', '#a6857a', '#cbb0a8', '#f0e4d7', '#5c4033', '#8b5e3c', '#b07e5a', '#d4a488', '#e8cfc1', '#3e2b26']

                            with ui.grid(columns=2).classes('w-full gap-4 h-80').style('grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));'):
                                with ui.card().classes('w-full h-full pixelated pixel-3d').style('background-color: #bd9a8e;'):
                                    ui.label('Skin Distribution').classes('text-lg font-bold mb-2')
                                    ui.echart({
                                        'backgroundColor': chart_bg,
                                        'color': color_palette,
                                        'textStyle': {'fontFamily': 'runescape', 'color': text_color, 'fontSize' : 14},
                                        'tooltip': {'trigger': 'item', 'backgroundColor': '#f0e4d7', 'textStyle': {'color': '#000', 'fontSize' : 16}},
                                        'legend': {'type': 'scroll', 'bottom': '0', 'textStyle': {'color': text_color, 'fontSize' : 12}}, 
                                        'series': [{
                                            'name': 'Skins',
                                            'type': 'pie',
                                            'radius': ['40%', '65%'], 
                                            'center': ['50%', '45%'],
                                            'itemStyle': {'borderRadius': 4, 'borderColor': '#7c5a52', 'borderWidth': 2},
                                            'label': {'show': False}, 
                                            'data': pie_data
                                        }]
                                    }).classes('h-full w-full')

                                with ui.card().classes('w-full h-full pixelated pixel-3d').style('background-color: #bd9a8e;'):
                                    ui.label('Average Stats').classes('text-lg font-bold mb-2')
                                    ui.echart({
                                        'backgroundColor': chart_bg,
                                        'textStyle': {'fontFamily': 'runescape', 'color': text_color},
                                        'tooltip': {'trigger': 'axis', 'backgroundColor': '#f0e4d7', 'textStyle': {'color': '#000'}},
                                        'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
                                        'xAxis': {'type': 'category', 'data': ['Hunger', 'Thirst', 'Sleep', 'Happy'], 'axisLabel': {'color': text_color}, 'axisLine': {'lineStyle': {'color': '#7c5a52'}}},
                                        'yAxis': {'type': 'value', 'max': 100, 'axisLabel': {'color': text_color}, 'splitLine': {'lineStyle': {'color': '#a6857a', 'type': 'dashed'}}},
                                        'series': [{
                                            'data': values[2],
                                            'type': 'bar',
                                            'showBackground': True,
                                            'backgroundStyle': {'color': 'rgba(124, 90, 82, 0.2)'},
                                            'itemStyle': {'color': '#7c5a52', 'borderColor': '#3e2b26', 'borderWidth': 1} 
                                        }]
                                    }).classes('h-full w-full text-xl').style('font-family: runescape;')

                            with ui.card().classes('w-full pixelated pixel-3d').style('background-color: #bd9a8e; color: #3e2b26; --q-primary: #7c5a52; '):
                                ui.label('Richest Players').classes('text-lg font-bold mb-2')
                                ui.table(
                                    columns=[
                                        {'name': 'username', 'label': 'Username', 'field': 'username', 'align': 'left'},
                                        {'name': 'money', 'label': 'Money', 'field': 'money', 'sortable': True},
                                        {'name': 'title', 'label': 'Title', 'field': 'title', 'align': 'left'},
                                    ],
                                    rows=values[3],
                                    pagination=5
                                ).classes('w-full').props('flat bordered separator="cell"').style('background-color: #bd9a8e; color: #3e2b26; --q-primary: #bd9a8e; font-size: 1.1rem; font-weight: bold; font-family: runescape;')

                        with ui.column().classes('w-full h-full'):
                            with ui.row().classes('w-full h-6 space-between mb-4'):
                                ui.label('Master User List (Editable)').style('color: #7c5a52').classes('text-2xl font-bold mb-0')
                                ui.button('Refresh Data', on_click=lambda: restofthedb.refresh()).classes('bg-blue-600 text-white pixelated pixel-3d px-4 py-2 rounded hover:bg-blue-700')
                            
                            grid = ui.aggrid({
                                'columnDefs': [
                                    {'headerName': 'ID', 'field': 'id', 'width': 60, 'sortable': True},
                                    {'headerName': 'Username', 'field': 'username', 'sortable': True, 'filter': True, 'editable': True},
                                    {'headerName': 'Email', 'field': 'email', 'sortable': True, 'filter': True, 'editable': True},
                                    {'headerName': 'Skin', 'field': 'equipped_skin', 'sortable': True, 'width':120, 'editable': True, 'cellEditor': 'agSelectCellEditor', 'cellEditorParams': {'values': skinfolderarray}},
                                    {'headerName': 'Money', 'field': 'money', 'sortable': True, 'editable': True},
                                    {'headerName': 'Hunger', 'field': 'hunger', 'width': 100, 'editable': True},
                                    {'headerName': 'Health', 'field': 'health', 'width': 90, 'editable': True},
                                    {'headerName': 'Admin', 'field': 'isAdmin', 'width': 90, 'editable': True},
                                    {'headerName': '🟢', 'field': 'isLoggedIn', 'width': 70},
                                ],
                                'rowData': values[4],
                                'pagination': True,
                                'paginationPageSize': 20,
                                'defaultColDef': {
                                    'resizable': True,
                                    'cellStyle': {'borderRight': '1px solid #a6857a'},   
                                }
                            }, theme='balham').classes('w-full pixelated pixel-3d text-2xl')
                            
                            grid.style(
                                'height: 80vh; ' 
                                'border: 4px solid #7c5a52; '
                                'color: #3e2b26; '
                                '--q-primary: #7c5a52; '
                                '--ag-background-color: #bd9a8e; '
                                '--ag-foreground-color: #361007; '
                                '--ag-header-background-color: #5A5A84; '
                                '--ag-header-foreground-color: #F0E4D7; '
                                '--ag-row-hover-color: #6e4638; ' 
                                '--ag-odd-row-background-color: #bd9a8e; '
                                'font-family: runescape; '
                                '--ag-font-family: runescape; '
                                '--ag-header-font-size: 1.2rem; '
                                '--ag-data-font-size: 1.1rem; '
                            )
                            grid.on('cellValueChanged', self.handle_grid_update)
                    
                    
                    with ui.card().classes('w-full p-6 border-4 border-blue-500 pixelated pixel-3d').style('background-color: #bd9a8e; color: #3e2b26;'):
                        ui.label('Game Difficulty & Balance').classes('text-l font-bold mb-4').style('font-family: runescape;')
                        
                        def style_slider(slider_element):
                            slider_element.props('label-always snap color="brown-10" track-color="orange-3" thumb-size="20px" track-size="8px"') \
                                            .classes('w-full mt-2 mb-6') \
                                            .style('font-family: runescape;')

                        ui.label(f'Sleep Recovery Speed: {SLEEP_DURATION_HOURS} Hours to 100%').classes('font-bold').bind_text_from(globals(), 'SLEEP_DURATION_HOURS', backward=lambda x: f'Sleep Recovery Speed: {x} Hours to 100%')
                        style_slider(ui.slider(min=1, max=12, step=1, value=SLEEP_DURATION_HOURS, on_change=self.set_sleep_duration))
                        
                        ui.separator().classes('bg-brown-800 my-4')

                        with ui.grid(columns=2).classes('w-full gap-8'):
                            
                            with ui.column().classes('w-full'):
                                ui.label('Hunger Duration').classes('font-bold text-xl')
                                ui.label(f'{HUNGER_HOURS} hours from Full to Starving').classes('text-l font-bold opacity-70').bind_text_from(globals(), 'HUNGER_HOURS', backward=lambda x: f'{x} hours from Full to Starving')
                                style_slider(
                                    ui.slider(min=1, max=48, step=1, value=HUNGER_HOURS, on_change=update_hunger_settings)
                                    .bind_value(globals(), 'HUNGER_HOURS')
                                )

                            with ui.column().classes('w-full'):
                                ui.label('Thirst Duration').classes('font-bold text-xl')
                                ui.label(f'{THIRST_HOURS} hours from Full to Dehydrate').classes('text-l font-bold opacity-70').bind_text_from(globals(), 'THIRST_HOURS', backward=lambda x: f'{x} hours from Full to Dehydrate')
                                style_slider(
                                    ui.slider(min=1, max=48, step=1, value=THIRST_HOURS, on_change=update_thirst_settings)
                                    .bind_value(globals(), 'THIRST_HOURS')
                                )

                            with ui.column().classes('w-full'):
                                ui.label('Energy Duration').classes('font-bold text-xl')
                                ui.label(f'{SLEEP_DECAY_HOURS} hours from Awake to Exhausted').classes('text-l font-bold opacity-70').bind_text_from(globals(), 'SLEEP_DECAY_HOURS', backward=lambda x: f'{x} hours from Awake to Exhausted')
                                style_slider(
                                    ui.slider(min=1, max=72, step=1, value=SLEEP_DECAY_HOURS, on_change=update_sleep_decay_settings)
                                    .bind_value(globals(), 'SLEEP_DECAY_HOURS')
                                )

                            with ui.column().classes('w-full'):
                                ui.label('Hygiene Duration (Avg)').classes('font-bold text-xl')
                                ui.label(f'{CLEAN_HOURS} hours on average until cat gets dirty').classes('text-l font-bold opacity-70').bind_text_from(globals(), 'CLEAN_HOURS', backward=lambda x: f'{x} hours on average until cat gets dirty')
                                style_slider(
                                    ui.slider(min=1, max=72, step=1, value=CLEAN_HOURS, on_change=update_clean_settings)
                                    .bind_value(globals(), 'CLEAN_HOURS')
                                )
                                
                                         
                                    

                except Exception as e:
                    ui.notify(f"Error rendering dashboard: {e}").classes('text-red-500 text-xl font-bold')
                    print(e) 

            await restofthedb()
    
    async def handle_grid_update(self, e):
        row_data = e.args['data']
        new_value = e.args['newValue']
        field = e.args['colId']
        user_id = row_data['id']

        if field in ['money', 'hunger', 'thirst', 'sleep', 'health']:
            try:
                new_value = int(new_value)
            except ValueError:
                ui.notify(f"Invalid value for {field}", color='negative')
                return

        await User.filter(id=user_id).update(**{field: new_value})
        ui.notify(f"Updated User {user_id}: {field} -> {new_value}", color='positive')  
    
    def settings_page(self):
        self.current_room = 'settings'      
        self.anim_arrays = {}
        with ui.element('div').classes('fixed inset-0 pixelated').style(' overflow:hidden; height: 104vh; display: flex; align-items: center; justify-content: center; font-family: runescape; background-color: #f0e4d7; flex-direction: column;'):
            with ui.element('div').classes('absolute right-6 top-20 z-50'):
                self.toolbar_right()
            ui.label('Settings page').style('font-size: 3rem; color: #333; text-align: center; width:100vw; margin-top: 20px;')
            with ui.grid(columns=2).style('gap: 20px; width: 70vw; margin: 50px 0; ').classes('items-center'):
                ui.label('Change Username')
                userchfld = ui.input(value=self.user.username).style('font-size: 1.2rem; padding: 10px; width: 100%; border: 2px solid #ccc; border-radius: 5px;')#.bind_value_from(self.user, 'username')
                
                ui.label('Current Password')
                oldpwdfld = ui.input(password=True).style('font-size: 1.2rem; padding: 10px; width: 100%; border: 2px solid #ccc; border-radius: 5px;')
                
                ui.label('New Password')
                pwdchfld = ui.input(password=True).style('font-size: 1.2rem; padding: 10px; width: 100%; border: 2px solid #ccc; border-radius: 5px;')
                
                ui.label('Change Email')
                mailchfld = ui.input(value=self.user.email).style('font-size: 1.2rem; padding: 10px; width: 100%; border: 2px solid #ccc; border-radius: 5px;')#.bind_value_from(self.user, 'email')

                ui.label ('Log Out of your account')
                ui.button('Log Out', color='#bd9a8e').on('click', lambda: self.logout())

                ui.label('Mouse sensitivity')
                ui.slider(min=0.5, max=2.0, value=self.cam_zoom_sens, step=0.1).bind_value_to(self, 'cam_zoom_sens').style('color: primary;')
            
            ui.button('Confirm and Save Changes', color='#7c5a52').style('color: white; font-family: runescape; font-size: 1.2rem; padding: 10px; border-radius: 5px;').classes('pixel-border pixel-3d mt-4 w-50').on('click', lambda: self.settingsconfirmed(oldpwdfld.value, userchfld.value, pwdchfld.value, mailchfld.value))
   
    async def settingsconfirmed(self, oldpassword, username, password, email):
        
        cryptold = bcrypt.hashpw(oldpassword.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cryptnew = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        valid_data = self.UserCreate(
                username=username,
                password=password,
                email=email
            )
        try:
            bcrypt.checkpw(cryptold.encode('utf-8'), self.user.password.encode('utf-8'))
            self.user.password = cryptnew
        
        except ValidationError as e:
            error_msg = e.errors()[0]['msg']
            ui.notify(f"Registration Failed: {error_msg}", color='negative')
        
        except Exception as e:
            ui.notify(f"Error: {str(e)}", color='negative')
        
        self.user.username = valid_data.username
        
        self.user.email = valid_data.email
        asyncio.create_task(self.user.save())
        ui.notify('Settings have been saved!', color='green')

    def button(self, name: str):
        with ui.element('div').classes('inline-block'):
            with ui.element('div').classes('relative w-16 h-16 cursor-pointer').on('click', lambda e, n=name: self.press(n)):
                buttonUp = ui.image("/textures/button1.png").classes('absolute inset-0 w-full h-full object-contain opacity-100')
                buttonDown = ui.image("/textures/button2.png").classes('absolute inset-0 w-full h-full object-contain opacity-0')
                icon = ui.image(f"/textures/{name}.png").style(
                    'position:absolute; left:50%; top:50%; transform: translate(-50%, -55%) perspective(600px);'
                    'transform-origin: center bottom; width: 2.5rem; height: 2.5rem; object-fit: contain; pointer-events:none; transition: transform 90ms;'
                )
                self.buttons[name] = (buttonUp, buttonDown, icon)
                if self.current_room == name:
                    buttonUp.classes(remove='opacity-100', add='opacity-0')
                    buttonDown.classes(remove='opacity-0', add='opacity-100')
                    icon.style('transform: translate(-50%, -55%) perspective(600px) scaleY(1.02);')

    def toolbar_right(self, page=None):
        if page == 'dashboard':
            with ui.row().classes('gap-3 z-50'):
                self.button("home")
                self.button("shower")
                self.button("sleep")
                self.button("foodbowl")
                self.button("wardrobe")
                self.button("settings")
                if self.user.isAdmin:
                    self.button("dashboard")
        else:
            with ui.column().classes('gap-3 z-50'):
                self.button("home")
                self.button("shower")
                self.button("sleep")
                self.button("foodbowl")
                self.button("wardrobe")
                self.button("settings")
                if self.user.isAdmin:
                    self.button("dashboard")

    # def bottom_right_button(self):
    #     with ui.element('div').classes('relative w-32 h-32 cursor-pointer').style('background-color: #bd9a8e; border-radius: 30%; border: 4px solid #7c5a52;'):
    #         ui.image("/textures/swords.png").classes('w-24 h-24 cursor-pointer align-middle absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2').on('click', lambda: ui.notify('Battle button clicked'))

    async def foodbowl(self):
        if not self.readytoeat:
            await self.eatasync()
            return
        ui.navigate.to('/food')

    def bowlsUI(self):
        with ui.image(spriteHandler(261, 332, 53, 44, "Furnitures.png", scale=SPRITE_SCALE)).classes('object-contain absolute').style('left:5%; width:5vw;'):
            ui.element('div').classes('absolute cursor-pointer w-full h-full bg-transparent').on('click', self.foodbowl)
        with ui.image(spriteHandler(390, 332, 53, 44, "Furnitures.png", scale=SPRITE_SCALE)).classes('object-contain absolute').style('left:40%; top:35%; width:5vw;'):
            ui.element('div').classes('absolute cursor-pointer w-full h-full bg-transparent').on('click', self.waterbowl)

    def     bedUI(self):
        ui.image(spriteHandler(201, 137, 112, 83, "Furnitures.png", scale=SPRITE_SCALE)).classes('w-[10vw] object-contain')

    async def cycleclasses(self):
        classes = ['showerhandle1', 'showerhandle2', 'showerhandle3', 'showerhandle4']
        
        
        idx = 0
        while (self.water == True):
            self.canvas.classes(remove=classes[(idx -1) % len(classes)], add=classes[idx % len(classes)])
            idx += 1
            await asyncio.sleep(0.2)

    async def start_petting_game(self):
        if self.current_room != 'home':
            return
        if self.petting_mode: 
            return
            
        self.petting_mode = True
        
        self.petting_score = 0.0 
        self.game_score = 0      
        self.consecutive_misses = 0
        self.game_stats = {
            'perfect': 0,
            'okay': 0,
            'miss': 0,
            'max_combo': 0,
            'current_combo': 0
        }
        
        self.active_targets = []
        
        if self.move_task and not self.move_task.done():
            self.move_task.cancel()
        
        ui.add_head_html('''
            <style>
                @keyframes pet_wiggle {
                    0% { transform: translate(-50%, -50%) rotate(-10deg) scale(1.0); }
                    50% { transform: translate(-50%, -50%) rotate(10deg) scale(1.1); }
                    100% { transform: translate(-50%, -50%) rotate(-10deg) scale(1.0); }
                }
            </style>
        ''')

        self.petting_overlay = ui.element('div').classes('absolute inset-0 z-40 w-full h-full pointer-events-none')
        
        with self.petting_overlay:
            with ui.element('div').classes('absolute right-20 bg-black/30 border-2 border-white rounded').style('width:20vh; height:3vw; top:45vh; right:10vw; transform: rotate(-90deg);'):
                self.score_bar = ui.linear_progress(value=0.0, show_value=False, color='pink').classes('absolute inset-0 w-full h-full')
            
            ui.image('static/hand.png').classes('absolute w-32 h-32 z-0 opacity-70 pointer-events-none') \
                .style('left: 60%; top: 65%; transform: translate(-50%, -50%); animation: pet_wiggle 0.6s infinite ease-in-out;')

            self.combo_label = ui.label('').classes('absolute text-4xl font-bold text-white drop-shadow-lg').style('left: 50%; top: 30%; transform: translate(-50%, -50%); font-family: runescape;')

        cat_size = 15 
        center_x = self.cat_x + (cat_size / 2)
        center_y = self.cat_y + (cat_size / 2)

        zoom_target_x = -center_x + 50 
        zoom_target_y = -center_y + 50
        
        await self.cameraAction(zoom_target_x, zoom_target_y, 2.5, speed=3.0)
        self.doAnim("pet", 0.3)
        self.rhythm_task = asyncio.create_task(self.rhythm_loop())

    async def stop_petting_game(self, finished=False):
        self.petting_mode = False
        if self.rhythm_task:
            self.rhythm_task.cancel()
        
        if self.petting_overlay:
            self.petting_overlay.delete()
            self.petting_overlay = None
        
        for t in self.active_targets:
            try: t['el'].delete()
            except: pass
        self.active_targets = []
        
        if finished:
            total_hits = self.game_stats['perfect'] + self.game_stats['okay'] + self.game_stats['miss']
            if total_hits > 0:
                accuracy = ((self.game_stats['perfect'] * 1.0) + (self.game_stats['okay'] * 0.5)) / total_hits
            else:
                accuracy = 0
            
            acc_percent = accuracy * 100
            
            if acc_percent == 100: rank = "SS"
            elif acc_percent >= 95: rank = "S"
            elif acc_percent >= 90: rank = "A"
            elif acc_percent >= 80: rank = "B"
            elif acc_percent >= 70: rank = "C"
            else: rank = "D"
            
            display_score = min(10000, self.game_score)
            with self.room:
                with ui.dialog() as dialog, ui.card().style('background-color: #FFF8E1; border: 4px solid #F59E0B; min-width: 400px; text-align: center; padding: 20px;'):
                    ui.label('PETTING COMPLETE!').classes('text-3xl font-bold mb-2').style('font-family: runescape; color: #D97706;')
                    
                    rank_color = {'SS': '#00e676', 'S': '#00e676', 'A': '#2979ff', 'B': '#ffea00', 'C': '#ff9100', 'D': '#ff3d00'}[rank]
                    ui.label(rank).style(f'font-size: 6rem; line-height: 1; font-weight: bold; font-family: runescape; color: {rank_color}; text-shadow: 3px 3px 0 #000;')
                    
                    ui.label(f'Score: {display_score}').classes('text-2xl font-bold mt-2').style('font-family: runescape;')
                    ui.label(f'Accuracy: {acc_percent:.2f}%').classes('text-lg text-gray-600')
                    
                    ui.separator().classes('my-4')
                    
                    with ui.grid(columns=3).classes('w-full text-center'):
                        with ui.column():
                            ui.label('Perfect').classes('font-bold text-green-600')
                            ui.label(str(self.game_stats['perfect'])).classes('text-xl')
                        with ui.column():
                            ui.label('Okay').classes('font-bold text-yellow-600')
                            ui.label(str(self.game_stats['okay'])).classes('text-xl')
                        with ui.column():
                            ui.label('Miss').classes('font-bold text-red-600')
                            ui.label(str(self.game_stats['miss'])).classes('text-xl')
                    
                    ui.label(f'Max Combo: {self.game_stats["max_combo"]}').classes('mt-4 text-lg font-bold text-blue-800')
                    
                    reward = int(display_score / 100)
                    if reward > 0:
                        self.user.money += reward
                        asyncio.create_task(self.user.save())
                        ui.label(f'+{reward} Coins').classes('text-xl font-bold text-green-700 animate-bounce mt-2')

                    ui.button('Close', on_click=dialog.close).classes('mt-6 w-full').style('background-color: #F59E0B; color: white; font-family: runescape; border: 2px solid #78350F;')
            
            dialog.open()
        
        await self.cameraAction(0, 0, 1.0, speed=2.0)

    def update_petting_score(self, percent_add, raw_points=0):
        self.petting_score += (percent_add / 100.0)
        self.petting_score = max(0.0, min(1.0, self.petting_score))
        
        if self.score_bar:
            self.score_bar.value = self.petting_score
            
        self.game_score += raw_points
            
        if self.petting_score >= 1.0:
            asyncio.create_task(self.stop_petting_game(finished=True))

    async def rhythm_loop(self):
        try:
            while self.petting_mode:
                # if random.random() < 0.08:
                #     await self.stroke_phase()
                
                num = random.randint(1, 3)
                for _ in range(num):
                    if not self.petting_mode: break
                    self.spawn_rhythm_target()
                    await asyncio.sleep(random.uniform(0.4, 0.8))
                
                if not self.petting_mode: break
                await asyncio.sleep(random.uniform(0.5, 1.5))
        except asyncio.CancelledError:
            pass

    def show_hit_feedback(self, target, result):

        config = {
            'perfect': {'text': 'PERFECT!', 'bg': 'bg-green-500', 'score': '+4'},
            'average': {'text': 'OKAY', 'bg': 'bg-yellow-500', 'score': '+2'},
            'miss':    {'text': 'MISS', 'bg': 'bg-red-600', 'score': '-6'}
        }
        
        data = config.get(result, config['miss'])
        
        with self.petting_overlay:
            with ui.element('div').classes(f"absolute w-16 h-16 rounded-full flex flex-col items-center justify-center {data['bg']} z-50 shadow-lg") \
                .style(f'left: {target.x}%; top: {target.y}%; transform: translate(-50%, -50%); opacity: 1; transition: all 0.5s ease-out;') as feedback_el:
                
                ui.label(data['text']).classes('text-white font-bold text-xs drop-shadow-md')

        async def animate_feedback():
            await asyncio.sleep(0.05)
            feedback_el.style(f'left: {target.x}%; top: {target.y - 5}%; transform: translate(-50%, -50%) scale(1.2); opacity: 0;')
            await asyncio.sleep(0.5)
            feedback_el.delete()

        asyncio.create_task(animate_feedback())
            
    def spawn_rhythm_target(self):
        key_map = {
            'd': {'color': 'red-500', 'code': 'd'},
            'f': {'color': 'green-500', 'code': 'f'},
            'k': {'color': 'yellow-500', 'code': 'k'},
            'l': {'color': 'blue-500', 'code': 'l'}
        }
        key_char = random.choice(list(key_map.keys()))
        data = key_map[key_char]
        
        pos_x = 50 + random.uniform(-15, 15) 
        pos_y = 50 + random.uniform(-15, 15)
        
        with self.petting_overlay:
            container = ui.element('div').classes('absolute w-16 h-16 pointer-events-auto cursor-pointer').style(f'left: {pos_x}%; top: {pos_y}%; transform: translate(-50%, -50%);')
            
            with container:
                prog = ui.circular_progress(value=0, min=0, max=1, show_value=False, color=data['color']) \
                    .classes('absolute inset-0 w-full h-full') \
                    .props('animation-speed="0" thickness=0.2') 
                
                ui.label(data['code'].upper()).classes('absolute inset-0 flex items-center justify-center font-bold text-white text-xl drop-shadow-md').style('background-color: rgba(0, 0, 0, 0.3); border-radius: 50%; width: 100%; height: 100%;')
        
        curtarget = RhythmTarget(key_char, prog, container, pos_x, pos_y)
        
        container.on('click', lambda: self.handle_click_input(curtarget))
        
        self.active_targets.append(curtarget)
        asyncio.create_task(self.animate_target(curtarget))
        
    # target = {
            #     'el': container,
            #     'prog': prog,
            #     'key': key_char,
            #     'start_time': time.time(),
            #     'clicked': False
            # }
            
    def handle_miss(self, target):
        self.game_stats['miss'] += 1
        self.game_stats['current_combo'] = 0
        self.consecutive_misses += 1
        
        if self.combo_label: self.combo_label.set_text('')
        
        self.update_petting_score(-5, 0)
        self.show_hit_feedback(target, 'miss')
        
        if self.consecutive_misses >= 5:
            asyncio.create_task(self.fail_game())        
    
    async def fail_game(self):
        self.petting_mode = False
        if self.rhythm_task: self.rhythm_task.cancel()
        if self.petting_overlay: self.petting_overlay.delete()
        
        for t in self.active_targets:
            try: t['el'].delete()
            except: pass
        self.active_targets = []

        self.doAnim("walk", 0.15)
        
        run_x = 40 if self.cat_x > 50 else 60
        run_y = 40 if self.cat_y > 50 else 60
        
        await self.cameraAction(0, 0, 1.0, speed=4.0)
        await self.moveCat(run_x, run_y, speed=3.0, run_anim="walk", end_anim="idle")
        
        with ui.dialog() as dialog, ui.card().style('border: 4px solid red; background-color: #fce8e8; text-align: center;'):
            ui.label("GAME OVER!").classes('text-3xl font-bold text-red-600 mb-2').style('font-family: runescape;')
            ui.label("The cat got annoyed and ran away!").classes('text-lg')
            ui.label(f"You missed 5 times in a row.").classes('text-sm text-gray-600')
            ui.button('Okay...', on_click=dialog.close).classes('mt-4 bg-red-500 text-white w-full')
        
        dialog.open()
    
    async def animate_target(self, target):
        duration = 1.2
        late_duration = 0.4
        
        start = target.start_time
        while True:
            elapsed = time.time() - start
            if target.clicked: break
            
            val = elapsed / duration
            if val >= 1.0: break
            
            target.prog.value = val
            await asyncio.sleep(0.016)
            
        if not target.clicked and self.petting_mode:
            target.prog.value = 0
            target.prog.props(f'color="red-14"')
                    
            late_start = time.time()
            while True:
                elapsed_late = time.time() - late_start
                if target.clicked: break
                
                val = elapsed_late / late_duration
                if val >= 1.0: 
                    self.handle_miss(target)
                    target.el.style('opacity: 0;')
                    break
                
                target.prog.value = val
                await asyncio.sleep(0.016)

        if target in self.active_targets:
            self.active_targets.remove(target)
        
        await asyncio.sleep(0.1) 
        try: target.el.delete()
        except: pass

    def handle_rhythm_input(self, key):
        now = time.time()
        best_target = None
        
        for t in self.active_targets:
            if t.key == key and not t.clicked:
                best_target = t
                break
        
        if best_target:
            self.process_hit(best_target, now)
        else:
            self.update_petting_score(-6)

    def handle_click_input(self, target):
        if not target.clicked:
            self.process_hit(target, time.time())

    def process_hit(self, target, hit_time):
        target.clicked = True
        elapsed = hit_time - target.start_time
        
        self.consecutive_misses = 0
        
        is_hit = False
        
        if 1.1 <= elapsed <= 1.3:
            self.game_stats['perfect'] += 1
            self.game_stats['current_combo'] += 1
            combo_mult = min(5, 1 + (self.game_stats['current_combo'] // 10)) 
            points = 300 * combo_mult
            
            self.update_petting_score(4, points) 
            self.show_hit_feedback(target, 'perfect')
            is_hit = True
            
        elif (0.9 <= elapsed < 1.1) or (1.3 < elapsed <= 1.5):
            self.game_stats['okay'] += 1
            self.game_stats['current_combo'] += 1
            combo_mult = min(5, 1 + (self.game_stats['current_combo'] // 10))
            points = 100 * combo_mult
            
            self.update_petting_score(2, points) 
            self.show_hit_feedback(target, 'average')
            is_hit = True
            
        else:
            self.handle_miss(target)
            
        if is_hit:
            if self.game_stats['current_combo'] > self.game_stats['max_combo']:
                self.game_stats['max_combo'] = self.game_stats['current_combo']
                
            if self.combo_label and self.game_stats['current_combo'] > 1:
                self.combo_label.set_text(f"{self.game_stats['current_combo']}x")
                self.combo_label.classes(remove='scale-100', add='scale-125')
                ui.timer(0.1, lambda: self.combo_label.classes(remove='scale-125', add='scale-100') if self.combo_label else None)
            
        target.el.style('opacity: 0;')

    # async def stroke_phase(self):
    #     self.stroke_phase_active = True
    #     self.stroke_counter = 0
        
    #     await asyncio.sleep(0.8)
        
    #     if not self.petting_mode: return

    #     with self.petting_overlay:
    #         arrow = ui.label('↕').style('font-size: 5rem; color: white; left: 50%; top: 50%; position: absolute; transform: translate(-50%, -50%); text-shadow: 2px 2px 4px #000;')
        
    #     start_time = time.time()
    #     while time.time() - start_time < 3.0:
    #         if not self.petting_mode: break
    #         await asyncio.sleep(0.1)
        
    #     arrow.classes('glow-effect')
    #     await asyncio.sleep(0.5)
    #     arrow.delete()
        
    #     await asyncio.sleep(0.8)
    #     self.stroke_phase_active = False


    def room_content(self):
        with ui.element('div').classes('absolute cursor-pointer z-20 pointer-events-auto') \
            .style('left: 48%; top: 40%; width: 20%; height: 18%;') \
            .on('click.stop', self.sleep):
            self.bedUI()

        with ui.element('div').classes('relative').style('left: 35%; top: 72.5%; width: 20%; height: 10%;'):
            self.bowlsUI()
        
        if self.user.isSleeping:
            self.cat_x = 53
            self.cat_y = 34
            initial_anim = "sleep"
            
            self.cam_x = -15
            self.cam_y = -15
            self.cam_zoom = 2.0
        else:
            initial_anim = "idle"
            self.cam_x = 0
            self.cam_y = 0
            self.cam_zoom = 1.0

        self.cat = ui.element('div').classes('absolute z-30').style(
            f'left:{self.cat_x}%; top:{self.cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;').on('click.stop', self.start_petting_game) 
        
        with self.cat:
            self.cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
            with self.cat_visuals:
                self.Preload(f"{self.user.equipped_skin}/sittingb.png", 2, "idle")
                self.Preload(f"{self.user.equipped_skin}/Idle2Catb.png", 13, "pet")
                self.Preload(f"{self.user.equipped_skin}/RunCatb.png", 6, "walk")
                self.Preload(f"{self.user.equipped_skin}/JumpCatb.png", 12, "jump")
                self.Preload(f"{self.user.equipped_skin}/SleepCatb.png", 2, "sleep")
                
        ui.timer(0.1, lambda: self.doAnim(initial_anim, 0.35), once=True)
        self.update_transform()
        
        if not self.user.isSleeping:
            ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{self.cat_visuals.id}")'), once=True)
        else:
            self.set_cat_orientation(True)
        
    def set_sleep_duration(self, e):
        global SLEEP_DURATION_HOURS
        SLEEP_DURATION_HOURS = e.value

    def baseui(self, room_texture='Room.png', bg='bg-blue-200'):
        self.setup_lifecycle_hooks()
        if self.user.isSleeping and self.user.sleep_start_time:
            print('true')
            now = datetime.now(timezone.utc)
            
            start_time = self.user.sleep_start_time
            
            diff = now - start_time
            seconds_passed = diff.total_seconds()
            
            total_seconds_needed = SLEEP_DURATION_HOURS * 3600
            sleep_gained = (seconds_passed / total_seconds_needed) * 100
            
            self.user.sleep = min(100.0, self.user.sleep_stored_val + sleep_gained)
            asyncio.create_task(self.user.save())
        if hasattr(self, '_stat_timer') and self._stat_timer:
            self._stat_timer.cancel()
            self._stat_timer = None
        with ui.element('div').classes(f'fixed inset-0 {bg} overflow-hidden pixelated'):
            with ui.element('div').classes('absolute left-6 top-6 z-50'):
                self.hud_top_left()
            with ui.element('div').classes('absolute left-6 top-40 z-50'):
                self.stats_left()
            with ui.element('div').classes('absolute right-6 top-20 z-50'):
                self.toolbar_right()
            # with ui.element('div').classes('absolute right-8 bottom-8 z-50'):
            #     self.bottom_right_button()
            with ui.element('div').classes('absolute left-10 bottom-20 z-50'):
                self.resetbut()
            with ui.element('div').classes('absolute inset-0 overflow-hidden'):
                ui.timer(0.1, lambda: self.newcommer_banner(), once=True)
            
            room_wrapper = ui.element('div').classes('absolute inset-0 flex items-center justify-center z-0 pointer-events-none')
            with room_wrapper:
                self.canvas = ui.element('div').classes('relative w-[min(50vw,1800px)] aspect-[1/1] bg-transparent pointer-events-auto').style('transform-origin: center center; transition: transform 80ms ease-out;')
                self.canvas.on('wheel', self.on_wheel)
                
                with self.canvas:
                    if room_texture in ['bigbowl.png', 'waterbowl.png']:
                        self.roomim = ui.image(f'/textures/{room_texture}').classes('absolute inset-0 w-full h-full object-contain select-none pointer-events-none')
                    else:
                        self.roomim = ui.interactive_image(f'/textures/{room_texture}', on_mouse=self.mouse_handler, events=['mousedown', 'mouseup'], cross=False, sanitize=False)
                    
                    self.room = ui.element('div').classes('absolute inset-0 pointer-events-none')
        
        self._stat_timer = ui.timer(0.1, self.statuscheck)
        self.loading_overlay()

    async def mouse_handler(self, e: events.MouseEventArguments):
        if self.current_room == 'food': 
            return

        click_x_pct = (e.image_x / roomsize) * 100
        click_y_pct = (e.image_y / roomsize) * 100

        cat_size = 15 
        if (self.cat_x <= click_x_pct <= self.cat_x + cat_size) and (self.cat_y <= click_y_pct <= self.cat_y + cat_size):
            await self.start_petting_game()
            return

        if self.petting_mode:
            return

        if self.move_task and not self.move_task.done():
            self.move_task.cancel()
        
        if self.user.isSleeping:
            self.user.isSleeping = False
            self.user.sleep_start_time = None
            await self.user.save()
            self.cat.client.run_javascript('window.setTracking(true)')
            asyncio.create_task(self.cameraAction(0, 0, 1.0, speed=2.0))
       
        floor_min_y = 50   
        floor_max_y = 75  
        floor_min_x = 15   
        floor_max_x = 85   
        
        dest_x_pct = max(floor_min_x, min(floor_max_x, click_x_pct))
        dest_y_pct = max(floor_min_y, min(floor_max_y, click_y_pct))
        
        cat_width_pct = 16
        cat_height_pct = 16 

        target_x = dest_x_pct - (cat_width_pct / 2)
        target_y = dest_y_pct - (cat_height_pct) + 2
        
        self.roomim.content = f'<circle cx="{dest_x_pct * (roomsize/100)}" cy="{dest_y_pct * (roomsize/100)}" r="5" fill="none" stroke="#bd9a8e" stroke-width="3" />'
        ui.timer(0.5, lambda: setattr(self.roomim, 'content', ''), once=True)
        
        self.move_task = asyncio.create_task(self.moveCat(target_x, target_y, speed=1.3, run_anim="walk", end_anim="idle"))

    def check_and_refresh(self, ui_element, stat_name, current_val, sprite_name):
        if ui_element is None:
            return

        full = int(current_val) // 20
        half = 1 if int(current_val) % 20 >= 10 else 0
        visual_state = (full, half)

        if self.stat_cache.get(stat_name) != visual_state:
            self.stat_cache[stat_name] = visual_state
            ui_element.refresh(current_val, sprite_name)

    async def statuscheck(self):
        if not self.isloggedin:
            return
        
        if self.cam_x != 0.0 or self.cam_y != 0.0 or self.cam_zoom != 1.0:
            self.reseticon.classes(remove='opacity-0', add='opacity-100')
        else:
            self.reseticon.classes(remove='opacity-100', add='opacity-0')
        
        self.age_display.set_text(f"Age: {self.agecheck()}")    
        self.agetip.set_text(f'{self.agecheck(tooltip=True)}')
        
        self.user.hunger = max(0, self.user.hunger - hungerdecrement)
        self.user.thirst = max(0, self.user.thirst - thirstdecrement)

        if self.user.isSleeping:
            total_seconds = SLEEP_DURATION_HOURS * 3600
            inc_per_tick = (100 / total_seconds) * 0.1
            self.user.sleep = min(100, self.user.sleep + inc_per_tick)
            
            time_left = get_remaining_time_str(self.user.sleep, SLEEP_DURATION_HOURS, is_filling=True)
            self.sleep_timer_label.set_text(f"Waking up in: {time_left}")
        else:
            self.user.sleep = max(0, self.user.sleep - sleepdecrement)
            self.sleep_timer_label.set_text("")

        if random.randint(1, cleanchance) == 1:
             self.user.cleanliness = False

        damage_multiplier = 0
        if self.user.hunger <= 0: damage_multiplier += 1
        if self.user.thirst <= 0: damage_multiplier += 1
        if self.user.sleep <= 0:  damage_multiplier += 1

        if damage_multiplier > 0:
            damage = HEALTH_DECAY_PER_TICK * damage_multiplier
            self.user.health = max(0, self.user.health - damage)
        else:
            self.user.health = min(100, self.user.health + HEALTH_REGEN_PER_TICK)

        await self.user.save()

        if hasattr(self, 'hud_health_bar') and self.hud_health_bar:
            self.hud_health_bar.value = self.user.health / 100.0
        if hasattr(self, 'hud_health_text') and self.hud_health_text:
            self.hud_health_text.set_text(str(int(self.user.health)))

        if hasattr(self, 'hud_energy_bar') and self.hud_energy_bar:
            self.hud_energy_bar.value = self.user.sleep / 100.0
        if hasattr(self, 'hud_energy_text') and self.hud_energy_text:
            self.hud_energy_text.set_text(str(int(self.user.sleep)))

        if hasattr(self, 'dirty_indicator'):
            if self.user.cleanliness == False:
                self.dirty_indicator.classes(remove='hidden')
            else:
                self.dirty_indicator.classes(add='hidden')

        if hasattr(self, 'hunger_tooltip') and self.hunger_tooltip:
            h_time = get_remaining_time_str(self.user.hunger, HUNGER_HOURS)
            self.hunger_tooltip.set_text(f"Starving in: {h_time}")

        if hasattr(self, 'thirst_tooltip') and self.thirst_tooltip:
            t_time = get_remaining_time_str(self.user.thirst, THIRST_HOURS)
            self.thirst_tooltip.set_text(f"Dehydrated in: {t_time}")
            
        self.update_stat_icons(self.hunger_container, self.user.hunger, "foodsprite.png")
        self.update_stat_icons(self.thirst_container, self.user.thirst, "watersprite.png")
        self.update_stat_icons(self.sleep_container,  self.user.sleep,  "sleepsprite.png")

    def logout(self):
        self.isloggedin = False
        app.storage.user.clear()
        if self.on_logout_callback:
            self.on_logout_callback(self.user.id)
            
        ui.navigate.to('/login')
    
    def resetbut(self):
        self.reseticon = ui.image(spriteHandler(487, 256, 22, 16, "catUI.png", scale=SPRITE_SCALE)).classes('w-10 h-10 cursor-pointer absolute opacity-0').style('left:0%; top:0%;').on('click', self.reset)

    async def reset(self):
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.cam_zoom = 1.0
        self.update_transform()
    
    def bathui(self):
        with self.room:
            with ui.element('div').classes('relative pointer-events-auto cursor-pointer').style('left: 20.5%; top: 31.9%; width: 11.1%; height: 33.3%; transform: rotate(-1deg);').on('click', lambda: self.showerhelp()):
                ui.image(spriteHandler(0, 0, 64, 192, "showersprite.png", scale=SPRITE_SCALE)).classes('object-contain absolute')
                self.Preload("realshower.png", 3, "showering", 64, 192)
            
            self.shower_progress_bar = ui.linear_progress(value=0.0, show_value=False, color='#90D5FF').classes('absolute w-100 z-50 h-20 instant-progress').style('left:95%; top:40%; transform: rotate(-90deg); border: 2px solid black;')
            with self.shower_progress_bar:
                self.showernum = ui.label('0%').classes('absolute-full flex flex-center text-black bg-transparent text-lg content-center h-5').style('left:50%; top:50%; transform: translate(-50%, -50%) rotate(90deg);;')
            
            self.cat = ui.element('div').classes('absolute pointer-events-auto').style(f'left:{self.cat_x}%; top:{self.cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;')
            
            with self.cat:
                self.cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
                with self.cat_visuals:
                    self.Preload(f"{self.user.equipped_skin}/SittingB.png", 2, "idle")
                    self.Preload("shower.png", 3, "shower")
                    self.Preload(f"{self.user.equipped_skin}/RunCatb.png", 6, "walk")
            
            ui.timer(0.1, lambda: self.doAnim("idle", 0.35), once=True)
            self.update_transform()
            
            ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{self.cat_visuals.id}")'), once=True)


    async def cleaningcat(self):
        progress = 0.0
    
        while self.water and progress < 1.0:
            overlap = await self.cat_visuals.client.run_javascript(f'return window.checkOverlap("c{self.cat_visuals.id}")')
            if overlap:
                progress += 0.04
                self.shower_progress_bar.value = progress
                self.showernum.set_text(f"{int(progress * 100)}%")
            await asyncio.sleep(0.2)    
        if progress >= 1.0:
            with self.cat_visuals.client:
                self.showerhelp(progress>=1.0)

    async def run_away_loop(self):
        while self.water:
            
            target_x = random.uniform(30, 60) 
            target_y = random.uniform(30, 60)
            run_speed = random.uniform(1.0, 2.0) 
            await self.moveCat(target_x, target_y, speed=run_speed, run_anim="walk", end_anim="walk", restore_tracking=False)
            await asyncio.sleep(0.3)

    def showerhelp(self, progress=False):
        frames = self.anim_arrays.get("showering")

        if self.water == False:
            self.water = True
            self.washstart = time.time()
            self.canvas.classes(add='showerhandle1 showerhandle2 showerhandle3 showerhandle4')
            if self.evading:
                self.evading.cancel()
            self.evading = asyncio.create_task(self.run_away_loop())
            asyncio.create_task(self.cleaningcat())
            asyncio.create_task(self.cycleclasses())
            
            if self.shower_task:
                self.shower_task.cancel()
            
            frames[0].classes(remove='opacity-0', add='opacity-100')
            self.shower_task = asyncio.create_task(self.cyclingSprite(frames, 0.2))
                
        elif( self.water == True and progress):
            timedif = time.time() - self.washstart
            mooddebuff = int(max(5, timedif / 2.0))
            self.water = False

            self.canvas.classes(remove='showerhandle1 showerhandle2 showerhandle3 showerhandle4')
            
            if self.shower_task:
                self.shower_task.cancel()
                self.shower_task = None
            self.evading.cancel()
            self.evading = None
            
            for f in frames:
                f.classes(remove='opacity-100', add='opacity-0')
            asyncio.create_task(self.moveCat(55, 50, speed=2, run_anim="walk", end_anim="idle", restore_tracking=True))
            with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
                # self.user.mood-=mooddebuff
                self.user.mood = 33
                self.user.cleanliness = True
                asyncio.create_task(self.user.save())
                asyncio.create_task(self.user.save())
                ui.label(f'You have cleaned your cat!\n Time taken: {int(timedif)} seconds.\n The subsequent debuff for washing is -{mooddebuff} mood points. Cats hate water!').classes('text-xl font-bold').style('font-family: runescape; color: #7c5a52;')
                ui.button('Go Home', on_click=dialog.close, color='rgb(255, 210, 194)').style('background-color: #7c5a52; color: white; font-family: runescape; font-size: 1.2vw; padding: 0.5vw 1vw; border-radius: none; margin-top: 1vw;').classes('pixel-border pixel-3d')
            async def dial():
                await dialog
                with dialog.client:
                    await self.home()
            asyncio.create_task(dial())
        
        else:
            self.water = False

            self.canvas.classes(remove='showerhandle1 showerhandle2 showerhandle3 showerhandle4')
            
            
            if self.shower_task:
                self.shower_task.cancel()
                self.shower_task = None
            self.evading.cancel()
            self.evading = None
            
            for f in frames:
                f.classes(remove='opacity-100', add='opacity-0')
            asyncio.create_task(self.moveCat(55, 50, speed=2, run_anim="walk", end_anim="idle", restore_tracking=True))
            with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
                ui.label('You haven\'t finished cleaning your cat!').classes('text-xl font-bold').style('font-family: runescape; color: #7c5a52;')
                ui.button('Try again!', on_click=dialog.close, color='rgb(255, 210, 194)').style('background-color: #7c5a52; color: white; font-family: runescape; font-size: 1.2vw; padding: 0.5vw 1vw; border-radius: none; margin-top: 1vw;').classes('pixel-border pixel-3d')
            async def dial():
                await dialog
                with dialog.client:
                    await self.shower()
            asyncio.create_task(dial())
                
    def loading_overlay(self):
        with ui.element('div').classes('fixed inset-0 z-[9999] flex items-center justify-center transition-opacity duration-700 ease-out') \
            .style('background-color: #bd9a8e;') as overlay:
            
            with ui.column().classes('items-center gap-4'):
                ui.label('Loading...').style('font-family: runescape; font-size: 3vw; color: #7c5a52;')
                ui.spinner(size='3em', color='#7c5a52')

        def fade_out():
            try:
                overlay.classes('opacity-0 pointer-events-none')
                ui.timer(0.7, overlay.delete, once=True)
            except Exception:
                overlay.delete()
        ui.timer(0.5, fade_out, once=True)

    def room_page(self):
        self.current_room = 'home'      
        self.anim_arrays = {}          
        self.baseui('Room.png')
        with self.room:
            self.room_content()
    
        
    def food_page(self):
        if self.current_room != 'food':
            self.current_room = 'food'      
        self.anim_arrays = {}
        
        if not hasattr(self, 'food_mode'):
            self.food_mode = 'eat'
            
        texture = 'waterbowl.png' if self.food_mode == 'drink' else 'bigbowl.png'
        
        self.baseui(texture, 'bg-tan-200')
        with self.room:
            self.foodui()
    
    def foodui(self):
        with self.room:
            with ui.element('div').classes('absolute').style('width: 21vw; height: 21vw; right:20%; top:25%;'):  
                self.Preload("edafood.png", 3, "foodadd", 256, 256)
            
            self.blackcat = ui.element('div').classes('absolute z-40').style('top:120%; width:70vw; transform: translateX(-10%);') 
            with self.blackcat:     
                ui.image("/textures/eatingbro.png").classes('object-contain')
            
            self.scale_img = ui.image("/textures/catscale.png").classes('object-contain absolute pointer-events-auto cursor-pointer z-40').style('left:95%; top:10%; width:20vw;').on('click', self.scaleclickhandle)
            self.eatlevel = ui.image(spriteHandler(267, 708, 62, 25, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain absolute z-40').style('left:113%; top:55%; width:10vw;') 
            
            self.water_zone = ui.element('div').classes('absolute cursor-pointer pointer-events-auto z-40').style('left: 20%; top: 40%; width: 60%; height: 40%;').on('click', self.drink_action)

            self.arrow_to_drink = ui.image(spriteHandler(392, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('absolute object-contain cursor-pointer pointer-events-auto z-50').style('right: 102%; top: 50%; width: 7vw;').on('click', lambda: self.switch_food_mode('drink'))

            self.arrow_to_eat = ui.image(spriteHandler(448, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('absolute object-contain cursor-pointer pointer-events-auto z-50').style('left: 102%; top: 50%; width: 7vw;').on('click', lambda: self.switch_food_mode('eat'))

            if self.oscillate_task and not self.oscillate_task.done():
                self.oscillate_task.cancel()
            self.oscillate_task = asyncio.create_task(self.oscilatefood())

            self.switch_food_mode(self.food_mode)

    def switch_food_mode(self, mode):
        self.food_mode = mode
        
        if mode == 'drink':
            self.roomim.set_source('/textures/waterbowl.png')
            
            self.scale_img.classes(remove='block', add='hidden')
            self.eatlevel.classes(remove='block', add='hidden')
            self.arrow_to_drink.classes(remove='block', add='hidden')
            
            self.water_zone.classes(remove='hidden', add='block')
            self.arrow_to_eat.classes(remove='hidden', add='block')
            
        else: # mode == 'eat'
            self.roomim.set_source('/textures/bigbowl.png')
            
            self.scale_img.classes(remove='hidden', add='block')
            self.eatlevel.classes(remove='hidden', add='block')
            self.arrow_to_drink.classes(remove='hidden', add='block')
            
            self.water_zone.classes(remove='block', add='hidden')
            self.arrow_to_eat.classes(remove='block', add='hidden')

    async def drink_action(self):
        for x in range(120, 20, -1):
             self.blackcat.style(f'top:{x}%; width:70vw; transform: translateX(-10%);')
             await asyncio.sleep(0.01)

        await asyncio.sleep(1.5)

        for x in range(20, 120):
             self.blackcat.style(f'top:{x}%; width:70vw; transform: translateX(-10%);')
             await asyncio.sleep(0.01)

        with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
                ui.label("You gave your cat water!\nThirst restored.").classes('text-xl font-bold ').style('font-family: runescape; color: #7c5a52; white-space: pre-wrap;')
                ui.button('Close', on_click=dialog.close, color='rgb(255, 210, 194)').style('background-color: #7c5a52; color: white; font-family: runescape; font-size: 1.2vw; padding: 0.5vw 1vw; border-radius: none; margin-top: 1vw;').classes('pixel-border pixel-3d')
        await dialog
        self.user.thirst = 100
        await self.user.save()
        print(self.user.thirst)
        self.switch_food_mode('eat')

    async def scaleclickhandle(self):
        self.pressed = True
        feedquality = ["too little food.\nHunger set to 80, Health decreased by 10 points.", "almost the perfect amount of food.\nHunger set to 100.", "the perfect amount of food.\nHunger set to 100, added 20 Energy, added 10 Health points.", "too much food.\n Hunger set to 100, decreased Health by 10 points."]
        
        with self.room:
            if self.pos<=36 and self.pos>=32 or self.pos<27 and self.pos>=23:
                feed = 1
            elif self.pos<32 and self.pos>27:
                feed = 2
            if self.pos<=55 and self.pos>36:
                feed = 0
            if self.pos<23 and self.pos>=17:
                feed = 3
            await asyncio.sleep(1)
            getfood = self.anim_arrays.get("foodadd")
            getfood[0].classes(remove='opacity-0', add='opacity-100')
            await asyncio.sleep(0.2)
            getfood[1].classes(remove='opacity-0', add='opacity-100')
            getfood[0].classes(remove='opacity-100', add='opacity-0')
            await asyncio.sleep(0.2)
            getfood[2].classes(remove='opacity-0', add='opacity-100')
            getfood[1].classes(remove='opacity-100', add='opacity-0')
            await asyncio.sleep(0.2)
            getfood[2].classes(remove='opacity-100', add='opacity-0')
            getfood[3].classes(remove='opacity-0', add='opacity-100')
            await asyncio.sleep(0.5)
            for x in range(120, 20, -1):
                self.blackcat.style(f'top:{x}%; width:70vw; transform: translateX(-10%);')
                await asyncio.sleep(0.01)
            getfood[3].classes(remove='opacity-100', add='opacity-0')
            await asyncio.sleep(1)
            for x in range(20, 120):
                self.blackcat.style(f'top:{x}%; width:70vw; transform: translateX(-10%);')
                await asyncio.sleep(0.01)
            with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
                ui.label(f"You gave your cat {feedquality[feed]}").classes('text-xl font-bold ').style('font-family: runescape; color: #7c5a52; white-space: pre-wrap;')
                ui.button('Go Home', on_click=dialog.close, color='rgb(255, 210, 194)').style('background-color: #7c5a52; color: white; font-family: runescape; font-size: 1.2vw; padding: 0.5vw 1vw; border-radius: none; margin-top: 1vw;').classes('pixel-border pixel-3d')
            async def dial():
                if feed == 0:
                    self.user.hunger = 80
                    self.user.health -=10
                elif feed == 1:
                    self.user.hunger = 100
                elif feed == 2:
                    self.user.hunger = 100
                    self.user.energy +=20
                    self.user.health +=10
                elif feed == 3:
                    self.user.hunger = 100
                    self.user.health -=10
                await self.user.save()
                print(self.user.hunger)
                await dialog
                with dialog.client:
                    await self.home()
            asyncio.create_task(dial())        
        
    

    async def oscilatefood(self):
        self.pressed = False
        up=True
        
        while self.pressed == False:
            if self.pos>=55:
                up = False
            if self.pos<=17:
                up = True
            if up==True:
                self.pos+=1
            elif up==False:
                self.pos-=1
            self.eatlevel.style(f'left:113%; top:{self.pos}%; width:10vw;')
            await asyncio.sleep(0.025)

    


    def bath_page(self):
        self.current_room = 'bath'           
        self.anim_arrays = {}           
        self.water = False
        
        self.baseui('emptyshower.png')
        with self.room:
            self.bathui()
    

    def skins_page(self):
        self.current_room = 'skins'      
        self.anim_arrays = {}
        self.current = 'wardrobe'
        self.baseui('wardroberoom1.png')
        
        with self.room:
            self.skinsui()          

            self.changingui = ui.element('div').classes('absolute z-20 pointer-events-auto').style("left:7%; top:250%; width:70%; height:35%; border-radius:2%; border: 0.2vw solid grey; background-color: rgba(189, 154, 142, 0.7);")
            
            with self.changingui:
                self.skinnamelabel = ui.label(self.user.equipped_skin).style('position:absolute; top:10%; left:50%; transform: translateX(-50%) translateY(-50%); color:white; font-size:2vw; background:transparent;')
                with ui.element('div').classes('absolute').style('height:15%; top:70%; left:15%; display:flex; flex-direction:row; align-items:center; justify-content:center; gap:1vw; padding:2vw; background-color: rgba(0, 0, 0, 0.3); border-radius:1%; width:70%;'):
                    ui.image(spriteHandler(392, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; display: inline-block;').on('click.stop', lambda: self.skinarrows('left'))
                    # ui.element('div').classes('absolute').style('left:17.1vw; height:2vw; width:6vw; top:3.8vw; box-shadow: 0 0 40px 10px #000;')
                    with ui.image(spriteHandler(180, 797, 41 , 21, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; bottom:32%; left:2%; display: inline-block;').on('click', self.skinconfirm):
                        ui.label('Confirm').style('position:absolute; top:45%; left:52%; transform: translateX(-50%) translateY(-50%); color:white; font-size:1.2vw; background:transparent;')
                    ui.image(spriteHandler(448, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; display: inline-block;').on('click.stop', lambda: self.skinarrows('right'))
        
    def skinsui(self):
        self.cat_x = 40
        with self.room:
            ui.element('div').classes('absolute object-contain pointer-events-auto cursor-pointer z-20').style('width: 20vw; height: 25vh; right:38%; top:25%; transform: rotate(-15deg);').on('click', self.wardrobechanging)

            self.cat = ui.element('div').classes('absolute z-10').style(f'left:{self.cat_x}%; top:{self.cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;')
            with self.cat:
                self.cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
                
                ui.timer(0.1, self.wardrobecallableprelod, once=True)
        ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{self.cat_visuals.id}")'), once=True)

    def wardrobecallableprelod(self):
        self.cat_visuals.clear()
        with self.cat_visuals:
            self.Preload(f"{self.user.equipped_skin}/SittingB.png", 2, "idle")
            self.Preload(f"{self.user.equipped_skin}/RunCatb.png", 6, "walk")
            self.Preload(f"{self.user.equipped_skin}/JumpCatb.png", 12, "jump")
        self.doAnim("idle", 0.35)


    async def wardrobechanging(self):
        self.cat.client.run_javascript('window.setTracking(false)')
        
        asyncio.create_task(self.cameraAction(20, 20, 2.0, speed=2.0))
        asyncio.create_task(self.moveCat(41, 43, speed=2, run_anim="walk", restore_tracking=False))
        
        await asyncio.sleep(1.5)
        
        
        await asyncio.gather(
            self.moveCat(45, 9, speed=1.5, run_anim="jump", end_anim="idle", restore_tracking=False, animtime1=0.3, animtime2=0.35, delay=0.85),
            self.menurollout(115, 23)
        )
        
        self.set_cat_orientation(False)
        self.cat.classes(remove='z-10', add='z-50')
        asyncio.create_task(self.moveCat(35, 30, speed=1.5, run_anim="jump", end_anim="idle", restore_tracking=False, animtime1=0.3, animtime2=0.35, delay=0.7))



    def skinarrows(self, direction):
        if direction == 'left':
            self.skinnum -= 1
            if self.skinnum < 1:
                self.skinnum = len(skinfolderarray)

        elif direction == 'right':
            self.skinnum += 1
            if self.skinnum > len(skinfolderarray):
                self.skinnum = 1
        self.user.equipped_skin = skinfolderarray[self.skinnum -1]
        self.skinnamelabel.set_text(self.user.equipped_skin)
        asyncio.create_task(self.user.save())
        self.wardrobecallableprelod()
    
    async def skinconfirm(self):
        self.changePfp.refresh()
        asyncio.create_task(self.moveCat(41, 43, speed=1.5, run_anim="jump", end_anim="idle", restore_tracking=False, animtime1=0.3, animtime2=0.35, delay=0.7))
        await asyncio.sleep(0.7)
        asyncio.create_task(self.cameraAction(0, 0, 1.0, speed=2.0))
        asyncio.create_task(self.menurollout(23, -150))
        
        await asyncio.sleep(1.5)
        
        asyncio.create_task(self.moveCat(40, 55, speed=1.5, run_anim="walk"))
        
        await asyncio.sleep(1.5)
        
        self.cat.client.run_javascript('window.setTracking(true)')
        self.cat.classes(remove='z-50', add='z-10')    
    
    async def menurollout(self, start, end):
        for x in range(start, end, -1):
            self.changingui.style(f'top:{x}%;')
            await asyncio.sleep(0.01)