from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="conecta4_deluxe"

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Conecta 4",2)

    from flask_socketio import emit, join_room
    from flask import jsonify, request

    def public_state(r):
        c4=r.get("c4",{})
        return {
            "board":c4.get("board",[[0]*7 for _ in range(6)]),
            "turn":c4.get("turn",0),
            "target":c4.get("target",1),
            "wins":c4.get("wins",[0,0]),
            "round_over":c4.get("round_over",False),
            "champ_over":c4.get("champ_over",False),
            "winner":c4.get("winner",0),
            "last_move":c4.get("last_move"),
            "players":[{"id":p["id"],"name":p["name"],"bot":p.get("bot",False)} for p in r.get("players",[])],
            "configured":c4.get("configured",False),
            "round_no":c4.get("round_no",0),
            "starter":c4.get("starter",0),
            "starter_reason":c4.get("starter_reason","draw"),
        }

    def init_c4(r,target=1,keep_score=False):
        old=r.get("c4",{})
        wins=old.get("wins",[0,0]) if keep_score else [0,0]
        round_no=int(old.get("round_no",0))+1
        if keep_score and "starter" in old:
            starter=1-int(old.get("starter",0))
            starter_reason="alternate"
        else:
            starter=random.randint(0,1)
            starter_reason="draw"
        r["c4"]={
            "board":[[0]*7 for _ in range(6)],
            "turn":starter,
            "starter":starter,
            "starter_reason":starter_reason,
            "target":max(1,min(9,int(target))),
            "wins":wins,
            "round_over":False,
            "champ_over":False,
            "winner":0,
            "last_move":None,
            "configured":True,
            "round_no":round_no
        }

    def check_win(b,r,c,p):
        for dr,dc in ((1,0),(0,1),(1,1),(1,-1)):
            n=1
            for s in (-1,1):
                rr,cc=r+dr*s,c+dc*s
                while 0<=rr<6 and 0<=cc<7 and b[rr][cc]==p:
                    n+=1; rr+=dr*s; cc+=dc*s
            if n>=4:return True
        return False

    def cpu_col(c4):
        b=c4["board"]
        cols=[c for c in range(7) if b[0][c]==0]
        def row(c):
            for rr in range(5,-1,-1):
                if b[rr][c]==0:return rr
            return -1
        def win_col(p):
            for c in cols:
                rr=row(c)
                if rr<0:continue
                b[rr][c]=p
                w=check_win(b,rr,c,p)
                b[rr][c]=0
                if w:return c
            return None
        w=win_col(2)
        if w is not None:return w
        w=win_col(1)
        if w is not None:return w
        pref=[3,2,4,1,5,0,6]
        avail=[c for c in pref if c in cols]
        return random.choice(avail[:min(3,len(avail))]) if avail else None

    def do_move(r,player_index,col):
        c4=r["c4"]; b=c4["board"]
        if c4["round_over"] or c4["champ_over"] or c4["turn"]!=player_index:return False
        if not 0<=col<7 or b[0][col]!=0:return False
        rr=-1
        for x in range(5,-1,-1):
            if b[x][col]==0:rr=x;break
        if rr<0:return False
        piece=player_index+1
        b[rr][col]=piece
        c4["last_move"]={"r":rr,"c":col,"p":piece}
        if check_win(b,rr,col,piece):
            c4["round_over"]=True;c4["winner"]=piece
            c4["wins"][player_index]+=1
            if c4["wins"][player_index]>=c4["target"]:c4["champ_over"]=True
        elif all(b[0][c]!=0 for c in range(7)):
            c4["round_over"]=True;c4["winner"]=0
        else:
            c4["turn"]=1-player_index
        return True


    @app.get("/api/conecta4/<code>/state")
    def c4_http_state(code):
        u=current_user(); code=code.upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:
            return jsonify({"ok":False}),404
        if not any(str(p.get("id"))==str(u["id"]) for p in r.get("players",[])):
            return jsonify({"ok":False}),403
        if "c4" not in r:
            r["c4"]={"configured":False,"target":1,"wins":[0,0],
                     "board":[[0]*7 for _ in range(6)],"turn":0,
                     "round_over":False,"champ_over":False,"winner":0,"last_move":None}
        return jsonify({"ok":True,"state":public_state(r)})

    @app.post("/api/conecta4/<code>/configure")
    def c4_http_configure(code):
        u=current_user(); code=code.upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:
            return jsonify({"ok":False,"error":"sala"}),404
        host_id=r.get("host_id")
        first_id=r.get("players",[{}])[0].get("id") if r.get("players") else None
        if str(u["id"]) not in (str(host_id),str(first_id)):
            return jsonify({"ok":False,"error":"host"}),403
        data=request.get_json(silent=True) or {}
        try: target=max(1,min(9,int(data.get("target",1))))
        except: target=1
        init_c4(r,target,False)
        state=public_state(r)
        socketio.emit("c4_state",state,room="game_"+code)
        return jsonify({"ok":True,"state":state})

    @app.post("/api/conecta4/<code>/move")
    def c4_http_move(code):
        u=current_user(); code=code.upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "c4" not in r:
            return jsonify({"ok":False}),404
        idx=next((i for i,p in enumerate(r.get("players",[])) if str(p.get("id"))==str(u["id"])),None)
        if idx is None:return jsonify({"ok":False}),403
        data=request.get_json(silent=True) or {}
        try: col=int(data.get("col"))
        except: return jsonify({"ok":False}),400
        changed=do_move(r,idx,col)
        state=public_state(r)
        if changed:
            socketio.emit("c4_state",state,room="game_"+code)
        return jsonify({"ok":changed,"state":state})

    @app.post("/api/conecta4/<code>/next")
    def c4_http_next(code):
        u=current_user(); code=code.upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:return jsonify({"ok":False}),404
        host_id=r.get("host_id")
        first_id=r.get("players",[{}])[0].get("id") if r.get("players") else None
        if str(u["id"]) not in (str(host_id),str(first_id)):
            return jsonify({"ok":False}),403
        if r.get("c4",{}).get("champ_over"):
            target=r["c4"].get("target",1); init_c4(r,target,False)
        else:
            target=r.get("c4",{}).get("target",1); init_c4(r,target,True)
        state=public_state(r)
        socketio.emit("c4_state",state,room="game_"+code)
        return jsonify({"ok":True,"state":state})

    @socketio.on("c4_game_join")
    def c4_join(data):
        u=current_user(); code=str(data.get("code","")).upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:return
        if not any(p["id"]==u["id"] for p in r.get("players",[])):return
        join_room("game_"+code)
        if "c4" not in r:
            if r.get("tournament_id"):
                init_c4(r, r.get("tournament_target",1), False)
            else:
                r["c4"]={"configured":False,"target":1,"wins":[0,0],
                         "board":[[0]*7 for _ in range(6)],"turn":0,
                         "round_over":False,"champ_over":False,"winner":0,"last_move":None,"round_no":0}
        emit("c4_state",public_state(r))

    @socketio.on("c4_configure")
    def c4_configure(data):
        u=current_user(); code=str(data.get("code","")).upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:
            return {"ok":False,"error":"sala"}
        # El anfitrión es SIEMPRE el creador / primer jugador.
        host_id=r.get("host_id")
        first_id=r.get("players",[{}])[0].get("id") if r.get("players") else None
        if str(u["id"]) not in (str(host_id),str(first_id)):
            return {"ok":False,"error":"host"}
        try:
            target=max(1,min(9,int(data.get("target",1))))
        except:
            target=1
        init_c4(r,target,False)
        state=public_state(r)
        socketio.emit("c4_state",state,room="game_"+code)
        return {"ok":True,"target":target}

    @socketio.on("c4_move")
    def c4_move(data):
        u=current_user(); code=str(data.get("code","")).upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "c4" not in r:return
        idx=next((i for i,p in enumerate(r.get("players",[])) if p["id"]==u["id"]),None)
        if idx is None:return
        try:col=int(data.get("col"))
        except:return
        if do_move(r,idx,col):
            socketio.emit("c4_state",public_state(r),room="game_"+code)
            # CPU si ocupa el segundo puesto
            if not r["c4"]["round_over"] and len(r["players"])>1 and r["players"][1].get("bot") and r["c4"]["turn"]==1:
                socketio.sleep(.7)
                c=cpu_col(r["c4"])
                if c is not None:
                    do_move(r,1,c)
                    socketio.emit("c4_state",public_state(r),room="game_"+code)

    @socketio.on("c4_next_round")
    def c4_next(data):
        u=current_user(); code=str(data.get("code","")).upper(); r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or r.get("host_id")!=u["id"]:return
        if r.get("c4",{}).get("champ_over"):
            target=r["c4"].get("target",1)
            init_c4(r,target,False)
        else:
            target=r.get("c4",{}).get("target",1)
            init_c4(r,target,True)
        socketio.emit("c4_state",public_state(r),room="game_"+code)
