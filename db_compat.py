import os, re, sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def _translate(sql):
        q = sql.replace("?", "%s")
        q = q.replace("MAX(best_streak,current_streak+1)", "GREATEST(best_streak,current_streak+1)")
        q = q.replace("MAX(best_score,%s)", "GREATEST(best_score,%s)")
        q = q.replace("username LIKE %s", "username ILIKE %s")
        if re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", q, re.I):
            q = re.sub(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", q, count=1, flags=re.I)
            q = q.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return q

    class CursorAdapter:
        def __init__(self, cursor):
            self.cursor = cursor
            self.lastrowid = None
        def execute(self, sql, params=()):
            if sql.strip().upper().startswith("PRAGMA TABLE_INFO(USUARIOS)"):
                self.cursor.execute("SELECT column_name AS name FROM information_schema.columns WHERE table_schema='public' AND table_name='usuarios' ORDER BY ordinal_position")
                return self
            q = _translate(sql)
            wants_id = bool(re.match(r"^\s*INSERT\s+INTO\s+(usuarios|torneos)\b", q, re.I)) and "RETURNING" not in q.upper()
            if wants_id:
                q = q.rstrip().rstrip(";") + " RETURNING id"
            self.cursor.execute(q, params or ())
            if wants_id:
                row = self.cursor.fetchone()
                self.lastrowid = int(row["id"]) if row else None
            return self
        def fetchone(self): return self.cursor.fetchone()
        def fetchall(self): return self.cursor.fetchall()

    class ConnectionAdapter:
        def __init__(self, conn): self.conn = conn
        def execute(self, sql, params=()):
            return CursorAdapter(self.conn.cursor(cursor_factory=RealDictCursor)).execute(sql, params)
        def executescript(self, _script):
            schema = [
                "CREATE TABLE IF NOT EXISTS usuarios (id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, password_hash TEXT NOT NULL, email TEXT, display_name TEXT, theme TEXT NOT NULL DEFAULT 'violeta', avatar_style TEXT NOT NULL DEFAULT 'inicial', sound_enabled INTEGER NOT NULL DEFAULT 1, stars INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_username_ci ON usuarios(LOWER(username))",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_ci ON usuarios(LOWER(email)) WHERE email IS NOT NULL AND email <> ''",
                "CREATE TABLE IF NOT EXISTS amistades (id BIGSERIAL PRIMARY KEY, usuario_id BIGINT NOT NULL, amigo_id BIGINT NOT NULL, estado TEXT NOT NULL DEFAULT 'pendiente', creado_en TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, UNIQUE(usuario_id, amigo_id))",
                "CREATE TABLE IF NOT EXISTS progreso_juegos (user_id BIGINT NOT NULL, game TEXT NOT NULL, plays INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, cpu_wins INTEGER NOT NULL DEFAULT 0, online_wins INTEGER NOT NULL DEFAULT 0, current_streak INTEGER NOT NULL DEFAULT 0, best_streak INTEGER NOT NULL DEFAULT 0, best_score INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, game))",
                "CREATE TABLE IF NOT EXISTS medallas_usuario (user_id BIGINT NOT NULL, game TEXT NOT NULL, medal_key TEXT NOT NULL, earned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, game, medal_key))",
                "CREATE TABLE IF NOT EXISTS partidas_contadas (user_id BIGINT NOT NULL, game TEXT NOT NULL, room_code TEXT NOT NULL, PRIMARY KEY(user_id, game, room_code))",
                "CREATE TABLE IF NOT EXISTS torneos (id BIGSERIAL PRIMARY KEY, creator_id BIGINT NOT NULL, opponent_id BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'pendiente', created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)",
                "CREATE TABLE IF NOT EXISTS torneo_juegos (id BIGSERIAL PRIMARY KEY, torneo_id BIGINT NOT NULL, game TEXT NOT NULL, wins_needed INTEGER NOT NULL DEFAULT 3, creator_wins INTEGER NOT NULL DEFAULT 0, opponent_wins INTEGER NOT NULL DEFAULT 0, orden INTEGER NOT NULL DEFAULT 0)"
            ]
            for statement in schema: self.execute(statement)
            return self
        def commit(self): self.conn.commit()
        def rollback(self): self.conn.rollback()
        def close(self): self.conn.close()

    def pg_connect(*_args, **_kwargs):
        return ConnectionAdapter(psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require"))
    def install():
        sqlite3.connect = pg_connect
        sqlite3.IntegrityError = psycopg2.IntegrityError
else:
    def install(): pass
