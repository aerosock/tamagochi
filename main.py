from sys import exit
import datetime as dt
import json
import os
from nicegui import ui, app
from PIL import Image
import pathlib
import asyncio
from itertools import cycle

cat_layer = None
canvas = None
zoom = 1.0
SPRITE_SCALE = 4

anim_arrays = {}           
current_anim_task = None   
current_visible_list = None 
petState = 0               

posx = 0
posy = 0
zoom = 1.0

BASE = pathlib.Path(__file__).parent
app.add_static_files('/static', str(BASE / 'static'))      
app.add_static_files('/textures', str(BASE / 'textures'))  

ui.add_head_html("""
<style>
  @font-face {
    font-family: 'runescape';
    src: url('/static/runescape.ttf') format('truetype');
  }
  html, body {
    margin: 0; padding: 0; width: 100%; height: 100%;
    font-family: 'runescape', sans-serif;
    font-size: 16px;
  }
  .pixelated {
    image-rendering: pixelated;
    image-rendering: -moz-crisp-edges;
    image-rendering: crisp-edges;
  }
  .custom-cursor {
    cursor: url('/static/hand.png') 16 16, auto !important; 
  }
  .custom-cursor * {
    cursor: url('/static/hand.png') 16 16, auto !important; 
  }
</style>
<link rel="stylesheet" href="https://maxst.icons8.com/vue-static/landings/line-awesome/line-awesome/1.3.0/css/line-awesome.min.css">
""")



def clamp(v, lo=0.5, hi=2.0):
    return max(lo, min(hi, v))

def update_transform():
    """Applies both current Zoom and Position together."""
    global zoom, posx, posy, canvas
    if canvas:
        canvas.style(f'transform: translate({posx}px, {posy}px) scale({zoom})')

def on_wheel(e):
    global zoom, canvas
    dy = e.args.get('deltaY', 0)
    zoom = clamp(zoom * (0.9 if dy > 0 else 1.1))
    update_transform()

def spriteHandler(xs, ys, xe, ye, name, scale: int = 1):
    img = Image.open(BASE / 'textures' / name).crop((xs, ys, xs + xe, ys + ye))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), resample=Image.NEAREST)
    return img

def spriteCycler(x, y, step, path, scale: int = 1):
    x *= step
    y *= step
    img = Image.open(BASE / 'textures' / path).crop((x, y, x + step, y + step))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), resample=Image.NEAREST)
    return img

def Preload(path, NofSprites, anim_name):
    global anim_arrays
    Pics = [spriteCycler(x, 0, 32, path, scale=SPRITE_SCALE) for x in range(NofSprites + 1)]
    local_frames = []
    for pic in Pics:
        img = ui.image(pic).classes('absolute w-full h-full object-contain')
        img.set_visibility(False)
        local_frames.append(img)
    anim_arrays[anim_name] = local_frames

def doAnim(anim_name, time):
    global current_anim_task, current_visible_list
    if current_anim_task and not current_anim_task.done():
        current_anim_task.cancel()
    if current_visible_list:
        for f in current_visible_list:
            f.set_visibility(False)
    target_frames = anim_arrays.get(anim_name)
    current_visible_list = target_frames
    target_frames[0].set_visibility(True) 
    current_anim_task = asyncio.create_task(cyclingSprite(target_frames, time))

async def cyclingSprite(frames_list, time):
    NofSprites = len(frames_list) - 1
    while True:
        sequence = list(range(NofSprites + 1)) + list(range(NofSprites - 1, 0, -1))
        for index in sequence:
            for f in frames_list:
                f.set_visibility(False)
            frames_list[index].set_visibility(True)
            await asyncio.sleep(time)


curCatSkin = "BlackCat/SittingB.png"

def catPet(coord):
    global petState
    if petState == 0:
        if coord.y > 0.5:
            petState = 3
        elif coord.y < -0.5:
            petState = 1
    if petState == 1:
        if coord.y > 0.5:
            petAnim()
    if petState == 3:
        if coord.y < -0.5:
            petAnim()

def petAnim():
    global petState
    if petState == 2: return 
    petState = 2
    ui.notify("Cat petted!")
    doAnim("pet", 0.15)
    asyncio.create_task(petEnd())

async def petEnd():
    global petState
    await asyncio.sleep(4) 
    petState = 0
    doAnim("idle", 0.35)

async def cameraAction(target_x, target_y, target_zoom, speed=2.0):
    global posx, posy, zoom
    
    dist_x = target_x - posx
    dist_y = target_y - posy
    dist_z = target_zoom - zoom
    
    max_pixel_dist = max(abs(dist_x), abs(dist_y))
    

    total_steps = int(max(1, max_pixel_dist / speed))
        
    inc_x = dist_x / total_steps
    inc_y = dist_y / total_steps
    inc_z = dist_z / total_steps
    

    for step in range(total_steps):
        posx += inc_x
        posy += inc_y
        zoom += inc_z
        
        update_transform()
        await asyncio.sleep(0.01)
        
    posx = target_x
    posy = target_y
    zoom = target_zoom
    update_transform()

def catmove(x, y, speed, invert):
    global cat
    
    cat.style(f'left:{x}%; top:{y}%; width:12%; aspect-ratio: 1/1; image-rendering: pixelated;')


def changePfp(skin):
    ui.image(spriteCycler(0, 0, 32, skin, scale=SPRITE_SCALE)).classes('w-25 h-25')
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

def press(name: str):
    global current, buttons
    prev = current
    if prev == name: return
    p_up, p_dn, p_icon = buttons[prev]
    p_up.classes(remove='opacity-0', add='opacity-100')
    p_dn.classes(remove='opacity-100', add='opacity-0')
    p_icon.style('transform: translate(-50%, -55%) perspective(600px);')
    n_up, n_dn, n_icon = buttons[name]
    n_up.classes(remove='opacity-100', add='opacity-0')
    n_dn.classes(remove='opacity-0', add='opacity-100')
    n_icon.style('transform: translate(-50%, -57%) perspective(600px) scaleY(1.02);')
    current = name
    if globals().get(name): globals().get(name)()


def home(): 
    ui.notify("home")
    asyncio.create_task(cameraAction(0, 0, 1.0, speed=7))

def shower(): ui.notify("shower")
def sleep(): ui.notify("sleep")

def eat(): 
    ui.notify("eat")
    asyncio.create_task(cameraAction(150, -350, 2.0, speed=5))

def wardrobe(): ui.notify("wardrobe")
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
        button("eat")
        button("wardrobe")
        button("settings")

def bottom_right_button():
    with ui.element('div').classes('relative w-32 h-32 cursor-pointer').style('background-color: #bd9a8e; border-radius: 30%; border: 4px solid #7c5a52;'):
        ui.image("/textures/swords.png").classes('w-24 h-24 cursor-pointer align-middle absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2').on('click', lambda: ui.notify('Battle button clicked'))

def bowlsUI():
    with ui.image(spriteHandler(261, 332, 53, 44, "Furnitures.png", scale=SPRITE_SCALE)).classes('object-contain absolute').style('left:5%; width:5vw;'):
        ui.element('div').classes('absolute cursor-pointer').style('width: 100%; height: 100%; background: transparent;').on('click', lambda: ui.notify('Food bowl clicked'))
    with ui.image(spriteHandler(390, 332, 53, 44, "Furnitures.png", scale=SPRITE_SCALE)).classes('object-contain absolute').style('left:40%; top:35%; width:5vw;'):
        ui.element('div').classes('absolute cursor-pointer').style('width: 100%; height: 100%; background: transparent;').on('click', lambda: ui.notify('Water bowl clicked'))

def bedUI():
    ui.image(spriteHandler(201, 137, 112, 83, "Furnitures.png", scale=SPRITE_SCALE)).classes('w-[10vw] object-contain')


def baseui():
    global canvas, cat_idle, curCatSkin, cat
    with ui.element('div').classes('fixed inset-0 bg-sky-200 overflow-hidden pixelated'):
        with ui.element('div').classes('absolute left-6 top-6 z-50'):
            hud_top_left()
        with ui.element('div').classes('absolute left-6 top-40 z-50'):
            stats_left()
        with ui.element('div').classes('absolute right-6 top-20 z-50'):
            toolbar_right()
        with ui.element('div').classes('absolute right-8 bottom-8 z-50'):
            bottom_right_button()

        room_wrapper = ui.element('div').classes('absolute inset-0 flex items-center justify-center z-0 pointer-events-none')
        with room_wrapper:
            canvas = ui.element('div').classes('relative w-[min(50vw,1800px)] aspect-[1/1] bg-transparent pointer-events-auto').style('transform-origin: center center; transform: scale(1); transition: transform 80ms ease-out;')
            canvas.on('wheel', on_wheel)
            with canvas:
                ui.image('/textures/Room.png').classes('absolute inset-0 w-full h-full object-contain select-none pointer-events-none')
                with ui.element('div').classes('absolute inset-0 pointer-events-auto'):
                    with ui.element('div').classes('absolute cursor-pointer').style('left: 48%; top: 40%; width: 20%; height: 18%;').on('click', lambda: ui.notify('Bed clicked')):
                        bedUI()
                    with ui.element('div').classes('relative').style('left: 35%; top: 72.5%; width: 20%; height: 10%;'):
                        bowlsUI()
                    cat = ui.element('div').classes('absolute').style('left:50%; top:55%; width:15%; aspect-ratio: 1/1; image-rendering: pixelated;')
                    with cat:
                        cat_visuals = ui.element('div').classes('absolute inset-0 w-full h-full pointer-events-none')
                        with cat_visuals:
                            Preload(curCatSkin, 2, "idle")
                            Preload("BlackCat/Idle2Catb.png", 13, "pet")
                            Preload("BlackCat/RunCatb.png", 6, "walk")
                        ui.joystick(color='transparent', size=80, on_move=lambda e: catPet(e)).classes('bg-transparent absolute inset-0 w-full h-full custom-cursor')
                    doAnim("idle", 0.35)

def room():
    baseui()

def other():
    ui.label('Other page')

ui.sub_pages({
    '/': room,
    '/room': room,
    '/other': other,
})

ui.run(native=False)