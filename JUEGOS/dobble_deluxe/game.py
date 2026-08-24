from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="dobble_deluxe"

SYMBOLS=[
    "🚀","🍉","🐙","⚡","🎸","🌙","🦋","🔑","🎯","🌵","👻","🍎",
    "💎","☀️","🐢","⚽","🎲","🍓","🚗","⭐","🐬","👑","🔥","🌈",
    "🍀","🎈","🍕","🧲","🦄","🐝","🧁","🎵","🌸","🐠","🛸","🧠"
]

POINTS_TO_WIN=7

def register(app,socketio,active_rooms,current_user,friends_of):
    # Solo dos jugadores: humano vs humano o humano vs CPU.
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Dobble Arena",2)
    from flask_socketio import emit,join_room

    def seat_for(room,uid):
        for i,p in enumerate(room.get("players",[])):
            if str(p.get("id"))==str(uid):
                return i
        return None

    def make_cards():
        common=random.choice(SYMBOLS)
        rest=[x for x in SYMBOLS if x!=common]
        random.shuffle(rest)
        # 8 símbolos por carta, exactamente uno común.
        a=[common]+rest[:7]
        b=[common]+rest[7:14]
        random.shuffle(a);random.shuffle(b)
        return a,b,common

    def fresh_round(room):
        series=room.setdefault("dobble_series",{
            "configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False
        })
        series["round_no"]=int(series.get("round_no",0))+1
        a,b,common=make_cards()
        room["dobble"]={
            "cards":[a,b],
            "common":common,
            "scores":[0,0],
            "round_over":False,
            "winner":None,
            "seq":0,
            "last_event":None,
            "cpu_busy":False
        }

    def public(room):
        series=room.get("dobble_series",{
            "configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False
        })
        g=room.get("dobble")
        return {
            "host_id":room.get("host_id"),
            "players":[
                {"id":p.get("id"),"name":p.get("name"),"bot":bool(p.get("bot"))}
                for p in room.get("players",[])
            ],
            "configured":bool(series.get("configured",False)),
            "target":int(series.get("target",1)),
            "wins":list(series.get("wins",[0,0])),
            "round_no":int(series.get("round_no",0)),
            "champ_over":bool(series.get("champ_over",False)),
            "points_to_win":POINTS_TO_WIN,
            "cards":g.get("cards",[[],[]]) if g else [[],[]],
            "scores":list(g.get("scores",[0,0])) if g else [0,0],
            "round_over":bool(g.get("round_over",False)) if g else False,
            "winner":g.get("winner") if g else None,
            "seq":int(g.get("seq",0)) if g else 0,
            "last_event":g.get("last_event") if g else None,
        }

    def emit_state(room):
        socketio.emit("dobble_state",public(room),room="dobble_"+room["code"])

    def new_cards(room):
        a,b,common=make_cards()
        room["dobble"]["cards"]=[a,b]
        room["dobble"]["common"]=common

    def finish_round_if_needed(room):
        g=room["dobble"]
        if max(g["scores"])<POINTS_TO_WIN:
            return False
        winner=0 if g["scores"][0]>g["scores"][1] else 1
        g["round_over"]=True
        g["winner"]=winner
        series=room["dobble_series"]
        while len(series["wins"])<2:
            series["wins"].append(0)
        series["wins"][winner]+=1
        series["champ_over"]=series["wins"][winner]>=series["target"]
        return True

    def apply_pick(room,seat,symbol,forced_cpu=False):
        g=room.get("dobble")
        if not g or g.get("round_over"):
            return False

        symbol=str(symbol)
        # Debe existir en la carta del jugador que pulsa.
        if symbol not in g["cards"][seat]:
            return False

        correct=(symbol==g["common"])
        scorer=seat if correct else 1-seat

        g["scores"][scorer]+=1
        g["seq"]+=1
        g["last_event"]={
            "seq":g["seq"],
            "picker":seat,
            "symbol":symbol,
            "correct":correct,
            "scorer":scorer,
            "cpu":bool(forced_cpu)
        }

        ended=finish_round_if_needed(room)

        # Las cartas SOLO cambian cuando alguien pulsa/elige algo.
        if not ended:
            new_cards(room)

        return True

    def schedule_next_round(room):
        if room.get("dobble_next_busy"):
            return
        if room.get("dobble_series",{}).get("champ_over"):
            return
        room["dobble_next_busy"]=True
        code=room["code"]

        def task():
            socketio.sleep(3.4)
            r=active_rooms.get(code)
            if not r:
                return
            r["dobble_next_busy"]=False
            if r.get("game")!=SLUG:
                return
            series=r.get("dobble_series",{})
            if not series.get("configured") or series.get("champ_over"):
                return
            fresh_round(r)
            emit_state(r)
            schedule_cpu(r)

        socketio.start_background_task(task)

    def schedule_cpu(room):
        if len(room.get("players",[]))<2 or not room["players"][1].get("bot"):
            return
        g=room.get("dobble")
        if not g or g.get("round_over") or g.get("cpu_busy"):
            return

        g["cpu_busy"]=True
        code=room["code"]

        def task():
            try:
                # La CPU tarda un poco; no hay cambio automático hasta que elige.
                socketio.sleep(random.uniform(5.5,8.5))
                r=active_rooms.get(code)
                if not r or r.get("game")!=SLUG:
                    return
                gg=r.get("dobble")
                if not gg or gg.get("round_over"):
                    return

                # CPU puede equivocarse alguna vez.
                if random.random()<0.52:
                    wrong=[x for x in gg["cards"][1] if x!=gg["common"]]
                    chosen=random.choice(wrong) if wrong else gg["common"]
                else:
                    chosen=gg["common"]

                if apply_pick(r,1,chosen,forced_cpu=True):
                    emit_state(r)
                    if r["dobble"].get("round_over"):
                        schedule_next_round(r)
                    else:
                        schedule_cpu(r)
            finally:
                rr=active_rooms.get(code)
                if rr and rr.get("dobble"):
                    rr["dobble"]["cpu_busy"]=False
                    # Si no terminó y sigue siendo CPU, programar el siguiente intento.
                    if not rr["dobble"].get("round_over"):
                        schedule_cpu(rr)

        socketio.start_background_task(task)

    @socketio.on("dobble_game_join")
    def game_join(data):
        u=current_user()
        code=str(data.get("code","")).upper()
        room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:
            return
        if seat_for(room,u["id"]) is None:
            return

        join_room("dobble_"+code)

        if "dobble_series" not in room:
            room["dobble_series"]={
                "configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False
            }
        if "dobble" not in room:
            fresh_round(room)

        emit("dobble_state",public(room))
        schedule_cpu(room)

    @socketio.on("dobble_configure")
    def configure(data):
        u=current_user()
        code=str(data.get("code","")).upper()
        room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:
            return
        if str(room.get("host_id"))!=str(u["id"]):
            return

        try:
            target=max(1,min(9,int(data.get("target",1))))
        except Exception:
            target=1

        room["dobble_series"]={
            "configured":True,"target":target,"wins":[0,0],"round_no":0,"champ_over":False
        }
        fresh_round(room)
        emit_state(room)
        schedule_cpu(room)

    @socketio.on("dobble_pick")
    def pick(data):
        u=current_user()
        code=str(data.get("code","")).upper()
        room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:
            return

        seat=seat_for(room,u["id"])
        if seat is None:
            return

        # Nunca permitimos que un humano pulse por el asiento CPU.
        if room["players"][seat].get("bot"):
            return

        if apply_pick(room,seat,data.get("symbol",""),forced_cpu=False):
            emit_state(room)
            if room["dobble"].get("round_over"):
                schedule_next_round(room)
            else:
                schedule_cpu(room)

    @socketio.on("dobble_new_championship")
    def new_championship(data):
        u=current_user()
        code=str(data.get("code","")).upper()
        room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:
            return
        if str(room.get("host_id"))!=str(u["id"]):
            return

        room["dobble_series"]={
            "configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False
        }
        fresh_round(room)
        emit_state(room)
