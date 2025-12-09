from sys import exit
import datetime as dt
import json
import os
from nicegui import ui
from PIL import Image

cas = dt.datetime.now()
spritesheet = Image.open("cat.png")

zprava = None
kohout = {}
default_kohout = {}

#kohout = {
#    "jmeno": "silver",
#    "hlad": 50,
#    "zizen": 0,
#    "vek": 0,
#    "zivoty": 100,
#    "cistota": 100,
#    "barva": "pink",
#    "energie": 90,
#    "zije": True,
#    "nestastnost": False,
#    "nemoc": False,
#}

def krmeni():
    kohout["hlad"] -= 10
    
    zprava.text =  (f"{kohout["jmeno"]} vypadá šťastně.\nHlad je {kohout["hlad"]}.")
    ui.notify(f"{kohout["jmeno"]} byl nakrmen. Hlad je {kohout["hlad"]}")


def zkontroluj_status():
    if kohout["hlad"] > 120 or kohout["hlad"] < -20:
        kohout["zivoty"] -= 10
    
    if kohout["zizen"] > 120 or kohout["zizen"] < -20:
        kohout["zivoty"] -= 10

    if kohout["zivoty"] <= 0:
        kohout["zije"] = False
        print(f"{kohout["jmeno"]} se nedostal do sněmovny. (died)")
        ui.shutdown()
        exit()
    

def hra():
    kohout["nestastnost"] = False
    kohout["energie"] -= 10
    kohout["hlad"] -= 10
    kohout["zizen"] -= 10
    obrazek.source = cutout(3, 65)
    obrazek.style.transform = "scale(1.2)"
    ui.notify(f"{kohout["jmeno"]} je vic happy, jeho energie je {kohout["energie"]}")

def kys():
    pass

def insult():
    if kohout["nestastnost"] == False:
        kohout["nestastnost"] = True

def spanek():
     kohout["energie"] = 100
     ui.notify(f"{kohout["jmeno"]} se vyspal a má energii {kohout["energie"]}")
     obrazek.source = cutout(0, 45)

def hladoveni():
    global cas

    ted = dt.datetime.now()

    if ted > cas + dt.timedelta(seconds=10):
        kohout["hlad"] += 10
        ui.notify(f"{kohout["jmeno"]} začíná mít hlad. Hlad je {kohout["hlad"]}")
        cas = ted

def starnuti():
    global cas

    ted = dt.datetime.now()

    if ted > cas + dt.timedelta(hours=10):
        kohout["vek"] += 1
        ui.notify(f"{kohout["jmeno"]} má narozeniny")
        cas = ted


def status():
    print(f"{kohout["jmeno"]} me energii {kohout["energie"]} \n hlad {kohout["hlad"]} \n zizen {kohout["zizen"]} \n {kohout["jmeno"]} je {"stastny" if kohout["nestastnost"] == False else "nestastny"} \n zije? {kohout["zije"]} \n nemoc {kohout["nemoc"]} \n je stary {kohout["vek"]}")
        
def load():
    # TODO roset hry, kontrola existence save
    global kohout

    if os.path.isfile("tamagoci.json"):
        with open("tamagoci.json", "r", encoding="utf-8") as f:
            kohout = json.load(f)
    else:
        kohout = default_kohout
        save()


def save():
    global kohout
    with open("tamagoci.json", "w", encoding="utf-8") as f:
        json.dump(kohout, f, ensure_ascii=False, indent=4)

def reset():
    global kohout, default_kohout
    kohout = default_kohout
    save()
    ui.notify("Hra byla resetována.")
def cutout(x, y):
    x = x * 64
    y = y * 64 
    return spritesheet.crop((x, y, x + 64, y + 64))



def main():
    global zprava
    global obrazek
    tlacitka = {
        "krmeni": krmeni,
        "hra": hra,
        "spanek": spanek,
        "umřit": kys,

    }

    load()

    with ui.element("div").classes("w-full h-screen flex items-center justify-center flex-col gap-5"):
        
        obrazek = ui.image(cutout(0, 1)).classes("w-32 h-32")
        zprava = ui.label("vitej")
        with ui.grid(columns=3):
            for jmeno, funkce in tlacitka.items():
                ui.button(jmeno, on_click=funkce)

    print("čau lidi")
    print("""
        |\\---/|
        | o_o |
         \\_^_/
          """)
    hladoveni()

    print(f"Pro nakrmeni {kohout["jmeno"]} stiskni k. \nPro ukončení napiš konec. \nPro happy dejte h \nPro urazit dejte i \nPro spanek dej s \nPro reset hry dejte reset ")

    zkontroluj_status()
    save()


    ui.run(native=True)


main()
