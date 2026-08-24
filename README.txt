APP JUEGOS ONLINE - V3

Incluye:
- Usuarios únicos y login.
- Amigos.
- Estado online.
- Salas creadas por un anfitrión.
- Entrada mediante código de sala.
- Invitación de amigos.
- Sin límite fijo de jugadores en la lógica de la sala.
- El anfitrión decide cuándo comenzar.
- Rivales CPU para jugar solo o completar la sala.
- Primer juego: RETO RELÁMPAGO.
- Marcador, rachas, velocidad y preguntas sincronizadas en tiempo real.

PARA PROBAR
1) pip install -r requirements.txt
2) python app.py
3) abre http://127.0.0.1:5000

Para simular varios usuarios en un PC, usa navegadores/perfiles distintos.

NOTA
Sigue siendo una versión de desarrollo local. Las salas viven en memoria del servidor:
si reinicias app.py desaparecen. Los usuarios y amistades sí permanecen en usuarios.db.
Cuando publiquemos en Internet, migraremos usuarios/salas a servicios centrales (por ejemplo
PostgreSQL + Redis) para múltiples móviles y servidores.


NOVEDADES V4
- 12 temas de color persistentes por usuario.
- Correo electrónico asociado y único por cuenta.
- Nombre visible configurable.
- Cambio de contraseña verificando la contraseña actual.
- Estilo de avatar configurable.
- Preferencia para sonidos.
- Pantalla de ajustes y perfil.
- Migración automática de usuarios.db de versiones anteriores.

IMPORTANTE SOBRE EL CORREO
En esta versión local el correo queda asociado a la cuenta en usuarios.db.
Cuando la app esté publicada en Internet, permitirá identificar la misma cuenta
desde cualquier equipo. Aún NO se envían correos de recuperación; eso requiere
conectar un servicio de email real en la versión online.

NOVEDADES V5 - BINGO 90 DELUXE
- Nuevo juego completo de Bingo de 90 bolas.
- Cartones españoles 3x9 con 15 números.
- Bolas animadas e historial.
- Voz del número y efecto de sonido.
- Velocidad 1-10 segundos controlada por el anfitrión.
- Pausa/reanudación.
- Premios con puntos: Inicio rápido 150, Línea 250, 4 esquinas 300,
  Vertical 350, Doble línea 500, Borde exterior 700 y Bingo 1200.
- Clasificación en vivo; gana quien suma más puntos.

CORRECCIONES V5.1
- Corregido cursor de prohibido en los botones activos de Crear sala.
- Eliminado código antiguo de invitaciones mezclado con el sistema actual.
- Corregido receptor room_invitation en el menú.
- Invitaciones de Bingo redirigen correctamente a /sala_bingo/CODIGO.
- Confirmación visual 'ENVIADA ✓' al invitar desde la sala de Bingo.

NOVEDADES V6 - BINGO
- Marcado manual de números.
- 1 a 4 cartones por jugador.
- Bombo visual con 18 bolas animadas.
- Contador descendente de bolas restantes.
- Solo 6 últimas bolas visibles.
- Tablero completo 1-90 con extraídas resaltadas.
- Comprobación manual de objetivos.
- Penalización de 10 segundos si se comprueba sin objetivo nuevo.

V6.2
- Corregida selección de 1 a 4 cartones: se generan y se muestran en la propia sala antes de empezar.
- La locución ya no dice la palabra 'número'.
- Añadidos cantos especiales: 15 'La niña bonita', 22 'Los dos patitos', 33 'La edad de Cristo', etc.
- Para bolas sin apodo: dice la bola y sus cifras, por ejemplo '35. El 3 y el 5'.

V6.3 - CORRECCIÓN CARTONES EN PARTIDA
- Corregido backend antiguo 'ticket' vs nuevo 'tickets'.
- Los 1-4 cartones elegidos en la sala se conservan exactamente al iniciar.
- bingo_public envía explícitamente los cartones al propietario.
- join_bingo normaliza jugadores antiguos y entrega sus cartones.
- Marcado manual y comprobación de objetivos quedan en el mismo modelo multi-cartón.

V6.4 - CORRECCIONES
- Reto Relámpago vuelve a crear sala correctamente (corregido NameError de 'room').
- Entrada por código redirige correctamente según sea Bingo o Reto Relámpago.
- En Bingo, al salir una bola NO se ilumina, habilita ni señala su casilla en los cartones.
- Solo se tacha una casilla cuando el jugador la pulsa manualmente.
- Eliminado el texto bajo la bola extraída (por ejemplo '57. El 5 y el 7').
- Se mantiene la locución por voz, sin decir la palabra 'número'.

V6.5 - PREMIOS Y COMPROBACIÓN DE BINGO
- Cuando se consigue un objetivo válido, el bombo se pausa automáticamente.
- Se anuncia por voz el jugador y el premio.
- Tras unos segundos, el bombo se reanuda automáticamente.
- Al detectar Bingo, el bombo se detiene y se anuncia 'Comprobando bingo'.
- El cartón del jugador se revisa visualmente celda a celda.
- Cada casilla se ilumina progresivamente durante la comprobación.
- Si el Bingo es correcto, se anuncia 'Bingo correcto' y finaliza la partida.

V7: Parchís integrado con CPU, máximo 4 jugadores e invitación de amigos online.

V8 - PARCHÍS DELUXE REHECHO
- Tablero clásico visual con 68 casillas, casas, seguros, salidas, pasillos y meta.
- Siempre se tiran 2 dados.
- Dos movimientos por turno, pudiendo usar la misma ficha o dos distintas.
- Salida obligatoria si un dado es 5 o ambos suman 5.
- Dobles repiten turno.
- Tercer doble consecutivo: última ficha movida vuelve a casa salvo pasillo/meta.
- Barreras de dos fichas del mismo color bloquean paso.
- Con dobles se obliga a abrir barrera si es posible.
- Captura: ficha rival a casa + movimiento extra de 20.
- Ficha en meta: movimiento extra de 10.
- Rebote en pasillo de llegada al sobrepasar meta.
- Elección manual de colores.
- 2 jugadores: 2 colores por jugador.
- 3/4 jugadores: 1 color por jugador.
- CPU selecciona colores restantes y juega con dos dados.
- Animación casilla a casilla.
- Sonidos diferenciados: dados, pasos, salida, captura, meta y tercer doble.

V12 - PARCHÍS TABLERO CORREGIDO
- Eliminado el recorrido rectangular/interpolado.
- Las 68 casillas tienen ahora posiciones fijas dentro de los pasillos blancos.
- Recorrido con cuatro brazos tipo Parchís tradicional.
- Seguros visibles en gris con círculo y estrella.
- Salidas coloreadas para rojo, amarillo, verde y azul.
- Los pasillos de llegada quedan rectos hacia la meta.

V13
- Parchís: las casillas ya no pisan las casas; quedan dentro de los corredores blancos.
- Seguros visibles con círculo gris y estrella.
- Inicio de Parchís reforzado: Socket.IO + consulta HTTP cada segundo.
- Cualquier jugador que siga en la sala entra automáticamente cuando status=playing.
