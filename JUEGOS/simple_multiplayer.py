from flask import render_template,redirect,url_for
from uuid import uuid4
def register_simple_game(app,socketio,active_rooms,current_user,friends_of,slug,title,max_players):
    from flask_socketio import emit,join_room
    ce="crear_"+slug; se="sala_"+slug; pe="partida_"+slug
    def create():
        u=current_user()
        if not u:return redirect(url_for("index"))
        code=uuid4().hex[:6].upper();active_rooms[code]={"code":code,"game":slug,"game_name":title,"host_id":u["id"],"host_name":u["username"],"status":"waiting","max_players":max_players,"players":[{"id":u["id"],"name":u["username"],"bot":False,"fake_user":False,"stars":int(u["stars"] or 0),"score":0}]}
        return redirect(url_for(se,codigo=code))
    def room(codigo):
        u=current_user();r=active_rooms.get(codigo.upper())
        if not u or not r or r.get("game")!=slug:return redirect(url_for("juegos"))
        if r.get("status")=="playing" and any(p["id"]==u["id"] for p in r["players"]):
            return redirect(url_for(pe,codigo=codigo.upper()))
        if not any(p["id"]==u["id"] for p in r["players"]):
            if r["status"]!="waiting" or len(r["players"])>=max_players:return redirect(url_for("juegos"))
            r["players"].append({"id":u["id"],"name":u["username"],"bot":False,"fake_user":False,"stars":int(u["stars"] or 0),"score":0})
        return render_template("simple_game_room.html",user=u,sala=r,codigo=codigo.upper(),amigos=friends_of(u["id"]))
    def play(codigo):
        u=current_user();r=active_rooms.get(codigo.upper())
        if not u or not r or r.get("game")!=slug:return redirect(url_for("juegos"))
        return render_template(slug+".html",user=u,sala=r,codigo=codigo.upper())
    app.add_url_rule("/crear_sala/"+slug,ce,create,methods=["POST"]);app.add_url_rule("/sala_"+slug+"/<codigo>",se,room);app.add_url_rule("/"+slug+"/<codigo>",pe,play)
    status_ep="estado_"+slug
    def room_status(codigo):
        from flask import jsonify
        u=current_user();r=active_rooms.get(codigo.upper())
        if not u or not r or r.get("game")!=slug:return jsonify({"ok":False}),404
        return jsonify({"ok":True,"status":r.get("status","waiting"),"game":slug,"code":r["code"]})
    app.add_url_rule("/estado_sala/"+slug+"/<codigo>",status_ep,room_status)
    @socketio.on(slug+"_join_lobby")
    def jl(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or r.get("game")!=slug:return
        join_room("game_"+r["code"]);emit(slug+"_lobby_state",r,to="game_"+r["code"])
    @socketio.on(slug+"_add_cpu")
    def add_cpu(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or r["host_id"]!=u["id"]:return
        if len(r["players"])>=max_players:
            emit("app_error",{"message":"Esta partida admite un máximo de 2 jugadores."})
            return
        n=1+sum(1 for p in r["players"] if p.get("bot"))
        r["players"].append({"id":"cpu_"+uuid4().hex[:8],"name":f"CPU {n}","bot":True,"fake_user":False,"stars":0,"score":0})
        emit(slug+"_lobby_state",r,to="game_"+r["code"])

    @socketio.on(slug+"_remove_cpu")
    def remove_cpu(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or r["host_id"]!=u["id"]:return
        for i in range(len(r["players"])-1,-1,-1):
            if r["players"][i].get("bot"):r["players"].pop(i);break
        emit(slug+"_lobby_state",r,to="game_"+r["code"])

    @socketio.on(slug+"_start")
    def st(data):
        u=current_user();r=active_rooms.get(str(data.get("code","")).upper())
        if not u or not r or r["host_id"]!=u["id"]:return
        if len(r.get("players",[]))<2:
            emit("app_error",{"message":"Necesitas al menos 2 jugadores. Añade una CPU o invita a alguien."})
            return
        r["status"]="playing"
        socketio.emit("simple_game_started",{"code":r["code"],"game":slug},room="game_"+r["code"])
