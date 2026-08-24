from flask import render_template, redirect, url_for, flash, jsonify
from uuid import uuid4
import random

COLORS = ["rojo", "azul", "verde", "amarillo"]
COLOR_LABELS = {"rojo":"Rojo","azul":"Azul","verde":"Verde","amarillo":"Amarillo"}

# Salidas separadas 17 casillas en un circuito de 68.
OFFSETS = {"amarillo":4, "azul":21, "rojo":38, "verde":55}

# Seguros comunes. Las cuatro salidas también cuentan como seguro.
SAFE_GLOBAL = {4,11,16,21,28,33,38,45,50,55,62,67}
EXITS = {4,21,38,55}

def _new_piece(color, i):
    return {
        "id": f"{color}_{i}",
        "color": color,
        "n": i + 1,
        "state": "home",       # home | track | finish | done
        "pos": -1,             # recorrido local 0..67
        "finish_pos": -1,      # 0..7 (7 = meta)
    }

def _new_color(color):
    return {"color":color, "pieces":[_new_piece(color, i) for i in range(4)]}

def _player(room, uid):
    return next((p for p in room["players"] if p["id"] == uid), None)

def _piece(room, pid):
    for c in COLORS:
        for p in room["colors"][c]["pieces"]:
            if p["id"] == pid:
                return p
    return None

def _global_pos(piece_or_color, local_pos=None):
    if isinstance(piece_or_color, dict):
        return (OFFSETS[piece_or_color["color"]] + piece_or_color["pos"]) % 68
    return (OFFSETS[piece_or_color] + local_pos) % 68

def _public(room):
    turn_color = _turn_color(room)
    owner = _owner_of_color(room, turn_color) if turn_color else None
    turn_id = owner["id"] if owner else None
    return {
        "code": room["code"],
        "game": "parchis_deluxe",
        "game_name": "Parchís Deluxe",
        "host_id": room["host_id"],
        "host_name": room["host_name"],
        "status": room["status"],
        "turn_player_id": turn_id,
        "turn_color": turn_color,
        "color_turn_order": room.get("color_turn_order", []),
        "players": [{
            "id": p["id"],
            "name": p["name"],
            "bot": p.get("bot", False),
            "fake_user": p.get("fake_user", False),
            "stars": p.get("stars", 0),
            "colors": p.get("colors", []),
            "score": p.get("score", 0),
            "doubles_streak": p.get("doubles_streak", 0),
        } for p in room["players"]],
        "colors": room["colors"],
        "dice": room.get("dice"),
        "pending_dice": room.get("pending_dice", []),
        "rolled": room.get("rolled", False),
        "actions": room.get("actions", []),
        "bonus_queue": room.get("bonus_queue", []),
        "last_event": room.get("last_event", ""),
        "winner": room.get("winner"),
        "must_open_barrier": room.get("must_open_barrier", False),
    }

def _pieces_at_global(room, gp):
    out = []
    for c in COLORS:
        for p in room["colors"][c]["pieces"]:
            if p["state"] == "track" and _global_pos(p) == gp:
                out.append(p)
    return out

def _barrier_positions(room):
    barriers = set()
    for gp in range(68):
        pieces = _pieces_at_global(room, gp)
        counts = {}
        for p in pieces:
            counts[p["color"]] = counts.get(p["color"], 0) + 1
        if any(v >= 2 for v in counts.values()):
            barriers.add(gp)
    return barriers

def _own_barrier_piece_ids(room, player):
    ids = set()
    for gp in _barrier_positions(room):
        tc=_turn_color(room)
        pieces = [p for p in _pieces_at_global(room, gp) if p["color"] == tc]
        by_color = {}
        for p in pieces:
            by_color.setdefault(p["color"], []).append(p)
        for group in by_color.values():
            if len(group) >= 2:
                ids.update(p["id"] for p in group)
    return ids

def _home_pieces(room, player):
    c=_turn_color(room)
    if not c or c not in player.get("colors",[]): return []
    return [p for p in room["colors"][c]["pieces"] if p["state"]=="home"]

def _exit_blocked_by_own_barrier(room, color):
    gp = OFFSETS[color]
    pieces = _pieces_at_global(room, gp)
    own = [p for p in pieces if p["color"] == color]
    return len(own) >= 2

def _simulate_steps(room, piece, amount):
    """
    Devuelve (legal, path, final_state, capture_target_id).
    path: lista de descriptores para animar cada casilla.
    El rebote en pasillo de llegada se hace dentro de la misma jugada.
    """
    if amount <= 0 or piece["state"] in ("home", "done"):
        return False, [], None, None

    state = piece["state"]
    pos = piece["pos"]
    finish = piece["finish_pos"]
    path = []
    barriers = _barrier_positions(room)

    if state == "track":
        for _ in range(amount):
            if state == "track":
                if pos < 67:
                    pos += 1
                    gp = (OFFSETS[piece["color"]] + pos) % 68
                    # Una barrera bloquea paso y llegada.
                    if gp in barriers:
                        return False, [], None, None
                    path.append({"state":"track","pos":pos,"global":gp})
                else:
                    state = "finish"
                    finish = 0
                    path.append({"state":"finish","finish_pos":0})
            else:
                break

        # continuar por pasillo si faltan pasos
        used = len(path)
        remaining = amount - used
        if state == "finish" and remaining > 0:
            cur = finish
            direction = 1
            for _ in range(remaining):
                nxt = cur + direction
                if nxt > 7:
                    direction = -1
                    nxt = 6
                if nxt < 0:
                    return False, [], None, None
                cur = nxt
                path.append({"state":"finish","finish_pos":cur})
            finish = cur

    elif state == "finish":
        cur = finish
        direction = 1
        for _ in range(amount):
            nxt = cur + direction
            if nxt > 7:
                direction = -1
                nxt = 6
            if nxt < 0:
                return False, [], None, None
            cur = nxt
            path.append({"state":"finish","finish_pos":cur})
        finish = cur

    final_state = state
    if final_state == "finish" and finish == 7:
        final_state = "done"

    # Comprobar ocupación final en circuito.
    capture_id = None
    if final_state == "track":
        gp = path[-1]["global"] if path else _global_pos(piece)
        occupants = [p for p in _pieces_at_global(room, gp) if p["id"] != piece["id"]]

        own_same = [p for p in occupants if p["color"] == piece["color"]]
        if len(own_same) >= 2:
            return False, [], None, None

        # En seguro pueden convivir hasta dos fichas, sin captura.
        if gp in SAFE_GLOBAL:
            if len(occupants) >= 2:
                return False, [], None, None
        else:
            enemies = [p for p in occupants if p["color"] != piece["color"]]
            if len(enemies) >= 2:
                return False, [], None, None
            if len(enemies) == 1:
                capture_id = enemies[0]["id"]

    return True, path, {
        "state": final_state,
        "pos": pos if final_state == "track" else -1,
        "finish_pos": finish if final_state == "finish" else -1,
    }, capture_id

def _apply_move(room, piece, amount):
    legal, path, final, capture_id = _simulate_steps(room, piece, amount)
    if not legal:
        return None

    old = {
        "state": piece["state"],
        "pos": piece["pos"],
        "finish_pos": piece["finish_pos"]
    }

    piece["state"] = final["state"]
    piece["pos"] = final["pos"]
    piece["finish_pos"] = final["finish_pos"]

    captured = None
    if capture_id:
        captured = _piece(room, capture_id)
        if captured:
            captured["state"]="home"
            captured["pos"]=-1
            captured["finish_pos"]=-1

    reached_goal = piece["state"] == "done"

    return {
        "piece_id": piece["id"],
        "color": piece["color"],
        "amount": amount,
        "from": old,
        "path": path,
        "captured": captured["id"] if captured else None,
        "goal": reached_goal,
    }

def _can_exit(room, piece):
    return piece["state"] == "home" and not _exit_blocked_by_own_barrier(room, piece["color"])

def _exit_piece(room, piece):
    gp = OFFSETS[piece["color"]]
    occupants = _pieces_at_global(room, gp)
    own = [p for p in occupants if p["color"] == piece["color"]]
    if len(own) >= 2:
        return None

    captured = None
    enemies = [p for p in occupants if p["color"] != piece["color"]]
    # Regla especial de salida: si hay contrario, sale y devuelve uno a casa.
    if enemies:
        captured = enemies[-1]
        captured["state"]="home";captured["pos"]=-1;captured["finish_pos"]=-1

    piece["state"]="track";piece["pos"]=0;piece["finish_pos"]=-1
    return {
        "piece_id":piece["id"],"color":piece["color"],"amount":0,
        "from":{"state":"home","pos":-1,"finish_pos":-1},
        "path":[{"state":"track","pos":0,"global":gp}],
        "captured":captured["id"] if captured else None,
        "goal":False,
        "exit":True
    }

def _required_color_count(room, player):
    # Mínimo obligatorio. Con 2 jugadores pueden elegir 1 o 2 colores.
    return 1

def _max_color_count(room, player):
    return 2 if len(room["players"]) == 2 else 1

def _used_colors(room, exclude_id=None):
    used=set()
    for p in room["players"]:
        if p["id"] != exclude_id:
            used.update(p.get("colors", []))
    return used

def _assign_cpu_colors(room):
    used=set()
    for pl in room["players"]:
        if not pl.get("bot"):
            used.update(pl.get("colors", []))
    remaining=[c for c in COLORS if c not in used]
    for pl in room["players"]:
        if pl.get("bot") and not pl.get("colors"):
            if remaining:
                pl["colors"]=[remaining.pop(0)]

def _colors_valid(room):
    used=[]
    for pl in room["players"]:
        n=len(pl.get("colors", []))
        if n < 1 or n > _max_color_count(room,pl):
            return False
        used.extend(pl["colors"])
    return len(used)==len(set(used)) and set(used).issubset(set(COLORS))

def _active_colors(room):
    return [c for pl in room["players"] for c in pl.get("colors",[])]

def _build_color_turn_order(room):
    # El turno real es por COLOR, no por jugador. Si Juan tiene rojo y azul,
    # primero juega rojo y cuando vuelva su siguiente turno será azul.
    colors=_active_colors(room)
    random.shuffle(colors)
    return colors

def _turn_color(room):
    order=room.get("color_turn_order",[])
    if not order:return None
    return order[room.get("color_turn_index",0)%len(order)]

def _owner_of_color(room,color):
    return next((pl for pl in room["players"] if color in pl.get("colors",[])),None)

def _colors_valid_legacy_unused(room):
    used=[]
    for p in room["players"]:
        need=_required_color_count(room,p)
        if len(p.get("colors", [])) != need:
            return False
        used.extend(p["colors"])
    return len(used)==len(set(used)) and set(used).issubset(set(COLORS))

def _next_player(room, extra_turn=False):
    room["rolled"]=False
    room["dice"]=None
    room["pending_dice"]=[]
    room["actions"]=[]
    room["bonus_queue"]=[]
    room["must_open_barrier"]=False
    room["last_moved_piece"]=None

    if not extra_turn and room.get("color_turn_order"):
        room["color_turn_index"]=(room.get("color_turn_index",0)+1)%len(room["color_turn_order"])
        nc=_turn_color(room)
        owner=_owner_of_color(room,nc)
        if owner:
            room["last_event"]=f"Turno de {owner['name']} · {COLOR_LABELS.get(nc,nc)}"
    elif extra_turn:
        tc=_turn_color(room)
        owner=_owner_of_color(room,tc)
        if owner:
            room["last_event"]=f"¡Dobles! Repite {owner['name']} · {COLOR_LABELS.get(tc,tc)}"

def _finish_turn_if_done(room):
    """
    Cierra exactamente UNA vez un turno que ya fue tirado y consumido.
    Un turno nuevo (rolled=False) jamás puede cerrarse desde aquí.
    """
    if room.get("status")!="playing" or not room.get("rolled"):
        return False

    pending=[d for d in room.get("pending_dice",[]) if not d.get("used")]
    if pending or room.get("bonus_queue") or room.get("actions"):
        return False

    extra=bool(room.get("extra_turn",False))
    _next_player(room,extra_turn=extra)
    return True

def _movement_actions(room, player):
    # Los bonus de 20/10 tienen prioridad sobre los dados restantes.
    if room.get("bonus_queue"):
        amount=room["bonus_queue"][0]
        actions=[]
        for c in [_turn_color(room)]:
            if not c: continue
            for p in room["colors"][c]["pieces"]:
                if p["state"] in ("track","finish"):
                    legal,_,_,_=_simulate_steps(room,p,amount)
                    if legal:
                        actions.append({
                            "id":f"bonus_{amount}_{p['id']}",
                            "kind":"bonus","piece_id":p["id"],"value":amount,
                            "consumes":[],"label":f"{COLOR_LABELS[c]} {p['n']} · contar {amount}"
                        })
        return actions

    remaining=[d for d in room.get("pending_dice",[]) if not d["used"]]
    if not remaining:
        return []

    homes=[p for p in _home_pieces(room,player) if _can_exit(room,p)]
    exit_actions=[]

    # Un 5 individual puede sacar una ficha.
    for d in remaining:
        if d["value"]==5 and homes:
            for p in homes:
                exit_actions.append({
                    "id":f"exit_{d['id']}_{p['id']}",
                    "kind":"exit","piece_id":p["id"],"value":5,
                    "consumes":[d["id"]],
                    "label":f"Sacar {COLOR_LABELS[p['color']]} {p['n']} con 5"
                })

    # Si ninguno de los dados es 5, pero la suma es 5, se consumen ambos.
    if len(remaining)>=2 and not any(d["value"]==5 for d in remaining):
        if remaining[0]["value"]+remaining[1]["value"]==5 and homes:
            for p in homes:
                exit_actions.append({
                    "id":f"exit_sum_{p['id']}",
                    "kind":"exit","piece_id":p["id"],"value":5,
                    "consumes":[remaining[0]["id"],remaining[1]["id"]],
                    "label":f"Sacar {COLOR_LABELS[p['color']]} {p['n']} sumando 5"
                })

    # Sacar ficha es obligatorio si existe la posibilidad.
    if exit_actions:
        return exit_actions

    actions=[]
    barrier_ids=_own_barrier_piece_ids(room,player) if room.get("must_open_barrier") else set()

    for d in remaining:
        for c in [_turn_color(room)]:
            if not c: continue
            for p in room["colors"][c]["pieces"]:
                if p["state"] in ("track","finish"):
                    if barrier_ids and p["id"] not in barrier_ids:
                        continue
                    legal,_,_,_=_simulate_steps(room,p,d["value"])
                    if legal:
                        actions.append({
                            "id":f"move_{d['id']}_{p['id']}",
                            "kind":"move","piece_id":p["id"],"value":d["value"],
                            "consumes":[d["id"]],
                            "label":f"{COLOR_LABELS[c]} {p['n']} · mover {d['value']}"
                        })
    return actions

def _refresh_actions(room):
    if room["status"]!="playing" or not room.get("color_turn_order"):
        room["actions"]=[]
        return

    player=_owner_of_color(room,_turn_color(room))
    if not player:
        room["actions"]=[]
        return

    # Bonus 20/10: si no existe movimiento legal, se descarta y continúa.
    while room.get("bonus_queue"):
        room["actions"]=_movement_actions(room,player)
        if room["actions"]:
            return
        room["bonus_queue"].pop(0)

    room["actions"]=_movement_actions(room,player)

    # Si queda algún dado pero ya no existe ninguna jugada legal,
    # esos dados se pierden y el turno termina.
    if not room["actions"]:
        for d in room.get("pending_dice",[]):
            if not d.get("used"):
                d["used"]=True

    # En cuanto ya no quede nada por jugar, cambiar de turno AHORA.
    if not room["actions"] and not room.get("bonus_queue"):
        _finish_turn_if_done(room)

def _all_done(room,player):
    pcs=[]
    for c in player.get("colors",[]):
        pcs += room["colors"][c]["pieces"]
    return pcs and all(p["state"]=="done" for p in pcs)

def _choose_cpu_action(room,player):
    actions=room.get("actions",[])
    if not actions:return None

    ranked=[]
    for a in actions:
        p=_piece(room,a["piece_id"])
        score=0
        if a["kind"]=="exit":score+=500
        if a["kind"]=="bonus":score+=80
        if p and p["state"]=="finish":score+=400+p["finish_pos"]*10
        if p and p["state"]=="track":
            legal,path,final,capture=_simulate_steps(room,p,a["value"]) if a["kind"]!="exit" else (True,[],None,None)
            if capture:score+=1000
            if final and final["state"]=="done":score+=1200
            score+=p["pos"]
        ranked.append((score,random.random(),a))
    ranked.sort(reverse=True,key=lambda x:(x[0],x[1]))
    return ranked[0][2]

def create_room(user):
    code=uuid4().hex[:6].upper()
    return code,{
        "code":code,"game":"parchis_deluxe","game_name":"Parchís Deluxe",
        "host_id":user["id"],"host_name":user["username"],"status":"waiting",
        "players":[{
            "id":user["id"],"name":user["username"],"bot":False,"fake_user":False,
            "stars":int(user["stars"] or 0),"colors":[],"score":0,"doubles_streak":0
        }],
        "colors":{c:_new_color(c) for c in COLORS},
        "turn_order":[],"turn_index":0,
        "color_turn_order":[],"color_turn_index":0,
        "dice":None,"pending_dice":[],"rolled":False,"actions":[],
        "bonus_queue":[],"extra_turn":False,"must_open_barrier":False,
        "last_moved_piece":None,"winner":None,"last_event":"","cpu_task_running":False
    }

def register_parchis(app,socketio,active_rooms,current_user,find_player,friends_of,connected_users,result_callback=None):
    from flask_socketio import emit,join_room

    def lobby_emit(room):
        socketio.emit("parchis_lobby_state",_public(room),to=f"game_{room['code']}")

    def emit_state(room):
        socketio.emit("parchis_state",_public(room),to=f"game_{room['code']}")

    def schedule_cpu(code):
        room=active_rooms.get(code)
        if not room or room.get("status")!="playing" or not room.get("color_turn_order"):
            return
        pl=_owner_of_color(room,_turn_color(room))
        if not pl or not pl.get("bot"):
            return
        # IMPORTANT: solo puede existir UN trabajador CPU por sala.
        # Antes se lanzaban varios desde process_action + cpu_play y la CPU
        # podía encadenar tiradas saltándose aparentemente al humano.
        if room.get("cpu_task_running"):
            return
        room["cpu_task_running"]=True
        socketio.start_background_task(cpu_play,code)

    def finish_if_winner(room,player):
        if _all_done(room,player):
            room["status"]="finished"
            room["winner"]=player["id"]
            player["score"]+=1000
            if result_callback:
                result_callback(room,player["id"],"parchis_deluxe")
            ranking=sorted(
                [{"name":p["name"],"score":p["score"],"bot":p.get("bot",False)} for p in room["players"]],
                key=lambda x:x["score"],reverse=True
            )
            socketio.emit("parchis_game_over",{"winner":player["name"],"players":ranking},to=f"game_{room['code']}")
            return True
        return False

    def process_action(room,player,action):
        piece=_piece(room,action["piece_id"])
        if not piece:return False

        if action["kind"]=="exit":
            movement=_exit_piece(room,piece)
        else:
            movement=_apply_move(room,piece,action["value"])
        if not movement:return False

        # Consumir dados.
        for did in action.get("consumes",[]):
            for d in room.get("pending_dice",[]):
                if d["id"]==did:d["used"]=True

        if action["kind"]=="bonus" and room.get("bonus_queue"):
            room["bonus_queue"].pop(0)

        room["last_moved_piece"]=piece["id"]
        room["must_open_barrier"]=False

        # Captura => contar 20.
        if movement.get("captured"):
            room["bonus_queue"].append(20)
            player["score"]+=50
            room["last_event"]=f"{player['name']} come una ficha · ¡cuenta 20!"
        # Meta => contar 10.
        elif movement.get("goal"):
            room["bonus_queue"].append(10)
            player["score"]+=100
            room["last_event"]=f"{player['name']} mete una ficha · ¡cuenta 10!"
        elif movement.get("exit"):
            room["last_event"]=f"{player['name']} saca ficha de casa"
        else:
            room["last_event"]=f"{player['name']} mueve {COLOR_LABELS[piece['color']]} {piece['n']}"

        if finish_if_winner(room,player):
            # Aun así mandamos el movimiento para que la ficha termine su animación.
            socketio.emit("parchis_piece_move",{
                "movement":movement,
                "player_name":player["name"],
                "state":_public(room)
            },to=f"game_{room['code']}")
            return True

        # Recalcular dados restantes / acciones / siguiente turno ANTES
        # de mandar el estado al cliente. Así la animación nunca termina
        # restaurando un estado antiguo.
        _refresh_actions(room)
        final_state=_public(room)

        socketio.emit("parchis_piece_move",{
            "movement":movement,
            "player_name":player["name"],
            "state":final_state
        },to=f"game_{room['code']}")

        emit_state(room)

        if room["status"]=="playing":
            next_owner=_owner_of_color(room,_turn_color(room))
            if next_owner and next_owner.get("bot"):
                schedule_cpu(room["code"])
        return True

    def cpu_play(code):
        room=active_rooms.get(code)
        try:
            if not room or room.get("status")!="playing":
                return

            # Una tarea CPU solo trabaja mientras el COLOR ACTUAL pertenezca
            # a una CPU. En cuanto el turno pasa a un humano, termina.
            guard=0
            while True:
                room=active_rooms.get(code)
                if not room or room.get("status")!="playing":
                    return

                turn_color=_turn_color(room)
                player=_owner_of_color(room,turn_color)
                if not player or not player.get("bot"):
                    return

                guard+=1
                if guard>16:
                    return

                if not room.get("rolled"):
                    socketio.sleep(1.0)
                    # Revalidar después de la espera.
                    if _turn_color(room)!=turn_color:
                        continue
                    current=_owner_of_color(room,_turn_color(room))
                    if not current or current["id"]!=player["id"] or not current.get("bot"):
                        return
                    roll_for(room,player,code)
                    socketio.sleep(0.65)

                room=active_rooms.get(code)
                if not room or room.get("status")!="playing":
                    return

                # Si al tirar no había movimiento, _refresh_actions ya habrá
                # pasado al siguiente color. Repetimos el bucle para comprobar
                # quién es el nuevo dueño del turno.
                current_owner=_owner_of_color(room,_turn_color(room))
                if not current_owner or not current_owner.get("bot"):
                    return
                player=current_owner

                if not room.get("rolled"):
                    continue

                if not room.get("actions"):
                    _refresh_actions(room)
                    emit_state(room)
                    socketio.sleep(0.25)
                    continue

                action=_choose_cpu_action(room,player)
                if not action:
                    _refresh_actions(room)
                    emit_state(room)
                    socketio.sleep(0.25)
                    continue

                # Pausa antes de elegir/mover para que el jugador vea la tirada.
                socketio.sleep(0.9)
                process_action(room,player,action)

                # IMPORTANTE: no lanzar otra tarea aquí. Este mismo worker
                # continúa solo si el siguiente color sigue siendo de CPU.
                socketio.sleep(0.35)
        finally:
            room=active_rooms.get(code)
            if room:
                room["cpu_task_running"]=False
                # Si al terminar sigue tocando CPU (por ejemplo dobles),
                # relanzamos una única tarea controlada.
                pl=_owner_of_color(room,_turn_color(room)) if room.get("color_turn_order") else None
                if room.get("status")=="playing" and pl and pl.get("bot"):
                    schedule_cpu(code)

    def roll_for(room,player,code):
        d1=random.randint(1,6);d2=random.randint(1,6)
        doubles=d1==d2

        player["doubles_streak"]=player.get("doubles_streak",0)+1 if doubles else 0

        room["dice"]=[d1,d2]
        room["pending_dice"]=[
            {"id":"d1","value":d1,"used":False},
            {"id":"d2","value":d2,"used":False}
        ]
        room["rolled"]=True
        room["extra_turn"]=doubles
        room["bonus_queue"]=[]
        room["must_open_barrier"]=False
        room["last_event"]=f"{player['name']} saca {d1} y {d2}"

        # Tercer doble consecutivo: última ficha movida vuelve a casa,
        # salvo si ya está en pasillo/meta.
        if doubles and player["doubles_streak"]>=3:
            player["doubles_streak"]=0
            punished=None
            if room.get("last_moved_piece"):
                punished=_piece(room,room["last_moved_piece"])
            if punished and punished["state"]=="track":
                punished["state"]="home";punished["pos"]=-1;punished["finish_pos"]=-1
                room["last_event"]=f"¡Tercer doble! {COLOR_LABELS[punished['color']]} {punished['n']} vuelve a casa"
                socketio.emit("parchis_triple_double",{
                    "piece_id":punished["id"],"state":_public(room)
                },to=f"game_{code}")
            else:
                room["last_event"]="¡Tercer doble! Se pierde el turno"
            _next_player(room,extra_turn=False)
            emit_state(room);schedule_cpu(code)
            return

        # Con dobles y barrera propia, hay que abrir si existe movimiento legal.
        if doubles:
            barrier_ids=_own_barrier_piece_ids(room,player)
            if barrier_ids:
                possible=False
                for did,val in [("d1",d1),("d2",d2)]:
                    for pid in barrier_ids:
                        p=_piece(room,pid)
                        if p:
                            legal,_,_,_=_simulate_steps(room,p,val)
                            if legal:possible=True
                room["must_open_barrier"]=possible

        _refresh_actions(room)

        socketio.emit("parchis_roll_result",{
            "dice":[d1,d2],"double":doubles,"state":_public(room)
        },to=f"game_{code}")

        # Si la tirada no permitía ningún movimiento, _refresh_actions ya habrá
        # cambiado de color. Publicamos también el estado definitivo.
        emit_state(room)

        next_owner=_owner_of_color(room,_turn_color(room))
        if next_owner and next_owner.get("bot"):
            schedule_cpu(code)

    @app.route("/crear_sala/parchis",methods=["POST"])
    def parchis_crear_sala():
        user=current_user()
        if not user:return redirect(url_for("index"))
        code,room=create_room(user)
        active_rooms[code]=room
        return redirect(url_for("parchis_sala",codigo=code))

    @app.route("/parchis/sala/<codigo>")
    def parchis_sala(codigo):
        user=current_user()
        if not user:return redirect(url_for("index"))
        room=active_rooms.get(codigo.upper())
        if not room or room.get("game")!="parchis_deluxe":
            flash("Sala de Parchís no encontrada.","error")
            return redirect(url_for("juegos"))

        if not _player(room,user["id"]):
            if room["status"]!="waiting" or len(room["players"])>=4:
                flash("La sala está llena o ya ha comenzado.","error")
                return redirect(url_for("juegos"))
            room["players"].append({
                "id":user["id"],"name":user["username"],"bot":False,"fake_user":False,
                "stars":int(user["stars"] or 0),"colors":[],"score":0,"doubles_streak":0
            })
            # Cambia el nº de colores requerido: reset para evitar asignaciones inválidas.
            for p in room["players"]:p["colors"]=[]

        if room["status"]=="playing":
            return redirect(url_for("parchis_partida",codigo=codigo.upper()))

        return render_template("parchis_sala.html",user=user,sala=_public(room),
                               codigo=codigo.upper(),amigos=friends_of(user["id"]))

    @app.route("/estado_parchis/<codigo>")
    def parchis_estado(codigo):
        user=current_user()
        room=active_rooms.get(codigo.upper())
        if not user or not room or room.get("game")!="parchis_deluxe":
            return jsonify({"ok":False}),404
        if not _player(room,user["id"]):
            return jsonify({"ok":False}),403
        return jsonify({
            "ok":True,
            "status":room.get("status","waiting"),
            "code":room["code"],
            "game":"parchis_deluxe"
        })

    @app.route("/parchis/<codigo>")
    def parchis_partida(codigo):
        user=current_user()
        if not user:return redirect(url_for("index"))
        room=active_rooms.get(codigo.upper())
        if not room or room.get("game")!="parchis_deluxe" or not _player(room,user["id"]):
            return redirect(url_for("juegos"))
        return render_template("parchis_partida.html",user=user,sala=_public(room),codigo=codigo.upper())

    @socketio.on("parchis_join_lobby")
    def parchis_join_lobby(data):
        user=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not user or not room or not _player(room,user["id"]):return
        join_room(f"game_{code}")
        emit("parchis_lobby_state",_public(room),to=f"game_{code}")

    @socketio.on("parchis_choose_color")
    def parchis_choose_color(data):
        user=current_user();code=str(data.get("code","")).upper();color=str(data.get("color",""))
        room=active_rooms.get(code)
        if not user or not room or room["status"]!="waiting" or color not in COLORS:return
        player=_player(room,user["id"])
        if not player or player.get("bot"):return

        max_colors=_max_color_count(room,player)
        used=_used_colors(room,exclude_id=player["id"])

        if color in player["colors"]:
            player["colors"].remove(color)
        else:
            if color in used:
                emit("app_error",{"message":"Ese color ya lo ha elegido otro jugador."});return
            if len(player["colors"])>=max_colors:
                emit("app_error",{"message":f"Puedes elegir como máximo {max_colors} color{'es' if max_colors>1 else ''}."});return
            player["colors"].append(color)

        lobby_emit(room)

    @socketio.on("parchis_add_cpu")
    def parchis_add_cpu(data):
        user=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not user or not room or room["host_id"]!=user["id"] or room["status"]!="waiting":return
        if len(room["players"])>=4:
            emit("app_error",{"message":"Máximo 4 jugadores."});return
        n=sum(1 for p in room["players"] if p.get("bot"))+1
        room["players"].append({
            "id":f"pcpu_{uuid4().hex[:8]}","name":f"CPU Parchís {n}",
            "bot":True,"fake_user":False,"stars":0,"colors":[],"score":0,"doubles_streak":0
        })
        for p in room["players"]:p["colors"]=[]
        lobby_emit(room)

    @socketio.on("parchis_remove_cpu")
    def parchis_remove_cpu(data):
        user=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not user or not room or room["host_id"]!=user["id"] or room["status"]!="waiting":return
        bid=str(data.get("bot_id",""))
        room["players"]=[p for p in room["players"] if not(p["id"]==bid and p.get("bot"))]
        for p in room["players"]:p["colors"]=[]
        lobby_emit(room)

    @socketio.on("parchis_start")
    def parchis_start(data):
        user=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not user or not room or room["host_id"]!=user["id"] or room["status"]!="waiting":return
        if len(room["players"])<2 or len(room["players"])>4:
            emit("app_error",{"message":"Parchís necesita de 2 a 4 jugadores."});return

        _assign_cpu_colors(room)

        if not _colors_valid(room):
            emit("app_error",{"message":"Cada jugador debe elegir al menos un color. Con 2 jugadores podéis elegir 1 o 2 colores cada uno, sin repetir."});return

        room["status"]="playing"
        room["color_turn_order"]=_build_color_turn_order(room)
        room["color_turn_index"]=0
        room["turn_order"]=[p["id"] for p in room["players"]]
        room["turn_index"]=0
        room["last_event"]="¡Comienza la partida!"
        socketio.emit("parchis_started",{"code":code,"game":"parchis_deluxe"},room=f"game_{code}")

    @socketio.on("parchis_join")
    def parchis_join(data):
        user=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not user or not room or not _player(room,user["id"]):return
        join_room(f"game_{code}")
        emit("parchis_state",_public(room))
        schedule_cpu(code)

    @socketio.on("parchis_roll")
    def parchis_roll(data):
        user=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not user or not room or room["status"]!="playing" or not room.get("color_turn_order"):return
        owner=_owner_of_color(room,_turn_color(room))
        if not owner or owner["id"]!=user["id"] or room["rolled"]:return
        player=_player(room,user["id"])
        roll_for(room,player,code)

    @socketio.on("parchis_action")
    def parchis_action(data):
        user=current_user();code=str(data.get("code","")).upper();aid=str(data.get("action_id",""))
        room=active_rooms.get(code)
        if not user or not room or room["status"]!="playing" or not room.get("color_turn_order"):return
        owner=_owner_of_color(room,_turn_color(room))
        if not owner or owner["id"]!=user["id"]:return
        player=_player(room,user["id"])
        action=next((a for a in room.get("actions",[]) if a["id"]==aid),None)
        if not action:return
        process_action(room,player,action)
