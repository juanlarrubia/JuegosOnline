from JUEGOS.simple_multiplayer import register_simple_game
from flask_socketio import emit, join_room
import random


SLUG="poker_deluxe"
SUITS="♠♥♦♣";RANKS=list(range(2,15))
def deck(): return [(r,s) for s in SUITS for r in RANKS]
def score(hand):
    rs=sorted([r for r,s in hand],reverse=True); suits=[s for r,s in hand]
    from collections import Counter
    c=Counter(rs); groups=sorted(((n,r) for r,n in c.items()),reverse=True)
    flush=len(set(suits))==1; uniq=sorted(set(rs),reverse=True)
    if 14 in uniq:uniq.append(1)
    straight=next((uniq[i] for i in range(len(uniq)-4) if uniq[i]-uniq[i+4]==4),None)
    if flush and straight:return (8,straight)
    if groups[0][0]==4:return (7,groups[0][1],groups[1][1])
    triples=sorted([r for r,n in c.items() if n==3],reverse=True);pairs=sorted([r for r,n in c.items() if n==2],reverse=True)
    if triples and pairs:return (6,triples[0],pairs[0])
    if flush:return (5,*rs)
    if straight:return (4,straight)
    if triples:return (3,triples[0],*sorted([r for r in rs if r!=triples[0]],reverse=True))
    if len(pairs)>=2:return (2,*pairs[:2],max(r for r in rs if r not in pairs[:2]))
    if pairs:return (1,pairs[0],*sorted([r for r in rs if r!=pairs[0]],reverse=True))
    return (0,*rs)
def label(sc):return ["Carta alta","Pareja","Doble pareja","Trío","Escalera","Color","Full","Póker","Escalera de color"][sc[0]]
def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Póker Deluxe",4)
    def seat(r,uid):return next((i for i,p in enumerate(r["players"]) if str(p["id"])==str(uid)),None)
    def fresh(r):
        ser=r.setdefault("poker_series",{"configured":False,"target":1,"wins":[0]*len(r["players"]),"round":0,"champ":False});ser["round"]+=1
        d=deck();random.shuffle(d);hands=[[d.pop() for _ in range(5)] for p in r["players"]]
        r["poker"]={"hands":hands,"done":[False]*len(hands),"over":False,"winner":None,"seq":0,"event":None,"cpu_busy":False}
    def pub(r,v):
        g=r["poker"];ser=r["poker_series"]
        hands=[h if (i==v or g["over"]) else [None]*5 for i,h in enumerate(g["hands"])]
        return {"players":[{"id":p["id"],"name":p["name"],"bot":p.get("bot",False),"stars":p.get("stars",0)} for p in r["players"]],"host_id":r["host_id"],"configured":ser["configured"],"target":ser["target"],"wins":ser["wins"],"round":ser["round"],"champ":ser["champ"],"hands":hands,"done":g["done"],"over":g["over"],"winner":g["winner"],"seq":g["seq"],"event":g["event"],"labels":[label(score(h)) if (i==v or g["over"]) else "" for i,h in enumerate(g["hands"])]}
    def emit_all(r):
        for i,p in enumerate(r["players"]):
            if not p.get("bot"):socketio.emit("poker_state",pub(r,i),room=f"poker_{r['code']}_{p['id']}")
    def showdown(r):
        g=r["poker"];ser=r["poker_series"];vals=[score(h) for h in g["hands"]];w=max(range(len(vals)),key=lambda i:vals[i]);g["over"]=True;g["winner"]=w;ser["wins"][w]+=1;ser["champ"]=ser["wins"][w]>=ser["target"];g["seq"]+=1;g["event"]={"type":"showdown","seq":g["seq"]};emit_all(r)
        if not ser["champ"]:
            code=r["code"]
            def nxt():
                socketio.sleep(4);rr=active_rooms.get(code)
                if rr:fresh(rr);emit_all(rr);cpu(rr)
            socketio.start_background_task(nxt)
    def draw_cards(r,s,keep):
        g=r["poker"]
        if g["over"] or g["done"][s]:return
        d=deck();used={tuple(c) for h in g["hands"] for c in h};d=[c for c in d if c not in used];random.shuffle(d)
        g["hands"][s]=[c if i in keep else d.pop() for i,c in enumerate(g["hands"][s])];g["done"][s]=True;g["seq"]+=1;g["event"]={"type":"draw","seat":s,"seq":g["seq"]};emit_all(r)
        if all(g["done"]):showdown(r)
        else:cpu(r)
    def cpu(r):
        g=r.get("poker")
        if not g or g["over"] or g["cpu_busy"]:return
        pending=[i for i,p in enumerate(r["players"]) if p.get("bot") and not g["done"][i]]
        if not pending:return
        g["cpu_busy"]=True;code=r["code"];s=pending[0]
        def task():
            socketio.sleep(random.uniform(1.2,2));rr=active_rooms.get(code)
            if rr and not rr["poker"]["done"][s]:
                h=rr["poker"]["hands"][s];from collections import Counter;c=Counter(x[0] for x in h)
                keep={i for i,x in enumerate(h) if c[x[0]]>=2}
                if not keep:keep={max(range(5),key=lambda i:h[i][0])}
                draw_cards(rr,s,keep)
            rr=active_rooms.get(code)
            if rr and rr.get("poker"):rr["poker"]["cpu_busy"]=False;cpu(rr)
        socketio.start_background_task(task)
    @socketio.on("poker_join")
    def join(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or r.get("game")!=SLUG:return
        s=seat(r,u["id"]);join_room(f"poker_{r['code']}_{u['id']}")
        if "poker_series" not in r:r["poker_series"]={"configured":False,"target":1,"wins":[0]*len(r["players"]),"round":0,"champ":False}
        if "poker" not in r:fresh(r)
        emit("poker_state",pub(r,s));cpu(r)
    @socketio.on("poker_config")
    def config(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or str(r["host_id"])!=str(u["id"]):return
        t=max(1,min(9,int(data.get("target",1))));r["poker_series"]={"configured":True,"target":t,"wins":[0]*len(r["players"]),"round":0,"champ":False};fresh(r);emit_all(r);cpu(r)
    @socketio.on("poker_draw")
    def draw(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper());s=seat(r,u["id"]) if r else None
        if s is not None:draw_cards(r,s,{int(x) for x in data.get("keep",[]) if str(x).isdigit()})
