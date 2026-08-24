from JUEGOS.simple_multiplayer import register_simple_game
import random

SLUG="damas_deluxe"

EMPTY=0
P0_MAN=1
P1_MAN=2
P0_KING=3
P1_KING=4

def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Damas Deluxe",2)
    from flask_socketio import emit,join_room

    def seat_for(room,uid):
        for i,p in enumerate(room.get("players",[])):
            if str(p.get("id"))==str(uid):
                return i
        return None

    def owner(piece):
        if piece in (P0_MAN,P0_KING): return 0
        if piece in (P1_MAN,P1_KING): return 1
        return None

    def is_king(piece):
        return piece in (P0_KING,P1_KING)

    def initial_board():
        b=[0]*64
        for r in range(3):
            for c in range(8):
                if (r+c)%2==1:
                    b[r*8+c]=P1_MAN
        for r in range(5,8):
            for c in range(8):
                if (r+c)%2==1:
                    b[r*8+c]=P0_MAN
        return b

    def diag_steps(idx):
        r,c=divmod(idx,8)
        out=[]
        for dr,dc in ((-1,-1),(-1,1),(1,-1),(1,1)):
            rr,cc=r+dr,c+dc
            if 0<=rr<8 and 0<=cc<8:
                out.append((rr*8+cc,dr,dc))
        return out

    def man_moves(board,idx,seat,captures_only=False):
        r,c=divmod(idx,8)
        out=[]
        # Ficha normal: movimiento hacia delante.
        if not captures_only:
            dr=-1 if seat==0 else 1
            for dc in (-1,1):
                rr,cc=r+dr,c+dc
                if 0<=rr<8 and 0<=cc<8 and board[rr*8+cc]==EMPTY:
                    out.append({"from":idx,"to":rr*8+cc,"capture":None})
        # Captura en las cuatro diagonales.
        for dr,dc in ((-1,-1),(-1,1),(1,-1),(1,1)):
            mr,mc=r+dr,c+dc
            lr,lc=r+2*dr,c+2*dc
            if 0<=lr<8 and 0<=lc<8 and 0<=mr<8 and 0<=mc<8:
                mid=mr*8+mc;land=lr*8+lc
                if board[land]==EMPTY and board[mid]!=EMPTY and owner(board[mid])==1-seat:
                    out.append({"from":idx,"to":land,"capture":mid})
        return out

    def king_moves(board,idx,seat,captures_only=False):
        r,c=divmod(idx,8)
        captures=[]
        quiet=[]
        for dr,dc in ((-1,-1),(-1,1),(1,-1),(1,1)):
            rr,cc=r+dr,c+dc
            seen_enemy=None
            while 0<=rr<8 and 0<=cc<8:
                j=rr*8+cc
                if board[j]==EMPTY:
                    if seen_enemy is None:
                        if not captures_only:
                            quiet.append({"from":idx,"to":j,"capture":None})
                    else:
                        captures.append({"from":idx,"to":j,"capture":seen_enemy})
                    rr+=dr;cc+=dc
                    continue
                if owner(board[j])==seat:
                    break
                # Rival.
                if seen_enemy is not None:
                    break
                seen_enemy=j
                rr+=dr;cc+=dc
        return captures if captures_only else quiet+captures

    def piece_moves(board,idx,captures_only=False):
        piece=board[idx]
        seat=owner(piece)
        if seat is None:
            return []
        return king_moves(board,idx,seat,captures_only) if is_king(piece) else man_moves(board,idx,seat,captures_only)

    def capture_sources(board,seat):
        return [i for i,p in enumerate(board) if owner(p)==seat and any(m["capture"] is not None for m in piece_moves(board,i,True))]

    def any_moves(board,seat):
        return any(piece_moves(board,i,False) for i,p in enumerate(board) if owner(p)==seat)

    def promote_if_needed(board,idx):
        p=board[idx];r=idx//8
        if p==P0_MAN and r==0:
            board[idx]=P0_KING
            return True
        if p==P1_MAN and r==7:
            board[idx]=P1_KING
            return True
        return False

    def new_match(room):
        series=room.setdefault("damas_series",{
            "configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False
        })
        series["round_no"]=int(series.get("round_no",0))+1
        # Alterna quién empieza cada partida del campeonato.
        starter=(series["round_no"]-1)%2
        room["damas"]={
            "board":initial_board(),
            "turn":starter,
            "forced_piece":None,
            "round_over":False,
            "winner":None,
            "seq":0,
            "last_event":None,
            "cpu_busy":False
        }

    def public(room):
        ser=room.get("damas_series",{"configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False})
        g=room.get("damas")
        return {
            "host_id":room.get("host_id"),
            "players":[{"id":p.get("id"),"name":p.get("name"),"bot":bool(p.get("bot"))} for p in room.get("players",[])],
            "configured":bool(ser.get("configured",False)),
            "target":int(ser.get("target",1)),
            "wins":list(ser.get("wins",[0,0])),
            "round_no":int(ser.get("round_no",0)),
            "champ_over":bool(ser.get("champ_over",False)),
            "board":list(g.get("board",[0]*64)) if g else [0]*64,
            "turn":int(g.get("turn",0)) if g else 0,
            "forced_piece":g.get("forced_piece") if g else None,
            "round_over":bool(g.get("round_over",False)) if g else False,
            "winner":g.get("winner") if g else None,
            "seq":int(g.get("seq",0)) if g else 0,
            "last_event":g.get("last_event") if g else None,
        }

    def emit_state(room):
        socketio.emit("damas_state",public(room),room="damas_"+room["code"])

    def finish_if_needed(room,last_mover):
        g=room["damas"]
        opponent=1-last_mover
        opp_pieces=sum(1 for p in g["board"] if owner(p)==opponent)
        if opp_pieces>0 and any_moves(g["board"],opponent):
            return False
        g["round_over"]=True
        g["winner"]=last_mover
        ser=room["damas_series"]
        ser["wins"][last_mover]+=1
        ser["champ_over"]=ser["wins"][last_mover]>=ser["target"]
        return True

    def legal_move(board,seat,src,dst,forced_piece=None):
        if not (0<=src<64 and 0<=dst<64):
            return None
        if owner(board[src])!=seat:
            return None
        if forced_piece is not None and src!=forced_piece:
            return None
        for m in piece_moves(board,src,False):
            if m["to"]==dst:
                return m
        return None

    def do_move(room,seat,src,dst):
        g=room["damas"]
        if g["round_over"] or g["turn"]!=seat:
            return False
        board=g["board"]
        move=legal_move(board,seat,src,dst,g.get("forced_piece"))
        if not move:
            return False

        before_capture_sources=capture_sources(board,seat)
        moving_piece=board[src]
        board[src]=EMPTY
        board[dst]=moving_piece

        captured=None
        if move["capture"] is not None:
            captured=move["capture"]
            board[captured]=EMPTY

        promoted=promote_if_needed(board,dst)
        blown=None

        if captured is not None:
            # Tras comer, si puede volver a comer, debe seguir con la misma ficha.
            more=[m for m in piece_moves(board,dst,True) if m["capture"] is not None]
            if more:
                g["forced_piece"]=dst
                g["turn"]=seat
            else:
                g["forced_piece"]=None
                g["turn"]=1-seat
        else:
            # Regla solicitada "si puede comer y no come, se sopla".
            if before_capture_sources:
                # Si la ficha movida era la que debía comer, se sopla en su nueva casilla.
                if src in before_capture_sources and owner(board[dst])==seat:
                    blown=dst
                else:
                    # Si movió otra ficha, se sopla la primera ficha que tenía captura.
                    candidate=before_capture_sources[0]
                    blown=candidate if owner(board[candidate])==seat else None
                if blown is not None:
                    board[blown]=EMPTY
            g["forced_piece"]=None
            g["turn"]=1-seat

        g["seq"]+=1
        g["last_event"]={
            "seq":g["seq"],"seat":seat,"from":src,"to":dst,
            "capture":captured,"promoted":promoted,"blown":blown,
            "continue":g["forced_piece"] is not None
        }

        finish_if_needed(room,seat)
        return True

    def all_moves(board,seat,forced_piece=None):
        out=[]
        indices=[forced_piece] if forced_piece is not None else [i for i,p in enumerate(board) if owner(p)==seat]
        for i in indices:
            if i is None: continue
            out.extend(piece_moves(board,i,False))
        return out

    def cpu_choose(room):
        g=room["damas"];board=g["board"];seat=1
        moves=all_moves(board,seat,g.get("forced_piece"))
        if not moves:return None

        captures=[m for m in moves if m["capture"] is not None]
        if captures:
            # Prioridad: capturar dama, promocionar o acercarse al centro.
            def score(m):
                s=random.random()
                if board[m["capture"]] in (P0_KING,P1_KING): s+=6
                rr=m["to"]//8
                if rr==7: s+=4
                s+=1.5-(abs((m["to"]%8)-3.5)+abs(rr-3.5))*0.08
                return s
            return max(captures,key=score)

        # CPU respeta normalmente la captura obligatoria; si no hay captura, movimiento razonable.
        def qscore(m):
            rr=m["to"]//8;cc=m["to"]%8
            s=random.random()*1.8
            if rr==7:s+=5
            s+=1.2-(abs(cc-3.5)+abs(rr-3.5))*0.07
            return s
        return max(moves,key=qscore)

    def schedule_cpu(room):
        if len(room.get("players",[]))<2 or not room["players"][1].get("bot"):
            return
        g=room.get("damas")
        if not g or g["round_over"] or g["turn"]!=1 or g.get("cpu_busy"):
            return
        g["cpu_busy"]=True
        code=room["code"]

        def task():
            try:
                socketio.sleep(1.15)
                r=active_rooms.get(code)
                if not r or r.get("game")!=SLUG:return
                gg=r.get("damas")
                if not gg or gg["round_over"] or gg["turn"]!=1:return
                m=cpu_choose(r)
                if not m:
                    gg["round_over"]=True;gg["winner"]=0
                    ser=r["damas_series"];ser["wins"][0]+=1;ser["champ_over"]=ser["wins"][0]>=ser["target"]
                    emit_state(r);schedule_next_round(r);return
                if do_move(r,1,m["from"],m["to"]):
                    emit_state(r)
                    if r["damas"]["round_over"]:
                        schedule_next_round(r)
            finally:
                rr=active_rooms.get(code)
                if rr and rr.get("damas"):
                    rr["damas"]["cpu_busy"]=False
                    if not rr["damas"]["round_over"] and rr["damas"]["turn"]==1:
                        schedule_cpu(rr)

        socketio.start_background_task(task)

    def schedule_next_round(room):
        if room.get("damas_next_busy") or room.get("damas_series",{}).get("champ_over"):
            return
        room["damas_next_busy"]=True
        code=room["code"]
        def task():
            socketio.sleep(4.0)
            r=active_rooms.get(code)
            if not r:return
            r["damas_next_busy"]=False
            if r.get("game")!=SLUG:return
            ser=r.get("damas_series",{})
            if not ser.get("configured") or ser.get("champ_over"):return
            new_match(r);emit_state(r);schedule_cpu(r)
        socketio.start_background_task(task)

    @socketio.on("damas_game_join")
    def game_join(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        if seat_for(room,u["id"]) is None:return
        join_room("damas_"+code)
        if "damas_series" not in room:
            room["damas_series"]={"configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False}
        if "damas" not in room:new_match(room)
        emit("damas_state",public(room))
        schedule_cpu(room)

    @socketio.on("damas_configure")
    def configure(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        if str(room.get("host_id"))!=str(u["id"]):return
        try:target=max(1,min(9,int(data.get("target",1))))
        except:target=1
        room["damas_series"]={"configured":True,"target":target,"wins":[0,0],"round_no":0,"champ_over":False}
        new_match(room);emit_state(room);schedule_cpu(room)

    @socketio.on("damas_move")
    def move(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        seat=seat_for(room,u["id"])
        if seat is None or room["players"][seat].get("bot"):return
        try:src=int(data.get("from"));dst=int(data.get("to"))
        except:return
        if do_move(room,seat,src,dst):
            emit_state(room)
            if room["damas"]["round_over"]:schedule_next_round(room)
            else:schedule_cpu(room)

    @socketio.on("damas_new_championship")
    def new_championship(data):
        u=current_user();code=str(data.get("code","")).upper();room=active_rooms.get(code)
        if not u or not room or room.get("game")!=SLUG:return
        if str(room.get("host_id"))!=str(u["id"]):return
        room["damas_series"]={"configured":False,"target":1,"wins":[0,0],"round_no":0,"champ_over":False}
        new_match(room);emit_state(room)
