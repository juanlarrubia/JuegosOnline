V24 - PROGRESIÓN, ESTRELLAS, MATCHMAKING Y TORNEOS
==================================================

NUEVO
- Cada usuario tiene estrellas persistentes (empieza con 0).
- 20 medallas por cada juego actual (160 medallas en total).
- Las primeras medallas de participación se desbloquean automáticamente al jugar.
- Bingo, Reto Relámpago y Parchís registran también resultados en servidor.
- UNO, Dominó y Batalla Naval reportan victoria/derrota local contra CPU.
- Medallas y estrellas se guardan en usuarios.db.

MODOS DE JUEGO
Antes de entrar a cada juego:
1. Con amigos.
2. Contra CPU.
3. Rival aleatorio.

RIVAL ALEATORIO
- Busca otro usuario que esté esperando el mismo juego.
- Si no aparece nadie en 4 segundos, crea un rival virtual con nombre y estrellas.
- El rival virtual está controlado por CPU, pero visualmente aparece como un jugador.

TORNEOS
- Nuevo botón TORNEOS en menú principal.
- Se elige un amigo.
- Por defecto se seleccionan todos los juegos.
- Por defecto cada serie requiere 3 victorias.
- El rival recibe invitación.
- Al aceptar, se muestra un marcador por cada juego.
- Se puede iniciar una partida de torneo desde cada juego.
- Los resultados de juegos ya conectados al sistema actualizan progresión.
- A medida que terminemos los juegos que aún están en desarrollo, se conectarán
  sus finales al marcador del torneo.

MÓVIL
Las nuevas pantallas (modo de juego, matchmaking, medallas y torneos) incluyen
diseño responsive para móvil.
