import random, time
from uuid import uuid4
from JUEGOS.simple_multiplayer import register_simple_game

COLORS=["red","yellow","green","blue"]
VALUES=["0","1","2","3","4","5","6","7","8","9","reverse","skip","+2"]

def _deck():
    d=[]
    for c in COLORS:
        d.append({"c":c,"v":"0"})
        for v in VALUES[1:]:
            d.append({"c":c,"v":v})
            d.append({"c":c,"v":v})
    for _ in range(4):
        d.append({"c":"wild","v":"wild"})
        d.append({"c":"wild","v":"+4"})
    random.shuffle(d)
    return d

def _take(g):
    if not g["deck"] and len(g["discard"])>1:
        top=g["discard"].pop()
        rebuilt=[]
        for c in g["discard"]:
            rebuilt.append({"c":c.get("base",c["c"]),"v":c["v"]})
        random.shuffle(rebuilt)
        g["deck"]=rebuilt
        g["discard"]=[top]
    return g["deck"].pop() if g["deck"] else None

def _legal(card,top):
    return bool(card and top and (card["c"]=="wild" or card["c"]==top["c"] or card["v"]==top["v"]))

def _player(room,pid):
    return next((p for p in room["players"] if p["id"]==pid),None)

def _setup(room):
    d=_deck()
    hands={}
    for p in room["players"]:
        hands[str(p["id"])]=[]
        for _ in range(7):
            hands[str(p["id"])].append(d.pop())
    first=d.pop()
    guard=0
    while (first["c"]=="wild" or first["v"] in ("+2","skip","reverse")) and guard<30:
        d.insert(0,first);random.shuffle(d);first=d.pop();guard+=1
    room["uno"]={
        "deck":d,
        "hands":hands,
        "discard":[first],
        "turn_index":0,
        "direction":1,
        "drawn_this_turn":False,
        "said_uno":{},
        "catchable_id":None,
        "catch_until":0,
        "winner_id":None,
        "message":"Mismo color, número o comodín.",
        "cpu_running":False
    }

def _turn_player(room):
    if not room.get("players"):return None
    g=room["uno"]
    return room["players"][g["turn_index"]%len(room["players"])]

def _advance(room,steps=1):
    g=room["uno"]
    n=len(room["players"])
    g["turn_index"]=(g["turn_index"]+(steps*g["direction"]))%n
    g["drawn_this_turn"]=False

def _public(room,viewer_id):
    g=room["uno"]
    tp=_turn_player(room)
    me=_player(room,viewer_id)
    hand=g["hands"].get(str(viewer_id),[])
    opponents=[]
    for p in room["players"]:
        if p["id"]==viewer_id:continue
        opponents.append({
            "id":p["id"],"name":p["name"],"bot":p.get("bot",False),
            "fake_user":p.get("fake_user",False),"stars":p.get("stars",0),
            "cards":len(g["hands"].get(str(p["id"]),[]))
        })
    return {
        "code":room["code"],"status":room["status"],
        "me":{"id":viewer_id,"name":me["name"] if me else "Jugador","stars":me.get("stars",0) if me else 0},
        "hand":hand,
        "opponents":opponents,
        "top":g["discard"][-1],
        "deck_count":len(g["deck"]),
        "turn_player_id":tp["id"] if tp else None,
        "turn_name":tp["name"] if tp else "",
        "drawn_this_turn":g["drawn_this_turn"],
        "said_uno":bool(g["said_uno"].get(str(viewer_id),False)),
        "catchable_id":g["catchable_id"] if time.time()<g["catch_until"] else None,
        "catch_until":g["catch_until"],
        "message":g["message"],
        "winner_id":g["winner_id"]
    }

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,"uno_deluxe","UNO Deluxe",8)
    from flask_socketio import emit,join_room

    def emit_all(room):
        for p in room["players"]:
            if isinstance(p["id"],int):
                socketio.emit("uno_state",_public(room,p["id"]),to=f"user_{p['id']}")
        # CPU/fake users have no socket.

    def schedule_cpu(room):
        if room.get("status")!="playing" or not room.get("uno"):return
        tp=_turn_player(room)
        if not tp or not tp.get("bot") or room["uno"].get("cpu_running"):return
        room["uno"]["cpu_running"]=True
        socketio.start_background_task(cpu_turn,room["code"])

    def finish_or_next(room,player,skip_next=False):
        g=room["uno"]
        hand=g["hands"][str(player["id"])]
        if len(hand)==0:
            g["winner_id"]=player["id"]
            room["status"]="finished"
            g["message"]=f"🏆 {player['name']} ha ganado"
            emit_all(room)
            socketio.emit("uno_game_over",{"winner_id":player["id"],"winner":player["name"]},room=f"game_{room['code']}")
            return
        _advance(room,2 if skip_next and len(room["players"])>1 else 1)
        emit_all(room)
        schedule_cpu(room)

    def apply_special(room,card,player,chosen_color=None):
        g=room["uno"]
        skip=False
        if card["v"]=="wild":
            card["base"]="wild";card["c"]=chosen_color if chosen_color in COLORS else random.choice(COLORS)
            g["message"]=f"{player['name']} cambia a {card['c']}"
        elif card["v"]=="+4":
            card["base"]="wild";card["c"]=chosen_color if chosen_color in COLORS else random.choice(COLORS)
            # siguiente jugador roba 4 y pierde turno
            ni=(g["turn_index"]+g["direction"])%len(room["players"])
            target=room["players"][ni]
            for _ in range(4):
                c=_take(g)
                if c:g["hands"][str(target["id"])].append(c)
            g["message"]=f"+4 · {target['name']} roba 4"
            skip=True
        elif card["v"]=="+2":
            ni=(g["turn_index"]+g["direction"])%len(room["players"])
            target=room["players"][ni]
            for _ in range(2):
                c=_take(g)
                if c:g["hands"][str(target["id"])].append(c)
            g["message"]=f"+2 · {target['name']} roba 2"
            skip=True
        elif card["v"]=="skip":
            g["message"]=f"{player['name']} salta el turno"
            skip=True
        elif card["v"]=="reverse":
            if len(room["players"])==2:
                g["message"]=f"{player['name']} cambia sentido · vuelve a jugar"
                skip=True
            else:
                g["direction"]*=-1
                g["message"]=f"{player['name']} cambia el sentido"
        return skip

    def cpu_turn(code):
        room=active_rooms.get(code)
        try:
            socketio.sleep(.9)
            if not room or room.get("status")!="playing":return
            g=room["uno"];p=_turn_player(room)
            if not p or not p.get("bot"):return
            hand=g["hands"][str(p["id"])]
            top=g["discard"][-1]
            idx=next((i for i,c in enumerate(hand) if _legal(c,top)),None)
            if idx is None:
                c=_take(g)
                if c:hand.append(c)
                socketio.emit("uno_sound",{"kind":"draw"},room=f"game_{code}")
                idx=next((i for i,c in enumerate(hand) if _legal(c,top)),None)
                if idx is None:
                    g["message"]=f"{p['name']} roba y pasa"
                    _advance(room);emit_all(room);schedule_cpu(room);return
            card=hand.pop(idx)
            g["discard"].append(card)
            socketio.emit("uno_sound",{"kind":"play"},room=f"game_{code}")
            before=len(hand)+1
            if len(hand)==1:
                # CPU falla UNO un 25% de las veces
                if random.random()<.75:
                    g["said_uno"][str(p["id"])]=True
                    g["catchable_id"]=None;g["catch_until"]=0
                    g["message"]=f"📣 {p['name']} dice ¡UNO!"
                else:
                    g["said_uno"][str(p["id"])]=False
                    g["catchable_id"]=p["id"];g["catch_until"]=time.time()+3.5
                    g["message"]=f"⚠️ {p['name']} no ha dicho UNO"
            skip=apply_special(room,card,p)
            finish_or_next(room,p,skip)
        finally:
            room=active_rooms.get(code)
            if room and room.get("uno"):
                room["uno"]["cpu_running"]=False
                # si tras soltar el bloqueo sigue siendo CPU, continuar
                tp=_turn_player(room) if room.get("status")=="playing" else None
                if tp and tp.get("bot"):
                    schedule_cpu(room)

    @socketio.on("uno_deluxe_start")
    def uno_start(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!="uno_deluxe" or room["host_id"]!=u["id"]:return
        if len(room["players"])<2:
            emit("app_error",{"message":"Añade un rival o una CPU antes de empezar."});return
        _setup(room);room["status"]="playing"
        socketio.emit("simple_game_started",{"code":code,"game":"uno_deluxe"},room=f"game_{code}")

    @socketio.on("uno_join_game")
    def uno_join_game(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!="uno_deluxe" or not _player(room,u["id"]):return
        join_room(f"game_{code}")
        join_room(f"user_{u['id']}")
        if room.get("status")=="playing" and room.get("uno"):
            emit("uno_state",_public(room,u["id"]))
            schedule_cpu(room)

    @socketio.on("uno_play")
    def uno_play(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("status")!="playing" or not room.get("uno"):return
        g=room["uno"];tp=_turn_player(room)
        if not tp or tp["id"]!=u["id"]:return
        hand=g["hands"][str(u["id"])]
        try:i=int(data.get("index"))
        except:return
        if i<0 or i>=len(hand):return
        card=hand[i]
        if not _legal(card,g["discard"][-1]):return
        # UNO debe haberse anunciado antes de bajar de 2 a 1
        before=len(hand)
        card=hand.pop(i);g["discard"].append(card)
        socketio.emit("uno_sound",{"kind":"play"},room=f"game_{code}")
        if before==2 and not g["said_uno"].get(str(u["id"]),False):
            for _ in range(2):
                c=_take(g)
                if c:hand.append(c)
            g["message"]="⚠️ No dijiste UNO · robas 2 cartas"
        g["said_uno"][str(u["id"])]=False
        skip=apply_special(room,card,tp,data.get("color"))
        finish_or_next(room,tp,skip)

    @socketio.on("uno_draw")
    def uno_draw(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("status")!="playing":return
        g=room["uno"];tp=_turn_player(room)
        if not tp or tp["id"]!=u["id"] or g["drawn_this_turn"]:return
        hand=g["hands"][str(u["id"])]
        if any(_legal(c,g["discard"][-1]) for c in hand):return
        c=_take(g)
        if c:hand.append(c)
        g["drawn_this_turn"]=True
        g["message"]="Carta robada"
        socketio.emit("uno_sound",{"kind":"draw"},room=f"game_{code}")
        emit_all(room)

    @socketio.on("uno_pass")
    def uno_pass(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("status")!="playing":return
        g=room["uno"];tp=_turn_player(room)
        if not tp or tp["id"]!=u["id"] or not g["drawn_this_turn"]:return
        hand=g["hands"][str(u["id"])]
        if any(_legal(c,g["discard"][-1]) for c in hand):return
        _advance(room);g["message"]=f"{u['username']} pasa";emit_all(room);schedule_cpu(room)

    @socketio.on("uno_call")
    def uno_call(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("status")!="playing":return
        g=room["uno"];tp=_turn_player(room)
        if not tp or tp["id"]!=u["id"]:return
        hand=g["hands"][str(u["id"])]
        if len(hand)==2 and any(_legal(c,g["discard"][-1]) for c in hand):
            g["said_uno"][str(u["id"])]=True;g["message"]=f"📣 {u['username']} dice ¡UNO!";emit_all(room)

    @socketio.on("uno_catch")
    def uno_catch(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("status")!="playing":return
        g=room["uno"];cid=g.get("catchable_id")
        if not cid or time.time()>=g.get("catch_until",0):return
        if cid==u["id"]:return
        hand=g["hands"].get(str(cid),[])
        for _ in range(2):
            c=_take(g)
            if c:hand.append(c)
        victim=_player(room,cid)
        g["message"]=f"😈 {victim['name'] if victim else 'Jugador'} no dijo UNO · roba 2"
        g["catchable_id"]=None;g["catch_until"]=0;emit_all(room)
