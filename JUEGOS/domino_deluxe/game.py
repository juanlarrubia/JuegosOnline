from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="domino_deluxe"

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Dominó Deluxe",4)
    from flask_socketio import emit,join_room

    def seat_for(room,uid):
        for i,p in enumerate(room.get("players",[])):
            if str(p.get("id"))==str(uid): return i
        return None

    def make_set():
        return [[a,b] for a in range(7) for b in range(a,7)]

    def pip_sum(hand):
        return sum(a+b for a,b in hand)

    def can_play(tile,left,right):
        if left is None:return True
        return tile[0] in (left,right) or tile[1] in (left,right)

    def orient(tile,left,right,side=None):
        a,b=tile
        if left is None:
            return [a,b],"right"

        # En la cadena guardamos cada ficha orientada como [extremo_izq, extremo_der].
        # Por tanto, al colocar a la izquierda el valor que conecta debe quedar a la DERECHA.
        if side=="left":
            if a==left:return [b,a],"left"
            if b==left:return [a,b],"left"
            return None,None

        # Al colocar a la derecha el valor que conecta debe quedar a la IZQUIERDA.
        if side=="right":
            if a==right:return [a,b],"right"
            if b==right:return [b,a],"right"
            return None,None

        # Sin lado explícito: derecha primero.
        if a==right:return [a,b],"right"
        if b==right:return [b,a],"right"
        if a==left:return [b,a],"left"
        if b==left:return [a,b],"left"
        return None,None

    def fresh_round(room):
        ser=room.setdefault("domino_series",{
            "configured":False,"target":1,"wins":[],"round_no":0,"champ_over":False
        })
        n=len(room.get("players",[]))
        if len(ser["wins"])!=n:ser["wins"]=[0]*n
        ser["round_no"]+=1
        tiles=make_set();random.shuffle(tiles)
        hands=[[] for _ in range(n)]
        for _ in range(7):
            for s in range(n):
                if tiles:hands[s].append(tiles.pop())
        starter=(ser["round_no"]-1)%max(1,n)
        room["domino"]={
            "hands":hands,"stock":tiles,"chain":[],
            "left":None,"right":None,"turn":starter,
            "round_over":False,"winner":None,"seq":0,"last_event":None,
            "passes":0,"cpu_busy":False
        }

    def public(room,viewer):
        ser=room.get("domino_series",{"configured":False,"target":1,"wins":[],"round_no":0,"champ_over":False})
        g=room.get("domino")
        players=[{"id":p["id"],"name":p["name"],"bot":bool(p.get("bot"))} for p in room.get("players",[])]
        n=len(players)
        if not g:
            return {"host_id":room.get("host_id"),"players":players,"viewer":viewer,
                    "configured":False,"target":1,"wins":[0]*n,"round_no":0,
                    "champ_over":False,"hands":[0]*n,"hand":[],"stock_count":0,"stock_ids":[],
                    "chain":[],"turn":0,"round_over":False,"winner":None,"last_event":None,"seq":0}
        return {
            "host_id":room.get("host_id"),"players":players,"viewer":viewer,
            "configured":bool(ser.get("configured")),"target":int(ser.get("target",1)),
            "wins":list(ser.get("wins",[0]*n)),"round_no":int(ser.get("round_no",0)),
            "champ_over":bool(ser.get("champ_over",False)),
            "hands":[len(h) for h in g["hands"]],
            "hand":[list(t) for t in g["hands"][viewer]],
            "stock_count":len(g["stock"]),
            "stock_ids":list(range(len(g["stock"]))),
            "chain":[list(t) for t in g["chain"]],
            "left":g["left"],"right":g["right"],"turn":g["turn"],
            "round_over":g["round_over"],"winner":g["winner"],
            "last_event":g["last_event"],"seq":g["seq"]
        }

    def emit_all(room):
        code=room["code"]
        for i,p in enumerate(room["players"]):
            if p.get("bot"):continue
            socketio.emit("domino_state",public(room,i),room=f"domino_{code}_{p['id']}")

    def advance_turn(room):
        g=room["domino"];n=len(room["players"])
        g["turn"]=(g["turn"]+1)%n

    def finish_round(room,winner):
        g=room["domino"];ser=room["domino_series"]
        g["round_over"]=True;g["winner"]=winner
        ser["wins"][winner]+=1
        ser["champ_over"]=ser["wins"][winner]>=ser["target"]

    def blocked_winner(room):
        g=room["domino"]
        sums=[pip_sum(h) for h in g["hands"]]
        return min(range(len(sums)),key=lambda i:sums[i])

    def legal_for_hand(g,seat):
        return any(can_play(t,g["left"],g["right"]) for t in g["hands"][seat])

    def do_play(room,seat,index,side=None):
        g=room["domino"]
        if g["round_over"] or g["turn"]!=seat:return False
        if not (0<=index<len(g["hands"][seat])):return False
        tile=g["hands"][seat][index]
        placed,where=orient(tile,g["left"],g["right"],side)
        if placed is None:return False
        g["hands"][seat].pop(index)
        if g["left"] is None:
            g["chain"]=[placed]
            g["left"]=placed[0]
            g["right"]=placed[1]
        elif where=="right":
            g["chain"].append(placed)
            g["right"]=placed[1]
        else:
            g["chain"].insert(0,placed)
            g["left"]=placed[0]
        g["passes"]=0;g["seq"]+=1
        g["last_event"]={"seq":g["seq"],"type":"play","seat":seat,"tile":tile,"placed":placed,"side":where}
        if not g["hands"][seat]:
            finish_round(room,seat)
        else:
            advance_turn(room)
        return True

    def do_draw(room,seat,stock_index):
        g=room["domino"]
        if g["round_over"] or g["turn"]!=seat or not g["stock"]:return False
        # Solo se roba si no hay jugada.
        if legal_for_hand(g,seat):return False
        if not (0<=stock_index<len(g["stock"])):return False
        tile=g["stock"].pop(stock_index)
        g["hands"][seat].append(tile)
        g["seq"]+=1;g["last_event"]={"seq":g["seq"],"type":"draw","seat":seat,"tile":tile}
        # Mantiene turno para decidir si puede tirar o seguir robando.
        return True

    def do_pass(room,seat):
        g=room["domino"]
        if g["round_over"] or g["turn"]!=seat:return False
        # Solo se puede pasar si no puede jugar y ya no quedan fichas para robar.
        if legal_for_hand(g,seat) or g["stock"]:return False
        g["passes"]+=1;g["seq"]+=1;g["last_event"]={"seq":g["seq"],"type":"pass","seat":seat}
        if g["passes"]>=len(room["players"]):
            finish_round(room,blocked_winner(room))
        else:
            advance_turn(room)
        return True

    def cpu_action(room,seat):
        g=room["domino"]
        playable=[i for i,t in enumerate(g["hands"][seat]) if can_play(t,g["left"],g["right"])]
        if playable:
            # Preferencia por dobles y fichas altas.
            def score(i):
                a,b=g["hands"][seat][i]
                return (4 if a==b else 0)+a+b+random.random()
            i=max(playable,key=score)
            return ("play",i,None)
        if g["stock"]:
            return ("draw",random.randrange(len(g["stock"])),None)
        return ("pass",None,None)

    def schedule_cpu(room):
        g=room.get("domino")
        if not g or g["round_over"]:return
        seat=g["turn"]
        if seat>=len(room["players"]) or not room["players"][seat].get("bot"):return
        if g.get("cpu_busy"):return
        g["cpu_busy"]=True;code=room["code"]

        def task():
            try:
                socketio.sleep(1.0)
                r=active_rooms.get(code)
                if not r or r.get("game")!=SLUG:return
                gg=r.get("domino")
                if not gg or gg["round_over"]:return
                seat2=gg["turn"]
                if not r["players"][seat2].get("bot"):return
                action,a,b=cpu_action(r,seat2)
                ok=False
                if action=="play":ok=do_play(r,seat2,a,b)
                elif action=="draw":ok=do_draw(r,seat2,a)
                else:ok=do_pass(r,seat2)
                if ok:
                    emit_all(r)
                    if r["domino"]["round_over"]:schedule_next_round(r)
            finally:
                rr=active_rooms.get(code)
                if rr and rr.get("domino"):
                    rr["domino"]["cpu_busy"]=False
                    if not rr["domino"]["round_over"] and rr["players"][rr["domino"]["turn"]].get("bot"):
                        schedule_cpu(rr)
        socketio.start_background_task(task)

    def schedule_next_round(room):
        if room.get("domino_next_busy") or room.get("domino_series",{}).get("champ_over"):return
        room["domino_next_busy"]=True;code=room["code"]
        def task():
            socketio.sleep(4.2)
            r=active_rooms.get(code)
            if not r:return
            r["domino_next_busy"]=False
            if r.get("game")!=SLUG:return
            ser=r.get("domino_series",{})
            if not ser.get("configured") or ser.get("champ_over"):return
            fresh_round(r);emit_all(r);schedule_cpu(r)
        socketio.start_background_task(task)

    @socketio.on("domino_game_join")
    def game_join(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        seat=seat_for(room,u["id"])
        if seat is None:return
        join_room(f"domino_{code}_{u['id']}")
        if "domino_series" not in room:
            room["domino_series"]={"configured":False,"target":1,"wins":[0]*len(room["players"]),"round_no":0,"champ_over":False}
        if "domino" not in room:fresh_round(room)
        emit("domino_state",public(room,seat))
        schedule_cpu(room)

    @socketio.on("domino_configure")
    def configure(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        if str(room.get("host_id"))!=str(u["id"]):return
        try:target=max(1,min(9,int(data.get("target",1))))
        except:target=1
        room["domino_series"]={"configured":True,"target":target,"wins":[0]*len(room["players"]),"round_no":0,"champ_over":False}
        fresh_round(room);emit_all(room);schedule_cpu(room)

    @socketio.on("domino_play")
    def play(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        seat=seat_for(room,u["id"])
        if seat is None or room["players"][seat].get("bot"):return
        try:index=int(data.get("index"))
        except:return
        side=data.get("side")
        if do_play(room,seat,index,side):
            emit_all(room)
            if room["domino"]["round_over"]:schedule_next_round(room)
            else:schedule_cpu(room)

    @socketio.on("domino_draw")
    def draw(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        seat=seat_for(room,u["id"])
        if seat is None:return
        try:i=int(data.get("stock_index"))
        except:return
        if do_draw(room,seat,i):
            emit_all(room);schedule_cpu(room)

    @socketio.on("domino_pass")
    def pas(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        seat=seat_for(room,u["id"])
        if seat is None:return
        if do_pass(room,seat):
            emit_all(room)
            if room["domino"]["round_over"]:schedule_next_round(room)
            else:schedule_cpu(room)

    @socketio.on("domino_new_championship")
    def new_championship(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        if str(room.get("host_id"))!=str(u["id"]):return
        room["domino_series"]={"configured":False,"target":1,"wins":[0]*len(room["players"]),"round_no":0,"champ_over":False}
        fresh_round(room);emit_all(room)
