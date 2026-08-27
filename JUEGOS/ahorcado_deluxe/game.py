from JUEGOS.simple_multiplayer import register_simple_game
from flask_socketio import emit, join_room
import random
from uuid import uuid4


SLUG = "ahorcado_deluxe"
WORDS = [
'ELEFANTE',
'ORDENADOR',
'MARIPOSA',
'CHOCOLATE',
'AVENTURA',
'CASTILLO',
'GUITARRA',
'PLANETA',
'BIBLIOTECA',
'TORMENTA',
'DINOSAURIO',
'CARRETERA',
'FANTASMA',
'PIRAMIDE',
'TELEFONO',
'MONTAÑA',
'SEMAFORO',
'HELICOPTERO',
'CANGURO',
'LABERINTO',
'AGUA',
'AIRE',
'AMIGO',
'AMIGA',
'ANIMAL',
'ARANA',
'ARBOL',
'ARENA',
'ARMADURA',
'ARTISTA',
'AVESTRUZ',
'AVELLANA',
'AVELLANO',
'BACON',
'BAILARINA',
'BALCON',
'BARRERA',
'BASTON',
'BATERIA',
'BEISBOL',
'BIGOTE',
'BINGO',
'BLUSA',
'BOCADILLO',
'BOLSA',
'BORRADOR',
'BRASIL',
'BRONCE',
'BROCHA',
'BURBUJA',
'CABINA',
'CADENA',
'CACTUS',
'CAFETERA',
'CALABAZA',
'CALCETIN',
'CALLEJON',
'CAMELLO',
'CAMISA',
'CAMPANA',
'CAMPING',
'CANICA',
'CANTINA',
'CAPA',
'CAPITAN',
'CARAMELO',
'CASTANA',
'CEBRA',
'CEMENTO',
'CENTRO',
'CEPILLO',
'CEREBRO',
'CESTA',
'CHIMENEA',
'CHORIZO',
'CHUPETE',
'CIELO',
'CIGARRO',
'CINTA',
'CIRUELA',
'CLASE',
'COCODRILO',
'COLA',
'COMETA',
'CONEJO',
'CONFITE',
'CORAL',
'CORCHO',
'CORTADOR',
'CRAYON',
'CREMA',
'CRUZ',
'CUADRO',
'CUENTO',
'CUNA',
'CURA',
'DADO',
'DAGA',
'DAMA',
'DANZA',
'DEPORTE',
'DEDO',
'DELFIN',
'DENTADURA',
'DESIERTO',
'DIAMANTE',
'DIARIO',
'DICCIONARIO',
'DULCE',
'ECO',
'EDAD',
'EDREDON',
'EJERCITO',
'EMBUDO',
'ENCHUFE',
'ENTRADA',
'ENVASE',
'ESCALERA',
'ESCARABAJO',
'ESCRITOR',
'ESCRITORIO',
'ESPADA',
'ESPAGUETI',
'ESPEJO',
'ESTACION',
'ESTANQUE',
'ESTUCHE',
'EXAMEN',
'FAROL',
'FELICIDAD',
'FERIA',
'FERROCARRIL',
'FIEBRE',
'FIGURA',
'FLAUTA',
'FLOR',
'FONDO',
'FUENTE',
'GALLETA',
'GANSO',
'GARBANZO',
'GAVIOTA',
'GOMA',
'GORRA',
'GRILLO',
'GRUA',
'HADA',
'HAMBURGUESA',
'HAMSTER',
'HARINA',
'HERRADURA',
'HIELO',
'HORMIGA',
'HUERTO',
'IGUANA',
'INSECTO',
'ISLA',
'JABALI',
'JARDINERA',
'JARRON',
'JEFE',
'JINETE',
'JOYA',
'JUEVES',
'LADRILLO',
'LAGO',
'LANA',
'LAPTOP',
'LATA',
'LECHERO',
'LIMONERO',
'LINTERNAS',
'LINTERNA',
'LOBO',
'LOCOMOTORA',
'LUNA',
'MACETA',
'MAESTRO',
'MAGIA',
'MANGO',
'MANO',
'MANTEL',
'MAQUETA',
'MAQUINA',
'MAR',
'MARCO',
'MARTES',
'MEDICINA',
'MELON',
'MERMELADA',
'MESA',
'METRO',
'MONEDA',
'MONO',
'MONTANA',
'MOSQUITO',
'MOTORCICLETA',
'MUEBLE',
'MUNECA',
'NARANJO',
'NARIZ',
'NAVEGANTE',
'NEGOCIO',
'NIDO',
'NOCHE',
'NOMBRE',
'NOVIA',
'NOVIEMBRE',
'NUBE',
'NUEZ',
'OCEANO',
'OLIVA',
'OLIVO',
'OREJA',
'ORO',
'OTONO',
'PADRE',
'PAJARITO',
'PALA',
'PALOMA',
'PAN',
'PANTANO',
'PANTALON',
'PAPAYA',
'PATO',
'PECERA',
'PEINE',
'PELUCHE',
'PEPINO',
'PERA',
'PERSONA',
'PIANISTA',
'PIEDRA',
'PILAR',
'PINCEL',
'PINGUINO',
'PINTOR',
'PIPA',
'PISCINA',
'PLANTA',
'PLATILLO',
'PLUMA',
'POEMA',
'POMELO',
'PORTERO',
'PRADO',
'PREMIO',
'PRIMERO',
'PUERTO',
'QUESERA',
'QUESITO',
'RADIO',
'RANA',
'RAPIDO',
'RATON',
'REGLA',
'RELOJERO',
'RINOCERONTE',
'RIO',
'ROPA',
'RUEDA',
'SABOR',
'SAL',
'SALTAMONTES',
'SANDIA',
'SAPO',
'SARTEN',
'SECRETO',
'SEMILLA',
'SERPIENTE',
'SIERRA',
'SILBATO',
'SILLA',
'SIRENA',
'SOBRE',
'SOMBRERO',
'SONIDO',
'SOPA',
'TACO',
'TAMBOR',
'TAPIZ',
'TECHO',
'TERMOMETRO',
'TIENDA',
'TIGRE',
'TIJERA',
'TIMBRE',
'TORTA',
'TORTUGA',
'TRABAJO',
'TRAJE',
'TRANVIA',
'TRENZA',
'TRUENO',
'TUBO',
'TURISMO',
'UVA',
'VACA',
'VALLE',
'VASO',
'VELA',
'VECINO',
'VENTILADOR',
'VERDURA',
'VIAJE',
'VIDRIO',
'VIENTO',
'VIOLETA',
'VIRUS',
'VOLANTE',
'WAGON',
'XILOFONO',
'YEGUA',
'ZANAHORIA',
'ZORRA',
'ABUELO',
'ABUELA',
'ACTOR',
'ACTRIZ',
'ALCACHOFA',
'ALDEA',
'ALGODON',
'ALMACEN',
'AMBULANCIA',
'ANGEL',
'ANTIGUO',
'APIO',
'APLAUSO',
'ARCO',
'ARMARIO',
'ARROYO',
'ASIENTO',
'AVIONETA',
'AZOTEA',
'BAILAR',
'BARRIO',
'BASTIDOR',
'BIBLIA',
'BODEGA',
'BOMBERO',
'BOTON',
'BRAZO',
'BUFANDA',
'CABLE',
'CACHORRO',
'CALENDARIO',
'CANCION',
'CANTARO',
'CARBON',
'CARNAVAL',
'CARTON',
'CASA',
'CEBOLLA',
'CELULAR',
'CERRO',
'CERVEZA',
'CHISTE',
'CHUBASQUERO',
'CILINDRO',
'COLUMNA',
'CONCHA',
'CORREDOR',
'CRISTAL',
'CUCHARON',
'CUERNO',
'DIBUJANTE',
'DIBUJO',
'DOCTOR',
'DOMINGO',
'ESCULTURA',
'ESQUEMA',
'FABRICA',
'FAMILIA',
'FANTASIA',
'FARMACIA',
'FIESTA',
'FILTRO',
'FUEGO',
'GAFAS',
'GIMNASIO',
'GLACIAR',
'GLOBO',
'GOLFIN',
'GORILA',
'GRANIZO',
'GUITARRISTA',
'HABITANTE',
'HILO',
'HOGAR',
'HORMIGUERO',
'HOTEL',
'HUELLA',
'HUMO',
'IGLESIA',
'IMAGEN',
'IMPRESORA',
'INVIERNO',
'JUGADOR',
'LAGUNA',
'LANCHA',
'LECTURA',
'LIBRERIA',
'LIMONADA',
'LLAVE',
'LLUVIA',
'MAESTRA',
'MADERA',
'MANDARINA',
'MANZANA',
'MAPA',
'MARMOL',
'MEDALLON',
'MERCADO',
'MICROONDAS',
'MINUTO',
'MOCHILA',
'MONITOR',
'MUSEO',
'NARVAL',
'NIEBLA',
'NOTICIA',
'NOVELA',
'OBJETO',
'OFICINA',
'PALACIO',
'PARED',
'PASILLO',
'PASTEL',
'PELICULA',
'PESCADO',
'PESCADOR',
'PIZARRA',
'PLATANO',
'POLLO',
'PRINCIPE',
'PRINCESA',
'PUZZLE',
'RELOJ',
'RINCON',
'SABADO',
'SALSA',
'SALTAR',
'SANDALIA',
'SEMANA',
'SOMBRA',
'TARTA',
'TEATRO',
'TELESCOPIO',
'TORNILLO',
'TRAPO',
'TROMPETA',
'UNIVERSIDAD',
'VACUNA',
'VENTANA',
'VERANO',
'VESTIDO',
'VETERINARIO',
'VIDEO',
'VIOLIN',
'ZAPATILLA',
'ZAPATERO'
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
        players = r.get("players", [])[:2]
        n = len(players)
        if n < 2:
            return

        ser = r.setdefault("hang_series", {
            "configured": False,
            "target": 1,
            "wins": [0, 0],
            "round": 0,
            "champ": False,
            "starter": None,
        })
        old = list(ser.get("wins", []))
        ser["wins"] = (old + [0, 0])[:2]
        ser["round"] = int(ser.get("round", 0)) + 1

        # Elegir aleatoriamente quién empieza ESTA ronda.
        # Antes starter quedaba en None y por eso ambos clientes
        # mostraban "Espera al rival..." indefinidamente.
        ser["starter"] = random.randint(0, 1)

        word = random.choice(WORDS)
        r["hang"] = {
            "word": word,
            "used": [],
            # Errores independientes: cada muñeco representa a su jugador.
            "errors": [0, 0],
            "max_errors": 7,
            "turn": int(ser.get("starter", random.randint(0, 1))),
            "over": False,
            "winner": None,
            "seq": 0,
            "event": None,
            "cpu_busy": False,
        }

    def pub(r):
        ser = r.setdefault("hang_series", {
            "configured": False,
            "target": 1,
            "wins": [0, 0],
            "round": 0,
            "champ": False,
            "starter": None,
        })
        g = r.get("hang") or {
            "word": "",
            "used": [],
            "errors": [0, 0],
            "max_errors": 7,
            "turn": None,
            "over": False,
            "winner": None,
            "seq": 0,
            "event": None,
        }
        players = r.get("players", [])[:2]

        masked = " ".join(c if c in g["used"] else "_" for c in g["word"])

        return {
            "players": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "bot": p.get("bot", False),
                    "stars": p.get("stars", 0),
                }
                for p in players
            ],
            "host_id": r["host_id"],
            "configured": bool(ser.get("configured")),
            "target": int(ser.get("target", 1)),
            "wins": list(ser.get("wins", [0, 0]))[:2],
            "round": int(ser.get("round", 0)),
            "champ": bool(ser.get("champ")),
            "masked": masked,
            "used": list(g["used"]),
            "errors": list(g["errors"]),
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
        g["seq"] += 1

        if winner is not None:
            ser["wins"][winner] += 1
            ser["champ"] = ser["wins"][winner] >= ser["target"]
            g["event"] = {
                "type": "word_win",
                "winner": winner,
                "seq": g["seq"],
            }
        else:
            # La palabra se agota para el jugador que estaba jugando.
            g["event"] = {
                "type": "word_lose",
                "winner": None,
                "seq": g["seq"],
            }

        emit_all(r)

        if not ser["champ"]:
            code = r["code"]

            def nxt():
                socketio.sleep(3.2)
                rr = active_rooms.get(code)
                if not rr or rr.get("game") != SLUG:
                    return
                if len(rr.get("players", [])) < 2:
                    return
                fresh(rr)
                emit_all(rr)
                cpu(rr)

            socketio.start_background_task(nxt)

    def act(r, s, letter):
        g = r["hang"]
        players = r.get("players", [])[:2]
        if len(players) < 2:
            return

        if (
            g["over"]
            or s != g["turn"]
            or letter in g["used"]
            or len(letter) != 1
            or letter not in "ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
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
            g["errors"][s] += 1

        # Palabra completa = victoria de quien la completa.
        if all(c in g["used"] for c in g["word"]):
            finish(r, s)
            return

        # Cada jugador tiene su propio ahorcado.
        # Si agota sus 7 errores, gana el rival.
        if g["errors"][s] >= g["max_errors"]:
            finish(r, 1 - s)
            return

        # Acierto: conserva el turno. Fallo: pasa al rival.
        g["turn"] = s if hit else 1 - s
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
            r["hang_series"] = {
                "configured": False,
                "target": 1,
                "wins": [0, 0],
                "round": 0,
                "champ": False,
                "starter": None,
            }

        # No creamos la ronda hasta que el anfitrión elija la serie.
        # Así el invitado solo espera y nunca se bloquea en una ronda
        # parcialmente inicializada.
        if r["hang_series"].get("configured") and "hang" not in r:
            fresh(r)

        emit("hang_state", pub(r))
        cpu(r)

    @socketio.on("hang_config")
    def config(data):
        u = current_user()
        r = active_rooms.get(str(data.get("code", "")).upper())

        if not u or not r or r.get("game") != SLUG:
            return

        # Solo el anfitrión puede elegir la serie.
        if str(r["host_id"]) != str(u["id"]):
            return

        players = r.get("players", [])[:2]

        # Ahorcado siempre necesita exactamente dos participantes.
        # En modo CPU normalmente ya existe el bot desde create_mode_room.
        # Si por una sala antigua no estuviera, añadimos una CPU automáticamente.
        if len(players) < 2:
            players.append({
                "id": "cpu_" + uuid4().hex[:8],
                "name": "CPU Nova",
                "bot": True,
                "fake_user": False,
                "stars": 0,
                "score": 0,
                "streak": 0,
            })
            r["players"] = players

        try:
            t = int(data.get("target", 1))
        except (TypeError, ValueError):
            t = 1
        t = max(1, min(9, t))

        r["players"] = players
        r["hang_series"] = {
            "configured": True,
            "target": t,
            "wins": [0, 0],
            "round": 0,
            "champ": False,
            "starter": None
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
