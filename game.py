import asyncio
import random
import pathlib
from itertools import cycle
from PIL import Image
from nicegui import ui, app, events

# Import the User model from our new models file
from models import User

# --- CONSTANTS & HELPERS ---
SPRITE_SCALE = 4
roomsize = 512
BASE = pathlib.Path(__file__).parent

skinfolderarray = [
    "Batman Cat", "Brown Cat", "Classical Cat", "Christmas Cat",
    "Demonic Cat", "Egypt Cat", "Siamese Cat", "Three Color Cat",
    "Tiger Cat", "Black Cat", "Halloween Cat", "Goofy White Cat"
]

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

# --- GAME CLASS ---
class Game:
    # Added on_logout_callback so we can tell main.py to remove this game from the list
    def __init__(self, user: User, on_logout_callback):
        self.user = user
        self.on_logout_callback = on_logout_callback # Save the callback
        self.curCatSkin = user.equipped_skin
        
        self.user = user
        self.curCatSkin = user.equipped_skin
        self.move_task = None
        self.evading = None
        self.cat_layer = None
        self.canvas = None
        self.cat = None
        self.cat_joystick = None 
        self.cat_visuals = None
        self.pet_timeout_task = None
        self.anim_arrays = {}           
        self.current_anim_task = None   
        self.current_visible_list = None 
        self.petState = 0               
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
        self.skinnum = skinfolderarray.index(self.curCatSkin)
        self.isloggedin = True
        self.oscillate_task = None
        
    
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
        if self.current_room == 'home':
            if self.petState == 0:
                if coord.y > 0.5: 
                    self.petState = 3
                elif coord.y < -0.5: 
                    self.petState = 1
            if self.petState == 1 and coord.y > 0.5: 
                print("petanim")
                self.petAnim()
            if self.petState == 3 and coord.y < -0.5: 
                print("petanim")
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
        if self.current_room != 'bath':
            self.doAnim("idle", 0.35)

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

    def changePfp(self, skin):
        endskin = f"{skin}/SittingB.png"
        ui.image(spriteCycler(0, 0, 32, endskin, scale=SPRITE_SCALE)).classes('w-25 h-25')

    def hud_top_left(self):
        with ui.element('div').classes('relative pixelated'):
            ui.image("/textures/statusbar.png").classes('w-100 mb-2')
            with ui.element('div').classes('absolute left-33 top-9 w-63'):
                ui.linear_progress(value=0.7, color='red', show_value=False).props('instant-feedback').classes('absolute w-63 h-5')
                ui.badge('67').classes('absolute-full flex flex-center text-black bg-transparent text-xl content-center h-5')
                ui.image("/textures/heart.png").classes('absolute w-10 h-10 -left-5 -top-5')
            with ui.element('div').classes('absolute left-33 top-17 w-63'):
                ui.linear_progress(value=0.7, color='yellow', show_value=False).props('instant-feedback').classes('absolute w-63 h-5')
                ui.badge('67').classes('absolute-full flex flex-center text-pink bg-transparent text-xl h-5')
                ui.image("/textures/bolt.png").classes('absolute w-10 h-10 z-100 -left-5 -top-3')
            with ui.element('div').classes('absolute left-30 top-24'):
                ui.image("/textures/coin.png").classes('w-12 h-12 inline-block ml-2')
                ui.label('181122').classes('inline-block ml-2 text-2xl font-bold').style(
                    'transform: translateY(7px); color: #f0e68c; text-shadow: 2px 2px 3px #000;')
                ui.circular_progress(value =0.5, show_value=False).props('instant-feedback').classes('inline-block ml-2')
                ui.label('50%').classes('inline-block ml-2 text-lg font-bold').style('transform: translate(-45.5px, 4px); color: #82C8E5;')
            with ui.element('div').classes('absolute left-4 top-8'):
                self.changePfp(self.curCatSkin) 

    def stats_left(self):
        with ui.element('div').classes('relative top-30'):
            ui.image("/textures/stats.png").classes('absolute w-70 mb-2')
            with ui.element('div').classes('absolute top-20 left-10 w-50 text-xl'):
                ui.label('Stats').classes("h-10 text-lg font-bold text-center")
                ui.separator()
                ui.label(self.user.username).classes('font-bold text-lg')
                ui.label('lvl: 3')
                ui.label('hunger: 79/100')
                ui.label('thirst: 79/100')
                ui.label('sleep: 100/100')
                ui.label('age: ...')

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

    async def settings(self):
        ui.navigate.to('/settings')
        self.current_room = 'settings'
    
    async def home(self):
        if self.current_room != 'home':
            ui.navigate.to('/')
            self.current_room = 'home'
        await asyncio.sleep(0.2)
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
        
        await self.sleepbutasync()

    async def sleepbutasync(self):
        self.cat.client.run_javascript('window.setTracking(false)')
        asyncio.create_task(self.cameraAction(-15, -15, 2.0, speed=3.0))
        await self.moveCat(38, 44, speed=1, run_anim="walk", restore_tracking=False)
        self.set_cat_orientation(True)
        await asyncio.sleep(0.5)
        await self.moveCat(53, 34, speed=1.0, run_anim="jump", end_anim="sleep", restore_tracking=False)

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


    def settings_page(self):
        self.current_room = 'settings'      
        self.anim_arrays = {}
        with ui.element('div').classes('fixed inset-0 pixelated').style(' overflow:hidden; height: 104vh; display: flex; align-items: center; justify-content: center; font-family: runescape; background-color: #f0e4d7; flex-direction: column;'):
            with ui.element('div').classes('absolute right-6 top-20 z-50'):
                self.toolbar_right()
            ui.label('Settings page').style('font-size: 3rem; color: #333; text-align: center; width:100vw; margin-top: 20px;')
            with ui.grid(columns=2).style('gap: 20px; width: 70vw; margin: 50px 0; ').classes('items-center'):
                ui.label('Change Password')
                pwdchfld = ui.input(password=True).style('font-size: 1.2rem; padding: 10px; width: 100%; border: 2px solid #ccc; border-radius: 5px;')
                
                ui.label('Change Email')
                mailchfld = ui.input().style('font-size: 1.2rem; padding: 10px; width: 100%; border: 2px solid #ccc; border-radius: 5px;')

                ui.label ('Log Out of your account')
                ui.button('Log Out', color='#bd9a8e').on('click', lambda: self.logout())

                ui.label('Mouse sensitivity')
                ui.slider(min=0.5, max=2.0, value=self.cam_zoom_sens, step=0.1).bind_value_to(self, 'cam_zoom_sens').style('color: primary;')


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

    def toolbar_right(self):
        with ui.column().classes('gap-3 z-50'):
            self.button("home")
            self.button("shower")
            self.button("sleep")
            self.button("foodbowl")
            self.button("wardrobe")
            self.button("settings")

    def bottom_right_button(self):
        with ui.element('div').classes('relative w-32 h-32 cursor-pointer').style('background-color: #bd9a8e; border-radius: 30%; border: 4px solid #7c5a52;'):
            ui.image("/textures/swords.png").classes('w-24 h-24 cursor-pointer align-middle absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2').on('click', lambda: ui.notify('Battle button clicked'))

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

    def bedUI(self):
        ui.image(spriteHandler(201, 137, 112, 83, "Furnitures.png", scale=SPRITE_SCALE)).classes('w-[10vw] object-contain')

    async def cycleclasses(self):
        classes = ['showerhandle1', 'showerhandle2', 'showerhandle3', 'showerhandle4']
        
        self.catjoy.classes(remove='custom-cursor')
        
        idx = 0
        while (self.water == True):
            self.canvas.classes(remove=classes[(idx -1) % len(classes)], add=classes[idx % len(classes)])
            idx += 1
            await asyncio.sleep(0.2)


    
    def room_content(self):
        with ui.element('div').classes('absolute cursor-pointer z-20 pointer-events-auto') \
            .style('left: 48%; top: 40%; width: 20%; height: 18%;') \
            .on('click.stop', self.sleep):
            self.bedUI()

        with ui.element('div').classes('relative').style('left: 35%; top: 72.5%; width: 20%; height: 10%;'):
            self.bowlsUI()
        
        self.cat = ui.element('div').classes('absolute z-30').style(
            f'left:{self.cat_x}%; top:{self.cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;'
        )
        with self.cat:

            self.cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
            with self.cat_visuals:
                self.Preload(f"{self.curCatSkin}/sittingb.png", 2, "idle")
                self.Preload(f"{self.curCatSkin}/Idle2Catb.png", 13, "pet")
                self.Preload(f"{self.curCatSkin}/RunCatb.png", 6, "walk")
                self.Preload(f"{self.curCatSkin}/JumpCatb.png", 12, "jump")
                self.Preload(f"{self.curCatSkin}/SleepCatb.png", 2, "sleep")
            ui.joystick(color='transparent', size=80, on_move=lambda e: self.catPet(e)).classes('bg-transparent absolute inset-0 w-full h-full custom-cursor')
        
        ui.timer(0.1, lambda: self.doAnim("idle", 0.35), once=True)
        self.update_transform()
        
        ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{self.cat_visuals.id}")'), once=True)

    def baseui(self, room_texture='Room.png', bg='bg-blue-200'):
        with ui.element('div').classes(f'fixed inset-0 {bg} overflow-hidden pixelated'):
            with ui.element('div').classes('absolute left-6 top-6 z-50'):
                self.hud_top_left()
            with ui.element('div').classes('absolute left-6 top-40 z-50'):
                self.stats_left()
            with ui.element('div').classes('absolute right-6 top-20 z-50'):
                self.toolbar_right()
            with ui.element('div').classes('absolute right-8 bottom-8 z-50'):
                self.bottom_right_button()
            with ui.element('div').classes('absolute left-10 bottom-20 z-50'):
                self.resetbut()
            
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
        
        asyncio.create_task(self.statuscheck())
        self.loading_overlay()

    async def mouse_handler(self, e: events.MouseEventArguments):
        if self.current_room == 'food': 
            return

        if self.move_task and not self.move_task.done():
            self.move_task.cancel()
       
        floor_min_y = 50   
        floor_max_y = 75  
        floor_min_x = 15   
        floor_max_x = 85   
        click_x_pct = (e.image_x / roomsize) * 100
        click_y_pct = (e.image_y / roomsize) * 100
        dest_x_pct = max(floor_min_x, min(floor_max_x, click_x_pct))
        dest_y_pct = max(floor_min_y, min(floor_max_y, click_y_pct))
        cat_width_pct = 16
        cat_height_pct = 16 

        target_x = dest_x_pct - (cat_width_pct / 2)
        target_y = dest_y_pct - (cat_height_pct) + 2
        
        self.roomim.content = f'<circle cx="{dest_x_pct * (roomsize/100)}" cy="{dest_y_pct * (roomsize/100)}" r="5" fill="none" stroke="#bd9a8e" stroke-width="3" />'
        ui.timer(0.5, lambda: setattr(self.roomim, 'content', ''), once=True)
        
        self.move_task = asyncio.create_task(self.moveCat(target_x, target_y, speed=1.3, run_anim="walk", end_anim="idle"))

    async def statuscheck(self):
        while self.isloggedin:
            if self.cam_x != 0.0 or self.cam_y != 0.0 or self.cam_zoom != 1.0:
                self.reseticon.classes(remove='opacity-0', add='opacity-100')
            else:
                self.reseticon.classes(remove='opacity-100', add='opacity-0')
            await asyncio.sleep(0.1)

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
                    self.Preload(f"{self.curCatSkin}/SittingB.png", 2, "idle")
                    self.Preload("shower.png", 3, "shower")
                    self.Preload(f"{self.curCatSkin}/RunCatb.png", 6, "walk")
                self.catjoy = ui.joystick(color='transparent', size=80, on_move=lambda e: self.catPet(e)).classes('bg-transparent absolute inset-0 w-full h-full custom-cursor')
            
            ui.timer(0.1, lambda: self.doAnim("idle", 0.35), once=True)
            self.update_transform()
            
            ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{self.cat_visuals.id}")'), once=True)


    async def cleaningcat(self):
        progress = 0.0
    
        while self.water and progress < 1.0:
            overlap = await self.cat_visuals.client.run_javascript(f'return window.checkOverlap("c{self.cat_visuals.id}")')
            if overlap:
                progress += 0.15
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
            self.water = False

            self.canvas.classes(remove='showerhandle1 showerhandle2 showerhandle3 showerhandle4')
            self.catjoy.classes(add='custom-cursor')
            
            if self.shower_task:
                self.shower_task.cancel()
                self.shower_task = None
            self.evading.cancel()
            self.evading = None
            
            for f in frames:
                f.classes(remove='opacity-100', add='opacity-0')
            asyncio.create_task(self.moveCat(55, 50, speed=2, run_anim="walk", end_anim="idle", restore_tracking=True))
            with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
                ui.label('You have cleaned your cat!').classes('text-xl font-bold').style('font-family: runescape; color: #7c5a52;')
                ui.button('Go Home', on_click=dialog.close, color='rgb(255, 210, 194)').style('background-color: #7c5a52; color: white; font-family: runescape; font-size: 1.2vw; padding: 0.5vw 1vw; border-radius: none; margin-top: 1vw;').classes('pixel-border pixel-3d')
            async def dial():
                await dialog
                with dialog.client:
                    await self.home()
            asyncio.create_task(dial())
        
        else:
            self.water = False

            self.canvas.classes(remove='showerhandle1 showerhandle2 showerhandle3 showerhandle4')
            self.catjoy.classes(add='custom-cursor')
            
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

        self.switch_food_mode('eat')

    async def scaleclickhandle(self):
        self.pressed = True
        feedquality = ["too little food.\nHunger set to 20, Health decreased by 10 points.", "almost the perfect amount of food.\nHunger set to 0.", "the perfect amount of food.\nHunger set to 0, added 20 Energy, added 10 Health points.", "too much food.\n Hunger set to 0, decreased Health by 10 points."]
        
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

            self.changingui = ui.element('div').classes('absolute z-20').style("left:7%; top:250%; width:70%; height:35%; ""border-radius:2%; border: 0.2vw solid grey; ""background-color: rgba(189, 154, 142, 0.7);")
            
            with self.changingui:
                self.skinnamelabel = ui.label(self.curCatSkin).style('position:absolute; top:10%; left:50%; transform: translateX(-50%) translateY(-50%); color:white; font-size:2vw; background:transparent;')
                with ui.element('div').classes('absolute').style('height:15%; top:70%; left:15%; display:flex; flex-direction:row; align-items:center; justify-content:center; gap:1vw; padding:2vw; background-color: rgba(0, 0, 0, 0.3); border-radius:1%; width:70%;'):
                    ui.image(spriteHandler(392, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; display: inline-block;').on('click', lambda: self.skinarrows('left'))
                    # ui.element('div').classes('absolute').style('left:17.1vw; height:2vw; width:6vw; top:3.8vw; box-shadow: 0 0 40px 10px #000;')
                    with ui.image(spriteHandler(180, 797, 41 , 21, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; bottom:32%; left:2%; display: inline-block;').on('click', self.skinconfirm):
                        ui.label('Confirm').style('position:absolute; top:45%; left:52%; transform: translateX(-50%) translateY(-50%); color:white; font-size:1.2vw; background:transparent;')
                    ui.image(spriteHandler(448, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; display: inline-block;').on('click', lambda: self.skinarrows('right'))
        
    def skinsui(self):
        self.cat_x = 40
        with self.room:
            ui.element('div').classes('absolute object-contain').style('width: 20vw; height: 25vh; right:38%; top:25%; transform: rotate(-15deg);').on('click', self.wardrobechanging)
            self.cat = ui.element('div').classes('absolute z-10').style(f'left:{self.cat_x}%; top:{self.cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;')
            with self.cat:
                self.cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
                
                ui.timer(0.1, self.wardrobecallableprelod, once=True)
        ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{self.cat_visuals.id}")'), once=True)

    def wardrobecallableprelod(self):
        self.cat_visuals.clear()
        with self.cat_visuals:
            self.Preload(f"{self.curCatSkin}/SittingB.png", 2, "idle")
            self.Preload(f"{self.curCatSkin}/RunCatb.png", 6, "walk")
            self.Preload(f"{self.curCatSkin}/JumpCatb.png", 12, "jump")
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
        self.curCatSkin = skinfolderarray[self.skinnum -1]
        self.skinnamelabel.set_text(self.curCatSkin)
        self.wardrobecallableprelod()
    
    async def skinconfirm(self):
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