from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="brisca_deluxe"
SUITS=["oros","copas","espadas","bastos"]
VALUES=[1,2,3,4,5,6,7,10,11,12]
POINTS={1:11,3:10,12:4,11:3,10:2,7:0,6:0,5:0,4:0,2:0}
POWER={1:10,3:9,12:8,11:7,10:6,7:5,6:4,5:3,4:2,2:1}

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"La Brisca",4)
    from flask_socketio import emit,join_room

    def card(s,n):
        return {"s":s,"n":n,"pts":POINTS[n]}

    def new_game(r):
        series=r.setdefault("brisca_series",{
            "configured":False,"target":1,
            "wins":[0 for _ in r["players"]],"round_no":0,"champ_over":False
        })
        while len(series["wins"])<len(r["players"]):series["wins"].append(0)
        series["round_no"]=int(series.get("round_no",0))+1
        deck=[card(s,n) for s in SUITS for n in VALUES]
        random.shuffle(deck)
        nplayers=len(r["players"])
        hands=[[] for _ in range(nplayers)]
        for _ in range(3):
            for i in range(nplayers):
                hands[i].append(deck.pop())
        muestra=deck.pop()
        r["brisca"]={
            "hands":hands,
            "stock":deck,
            "muestra":muestra,
            "trump":muestra["s"],
            "trick":[],
            "leader":0,
            "turn":0,
            "scores":[0 for _ in range(nplayers)],
            "captured":[[] for _ in range(nplayers)],
            "phase":"play",
            "exchange_seat":None,
            "draw_order":[],
            "draw_pos":0,
            "message":"Empieza la partida.",
            "last_trick_winner":None,
            "pending_trick_winner":None,
            "over":False,
            "winner":None,
            "started":True,
            "cpu_pending_token":None,
        }

    def seat_for(r,uid):
        for i,p in enumerate(r.get("players",[])):
            if str(p.get("id"))==str(uid):
                return i
        return None

    def card_beats(a,b,lead,trump):
        # True si a gana a b
        if a["s"]==b["s"]:
            return POWER[a["n"]]>POWER[b["n"]]
        if a["s"]==trump and b["s"]!=trump:
            return True
        if b["s"]==trump and a["s"]!=trump:
            return False
        if a["s"]==lead and b["s"]!=lead:
            return True
        return False

    def trick_winner(g):
        lead=g["trick"][0]["card"]["s"]
        win=g["trick"][0]
        for x in g["trick"][1:]:
            if card_beats(x["card"],win["card"],lead,g["trump"]):
                win=x
        return win["seat"]

    def exchange_option(g,seat):
        m=g.get("muestra")
        if not m or not g.get("stock"):
            return None
        hand=g["hands"][seat]
        # Regla clásica:
        # muestra alta (As,3,figuras) -> se cambia por 7 de triunfo
        if m["n"] in (1,3,10,11,12):
            for i,c in enumerate(hand):
                if c["s"]==g["trump"] and c["n"]==7:
                    return {"index":i,"with":7}
        # muestra baja (7,6,5,4) -> se cambia por 2 de triunfo
        if m["n"] in (7,6,5,4):
            for i,c in enumerate(hand):
                if c["s"]==g["trump"] and c["n"]==2:
                    return {"index":i,"with":2}
        return None

    def do_exchange(g,seat):
        opt=exchange_option(g,seat)
        if not opt:return False
        old=g["muestra"]
        g["muestra"]=g["hands"][seat][opt["index"]]
        g["hands"][seat][opt["index"]]=old
        return True

    def prepare_draw_phase(r,winner):
        g=r["brisca"]; n=len(r["players"])
        # Roba primero quien gana la baza y luego en sentido de juego.
        order=[(winner+k)%n for k in range(n)]
        g["trick"]=[]
        g["leader"]=winner
        g["draw_order"]=order
        g["draw_pos"]=0
        g["phase"]="draw"
        g["turn"]=order[0]
        g["exchange_seat"]=None

        # Si ya no queda ninguna carta para robar, continúa directamente.
        if not g["stock"] and g.get("muestra") is None:
            g["phase"]="play"
            g["turn"]=winner
            if all(len(h)==0 for h in g["hands"]):
                finish_game(r)

    def draw_one(r,seat):
        g=r["brisca"]
        if g["over"] or g["phase"]!="draw":return False
        if g["draw_pos"]>=len(g["draw_order"]) or g["draw_order"][g["draw_pos"]]!=seat:return False

        if g["stock"]:
            g["hands"][seat].append(g["stock"].pop())
        elif g.get("muestra") is not None:
            g["hands"][seat].append(g["muestra"])
            g["muestra"]=None
        else:
            # No quedan cartas: termina fase de robo.
            g["draw_pos"]=len(g["draw_order"])

        g["draw_pos"]+=1
        if g["draw_pos"]>=len(g["draw_order"]) or (not g["stock"] and g.get("muestra") is None):
            winner=g["leader"]
            g["phase"]="play"
            g["turn"]=winner
            g["draw_order"]=[]
            g["draw_pos"]=0
            if all(len(h)==0 for h in g["hands"]):
                finish_game(r)
        else:
            g["turn"]=g["draw_order"][g["draw_pos"]]
        return True

    def finish_game(r):
        g=r["brisca"]
        g["over"]=True
        g["phase"]="over"
        best=max(g["scores"])
        winners=[i for i,x in enumerate(g["scores"]) if x==best]
        if len(winners)==1:
            g["winner"]=winners[0]
            g["message"]=r["players"][winners[0]]["name"]+" gana con "+str(best)+" puntos."
        else:
            lw=g.get("last_trick_winner")
            if lw in winners:
                g["winner"]=lw
                g["message"]=r["players"][lw]["name"]+" gana el empate por la última baza."
            else:
                g["winner"]=winners[0]
                g["message"]="Empate a "+str(best)+" puntos."

        series=r.setdefault("brisca_series",{
            "configured":True,"target":1,
            "wins":[0 for _ in r["players"]],"round_no":1,"champ_over":False
        })
        while len(series["wins"])<len(r["players"]):series["wins"].append(0)
        if g["winner"] is not None:
            series["wins"][g["winner"]]+=1
        series["champ_over"]=max(series["wins"] or [0])>=int(series.get("target",1))

    def resolve_trick(r):
        g=r["brisca"]
        w=trick_winner(g)
        score=sum(x["card"]["pts"] for x in g["trick"])
        g["scores"][w]+=score
        g["captured"][w].extend([x["card"] for x in g["trick"]])
        g["last_trick_winner"]=w
        g["pending_trick_winner"]=w
        g["message"]=r["players"][w]["name"]+" gana la baza · +"+str(score)+" puntos"
        # IMPORTANTE: dejamos las cartas sobre la mesa durante un momento.
        g["phase"]="trick_pause"
        g["turn"]=w

        def advance():
            socketio.sleep(1.45)
            rr=active_rooms.get(r["code"])
            if not rr or rr.get("game")!=SLUG or "brisca" not in rr:return
            gg=rr["brisca"]
            if gg.get("phase")!="trick_pause":return
            winner=gg.get("pending_trick_winner")
            gg["pending_trick_winner"]=None

            opt=exchange_option(gg,winner)
            if opt:
                if rr["players"][winner].get("bot"):
                    if do_exchange(gg,winner):
                        gg["message"]=rr["players"][winner]["name"]+" cambia la muestra."
                    prepare_draw_phase(rr,winner)
                else:
                    gg["trick"]=[]
                    gg["phase"]="exchange"
                    gg["exchange_seat"]=winner
                    gg["leader"]=winner
                    gg["turn"]=winner
            else:
                prepare_draw_phase(rr,winner)

            emit_states(rr)
            maybe_cpu(rr["code"])

        socketio.start_background_task(advance)

    def play_card(r,seat,index):
        g=r["brisca"]
        if g["over"] or g["phase"]!="play" or g["turn"]!=seat:return False
        if index<0 or index>=len(g["hands"][seat]):return False
        c=g["hands"][seat].pop(index)
        g["trick"].append({"seat":seat,"card":c})
        if len(g["trick"])==len(r["players"]):
            resolve_trick(r)
        else:
            g["turn"]=(seat+1)%len(r["players"])
        return True

    def cpu_choice(g,seat):
        hand=g["hands"][seat]
        if not hand:return 0
        # IA sencilla: si puede ganar la baza, usa la carta ganadora de menor coste;
        # si no, tira la carta de menor valor/fuerza.
        if g["trick"]:
            lead=g["trick"][0]["card"]["s"]
            current=g["trick"][0]["card"]
            for x in g["trick"][1:]:
                if card_beats(x["card"],current,lead,g["trump"]):
                    current=x["card"]
            candidates=[]
            for i,c in enumerate(hand):
                if card_beats(c,current,lead,g["trump"]):
                    candidates.append((POINTS[c["n"]]*20+POWER[c["n"]],i))
            if candidates:
                candidates.sort()
                return candidates[0][1]
        low=sorted((POINTS[c["n"]]*20+POWER[c["n"]],i) for i,c in enumerate(hand))
        return low[0][1]

    def public_state(r,viewer_id):
        g=r["brisca"]; myseat=seat_for(r,viewer_id)
        players=[]
        for i,p in enumerate(r["players"]):
            players.append({
                "id":p["id"],"name":p["name"],"bot":p.get("bot",False),
                "stars":int(p.get("stars",0) or 0),
                "hand_count":len(g["hands"][i]),
                "score":g["scores"][i],
                "captured_count":len(g["captured"][i]),
            })
        return {
            "players":players,
            "my_seat":myseat,
            "my_hand":g["hands"][myseat] if myseat is not None else [],
            "stock_count":len(g["stock"])+(1 if g.get("muestra") else 0),
            "hidden_stock_count":len(g["stock"]),
            "muestra":g.get("muestra"),
            "trump":g["trump"],
            "trick":g["trick"],
            "turn":g["turn"],
            "leader":g["leader"],
            "phase":g["phase"],
            "exchange_seat":g.get("exchange_seat"),
            "can_exchange":bool(myseat is not None and g["phase"]=="exchange" and g["exchange_seat"]==myseat and exchange_option(g,myseat)),
            "can_draw":bool(myseat is not None and g["phase"]=="draw" and g["turn"]==myseat and (g["stock"] or g.get("muestra") is not None)),
            "draw_pos":g.get("draw_pos",0),
            "scores":g["scores"],
            "message":g["message"],
            "over":g["over"],
            "winner":g["winner"],
            "series":{
                "configured":bool(r.get("brisca_series",{}).get("configured",False)),
                "target":int(r.get("brisca_series",{}).get("target",1)),
                "wins":list(r.get("brisca_series",{}).get("wins",[0 for _ in r["players"]])),
                "round_no":int(r.get("brisca_series",{}).get("round_no",1)),
                "champ_over":bool(r.get("brisca_series",{}).get("champ_over",False)),
            }
        }

    def emit_states(r):
        for p in r.get("players",[]):
            if isinstance(p.get("id"),int):
                socketio.emit("brisca_state",public_state(r,p["id"]),room="user_"+str(p["id"]))

    def cpu_step(code, expected_phase, expected_seat):
        # Una única acción CPU. Al terminar, programa la siguiente si procede.
        socketio.sleep(.32)
        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "brisca" not in r:return
        g=r["brisca"]
        if g.get("over"):return

        # Si mientras esperábamos cambió el turno/fase, este paso ya no vale.
        if g.get("phase")!=expected_phase:return

        if expected_phase=="play":
            if g.get("turn")!=expected_seat:return
            if expected_seat<0 or expected_seat>=len(r["players"]):return
            if not r["players"][expected_seat].get("bot"):return
            if not g["hands"][expected_seat]:return
            idx=cpu_choice(g,expected_seat)
            if not play_card(r,expected_seat,idx):return
            emit_states(r)

        elif expected_phase=="draw":
            if g.get("turn")!=expected_seat:return
            if expected_seat<0 or expected_seat>=len(r["players"]):return
            if not r["players"][expected_seat].get("bot"):return
            if draw_one(r,expected_seat):
                g["message"]=r["players"][expected_seat]["name"]+" roba una carta."
                emit_states(r)

        elif expected_phase=="exchange":
            if g.get("exchange_seat")!=expected_seat:return
            if expected_seat<0 or expected_seat>=len(r["players"]):return
            if not r["players"][expected_seat].get("bot"):return
            do_exchange(g,expected_seat)
            g["message"]=r["players"][expected_seat]["name"]+" cambia la muestra."
            prepare_draw_phase(r,expected_seat)
            emit_states(r)

        maybe_cpu(code)

    def maybe_cpu(code):
        r=active_rooms.get(code)
        if not r or r.get("game")!=SLUG or "brisca" not in r:return
        g=r["brisca"]
        if g.get("over"):return

        phase=g.get("phase")
        seat=None
        if phase in ("play","draw"):
            seat=g.get("turn")
        elif phase=="exchange":
            seat=g.get("exchange_seat")
        else:
            return

        if seat is None or seat<0 or seat>=len(r["players"]):return
        if not r["players"][seat].get("bot"):return

        # Token por estado: impide programar dos veces exactamente la misma acción.
        token=(phase,seat,len(g.get("trick",[])),len(g["hands"][seat]),len(g.get("stock",[])))
        if g.get("cpu_pending_token")==token:return
        g["cpu_pending_token"]=token

        def run():
            try:
                cpu_step(code,phase,seat)
            finally:
                rr=active_rooms.get(code)
                if rr and "brisca" in rr and rr["brisca"].get("cpu_pending_token")==token:
                    rr["brisca"]["cpu_pending_token"]=None
                    # Si sigue siendo turno CPU por cualquier motivo, reintenta.
                    gg=rr["brisca"]
                    ph=gg.get("phase")
                    st=gg.get("exchange_seat") if ph=="exchange" else gg.get("turn")
                    if st is not None and 0<=st<len(rr["players"]) and rr["players"][st].get("bot"):
                        socketio.start_background_task(lambda: (socketio.sleep(.15), maybe_cpu(code)))
        socketio.start_background_task(run)

    @socketio.on("brisca_game_join")
    def br_join(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:return
        seat=seat_for(r,u["id"])
        if seat is None:return
        join_room("game_"+code)
        if "brisca_series" not in r:
            r["brisca_series"]={"configured":False,"target":1,"wins":[0 for _ in r["players"]],"round_no":0,"champ_over":False}
        if "brisca" not in r:
            new_game(r)
        emit("brisca_state",public_state(r,u["id"]))
        maybe_cpu(code)

    @socketio.on("brisca_configure")
    def br_configure(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or str(r.get("host_id"))!=str(u["id"]):return
        try:target=max(1,min(9,int(data.get("target",1))))
        except:target=1
        r["brisca_series"]={"configured":True,"target":target,"wins":[0 for _ in r["players"]],"round_no":0,"champ_over":False}
        new_game(r)
        emit_states(r)
        maybe_cpu(code)

    @socketio.on("brisca_next_game")
    def br_next_game(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or str(r.get("host_id"))!=str(u["id"]):return
        series=r.get("brisca_series",{})
        if not series.get("configured"):return
        if series.get("champ_over"):
            series["configured"]=False
            series["wins"]=[0 for _ in r["players"]]
            series["round_no"]=0
            series["champ_over"]=False
            emit_states(r)
            return
        new_game(r)
        emit_states(r)
        maybe_cpu(code)

    @socketio.on("brisca_play")
    def br_play(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "brisca" not in r:return
        seat=seat_for(r,u["id"])
        try:index=int(data.get("index"))
        except:return
        if seat is not None and play_card(r,seat,index):
            if r["brisca"].get("phase")=="play":
                nxt=r["brisca"].get("turn")
                if nxt is not None and 0<=nxt<len(r["players"]) and r["players"][nxt].get("bot"):
                    r["brisca"]["message"]=r["players"][nxt]["name"]+" está pensando…"
            emit_states(r)
            maybe_cpu(code)

    @socketio.on("brisca_draw")
    def br_draw(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "brisca" not in r:return
        seat=seat_for(r,u["id"])
        if seat is not None and draw_one(r,seat):
            r["brisca"]["message"]=r["players"][seat]["name"]+" roba una carta."
            emit_states(r)
            maybe_cpu(code)

    @socketio.on("brisca_exchange")
    def br_exchange(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "brisca" not in r:return
        g=r["brisca"];seat=seat_for(r,u["id"])
        if seat is None or g["phase"]!="exchange" or g.get("exchange_seat")!=seat:return
        if bool(data.get("yes")):
            do_exchange(g,seat)
            g["message"]="Has cambiado la muestra."
        prepare_draw_phase(r,seat)
        emit_states(r)
        maybe_cpu(code)
