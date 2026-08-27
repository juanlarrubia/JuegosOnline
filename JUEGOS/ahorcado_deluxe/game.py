from JUEGOS.simple_multiplayer import register_simple_game
from flask_socketio import emit, join_room
import random


SLUG = "ahorcado_deluxe"
WORDS = [
    "ELEFANTE","ORDENADOR","MARIPOSA","CHOCOLATE","AVENTURA",
    "CASTILLO","GUITARRA","PLANETA","BIBLIOTECA","TORMENTA",
    "DINOSAURIO","CARRETERA","FANTASMA","PIRAMIDE","TELEFONO",
    "MONTAÑA","SEMÁFORO","HELICOPTERO","CANGURO","LABERINTO"
]


def register(app, socketio, active_rooms, current_user, friends_of):
    # Ahorcado solo admite 2 jugadores: anfitrión + rival/CPU.
    register_simple_game(
        app, socketio, active_rooms, current_user, friends_of,
        SLUG, "Ahorcado Deluxe", 2
    )

    def seat(r, uid):
        return next(
            (i for i, p in enumerate(r["players"])
             if str(p["id"]) == str(uid)),
            None
        )

    def fresh(r):
        players = r.get("players", [])
        n = len(players)
        if n < 1:
            return

        ser = r.setdefault(
            "hang_series",
            {
                "configured": False,
                "target": 1,
                "wins": [0] * n,
                "round": 0,
                "champ": False,
            }
        )

        # Mantener exactamente una puntuación por jugador.
        if len(ser["wins"]) != n:
            old = list(ser.get("wins", []))
            ser["wins"] = (old + [0] * n)[:n]

        ser["round"] += 1

        # Cada ronda utiliza una palabra aleatoria.
        word = random.choice(WORDS)

        r["hang"] = {
            "word": word,
            "used": [],
            "errors": 0,
            "max_errors": 7,
            "turn": (ser["round"] - 1) % n,
            "over": False,
            "winner": None,
            "seq": 0,
            "event": None,
            "cpu_busy": False,
        }

    def pub(r):
        g = r["hang"]
        ser = r["hang_series"]

        masked = " ".join(
            c if c in g["used"] else "_"
            for c in g["word"]
        )

        return {
            "players": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "bot": p.get("bot", False),
                    "stars": p.get("stars", 0),
                }
                for p in r["players"][:2]
            ],
            "host_id": r["host_id"],
            "configured": ser["configured"],
            "target": ser["target"],
            "wins": ser["wins"],
            "round": ser["round"],
            "champ": ser["champ"],
            "masked": masked,
            "used": g["used"],
            "errors": g["errors"],
            "max_errors": g["max_errors"],
            "turn": g["turn"],
            "over": g["over"],
            "winner": g["winner"],
            "seq": g["seq"],
            "event": g["event"],
            "word": g["word"] if g["over"] else "",
        }

    def emit_all(r):
        socketio.emit(
            "hang_state",
            pub(r),
            room="hang_" + r["code"]
        )

    def finish(r, winner):
        g = r["hang"]
        ser = r["hang_series"]

        if g["over"]:
            return

        g["over"] = True
        g["winner"] = winner

        if winner is not None:
            ser["wins"][winner] += 1
            ser["champ"] = ser["wins"][winner] >= ser["target"]

        emit_all(r)

        # Si aún no hay campeón, se prepara automáticamente otra palabra.
        # Así una palabra acertada NO termina el campeonato.
        if not ser["champ"]:
            code = r["code"]

            def nxt():
                socketio.sleep(3.5)
                rr = active_rooms.get(code)
                if not rr or rr.get("game") != SLUG:
                    return
                fresh(rr)
                emit_all(rr)
                cpu(rr)

            socketio.start_background_task(nxt)

    def act(r, s, letter):
        g = r["hang"]

        if (
            g["over"]
            or s != g["turn"]
            or letter in g["used"]
            or len(letter) != 1
        ):
            return

        g["used"].append(letter)
        g["seq"] += 1

        hit = letter in g["word"]
        g["event"] = {
            "type": "hit" if hit else "miss",
            "letter": letter,
            "seat": s,
            "seq": g["seq"],
        }

        if not hit:
            g["errors"] += 1

        if all(c in g["used"] for c in g["word"]):
            finish(r, s)
            return

        if g["errors"] >= g["max_errors"]:
            finish(r, None)
            return

        g["turn"] = (g["turn"] + 1) % len(r["players"])
        emit_all(r)
        cpu(r)

    def cpu(r):
        g = r.get("hang")

        if (
            not g
            or g["over"]
            or g["turn"] >= len(r["players"])
            or not r["players"][g["turn"]].get("bot")
            or g["cpu_busy"]
        ):
            return

        g["cpu_busy"] = True
        code = r["code"]

        def task():
            socketio.sleep(random.uniform(1.2, 2.3))

            rr = active_rooms.get(code)

            if (
                rr
                and rr.get("hang")
                and not rr["hang"]["over"]
            ):
                gg = rr["hang"]

                unused = [
                    c for c in "ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
                    if c not in gg["used"]
                ]

                likely = [
                    c for c in "EAOSRNIDLCTUMPBGVYQHFZJÑXKW"
                    if c in unused
                ]

                choice = (
                    random.choice(likely[:min(8, len(likely))])
                    if likely
                    else random.choice(unused)
                )

                act(rr, gg["turn"], choice)

            rr = active_rooms.get(code)

            if rr and rr.get("hang"):
                rr["hang"]["cpu_busy"] = False
                cpu(rr)

        socketio.start_background_task(task)

    @socketio.on("hang_join")
    def join(data):
        u = current_user()
        r = active_rooms.get(
            str(data.get("code", "")).upper()
        )

        if not u or not r or r.get("game") != SLUG:
            return

        join_room("hang_" + r["code"])

        if "hang_series" not in r:
            n = min(2, len(r.get("players", [])))
            r["hang_series"] = {
                "configured": False,
                "target": 1,
                "wins": [0] * n,
                "round": 0,
                "champ": False,
            }

        if "hang" not in r:
            fresh(r)

        emit("hang_state", pub(r))
        cpu(r)

    @socketio.on("hang_config")
    def config(data):
        u = current_user()
        r = active_rooms.get(
            str(data.get("code", "")).upper()
        )

        # Solo el anfitrión puede configurar la serie.
        if (
            not u
            or not r
            or str(r["host_id"]) != str(u["id"])
        ):
            return

        # Nunca permitimos más de dos jugadores.
        if len(r.get("players", [])) > 2:
            r["players"] = r["players"][:2]

        t = max(1, min(9, int(data.get("target", 1))))

        r["hang_series"] = {
            "configured": True,
            "target": t,
            "wins": [0] * len(r["players"]),
            "round": 0,
            "champ": False,
        }

        fresh(r)
        emit_all(r)
        cpu(r)

    @socketio.on("hang_letter")
    def letter(data):
        u = current_user()
        r = active_rooms.get(
            str(data.get("code", "")).upper()
        )

        if not u or not r:
            return

        s = seat(r, u["id"])

        if s is not None:
            act(
                r,
                s,
                str(data.get("letter", "")).upper()
            )
