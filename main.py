from nicegui import ui, app, events
from tortoise import Tortoise, fields, models
import pathlib
from datetime import datetime, timezone
import bcrypt
import game
from models import User, init_db
from game import Game
from pydantic import BaseModel, EmailStr, ValidationError
from models import User
from tortoise.functions import Count, Sum, Avg
from tortoise import Tortoise
from datetime import timedelta

BASE = pathlib.Path(__file__).parent
app.add_static_files('/static', str(BASE / 'static'))      
app.add_static_files('/textures', str(BASE / 'textures'))  
active_games = {}

ui.add_head_html("""
<style>
@keyframes glow-pulse {
  0% { box-shadow: 0 0 5px #fff; }
  50% { box-shadow: 0 0 20px #fff, 0 0 10px #bd9a8e; }
  100% { box-shadow: 0 0 5px #fff; }
}
.glow-effect {
    animation: glow-pulse 1s infinite;
}
.text-my-brown { color: #bd9a8e !important; }
.text-my-grey  { color: #cccccc !important; }
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
  @keyframes rainbow-text {
    0% { color: #e60073; }
    15% { color: #8e44ad; }
    30% { color: #2980b9; }
    45% { color: #27ae60; }
    60% { color: #f1c40f; }
    75% { color: #d35400; }
    100% { color: #e60073; }
}
.celestial-text {
animation: rainbow-text 3s infinite;
font-weight: bold;
text-shadow: 1px 1px 0px rgba(0,0,0,0.2);
}
.ag-theme-balham {
--ag-background-color: #bd9a8e;
--ag-header-background-color: #a6857a;
--ag-odd-background-color: #cbb0a8;
--ag-foreground-color: #3e2b26;
--ag-border-color: #7c5a52;
font-family: 'runescape';
font-size: 1.1em;
}
.ag-header-cell-label {
    color: #f0e4d7;
    font-weight: bold;
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
""", shared=True)




class UserCreate(BaseModel):
    username: str
    password: str
    email: EmailStr

def remove_active_game(user_id):
    if user_id in active_games:
        active_games.pop(user_id, None)



@ui.page('/')
async def route_home():
    game = await get_current_game()
    if not game:
        ui.navigate.to('/login')
        return
    ui.keyboard(on_key=handle_key)
    game.room_page()

@ui.page('/bath')
async def route_bath():
    game = await get_current_game()
    if not game:
        ui.navigate.to('/login')
        return
    game.bath_page()
@ui.page('/wardrobe')
async def route_wardrobe():
    game = await get_current_game()
    if not game:
        ui.navigate.to('/login')
        return
    game.skins_page()
@ui.page('/food')
async def route_food():
    game = await get_current_game()
    if not game:
        ui.navigate.to('/login')
        return
    game.food_page()

@ui.page('/settings')
async def route_settings():
    game = await get_current_game()
    if not game:
        ui.navigate.to('/login')
        return
    game.settings_page()
@ui.page('/dashboard')
async def route_dashboard():
    game = await get_current_game()
    if not game:
        ui.navigate.to('/login')
        return
    if not game.user.isAdmin:
        ui.navigate.to('/')
        return
    game.dashboard_page()

@ui.page('/login')
async def route_login():
    with ui.element('div').classes('fixed inset-0 z-50 flex items-center justify-center').style('font-family: runescape; background-color: #bd9a8e;'):
        with ui.element('div').classes('pixel-border pixel-3d').style('background-color: #7c5a52; padding: 3vw; border:0.2vw solid #604c45; border-radius: 2%; min-width: 300px;'):
            
            ui.label('Welcome! Please, enter the login details').classes('text-2xl font-bold text-white mb-4 text-center').style('font-family: runescape;')
            
            user = ui.input(label='Username').classes('mb-4 w-full text-l').style('font-family: runescape; color: #ffd2c2;')
            pwd = ui.input(label='Password', password=True).classes('mb-4 w-full text-l font-bold text-black').style('font-family: runescape; color: #ffd2c2;')

            ui.button('Login', color='#bd9a8e').classes('w-full pixel-border pixel-3d').style('color: white; font-family: runescape; font-size: 1.2rem; padding: 10px; border-radius: 0;').on('click', lambda: try_login(user, pwd, errortext, regbut))
            errortext = ui.label('Don\'t have an account? Register below!').style('font-size: 1rem; color: red; margin: 0.8rem 0;')
            regbut = ui.button('Register', on_click=lambda: registeriface(user, pwd), color='turquoise').classes('w-full mt-2 text-sm pixel-border pixel-3d inline-block').style('color: white; font-family: runescape; font-size: 1rem; padding: 8px; border-radius: 0; transition: opacity 0.5s;')
            


async def try_login(user_input, pwd_input, field, regbut):
    user = await User.filter(username=user_input.value).first()
    if user and bcrypt.checkpw(pwd_input.value.encode('utf-8'), user.password.encode('utf-8')):
        app.storage.user['user_id'] = user.id
        
        active_games[user.id] = game.Game(user, on_logout_callback=remove_active_game)
        game_instance = await get_current_game()
        game_instance.user.isLoggedIn = True
        await user.save()
        ui.notify('Login successful!', color='positive')

        ui.navigate.to('/')
    else:
        ui.notify('Invalid username or password', color='negative')

async def registeriface(user, pwd):
    with ui.dialog() as dialog, ui.card().style( 'padding: 2vw; background-color: rgb(255, 210, 194); overflow:hidden;').classes('pixel-border pixel-3d'):
        # with ui.element('div').classes('pixel-border pixel-3d').style('background-color: #7c5a52; padding: 3vw; border:0.2vw solid #604c45; border-radius: 2%; min-width: 300px;'):
        ui.icon('cross').classes('absolute top-2 right-2 w-6 h-6 cursor-pointer').on('click', lambda: dialog.close())
        ui.label('Welcome! Please, enter the login details').classes('text-2xl font-bold text-white mb-4 text-center').style('font-family: runescape;')
        
        reg_user = ui.input(label='Username', value=user.value).classes('mb-4 w-full text-l').style('font-family: runescape; color: #ffd2c2;')
        reg_pwd = ui.input(label='Password', password=True, value=pwd.value).classes('mb-4 w-full text-l font-bold text-black').style('font-family: runescape; color: #ffd2c2;')
        reg_email = ui.input(label='Email').classes('mb-4 w-full')
        ui.button('Register', color='#604c45').classes('w-full pixel-border pixel-3d').style('color: white; font-family: runescape; font-size: 1.2rem; padding: 10px; border-radius: 0;').on('click', lambda: trytoreg(reg_user, reg_pwd, reg_email, dialog))
    dialog.open()        
            
    async def trytoreg(u_input, p_input, e_input, dialog):
        try:
            valid_data = UserCreate(
                username=u_input.value,
                password=p_input.value,
                email=e_input.value
            )
            pwdhash = bcrypt.hashpw(valid_data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            await User.create(
                username=valid_data.username, 
                password=pwdhash, 
                email=valid_data.email, 
                age=datetime.now(timezone.utc)
            )
            
            dialog.close()
            ui.notify("User created! Click login now.", color='positive')

        except ValidationError as e:
            error_msg = e.errors()[0]['msg']
            ui.notify(f"Registration Failed: {error_msg}", color='negative')
        
        except Exception as e:
            ui.notify(f"Error: {str(e)}", color='negative')
                              
async def get_current_game():
    ui.colors(primary='#bd9a8e')
    user_id = app.storage.user.get('user_id')
    if not user_id:
        return None

    if user_id in active_games:
        return active_games[user_id]
 
    user = await User.get_or_none(id=user_id)
    if user:
        new_game = Game(user, on_logout_callback=remove_active_game)
        active_games[user_id] = new_game
        return new_game
    
    return None

def handle_key(e: events.KeyEventArguments):
    if not e.action.keydown: return
    
    user_id = app.storage.user.get('user_id')
    if user_id in active_games:
        game = active_games[user_id]
        if game.petting_mode:
            key_value = str(e.key)
            if hasattr(e.key, 'name'):
                key_value = e.key.name
            
            game.handle_rhythm_input(key_value.lower())



if __name__ in {"__main__", "__mp_main__"}:
    app.on_startup(init_db)
    app.on_shutdown(Tortoise.close_connections)
    ui.run(native=False, storage_secret='abcd', on_air='ifucQoW7nDIIj7iI')