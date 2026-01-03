from sys import exit
import datetime as dt
import json
import os
from nicegui import ui, app
from PIL import Image
import pathlib
import asyncio
from itertools import cycle
import random

evading = None
cat_layer = None
canvas = None
cat = None
cat_joystick = None 
cat_visuals = None
pet_timeout_task = None

anim_arrays = {}           
current_anim_task = None   
current_visible_list = None 
petState = 0               
currentroom = 'home'

cam_x = 0.0 
cam_y = 0.0
cam_zoom = 1.0

cat_x = 50.0 
cat_y = 55.0    
SPRITE_SCALE = 4
pos = 55

BASE = pathlib.Path(__file__).parent
app.add_static_files('/static', str(BASE / 'static'))      
app.add_static_files('/textures', str(BASE / 'textures'))  

skinfolderarray = [
    "Batman Cat",
    "Brown Cat", 
    "Classical Cat",
    "Christmas Cat",
    "Demonic Cat",
    "Egypt Cat",
    "Siamese Cat",
    "Three Color Cat",
    "Tiger Cat",
    "Black Cat",
    "Halloween Cat",
    "Goofy White Cat"
]

skinnum = 3
curCatSkin = skinfolderarray[skinnum - 1]

ui.add_head_html("""
<style>
.pixel-border {
	clip-path: polygon(
		0px 4px,
		4px 4px,
		4px 0px,
		calc(100% - 4px) 0px,
		calc(100% - 4px) 4px,
		100% 4px,
		100% calc(100% - 4px),
		calc(100% - 4px) calc(100% - 4px),
		calc(100% - 4px) 100%,
		4px 100%,
		4px calc(100% - 4px),
		0px calc(100% - 4px)
	);
}
  .q-img__loading {
    display: none !important;
  }
  .instant-progress .q-linear-progress__model {
  transition: none !important;
  }
  img{ 
  user-select: none;
  -webkit-user-select: none;
  user-drag: none; 
  -webkit-user-drag: none;
  }
  @font-face{ 
  font-family: 'runescape'; src: url('/static/runescape.ttf') format('truetype'); 
  }
  html, body{ 
  margin: 0; 
  padding: 0;
  width: 100%; 
  height: 100%; 
  font-family: 'runescape', sans-serif; 
  font-size: 16px; 
  }
  .pixelated{ 
  image-rendering: pixelated; 
  image-rendering: -moz-crisp-edges; 
  image-rendering: crisp-edges; 
  }
  .custom-cursor{ 
  cursor: url('/static/hand.png') 16 16, auto !important; 
  }
  .fade-me{ 
  transition: opacity 0.1s; 
  }
  .showerhandle1{ 
  cursor: url('/static/showerhandle1.png') 32 32, auto !important; 
  }
  .showerhandle2{ 
  cursor: url('/static/showerhandle2.png') 32 32, auto !important; 
  }
  .showerhandle3{ 
  cursor: url('/static/showerhandle3.png') 32 32, auto !important; 
  }
  .showerhandle4{ 
  cursor: url('/static/showerhandle4.png') 32 32, auto !important; 
  }
  .pixel-3d {
	box-shadow:
		2px 2px 0px rgba(0, 0, 0, 0.3),
		inset 1px 1px 0px rgba(255, 255, 255, 0.2);
  }
</style>

<script>
  window.catVisualsId = null;
  window.isTracking = true; 
  window.mouseX = 0;
  window.mouseY = 0;

  window.startCatTracking = (elementId) => {
    const checkElement = () => {
        let el = document.getElementById(elementId);
        if (el) {
            window.catVisualsId = elementId;
        } else {
            setTimeout(checkElement, 50);
        }
    };
    checkElement();
  };

  window.setTracking = (state) => {
    window.isTracking = state;
  };

  window.checkOverlap = (elementId) => {
    const el = document.getElementById(elementId);
    if (!el) return false;
    
    const rect = el.getBoundingClientRect();
    
    return (
        window.mouseX >= rect.left && 
        window.mouseX <= rect.right && 
        window.mouseY >= rect.top && 
        window.mouseY <= rect.bottom
    );
  };

  document.addEventListener('mousemove', (e) => {
    window.mouseX = e.clientX;
    window.mouseY = e.clientY;

    if (!window.catVisualsId || !window.isTracking) return;
    
    const element = document.getElementById(window.catVisualsId);
    if (!element) return;

    const rect = element.getBoundingClientRect();

    if (e.clientX > rect.right) {
        element.style.transform = 'scaleX(1)';
    } else if(e.clientX < rect.left) {
        element.style.transform = 'scaleX(-1)';
    }
  });
</script>
""")

def clamp(v, lo=0.5, hi=2.0):
    return max(lo, min(hi, v))

def update_transform():
    global cam_zoom, cam_x, cam_y, canvas
    if canvas:
        canvas.style(f'transform: translate({cam_x}%, {cam_y}%) scale({cam_zoom})')

def on_wheel(e):
    global cam_zoom
    dy = e.args.get('deltaY', 0)
    cam_zoom = clamp(cam_zoom * (0.9 if dy > 0 else 1.1))
    update_transform()

def set_cat_orientation(facing_right: bool):
    global cat_visuals
    scale_x = 1 if facing_right else -1
    
    if cat_visuals:
        cat_visuals.style(f'transform: scaleX({scale_x});')

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

def Preload(path, NofSprites, anim_name, step=32, ystep=32):
    global anim_arrays
    Pics = [spriteCycler(x, 0, step, path, scale=SPRITE_SCALE, ystep=ystep) for x in range(NofSprites + 1)]
    local_frames = []
    for pic in Pics:
        img = ui.image(pic).classes('absolute w-full h-full object-contain opacity-0 transition-none')
        local_frames.append(img)
    anim_arrays[anim_name] = local_frames

def doAnim(anim_name, time, cancel_current=True):
    global current_anim_task, current_visible_list
    if current_anim_task and cancel_current:
        current_anim_task.cancel()
        if current_visible_list:
            for x in current_visible_list:
                x.classes(remove='opacity-100', add='opacity-0')
            
    target_frames = anim_arrays.get(anim_name)
    current_visible_list = target_frames
    
    if target_frames:
        target_frames[0].classes(remove='opacity-0', add='opacity-100') 
        current_anim_task = asyncio.create_task(cyclingSprite(target_frames, time))

async def cyclingSprite(frames_list, time):
    NofSprites = len(frames_list) - 1
    while True:
        sequence = list(range(NofSprites + 1)) + list(range(NofSprites - 1, 0, -1))
        for index in sequence:
            for f in frames_list:
                f.classes(remove='opacity-100', add='opacity-0')
            frames_list[index].classes(remove='opacity-0', add='opacity-100')
            await asyncio.sleep(time)



def catPet(coord):
    global petState, currentroom

    if currentroom == 'home':
        if petState == 0:
            if coord.y > 0.5: 
                petState = 3
            elif coord.y < -0.5: 
                petState = 1
        if petState == 1 and coord.y > 0.5: 
            print("petanim")
            petAnim()
        if petState == 3 and coord.y < -0.5: 
            print("petanim")
            petAnim()
            

def petAnim():
    global petState, pet_timeout_task
    
    if pet_timeout_task:
        pet_timeout_task.cancel()
        pet_timeout_task = None

    if petState != 2:
        petState = 2
        ui.notify("Cat petted!")
        doAnim("pet", 0.15)

    pet_timeout_task = asyncio.create_task(petEnd())

async def petEnd():
    global petState, pet_timeout_task, currentroom
    
    await asyncio.sleep(0.2) 
    petState = 0
    pet_timeout_task = None
    if currentroom != 'bath':
        doAnim("idle", 0.35)

async def cameraAction(target_x_pct, target_y_pct, target_zoom, speed=2.0):
    global cam_x, cam_y, cam_zoom
    
    dist_x = target_x_pct - cam_x
    dist_y = target_y_pct - cam_y
    dist_z = target_zoom - cam_zoom
    
    max_dist = max(abs(dist_x), abs(dist_y))
    
    total_steps = int(max(1, max_dist * speed)) 
        
    inc_x = dist_x / total_steps
    inc_y = dist_y / total_steps
    inc_z = dist_z / total_steps
    
    for _ in range(total_steps):
        cam_x += inc_x
        cam_y += inc_y
        cam_zoom += inc_z
        update_transform()
        await asyncio.sleep(0.01)
        
    cam_x = target_x_pct
    cam_y = target_y_pct
    cam_zoom = target_zoom
    update_transform()

async def moveCat(target_x_pct, target_y_pct, speed=1.0, run_anim="walk", end_anim="idle", restore_tracking=True, animtime1=0.15, animtime2=0.35, delay=0.0):
    global cat_x, cat_y, cat

    cat.client.run_javascript('window.setTracking(false)')

    if target_x_pct < cat_x:
        set_cat_orientation(False)
    elif target_x_pct > cat_x:
        set_cat_orientation(True) 

    
    doAnim(run_anim, animtime1)

    await asyncio.sleep(delay)
    
    dx = target_x_pct - cat_x
    dy = target_y_pct - cat_y
    dist = (dx**2 + dy**2)**0.5
    
    step_size = 0.5 * speed
    steps = int(dist / step_size)
    dx /= steps
    dy /= steps
    for _ in range(steps):
        cat_x += dx
        cat_y += dy
        
        cat.style(f'left:{cat_x}%; top:{cat_y}%;')
        await asyncio.sleep(0.016) 

    cat_x = target_x_pct
    cat_y = target_y_pct
    if cat:
        cat.style(f'left:{cat_x}%; top:{cat_y}%;')

    doAnim(end_anim, animtime2)
    
    if restore_tracking and cat:
        cat.client.run_javascript('window.setTracking(true)')

def changePfp(skin):
    endskin = f"{skin}/SittingB.png"
    ui.image(spriteCycler(0, 0, 32, endskin, scale=SPRITE_SCALE)).classes('w-25 h-25')

def hud_top_left():
    with ui.element('div').classes('relative'):
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
            changePfp(curCatSkin) 

def stats_left():
    with ui.element('div').classes('relative top-30'):
        ui.image("/textures/stats.png").classes('absolute w-70 mb-2')
        with ui.element('div').classes('absolute top-20 left-10 w-50 text-xl'):
            ui.label('Stats').classes("h-10 text-lg font-bold text-center")
            ui.separator()
            ui.label('name: cat')
            ui.label('lvl: 3')
            ui.label('hunger: 79/100')
            ui.label('thirst: 79/100')
            ui.label('sleep: 100/100')
            ui.label('age: ...')


current = 'home'   
buttons = {}   

async def press(name: str):
    global current, buttons
    prev = current
    if prev == name: 
        return
    p_up, p_dn, p_icon = buttons[prev]
    p_up.classes(remove='opacity-0', add='opacity-100')
    p_dn.classes(remove='opacity-100', add='opacity-0')
    p_icon.style('transform: translate(-50%, -55%) perspective(600px);')
    n_up, n_dn, n_icon = buttons[name]
    n_up.classes(remove='opacity-100', add='opacity-0')
    n_dn.classes(remove='opacity-0', add='opacity-100')
    n_icon.style('transform: translate(-50%, -57%) perspective(600px) scaleY(1.02);')
    current = name
    
    if name in globals():
        func = globals()[name]
        if callable(func):
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                func()


async def home():
    global currentroom
    if currentroom != 'home':
        ui.navigate.to('/')
        currentroom = 'home'
    ui.notify("home")
    
    await cameraAction(0, 0, 1.0, speed=2.0)
    if cat_x != 50 or cat_y != 55:
        await moveCat(50, 55, speed=1.5, run_anim="walk")


async def shower(): 
    global currentroom
    ui.navigate.to('/bath')
    currentroom = 'bath'
    asyncio.create_task(cameraAction(0, 0, 1.0, speed=2.0))
    if cat_x != 50 or cat_y != 55:
        asyncio.create_task(moveCat(50, 55, speed=1.5, run_anim="walk"))
    
async def sleep(): 
    global currentroom, current
    if currentroom != 'home':
        ui.navigate.to('/')
        currentroom = 'home'
    if current != 'sleep':
        current = 'sleep'
    
    await sleepbutasync()

async def sleepbutasync():
    cat.client.run_javascript('window.setTracking(false)')
    asyncio.create_task(cameraAction(-15, -15, 2.0, speed=3.0))
    await moveCat(38, 44, speed=1, run_anim="walk", restore_tracking=False)
    set_cat_orientation(True)
    await asyncio.sleep(0.5)
    await moveCat(53, 34, speed=1.0, run_anim="jump", end_anim="sleep", restore_tracking=False)

    
readytoeat = False

def eat(): 
    with ui.context.client:
        asyncio.create_task(foodbowl())
    
    
async def eatasync():
    global readytoeat
    ui.notify("eat")
    readytoeat = True
    
    await asyncio.gather(
        cameraAction(-15, -25, 2.0, speed=2.0),
        moveCat(45, 61, speed=1.5, run_anim="walk")
    )
    
    if cat:
        cat.client.open('/food')
    else:
        ui.navigate.to('/food')

async def wardrobe(): 
    ui.notify("wardrobe")
    if cat:
        cat.client.open('/wardrobe')
    else:
        ui.navigate.to('/wardrobe')


def settings(): ui.notify("settings")

def button(name: str):
    global current, buttons
    with ui.element('div').classes('inline-block'):
        with ui.element('div').classes('relative w-16 h-16 cursor-pointer').on('click', lambda e, n=name: press(n)):
            buttonUp = ui.image("/textures/button1.png").classes('absolute inset-0 w-full h-full object-contain opacity-100')
            buttonDown = ui.image("/textures/button2.png").classes('absolute inset-0 w-full h-full object-contain opacity-0')
            icon = ui.image(f"/textures/{name}.png").style(
                'position:absolute; left:50%; top:50%; transform: translate(-50%, -55%) perspective(600px);'
                'transform-origin: center bottom; width: 2.5rem; height: 2.5rem; object-fit: contain; pointer-events:none; transition: transform 90ms;'
            )
            buttons[name] = (buttonUp, buttonDown, icon)
            if current == name:
                buttonUp.classes(remove='opacity-100', add='opacity-0')
                buttonDown.classes(remove='opacity-0', add='opacity-100')
                icon.style('transform: translate(-50%, -55%) perspective(600px) scaleY(1.02);')

def toolbar_right():
    with ui.column().classes('gap-3 z-50'):
        button("home")
        button("shower")
        button("sleep")
        button("foodbowl")
        button("wardrobe")
        button("settings")

def bottom_right_button():
    with ui.element('div').classes('relative w-32 h-32 cursor-pointer').style('background-color: #bd9a8e; border-radius: 30%; border: 4px solid #7c5a52;'):
        ui.image("/textures/swords.png").classes('w-24 h-24 cursor-pointer align-middle absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2').on('click', lambda: ui.notify('Battle button clicked'))

async def foodbowl():
    global readytoeat
    ui.notify("Food bowl clicked")
    if not readytoeat:
        await eatasync()
        return
    ui.navigate.to('/food')

def waterbowl():
    ui.notify("Water bowl clicked")

def bowlsUI():
    with ui.image(spriteHandler(261, 332, 53, 44, "Furnitures.png", scale=SPRITE_SCALE)).classes('object-contain absolute').style('left:5%; width:5vw;'):
        ui.element('div').classes('absolute cursor-pointer w-full h-full bg-transparent').on('click', foodbowl)
    with ui.image(spriteHandler(390, 332, 53, 44, "Furnitures.png", scale=SPRITE_SCALE)).classes('object-contain absolute').style('left:40%; top:35%; width:5vw;'):
        ui.element('div').classes('absolute cursor-pointer w-full h-full bg-transparent').on('click', waterbowl)

def bedUI():
    ui.image(spriteHandler(201, 137, 112, 83, "Furnitures.png", scale=SPRITE_SCALE)).classes('w-[10vw] object-contain')

async def cycleclasses():
    global water, catjoy    
    classes = ['showerhandle1', 'showerhandle2', 'showerhandle3', 'showerhandle4']
    idx = 0
    while (water == True):
        catjoy.classes(remove=classes[(idx -1) % len(classes)], add=classes[idx % len(classes)])
        idx += 1
        await asyncio.sleep(0.2)

def room_content():
    global canvas, cat, cat_x, cat_y, cat_visuals, curCatSkin
      
    with ui.element('div').classes('absolute cursor-pointer').style('left: 48%; top: 40%; width: 20%; height: 18%;').on('click', sleep):
        bedUI()

    with ui.element('div').classes('relative').style('left: 35%; top: 72.5%; width: 20%; height: 10%;'):
        bowlsUI()
    
    cat = ui.element('div').classes('absolute').style(
        f'left:{cat_x}%; top:{cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;'
    )
    with cat:

        cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
        with cat_visuals:
            Preload(f"{curCatSkin}/sittingb.png", 2, "idle")
            Preload(f"{curCatSkin}/Idle2Catb.png", 13, "pet")
            Preload(f"{curCatSkin}/RunCatb.png", 6, "walk")
            Preload(f"{curCatSkin}/JumpCatb.png", 12, "jump")
            Preload(f"{curCatSkin}/SleepCatb.png", 2, "sleep")
        ui.joystick(color='transparent', size=80, on_move=lambda e: catPet(e)).classes('bg-transparent absolute inset-0 w-full h-full custom-cursor')
    
    ui.timer(0, lambda: doAnim("idle", 0.35), once=True)
    update_transform()
    
    ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{cat_visuals.id}")'), once=True)

def baseui(room_texture='Room.png', bg='bg-blue-200'):
    global canvas, room
    with ui.element('div').classes(f'fixed inset-0 {bg} overflow-hidden pixelated'):
        with ui.element('div').classes('absolute left-6 top-6 z-50'):
            hud_top_left()
        with ui.element('div').classes('absolute left-6 top-40 z-50'):
            stats_left()
        with ui.element('div').classes('absolute right-6 top-20 z-50'):
            toolbar_right()
        with ui.element('div').classes('absolute right-8 bottom-8 z-50'):
            bottom_right_button()
        with ui.element('div').classes('absolute left-10 bottom-20 z-50'):
            resetbut()
        room_wrapper = ui.element('div').classes('absolute inset-0 flex items-center justify-center z-0 pointer-events-none')
        with room_wrapper:
            canvas = ui.element('div').classes('relative w-[min(50vw,1800px)] aspect-[1/1] bg-transparent pointer-events-auto').style('transform-origin: center center; transition: transform 80ms ease-out;')
            canvas.on('wheel', on_wheel)
            
            with canvas:
                ui.image(f'/textures/{room_texture}').classes('absolute inset-0 w-full h-full object-contain select-none pointer-events-none')
                
                room = ui.element('div').classes('absolute inset-0 pointer-events-auto')
    asyncio.create_task(statuscheck())

async def statuscheck():
    global cam_x, cam_y, cam_zoom, reseticon
    while True:
        if cam_x != 0.0 or cam_y != 0.0 or cam_zoom != 1.0:
            reseticon.classes(remove='opacity-0', add='opacity-100')
        else:
            reseticon.classes(remove='opacity-100', add='opacity-0')
        await asyncio.sleep(0.1)

def resetbut():
    global reseticon
    reseticon = ui.image(spriteHandler(487, 256, 22, 16, "catUI.png", scale=SPRITE_SCALE)).classes('w-10 h-10 cursor-pointer absolute opacity-0').style('left:0%; top:0%;').on('click', reset)

async def reset():
    global cam_x, cam_y, cam_zoom
    cam_x = 0.0
    cam_y = 0.0
    cam_zoom = 1.0
    update_transform()

def showerui():
    pass
    
def bathui():
    global canvas, room, cat, cat_x, cat_y, water, catjoy, cat_visuals, target_x, target_y, curCatSkin, shower_progress_bar, showernum
    with room:
        with ui.element('div').classes('relative').style('left: 20.5%; top: 31.9%; width: 11.1%; height: 33.3%; transform: rotate(-1deg);').on('click', lambda: showerhelp()):
            ui.image(spriteHandler(0, 0, 64, 192, "showersprite.png", scale=SPRITE_SCALE)).classes('object-contain absolute')
            Preload("realshower.png", 3, "showering", 64, 192)
        shower_progress_bar = ui.linear_progress(value=0.0, show_value=False).classes('absolute w-100 z-50 h-20 instant-progress').style('left:95%; top:40%; transform: rotate(-90deg)')
        with shower_progress_bar:
            showernum = ui.label('0%').classes('absolute-full flex flex-center text-black bg-transparent text-lg content-center h-5').style('left:50%; top:50%; transform: translate(-50%, -50%) rotate(90deg);;')
        
        cat = ui.element('div').classes('absolute').style(f'left:{cat_x}%; top:{cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;')
        with cat:
            cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
            with cat_visuals:
                Preload(f"{curCatSkin}/SittingB.png", 2, "idle")
                Preload("shower.png", 3, "shower")
                Preload(f"{curCatSkin}/RunCatb.png", 6, "walk")
            catjoy = ui.joystick(color='transparent', size=80, on_move=lambda e: catPet(e)).classes('bg-transparent absolute inset-0 w-full h-full custom-cursor')
        
        ui.timer(0, lambda: doAnim("idle", 0.35), once=True)
        update_transform()
        
        ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{cat_visuals.id}")'), once=True)

shower_task = None

async def cleaningcat():
    global water, shower_progress_bar, showernum
    progress = 0.0
   
    while water and progress < 1.0:
        overlap = await cat_visuals.client.run_javascript(f'return window.checkOverlap("c{cat_visuals.id}")')
        if overlap:
            progress += 0.15
            shower_progress_bar.value = progress
            showernum.set_text(f"{int(progress * 100)}%")
        await asyncio.sleep(0.2)    
    if progress >= 1.0:
        with cat_visuals.client:
            ui.notify("Cat is clean now!")
            showerhelp()

async def run_away_loop():
    global water, target_x, target_y
    while water:
        
        target_x = random.uniform(30, 60) 
        target_y = random.uniform(30, 60)
        run_speed = random.uniform(1.0, 2.0) 
        await moveCat(target_x, target_y, speed=run_speed, run_anim="walk", end_anim="walk", restore_tracking=False)
        await asyncio.sleep(0.3)

def showerhelp():
    global water, shower_task, catjoy, evading
    frames = anim_arrays.get("showering")

    if water == False:
        water = True
        if evading:
            evading.cancel()
        evading = asyncio.create_task(run_away_loop())
        asyncio.create_task(cleaningcat())
        asyncio.create_task(cycleclasses())
        
        if shower_task:
            shower_task.cancel()
        
        frames[0].classes(remove='opacity-0', add='opacity-100')
        shower_task = asyncio.create_task(cyclingSprite(frames, 0.2))
            
    else:
        water = False

 
        catjoy.classes(remove='showerhandle1 showerhandle2 showerhandle3 showerhandle4')
        
        if shower_task:
            shower_task.cancel()
            shower_task = None
        evading.cancel()
        evading = None
        
        for f in frames:
            f.classes(remove='opacity-100', add='opacity-0')
        asyncio.create_task(moveCat(55, 50, speed=2, run_anim="walk", end_anim="idle", restore_tracking=True))
        with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
            ui.label('You have cleaned your cat!').classes('text-xl font-bold').style('font-family: runescape; color: #7c5a52;')
            ui.button('Go Home', on_click=dialog.close, color='rgb(255, 210, 194)').style('background-color: #7c5a52; color: white; font-family: runescape; font-size: 1.2vw; padding: 0.5vw 1vw; border-radius: none; margin-top: 1vw;').classes('pixel-border pixel-3d')
        async def dial():
            await dialog
            with dialog.client:
                await home()
        asyncio.create_task(dial())
               
        

def room_page():
    global currentroom, anim_arrays
    currentroom = 'home'      
    anim_arrays = {}          
    
    baseui('Room.png')
    with room:
        room_content()
        
def food_page():
    global currentroom, anim_arrays, current
    if current != 'foodbowl':
        current = 'foodbowl'
    currentroom = 'food'      
    anim_arrays = {}
    baseui('bigbowl.png', 'bg-tan-200')
    with room:
        foodui()

def foodui():
    global room, eatlevel, pressed, blackcat
    with room:
        with ui.element('div').classes('absolute object-contain').style('width: 21vw; height: 30vh; right:28%; top:30%;'):  
            Preload("edafood.png", 3, "foodadd", 256, 256)
        blackcat = ui.element('div').classes('absolute').style('top:120%; width:70vw; transform: translateX(-10%);') #20 good 120 out
        with blackcat:     
            ui.image("/textures/eatingbro.png").classes('object-contain')
        ui.image("/textures/catscale.png").classes('object-contain absolute').style('left:95%; top:10%; width:20vw;').on('click', scaleclickhandle)
        eatlevel = ui.image(spriteHandler(267, 708, 62, 25, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain absolute').style('left:113%; top:55%; width:10vw;') # bottom 55%, top 17%
        asyncio.create_task(oscilatefood())

async def scaleclickhandle():
    global pressed, pos, room, blackcat
    pressed = True
    feedquality = ["too much food.\n Hunger set to 0, decreased Health by 10 points.", "almost the perfect amount of food.\nHunger set to 0.", "the perfect amount of food.\nHunger set to 0, added 20 Energy, added 10 Health points.", "too little food.\nHunger set to 20, Health decreased by 10 points."]
    with room:
        if pos<=36 and pos>=32 or pos<27 and pos>=23:
            feed = 1
        elif pos<32 and pos>27:
            feed = 2
        if pos<=55 and pos>36:
            feed = 0
        if pos<23 and pos>=17:
            feed = 3
        await asyncio.sleep(1)
        getfood = anim_arrays.get("foodadd")
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
            blackcat.style(f'top:{x}%; width:70vw; transform: translateX(-10%);')
            await asyncio.sleep(0.01)
        getfood[3].classes(remove='opacity-100', add='opacity-0')
        await asyncio.sleep(1)
        for x in range(20, 120):
            blackcat.style(f'top:{x}%; width:70vw; transform: translateX(-10%);')
            await asyncio.sleep(0.01)
        with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194);').classes('pixel-border pixel-3d'):
            ui.label(f"You gave your cat {feedquality[feed]}").classes('text-xl font-bold ').style('font-family: runescape; color: #7c5a52; white-space: pre-wrap;')
            ui.button('Go Home', on_click=dialog.close, color='rgb(255, 210, 194)').style('background-color: #7c5a52; color: white; font-family: runescape; font-size: 1.2vw; padding: 0.5vw 1vw; border-radius: none; margin-top: 1vw;').classes('pixel-border pixel-3d')
        async def dial():
            await dialog
            with dialog.client:
                await home()
        asyncio.create_task(dial())        
        
    

async def oscilatefood():
    global eatlevel, pressed, pos
    pressed = False
    up=True
    
    while pressed == False:
        if pos>=55:
            up = False
        if pos<=17:
            up = True
        if up==True:
            pos+=1
        elif up==False:
            pos-=1
        eatlevel.style(f'left:113%; top:{pos}%; width:10vw;')
        await asyncio.sleep(0.025)

def other():
    ui.label('Other page')


def bath_page():
    global currentroom, anim_arrays, water
    currentroom = 'bath'           
    anim_arrays = {}           
    water = False
    
    baseui('emptyshower.png')
    with room:
        bathui()
    

def skins_page():
    global currentroom, anim_arrays, current, skinnamelabel, changingui
    currentroom = 'skins'      
    anim_arrays = {}
    current = 'wardrobe'
    baseui('wardroberoom1.png')
    
    with room:
        skinsui()          

        changingui = ui.element('div').classes('absolute z-20').style("left:7%; top:250%; width:70%; height:35%; ""border-radius:2%; border: 0.2vw solid grey; ""background-color: rgba(189, 154, 142, 0.7);")
        
        with changingui:
            skinnamelabel = ui.label(curCatSkin).style('position:absolute; top:10%; left:50%; transform: translateX(-50%) translateY(-50%); color:white; font-size:2vw; background:transparent;')
            with ui.element('div').classes('absolute').style('height:15%; top:70%; left:15%; display:flex; flex-direction:row; align-items:center; justify-content:center; gap:1vw; padding:2vw; background-color: rgba(0, 0, 0, 0.3); border-radius:1%; width:70%;'):
                ui.image(spriteHandler(392, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; display: inline-block;').on('click', lambda: skinarrows('left'))
                # ui.element('div').classes('absolute').style('left:17.1vw; height:2vw; width:6vw; top:3.8vw; box-shadow: 0 0 40px 10px #000;')
                with ui.image(spriteHandler(180, 797, 41 , 21, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; bottom:32%; left:2%; display: inline-block;').on('click', skinconfirm):
                    ui.label('Confirm').style('position:absolute; top:45%; left:52%; transform: translateX(-50%) translateY(-50%); color:white; font-size:1.2vw; background:transparent;')
                ui.image(spriteHandler(448, 767, 64 , 37, "catUI.png", scale=SPRITE_SCALE)).classes('object-contain').style('width:7vw; display: inline-block;').on('click', lambda: skinarrows('right'))
    
def skinsui():
    global room, cat_x, cat_y, cat, cat_visuals
    cat_x = 40
    with room:
        ui.element('div').classes('absolute object-contain').style('width: 20vw; height: 25vh; right:38%; top:25%; transform: rotate(-15deg);').on('click', wardrobechanging)
        cat = ui.element('div').classes('absolute z-10').style(f'left:{cat_x}%; top:{cat_y}%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;')
        with cat:
            cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
            
            ui.timer(0, wardrobecallableprelod, once=True)
    ui.timer(0, lambda: ui.run_javascript(f'window.startCatTracking("c{cat_visuals.id}")'), once=True)

def wardrobecallableprelod():
    global cat_visuals, curCatSkin
    cat_visuals.clear()
    with cat_visuals:
        Preload(f"{curCatSkin}/SittingB.png", 2, "idle")
        Preload(f"{curCatSkin}/RunCatb.png", 6, "walk")
        Preload(f"{curCatSkin}/JumpCatb.png", 12, "jump")
    doAnim("idle", 0.35)


async def wardrobechanging():
    global changingui, cat, cat_visuals
    
    cat.client.run_javascript('window.setTracking(false)')
    
    
    asyncio.create_task(cameraAction(20, 20, 2.0, speed=2.0))
    asyncio.create_task(moveCat(41, 43, speed=2, run_anim="walk", restore_tracking=False))
    
    await asyncio.sleep(1.5)
    
    
    await asyncio.gather(
        moveCat(45, 9, speed=1.5, run_anim="jump", end_anim="idle", restore_tracking=False, animtime1=0.3, animtime2=0.35, delay=0.85),
        menurollout(115, 23)
    )
    
    set_cat_orientation(False)
    cat.classes(remove='z-10', add='z-50')
    asyncio.create_task(moveCat(35, 30, speed=1.5, run_anim="jump", end_anim="idle", restore_tracking=False, animtime1=0.3, animtime2=0.35, delay=0.7))



def skinarrows(direction):
    global skinnum, curCatSkin, skinnamelabel
    if direction == 'left':
        skinnum -= 1
        if skinnum < 1:
            skinnum = len(skinfolderarray)

    elif direction == 'right':
        skinnum += 1
        if skinnum > len(skinfolderarray):
            skinnum = 1
    curCatSkin = skinfolderarray[skinnum -1]
    skinnamelabel.set_text(curCatSkin)
    wardrobecallableprelod()
    
async def skinconfirm():
    global changingui, cat, cat_visuals
    asyncio.create_task(moveCat(41, 43, speed=1.5, run_anim="jump", end_anim="idle", restore_tracking=False, animtime1=0.3, animtime2=0.35, delay=0.7))
    await asyncio.sleep(0.7)
    asyncio.create_task(cameraAction(0, 0, 1.0, speed=2.0))
    asyncio.create_task(menurollout(23, -150))
    
    await asyncio.sleep(1.5)
    
    asyncio.create_task(moveCat(40, 55, speed=1.5, run_anim="walk"))
    
    await asyncio.sleep(1.5)
    
    cat.client.run_javascript('window.setTracking(true)')
    cat.classes(remove='z-50', add='z-10')
        
def login_page():
    global currentroom, anim_arrays
    currentroom = 'login'      
    anim_arrays = {}
    with ui.element('div').classes('fixed inset-0 z-50 flex items-center justify-center').style('font-family: runescape; background-color: #bd9a8e;'):
        with ui.element('div').classes('pixel-border pixel-3d').style('background-color: #7c5a52; padding: 3vw; border:0.2vw solid #604c45; border-radius: 2%; min-width: 300px;'):
            
            ui.label('Welcome! Please, enter the login details').classes('text-2xl font-bold text-white mb-4 text-center').style('font-family: runescape;')
            
            ui.input(label='Username').classes('mb-4 w-full text-l').style('font-family: runescape; color: #ffd2c2;')
            ui.input(label='Password', password=True).classes('mb-4 w-full text-l font-bold text-black').style('font-family: runescape; color: #ffd2c2;')
            
            ui.button('Login', on_click=lambda: ui.notify('Login clicked!'), color='#bd9a8e').classes('w-full pixel-border pixel-3d').style('color: white; font-family: runescape; font-size: 1.2rem; padding: 10px; border-radius: 0;')

async def menurollout(start, end):
    global changingui
    
    for x in range(start, end, -1):
        changingui.style(f'top:{x}%;')
        await asyncio.sleep(0.01)

ui.sub_pages({
    '/': room_page,
    '/login': login_page,
    '/wardrobe': skins_page,
    '/bath': bath_page,
    '/food': food_page
})


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(native=False)
