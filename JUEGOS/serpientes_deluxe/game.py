from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="serpientes_deluxe"
LADDERS={10:11, 12:33, 16:35, 20:40, 44:76, 60:81, 69:90}
SNAKES={38:4, 63:38, 67:48, 80:59, 94:66, 97:77}
COLORS=["blue","red","green","purple"]

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Serpientes y Escaleras",4)
    from flask_socketio import emit,join_room

    def seat_for(r,uid):
        for i,p in enumerate(r.get("players",[])):
            if str(p.get("id"))==str(uid):return i
        return None

    def new_game(r):
        n=len(r["players"])
        colors=COLORS[:]
        random.shuffle(colors)
        starter=random.randrange(n)
        r["snake"]={
            "positions":[0 for _ in range(n)],
            "colors":colors[:n],
            "turn":starter,
            "starter":starter,
            "dice":None,
            "over":False,
            "winner":None,
            "move_no":0,
            "last_move":None,
            "message":"🎲 Sorteo inicial: empieza "+r["players"][starter]["name"],
        }

    def public_state(r):
        g=r["snake"]
        return {
            "players":[{"id":p["id"],"name":p["name"],"bot":p.get("bot",False),"stars":int(p.get("stars",0) or 0)}
                       for p in r["players"]],
            "positions":g["positions"],
            "colors":g["colors"],
            "turn":g["turn"],
            "starter":g["starter"],
            "dice":g["dice"],
            "over":g["over"],
            "winner":g["winner"],
            "move_no":g["move_no"],
            "last_move":g["last_move"],
            "message":g["message"],
        }

    def emit_state(r):
        socketio.emit("snake_state",public_state(r),room="game_"+r["code"])

    def do_roll(r,seat):
        g=r["snake"]
        if g["over"] or g["turn"]!=seat:return False
        d=random.randint(1,6)
        old=g["positions"][seat]
        tentative=old+d
        if tentative>100:
            new=old
            special=None
            msg=r["players"][seat]["name"]+" saca "+str(d)+" pero necesita tirada exacta."
        else:
            new=tentative
            special=None
            if new in LADDERS:
                special="ladder";new=LADDERS[new]
            elif new in SNAKES:
                special="snake";new=SNAKES[new]
            msg=r["players"][seat]["name"]+" saca "+str(d)
        g["positions"][seat]=new
        g["dice"]=d
        g["move_no"]+=1
        g["last_move"]={"seat":seat,"from":old,"to":new,"dice":d,"special":special,"seq":g["move_no"]}
        if new==100:
            g["over"]=True;g["winner"]=seat
            g["message"]="🏆 "+r["players"][seat]["name"]+" gana la partida."
        else:
            if special=="ladder":msg+=" · 🪜 sube hasta "+str(new)
            elif special=="snake":msg+=" · 🐍 baja hasta "+str(new)
            g["message"]=msg
            g["turn"]=(seat+1)%len(r["players"])
        return True

    def cpu_action(code,seat,seq):
        # Espera suficiente para que el movimiento anterior termine
        # visualmente en todos los dispositivos antes de tirar otra vez.
        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "snake" not in r:return
        prev=r["snake"].get("last_move") or {}
        dice=int(prev.get("dice") or 0)
        extra=1.0 if prev.get("special") else 0.0
        delay=1.55 + dice*0.38 + extra
        socketio.sleep(delay)

        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "snake" not in r:return
        g=r["snake"]
        if g["over"] or g["turn"]!=seat:return
        if do_roll(r,seat):
            emit_state(r)
            maybe_cpu(code)

    def maybe_cpu(code):
        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "snake" not in r:return
        g=r["snake"]
        if g["over"]:return
        seat=g["turn"]
        if not r["players"][seat].get("bot"):return
        token=(seat,g["move_no"])
        if g.get("cpu_token")==token:return
        g["cpu_token"]=token
        def run():
            try:cpu_action(code,seat,g["move_no"])
            finally:
                rr=active_rooms.get(code)
                if rr and "snake" in rr:rr["snake"]["cpu_token"]=None
        socketio.start_background_task(run)

    @socketio.on("snake_game_join")
    def snake_join(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:return
        if seat_for(r,u["id"]) is None:return
        join_room("game_"+code)
        if "snake" not in r:new_game(r)
        emit("snake_state",public_state(r))
        maybe_cpu(code)

    @socketio.on("snake_roll")
    def snake_roll(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "snake" not in r:return
        seat=seat_for(r,u["id"])
        if seat is None:return
        if do_roll(r,seat):
            emit_state(r)
            maybe_cpu(code)
