from sys import exit
import datetime as dt
import json
import os

cas = dt.datetime.now()

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
    print(f"{kohout["jmeno"]} vypadá šťastně.\nHlad je {kohout["hlad"]}.")


def zkontroluj_status():
    if kohout["hlad"] > 120 or kohout["hlad"] < -20:
        kohout["zivoty"] -= 10
    
    if kohout["zizen"] > 120 or kohout["zizen"] < -20:
        kohout["zivoty"] -= 10

    if kohout["zivoty"] <= 0:
        kohout["zije"] = False
        print(f"{kohout["jmeno"]} se nedostal do sněmovny. (died)")
        exit()
    

def hra():
    if kohout["nestastnost"] == True:
        kohout["nestastnost"] = False
        kohout["energie"] -= 10
        kohout["hlad"] -= 10
        kohout["zizen"] -= 10
        print(f"{kohout["jmeno"]} je vic happy, jeho energie je {kohout["energie"]}")


def insult():
    if kohout["nestastnost"] == False:
        kohout["nestastnost"] = True

def spanek():
    if kohout["energie"] <= 100:
        kohout["energie"] = 100

def hladoveni():
    global cas

    ted = dt.datetime.now()

    if ted > cas + dt.timedelta(seconds=10):
        kohout["hlad"] += 10
        print(f"{kohout["jmeno"]} zacina mit hlad")
        cas = ted

def starnuti():
    global cas

    ted = dt.datetime.now()

    if ted > cas + dt.timedelta(hours=10):
        kohout["vek"] += 1
        print(f"{kohout["jmeno"]} ma narozeniny")
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



def main():
    load()


    print("čau lidi")
    print("""
        |\\---/|
        | o_o |
         \\_^_/
          """)
    while True:
        hladoveni()

        print(f"Pro nakrmeni {kohout["jmeno"]} stiskni k. \nPro ukončení napiš konec. \nPro happy dejte h \nPro urazit dejte i \nPro spanek dej s \nPro reset hry dejte reset ")

        uziv_input = input()


#        if uziv_input.lower() == "konec":
#            print("Konec kariéry...")
#            break
#        elif uziv_input.lower() == "k":
#            krmeni()
#        elif uziv_input.lower() == "h":
#            hra()
#        elif uziv_input.lower() == "i":
#           insult()
#        elif uziv_input.lower() == "s":
#            spanek()


        match uziv_input.lower():
            case "h":
                print("hrat")
                hra()
            case "s":
                print("spat")
                spanek()
            case "k":
                print("nakrmit")
                krmeni()
            case "i":
                print("insult")
                insult()
            case "konec":
                print("Konec kariéry...")
                break
            case "stats":
                status()
            case "reset":
                reset()
            case _:
                print("NE")
        
        zkontroluj_status()
        save()



if __name__ == "__main__":
    main()
