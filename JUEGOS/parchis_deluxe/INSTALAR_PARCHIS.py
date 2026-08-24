from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
app=ROOT/"app.py"
if not app.exists():
    raise SystemExit("Coloca parchis_deluxe dentro de JUEGOS/ antes de ejecutar.")

for n in ["parchis_sala.html","parchis_partida.html"]:
    shutil.copy2(HERE/"templates"/n,ROOT/"templates"/n)

css_target=ROOT/"static"/"style.css"
css=(HERE/"static"/"parchis.css").read_text(encoding="utf-8")
current=css_target.read_text(encoding="utf-8")
if "/* PARCHÍS DELUXE */" not in current:
    css_target.write_text(current+"\n\n"+css,encoding="utf-8")

(HERE.parent/"__init__.py").touch()
(HERE/"__init__.py").touch()

txt=app.read_text(encoding="utf-8")
imp="from JUEGOS.parchis_deluxe.parchis import register_parchis\n"
reg="register_parchis(app, socketio, active_rooms, current_user, find_player, friends_of)\n"
if imp not in txt:
    pos=txt.find("BASE_DIR")
    txt=txt[:pos]+imp+txt[pos:]
if reg not in txt:
    pos=txt.rfind('if __name__=="__main__":')
    if pos<0: pos=txt.rfind('if __name__ == "__main__":')
    txt=txt[:pos]+"\n"+reg+"\n"+txt[pos:]
app.write_text(txt,encoding="utf-8")
print("Parchís Deluxe instalado.")
print('Añade en juegos.html un formulario POST a "/crear_sala/parchis".')
