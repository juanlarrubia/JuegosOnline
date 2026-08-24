from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="barquitos_deluxe"
SHIP_LENGTHS={1:5,2:4,3:3,4:3,5:2}

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Batalla Naval",2)
    from flask_socketio import emit,join_room

    def seat_for(r,uid):
        for i,p in enumerate(r.get("players",[])):
            if str(p.get("id"))==str(uid): return i
        return None

    def ship_cells(board,ship_id):
        return [i for i,v in enumerate(board or []) if v==ship_id]

    def neighbors(i):
        rr=i//10;cc=i%10;out=[]
        for dr in (-1,0,1):
            for dc in (-1,0,1):
                if dr==0 and dc==0: continue
                r2=rr+dr;c2=cc+dc
                if 0<=r2<10 and 0<=c2<10: out.append(r2*10+c2)
        return out

    def halo(cells):
        own=set(cells);out=set()
        for i in cells:
            for n in neighbors(i):
                if n not in own: out.add(n)
        return list(out)

    def valid_fleet(board):
        if not isinstance(board,list) or len(board)!=100:return False
        try: b=[int(x) for x in board]
        except:return False
        if any(x not in (0,1,2,3,4,5) for x in b):return False
        for sid,L in SHIP_LENGTHS.items():
            cells=ship_cells(b,sid)
            if len(cells)!=L:return False
            rows=[i//10 for i in cells];cols=[i%10 for i in cells]
            if len(set(rows))==1:
                if max(cols)-min(cols)+1!=L:return False
            elif len(set(cols))==1:
                if max(rows)-min(rows)+1!=L:return False
            else:return False
        # no touching, even diagonally
        for sid in SHIP_LENGTHS:
            cells=set(ship_cells(b,sid))
            for i in cells:
                for n in neighbors(i):
                    if b[n] and n not in cells:return False
        return True

    def can_place(board,cells):
        if not cells or any(board[i] for i in cells):return False
        own=set(cells)
        for i in cells:
            for n in neighbors(i):
                if n not in own and board[n]:return False
        return True

    def make_cpu_fleet():
        board=[0]*100
        for sid,L in SHIP_LENGTHS.items():
            ok=False
            while not ok:
                horizontal=random.random()>.5
                r=random.randrange(10);c=random.randrange(10)
                cells=[]
                for k in range(L):
                    rr=r+(0 if horizontal else k)
                    cc=c+(k if horizontal else 0)
                    if rr>9 or cc>9:
                        cells=[];break
                    cells.append(rr*10+cc)
                if can_place(board,cells):
                    for i in cells:board[i]=sid
                    ok=True
        return board

    def init_series(r,target):
        r["bn_series"]={
            "configured":True,
            "target":max(1,min(9,int(target))),
            "wins":[0,0],
            "round_no":0,
            "champ_over":False
        }
        init_round(r,keep_score=True)

    def init_round(r,keep_score=True):
        series=r.setdefault("bn_series",{"configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False})
        series["round_no"]=int(series.get("round_no",0))+1
        series["champ_over"]=False
        r["bn"]={
            "boards":[None,None],
            "ready":[False,False],
            "shots":[[0]*100,[0]*100], # shots[attacker]
            "turn":0,
            "battle":False,
            "round_over":False,
            "winner":None,
            "last_event":None,
            "seq":0,
            "cpu_queue":[],
            "cpu_hits":{}
        }
        if len(r.get("players",[]))>1 and r["players"][1].get("bot"):
            r["bn"]["boards"][1]=make_cpu_fleet()
            r["bn"]["ready"][1]=True

    def is_sunk(board,shots,ship_id):
        cells=ship_cells(board,ship_id)
        return bool(cells) and all(shots[i]==2 for i in cells)

    def mark_halo(board,shots,ship_id):
        for i in halo(ship_cells(board,ship_id)):
            if shots[i]==0:shots[i]=3

    def public_state(r,viewer_idx):
        series=r.get("bn_series",{"configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False})
        g=r.get("bn")
        if not g:
            return {
                "configured":bool(series.get("configured",False)),
                "target":int(series.get("target",1)),
                "wins":list(series.get("wins",[0,0])),
                "round_no":int(series.get("round_no",0)),
                "champ_over":bool(series.get("champ_over",False)),
                "players":[{"id":p["id"],"name":p["name"],"bot":p.get("bot",False)} for p in r.get("players",[])],
                "host_id":r.get("host_id"),"viewer":viewer_idx,
                "ready":[False,False],"battle":False,"turn":0,"round_over":False,"winner":None
            }
        opp=1-viewer_idx
        own_board=g["boards"][viewer_idx] if g["boards"][viewer_idx] else [0]*100
        enemy_board=g["boards"][opp] if g["boards"][opp] else [0]*100
        own_received=g["shots"][opp]
        enemy_shots=g["shots"][viewer_idx]
        return {
            "configured":bool(series.get("configured",False)),
            "target":int(series.get("target",1)),
            "wins":list(series.get("wins",[0,0])),
            "round_no":int(series.get("round_no",0)),
            "champ_over":bool(series.get("champ_over",False)),
            "players":[{"id":p["id"],"name":p["name"],"bot":p.get("bot",False)} for p in r.get("players",[])],
            "host_id":r.get("host_id"),"viewer":viewer_idx,
            "ready":list(g["ready"]),
            "battle":g["battle"],"turn":g["turn"],
            "round_over":g["round_over"],"winner":g["winner"],
            "own_board":list(own_board),
            "own_received":list(own_received),
            "enemy_shots":list(enemy_shots),
            "own_sunk":[sid for sid in SHIP_LENGTHS if g["boards"][viewer_idx] and is_sunk(own_board,own_received,sid)],
            "enemy_sunk":[sid for sid in SHIP_LENGTHS if g["boards"][opp] and is_sunk(enemy_board,enemy_shots,sid)],
            "last_event":g.get("last_event"),
            "seq":g.get("seq",0)
        }

    def emit_all(r):
        code=r["code"]
        for idx,p in enumerate(r.get("players",[])):
            if p.get("bot"):continue
            # room per user so private board is never leaked
            socketio.emit("bn_state",public_state(r,idx),room=f"bn_{code}_{p['id']}")

    def cpu_push(g,items):
        for i in items:
            if 0<=i<100 and g["shots"][1][i]==0 and i not in g["cpu_queue"]:
                g["cpu_queue"].append(i)

    def ortho(i):
        r=i//10;c=i%10;out=[]
        if r>0:out.append(i-10)
        if r<9:out.append(i+10)
        if c>0:out.append(i-1)
        if c<9:out.append(i+1)
        return out

    def cpu_remember(g,i,ship_id):
        hits=g["cpu_hits"].setdefault(str(ship_id),[])
        if i not in hits:hits.append(i)
        if len(hits)==1:
            cpu_push(g,ortho(i));return
        rows=[x//10 for x in hits];cols=[x%10 for x in hits]
        if len(set(rows))==1:
            row=rows[0];mi=min(cols);ma=max(cols);cand=[]
            if mi>0:cand.append(row*10+mi-1)
            if ma<9:cand.append(row*10+ma+1)
            g["cpu_queue"]=cand+[x for x in g["cpu_queue"] if x not in cand and g["shots"][1][x]==0]
        elif len(set(cols))==1:
            col=cols[0];mi=min(rows);ma=max(rows);cand=[]
            if mi>0:cand.append((mi-1)*10+col)
            if ma<9:cand.append((ma+1)*10+col)
            g["cpu_queue"]=cand+[x for x in g["cpu_queue"] if x not in cand and g["shots"][1][x]==0]

    def cpu_choose(g):
        while g["cpu_queue"]:
            i=g["cpu_queue"].pop(0)
            if g["shots"][1][i]==0:return i
        free=[i for i,x in enumerate(g["shots"][1]) if x==0]
        return random.choice(free) if free else None

    def do_fire(r,attacker,i):
        g=r["bn"]
        if not g["battle"] or g["round_over"] or g["turn"]!=attacker:return False
        if not 0<=i<100 or g["shots"][attacker][i]!=0:return False
        defender=1-attacker
        board=g["boards"][defender]
        sid=board[i]
        g["shots"][attacker][i]=2 if sid else 1
        sunk=False
        if sid and is_sunk(board,g["shots"][attacker],sid):
            sunk=True
            mark_halo(board,g["shots"][attacker],sid)
        g["seq"]+=1
        g["last_event"]={"seq":g["seq"],"attacker":attacker,"cell":i,"hit":bool(sid),"ship_id":sid or 0,"sunk":sunk}
        if sid:
            if attacker==1:
                cpu_remember(g,i,sid)
                if sunk:
                    g["cpu_hits"].pop(str(sid),None)
                    g["cpu_queue"]=[x for x in g["cpu_queue"] if g["shots"][1][x]==0]
            if sum(1 for x in g["shots"][attacker] if x==2)>=17:
                g["round_over"]=True;g["battle"]=False;g["winner"]=attacker
                series=r["bn_series"];series["wins"][attacker]+=1
                series["champ_over"]=series["wins"][attacker]>=series["target"]
            else:
                g["turn"]=attacker # hit = repeat
        else:
            g["turn"]=defender
        return True

    def maybe_start_battle(r):
        g=r["bn"]
        if all(g["ready"]):
            g["battle"]=True;g["turn"]=0
            g["last_event"]={"seq":g["seq"],"type":"battle_start"}

    def schedule_next_round(r):
        if r.get("bn_next_scheduled"):return
        r["bn_next_scheduled"]=True
        code=r["code"]
        def task():
            socketio.sleep(4.2)
            rr=active_rooms.get(code)
            if not rr:return
            rr["bn_next_scheduled"]=False
            series=rr.get("bn_series",{})
            if not series.get("configured") or series.get("champ_over"):return
            init_round(rr,keep_score=True)
            emit_all(rr)
        socketio.start_background_task(task)

    def schedule_cpu(r):
        g=r.get("bn")
        if not g or not g["battle"] or g["round_over"] or g["turn"]!=1:return
        if len(r.get("players",[]))<2 or not r["players"][1].get("bot"):return
        if r.get("bn_cpu_busy"):return
        r["bn_cpu_busy"]=True;code=r["code"]
        def task():
            try:
                while True:
                    socketio.sleep(1.0)
                    rr=active_rooms.get(code)
                    if not rr or not rr.get("bn"):break
                    gg=rr["bn"]
                    if not gg["battle"] or gg["round_over"] or gg["turn"]!=1:break
                    i=cpu_choose(gg)
                    if i is None:break
                    if not do_fire(rr,1,i):break
                    emit_all(rr)
                    if gg["round_over"]:
                        schedule_next_round(rr)
                        break
                    if gg["turn"]!=1:break
            finally:
                rr=active_rooms.get(code)
                if rr:rr["bn_cpu_busy"]=False
        socketio.start_background_task(task)

    @socketio.on("bn_game_join")
    def join_game(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:return
        idx=seat_for(r,u["id"])
        if idx is None:return
        join_room(f"bn_{code}_{u['id']}")
        if "bn_series" not in r:
            r["bn_series"]={"configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False}
        emit("bn_state",public_state(r,idx))

    @socketio.on("bn_configure")
    def configure(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:return
        if str(r.get("host_id"))!=str(u["id"]):return
        try:target=max(1,min(9,int(data.get("target",1))))
        except:target=1
        init_series(r,target)
        emit_all(r)

    @socketio.on("bn_ready")
    def ready(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "bn" not in r:return
        idx=seat_for(r,u["id"])
        if idx is None:return
        board=data.get("board")
        if not valid_fleet(board):
            emit("bn_error",{"message":"La colocación de la flota no es válida."})
            return
        r["bn"]["boards"][idx]=[int(x) for x in board]
        r["bn"]["ready"][idx]=True
        maybe_start_battle(r)
        emit_all(r)
        schedule_cpu(r)

    @socketio.on("bn_fire")
    def fire(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG or "bn" not in r:return
        idx=seat_for(r,u["id"])
        if idx is None:return
        try:i=int(data.get("cell"))
        except:return
        if do_fire(r,idx,i):
            emit_all(r)
            if r["bn"]["round_over"]:
                schedule_next_round(r)
            else:
                schedule_cpu(r)

    @socketio.on("bn_new_championship")
    def new_championship(data):
        u=current_user();code=str(data.get("code","")).upper();r=active_rooms.get(code)
        if not u or not r or r.get("game")!=SLUG:return
        if str(r.get("host_id"))!=str(u["id"]):return
        r["bn_series"]={"configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False}
        r.pop("bn",None)
        emit_all(r)
