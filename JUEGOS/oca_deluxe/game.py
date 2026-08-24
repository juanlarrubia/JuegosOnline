from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="oca_deluxe"
GEESE=[5,9,14,18,23,27,32,36,41,45,50,54,59]
BRIDGES={6:12,12:6}
DICE_CELLS={26:53,53:26}
COLORS=["red","blue","green","purple"]

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"La Oca Deluxe",4)
    from flask_socketio import emit,join_room

    def seat_for(r,uid):
        for i,p in enumerate(r.get("players",[])):
            if str(p.get("id"))==str(uid):return i
        return None

    def new_game(r):
        n=len(r["players"])
        series=r.setdefault("oca_series",{
            "configured":False,"target":1,
            "wins":[0 for _ in r["players"]],"round_no":0,"champ_over":False
        })
        while len(series["wins"])<n: series["wins"].append(0)
        series["round_no"]=int(series.get("round_no",0))+1
        colors=COLORS[:];random.shuffle(colors);starter=random.randrange(n)
        r["oca"]={
            "positions":[0]*n,"colors":colors[:n],"turn":starter,"starter":starter,"dice":None,
            "over":False,"winner":None,"move_no":0,"last_move":None,
            "skip":[0]*n,"extra_roll":False,
            "message":"🎲 Sorteo inicial: empieza "+r["players"][starter]["name"]
        }

    def state(r):
        g=r["oca"]
        return {
            "players":[{"id":p["id"],"name":p["name"],"bot":p.get("bot",False),"stars":int(p.get("stars",0) or 0)} for p in r["players"]],
            "positions":g["positions"],"colors":g["colors"],"turn":g["turn"],"starter":g["starter"],
            "dice":g["dice"],"over":g["over"],"winner":g["winner"],"move_no":g["move_no"],
            "last_move":g["last_move"],"skip":g["skip"],"message":g["message"],
            "host_id":r.get("host_id"),
            "series":{
                "configured":bool(r.get("oca_series",{}).get("configured",False)),
                "target":int(r.get("oca_series",{}).get("target",1)),
                "wins":list(r.get("oca_series",{}).get("wins",[0 for _ in r["players"]])),
                "round_no":int(r.get("oca_series",{}).get("round_no",1)),
                "champ_over":bool(r.get("oca_series",{}).get("champ_over",False)),
            }
        }

    def emit_state(r):
        socketio.emit("oca_state",state(r),room="game_"+r["code"])

    def advance_turn(r,current):
        g=r["oca"];n=len(r["players"]);seat=(current+1)%n
        checked=0
        while checked<n and g["skip"][seat]>0:
            g["skip"][seat]-=1
            g["message"]=r["players"][seat]["name"]+" pierde este turno."
            seat=(seat+1)%n;checked+=1
        g["turn"]=seat

    def do_roll(r,seat):
        g=r["oca"]
        if g["over"] or g["turn"]!=seat:return False
        d=random.randint(1,6);old=g["positions"][seat]
        raw=old+d
        bounced=False
        if raw>63:
            new=63-(raw-63);bounced=True
        else:new=raw
        path_target=new;special=None;extra=False;msg=r["players"][seat]["name"]+" saca "+str(d)

        if new in GEESE:
            idx=GEESE.index(new)
            new = GEESE[idx+1] if idx+1<len(GEESE) else 63
            special="goose";extra=True
            msg="🪿 De oca a oca y tiro porque me toca"
        elif new in BRIDGES:
            new=BRIDGES[new];special="bridge";extra=True
            msg="🌉 De puente a puente y tiro porque me lleva la corriente"
        elif new==19:
            g["skip"][seat]=1;special="inn";msg="🏨 Posada: pierdes 1 turno"
        elif new==31:
            g["skip"][seat]=2;special="well";msg="🕳️ Pozo: pierdes 2 turnos"
        elif new==42:
            new=30;special="labyrinth";msg="🌀 Del laberinto al 30"
        elif new==52:
            g["skip"][seat]=2;special="prison";msg="🔒 Cárcel: pierdes 2 turnos"
        elif new in DICE_CELLS:
            new=DICE_CELLS[new];special="dice";extra=True
            msg="🎲 De dado a dado y tiro porque me ha tocado"
        elif new==58:
            new=0;special="death";msg="💀 Muerte: vuelves a la salida"

        g["positions"][seat]=new;g["dice"]=d;g["move_no"]+=1
        g["last_move"]={"seat":seat,"from":old,"landing":path_target,"to":new,"dice":d,
                        "special":special,"extra":extra,"bounced":bounced,"seq":g["move_no"]}
        if new==63:
            g["over"]=True;g["winner"]=seat;g["message"]="🏆 "+r["players"][seat]["name"]+" gana la partida."
            series=r.setdefault("oca_series",{"configured":True,"target":1,"wins":[0 for _ in r["players"]],"round_no":1,"champ_over":False})
            while len(series["wins"])<len(r["players"]):series["wins"].append(0)
            series["wins"][seat]+=1
            series["champ_over"]=max(series["wins"] or [0])>=int(series.get("target",1))
        else:
            if bounced and not special:msg+=" · rebota hasta "+str(new)
            g["message"]=msg
            if not extra:advance_turn(r,seat)
            else:g["turn"]=seat
        return True

    def cpu_action(code,seat):
        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "oca" not in r:return
        prev=r["oca"].get("last_move") or {}
        dice=int(prev.get("dice") or 0);extra=.9 if prev.get("special") else 0
        socketio.sleep(1.6+dice*.34+extra)
        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "oca" not in r:return
        if r["oca"]["over"] or r["oca"]["turn"]!=seat:return
        if do_roll(r,seat):
            emit_state(r);maybe_cpu(code)

    def maybe_cpu(code):
        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "oca" not in r:return
        g=r["oca"]
        if g["over"]:return
        seat=g["turn"]
        if not r["players"][seat].get("bot"):return
        token=(seat,g["move_no"])
        if g.get("cpu_token")==token:return
        g["cpu_token"]=token
        def run():
            try:cpu_action(code,seat)
            finally:
                rr=active_rooms.get(code)
                if rr and "oca" in rr:rr["oca"]["cpu_token"]=None
        socketio.start_background_task(run)

    @socketio.on("oca_game_join")
    def join_game(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or seat_for(r,u["id"]) is None:return
        join_room("game_"+code)
        if "oca_series" not in r:
            r["oca_series"]={"configured":False,"target":1,"wins":[0 for _ in r["players"]],"round_no":0,"champ_over":False}
        if "oca" not in r:new_game(r)
        emit("oca_state",state(r));maybe_cpu(code)


    @socketio.on("oca_configure")
    def configure_series(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or str(r.get("host_id"))!=str(u["id"]):return
        try:target=max(1,min(9,int(data.get("target",1))))
        except:target=1
        r["oca_series"]={"configured":True,"target":target,"wins":[0 for _ in r["players"]],"round_no":0,"champ_over":False}
        new_game(r)
        emit_state(r)
        maybe_cpu(code)

    @socketio.on("oca_next_game")
    def next_game(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or str(r.get("host_id"))!=str(u["id"]):return
        series=r.get("oca_series",{})
        if not series.get("configured"):return
        if series.get("champ_over"):
            series["configured"]=False
            series["wins"]=[0 for _ in r["players"]]
            series["round_no"]=0
            series["champ_over"]=False
            emit_state(r)
            return
        new_game(r)
        emit_state(r)
        maybe_cpu(code)

    @socketio.on("oca_roll")
    def roll(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "oca" not in r:return
        seat=seat_for(r,u["id"])
        if seat is not None and do_roll(r,seat):
            emit_state(r);maybe_cpu(code)
