from JUEGOS.simple_multiplayer import register_simple_game
from flask_socketio import emit, join_room
import random


SLUG="blackjack_deluxe";SUITS="♠♥♦♣";RANKS=["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
def deck():return [(r,s) for s in SUITS for r in RANKS]*4
def val(h):
    total=sum(11 if r=="A" else 10 if r in "JQK" else int(r) for r,s in h);aces=sum(r=="A" for r,s in h)
    while total>21 and aces:total-=10;aces-=1
    return total
def register(app,socketio,active_rooms,current_user,friends_of):
    register_simple_game(app,socketio,active_rooms,current_user,friends_of,SLUG,"Blackjack Deluxe",4)
    def seat(r,uid):return next((i for i,p in enumerate(r["players"]) if str(p["id"])==str(uid)),None)
    def fresh(r):
        ser=r.setdefault("bj_series",{"configured":False,"target":1,"wins":[0]*len(r["players"]),"round":0,"champ":False});ser["round"]+=1
        d=deck();random.shuffle(d);hands=[[d.pop(),d.pop()] for p in r["players"]];dealer=[d.pop(),d.pop()]
        r["bj"]={"deck":d,"hands":hands,"dealer":dealer,"done":[False]*len(hands),"turn":0,"over":False,"winners":[],"seq":0,"event":None,"cpu_busy":False}
    def pub(r,v):
        g=r["bj"];ser=r["bj_series"];dealer=g["dealer"] if g["over"] else [g["dealer"][0],None]
        return {"players":[{"id":p["id"],"name":p["name"],"bot":p.get("bot",False),"stars":p.get("stars",0)} for p in r["players"]],"host_id":r["host_id"],"configured":ser["configured"],"target":ser["target"],"wins":ser["wins"],"round":ser["round"],"champ":ser["champ"],"hands":g["hands"],"values":[val(h) for h in g["hands"]],"dealer":dealer,"dealer_value":val(g["dealer"]) if g["over"] else None,"done":g["done"],"turn":g["turn"],"over":g["over"],"winners":g["winners"],"seq":g["seq"],"event":g["event"]}
    def emit_all(r):socketio.emit("bj_state",pub(r,0),room="bj_"+r["code"])
    def finish(r):
        g=r["bj"];ser=r["bj_series"]
        while val(g["dealer"])<17:g["dealer"].append(g["deck"].pop())
        dv=val(g["dealer"]);w=[]
        for i,h in enumerate(g["hands"]):
            v=val(h)
            if v<=21 and (dv>21 or v>dv):w.append(i)
        g["over"]=True;g["winners"]=w
        for i in w:ser["wins"][i]+=1
        ser["champ"]=any(x>=ser["target"] for x in ser["wins"]);g["seq"]+=1;g["event"]={"type":"finish","seq":g["seq"]};emit_all(r)
        if not ser["champ"]:
            code=r["code"]
            def nxt():
                socketio.sleep(4);rr=active_rooms.get(code)
                if rr:fresh(rr);emit_all(rr);cpu(rr)
            socketio.start_background_task(nxt)
    def advance(r):
        g=r["bj"]
        while g["turn"]<len(r["players"]) and g["done"][g["turn"]]:g["turn"]+=1
        if g["turn"]>=len(r["players"]):finish(r)
        else:emit_all(r);cpu(r)
    def action(r,s,a):
        g=r["bj"]
        if g["over"] or s!=g["turn"] or g["done"][s]:return
        if a=="hit":
            g["hands"][s].append(g["deck"].pop());g["seq"]+=1;g["event"]={"type":"hit","seat":s,"seq":g["seq"]}
            if val(g["hands"][s])>=21:g["done"][s]=True;g["turn"]+=1;advance(r)
            else:emit_all(r)
        else:g["done"][s]=True;g["seq"]+=1;g["event"]={"type":"stand","seat":s,"seq":g["seq"]};g["turn"]+=1;advance(r)
    def cpu(r):
        g=r.get("bj")
        if not g or g["over"] or g["turn"]>=len(r["players"]) or not r["players"][g["turn"]].get("bot") or g["cpu_busy"]:return
        g["cpu_busy"]=True;code=r["code"]
        def task():
            socketio.sleep(random.uniform(1,1.8));rr=active_rooms.get(code)
            if rr and not rr["bj"]["over"]:
                s=rr["bj"]["turn"];action(rr,s,"hit" if val(rr["bj"]["hands"][s])<17 else "stand")
            rr=active_rooms.get(code)
            if rr and rr.get("bj"):rr["bj"]["cpu_busy"]=False;cpu(rr)
        socketio.start_background_task(task)
    @socketio.on("bj_join")
    def join(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or r.get("game")!=SLUG:return
        join_room("bj_"+r["code"])
        if "bj_series" not in r:r["bj_series"]={"configured":False,"target":1,"wins":[0]*len(r["players"]),"round":0,"champ":False}
        if "bj" not in r:fresh(r)
        emit("bj_state",pub(r,seat(r,u["id"])));cpu(r)
    @socketio.on("bj_config")
    def config(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or str(r["host_id"])!=str(u["id"]):return
        t=max(1,min(9,int(data.get("target",1))));r["bj_series"]={"configured":True,"target":t,"wins":[0]*len(r["players"]),"round":0,"champ":False};fresh(r);emit_all(r);cpu(r)
    @socketio.on("bj_action")
    def ac(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper());s=seat(r,u["id"]) if r else None
        if s is not None:action(r,s,data.get("action"))
