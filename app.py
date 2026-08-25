from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
# Firebase Admin se usa SOLO en el servidor.
# Lee la credencial desde GOOGLE_APPLICATION_CREDENTIALS y nunca desde el ZIP/APK.
try:
    import firebase_admin
    from firebase_admin import credentials as firebase_admin_credentials
    from firebase_admin import firestore as firebase_admin_firestore
    from firebase_admin import auth as firebase_admin_auth
except Exception:
    firebase_admin = None
    firebase_admin_credentials = None
    firebase_admin_firestore = None
    firebase_admin_auth = None
import sqlite3, random, time, json
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from uuid import uuid4
import os
import urllib.request, urllib.error
from datetime import datetime, timezone

from JUEGOS.parchis_deluxe.parchis import register_parchis, create_room as create_parchis_room
from JUEGOS.uno_deluxe.game import register as register_uno_deluxe
from JUEGOS.domino_deluxe.game import register as register_domino_deluxe
from JUEGOS.dobble_deluxe.game import register as register_dobble_deluxe
from JUEGOS.subastado_deluxe.game import register as register_subastado_deluxe
from JUEGOS.barquitos_deluxe.game import register as register_barquitos_deluxe
from JUEGOS.oca_deluxe.game import register as register_oca_deluxe
from JUEGOS.serpientes_deluxe.game import register as register_serpientes_deluxe
from JUEGOS.brisca_deluxe.game import register as register_brisca_deluxe
from JUEGOS.conecta4_deluxe.game import register as register_conecta4_deluxe
from JUEGOS.damas_deluxe.game import register as register_damas_deluxe
from JUEGOS.ahorcado_deluxe.game import register as register_ahorcado_deluxe
from JUEGOS.poker_deluxe.game import register as register_poker_deluxe
from JUEGOS.blackjack_deluxe.game import register as register_blackjack_deluxe
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "usuarios.db"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-cuando-publiquemos")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# Firebase (Authentication + Firestore)
# La API key web de Firebase es identificadora, no una contraseña.
# Puede sobreescribirse en Render con FIREBASE_API_KEY si alguna vez cambia.
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "AIzaSyBQCqvFJqFuuRlwiWSA_hUSUChuEMrpmEQ")
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "juegos-online-juan")

_firebase_admin_db = None

def get_firebase_admin_db():
    """Devuelve el cliente Firestore de servidor usando GOOGLE_APPLICATION_CREDENTIALS.

    Si la credencial no está configurada, la app sigue funcionando con su base local,
    pero no sincroniza estadísticas a Firestore.
    """
    global _firebase_admin_db
    if _firebase_admin_db is not None:
        return _firebase_admin_db
    if firebase_admin is None:
        return None
    try:
        if not firebase_admin._apps:
            cred = firebase_admin_credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        _firebase_admin_db = firebase_admin_firestore.client()
        return _firebase_admin_db
    except Exception as e:
        print(f"[Firebase Admin] No disponible: {e}")
        return None

def sync_game_stats_to_firestore(local_uid, game):
    """Sincroniza las estadísticas locales con Firestore desde el servidor.

    También recupera automáticamente el UID de Firebase por correo si se trata de
    una cuenta local antigua que todavía no tenía firebase_uid guardado.
    """
    if not isinstance(local_uid, int) or game not in GAME_META:
        return False

    db = get_firebase_admin_db()
    if db is None:
        print("[Firestore stats] Firebase Admin no disponible")
        return False

    conn = get_db()
    user = conn.execute(
        "SELECT id,email,firebase_uid FROM usuarios WHERE id=?", (local_uid,)
    ).fetchone()
    stats = conn.execute(
        "SELECT plays,wins,best_score FROM progreso_juegos WHERE user_id=? AND game=?",
        (local_uid, game)
    ).fetchone()

    if not user or not stats:
        conn.close()
        print(f"[Firestore stats] Sin usuario o estadísticas para {local_uid}/{game}")
        return False

    firebase_uid = (user["firebase_uid"] or "").strip()

    # Compatibilidad con cuentas antiguas: localizar la cuenta Firebase por email.
    if not firebase_uid and user["email"] and firebase_admin_auth is not None:
        try:
            fb_user = firebase_admin_auth.get_user_by_email(user["email"])
            firebase_uid = fb_user.uid
            conn.execute(
                "UPDATE usuarios SET firebase_uid=? WHERE id=?",
                (firebase_uid, local_uid)
            )
            conn.commit()
            print(f"[Firestore stats] UID Firebase recuperado para {user['email']}")
        except Exception as e:
            print(f"[Firestore stats] No se pudo localizar UID por email: {e}")

    conn.close()

    if not firebase_uid:
        print(f"[Firestore stats] Usuario local {local_uid} no tiene firebase_uid")
        return False

    played = int(stats["plays"] or 0)
    won = int(stats["wins"] or 0)
    lost = max(0, played - won)
    best_score = max(0, int(stats["best_score"] or 0))

    try:
        db.collection("users").document(firebase_uid).collection("stats").document(game).set({
            "played": played,
            "won": won,
            "lost": lost,
            "bestScore": best_score,
        }, merge=True)
        print(f"[Firestore stats] OK {firebase_uid}/{game}: {played}-{won}-{lost}")
        return True
    except Exception as e:
        print(f"[Firestore stats] Error sincronizando {local_uid}/{game}: {e}")
        return False

def _firebase_json(url, payload, method="POST", id_token=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read().decode("utf-8")
            return True, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            msg = body.get("error", {}).get("message", "ERROR_FIREBASE")
        except Exception:
            msg = "ERROR_FIREBASE"
        return False, msg
    except Exception:
        return False, "FIREBASE_NO_DISPONIBLE"

def firebase_sign_up(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    return _firebase_json(url, {"email": email, "password": password, "returnSecureToken": True})

def firebase_sign_in(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    return _firebase_json(url, {"email": email, "password": password, "returnSecureToken": True})

def firebase_delete_account(id_token):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:delete?key={FIREBASE_API_KEY}"
    return _firebase_json(url, {"idToken": id_token})

def firestore_create_profile(uid, id_token, email, username):
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/users?documentId={uid}"
    payload = {"fields": {
        "email": {"stringValue": email},
        "username": {"stringValue": username},
        "premium": {"booleanValue": False},
        "stars": {"integerValue": "0"},
        "createdAt": {"timestampValue": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
    }}
    return _firebase_json(url, payload, id_token=id_token)

def firestore_get_profile(uid, id_token):
    url = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}/databases/(default)/documents/users/{uid}"
    ok, data = _firebase_json(url, None, method="GET", id_token=id_token)
    if not ok:
        return False, data
    f = data.get("fields", {})
    def val(name, default=None):
        x=f.get(name,{})
        for k in ("stringValue","booleanValue","integerValue","timestampValue"):
            if k in x: return x[k]
        return default
    return True, {"email":val("email",""), "username":val("username",""),
                  "premium":bool(val("premium",False)), "stars":int(val("stars",0) or 0)}

def firebase_error_text(code):
    code = str(code).split(' : ')[0]
    return {
        "EMAIL_EXISTS":"Ese correo electrónico ya está registrado.",
        "INVALID_LOGIN_CREDENTIALS":"Correo/usuario o contraseña incorrectos.",
        "EMAIL_NOT_FOUND":"Correo/usuario o contraseña incorrectos.",
        "INVALID_PASSWORD":"Correo/usuario o contraseña incorrectos.",
        "WEAK_PASSWORD":"La contraseña debe tener al menos 6 caracteres.",
        "TOO_MANY_ATTEMPTS_TRY_LATER":"Demasiados intentos. Espera un poco y vuelve a intentarlo.",
        "FIREBASE_NO_DISPONIBLE":"No se ha podido conectar con Firebase. Inténtalo de nuevo.",
    }.get(code, "No se ha podido completar la operación con Firebase.")

connected_users = {}
active_rooms = {}
matchmaking_waiting = {}
matchmaking_matches = {}

GAME_META = {
    "bingo90":{"name":"Bingo 90 Deluxe","icon":"🎱"},
    "reto_relampago":{"name":"Reto Relámpago","icon":"⚡"},
    "parchis_deluxe":{"name":"Parchís Deluxe","icon":"🎲"},
    "uno_deluxe":{"name":"UNO Deluxe","icon":"🃏"},
    "domino_deluxe":{"name":"Dominó Deluxe","icon":"🁫"},
    "dobble_deluxe":{"name":"Dobble Arena","icon":"🔎"},
    "subastado_deluxe":{"name":"Tute Subastado","icon":"🪙"},
    "barquitos_deluxe":{"name":"Batalla Naval","icon":"🚢"},
    "oca_deluxe":{"name":"La Oca Deluxe","icon":"🪿"},
    "serpientes_deluxe":{"name":"Serpientes y Escaleras","icon":"🐍"},
    "brisca_deluxe":{"name":"La Brisca","icon":"🃏"},
    "conecta4_deluxe":{"name":"Conecta 4","icon":"🔴"},
    "damas_deluxe":{"name":"Damas Deluxe","icon":"♛"},
    "ahorcado_deluxe":{"name":"Ahorcado Deluxe","icon":"🪢"},
    "poker_deluxe":{"name":"Póker Deluxe","icon":"♠️"},
    "blackjack_deluxe":{"name":"Blackjack Deluxe","icon":"🂡"},
}

MEDAL_TEMPLATES = [
    ("play_1","Primera partida","Juega 1 partida","plays",1,1),
    ("play_3","Ya te gusta","Juega 3 partidas","plays",3,1),
    ("play_5","En marcha","Juega 5 partidas","plays",5,1),
    ("play_10","Habitual","Juega 10 partidas","plays",10,2),
    ("play_20","Veterano","Juega 20 partidas","plays",20,2),
    ("play_50","Incombustible","Juega 50 partidas","plays",50,4),
    ("win_1","Primera victoria","Gana 1 partida","wins",1,2),
    ("win_3","Triplete","Gana 3 partidas","wins",3,2),
    ("win_5","Cinco victorias","Gana 5 partidas","wins",5,2),
    ("win_10","Dominador","Gana 10 partidas","wins",10,3),
    ("win_25","Campeón","Gana 25 partidas","wins",25,4),
    ("cpu_1","Contra la máquina","Gana una partida a la CPU","cpu_wins",1,2),
    ("cpu_5","Domador de CPU","Gana 5 a la CPU","cpu_wins",5,3),
    ("online_1","Victoria online","Gana a otro jugador","online_wins",1,2),
    ("online_5","Rival temible","Gana 5 online","online_wins",5,3),
    ("streak_2","Doblete","Consigue 2 victorias seguidas","best_streak",2,2),
    ("streak_3","En racha","Consigue 3 victorias seguidas","best_streak",3,3),
    ("streak_5","Imparable","Consigue 5 victorias seguidas","best_streak",5,5),
    ("score_5000","Puntuación maestra","Alcanza 5.000 puntos","best_score",5000,4),
    ("master","Maestro del juego","Gana 50 partidas","wins",50,8),
]

def medal_definitions(game):
    return [
        {"key":k,"title":title,"description":desc,"metric":metric,
         "target":target,"stars":stars,"number":i+1}
        for i,(k,title,desc,metric,target,stars) in enumerate(MEDAL_TEMPLATES)
    ]

QUESTIONS = [
    {"q":"¿Qué planeta es conocido como el planeta rojo?","a":["Venus","Marte","Júpiter","Mercurio"],"ok":1,"emoji":"🪐"},
    {"q":"¿Cuántos lados tiene un hexágono?","a":["5","6","7","8"],"ok":1,"emoji":"🔷"},
    {"q":"¿Qué animal puede dormir de pie?","a":["Caballo","Delfín","Gato","Panda"],"ok":0,"emoji":"🐎"},
    {"q":"¿Cuál es el océano más grande?","a":["Atlántico","Índico","Pacífico","Ártico"],"ok":2,"emoji":"🌊"},
    {"q":"¿Qué número sigue? 2 · 4 · 8 · 16 · ?","a":["20","24","30","32"],"ok":3,"emoji":"⚡"},
    {"q":"¿Cuál de estos NO es un lenguaje de programación?","a":["Python","Java","HTML","C#"],"ok":2,"emoji":"💻"},
    {"q":"¿En qué continente está Japón?","a":["Europa","Asia","Oceanía","América"],"ok":1,"emoji":"🗾"},
    {"q":"¿Cuánto es 9 × 7?","a":["56","63","72","67"],"ok":1,"emoji":"🧠"},
    {"q":"¿Cuál es el mamífero más grande?","a":["Elefante","Ballena azul","Jirafa","Orca"],"ok":1,"emoji":"🐋"},
    {"q":"¿Qué color resulta de mezclar azul y amarillo?","a":["Naranja","Verde","Violeta","Rojo"],"ok":1,"emoji":"🎨"},
    {"q":"¿Cuál es el metal cuyo símbolo es Au?","a":["Plata","Cobre","Oro","Aluminio"],"ok":2,"emoji":"🏆"},
    {"q":"¿Qué país tiene forma de bota?","a":["Grecia","Italia","Portugal","Croacia"],"ok":1,"emoji":"👢"},
    {"q":'¿Cuál es la capital de Canadá?',"a":['Toronto', 'Ottawa', 'Vancouver', 'Montreal'],"ok":1,"emoji":'🇨🇦'},
    {"q":'¿Quién pintó La noche estrellada?',"a":['Picasso', 'Van Gogh', 'Monet', 'Dalí'],"ok":1,"emoji":'🎨'},
    {"q":'¿Cuántos lados tiene un dodecágono?',"a":['10', '12', '14', '16'],"ok":1,"emoji":'🔷'},
    {"q":'¿Cuál es el símbolo químico del oro?',"a":['Ag', 'Au', 'Fe', 'O'],"ok":1,"emoji":'🧪'},
    {"q":'¿En qué país está Petra?',"a":['Egipto', 'Jordania', 'Grecia', 'Turquía'],"ok":1,"emoji":'🏛️'},
    {"q":'¿Cuál es el animal más grande del planeta?',"a":['Elefante', 'Ballena azul', 'Tiburón blanco', 'Jirafa'],"ok":1,"emoji":'🐋'},
    {"q":'¿Cuánto es 12 × 8?',"a":['86', '96', '104', '88'],"ok":1,"emoji":'🧠'},
    {"q":'¿Qué instrumento mide la presión atmosférica?',"a":['Termómetro', 'Barómetro', 'Anemómetro', 'Higrómetro'],"ok":1,"emoji":'🌦️'},
    {"q":'¿Cuál es la capital de Australia?',"a":['Sídney', 'Melbourne', 'Canberra', 'Perth'],"ok":2,"emoji":'🇦🇺'},
    {"q":'¿Qué gas absorben principalmente las plantas?',"a":['Oxígeno', 'CO₂', 'Nitrógeno', 'Helio'],"ok":1,"emoji":'🌿'},
    {"q":'¿Cuántos jugadores tiene un equipo de fútbol en el campo?',"a":['9', '10', '11', '12'],"ok":2,"emoji":'⚽'},
    {"q":'¿Quién escribió Don Quijote?',"a":['Quevedo', 'Cervantes', 'Góngora', 'Lope de Vega'],"ok":1,"emoji":'📚'},
    {"q":'¿Cuál es el río más largo de la península ibérica?',"a":['Ebro', 'Tajo', 'Duero', 'Guadalquivir'],"ok":1,"emoji":'🏞️'},
    {"q":'¿Cuántos minutos tiene una hora y media?',"a":['80', '90', '100', '120'],"ok":1,"emoji":'⏱️'},
    {"q":'¿Cuál es el satélite natural de la Tierra?',"a":['Titán', 'La Luna', 'Fobos', 'Europa'],"ok":1,"emoji":'🌙'},
    {"q":'¿Qué metal es líquido a temperatura ambiente?',"a":['Hierro', 'Mercurio', 'Cobre', 'Aluminio'],"ok":1,"emoji":'🌡️'},
    {"q":'¿En qué deporte se usa un volante?',"a":['Tenis', 'Bádminton', 'Pádel', 'Squash'],"ok":1,"emoji":'🏸'},
    {"q":'¿Cuál es la capital de Portugal?',"a":['Oporto', 'Lisboa', 'Braga', 'Coímbra'],"ok":1,"emoji":'🇵🇹'},
    {"q":'¿Cuántos huesos tiene aproximadamente un adulto?',"a":['186', '206', '226', '246'],"ok":1,"emoji":'🦴'},
    {"q":'¿Cuál es la montaña más alta de España?',"a":['Mulhacén', 'Teide', 'Aneto', 'Veleta'],"ok":1,"emoji":'⛰️'},
    {"q":'¿Qué idioma se habla principalmente en Brasil?',"a":['Español', 'Portugués', 'Francés', 'Italiano'],"ok":1,"emoji":'🇧🇷'},
    {"q":'¿Qué número romano representa 50?',"a":['X', 'L', 'C', 'V'],"ok":1,"emoji":'🏛️'},
    {"q":'¿Cuál es el continente más grande?',"a":['África', 'Asia', 'Europa', 'Oceanía'],"ok":1,"emoji":'🌍'},
    {"q":'¿Qué órgano bombea la sangre?',"a":['Pulmón', 'Corazón', 'Hígado', 'Riñón'],"ok":1,"emoji":'❤️'},
    {"q":'¿Cuál es la raíz cuadrada de 144?',"a":['10', '12', '14', '16'],"ok":1,"emoji":'➗'},
    {"q":'¿Qué país ganó el Mundial de fútbol de 2010?',"a":['Alemania', 'España', 'Brasil', 'Países Bajos'],"ok":1,"emoji":'🏆'},
    {"q":'¿Quién formuló la teoría de la relatividad?',"a":['Newton', 'Einstein', 'Darwin', 'Tesla'],"ok":1,"emoji":'🔬'},
    {"q":'¿Cuál es la capital de Japón?',"a":['Kioto', 'Tokio', 'Osaka', 'Nagoya'],"ok":1,"emoji":'🗾'},
    {"q":'¿Qué mar separa Europa de África?',"a":['Báltico', 'Mediterráneo', 'Negro', 'Rojo'],"ok":1,"emoji":'🌊'},
    {"q":'¿Cuántos colores tiene tradicionalmente el arcoíris?',"a":['6', '7', '8', '9'],"ok":1,"emoji":'🌈'},
    {"q":'¿Cuál es el primer elemento de la tabla periódica?',"a":['Helio', 'Hidrógeno', 'Oxígeno', 'Carbono'],"ok":1,"emoji":'⚛️'},
    {"q":'¿En qué ciudad está la Alhambra?',"a":['Córdoba', 'Granada', 'Sevilla', 'Toledo'],"ok":1,"emoji":'🏰'},
    {"q":'¿Qué mamífero pone huevos?',"a":['Delfín', 'Ornitorrinco', 'Koala', 'Murciélago'],"ok":1,"emoji":'🥚'},
    {"q":'¿Qué moneda utiliza Japón?',"a":['Won', 'Yen', 'Yuan', 'Dólar'],"ok":1,"emoji":'💴'},
    {"q":'¿Cuántos segundos hay en 5 minutos?',"a":['250', '300', '350', '500'],"ok":1,"emoji":'⏲️'},
    {"q":'¿Quién pintó el Guernica?',"a":['Goya', 'Picasso', 'Velázquez', 'Sorolla'],"ok":1,"emoji":'🖼️'},
    {"q":'¿Qué vitamina produce la piel con ayuda del sol?',"a":['A', 'D', 'C', 'B12'],"ok":1,"emoji":'☀️'},
    {"q":'¿Cuál es la capital de Argentina?',"a":['Rosario', 'Buenos Aires', 'Córdoba', 'Mendoza'],"ok":1,"emoji":'🇦🇷'},
    {"q":'¿Qué planeta tiene los anillos más visibles?',"a":['Júpiter', 'Saturno', 'Urano', 'Neptuno'],"ok":1,"emoji":'🪐'},
    {"q":'¿Cuántas caras tiene un cubo?',"a":['4', '6', '8', '12'],"ok":1,"emoji":'🎲'},
    {"q":'¿Qué estrecho separa España de Marruecos?',"a":['Bering', 'Gibraltar', 'Bósforo', 'Magallanes'],"ok":1,"emoji":'🧭'},
    {"q":'¿Qué idioma tiene más hablantes nativos?',"a":['Inglés', 'Chino mandarín', 'Español', 'Hindi'],"ok":1,"emoji":'🗣️'},
    {"q":'¿Qué aparato registra los terremotos?',"a":['Barómetro', 'Sismógrafo', 'Altímetro', 'Telescopio'],"ok":1,"emoji":'🌋'},
    {"q":'¿Cuál de estos números es primo?',"a":['21', '29', '27', '33'],"ok":1,"emoji":'🔢'},
    {"q":'¿Cuál es la capital de Andalucía?',"a":['Córdoba', 'Sevilla', 'Málaga', 'Granada'],"ok":1,"emoji":'🇪🇸'},
    {"q":'¿Qué ave no puede volar y vive en la Antártida?',"a":['Flamenco', 'Pingüino', 'Águila', 'Pelícano'],"ok":1,"emoji":'🐧'},
    {"q":'¿Cuánto suman los ángulos de un triángulo?',"a":['90°', '180°', '270°', '360°'],"ok":1,"emoji":'📐'},
    {"q":'¿Qué planeta está más cerca del Sol?',"a":['Venus', 'Mercurio', 'Marte', 'Tierra'],"ok":1,"emoji":'☀️'},
    {"q":'¿Cuál es la capital de Grecia?',"a":['Atenas', 'Esparta', 'Patras', 'Salónica'],"ok":0,"emoji":'🇬🇷'},
    {"q":'¿Cuántos días tiene un año bisiesto?',"a":['365', '366', '364', '367'],"ok":1,"emoji":'📅'},
]


BINGO_PRIZES = [
    ("quick5", "5 números", 150, "⑤"),
    ("line", "Primera línea", 250, "━"),
    ("corners", "4 esquinas", 300, "⠉⠉"),
    ("vertical", "Primera vertical", 350, "┃"),
    ("double_line", "Doble línea", 500, "═"),
    ("border", "Borde exterior", 700, "▣"),
    ("bingo", "Bingo completo", 1200, "▦"),
]

def bingo_column_range(col):
    if col == 0:
        return list(range(1, 10))
    if col == 8:
        return list(range(80, 91))
    start = col * 10
    return list(range(start, start + 10))

def generate_spanish_ticket():
    """
    Cartón estilo bingo español: 3x9, 15 números, 5 por fila.
    Esta versión garantiza cuatro esquinas ocupadas para que el premio de
    esquinas y borde exterior sea visualmente inequívoco.
    """
    for _ in range(500):
        grid = [[None for _ in range(9)] for _ in range(3)]
        occupied = {(0,0),(0,8),(2,0),(2,8)}

        # Fill each row to 5 cells, while keeping between 1 and 3 cells per column.
        row_counts = [2,0,2]
        col_counts = [2,0,0,0,0,0,0,0,2]

        # Give middle row at least 3 cells first to avoid awkward layouts.
        available_mid = list(range(1,8))
        random.shuffle(available_mid)
        for c in available_mid[:3]:
            occupied.add((1,c)); row_counts[1]+=1; col_counts[c]+=1

        # Complete rows to 5.
        ok = True
        for r in range(3):
            tries = 0
            while row_counts[r] < 5 and tries < 100:
                tries += 1
                c = random.randrange(9)
                if (r,c) in occupied or col_counts[c] >= 3:
                    continue
                occupied.add((r,c)); row_counts[r]+=1; col_counts[c]+=1
            if row_counts[r] != 5:
                ok = False
                break
        if not ok or any(v == 0 for v in col_counts):
            continue

        # Assign ordered numbers within each column.
        valid = True
        for c in range(9):
            rows = sorted(r for r in range(3) if (r,c) in occupied)
            pool = bingo_column_range(c)
            if len(pool) < len(rows):
                valid = False; break
            nums = sorted(random.sample(pool, len(rows)))
            for r,n in zip(rows, nums):
                grid[r][c] = n
        if valid:
            return grid

    # Safe fallback (still 15 numbers, five per row)
    return [
        [3, None, 24, 34, None, 52, None, None, 84],
        [None, 12, None, 38, 45, None, 66, 73, None],
        [8, 18, None, None, 47, 58, None, 77, 90],
    ]

def ticket_numbers(grid):
    return [n for row in grid for n in row if n is not None]

def bingo_completed_features(grid, drawn):
    drawn = set(drawn)
    marked = {(r,c) for r,row in enumerate(grid) for c,n in enumerate(row) if n is not None and n in drawn}
    cells = {(r,c) for r,row in enumerate(grid) for c,n in enumerate(row) if n is not None}

    rows_complete = []
    for r in range(3):
        rc = {(r,c) for c in range(9) if grid[r][c] is not None}
        if rc and rc <= marked:
            rows_complete.append(r)

    cols_complete = []
    for c in range(9):
        cc = {(r,c) for r in range(3) if grid[r][c] is not None}
        # Require at least 2 numbers so a single-number column cannot win "vertical".
        if len(cc) >= 2 and cc <= marked:
            cols_complete.append(c)

    corners = {(0,0),(0,8),(2,0),(2,8)}
    border_cells = {(r,c) for (r,c) in cells if r in (0,2) or c in (0,8)}

    return {
        "marked_count": len(marked),
        "line": len(rows_complete) >= 1,
        "corners": corners <= marked,
        "vertical": len(cols_complete) >= 1,
        "double_line": len(rows_complete) >= 2,
        "border": bool(border_cells) and border_cells <= marked,
        "bingo": cells <= marked,
    }

def create_bingo_room(user):
    code = uuid4().hex[:6].upper()
    active_rooms[code] = {
        "code": code,
        "game": "bingo90",
        "game_name": "Bingo 90 Deluxe",
        "host_id": user["id"],
        "host_name": user["username"],
        "status": "waiting",
        "players": [{
            "id": user["id"],
            "name": user["username"],
            "bot": False,
            "fake_user": False,
            "stars": int(user["stars"] or 0),
            "score": 0,
            "streak": 0,
            "selected_tickets": 1,
            "tickets": [generate_spanish_ticket()],
            "marked": [],
            "last_bad_check": 0
        }],
        "drawn": [],
        "remaining": list(range(1, 91)),
        "speed": 8.0,
        "paused": False,
        "prizes": {},
        "bingo_loop_running": False,
    }
    return code

def normalize_bingo_player(p):
    """Migra en memoria jugadores de versiones antiguas al formato multi-cartón."""
    if "tickets" not in p:
        if p.get("ticket"):
            p["tickets"] = [p["ticket"]]
        else:
            p["tickets"] = [generate_spanish_ticket()]
    p["selected_tickets"] = max(1, min(4, int(p.get("selected_tickets", len(p["tickets"]) or 1))))
    while len(p["tickets"]) < p["selected_tickets"]:
        p["tickets"].append(generate_spanish_ticket())
    p["tickets"] = p["tickets"][:p["selected_tickets"]]
    # V15: cada cartón tiene sus propias marcas.
    # Migra el formato antiguo "marked" a todos los cartones solo una vez.
    if "marked_by_ticket" not in p:
        legacy = list(p.get("marked", []))
        p["marked_by_ticket"] = [list(legacy) for _ in range(p["selected_tickets"])]
    while len(p["marked_by_ticket"]) < p["selected_tickets"]:
        p["marked_by_ticket"].append([])
    p["marked_by_ticket"] = p["marked_by_ticket"][:p["selected_tickets"]]
    p["marked"] = []  # legado, ya no se usa para humanos
    p.setdefault("last_bad_check", 0)
    p.setdefault("score", 0)
    return p

def bingo_public(room, viewer_id=None):
    players = []
    for p in room["players"]:
        normalize_bingo_player(p)
        item = {
            "id": p["id"],
            "name": p["name"],
            "bot": p.get("bot", False),
            "fake_user": p.get("fake_user", False),
            "stars": p.get("stars", get_user_stars(p["id"]) if isinstance(p.get("id"),int) else 0),
            "score": p.get("score", 0),
            "selected_tickets": p.get("selected_tickets", 1)
        }
        # The owner receives their cards. Bots are visible only as score/name.
        if p["id"] == viewer_id:
            item["tickets"] = p.get("tickets", [])
            item["marked_by_ticket"] = p.get("marked_by_ticket", [])
        players.append(item)

    return {
        "code": room["code"],
        "game": room["game"],
        "game_name": room["game_name"],
        "host_id": room["host_id"],
        "host_name": room["host_name"],
        "status": room["status"],
        "players": players,
        "drawn": room.get("drawn", []),
        "remaining": len(room.get("remaining", [])),
        "speed": room.get("speed", 8.0),
        "paused": room.get("paused", False),
        "prizes": room.get("prizes", {}),
        "prize_defs": [
            {"key": k, "name": n, "points": pts, "icon": ic}
            for k, n, pts, ic in BINGO_PRIZES
        ],
    }

def bingo_check_player_objectives(room, player, include_bingo=True):
    normalize_bingo_player(player)
    newly = []
    drawn = set(room.get("drawn", []))

    for key, name, points, icon in BINGO_PRIZES:
        if key == "bingo" and not include_bingo:
            continue
        if key in room["prizes"]:
            continue

        achieved = False
        for idx, grid in enumerate(player.get("tickets", [])):
            # Solo son válidas para premios las marcas de bolas realmente salidas.
            raw_marks = set(
                player.get("marked_by_ticket", [])[idx]
                if idx < len(player.get("marked_by_ticket", []))
                else []
            )
            valid_marks = raw_marks & drawn
            feats = bingo_completed_features(grid, valid_marks)

            if key == "quick5":
                achieved = feats["marked_count"] >= 5
            else:
                achieved = feats.get(key, False)

            if achieved:
                break

        if achieved:
            room["prizes"][key] = [player["id"]]
            player["score"] += points
            newly.append({
                "key": key,
                "name": name,
                "points": points,
                "icon": icon,
                "player_id": player["id"],
                "player_name": player["name"]
            })

    return newly


def find_completed_bingo_ticket(player, drawn=None):
    normalize_bingo_player(player)
    drawn_set = set(drawn or [])
    for idx, grid in enumerate(player.get("tickets", [])):
        raw_marks = set(
            player.get("marked_by_ticket", [])[idx]
            if idx < len(player.get("marked_by_ticket", []))
            else []
        )
        marks = raw_marks & drawn_set if drawn is not None else raw_marks
        feats = bingo_completed_features(grid, marks)
        if feats.get("bingo"):
            return idx, grid
    return None, None

def bingo_pause_for_announcement(room, seconds=3.0):
    room["paused"] = True
    room["auto_pause_until"] = time.time() + seconds

def bingo_draw_loop(code):
    room = active_rooms.get(code)
    if not room or room.get("bingo_loop_running"):
        return

    room["bingo_loop_running"] = True
    try:
        while room.get("status") == "playing" and room.get("remaining"):
            if room.get("paused"):
                auto_until = room.get("auto_pause_until")
                if auto_until and time.time() >= auto_until:
                    room["paused"] = False
                    room["auto_pause_until"] = None
                    socketio.emit("bingo_pause", {"paused":False, "auto":True}, to=f"game_{code}")
                else:
                    socketio.sleep(0.25)
                    continue

            socketio.sleep(max(1.0, float(room.get("speed", 8.0))))

            if room.get("status") != "playing" or room.get("paused"):
                continue

            idx = random.randrange(len(room["remaining"]))
            ball = room["remaining"].pop(idx)
            room["drawn"].append(ball)

            # CPU players mark automatically.
            for p in room["players"]:
                normalize_bingo_player(p)
                if p.get("bot"):
                    for ti, t in enumerate(p["tickets"]):
                        nums = set(ticket_numbers(t))
                        if ball in nums and ball not in p["marked_by_ticket"][ti]:
                            p["marked_by_ticket"][ti].append(ball)

            socketio.emit("bingo_ball", {
                "number": ball,
                "drawn": room["drawn"],
                "remaining": len(room["remaining"]),
                "players": [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "bot": p.get("bot", False),
                        "score": p.get("score", 0)
                    }
                    for p in room["players"]
                ],
                "prizes": room["prizes"],
            }, to=f"game_{code}")

            # CPU checks claims automatically.
            cpu_new = []
            for p in room["players"]:
                if p.get("bot"):
                    cpu_new.extend(bingo_check_player_objectives(room, p, include_bingo=False))

            if cpu_new:
                socketio.emit("bingo_prize_awarded", {
                    "new_prizes": cpu_new,
                    "players": [
                        {
                            "id": p["id"],
                            "name": p["name"],
                            "bot": p.get("bot", False),
                            "score": p.get("score", 0)
                        }
                        for p in room["players"]
                    ],
                    "prizes": room["prizes"]
                }, to=f"game_{code}")

            if not room["remaining"]:
                room["status"] = "finished"
                ranking = sorted(room["players"], key=lambda p: p.get("score", 0), reverse=True)
                socketio.sleep(2.0)
                winner_id=ranking[0]["id"] if ranking else None
                finalize_game_progress(room,winner_id,"bingo90")
                socketio.emit("bingo_over", {
                    "players": [
                        {"id":p["id"],"name":p["name"],"score":p.get("score",0),"bot":p.get("bot",False),
                         "fake_user":p.get("fake_user",False),"stars":p.get("stars",get_user_stars(p["id"]) if isinstance(p.get("id"),int) else 0)}
                        for p in ranking
                    ],
                    "drawn_count": len(room["drawn"])
                }, to=f"game_{code}")
                break
    finally:
        room = active_rooms.get(code)
        if room:
            room["bingo_loop_running"] = False

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE COLLATE NOCASE,
            display_name TEXT,
            theme TEXT NOT NULL DEFAULT 'violeta',
            avatar_style TEXT NOT NULL DEFAULT 'inicial',
            sound_enabled INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS amistades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            amigo_id INTEGER NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(usuario_id, amigo_id)
        );
        CREATE TABLE IF NOT EXISTS progreso_juegos (
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            cpu_wins INTEGER NOT NULL DEFAULT 0,
            online_wins INTEGER NOT NULL DEFAULT 0,
            current_streak INTEGER NOT NULL DEFAULT 0,
            best_streak INTEGER NOT NULL DEFAULT 0,
            best_score INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, game)
        );
        CREATE TABLE IF NOT EXISTS medallas_usuario (
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            medal_key TEXT NOT NULL,
            earned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, game, medal_key)
        );
        CREATE TABLE IF NOT EXISTS partidas_contadas (
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            room_code TEXT NOT NULL,
            PRIMARY KEY(user_id, game, room_code)
        );
        CREATE TABLE IF NOT EXISTS torneos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            opponent_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendiente',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS torneo_juegos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            torneo_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            wins_needed INTEGER NOT NULL DEFAULT 3,
            creator_wins INTEGER NOT NULL DEFAULT 0,
            opponent_wins INTEGER NOT NULL DEFAULT 0,
            orden INTEGER NOT NULL DEFAULT 0
        );
    """)

    # Migraciones sencillas para usuarios.db de versiones anteriores.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(usuarios)").fetchall()}
    migrations = {
        "email": "ALTER TABLE usuarios ADD COLUMN email TEXT",
        "display_name": "ALTER TABLE usuarios ADD COLUMN display_name TEXT",
        "theme": "ALTER TABLE usuarios ADD COLUMN theme TEXT NOT NULL DEFAULT 'violeta'",
        "avatar_style": "ALTER TABLE usuarios ADD COLUMN avatar_style TEXT NOT NULL DEFAULT 'inicial'",
        "sound_enabled": "ALTER TABLE usuarios ADD COLUMN sound_enabled INTEGER NOT NULL DEFAULT 1",
        "stars": "ALTER TABLE usuarios ADD COLUMN stars INTEGER NOT NULL DEFAULT 0",
        "firebase_uid": "ALTER TABLE usuarios ADD COLUMN firebase_uid TEXT",
        "premium": "ALTER TABLE usuarios ADD COLUMN premium INTEGER NOT NULL DEFAULT 0",
    }
    for col, sql in migrations.items():
        if col not in cols:
            conn.execute(sql)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email) WHERE email IS NOT NULL AND email != ''")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_firebase_uid ON usuarios(firebase_uid) WHERE firebase_uid IS NOT NULL AND firebase_uid != ''")
    conn.commit()
    conn.close()

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute("""
        SELECT id, username, email, display_name, theme, avatar_style, sound_enabled, stars, firebase_uid, premium
        FROM usuarios WHERE id=?
    """, (uid,)).fetchone()
    conn.close()
    return user

def friends_of(uid):
    conn = get_db()
    rows = conn.execute("""
        SELECT u.id, u.username, u.stars FROM amistades a
        JOIN usuarios u ON u.id=a.amigo_id
        WHERE a.usuario_id=? AND a.estado='aceptada'
        ORDER BY u.username
    """,(uid,)).fetchall()
    conn.close()
    return rows

def get_user_stars(uid):
    if not isinstance(uid,int):
        return 0
    conn=get_db()
    row=conn.execute("SELECT stars FROM usuarios WHERE id=?",(uid,)).fetchone()
    conn.close()
    return int(row["stars"] if row else 0)

def get_game_progress(uid,game):
    conn=get_db()
    row=conn.execute("SELECT * FROM progreso_juegos WHERE user_id=? AND game=?",(uid,game)).fetchone()
    if not row:
        conn.execute("INSERT OR IGNORE INTO progreso_juegos(user_id,game) VALUES(?,?)",(uid,game))
        conn.commit()
        row=conn.execute("SELECT * FROM progreso_juegos WHERE user_id=? AND game=?",(uid,game)).fetchone()
    earned={r["medal_key"] for r in conn.execute(
        "SELECT medal_key FROM medallas_usuario WHERE user_id=? AND game=?",(uid,game)).fetchall()}
    conn.close()
    return dict(row),earned

def evaluate_medals(uid,game):
    stats,earned=get_game_progress(uid,game)
    new=[]
    conn=get_db()
    for md in medal_definitions(game):
        if md["key"] in earned: continue
        if int(stats.get(md["metric"],0)) >= md["target"]:
            conn.execute("INSERT OR IGNORE INTO medallas_usuario(user_id,game,medal_key) VALUES(?,?,?)",
                         (uid,game,md["key"]))
            conn.execute("UPDATE usuarios SET stars=stars+? WHERE id=?",(md["stars"],uid))
            new.append(md)
    conn.commit();conn.close()
    return new

def record_game_play(uid,game,room_code):
    if not isinstance(uid,int) or game not in GAME_META:return []
    conn=get_db()
    try:
        conn.execute("INSERT INTO partidas_contadas(user_id,game,room_code) VALUES(?,?,?)",
                     (uid,game,str(room_code)))
    except sqlite3.IntegrityError:
        conn.close();return []
    conn.execute("""INSERT INTO progreso_juegos(user_id,game,plays)
                    VALUES(?,?,1)
                    ON CONFLICT(user_id,game) DO UPDATE SET plays=plays+1""",(uid,game))
    conn.commit();conn.close()
    medals = evaluate_medals(uid,game)
    sync_game_stats_to_firestore(uid,game)
    return medals

def record_game_result(uid,game,won=False,vs_cpu=False,score=0):
    if not isinstance(uid,int) or game not in GAME_META:return []
    conn=get_db()
    conn.execute("INSERT OR IGNORE INTO progreso_juegos(user_id,game) VALUES(?,?)",(uid,game))
    if won:
        conn.execute("""UPDATE progreso_juegos SET wins=wins+1,
             cpu_wins=cpu_wins+?, online_wins=online_wins+?,
             current_streak=current_streak+1,
             best_streak=MAX(best_streak,current_streak+1),
             best_score=MAX(best_score,?)
             WHERE user_id=? AND game=?""",
             (1 if vs_cpu else 0,0 if vs_cpu else 1,int(score),uid,game))
    else:
        conn.execute("""UPDATE progreso_juegos SET current_streak=0,
             best_score=MAX(best_score,?) WHERE user_id=? AND game=?""",
             (int(score),uid,game))
    conn.commit();conn.close()
    medals = evaluate_medals(uid,game)
    sync_game_stats_to_firestore(uid,game)
    return medals


def record_tournament_win(room,winner_id):
    tid=room.get("tournament_id")
    if not tid or not isinstance(winner_id,int):
        return
    conn=get_db()
    t=conn.execute("SELECT * FROM torneos WHERE id=? AND status='activo'",(tid,)).fetchone()
    if not t:
        conn.close();return
    row=conn.execute("SELECT * FROM torneo_juegos WHERE torneo_id=? AND game=?",
                     (tid,room.get("game"))).fetchone()
    if not row:
        conn.close();return

    if winner_id==t["creator_id"]:
        conn.execute("UPDATE torneo_juegos SET creator_wins=creator_wins+1 WHERE id=?",(row["id"],))
    elif winner_id==t["opponent_id"]:
        conn.execute("UPDATE torneo_juegos SET opponent_wins=opponent_wins+1 WHERE id=?",(row["id"],))
    conn.commit()

    # Cierra el torneo cuando todos los juegos tienen un ganador de su serie.
    games=conn.execute("SELECT * FROM torneo_juegos WHERE torneo_id=?",(tid,)).fetchall()
    if games and all(max(g["creator_wins"],g["opponent_wins"])>=g["wins_needed"] for g in games):
        conn.execute("UPDATE torneos SET status='finalizado' WHERE id=?",(tid,))
        conn.commit()
    conn.close()

def finalize_game_progress(room,winner_id,game=None):
    if room.get("progress_finished"):
        return
    room["progress_finished"]=True
    game=game or room.get("game")
    for pl in room.get("players",[]):
        if not isinstance(pl.get("id"),int):
            continue
        opponents=[x for x in room.get("players",[]) if x.get("id")!=pl["id"]]
        vs_cpu=any(x.get("bot") for x in opponents)
        record_game_result(pl["id"],game,won=(pl["id"]==winner_id),
                           vs_cpu=vs_cpu,score=int(pl.get("score",0) or 0))
    if winner_id is not None:
        record_tournament_win(room,winner_id)

def fake_rival():
    names=["Alex","Dani","Marta","Lucia","Pablo","Nora","Leo","Sara","Hugo","Irene",
           "Mario","Claudia","Adrian","Eva","Marcos","Lola"]
    return {
        "id":"fake_"+uuid4().hex[:8],
        "name":random.choice(names)+"_"+str(random.randint(10,999)),
        "bot":True,"fake_user":True,"stars":random.randint(0,85),
        "score":0,"streak":0
    }

def room_public(room):
    players = []
    for p in room["players"]:
        players.append({
            "id": p["id"], "name": p["name"], "bot": p.get("bot", False),
            "score": p.get("score",0), "streak": p.get("streak",0),
            "fake_user":p.get("fake_user",False),
            "stars":p.get("stars", get_user_stars(p["id"]) if isinstance(p.get("id"),int) else 0)
        })
    return {
        "code": room["code"], "game": room["game"], "game_name": room["game_name"],
        "host_id": room["host_id"], "host_name": room["host_name"],
        "status": room["status"], "players": players
    }

def find_player(room, uid):
    return next((p for p in room["players"] if p["id"] == uid), None)

@app.route("/")
def index():
    return redirect(url_for("menu")) if current_user() else render_template("login.html")

@app.route("/registro", methods=["GET","POST"])
def registro():
    if request.method=="POST":
        username=request.form.get("username","").strip()
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        password2=request.form.get("password2","")
        if len(username)<3: flash("El nombre debe tener al menos 3 caracteres.","error"); return render_template("registro.html")
        if "@" not in email or "." not in email.split("@")[-1]: flash("Introduce un correo electrónico válido.","error"); return render_template("registro.html")
        if len(password)<6: flash("La contraseña debe tener al menos 6 caracteres.","error"); return render_template("registro.html")
        if password!=password2: flash("Las contraseñas no coinciden.","error"); return render_template("registro.html")
        conn=get_db()
        if conn.execute("SELECT 1 FROM usuarios WHERE username=?",(username,)).fetchone():
            conn.close(); flash("Ese nombre de usuario ya existe.","error"); return render_template("registro.html")
        if conn.execute("SELECT 1 FROM usuarios WHERE email=?",(email,)).fetchone():
            conn.close(); flash("Ese correo electrónico ya está asociado a otra cuenta.","error"); return render_template("registro.html")
        conn.close()

        # 1) Firebase Authentication
        ok, auth = firebase_sign_up(email,password)
        if not ok:
            flash(firebase_error_text(auth),"error"); return render_template("registro.html")
        firebase_uid=auth["localId"]; id_token=auth["idToken"]

        # 2) Perfil protegido en Cloud Firestore
        ok_profile, err = firestore_create_profile(firebase_uid,id_token,email,username)
        if not ok_profile:
            firebase_delete_account(id_token)
            flash("No se pudo crear el perfil en la nube. No se ha creado la cuenta; inténtalo otra vez.","error")
            return render_template("registro.html")

        # 3) Copia local para mantener intactos juegos, amigos, salas y medallas actuales
        conn=get_db()
        try:
            cur=conn.execute("""INSERT INTO usuarios(username,email,password_hash,display_name,firebase_uid,premium)
                                VALUES(?,?,?,?,?,0)""",
                             (username,email,"!firebase!",username,firebase_uid))
            conn.commit(); session["user_id"]=cur.lastrowid
            session["firebase_uid"]=firebase_uid
        except sqlite3.IntegrityError:
            conn.rollback(); firebase_delete_account(id_token)
            conn.close(); flash("Ese usuario o correo ya existe.","error"); return render_template("registro.html")
        conn.close()
        return redirect(url_for("menu"))
    return render_template("registro.html")

@app.route("/login", methods=["POST"])
def login():
    identifier=request.form.get("username","").strip()
    password=request.form.get("password","")
    conn=get_db()
    user=conn.execute("SELECT * FROM usuarios WHERE username=? OR email=?",(identifier,identifier.lower())).fetchone()

    # Cuentas nuevas: Firebase es quien valida la contraseña.
    if user and user["firebase_uid"]:
        email=(user["email"] or "").lower()
        ok, auth=firebase_sign_in(email,password)
        if not ok:
            conn.close(); flash(firebase_error_text(auth),"error"); return redirect(url_for("index"))
okp, profile=firestore_get_profile(auth["localId"],auth["idToken"])
if okp:
    conn.execute(
        "UPDATE usuarios SET premium=?, stars=? WHERE id=?",
        (1 if profile.get("premium") else 0,
         profile.get("stars", user["stars"] or 0),
         user["id"])
    )
    conn.commit()
        session["user_id"]=user["id"]; session["firebase_uid"]=auth["localId"]
        conn.close(); return redirect(url_for("menu"))

    # Permite entrar por correo a una cuenta Firebase que aún no tenga copia local
    # (por ejemplo, el usuario de prueba creado desde la consola).
    if not user and "@" in identifier:
        ok, auth=firebase_sign_in(identifier.lower(),password)
        if ok:
            okp, profile=firestore_get_profile(auth["localId"],auth["idToken"])
            if okp and profile.get("username"):
                try:
                    cur=conn.execute("""INSERT INTO usuarios(username,email,password_hash,display_name,stars,firebase_uid,premium)
                                        VALUES(?,?,?,?,?,?,?)""",
                                     (profile["username"],identifier.lower(),"!firebase!",profile["username"],
                                      profile.get("stars",0),auth["localId"],1 if profile.get("premium") else 0))
                    conn.commit(); session["user_id"]=cur.lastrowid; session["firebase_uid"]=auth["localId"]
                    conn.close(); return redirect(url_for("menu"))
                except sqlite3.IntegrityError:
                    conn.rollback()
        conn.close(); flash("Correo/usuario o contraseña incorrectos.","error"); return redirect(url_for("index"))

    # Compatibilidad temporal con usuarios antiguos del proyecto, todavía locales.
    if user and check_password_hash(user["password_hash"],password):
        session["user_id"]=user["id"]; conn.close(); return redirect(url_for("menu"))

    conn.close(); flash("Correo/usuario o contraseña incorrectos.","error"); return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))

@app.route("/menu")
def menu():
    user=current_user()
    if not user:return redirect(url_for("index"))
    conn=get_db()
    amigos=conn.execute("""SELECT u.id,u.username,u.stars FROM amistades a JOIN usuarios u ON u.id=a.amigo_id
        WHERE a.usuario_id=? AND a.estado='aceptada' ORDER BY u.username""",(user["id"],)).fetchall()
    solicitudes=conn.execute("""SELECT a.id solicitud_id,u.id,u.username,u.stars FROM amistades a JOIN usuarios u ON u.id=a.usuario_id
        WHERE a.amigo_id=? AND a.estado='pendiente' ORDER BY a.creado_en DESC""",(user["id"],)).fetchall()
    enviadas=conn.execute("""SELECT u.id,u.username,u.stars FROM amistades a JOIN usuarios u ON u.id=a.amigo_id
        WHERE a.usuario_id=? AND a.estado='pendiente'""",(user["id"],)).fetchall()
    torneos_pendientes=conn.execute("""SELECT t.id,u.username from_name
        FROM torneos t JOIN usuarios u ON u.id=t.creator_id
        WHERE t.opponent_id=? AND t.status='pendiente'
        ORDER BY t.created_at DESC""",(user["id"],)).fetchall()
    torneos_activos=conn.execute("""SELECT t.id,
        CASE WHEN t.creator_id=? THEN u2.username ELSE u1.username END rival
        FROM torneos t JOIN usuarios u1 ON u1.id=t.creator_id
        JOIN usuarios u2 ON u2.id=t.opponent_id
        WHERE (t.creator_id=? OR t.opponent_id=?) AND t.status='activo'
        ORDER BY t.created_at DESC""",(user["id"],user["id"],user["id"])).fetchall()
    conn.close()
    return render_template("menu.html",user=user,amigos=amigos,solicitudes=solicitudes,
                           enviadas=enviadas,torneos_pendientes=torneos_pendientes,
                           torneos_activos=torneos_activos)


@app.route("/torneos/nuevo")
def torneo_nuevo():
    user=current_user()
    if not user:return redirect(url_for("index"))
    return render_template("torneo_nuevo.html",user=user,amigos=friends_of(user["id"]),games=GAME_META)

@app.post("/torneos/crear")
def torneo_crear():
    user=current_user()
    if not user:return redirect(url_for("index"))
    try: opponent_id=int(request.form.get("opponent_id"))
    except: flash("Elige un rival.","error");return redirect(url_for("torneo_nuevo"))
    selected=[g for g in GAME_META if request.form.get("game_"+g)]
    if not selected:
        flash("Elige al menos un juego.","error");return redirect(url_for("torneo_nuevo"))
    conn=get_db()
    rival=conn.execute("SELECT id,username FROM usuarios WHERE id=?",(opponent_id,)).fetchone()
    if not rival:
        conn.close();flash("Rival no válido.","error");return redirect(url_for("torneo_nuevo"))
    cur=conn.execute("INSERT INTO torneos(creator_id,opponent_id,status) VALUES(?,?,'pendiente')",
                     (user["id"],opponent_id))
    tid=cur.lastrowid
    for i,g in enumerate(selected):
        try:wins=max(1,min(20,int(request.form.get("wins_"+g,3))))
        except:wins=3
        conn.execute("""INSERT INTO torneo_juegos(torneo_id,game,wins_needed,orden)
                        VALUES(?,?,?,?)""",(tid,g,wins,i))
    conn.commit();conn.close()
    if opponent_id in connected_users:
        socketio.emit("tournament_invitation",{
            "id":tid,"from_name":user["username"],"games":len(selected)
        },to=f"user_{opponent_id}")
    flash(f"Invitación de torneo enviada a {rival['username']}.","ok")
    return redirect(url_for("torneo_ver",tid=tid))

@app.post("/torneos/<int:tid>/jugar/<game>")
def torneo_jugar(tid,game):
    user=current_user()
    if not user:return redirect(url_for("index"))
    conn=get_db()
    t=conn.execute("SELECT * FROM torneos WHERE id=?",(tid,)).fetchone()
    gj=conn.execute("SELECT * FROM torneo_juegos WHERE torneo_id=? AND game=?",(tid,game)).fetchone()
    if not t or not gj or t["status"]!="activo" or user["id"] not in (t["creator_id"],t["opponent_id"]):
        conn.close();return redirect(url_for("menu"))
    other_id=t["opponent_id"] if user["id"]==t["creator_id"] else t["creator_id"]
    other=conn.execute("SELECT id,username,stars FROM usuarios WHERE id=?",(other_id,)).fetchone()
    conn.close()
    code,room=create_mode_room(game,user,other,opponent_kind="real")
    room["tournament_id"]=tid
    room["tournament_game"]=game
    room["tournament_target"]=int(gj["wins_needed"])
    room["tournament_order"]=int(gj["orden"])
    if other_id in connected_users:
        socketio.emit("room_invitation",{
            "code":code,"from_name":user["username"],
            "game":GAME_META[game]["name"]
        },to=f"user_{other_id}")
    return redirect(game_lobby_url(game,code))


@app.route("/api/torneos/<int:tid>/estado")
def torneo_estado_api(tid):
    user=current_user()
    if not user:return jsonify({"ok":False}),401
    conn=get_db()
    t=conn.execute("""SELECT t.*,u1.username creator_name,u2.username opponent_name
        FROM torneos t JOIN usuarios u1 ON u1.id=t.creator_id
        JOIN usuarios u2 ON u2.id=t.opponent_id WHERE t.id=?""",(tid,)).fetchone()
    if not t or user["id"] not in (t["creator_id"],t["opponent_id"]):
        conn.close();return jsonify({"ok":False}),403
    games=conn.execute("SELECT * FROM torneo_juegos WHERE torneo_id=? ORDER BY orden",(tid,)).fetchall()
    payload=[]
    for g in games:
        finished=max(g["creator_wins"],g["opponent_wins"])>=g["wins_needed"]
        winner_id=None
        if finished:
            winner_id=t["creator_id"] if g["creator_wins"]>g["opponent_wins"] else t["opponent_id"]
        payload.append({
            "game":g["game"],"wins_needed":g["wins_needed"],
            "creator_wins":g["creator_wins"],"opponent_wins":g["opponent_wins"],
            "orden":g["orden"],"finished":finished,"winner_id":winner_id,
            "name":GAME_META.get(g["game"],{}).get("name",g["game"]),
            "icon":GAME_META.get(g["game"],{}).get("icon","🎮")
        })
    conn.close()
    return jsonify({
        "ok":True,"status":t["status"],"id":tid,
        "creator_id":t["creator_id"],"opponent_id":t["opponent_id"],
        "creator_name":t["creator_name"],"opponent_name":t["opponent_name"],
        "games":payload
    })

@app.route("/torneos/<int:tid>")
def torneo_ver(tid):
    user=current_user()
    if not user:return redirect(url_for("index"))
    conn=get_db()
    t=conn.execute("""SELECT t.*,u1.username creator_name,u1.stars creator_stars,
        u2.username opponent_name,u2.stars opponent_stars
        FROM torneos t JOIN usuarios u1 ON u1.id=t.creator_id
        JOIN usuarios u2 ON u2.id=t.opponent_id WHERE t.id=?""",(tid,)).fetchone()
    if not t or user["id"] not in (t["creator_id"],t["opponent_id"]):
        conn.close();return redirect(url_for("menu"))
    games=conn.execute("SELECT * FROM torneo_juegos WHERE torneo_id=? ORDER BY orden",(tid,)).fetchall()
    conn.close()
    return render_template("torneo_ver.html",user=user,t=t,games=games,meta=GAME_META)

@app.post("/torneos/<int:tid>/responder")
def torneo_responder(tid):
    user=current_user()
    if not user:return redirect(url_for("index"))
    action=request.form.get("action")
    conn=get_db()
    t=conn.execute("SELECT * FROM torneos WHERE id=? AND opponent_id=?",(tid,user["id"])).fetchone()
    if t and t["status"]=="pendiente":
        conn.execute("UPDATE torneos SET status=? WHERE id=?",
                     ("activo" if action=="aceptar" else "rechazado",tid))
        conn.commit()
    conn.close()
    return redirect(url_for("torneo_ver",tid=tid) if action=="aceptar" else url_for("menu"))

@app.route("/buscar_usuario")
def buscar_usuario():
    user=current_user()
    if not user: return jsonify([]),401
    q=request.args.get("q","").strip()
    if not q: return jsonify([])
    conn=get_db(); rows=conn.execute("SELECT id,username,stars FROM usuarios WHERE username LIKE ? AND id!=? LIMIT 10",(f"%{q}%",user["id"])).fetchall(); conn.close()
    return jsonify([{"id":r["id"],"username":r["username"],"stars":r["stars"]} for r in rows])

@app.route("/estado_amigos")
def estado_amigos():
    user=current_user()
    if not user: return jsonify({}),401
    return jsonify({str(r["id"]):(r["id"] in connected_users) for r in friends_of(user["id"])})

@app.route("/anadir_amigo/<int:amigo_id>",methods=["POST"])
def anadir_amigo(amigo_id):
    user=current_user()
    if not user: return redirect(url_for("index"))
    conn=get_db(); amigo=conn.execute("SELECT id,username FROM usuarios WHERE id=?",(amigo_id,)).fetchone()
    if not amigo or amigo_id==user["id"]: conn.close(); flash("Usuario no válido.","error"); return redirect(url_for("menu"))
    ya=conn.execute("SELECT id,estado FROM amistades WHERE usuario_id=? AND amigo_id=?",(user["id"],amigo_id)).fetchone()
    inv=conn.execute("SELECT id,estado FROM amistades WHERE usuario_id=? AND amigo_id=?",(amigo_id,user["id"])).fetchone()
    if inv and inv["estado"]=="pendiente":
        conn.execute("UPDATE amistades SET estado='aceptada' WHERE id=?",(inv["id"],))
        conn.execute("INSERT OR IGNORE INTO amistades(usuario_id,amigo_id,estado) VALUES(?,?,'aceptada')",(user["id"],amigo_id))
        conn.commit(); conn.close(); flash("Solicitud aceptada automáticamente: ya sois amigos.","ok"); return redirect(url_for("menu"))
    if ya: conn.close(); flash("Ya existe una relación con ese usuario.","info"); return redirect(url_for("menu"))
    conn.execute("INSERT INTO amistades(usuario_id,amigo_id,estado) VALUES(?,?,'pendiente')",(user["id"],amigo_id)); conn.commit(); conn.close()
    flash(f"Solicitud enviada a {amigo['username']}.","ok"); return redirect(url_for("menu"))

@app.route("/aceptar_amigo/<int:sid>",methods=["POST"])
def aceptar_amigo(sid):
    user=current_user()
    if not user: return redirect(url_for("index"))
    conn=get_db(); s=conn.execute("SELECT * FROM amistades WHERE id=? AND amigo_id=? AND estado='pendiente'",(sid,user["id"])).fetchone()
    if s:
        conn.execute("UPDATE amistades SET estado='aceptada' WHERE id=?",(sid,))
        conn.execute("INSERT OR IGNORE INTO amistades(usuario_id,amigo_id,estado) VALUES(?,?,'aceptada')",(user["id"],s["usuario_id"]))
        conn.commit()
    conn.close(); return redirect(url_for("menu"))

@app.route("/rechazar_amigo/<int:sid>",methods=["POST"])
def rechazar_amigo(sid):
    user=current_user()
    if not user: return redirect(url_for("index"))
    conn=get_db(); conn.execute("DELETE FROM amistades WHERE id=? AND amigo_id=?",(sid,user["id"])); conn.commit(); conn.close()
    return redirect(url_for("menu"))


def game_lobby_url(game,code):
    if game=="bingo90": return url_for("sala_bingo",codigo=code)
    if game=="parchis_deluxe": return url_for("parchis_sala",codigo=code)
    if game=="reto_relampago": return url_for("sala",codigo=code)
    return f"/sala_{game}/{code}"

def make_game_player(user,game,bot=False,fake_user=False,stars=None):
    data=dict(user) if not isinstance(user,dict) else user
    p={
        "id":data["id"],
        "name":data.get("username",data.get("name","Jugador")),
        "bot":bot,"fake_user":fake_user,
        "stars":int(stars if stars is not None else data.get("stars",0) or 0),
        "score":0,"streak":0
    }
    if game=="bingo90":
        p.update({"selected_tickets":1,"tickets":[generate_spanish_ticket()],
                  "marked":[],"marked_by_ticket":[[]],"last_bad_check":0})
    if game=="parchis_deluxe":
        p.update({"colors":[],"doubles_streak":0})
    return p

def create_mode_room(game,host_user,opponent=None,opponent_kind=None):
    """Crea una sala común para Amigos/CPU/Matchmaking."""
    if game=="bingo90":
        code=create_bingo_room(host_user)
        room=active_rooms[code]
        room["players"][0]["stars"]=int(host_user["stars"] or 0)
    elif game=="parchis_deluxe":
        code,room=create_parchis_room(host_user)
        room["players"][0]["stars"]=int(host_user["stars"] or 0)
        active_rooms[code]=room
    elif game=="reto_relampago":
        code=uuid4().hex[:6].upper()
        room={
            "code":code,"game":"reto_relampago","game_name":"Reto Relámpago",
            "host_id":host_user["id"],"host_name":host_user["username"],"status":"waiting",
            "players":[{"id":host_user["id"],"name":host_user["username"],"bot":False,
                        "fake_user":False,"stars":int(host_user["stars"] or 0),
                        "score":0,"streak":0}],
            "question_order":random.sample(range(len(QUESTIONS)),min(12,len(QUESTIONS))),
            "round":-1,"answered":set(),"round_started":None,
            "round_token":0,"round_advancing":False
        }
        active_rooms[code]=room
    else:
        meta=GAME_META[game]
        max_players={"uno_deluxe":8,"domino_deluxe":4,"dobble_deluxe":8,
                     "subastado_deluxe":4,"barquitos_deluxe":4,
                     "oca_deluxe":4,"serpientes_deluxe":4,"brisca_deluxe":4,
                     "conecta4_deluxe":2,"damas_deluxe":2,"ahorcado_deluxe":4,"poker_deluxe":4,"blackjack_deluxe":4}.get(game,4)
        code=uuid4().hex[:6].upper()
        room={
            "code":code,"game":game,"game_name":meta["name"],
            "host_id":host_user["id"],"host_name":host_user["username"],
            "status":"waiting","max_players":max_players,
            "players":[{"id":host_user["id"],"name":host_user["username"],"bot":False,
                        "fake_user":False,"stars":int(host_user["stars"] or 0),
                        "score":0,"streak":0}]
        }
        active_rooms[code]=room

    if opponent is not None:
        if opponent_kind=="fake":
            fp=fake_rival()
            fp["score"]=0;fp["streak"]=0
            if game=="bingo90":
                fp.update({"selected_tickets":1,"tickets":[generate_spanish_ticket()],
                           "marked":[],"marked_by_ticket":[[]],"last_bad_check":0})
            if game=="parchis_deluxe":
                fp.update({"colors":[],"doubles_streak":0})
            room["players"].append(fp)
        elif opponent_kind=="cpu":
            fp={
                "id":"cpu_"+uuid4().hex[:8],"name":"CPU Nova","bot":True,
                "fake_user":False,"stars":0,"score":0,"streak":0
            }
            if game=="bingo90":
                fp.update({"selected_tickets":1,"tickets":[generate_spanish_ticket()],
                           "marked":[],"marked_by_ticket":[[]],"last_bad_check":0})
            if game=="parchis_deluxe":
                fp.update({"colors":[],"doubles_streak":0})
            room["players"].append(fp)
        elif opponent_kind=="real":
            room["players"].append(make_game_player(opponent,game,bot=False,fake_user=False))
    return code,room

@app.post("/juego/<game>/crear")
def juego_crear_modo(game):
    user=current_user()
    if not user:return redirect(url_for("index"))
    if game not in GAME_META:return redirect(url_for("juegos"))
    mode=request.form.get("mode","friends")
    if mode=="random":
        return redirect(url_for("matchmaking_page",game=game))
    opponent_kind="cpu" if mode=="cpu" else None
    code,room=create_mode_room(game,user,opponent=True if opponent_kind else None,
                               opponent_kind=opponent_kind)
    return redirect(game_lobby_url(game,code))

@app.route("/juego/<game>/buscar")
def matchmaking_page(game):
    user=current_user()
    if not user:return redirect(url_for("index"))
    if game not in GAME_META:return redirect(url_for("juegos"))
    return render_template("matchmaking.html",user=user,game=game,meta=GAME_META[game])

@app.post("/api/matchmaking/<game>/join")
def matchmaking_join(game):
    user=current_user()
    if not user:return jsonify({"ok":False}),401
    if game not in GAME_META:return jsonify({"ok":False}),404

    # ¿Ya fue emparejado en una petición anterior?
    ready=matchmaking_matches.pop(user["id"],None)
    if ready:
        return jsonify({"ok":True,"matched":True,"url":ready})

    waiting=matchmaking_waiting.get(game)
    if waiting and waiting["user_id"]!=user["id"]:
        other_id=waiting["user_id"]
        conn=get_db()
        other=conn.execute("SELECT id,username,stars FROM usuarios WHERE id=?",(other_id,)).fetchone()
        conn.close()
        if other:
            code,room=create_mode_room(game,other,user,opponent_kind="real")
            url_second=game_lobby_url(game,code)
            matchmaking_matches[other_id]=url_second
            matchmaking_waiting.pop(game,None)
            return jsonify({"ok":True,"matched":True,"url":url_second,"real":True})

    matchmaking_waiting[game]={
        "user_id":user["id"],"username":user["username"],"stars":int(user["stars"] or 0),
        "started":time.time()
    }
    return jsonify({"ok":True,"matched":False})

@app.get("/api/matchmaking/<game>/status")
def matchmaking_status(game):
    user=current_user()
    if not user:return jsonify({"ok":False}),401

    ready=matchmaking_matches.pop(user["id"],None)
    if ready:
        return jsonify({"ok":True,"matched":True,"url":ready,"real":True})

    waiting=matchmaking_waiting.get(game)
    if not waiting or waiting["user_id"]!=user["id"]:
        return jsonify({"ok":True,"matched":False})

    # Tras 4 segundos sin rival real, aparece un rival ficticio con nombre y estrellas.
    if time.time()-waiting["started"]>=4.0:
        matchmaking_waiting.pop(game,None)
        code,room=create_mode_room(game,user,opponent=True,opponent_kind="fake")
        return jsonify({"ok":True,"matched":True,"url":game_lobby_url(game,code),
                        "real":False,"opponent":room["players"][1]["name"],
                        "stars":room["players"][1]["stars"]})
    return jsonify({"ok":True,"matched":False})

@app.route("/juego/<game>/modo")
def juego_modo(game):
    user=current_user()
    if not user:return redirect(url_for("index"))
    if game not in GAME_META:return redirect(url_for("juegos"))
    stats,earned=get_game_progress(user["id"],game)
    medals=medal_definitions(game)
    return render_template("juego_modo.html",user=user,game=game,meta=GAME_META[game],
                           amigos=friends_of(user["id"]),stats=stats,earned=earned,medals=medals)

@app.route("/medallas")
def medallas():
    user=current_user()
    if not user:return redirect(url_for("index"))
    games=[]
    for slug,meta in GAME_META.items():
        stats,earned=get_game_progress(user["id"],slug)
        games.append({"slug":slug,"meta":meta,"stats":stats,"earned":earned,
                      "medals":medal_definitions(slug)})
    return render_template("medallas.html",user=user,games=games)


@app.post("/api/firebase/sync-test")
def api_firebase_sync_test():
    user=current_user()
    if not user:
        return jsonify({"ok":False,"error":"Sesión no válida"}),401
    d=request.get_json(silent=True) or {}
    game=d.get("game","oca_deluxe")
    ok=sync_game_stats_to_firestore(user["id"],game)
    conn=get_db()
    u=conn.execute("SELECT email,firebase_uid FROM usuarios WHERE id=?",(user["id"],)).fetchone()
    conn.close()
    return jsonify({
        "ok":bool(ok),
        "game":game,
        "firebase_uid_present":bool(u and u["firebase_uid"]),
        "email":u["email"] if u else ""
    })
@app.post("/api/progreso/jugada")
def api_progreso_jugada():
    user=current_user()
    if not user:
        return jsonify({"ok":False}),401

    d=request.get_json(silent=True) or {}
    game=d.get("game")
    code=d.get("code","sin_sala")

    new=record_game_play(user["id"],game,code)
    fresh=current_user()

    conn=get_db()
    row=conn.execute(
        "SELECT plays FROM progreso_juegos WHERE user_id=? AND game=?",
        (user["id"],game)
    ).fetchone()
    conn.close()

    plays=int(row["plays"] if row else 0)

    return jsonify({
        "ok":True,
        "stars":fresh["stars"],
        "new_medals":new,
        "plays":plays
    })
@app.post("/api/progreso/resultado")
def api_progreso_resultado():
    user=current_user()
    if not user:return jsonify({"ok":False}),401
    d=request.get_json(silent=True) or {}
    won=bool(d.get("won"))
    new=record_game_result(user["id"],d.get("game"),won,
                           bool(d.get("vs_cpu")),int(d.get("score",0) or 0))
    if won:
        room=active_rooms.get(str(d.get("code","")).upper())
        if room:
            record_tournament_win(room,user["id"])
    fresh=current_user()
    return jsonify({"ok":True,"stars":fresh["stars"],"new_medals":new})

@app.route("/juegos")
def juegos():
    user=current_user()
    if not user: return redirect(url_for("index"))
    return render_template("juegos.html",user=user)


@app.route("/crear_sala/bingo90", methods=["POST"])
def crear_sala_bingo():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    code = create_bingo_room(user)
    return redirect(url_for("sala_bingo", codigo=code))


@app.route("/bingo/<codigo>/cartones", methods=["POST"])
def bingo_cartones(codigo):
    user=current_user()
    if not user: return {"ok":False,"error":"Sesión no válida"},401
    room=active_rooms.get(codigo.upper())
    if not room or room.get("game")!="bingo90": return {"ok":False,"error":"Sala no encontrada"},404
    if room.get("status")!="waiting": return {"ok":False,"error":"La partida ya ha empezado"},400
    p=find_player(room,user["id"])
    if not p: return {"ok":False,"error":"No perteneces a esta sala"},403
    try: count=int(request.form.get("count",1))
    except: count=1
    count=max(1,min(4,count))
    p["selected_tickets"]=count
    p["tickets"]=[generate_spanish_ticket() for _ in range(count)]
    p["marked"]=[]
    p["marked_by_ticket"]=[[] for _ in range(p.get("selected_tickets",1))]
    return {"ok":True,"count":count,"tickets":p["tickets"]}

@app.route("/sala_bingo/<codigo>")
def sala_bingo(codigo):
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    room = active_rooms.get(codigo.upper())
    if not room or room.get("game") != "bingo90" or not find_player(room, user["id"]):
        flash("No perteneces a esa sala de Bingo.", "error")
        return redirect(url_for("menu"))
    if room["status"] == "playing":
        return redirect(url_for("bingo_partida", codigo=codigo.upper()))
    return render_template("bingo_sala.html", user=user, codigo=codigo.upper(),
                           sala=bingo_public(room,user["id"]), amigos=friends_of(user["id"]))

@app.route("/bingo/<codigo>")
def bingo_partida(codigo):
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    room = active_rooms.get(codigo.upper())
    if not room or room.get("game") != "bingo90" or not find_player(room,user["id"]):
        return redirect(url_for("menu"))
    return render_template("bingo_partida.html", user=user, codigo=codigo.upper(),
                           sala=bingo_public(room,user["id"]))

@app.route("/crear_sala/reto_relampago", methods=["POST"])
def crear_sala():
    user=current_user()
    if not user: return redirect(url_for("index"))
    code=uuid4().hex[:6].upper()
    active_rooms[code]={
        "code":code,"game":"reto_relampago","game_name":"Reto Relámpago",
        "host_id":user["id"],"host_name":user["username"],"status":"waiting",
        "players":[{"id":user["id"],"name":user["username"],"bot":False,"score":0,"streak":0}],
        "question_order":random.sample(range(len(QUESTIONS)), min(12,len(QUESTIONS))),
        "round":-1,"answered":set(),"round_started":None,
        "round_token":0,"round_advancing":False
    }
    return redirect(url_for("sala", codigo=code))

@app.route("/unirse", methods=["POST"])
def unirse_codigo():
    user=current_user()
    if not user: return redirect(url_for("index"))
    code=request.form.get("codigo","").strip().upper()
    room=active_rooms.get(code)
    if not room or room["status"]!="waiting":
        flash("Sala no encontrada o ya iniciada.","error"); return redirect(url_for("menu"))
    if not find_player(room,user["id"]):
        room["players"].append({"id":user["id"],"name":user["username"],"bot":False,"score":0,"streak":0,"stars":int(user["stars"] or 0)})
    if room.get("game") == "bingo90":
        return redirect(url_for("sala_bingo", codigo=code))
    if room.get("game") == "parchis_deluxe":
        return redirect(url_for("parchis_sala", codigo=code))
    return redirect(url_for("sala", codigo=code))

@app.route("/sala/<codigo>")
def sala(codigo):
    user=current_user()
    if not user: return redirect(url_for("index"))
    room=active_rooms.get(codigo.upper())
    if not room or not find_player(room,user["id"]):
        flash("No perteneces a esa sala.","error"); return redirect(url_for("menu"))
    if room["status"]=="playing": return redirect(url_for("partida",codigo=codigo.upper()))
    return render_template("sala.html",user=user,codigo=codigo.upper(),sala=room_public(room),amigos=friends_of(user["id"]))

@app.route("/estado_reto/<codigo>")
def estado_reto(codigo):
    user=current_user()
    room=active_rooms.get(codigo.upper())
    if not user or not room or room.get("game")!="reto_relampago":
        return jsonify({"ok":False}),404
    if not find_player(room,user["id"]):
        return jsonify({"ok":False}),403
    return jsonify({
        "ok":True,
        "status":room.get("status","waiting"),
        "code":room["code"]
    })

@app.route("/partida/<codigo>")
def partida(codigo):
    user=current_user()
    if not user: return redirect(url_for("index"))
    room=active_rooms.get(codigo.upper())
    if not room or not find_player(room,user["id"]): return redirect(url_for("menu"))
    return render_template("partida.html",user=user,codigo=codigo.upper(),sala=room_public(room))


THEMES = {
    "violeta": "Violeta",
    "oceano": "Océano",
    "esmeralda": "Esmeralda",
    "atardecer": "Atardecer",
    "rojo_neon": "Rojo neón",
    "dorado": "Dorado",
    "hielo": "Hielo",
    "medianoche": "Medianoche",
    "rosa": "Rosa",
    "cobre": "Cobre",
    "bosque": "Bosque",
    "arcade": "Arcade"
}

@app.context_processor
def inject_profile():
    user = current_user()
    return {"profile_user": user, "theme_options": THEMES}

@app.route("/ajustes", methods=["GET", "POST"])
def ajustes():
    user = current_user()
    if not user:
        return redirect(url_for("index"))

    if request.method == "POST":
        section = request.form.get("section", "profile")
        conn = get_db()

        if section == "appearance":
            theme = request.form.get("theme", "violeta")
            avatar_style = request.form.get("avatar_style", "inicial")
            sound_enabled = 1 if request.form.get("sound_enabled") == "on" else 0
            if theme not in THEMES:
                theme = "violeta"
            if avatar_style not in {"inicial", "rayo", "mando", "robot"}:
                avatar_style = "inicial"
            conn.execute("""
                UPDATE usuarios
                SET theme=?, avatar_style=?, sound_enabled=?
                WHERE id=?
            """, (theme, avatar_style, sound_enabled, user["id"]))
            conn.commit()
            conn.close()
            flash("Apariencia guardada.", "ok")
            return redirect(url_for("ajustes"))

        if section == "profile":
            display_name = request.form.get("display_name", "").strip() or user["username"]
            email = request.form.get("email", "").strip().lower()
            if "@" not in email or "." not in email.split("@")[-1]:
                conn.close()
                flash("Introduce un correo electrónico válido.", "error")
                return redirect(url_for("ajustes"))
            used = conn.execute("SELECT id FROM usuarios WHERE email=? AND id!=?", (email, user["id"])).fetchone()
            if used:
                conn.close()
                flash("Ese correo ya está asociado a otra cuenta.", "error")
                return redirect(url_for("ajustes"))
            conn.execute("UPDATE usuarios SET display_name=?, email=? WHERE id=?", (display_name[:30], email, user["id"]))
            conn.commit()
            conn.close()
            flash("Perfil actualizado.", "ok")
            return redirect(url_for("ajustes"))

        if section == "password":
            current = request.form.get("current_password", "")
            new1 = request.form.get("new_password", "")
            new2 = request.form.get("new_password2", "")
            row = conn.execute("SELECT password_hash FROM usuarios WHERE id=?", (user["id"],)).fetchone()
            if not row or not check_password_hash(row["password_hash"], current):
                conn.close()
                flash("La contraseña actual no es correcta.", "error")
                return redirect(url_for("ajustes"))
            if len(new1) < 6:
                conn.close()
                flash("La nueva contraseña debe tener al menos 6 caracteres.", "error")
                return redirect(url_for("ajustes"))
            if new1 != new2:
                conn.close()
                flash("Las nuevas contraseñas no coinciden.", "error")
                return redirect(url_for("ajustes"))
            conn.execute("UPDATE usuarios SET password_hash=? WHERE id=?", (generate_password_hash(new1), user["id"]))
            conn.commit()
            conn.close()
            flash("Contraseña cambiada correctamente.", "ok")
            return redirect(url_for("ajustes"))

        conn.close()

    return render_template("ajustes.html", user=current_user(), themes=THEMES)

@app.route("/mi_perfil")
def mi_perfil():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    return render_template("perfil.html", user=user)


@socketio.on("connect")
def ws_connect():
    user=current_user()
    if not user: return False
    uid=user["id"]; connected_users[uid]=connected_users.get(uid,0)+1
    join_room(f"user_{uid}")
    emit("presence_changed",{"user_id":uid,"online":True},broadcast=True)

@socketio.on("disconnect")
def ws_disconnect():
    user=current_user()
    if not user:return
    uid=user["id"]; connected_users[uid]=max(0,connected_users.get(uid,1)-1)
    if connected_users[uid]==0:
        connected_users.pop(uid,None); emit("presence_changed",{"user_id":uid,"online":False},broadcast=True)

@socketio.on("join_lobby")
def join_lobby(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or not find_player(room,user["id"]): return
    join_room(f"game_{code}")
    emit("lobby_state",room_public(room),to=f"game_{code}")

@socketio.on("invite_to_room")
def invite_to_room(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or room["host_id"]!=user["id"]: return
    try: fid=int(data.get("friend_id"))
    except: return
    maxp=int(room.get("max_players",4 if room.get("game")=="parchis_deluxe" else 99))
    if len(room.get("players",[]))>=maxp:
        emit("app_error",{"message":f"La sala ya está completa ({maxp} jugadores)."}); return
    if fid not in connected_users:
        emit("app_error",{"message":"Ese amigo está desconectado."}); return
    emit("room_invitation",{"code":code,"from_name":user["username"],"game":room["game_name"]},to=f"user_{fid}")
    emit("toast",{"message":"Invitación enviada."})

@socketio.on("accept_room_invitation")
def accept_room_invitation(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or room["status"]!="waiting": return
    maxp=int(room.get("max_players",4 if room.get("game")=="parchis_deluxe" else 99))
    if len(room.get("players",[]))>=maxp and not find_player(room,user["id"]):
        emit("app_error",{"message":f"La sala ya está completa ({maxp} jugadores)."}); return
    if not find_player(room,user["id"]):
        if room.get("game")=="parchis_deluxe":
            room["players"].append({"id":user["id"],"name":user["username"],"bot":False,"colors":[],"score":0,"stars":int(user["stars"] or 0)})
        else:
            room["players"].append({"id":user["id"],"name":user["username"],"bot":False,"score":0,"streak":0,"stars":int(user["stars"] or 0)})
    emit("lobby_state",room_public(room),to=f"game_{code}")
    emit("go_to_room",{"code":code,"game":room.get("game")})

@socketio.on("add_bot")
def add_bot(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or room["host_id"]!=user["id"] or room["status"]!="waiting": return
    botn=sum(1 for p in room["players"] if p.get("bot"))+1
    bot = {"id":f"bot_{uuid4().hex[:8]}","name":f"CPU Nova {botn}","bot":True,"score":0,"streak":0}
    if room.get("game") == "bingo90":
        bot["selected_tickets"] = 1
        bot["tickets"] = [generate_spanish_ticket()]
        bot["marked"] = []
        bot["marked_by_ticket"] = [[] for _ in range(bot.get("selected_tickets",1))]
        bot["last_bad_check"] = 0
    room["players"].append(bot)
    emit("lobby_state",room_public(room),to=f"game_{code}")

@socketio.on("remove_bot")
def remove_bot(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or room["host_id"]!=user["id"]: return
    bid=data.get("bot_id")
    room["players"]=[p for p in room["players"] if not (p["id"]==bid and p.get("bot"))]
    emit("lobby_state",room_public(room),to=f"game_{code}")

@socketio.on("start_game")
def start_game(data):
    user=current_user()
    code=str(data.get("code","")).upper()
    room=active_rooms.get(code)
    if not user or not room or room["host_id"]!=user["id"] or room["status"]!="waiting":
        return

    room["status"]="playing"

    if room.get("game") == "bingo90":
        room["drawn"] = []
        room["remaining"] = list(range(1,91))
        room["prizes"] = {}
        room["paused"] = False

        for p in room["players"]:
            normalize_bingo_player(p)
            p["score"] = 0
            p["marked"] = []
            p["marked_by_ticket"] = [[] for _ in range(p.get("selected_tickets",1))]
            p["last_bad_check"] = 0
            # IMPORTANT: preserve exactly the cards selected in the lobby.
            count = max(1, min(4, int(p.get("selected_tickets", 1))))
            p["selected_tickets"] = count
            if len(p["tickets"]) != count:
                p["tickets"] = p["tickets"][:count]
                while len(p["tickets"]) < count:
                    p["tickets"].append(generate_spanish_ticket())

        emit("game_started", {"code":code, "game":"bingo90"}, to=f"game_{code}")
    else:
        room["round"]=-1
        for p in room["players"]:
            p["score"]=0
            p["streak"]=0
        socketio.emit("game_started", {"code":code, "game":room.get("game")}, room=f"game_{code}")


@socketio.on("join_bingo_lobby")
def join_bingo_lobby(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or room.get("game")!="bingo90" or not find_player(room,user["id"]): return
    join_room(f"game_{code}")
    emit("bingo_lobby_state",bingo_public(room,user["id"]))

@socketio.on("bingo_toggle_mark")
def bingo_toggle_mark(data):
    user=current_user()
    code=str(data.get("code","")).upper()
    room=active_rooms.get(code)
    if not user or not room or room.get("game")!="bingo90" or room.get("status")!="playing":
        return

    p=find_player(room,user["id"])
    if not p:
        return
    normalize_bingo_player(p)

    try:
        number=int(data.get("number"))
        ticket_index=int(data.get("ticket_index"))
    except:
        return

    if ticket_index < 0 or ticket_index >= len(p["tickets"]):
        return
    if number not in set(ticket_numbers(p["tickets"][ticket_index])):
        return
    marks=p["marked_by_ticket"][ticket_index]
    if number in marks:
        marks.remove(number)
    else:
        marks.append(number)

    emit("bingo_mark_state", {
        "ticket_index":ticket_index,
        "marked_by_ticket":p["marked_by_ticket"]
    })

@socketio.on("bingo_restart")
def bingo_restart(data):
    user=current_user()
    code=str(data.get("code","")).upper()
    room=active_rooms.get(code)
    if not user or not room or room.get("game")!="bingo90":
        return
    if room.get("host_id") != user["id"]:
        emit("app_error", {"message":"Solo el anfitrión puede repetir la partida."})
        return

    room["status"]="waiting"
    room["drawn"]=[]
    room["remaining"]=list(range(1,91))
    room["paused"]=False
    room["auto_pause_until"]=None
    room["prizes"]={}
    room["bingo_loop_running"]=False
    room["speed"]=8.0

    for p in room["players"]:
        normalize_bingo_player(p)
        p["score"]=0
        p["last_bad_check"]=0
        p["marked_by_ticket"]=[[] for _ in range(p.get("selected_tickets",1))]
        # Nueva tanda: cartones nuevos, manteniendo cantidad elegida.
        if not p.get("bot"):
            p["tickets"]=[generate_spanish_ticket() for _ in range(p.get("selected_tickets",1))]
        else:
            p["tickets"]=[generate_spanish_ticket()]

    socketio.emit("bingo_restart_lobby", {"code":code}, to=f"game_{code}")

@socketio.on("bingo_check_objectives")
def bingo_check_objectives(data):
    user=current_user()
    code=str(data.get("code","")).upper()
    room=active_rooms.get(code)
    if not user or not room or room.get("game")!="bingo90" or room.get("status")!="playing":
        return

    p=find_player(room,user["id"])
    if not p:
        return
    normalize_bingo_player(p)

    now=time.time()
    last=float(p.get("last_bad_check",0))
    if now-last < 10:
        emit("bingo_check_penalty", {"remaining":max(0,10-(now-last))})
        return

    # First, check all non-bingo objectives.
    new_non_bingo = bingo_check_player_objectives(room, p, include_bingo=False)
    if new_non_bingo:
        bingo_pause_for_announcement(room, 3.2)
        emit("bingo_check_result", {"ok":True,"new_prizes":new_non_bingo,"score":p["score"]})
        emit("bingo_prize_awarded", {
            "new_prizes":new_non_bingo,
            "players":[
                {"id":x["id"],"name":x["name"],"bot":x.get("bot",False),"score":x.get("score",0)}
                for x in room["players"]
            ],
            "prizes":room["prizes"]
        }, to=f"game_{code}")
        emit("bingo_announcement", {
            "type":"prize",
            "items":new_non_bingo
        }, to=f"game_{code}")
        return

    # Then check Bingo separately with a verification sequence.
    ticket_index, bingo_ticket = find_completed_bingo_ticket(p, room.get("drawn", []))
    if bingo_ticket is not None and "bingo" not in room["prizes"]:
        room["paused"] = True
        room["auto_pause_until"] = None

        # Award only after the visual verification begins.
        prize_def = next(x for x in BINGO_PRIZES if x[0] == "bingo")
        key, name, points, icon = prize_def
        room["prizes"][key] = [p["id"]]
        p["score"] += points
        bingo_prize = {
            "key":key,"name":name,"points":points,"icon":icon,
            "player_id":p["id"],"player_name":p["name"]
        }

        cells = []
        for r,row in enumerate(bingo_ticket):
            for c,n in enumerate(row):
                if n is not None:
                    cells.append({"r":r,"c":c,"n":n})

        emit("bingo_verify_start", {
            "player_id":p["id"],
            "player_name":p["name"],
            "ticket_index":ticket_index,
            "cells":cells,
            "prize":bingo_prize
        }, to=f"game_{code}")

        socketio.start_background_task(
            finish_bingo_verification,
            code,
            p["id"],
            bingo_prize,
            len(cells)
        )
        return

    p["last_bad_check"]=now
    emit("bingo_check_result", {"ok":False,"penalty":10})

def finish_bingo_verification(code, player_id, bingo_prize, cell_count):
    room=active_rooms.get(code)
    if not room:
        return

    # Let the client animate the 15 cells one by one.
    socketio.sleep(max(3.5, cell_count * 0.24 + 1.0))

    room=active_rooms.get(code)
    if not room:
        return

    p=find_player(room, player_id)
    if not p:
        return

    socketio.emit("bingo_verify_result", {
        "correct":True,
        "player_name":p["name"],
        "prize":bingo_prize
    }, to=f"game_{code}")

    socketio.sleep(2.2)
    room["status"]="finished"
    ranking=sorted(room["players"], key=lambda x:x.get("score",0), reverse=True)
    finalize_game_progress(room,p["id"],"bingo90")
    socketio.emit("bingo_over", {
        "players":[
            {"id":x["id"],"name":x["name"],"score":x.get("score",0),"bot":x.get("bot",False),
             "fake_user":x.get("fake_user",False),"stars":x.get("stars",get_user_stars(x["id"]) if isinstance(x.get("id"),int) else 0)}
            for x in ranking
        ],
        "drawn_count":len(room.get("drawn",[])),
        "bingo_correct":True,
        "bingo_player":p["name"]
    }, to=f"game_{code}")


@socketio.on("join_bingo")
def join_bingo(data):
    user=current_user()
    code=str(data.get("code","")).upper()
    room=active_rooms.get(code)
    if not user or not room or room.get("game")!="bingo90":
        return
    p=find_player(room,user["id"])
    if not p:
        return

    normalize_bingo_player(p)
    join_room(f"game_{code}")

    # Explicitly send this player's selected cards.
    state=bingo_public(room,user["id"])
    emit("bingo_state", state)

    if room["status"]=="playing" and room["host_id"]==user["id"] and not room.get("bingo_loop_running"):
        socketio.start_background_task(bingo_draw_loop, code)

@socketio.on("bingo_set_speed")
def bingo_set_speed(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or room.get("game")!="bingo90" or room["host_id"]!=user["id"]: return
    try:
        speed=float(data.get("speed",4))
    except:
        return
    room["speed"]=max(1.0,min(10.0,speed))
    emit("bingo_speed",{"speed":room["speed"]},to=f"game_{code}")

@socketio.on("bingo_toggle_pause")
def bingo_toggle_pause(data):
    user=current_user(); code=str(data.get("code","")).upper(); room=active_rooms.get(code)
    if not user or not room or room.get("game")!="bingo90" or room["host_id"]!=user["id"]: return
    room["paused"]=not room.get("paused",False)
    emit("bingo_pause",{"paused":room["paused"]},to=f"game_{code}")

@socketio.on("join_match")
def join_match(data):
    user=current_user()
    code=str(data.get("code","")).upper()
    room=active_rooms.get(code)

    if not user or not room or not find_player(room,user["id"]):
        return

    join_room(f"game_{code}")
    emit("scoreboard",room_public(room))

    # Si el anfitrión es el primero en entrar, arranca la primera ronda.
    if room["round"]==-1 and room["host_id"]==user["id"] and room.get("status")=="playing":
        start_round(code)
        return

    # Si la ronda ya está activa, el jugador que acaba de entrar recibe
    # inmediatamente la pregunta actual. Esto evita quedarse en "Prepárate".
    if room.get("status")=="playing" and room.get("round",-1)>=0:
        try:
            qi=room["question_order"][room["round"]]
            q=QUESTIONS[qi]
            elapsed=max(0,time.time()-float(room.get("round_started") or time.time()))
            remaining=max(0.0,10.0-elapsed)

            emit("new_question",{
                "round":room["round"]+1,
                "total":len(room["question_order"]),
                "q":q["q"],
                "a":q["a"],
                "emoji":q["emoji"],
                "seconds":10,
                "remaining":remaining,
                "resume":True
            })

            # Si ese jugador ya había respondido antes de reconectar,
            # dejamos su pantalla bloqueada.
            if user["id"] in room.get("answered",set()):
                emit("already_answered",{})
        except Exception:
            pass

def start_round(code):
    room=active_rooms.get(code)
    if not room or room.get("status")!="playing":
        return

    room["round_advancing"]=False
    room["round"]+=1

    if room["round"]>=len(room["question_order"]):
        room["status"]="finished"
        ranking=sorted(room["players"],key=lambda p:p["score"],reverse=True)
        winner_id=ranking[0]["id"] if ranking else None
        finalize_game_progress(room,winner_id,"reto_relampago")
        socketio.emit("game_over",{
            "players":[
                {"id":p["id"],"name":p["name"],"score":p["score"],"bot":p.get("bot",False),
                 "fake_user":p.get("fake_user",False),"stars":p.get("stars",get_user_stars(p["id"]) if isinstance(p.get("id"),int) else 0)}
                for p in ranking
            ]
        },room=f"game_{code}")
        return

    qi=room["question_order"][room["round"]]
    q=QUESTIONS[qi]
    room["answered"]=set()
    room["round_started"]=time.time()
    room["round_token"]=int(room.get("round_token",0))+1
    token=room["round_token"]

    socketio.emit("new_question",{
        "round":room["round"]+1,
        "total":len(room["question_order"]),
        "q":q["q"],
        "a":q["a"],
        "emoji":q["emoji"],
        "seconds":10
    },room=f"game_{code}")

    # CPU: respuesta rápida y fiable.
    for p in list(room["players"]):
        if p.get("bot"):
            delay=random.uniform(.9,2.8)
            socketio.start_background_task(bot_answer,code,p["id"],qi,token,delay)

    # Cierre de seguridad: una ronda JAMÁS queda bloqueada.
    socketio.start_background_task(round_timeout,code,qi,token,10.2)


def bot_answer(code,bid,qi,token,delay):
    socketio.sleep(delay)
    room=active_rooms.get(code)
    if not room or room.get("status")!="playing":
        return
    if room.get("round_token")!=token:
        return
    if room["round"]<0 or room["question_order"][room["round"]]!=qi:
        return
    if bid in room["answered"]:
        return

    q=QUESTIONS[qi]
    # CPU acierta aproximadamente 72 %.
    if random.random()<.72:
        choice=q["ok"]
    else:
        wrong=[i for i in range(len(q["a"])) if i!=q["ok"]]
        choice=random.choice(wrong)

    result=process_answer(room,bid,choice)
    if result:
        correct,ok=result
        socketio.emit("cpu_answered",{
            "player_id":bid,
            "correct":correct
        },room=f"game_{code}")
        socketio.emit("scoreboard",room_public(room),room=f"game_{code}")

    maybe_finish_round(code,token)


def round_timeout(code,qi,token,seconds):
    socketio.sleep(seconds)
    room=active_rooms.get(code)
    if not room or room.get("status")!="playing":
        return
    if room.get("round_token")!=token:
        return
    if room["round"]<0 or room["question_order"][room["round"]]!=qi:
        return

    # Los jugadores que no respondieron pierden la ronda.
    for p in room["players"]:
        if p["id"] not in room["answered"]:
            room["answered"].add(p["id"])
            p["streak"]=0

    socketio.emit("round_timeout",{},room=f"game_{code}")
    maybe_finish_round(code,token,force=True)


def process_answer(room,pid,choice):
    if pid in room["answered"]:
        return
    room["answered"].add(pid)
    p=find_player(room,pid)
    if not p:
        return

    qi=room["question_order"][room["round"]]
    q=QUESTIONS[qi]
    elapsed=max(0,time.time()-room["round_started"])
    correct=int(choice)==q["ok"]

    if correct:
        p["streak"]+=1
        speed=max(0,600-int(elapsed*70))
        bonus=min(500,(p["streak"]-1)*100)
        p["score"]+=1000+speed+bonus
    else:
        p["streak"]=0

    return correct,q["ok"]


@socketio.on("submit_answer")
def submit_answer(data):
    user=current_user()
    code=str(data.get("code","")).upper()
    room=active_rooms.get(code)

    if not user or not room or room.get("game")!="reto_relampago" or room["status"]!="playing":
        return
    if not find_player(room,user["id"]) or user["id"] in room["answered"]:
        return

    try:
        choice=int(data.get("choice"))
    except:
        return

    result=process_answer(room,user["id"],choice)
    if not result:
        return

    correct,ok=result
    emit("answer_result",{"correct":correct,"correct_index":ok})
    socketio.emit("scoreboard",room_public(room),room=f"game_{code}")
    maybe_finish_round(code,room.get("round_token"))


def maybe_finish_round(code,token=None,force=False):
    room=active_rooms.get(code)
    if not room or room.get("status")!="playing":
        return
    if token is not None and room.get("round_token")!=token:
        return

    everyone=len(room["answered"])>=len(room["players"])
    if not everyone and not force:
        return

    # Evita que CPU + humano + timeout abran dos rondas a la vez.
    if room.get("round_advancing"):
        return
    room["round_advancing"]=True
    room["round_token"]=int(room.get("round_token",0))+1

    socketio.emit("round_complete",{
        "next_in":1.15
    },room=f"game_{code}")

    socketio.sleep(1.15)
    if room.get("status")=="playing":
        start_round(code)


init_db()

register_parchis(app, socketio, active_rooms, current_user, find_player, friends_of, connected_users, finalize_game_progress)
register_uno_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_domino_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_dobble_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_subastado_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_barquitos_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_oca_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_serpientes_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_brisca_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_conecta4_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_damas_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_ahorcado_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_poker_deluxe(app, socketio, active_rooms, current_user, friends_of)
register_blackjack_deluxe(app, socketio, active_rooms, current_user, friends_of)

if __name__=="__main__":
    init_db()
    socketio.run(app,host="0.0.0.0",port=5000,debug=True,allow_unsafe_werkzeug=True)
